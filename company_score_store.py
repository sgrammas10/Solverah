"""
company_score_store.py -- the web layer's only door to stored company scores.

The company-side analogue of assessment_store.py. Everything that reads or writes
`company_dimension_score`, `scorer_run` and `dimension_score_citation` goes through here,
so there is one place to audit what the match surface is allowed to see and one place the
ingest transaction boundary lives.

WHY THIS MODULE EXISTS AT ALL
-----------------------------
Until this change nothing in the app wrote `company_dimension_score` -- every company score
the LLM extractor had ever produced lived in loose JSON files, and the only code touching
the table was a constraint test. Two consequences: no match surface could be built on the
scores, and no stored score could be traced to the rubric wording that produced it. The
second is why anchor wording felt like a blocker on everything downstream. With a
`scorer_run` behind every score, changing the wording is a re-run, not a rebuild.

WHAT THIS MODULE DELIBERATELY DOES NOT IMPORT
---------------------------------------------
Not `openai`, and nothing from `causal_graph` -- `causal_graph/scorer_pipeline.py` imports
openai at module scope, so importing any of it here would drag an API client into the web
process to read a database row. This module takes plain dicts. The extractor, the citation
verifier and the packets stay research-side; converting their output into the dict shapes
below is the caller's job (see Scripts/backfill_company_scores.py, which may import
causal_graph precisely because it is not the app).

THE CONFIDENCE RULE (D-17(b) mirrored onto the company side)
-------------------------------------------------------------
`company_dimension_score.confidence` is STORED and must not be FILTERED or WEIGHTED by,
pending S-60. Round 1 measured company-side confidence not tracking reliability:
Spearman(B-C band distance, mean confidence) = -0.073, with `decision` carrying 3.2x
`pace`'s disagreement at ABOVE-average confidence. A confidence weight built on that would
weight the worst cells as heavily as the best. Nothing consumes the field yet, which is
exactly why the rule is cheap to state now and expensive to retrofit later.

Storing it is still right: it is the extractor's own report and re-deriving it later is
impossible. `CONFIDENCE_IS_NOT_A_WEIGHT` below is the rule in one string, and
tests/test_company_confidence_unused.py enforces it the way test_employer_visibility.py
enforces D-01 -- as reachability, so a module that reaches for the field fails at the
moment someone writes the import rather than after it has shipped into a ranking.
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Mapping, Optional

__all__ = [
    "CONFIDENCE_IS_NOT_A_WEIGHT",
    "get_company_scores",
    "get_score_citations",
    "ingest_extractor_result",
    "noncompany_support",
]


#: The rule, stated once, quoted by the guard test so the two cannot drift.
CONFIDENCE_IS_NOT_A_WEIGHT = (
    "company_dimension_score.confidence is stored but must not be filtered or weighted "
    "by, pending S-60: round 1 measured it not tracking reliability "
    "(Spearman(band distance, mean confidence) = -0.073)."
)

#: Metadata that identifies one scorer run. Re-ingesting a run means presenting this exact
#: tuple again; see _find_or_create_run for why it is the whole of the metadata and not a
#: shorter natural key.
_RUN_IDENTITY = (
    "model",
    "temperature",
    "temperature_honored",
    "reasoning_effort",
    "rubric_version",
    "packet_version",
    "run_at",
    "notes",
)


def _normalized_run(run: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and fill a scorer_run metadata dict.

    `model` is required and must be a pinned snapshot string. There is no default and no
    inference: an alias like 'gpt-5.5' silently re-points when the vendor ships an update,
    and a stored score that cannot say which model produced it is the exact thing this
    table was added to prevent.
    """
    missing = [k for k in ("model", "rubric_version", "packet_version") if not run.get(k)]
    if missing:
        raise ValueError(
            "scorer_run needs %s; got %r. rubric_version in particular is never inferred "
            "-- a mislabelled rubric poisons the cross-rubric comparison these rows exist "
            "to support." % (", ".join(missing), dict(run))
        )
    if "temperature_honored" not in run:
        raise ValueError(
            "scorer_run.temperature_honored is required and has no default: near-zero "
            "variance from an ignored temperature is not the same finding as near-zero "
            "variance from a better model."
        )
    return {
        "model": run["model"],
        "temperature": run.get("temperature"),
        "temperature_honored": bool(run["temperature_honored"]),
        "reasoning_effort": run.get("reasoning_effort"),
        "rubric_version": run["rubric_version"],
        "packet_version": run["packet_version"],
        "run_at": run.get("run_at"),
        "notes": run.get("notes"),
    }


def _find_or_create_run(fields: Mapping[str, Any]):
    """Return the ScorerRun matching *fields* exactly, creating it if there is none.

    Identity is the WHOLE metadata tuple, `run_at` and `notes` included, because
    `scorer_run` has no narrower natural key and inventing one would be a guess about which
    fields may repeat. Two ingests of the same run present the same tuple and collapse onto
    one row, which is what makes ingest idempotent.

    The limit is worth stating plainly: two genuinely different runs sharing byte-identical
    metadata -- same model, rubric, packet version, timestamp and notes -- are treated as
    one run. `notes` is free text and is the intended way to tell such a pair apart.

    A caller who supplies no `run_at` always gets a NEW run, because the lookup then asks
    for `run_at IS NULL` and the column never is. That is the right answer for a live run
    stamped with `now()`, and it is why a backfill -- which must be re-runnable -- passes
    the run's real timestamp explicitly.
    """
    from model import ScorerRun

    query = ScorerRun.query
    for name in _RUN_IDENTITY:
        query = query.filter(getattr(ScorerRun, name) == fields[name])
    existing = query.first()
    if existing is not None:
        return existing, False

    from model import db

    # run_at is left to the server default when the caller gives none, so a live run gets
    # `now()` and a backfill gets the date the run was actually made.
    run = ScorerRun(**{k: v for k, v in fields.items() if v is not None or k != "run_at"})
    db.session.add(run)
    db.session.flush()
    return run, True


def _citation_key(citation: Mapping[str, Any]) -> tuple:
    return (
        citation["quote_text"],
        bool(citation["matched"]),
        citation.get("matched_excerpt_id"),
        citation.get("source_tag"),
    )


def _normalized_citation(citation: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one citation. An UNMATCHED quote is kept, with both provenance fields null.

    Discarding it would leave the score looking better evidenced than it is; a quote the
    verifier could not find in the packet is the failure this table exists to surface. The
    database carries the same rule as a CHECK constraint -- this is the readable half.
    """
    matched = bool(citation["matched"])
    eid = citation.get("matched_excerpt_id")
    tag = citation.get("source_tag")
    if not matched and (eid is not None or tag is not None):
        raise ValueError(
            "citation %r is unmatched but carries provenance (%r, %r). An unverified "
            "quote has no known provenance to report." % (citation["quote_text"], eid, tag)
        )
    if matched and (eid is None or tag is None):
        raise ValueError(
            "citation %r is matched but is missing an excerpt id or source tag; both are "
            "the verifier's output and both are required when a quote verifies."
            % (citation["quote_text"],)
        )
    return {
        "quote_text": citation["quote_text"],
        "matched": matched,
        "matched_excerpt_id": eid,
        "source_tag": tag,
    }


def _sync_citations(score, citations: list[dict[str, Any]]) -> int:
    """Make the stored citation set for *score* equal *citations*, and report how many rows
    were written.

    Left untouched when the sets already agree, which is the re-ingest case and keeps row
    ids stable. Replaced wholesale when they differ -- the same run producing a different
    citation set is a contradiction, and the incoming set is the one that came with the
    run being ingested.
    """
    from model import db, DimensionScoreCitation

    existing = DimensionScoreCitation.query.filter_by(
        company_dimension_score_id=score.id
    ).all()
    if sorted(_citation_key(_as_dict(c)) for c in existing) == sorted(
        _citation_key(c) for c in citations
    ):
        return 0

    for row in existing:
        db.session.delete(row)
    for citation in citations:
        db.session.add(
            DimensionScoreCitation(company_dimension_score_id=score.id, **citation)
        )
    return len(citations)


def _as_dict(citation) -> dict[str, Any]:
    return {
        "quote_text": citation.quote_text,
        "matched": citation.matched,
        "matched_excerpt_id": citation.matched_excerpt_id,
        "source_tag": citation.source_tag,
    }


def ingest_extractor_result(
    *,
    company_id: int,
    as_of: datetime.date,
    run: Mapping[str, Any],
    dimensions: Iterable[Mapping[str, Any]],
    source: str = "scraped",
    is_ground_truth: bool = False,
) -> dict[str, Any]:
    """Write one extractor result -- run, scores and citations -- in ONE transaction.

    Args:
        company_id: an existing `company` row.
        as_of: the date the run was MADE, never today. These rows describe what the
            extractor thought then, and backdating them honestly is what lets two runs be
            compared at all.
        run: scorer_run metadata; see _normalized_run for what is required.
        dimensions: one mapping per dimension --
            ``{"dimension_key", "score", "confidence", "citations": [...]}`` where each
            citation is ``{"quote_text", "matched", "matched_excerpt_id", "source_tag"}``.
        source: 'scraped' means LLM-produced, 'researched' means human ground truth
            (per the PROPOSED DDL). A 'researched' or 'declared' row gets no scorer_run.
        is_ground_truth: flags the companies the scraped model is calibrated against.

    Re-ingesting the same run is a no-op on row counts: the run collapses onto its existing
    row by identity, each score is found by the five-column key and updated in place, and
    citations are left alone when they already match.

    Returns a summary dict of what was created or updated.
    """
    from model import db, CompanyDimensionScore

    fields = _normalized_run(run)
    scorer_run, run_created = _find_or_create_run(fields)
    # Only LLM-produced rows carry a scorer run; the column is NULL for the other two
    # sources and the uniqueness key is NULLS NOT DISTINCT so those keep de-duplicating
    # exactly as they did before scorer_run_id existed.
    scorer_run_id = scorer_run.id if source == "scraped" else None

    scores_created = scores_updated = citations_written = 0

    for entry in dimensions:
        citations = [_normalized_citation(c) for c in entry.get("citations", ())]
        score_row = CompanyDimensionScore.query.filter_by(
            company_id=company_id,
            dimension_key=entry["dimension_key"],
            source=source,
            as_of=as_of,
            scorer_run_id=scorer_run_id,
        ).first()

        if score_row is None:
            score_row = CompanyDimensionScore(
                company_id=company_id,
                dimension_key=entry["dimension_key"],
                score=entry["score"],
                # Stored, never filtered or weighted by -- see the module docstring.
                confidence=entry["confidence"],
                source=source,
                as_of=as_of,
                is_ground_truth=is_ground_truth,
                scorer_run_id=scorer_run_id,
            )
            db.session.add(score_row)
            scores_created += 1
        else:
            score_row.score = entry["score"]
            score_row.confidence = entry["confidence"]
            score_row.is_ground_truth = is_ground_truth
            scores_updated += 1
        db.session.flush()

        citations_written += _sync_citations(score_row, citations)

    db.session.commit()
    return {
        "scorer_run_id": scorer_run.id,
        "scorer_run_created": run_created,
        "scores_created": scores_created,
        "scores_updated": scores_updated,
        "citations_written": citations_written,
    }


def get_company_scores(
    company_id: int, rubric_version: str, *, source: str = "scraped"
) -> list[dict[str, Any]]:
    """Scores for one company under one rubric version, newest run first.

    The read the match surface will use. `rubric_version` is required rather than
    defaulting to "the latest": two rubrics now legitimately coexist for one company on one
    day, so a caller that does not say which one it means is asking an ambiguous question.

    `confidence` is returned because this module is the sanctioned doorway for it. Callers
    may display it; they may not rank, filter or weight by it (see the module docstring).
    """
    from model import CompanyDimensionScore, ScorerRun

    rows = (
        CompanyDimensionScore.query.join(
            ScorerRun, CompanyDimensionScore.scorer_run_id == ScorerRun.id
        )
        .filter(
            CompanyDimensionScore.company_id == company_id,
            CompanyDimensionScore.source == source,
            ScorerRun.rubric_version == rubric_version,
        )
        .order_by(ScorerRun.run_at.desc(), CompanyDimensionScore.dimension_key)
        .all()
    )
    return [
        {
            "id": r.id,
            "dimension_key": r.dimension_key,
            "score": r.score,
            "confidence": r.confidence,
            "as_of": r.as_of,
            "is_ground_truth": r.is_ground_truth,
            "scorer_run_id": r.scorer_run_id,
        }
        for r in rows
    ]


def get_score_citations(score_ids: Iterable[int]) -> dict[int, list[dict[str, Any]]]:
    """The citation set behind each score, keyed by `company_dimension_score.id`.

    Unmatched quotes are included. A caller showing "the evidence behind this score" that
    quietly dropped them would show a score as better supported than it is, which is the
    presentation failure the table was built to prevent.
    """
    from model import DimensionScoreCitation

    ids = list(score_ids)
    if not ids:
        return {}

    rows = DimensionScoreCitation.query.filter(
        DimensionScoreCitation.company_dimension_score_id.in_(ids)
    ).order_by(DimensionScoreCitation.id).all()

    out: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
    for row in rows:
        out[row.company_dimension_score_id].append(_as_dict(row))
    return out


def noncompany_support(
    company_id: Optional[int] = None, *, rubric_version: Optional[str] = None
) -> dict[int, bool]:
    """Per scraped score: is at least one MATCHED quote behind it non-company-authored?

    The 08-10 decision-3 measurement -- a score above 0.7 should have at least one
    non-company-authored source behind it. A MEASUREMENT, not an enforced cap.

    This is the PROPOSED DDL's closing query, and it is deliberately the same computation
    as ``causal_graph/scorer_pipeline.noncompany_support()``. The two must never be allowed
    to diverge: one runs over a live ScorerResult before anything is stored, the other over
    the stored rows, and a company that looked supported in the pipeline and unsupported in
    the database (or the reverse) would make both numbers untrustworthy without saying
    which one moved. In particular both require ``matched`` to be true -- a quote the
    verifier could not find cannot count as evidence of anything, which is the entire
    reason the verifier was built before the flag was trusted. If either side changes,
    change both.

    Returns:
        {company_dimension_score_id: bool}, for scraped rows only.
    """
    from model import db, CompanyDimensionScore, DimensionScoreCitation, ScorerRun

    query = (
        db.session.query(
            CompanyDimensionScore.id,
            db.func.bool_or(
                db.and_(
                    DimensionScoreCitation.source_tag == "noncompany",
                    DimensionScoreCitation.matched,
                )
            ),
        )
        .outerjoin(
            DimensionScoreCitation,
            DimensionScoreCitation.company_dimension_score_id == CompanyDimensionScore.id,
        )
        .filter(CompanyDimensionScore.source == "scraped")
        .group_by(CompanyDimensionScore.id)
    )
    if company_id is not None:
        query = query.filter(CompanyDimensionScore.company_id == company_id)
    if rubric_version is not None:
        query = query.join(
            ScorerRun, CompanyDimensionScore.scorer_run_id == ScorerRun.id
        ).filter(ScorerRun.rubric_version == rubric_version)

    # bool_or over no rows is NULL, which is 'no non-company support', not 'unknown'.
    return {score_id: bool(supported) for score_id, supported in query.all()}
