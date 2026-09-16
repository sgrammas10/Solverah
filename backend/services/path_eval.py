"""Offline evaluation harness for career-path scoring — BUILD_PLAN workstream F-2.

WHAT THIS IS FOR
----------------
`path_scoring.py` is about to be substantially rewritten (F-4).  Before this
module existed, "is the new ranking better than the old one" was answered by a
person reading ten results and forming an impression, which makes every weight
in the rewrite an opinion and "the new one is better" unfalsifiable.  This
module turns that into a number, and it is deliberately built *before* the
thing it measures so the rewrite has a target to beat.

**This is a SCORER-QUALITY baseline, not a test-suite baseline.**  CLAUDE.md's
"no baseline runs" rule is about pytest — one full suite run at the end, never a
"before" run, because CI on HEAD is already the before.  It has nothing to do
with this file.  Recording what today's scorer produces is the entire point of
this chunk, and nothing here ever runs a pytest suite.  Do not let the two
collapse into each other.

THE SHAPE
---------
Three pieces, deliberately separated so the expensive half runs once and the
cheap half runs as often as anyone likes:

  record_run()   Calls a scorer once per profile and writes the ranked output
                 to JSON.  This is the ONLY part that touches the network, and
                 for today's scorer it is expensive — see COST below.

  evaluate()     Pure function over a recorded run plus the labelled set.  No
                 network, no database, no clock.  Re-runnable for free, which
                 is what makes metric changes cheap to try and results
                 reproducible months later.

  A scorer is any ``Callable[[EvalProfile], Sequence[RankedResult]]``.  That is
  the whole contract, so F-4's rewrite, F-3's retrieval tier alone, or a
  random-ranking control can all be scored by the same code.

COST OF A LIVE BASELINE RUN
---------------------------
Today's `score_paths` makes roughly 160 O*NET requests per cold profile
(`_fetch_candidate_data` issues 3-4 per candidate across a ~40-candidate pool,
plus title resolution and candidate gathering), and one LLM call for search
terms plus one batched embedding call.  Twenty profiles is therefore on the
order of 3,000 O*NET requests.  `record_live` refuses to run without
``--confirm-live-calls`` for exactly that reason: O*NET's rate limit is a shared
budget, and two agents spending it at once is how both fail.  Run
``python -m backend.services.path_eval cost`` for the current estimate without
making a single call.

READING THE NUMBERS
-------------------
See :func:`evaluate` and the ``_meta`` block in
``tests/fixtures/path_eval/labels.json``.  The short version: the labelled set
covers 10-16 of ~1,016 occupations per profile, so an unlabelled result is
UNJUDGED rather than wrong, `precision_at_k` is a LOWER BOUND, and
`label_coverage_at_k` is what tells you how much of the gap is ignorance
instead of error.  `harmful_rate_at_k` is the one to watch: it counts
suggestions that are infeasible, a demotion, or a known surface-form false
positive, and those are what cost a user's trust.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import random
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Sequence

# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

#: Repository root, derived from this file rather than from the process CWD --
#: the module is invoked as ``python -m`` from the repo root and also imported
#: by pytest from anywhere, and only one of those has a reliable CWD.
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

FIXTURE_DIR: Path = REPO_ROOT / "tests" / "fixtures" / "path_eval"
PROFILES_PATH: Path = FIXTURE_DIR / "profiles.json"
LABELS_PATH: Path = FIXTURE_DIR / "labels.json"
OCCUPATIONS_PATH: Path = FIXTURE_DIR / "onet_occupations.json"

#: The scorer shows ten results (`path_scoring._TOP_N`), so ten is what gets
#: measured.  Kept as a parameter everywhere so a different serving depth can
#: be evaluated without editing the harness.
DEFAULT_K: int = 10

Grade = Literal["primary", "acceptable", "harmful", "anchor"]

#: Graded gains for nDCG.  `harmful` scores zero here rather than negative:
#: nDCG with negative gains has no agreed normalisation and stops being
#: comparable across profiles.  Harm is measured by its own rate instead, so
#: the two failure modes ("did not find the good ones" and "surfaced a bad
#: one") stay separable rather than being averaged into one number.
_GAIN: dict[str, float] = {"primary": 2.0, "acceptable": 1.0, "harmful": 0.0}

#: Grades that count as a hit for precision / MRR / recall.
_RELEVANT: frozenset[str] = frozenset({"primary", "acceptable"})


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalProfile:
    """One fixture profile: the scorer input plus the metadata the report needs."""

    id: str
    axes: dict[str, Any]
    note: str
    raw_profile: dict[str, Any]
    #: True for the ACC-4 / S22 degenerate case, where today's scorer correctly
    #: returns nothing.  Such profiles are reported separately and never folded
    #: into the aggregate, so a known-empty result cannot look like a zero.
    expect_empty_today: bool = False

    @property
    def is_degenerate(self) -> bool:
        return self.expect_empty_today


@dataclass(frozen=True)
class Label:
    """One (profile, occupation) judgement, with the reason it was made."""

    onet_code: str
    title: str
    grade: Grade
    confidence: Literal["high", "low"]
    justification: str


@dataclass(frozen=True)
class RankedResult:
    """One scorer output row.  Rank is positional; index 0 is rank 1."""

    onet_code: str
    title: str
    score: float


@dataclass(frozen=True)
class ProfileRun:
    """What one scorer produced for one profile, plus how much it cost."""

    profile_id: str
    results: list[RankedResult]
    elapsed_s: float
    error: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.results


@dataclass(frozen=True)
class ScorerRun:
    """A whole recorded run: every profile, one scorer, one point in time."""

    scorer_name: str
    recorded_at: str
    runs: list[ProfileRun]
    notes: str = ""

    def by_profile(self) -> dict[str, ProfileRun]:
        return {run.profile_id: run for run in self.runs}


@dataclass(frozen=True)
class ProfileReport:
    """Scored metrics for one profile.  Every field is interpretable alone."""

    profile_id: str
    k: int
    returned: int
    precision_at_k: float
    mrr: float
    ndcg_at_k: float
    harmful_rate_at_k: float
    label_coverage_at_k: float
    primary_recall_at_k: float
    hits: list[str] = field(default_factory=list)
    harms: list[str] = field(default_factory=list)
    missed_primaries: list[str] = field(default_factory=list)
    anchor_returned: bool = False
    error: str | None = None


@dataclass(frozen=True)
class EvalReport:
    """The whole measurement.  `headline` is what F-4 has to beat."""

    scorer_name: str
    recorded_at: str
    k: int
    profiles: list[ProfileReport]
    degenerate: list[ProfileReport]
    headline: dict[str, float]
    empty_result_profiles: list[str]
    errored_profiles: list[str]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_profiles(path: Path = PROFILES_PATH) -> list[EvalProfile]:
    """Load the fixture profile set in file order."""
    data = _read_json(path)
    return [
        EvalProfile(
            id=entry["id"],
            axes=entry.get("axes", {}),
            note=entry.get("note", ""),
            raw_profile=entry["profile"],
            expect_empty_today=bool(entry.get("expect_empty_today", False)),
        )
        for entry in data["profiles"]
    ]


def load_labels(path: Path = LABELS_PATH) -> dict[str, list[Label]]:
    """Load the labelled set, keyed by profile id."""
    data = _read_json(path)
    return {
        profile_id: [
            Label(
                onet_code=row["onet_code"],
                title=row["title"],
                grade=row["grade"],
                confidence=row["confidence"],
                justification=row["justification"],
            )
            for row in rows
        ]
        for profile_id, rows in data["labels"].items()
    }


def load_occupation_titles(path: Path = OCCUPATIONS_PATH) -> dict[str, str]:
    """The O*NET code -> title snapshot used to validate labels."""
    return dict(_read_json(path)["occupations"])


def low_confidence_labels(
    labels: dict[str, list[Label]],
) -> list[tuple[str, Label]]:
    """Every label flagged for human review, as (profile_id, label) pairs.

    The flag lives in the data, not in a comment, precisely so this function can
    exist: Sebastian reviews these rows and does not have to read the other two
    hundred.
    """
    return [
        (profile_id, label)
        for profile_id, rows in labels.items()
        for label in rows
        if label.confidence == "low"
    ]


# ---------------------------------------------------------------------------
# Building the scorer's input
# ---------------------------------------------------------------------------


def build_user_profile(eval_profile: EvalProfile) -> Any:
    """Turn a fixture row into `path_scoring.UserProfile`.

    Imported lazily so that :func:`evaluate` and the whole reporting half of
    this module stay importable without numpy, an OpenAI key, or an O*NET key.
    A metric change should never need the scorer's dependency tree.
    """
    from backend.services.path_scoring import UserProfile, UserSkill

    raw = dict(eval_profile.raw_profile)
    skills = [
        UserSkill(name=skill["name"], level=skill["level"])
        for skill in raw.pop("skills", [])
    ]
    return UserProfile(skills=skills, **raw)


Scorer = Callable[[EvalProfile], Sequence[RankedResult]]


def make_live_scorer(onet_client: Any, openai_client: Any) -> Scorer:
    """Wrap today's `score_paths` as a :data:`Scorer`.

    THIS SCORER MAKES ~160 O*NET REQUESTS PER PROFILE.  Nothing calls it
    implicitly; `record_live` is the only caller and it refuses to run without
    an explicit confirmation flag.
    """
    from backend.services.path_scoring import score_paths

    def _scorer(eval_profile: EvalProfile) -> list[RankedResult]:
        scored = score_paths(
            build_user_profile(eval_profile), onet_client, openai_client
        )
        return [
            RankedResult(onet_code=path.onet_code, title=path.title, score=path.score)
            for path in scored
        ]

    return _scorer


def make_random_scorer(
    occupation_titles: dict[str, str],
    k: int = DEFAULT_K,
    seed: int = 0,
) -> Scorer:
    """A uniform-random ranking over the whole corpus.

    The control every quality number needs.  "precision@10 is 0.21" means
    nothing until you know that guessing scores about 0.01, and it is also the
    cheapest possible regression test for the harness itself: if a change makes
    random look good, the metric is broken, not the scorer.
    """
    codes = sorted(occupation_titles)

    def _scorer(eval_profile: EvalProfile) -> list[RankedResult]:
        rng = random.Random(f"{seed}:{eval_profile.id}")
        picked = rng.sample(codes, min(k, len(codes)))
        return [
            RankedResult(onet_code=code, title=occupation_titles[code], score=1.0 - i / k)
            for i, code in enumerate(picked)
        ]

    return _scorer


def make_oracle_scorer(labels: dict[str, list[Label]], k: int = DEFAULT_K) -> Scorer:
    """A perfect scorer: the label set's own best ordering.

    The other end of the ruler.  It should score 1.0 on nDCG and 0.0 on harm,
    and if it does not, the metric implementation is wrong.  Never a baseline —
    it has read the answers.
    """

    def _scorer(eval_profile: EvalProfile) -> list[RankedResult]:
        rows = [
            label
            for label in labels.get(eval_profile.id, [])
            if label.grade in _RELEVANT
        ]
        rows.sort(key=lambda label: _GAIN[label.grade], reverse=True)
        return [
            RankedResult(onet_code=label.onet_code, title=label.title, score=_GAIN[label.grade])
            for label in rows[:k]
        ]

    return _scorer


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def record_run(
    scorer: Scorer,
    profiles: Iterable[EvalProfile],
    scorer_name: str,
    notes: str = "",
    on_progress: Callable[[ProfileRun, list[ProfileRun]], None] | None = None,
) -> ScorerRun:
    """Run *scorer* over *profiles* and capture the output verbatim.

    A scorer that raises is recorded as an error rather than aborting the run:
    one profile failing must not cost the other nineteen, and an exception is
    itself a result worth measuring (p19 is in the set because the live route
    turns an empty list into an HTTP 500).

    *on_progress* is called after each profile with that profile's result and
    everything recorded so far.  `record-live` uses it to checkpoint to disk:
    the live baseline is a ~3,000-request run that takes tens of minutes, and
    losing nineteen profiles' worth of spent rate limit because the twentieth
    timed out would mean paying the whole cost twice.
    """
    runs: list[ProfileRun] = []
    for profile in profiles:
        started = time.perf_counter()
        try:
            results = list(scorer(profile))
            error: str | None = None
        except Exception as exc:  # noqa: BLE001 -- recorded, not swallowed
            results = []
            error = f"{type(exc).__name__}: {exc}"
        profile_run = ProfileRun(
            profile_id=profile.id,
            results=results,
            elapsed_s=round(time.perf_counter() - started, 3),
            error=error,
        )
        runs.append(profile_run)
        if on_progress is not None:
            on_progress(profile_run, runs)
    return ScorerRun(
        scorer_name=scorer_name,
        recorded_at=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        runs=runs,
        notes=notes,
    )


def save_run(run: ScorerRun, path: Path) -> None:
    """Write a recorded run to JSON, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(asdict(run), fh, indent=1)


def load_run(path: Path) -> ScorerRun:
    """Read back a run written by :func:`save_run`."""
    data = _read_json(path)
    return ScorerRun(
        scorer_name=data["scorer_name"],
        recorded_at=data["recorded_at"],
        notes=data.get("notes", ""),
        runs=[
            ProfileRun(
                profile_id=row["profile_id"],
                results=[RankedResult(**res) for res in row["results"]],
                elapsed_s=row.get("elapsed_s", 0.0),
                error=row.get("error"),
            )
            for row in data["runs"]
        ],
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _dcg(gains: Sequence[float]) -> float:
    return sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))


def score_profile(
    profile: EvalProfile,
    run: ProfileRun,
    labels: Sequence[Label],
    k: int = DEFAULT_K,
) -> ProfileReport:
    """Score one profile's ranked output against its labels.

    Anchors are stripped from the results before anything is measured.  The
    anchor is the user's own occupation; `path_scoring._deduplicate` already
    removes it from the candidate pool, and "you should be what you already
    are" has no product value — so its presence is recorded as a flag and its
    rank is not allowed to shift any other metric.
    """
    by_code = {label.onet_code: label for label in labels}
    anchors = {code for code, label in by_code.items() if label.grade == "anchor"}

    ranked = [res for res in run.results if res.onet_code not in anchors]
    anchor_returned = len(ranked) != len(run.results)
    top = ranked[:k]

    grades = [by_code[res.onet_code].grade if res.onet_code in by_code else None for res in top]

    hit_count = sum(1 for grade in grades if grade in _RELEVANT)
    harm_count = sum(1 for grade in grades if grade == "harmful")
    labelled_count = sum(1 for grade in grades if grade is not None)

    # Precision uses k as the denominator, not len(top): a scorer that returns
    # three results has answered the user's question three-tenths of the way,
    # and hiding that behind a small denominator would reward returning less.
    precision = hit_count / k if k else 0.0

    mrr = 0.0
    for rank, grade in enumerate(grades, start=1):
        if grade in _RELEVANT:
            mrr = 1.0 / rank
            break

    gains = [_GAIN.get(grade or "", 0.0) for grade in grades]
    ideal = sorted(
        (_GAIN[label.grade] for label in labels if label.grade in _RELEVANT),
        reverse=True,
    )[:k]
    ideal_dcg = _dcg(ideal)
    ndcg = (_dcg(gains) / ideal_dcg) if ideal_dcg else 0.0

    # Harm and coverage are rates over what was actually shown: a scorer that
    # returns two results, one of them harmful, put a bad suggestion in front of
    # the user half the time, and dividing by k would understate that to 0.1.
    denom = len(top)
    harmful_rate = (harm_count / denom) if denom else 0.0
    coverage = (labelled_count / denom) if denom else 0.0

    primaries = [label.onet_code for label in labels if label.grade == "primary"]
    found_primaries = {res.onet_code for res in top} & set(primaries)
    primary_recall = (len(found_primaries) / len(primaries)) if primaries else 0.0

    return ProfileReport(
        profile_id=profile.id,
        k=k,
        returned=len(ranked),
        precision_at_k=round(precision, 4),
        mrr=round(mrr, 4),
        ndcg_at_k=round(ndcg, 4),
        harmful_rate_at_k=round(harmful_rate, 4),
        label_coverage_at_k=round(coverage, 4),
        primary_recall_at_k=round(primary_recall, 4),
        hits=[res.onet_code for res, grade in zip(top, grades) if grade in _RELEVANT],
        harms=[res.onet_code for res, grade in zip(top, grades) if grade == "harmful"],
        missed_primaries=sorted(set(primaries) - found_primaries),
        anchor_returned=anchor_returned,
        error=run.error,
    )


def evaluate(
    run: ScorerRun,
    profiles: Sequence[EvalProfile] | None = None,
    labels: dict[str, list[Label]] | None = None,
    k: int = DEFAULT_K,
) -> EvalReport:
    """Score a recorded run.  Pure: no network, no database, no clock.

    THE METRICS, AND WHAT A GOOD NUMBER LOOKS LIKE
    ----------------------------------------------
    All aggregates are macro-means over the non-degenerate profiles — each
    profile counts once regardless of how many labels it happens to carry, so a
    heavily-labelled profile cannot quietly become the benchmark.

    ``precision_at_k``  Fraction of the ten shown slots holding an occupation
        labelled `primary` or `acceptable`.  Against a set that labels 10-16 of
        ~1,016 occupations, this is a LOWER BOUND, not a true precision: an
        unlabelled result is unjudged.  Uniform random guessing scores about
        0.012 (~12 labels / 1,016 occupations).  A genuinely useful scorer
        should be well north of 0.30 here; anything below ~0.10 means the top
        ten is mostly occupations nobody thought to consider, which for a
        hand-labelled set this deliberate is a bad sign rather than a
        vocabulary gap.  Read it together with `label_coverage_at_k`.

    ``mrr``  Mean reciprocal rank of the FIRST acceptable suggestion.  This is
        the one that maps onto the product: a user reads from the top, so 1.0
        means the first card was right and 0.2 means they had to get to the
        fifth.  Above 0.5 is respectable, since it means the first or second
        card is typically usable.  0.0 means nothing in the whole top ten was
        labelled acceptable.

    ``ndcg_at_k``  The metric to actually tune on.  Uses the graded labels
        (primary 2, acceptable 1) and discounts by rank, so it distinguishes
        "the best answer at rank 1" from "a passable answer at rank 9", which
        precision@10 cannot.  Normalised against the best ordering this label
        set permits, so 1.0 is attainable and comparable across profiles.

    ``harmful_rate_at_k``  Fraction of shown results labelled `harmful` —
        infeasible (a credential the user does not hold), a demotion, or a
        documented surface-form false positive.  **The target is 0.0 and any
        non-zero value is a defect, not a tuning opportunity.**  This is the
        number that corresponds to a user losing trust in the product, and it
        is reported separately precisely because a good precision score can
        coexist with it.

    ``label_coverage_at_k``  Fraction of shown results carrying any label at
        all.  The honesty metric.  Low precision with low coverage means the
        scorer is returning things nobody judged; low precision with HIGH
        coverage means it is returning things that were judged and rejected.
        Those are different failures and the fix is different.

    ``primary_recall_at_k``  Fraction of a profile's `primary` labels that
        reached the top ten.  Primary sets are small (3-5) and close to
        complete, so unlike precision this one is a real recall.

    The degenerate profile (p19, the ACC-4 / S22 case) is scored and reported
    separately, never folded into the aggregate: it carries no labels by
    design, and averaging a structural zero into the headline would make every
    number quietly worse for a reason that has nothing to do with ranking.
    """
    profiles = list(profiles if profiles is not None else load_profiles())
    labels = labels if labels is not None else load_labels()
    runs = run.by_profile()

    ordinary: list[ProfileReport] = []
    degenerate: list[ProfileReport] = []
    for profile in profiles:
        profile_run = runs.get(profile.id)
        if profile_run is None:
            continue
        report = score_profile(profile, profile_run, labels.get(profile.id, []), k=k)
        (degenerate if profile.is_degenerate else ordinary).append(report)

    def _mean(attr: str) -> float:
        if not ordinary:
            return 0.0
        return round(statistics.fmean(getattr(r, attr) for r in ordinary), 4)

    headline = {
        "precision_at_k": _mean("precision_at_k"),
        "mrr": _mean("mrr"),
        "ndcg_at_k": _mean("ndcg_at_k"),
        "harmful_rate_at_k": _mean("harmful_rate_at_k"),
        "label_coverage_at_k": _mean("label_coverage_at_k"),
        "primary_recall_at_k": _mean("primary_recall_at_k"),
        "profiles_scored": float(len(ordinary)),
    }

    return EvalReport(
        scorer_name=run.scorer_name,
        recorded_at=run.recorded_at,
        k=k,
        profiles=ordinary,
        degenerate=degenerate,
        headline=headline,
        empty_result_profiles=[
            r.profile_id for r in (*ordinary, *degenerate) if r.returned == 0
        ],
        errored_profiles=[
            r.profile_id for r in (*ordinary, *degenerate) if r.error is not None
        ],
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def format_report(report: EvalReport) -> str:
    """A fixed-width text rendering of an :class:`EvalReport`."""
    lines: list[str] = []
    lines.append(f"scorer      : {report.scorer_name}")
    lines.append(f"recorded at : {report.recorded_at}")
    lines.append(f"k           : {report.k}")
    lines.append("")
    header = (
        f"{'profile':<36} {'ret':>4} {'P@k':>6} {'MRR':>6} {'nDCG':>6} "
        f"{'harm':>6} {'cover':>6} {'Prec':>6}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for row in report.profiles:
        lines.append(
            f"{row.profile_id:<36} {row.returned:>4} {row.precision_at_k:>6.3f} "
            f"{row.mrr:>6.3f} {row.ndcg_at_k:>6.3f} {row.harmful_rate_at_k:>6.3f} "
            f"{row.label_coverage_at_k:>6.3f} {row.primary_recall_at_k:>6.3f}"
        )
    lines.append("-" * len(header))
    head = report.headline
    lines.append(
        f"{'MACRO MEAN':<36} {'':>4} {head['precision_at_k']:>6.3f} "
        f"{head['mrr']:>6.3f} {head['ndcg_at_k']:>6.3f} "
        f"{head['harmful_rate_at_k']:>6.3f} {head['label_coverage_at_k']:>6.3f} "
        f"{head['primary_recall_at_k']:>6.3f}"
    )
    if report.degenerate:
        lines.append("")
        lines.append("degenerate profiles (reported, never averaged in):")
        for row in report.degenerate:
            state = "EMPTY" if row.returned == 0 else f"{row.returned} results"
            err = f" error={row.error}" if row.error else ""
            lines.append(f"  {row.profile_id:<36} {state}{err}")
    if report.empty_result_profiles:
        lines.append("")
        lines.append(f"empty results : {', '.join(report.empty_result_profiles)}")
    if report.errored_profiles:
        lines.append(f"errored       : {', '.join(report.errored_profiles)}")
    harmful = [r for r in report.profiles if r.harms]
    if harmful:
        lines.append("")
        lines.append("HARMFUL SUGGESTIONS SHOWN (target is none):")
        for row in harmful:
            lines.append(f"  {row.profile_id}: {', '.join(row.harms)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Funnel reachability — how well COULD today's scorer do?
# ---------------------------------------------------------------------------


def funnel_ceiling(
    profiles: Sequence[EvalProfile] | None = None,
    labels: dict[str, list[Label]] | None = None,
) -> list[dict[str, Any]]:
    """Per profile, the fraction of its labels today's funnel can even reach.

    Computed offline, with no API calls, by running the same profile through
    `path_scoring._get_allowed_soc_prefixes`.  It answers a question the
    baseline number cannot: when a profile scores badly, is the RANKING wrong,
    or was the right answer never in the candidate pool to begin with?  Those
    have different fixes -- F-4's comparison-target change fixes the first and
    F-3's retrieval tier fixes the second -- and a single precision number
    cannot tell them apart.

    This reaches into `path_scoring` internals on purpose, and it is expected
    to stop working when F-4 replaces the funnel.  That is the success
    condition, not a breakage: it returns an empty list rather than raising, so
    a deleted allow-list retires the diagnostic instead of failing the suite.
    """
    profiles = list(profiles if profiles is not None else load_profiles())
    labels = labels if labels is not None else load_labels()

    try:
        from backend.services.path_scoring import _get_allowed_soc_prefixes
    except ImportError:  # pragma: no cover -- the F-4 success case
        return []

    def _reachable(rows_in: Sequence[Label], allowed: Sequence[str]) -> list[Label]:
        return [
            label
            for label in rows_in
            if any(label.onet_code.startswith(prefix) for prefix in allowed)
        ]

    rows: list[dict[str, Any]] = []
    for profile in profiles:
        allowed = _get_allowed_soc_prefixes(build_user_profile(profile))
        relevant = [
            label for label in labels.get(profile.id, []) if label.grade in _RELEVANT
        ]
        primaries = [label for label in relevant if label.grade == "primary"]
        reachable_primaries = _reachable(primaries, allowed)

        rows.append(
            {
                "profile_id": profile.id,
                "allowed_soc_prefixes": sorted(allowed),
                "relevant_labels": len(relevant),
                "reachable_relevant": len(_reachable(relevant, allowed)),
                "primary_labels": len(primaries),
                "reachable_primary": len(reachable_primaries),
                "unreachable_primaries": sorted(
                    {label.onet_code for label in primaries}
                    - {label.onet_code for label in reachable_primaries}
                ),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Cost projection
# ---------------------------------------------------------------------------

#: Measured/derived in docs/PATH_INTELLIGENCE_REDESIGN.md §1.2: ~3-4 O*NET
#: requests per candidate over a ~40-candidate pool, plus title resolution and
#: pool gathering.  An estimate, and labelled as one.
_ONET_CALLS_PER_PROFILE: int = 160
_LLM_CALLS_PER_PROFILE: int = 1
_EMBED_BATCHES_PER_PROFILE: int = 1

#: The same three numbers for the F-4 corpus scorer, which reaches O*NET only to
#: resolve the user's own title (one search, plus a job-zone lookup when the
#: corpus sidecar has no zone for that code) and makes no LLM completion calls
#: at all.  Additive: the profile set, the labels and every metric are unchanged
#: -- this only makes the confirmation prompt tell the truth about what a run of
#: the new scorer costs, instead of quoting the old funnel's 160.
_CORPUS_ONET_CALLS_PER_PROFILE: int = 2
_CORPUS_LLM_CALLS_PER_PROFILE: int = 0

#: Cost models the ``--scorer`` flag on ``record-live`` selects between.
COST_MODELS: dict[str, tuple[int, int, str]] = {
    "live": (
        _ONET_CALLS_PER_PROFILE,
        _LLM_CALLS_PER_PROFILE,
        "design doc §1.2: ~160 O*NET requests per cold profile "
        "(3-4 per candidate x ~40 candidates, plus resolution and gathering); "
        "one LLM search-term call and one batched embedding call per profile",
    ),
    "corpus": (
        _CORPUS_ONET_CALLS_PER_PROFILE,
        _CORPUS_LLM_CALLS_PER_PROFILE,
        "BUILD_PLAN F-4: retrieval is a local matrix product, so O*NET is "
        "touched only for anchor resolution (<=2 calls) and no LLM completion "
        "is made; one batched embedding call covers the user's own documents",
    ),
}


def project_cost(profile_count: int, model: str = "live") -> dict[str, int | str]:
    """What a live run of *model* would spend.  Makes no calls of its own."""
    onet_per, llm_per, basis = COST_MODELS[model]
    return {
        "profiles": profile_count,
        "scorer": model,
        "onet_requests_estimate": profile_count * onet_per,
        "llm_completion_calls": profile_count * llm_per,
        "embedding_batch_calls": profile_count * _EMBED_BATCHES_PER_PROFILE,
        "basis": basis,
        "caveat": (
            "O*NET's _OCC_CACHE is per-process and 24h, so profiles sharing a "
            "candidate pool make this an upper bound within a single run"
        ),
    }


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------
#
# Deliberately NOT a flask CLI command.  solverah/cli.py belongs to F-1 this
# round, and a baseline run has no business needing an app context anyway.


def _cmd_cost(args: argparse.Namespace) -> int:
    profiles = load_profiles()
    print(json.dumps(project_cost(len(profiles), getattr(args, "scorer", "live")), indent=2))
    return 0


def _cmd_ceiling(args: argparse.Namespace) -> int:
    rows = funnel_ceiling()
    if not rows:
        print("no funnel to inspect -- path_scoring no longer exposes an allow-list.")
        return 0
    header = f"{'profile':<36} {'reachable/relevant':>19} {'reachable/primary':>18}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['profile_id']:<36} "
            f"{row['reachable_relevant']:>9}/{row['relevant_labels']:<9} "
            f"{row['reachable_primary']:>9}/{row['primary_labels']:<8}"
        )
    blocked = [r for r in rows if r["primary_labels"] and not r["reachable_primary"]]
    if blocked:
        print("")
        print("STRUCTURALLY UNANSWERABLE TODAY (no primary label survives the SOC allow-list):")
        for row in blocked:
            print(f"  {row['profile_id']}: {', '.join(row['unreachable_primaries'])}")
    return 0


def _cmd_record_live(args: argparse.Namespace) -> int:
    profiles = load_profiles()
    if args.only:
        wanted = set(args.only.split(","))
        profiles = [p for p in profiles if p.id in wanted]

    cost = project_cost(len(profiles), args.scorer)
    if not args.confirm_live_calls:
        print("REFUSING TO RUN. A live baseline spends a shared O*NET budget:")
        print(json.dumps(cost, indent=2))
        print(
            "\nRe-run with --confirm-live-calls once the overseer has sequenced "
            "it against F-1's corpus build."
        )
        return 2

    # The ONE place in this module that wants the real environment.  Nothing
    # else here reads a key, and no test reaches this line -- `record-live`
    # refuses above without --confirm-live-calls.  CI parity is a rule about the
    # SUITE (run it the way the runner does, with SOLVERAH_IGNORE_DOTENV=1); a
    # baseline that calls live O*NET and live OpenAI needs live credentials by
    # definition.  The escape hatch is still honoured so the two never conflict.
    if not os.environ.get("SOLVERAH_IGNORE_DOTENV"):
        try:
            from dotenv import load_dotenv

            load_dotenv(REPO_ROOT / ".env")
        except ImportError:  # pragma: no cover -- dotenv is a hard dependency
            pass

    from backend.services.onet_client import OnetClient
    from solverah.infra.llm import get_openai_client

    onet_client = OnetClient()
    try:
        openai_client = get_openai_client()
    except RuntimeError:
        openai_client = None
        print("WARNING: no OpenAI client; scoring degrades to non-embedding paths.")

    print(f"recording {len(profiles)} profiles ({cost['onet_requests_estimate']} O*NET calls est.)")
    out_path = Path(args.out)
    notes = f"live baseline; projected {cost['onet_requests_estimate']} O*NET requests"

    def _checkpoint(latest: ProfileRun, so_far: list[ProfileRun]) -> None:
        state = "EMPTY" if latest.is_empty else f"{len(latest.results)} results"
        flag = f" ERROR {latest.error}" if latest.error else ""
        print(f"  [{len(so_far):>2}/{len(profiles)}] {latest.profile_id:<36} {state} in {latest.elapsed_s}s{flag}")
        save_run(
            ScorerRun(
                scorer_name=args.name,
                recorded_at="(in progress)",
                runs=list(so_far),
                notes=notes + " -- PARTIAL, run did not finish",
            ),
            out_path,
        )

    run = record_run(
        make_live_scorer(onet_client, openai_client),
        profiles,
        scorer_name=args.name,
        notes=notes,
        on_progress=_checkpoint,
    )
    save_run(run, out_path)
    print(f"wrote {args.out}")
    print(format_report(evaluate(run, profiles)))
    return 0


def _cmd_record_control(args: argparse.Namespace) -> int:
    profiles = load_profiles()
    labels = load_labels()
    if args.scorer == "random":
        scorer = make_random_scorer(load_occupation_titles(), seed=args.seed)
        name = f"random(seed={args.seed})"
    else:
        scorer = make_oracle_scorer(labels)
        name = "oracle(label-set)"
    run = record_run(scorer, profiles, scorer_name=name, notes="offline control, no network")
    if args.out:
        save_run(run, Path(args.out))
    print(format_report(evaluate(run, profiles, labels)))
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    run = load_run(Path(args.run))
    report = evaluate(run, k=args.k)
    if args.json:
        print(json.dumps(asdict(report), indent=1))
    else:
        print(format_report(report))
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    """Print only the labels flagged for human review."""
    flagged = low_confidence_labels(load_labels())
    print(f"{len(flagged)} labels flagged confidence=low\n")
    for profile_id, label in flagged:
        print(f"{profile_id}")
        print(f"  {label.onet_code}  {label.title}  [{label.grade}]")
        print(f"    {label.justification}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.services.path_eval",
        description="Offline evaluation harness for career-path scoring (F-2).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_cost = sub.add_parser("cost", help="project the cost of a live baseline run")
    p_cost.add_argument("--scorer", choices=tuple(COST_MODELS), default="live")
    p_cost.set_defaults(func=_cmd_cost)

    p_live = sub.add_parser("record-live", help="run today's scorer and record it")
    p_live.add_argument(
        "--out",
        # Lands beside the profiles and labels it was scored against, so a run
        # months old can still be read with the exact set that produced it.
        default="tests/fixtures/path_eval/runs/baseline_today.json",
    )
    p_live.add_argument("--name", default="path_scoring.score_paths@HEAD")
    p_live.add_argument("--only", default="", help="comma-separated profile ids")
    p_live.add_argument("--confirm-live-calls", action="store_true")
    # Which cost model to quote before spending a shared budget. Both values run
    # the same `score_paths`; "corpus" says that scorer is the F-4 rewrite, whose
    # per-profile O*NET cost is 2 rather than the funnel's ~160.
    p_live.add_argument("--scorer", choices=tuple(COST_MODELS), default="live")
    p_live.set_defaults(func=_cmd_record_live)

    p_ctrl = sub.add_parser("record-control", help="random or oracle control, no network")
    p_ctrl.add_argument("scorer", choices=("random", "oracle"))
    p_ctrl.add_argument("--seed", type=int, default=0)
    p_ctrl.add_argument("--out", default="")
    p_ctrl.set_defaults(func=_cmd_record_control)

    p_eval = sub.add_parser("evaluate", help="score a recorded run (offline)")
    p_eval.add_argument("--run", required=True)
    p_eval.add_argument("--k", type=int, default=DEFAULT_K)
    p_eval.add_argument("--json", action="store_true")
    p_eval.set_defaults(func=_cmd_evaluate)

    p_ceiling = sub.add_parser(
        "ceiling", help="how many labels today's funnel can even reach (offline)"
    )
    p_ceiling.set_defaults(func=_cmd_ceiling)

    p_review = sub.add_parser("review", help="print labels flagged confidence=low")
    p_review.set_defaults(func=_cmd_review)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover -- exercised via main()
    sys.exit(main())
