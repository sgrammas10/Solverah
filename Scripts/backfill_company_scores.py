"""Load a historical LLM extractor run into scorer_run + company_dimension_score.

Two real runs survive from 2026-09-01, six packets x six dimensions each. Both scored the
same six companies from the same de-identified packets under DIFFERENT rubric anchor
wording, and neither could be stored until scorer_run existed -- the old four-column
uniqueness key refused the second one outright. Loading both is what makes the comparison
the scorer sprint exists for ("did the rubric move this, or did the model?") a query
instead of a diff of two JSON files.

    python -m Scripts.backfill_company_scores \
        --results ../decision_test/causal_graph/results/all_dims_evidence_2026-09-01.json \
        --rubric-version v1-frozen-2026-08-15 \
        --run-at 2026-09-01 \
        --notes "S-58 round 1, v1 anchors"

RUBRIC VERSION IS A REQUIRED ARGUMENT AND IS NEVER INFERRED
-----------------------------------------------------------
Neither results file records the rubric it was scored under -- which is precisely the gap
these tables close. There is no default and no guess from the filename: a mislabelled
rubric_version poisons the exact comparison this whole job exists to enable, and it would
do so silently, because a wrong label looks identical to a right one in every later query.
The path is an argument for the same reason -- the v1 file lives OUTSIDE this repo and
hardcoding a path to a sibling working directory is how a script stops working the day
someone reorganises their Desktop.

WHY THIS SCRIPT MAY IMPORT causal_graph AND company_score_store MAY NOT
-----------------------------------------------------------------------
`causal_graph/scorer_pipeline.py` imports openai at module scope. Importing it from the
web layer would drag an API client into the request path to read a database row, so
company_score_store.py takes plain dicts and this script does the conversion. A one-shot
backfill run by hand is exactly where that import belongs.

It is an IMPORT rather than a port on purpose: `parse_excerpts` and `verify_quote` are
pure and need no API key, and a second copy of the citation verifier is a copy that drifts
from the one the pipeline actually uses. **No network call is made by this script.**

RECOMPUTING PROVENANCE
----------------------
The results files record only whether each quote `verified`; the v3 file carries no excerpt
id and no source tag at all. Both are recomputed here by running every quote back through
the same verifier against the de-identified packets in
Solverah_IP/ground_truth/anonymization/.

That recomputation was checked against the v1 file, which happens to have kept its own
`eid` and `source_tag`: all 106 of its quotes reproduce exactly. The v3 file has no such
record, and that agreement on v1 is the evidence that its recomputed values are right too.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
# causal_graph has no __init__.py -- it is a directory of independently-runnable scripts,
# which is this project's convention for research code (see reidentification_attack.py).
if str(REPO_ROOT / "causal_graph") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "causal_graph"))


#: packet -> company, from causal_graph/reidentification_attack.py's GROUND_TRUTH. Read
#: from that module rather than retyped, so the two cannot disagree about which packet is
#: which company -- a mix-up that would be invisible in every downstream query.
def _packet_companies() -> dict[str, str]:
    import reidentification_attack

    return {pid: meta["company"] for pid, meta in reidentification_attack.GROUND_TRUTH.items()}


def _slug(name: str) -> str:
    """Match the slug convention already in the company table: lowercase, non-alphanumerics
    to hyphens. 'R/GA' -> 'r-ga'."""
    import re

    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def _company_id_for(name: str) -> int:
    """Find the Company row by slug, creating it if absent."""
    from model import Company, db

    slug = _slug(name)
    company = Company.query.filter_by(slug=slug).first()
    if company is None:
        company = Company(name=name, slug=slug, profile_json={})
        db.session.add(company)
        db.session.flush()
    return company.id


def _citations_for(quotes: list[dict], excerpts) -> list[dict]:
    """Recompute matched / excerpt id / source tag for every quote in one dimension.

    An unmatched quote is KEPT with both provenance fields null -- discarding it would
    leave the score looking better evidenced than it is, which is the failure the citation
    table was added to make visible.
    """
    import scorer_pipeline as sp

    out = []
    for q in quotes:
        matched, eid, tag = sp.verify_quote(q["quote"], excerpts)
        out.append(
            {
                "quote_text": q["quote"],
                "matched": matched,
                "matched_excerpt_id": eid if matched else None,
                "source_tag": tag if matched else None,
            }
        )
    return out


def backfill(
    results_path: Path,
    rubric_version: str,
    run_at: datetime.datetime,
    as_of: datetime.date,
    notes: str | None,
    model: str,
    temperature: float | None,
    temperature_honored: bool,
    reasoning_effort: str | None,
) -> dict:
    import scorer_pipeline as sp
    import company_score_store

    results = json.loads(results_path.read_text(encoding="utf-8"))
    companies = _packet_companies()

    totals = {"packets": 0, "scores_created": 0, "scores_updated": 0, "citations": 0}
    scorer_run_ids = set()

    for packet_id, dims in sorted(results.items()):
        if packet_id not in companies:
            raise ValueError(
                "%s is not in reidentification_attack.GROUND_TRUTH (%s). Refusing to guess "
                "which company it is." % (packet_id, sorted(companies))
            )
        packet_path = sp.packet_path_for(packet_id)
        packet_text = sp.load_packet_section1(packet_path)
        excerpts = sp.parse_excerpts(packet_text)
        # Parsed from the packet header, never invented -- ties packet_version to the thing
        # that actually changes packet content.
        packet_version = sp.packet_version_for(packet_path)

        company_id = _company_id_for(companies[packet_id])
        summary = company_score_store.ingest_extractor_result(
            company_id=company_id,
            as_of=as_of,
            run={
                "model": model,
                "temperature": temperature,
                "temperature_honored": temperature_honored,
                "reasoning_effort": reasoning_effort,
                "rubric_version": rubric_version,
                "packet_version": packet_version,
                "run_at": run_at,
                "notes": notes,
            },
            dimensions=[
                {
                    "dimension_key": d["dimension"],
                    "score": d["score"],
                    # Stored, never filtered or weighted by -- see company_score_store's
                    # module docstring and tests/test_company_confidence_unused.py.
                    "confidence": d["confidence"],
                    "citations": _citations_for(d.get("quotes", []), excerpts),
                }
                for d in dims
            ],
            # 'scraped' means LLM-produced; 'researched' would mean human ground truth.
            source="scraped",
            # These six are the calibration set the scraped model is measured against.
            is_ground_truth=True,
        )
        scorer_run_ids.add(summary["scorer_run_id"])
        totals["packets"] += 1
        totals["scores_created"] += summary["scores_created"]
        totals["scores_updated"] += summary["scores_updated"]
        totals["citations"] += summary["citations_written"]
        print(
            "  %s -> %-14s run=%s created=%d updated=%d citations=%d"
            % (
                packet_id, companies[packet_id], summary["scorer_run_id"],
                summary["scores_created"], summary["scores_updated"],
                summary["citations_written"],
            )
        )

    totals["scorer_run_ids"] = sorted(scorer_run_ids)
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--results", required=True, type=Path,
        help="extractor results JSON. Required: the v1 file lives outside this repo.",
    )
    parser.add_argument(
        "--rubric-version", required=True,
        help="anchors.json rubric_version this run was scored under. NEVER inferred: "
             "neither results file records it, and a wrong label is invisible downstream.",
    )
    parser.add_argument(
        "--run-at", required=True,
        help="date (YYYY-MM-DD) the run was MADE, not today. Also used as as_of: these "
             "rows describe what the extractor thought then.",
    )
    parser.add_argument("--notes", default=None)
    parser.add_argument(
        "--model", default="gpt-5.5-2026-04-23",
        help="exact pinned snapshot string, never an alias",
    )
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument(
        "--temperature-not-honored", action="store_true",
        help="set when the API rejected or ignored the requested temperature",
    )
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="parse, verify citations and report, without writing anything",
    )
    args = parser.parse_args(argv)

    run_date = datetime.date.fromisoformat(args.run_at)
    run_at = datetime.datetime.combine(
        run_date, datetime.time(0, 0), tzinfo=datetime.timezone.utc
    )

    if not args.results.exists():
        parser.error("results file not found: %s" % args.results)

    if args.dry_run:
        import scorer_pipeline as sp

        results = json.loads(args.results.read_text(encoding="utf-8"))
        companies = _packet_companies()
        n_scores = n_quotes = n_matched = 0
        for packet_id, dims in sorted(results.items()):
            excerpts = sp.parse_excerpts(sp.load_packet_section1(sp.packet_path_for(packet_id)))
            for d in dims:
                n_scores += 1
                for c in _citations_for(d.get("quotes", []), excerpts):
                    n_quotes += 1
                    n_matched += bool(c["matched"])
            print("  %s -> %s (%d dimensions)" % (packet_id, companies[packet_id], len(dims)))
        print(
            "DRY RUN: %d scores, %d quotes, %d matched, %d unmatched (kept, not discarded)"
            % (n_scores, n_quotes, n_matched, n_quotes - n_matched)
        )
        return 0

    from app import app

    with app.app_context():
        print("Backfilling %s under rubric_version=%s" % (args.results.name, args.rubric_version))
        totals = backfill(
            results_path=args.results,
            rubric_version=args.rubric_version,
            run_at=run_at,
            as_of=run_date,
            notes=args.notes,
            model=args.model,
            temperature=args.temperature,
            temperature_honored=not args.temperature_not_honored,
            reasoning_effort=args.reasoning_effort,
        )
    print(
        "DONE: %(packets)d packets, %(scores_created)d scores created, "
        "%(scores_updated)d updated, %(citations)d citations, scorer_run(s) "
        "%(scorer_run_ids)r" % totals
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
