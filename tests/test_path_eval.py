"""Tests for the F-2 scorer-quality evaluation harness.

Two jobs, and they are different in kind.

**Guard the labelled set.**  A labelled set is only worth what its worst label
is worth.  These tests fail on a hallucinated SOC code, a label whose title
disagrees with O*NET's, a missing justification, a profile with no labels, or a
profile whose fields have drifted away from `path_scoring.UserProfile`.  Every
one of those is a defect that would otherwise show up months later as a metric
that quietly measures nothing.

**Guard the metric.**  A measuring stick nobody has calibrated is a stick.  The
metric tests pin both ends of the ruler with synthetic runs: a perfect ranking
must score 1.0, a random ranking must score near zero, and the specific
behaviours that were chosen deliberately -- k in the precision denominator,
anchors excluded entirely, harm reported separately from relevance, degenerate
profiles never averaged in -- are each asserted, because each one is a judgement
call that a future reader would otherwise have to take on faith.

No network.  Nothing here calls O*NET or OpenAI, and nothing here runs
`score_paths`.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from backend.services import path_eval
from backend.services.path_eval import (
    DEFAULT_K,
    EvalProfile,
    Label,
    ProfileRun,
    RankedResult,
    ScorerRun,
    evaluate,
    format_report,
    load_labels,
    load_occupation_titles,
    load_profiles,
    low_confidence_labels,
    make_oracle_scorer,
    make_random_scorer,
    project_cost,
    record_run,
    save_run,
    load_run,
    score_profile,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def profiles() -> list[EvalProfile]:
    return load_profiles()


@pytest.fixture(scope="module")
def labels() -> dict[str, list[Label]]:
    return load_labels()


@pytest.fixture(scope="module")
def occupations() -> dict[str, str]:
    return load_occupation_titles()


def _profile(profile_id: str = "p_test", degenerate: bool = False) -> EvalProfile:
    return EvalProfile(
        id=profile_id,
        axes={},
        note="",
        raw_profile={},
        expect_empty_today=degenerate,
    )


def _results(*codes: str) -> list[RankedResult]:
    return [RankedResult(onet_code=code, title=code, score=1.0) for code in codes]


def _label(code: str, grade: str, confidence: str = "high") -> Label:
    return Label(
        onet_code=code,
        title=code,
        grade=grade,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        justification="because",
    )


# ---------------------------------------------------------------------------
# The profile set
# ---------------------------------------------------------------------------


def test_profile_set_spans_the_axes_it_claims_to(profiles: list[EvalProfile]) -> None:
    """Each axis named in the fixture's _meta must actually vary."""
    assert len(profiles) >= 15, "the spec asks for ~15-20 profiles"

    statuses = {p.raw_profile["career_status"] for p in profiles}
    assert statuses == {"first_job", "employed", "between_jobs"}

    intents = {p.raw_profile.get("move_intent") for p in profiles}
    assert intents == {"stay_in_field", "adjacent", "fresh_start", None}

    densities = {p.axes.get("skill_density") for p in profiles}
    assert densities >= {"rich", "moderate", "sparse", "none"}

    behavioral = {p.axes.get("behavioral") for p in profiles}
    assert behavioral == {"present", "absent"}

    # Tech and non-tech both represented, since the whole accuracy complaint in
    # the design doc is about a vocabulary that favours one of them.
    domains = {str(p.axes.get("domain", "")) for p in profiles}
    assert any("tech" in d for d in domains)
    assert any(d in {"healthcare", "education", "legal", "skilled trade", "creative"} for d in domains)


def test_profile_ids_are_unique(profiles: list[EvalProfile]) -> None:
    ids = [p.id for p in profiles]
    assert len(ids) == len(set(ids))


def test_the_degenerate_acc4_case_is_present(profiles: list[EvalProfile]) -> None:
    """The live production bug is in the set, and is the only degenerate row.

    ACC-4 / S22: career_status set, no title, no skills.  `score_paths` returns
    [] and `intelligence_service.path_suggestions` turns that into a generic
    500.  It is in the eval set so that F-8's fallback gets measured rather than
    asserted.
    """
    degenerate = [p for p in profiles if p.is_degenerate]
    assert len(degenerate) == 1
    only = degenerate[0]
    assert only.raw_profile["current_title"] is None
    assert only.raw_profile["skills"] == []
    assert only.raw_profile["career_status"], "career_status must be set, or the route 400s instead"


def test_every_profile_builds_a_real_user_profile(profiles: list[EvalProfile]) -> None:
    """The fixture's keys must match `path_scoring.UserProfile` exactly.

    This is the drift guard: a field added to UserProfile without being added
    here would silently make every profile in the set score a different scorer
    input than production uses.
    """
    from backend.services.path_scoring import UserProfile

    known = {f.name for f in dataclasses.fields(UserProfile)}
    for profile in profiles:
        keys = set(profile.raw_profile) | {"skills"}
        assert keys <= known, f"{profile.id} has unknown keys: {keys - known}"
        built = path_eval.build_user_profile(profile)
        assert isinstance(built, UserProfile)
        assert built.career_status == profile.raw_profile["career_status"]


# ---------------------------------------------------------------------------
# The labelled set
# ---------------------------------------------------------------------------


def test_every_labelled_code_is_a_real_onet_code(
    labels: dict[str, list[Label]], occupations: dict[str, str]
) -> None:
    """No hallucinated SOC codes.

    A labelled set full of invented codes is worse than no labelled set, because
    it produces a number that looks like a measurement.  The snapshot it checks
    against was captured from live O*NET in 24 calls.
    """
    unknown = [
        (profile_id, label.onet_code)
        for profile_id, rows in labels.items()
        for label in rows
        if label.onet_code not in occupations
    ]
    assert not unknown, f"codes absent from the O*NET snapshot: {unknown}"


def test_label_titles_match_onet(
    labels: dict[str, list[Label]], occupations: dict[str, str]
) -> None:
    """The title stored beside each code is O*NET's own, not a paraphrase."""
    wrong = [
        (profile_id, label.onet_code, label.title, occupations[label.onet_code])
        for profile_id, rows in labels.items()
        for label in rows
        if occupations.get(label.onet_code) != label.title
    ]
    assert not wrong, f"title mismatches: {wrong}"


def test_every_label_carries_a_justification(labels: dict[str, list[Label]]) -> None:
    """An unjustified label is an opinion wearing a number's clothing.

    The set will outlive anyone's memory of why a code was chosen, so the reason
    is stored with the label rather than in a commit message.
    """
    for profile_id, rows in labels.items():
        for label in rows:
            assert label.justification.strip(), f"{profile_id}/{label.onet_code}"
            assert len(label.justification) > 25, (
                f"{profile_id}/{label.onet_code}: justification is too thin to "
                f"be useful: {label.justification!r}"
            )


def test_label_grades_and_confidence_are_from_the_declared_vocabulary(
    labels: dict[str, list[Label]],
) -> None:
    for profile_id, rows in labels.items():
        for label in rows:
            assert label.grade in {"primary", "acceptable", "harmful", "anchor"}, profile_id
            assert label.confidence in {"high", "low"}, profile_id


def test_no_code_is_labelled_twice_for_one_profile(labels: dict[str, list[Label]]) -> None:
    for profile_id, rows in labels.items():
        codes = [label.onet_code for label in rows]
        assert len(codes) == len(set(codes)), f"{profile_id} labels a code twice"


def test_every_profile_is_labelled(
    profiles: list[EvalProfile], labels: dict[str, list[Label]]
) -> None:
    """Every profile has labels, except the degenerate one, which must not."""
    for profile in profiles:
        rows = labels.get(profile.id)
        assert rows is not None, f"{profile.id} has no entry in labels.json"
        if profile.is_degenerate:
            assert rows == [], (
                "the zero-signal profile must carry NO labels -- inventing them "
                "would make the metric reward guessing"
            )
        else:
            assert len(rows) >= 8, f"{profile.id} has only {len(rows)} labels"
            grades = {label.grade for label in rows}
            assert "primary" in grades, f"{profile.id} has no primary label"
            assert "harmful" in grades, (
                f"{profile.id} has no harmful label -- the negative list is what "
                f"catches infeasible and surface-form suggestions"
            )


def test_anchor_labels_are_the_users_own_occupation(
    profiles: list[EvalProfile], labels: dict[str, list[Label]]
) -> None:
    """An anchor only makes sense where the profile has a resolvable title."""
    by_id = {p.id: p for p in profiles}
    for profile_id, rows in labels.items():
        anchors = [label for label in rows if label.grade == "anchor"]
        assert len(anchors) <= 1, f"{profile_id} has more than one anchor"
        if anchors:
            profile = by_id[profile_id]
            assert profile.raw_profile.get("current_title"), (
                f"{profile_id} has an anchor label but no current_title"
            )


def test_low_confidence_labels_are_flagged_in_data_not_prose(
    labels: dict[str, list[Label]],
) -> None:
    """The review queue must be machine-readable.

    The brief asks for low-confidence labels flagged "in a field, not a
    comment", because Sebastian reviews those rows and not the other two
    hundred.  This asserts the field exists, is populated, and actually selects
    a reviewable subset rather than everything or nothing.
    """
    flagged = low_confidence_labels(labels)
    total = sum(len(rows) for rows in labels.values())
    assert flagged, "nothing flagged for review is not credible for a set this size"
    assert len(flagged) < total * 0.6, "flagging most of the set is not a review queue"
    for _, label in flagged:
        assert label.grade != "harmful", (
            "a harmful label that is only probably harmful should be softened to "
            "acceptable, not flagged -- harmful drives a target-zero metric"
        )


def test_the_labelled_set_has_no_external_gate(labels: dict[str, list[Label]]) -> None:
    """BUILD_PLAN F-2 warning 2: this must not become a Julie dependency.

    The judgement in every label is "would a careful person suggest this
    occupation to this person", which needs no I/O psychologist.  If a
    justification ever starts leaning on expert elicitation, workstream F
    inherits the blocker it was chosen to avoid, so the words that would signal
    that are refused here rather than in a review.
    """
    forbidden = ("julie", "expert elicitation", "i/o psychologist", "rater panel", "anchors v3")
    offenders = [
        (profile_id, label.onet_code, word)
        for profile_id, rows in labels.items()
        for label in rows
        for word in forbidden
        if word in label.justification.lower()
    ]
    assert not offenders, f"labels leaning on an external gate: {offenders}"


# ---------------------------------------------------------------------------
# The metric
# ---------------------------------------------------------------------------


def test_perfect_ranking_scores_one() -> None:
    """Pins the top of the ruler."""
    profile = _profile()
    rows = [_label("a", "primary"), _label("b", "primary"), _label("c", "acceptable")]
    run = ProfileRun(profile_id=profile.id, results=_results("a", "b", "c"), elapsed_s=0.0)
    report = score_profile(profile, run, rows)
    assert report.ndcg_at_k == 1.0
    assert report.mrr == 1.0
    assert report.primary_recall_at_k == 1.0
    assert report.harmful_rate_at_k == 0.0
    assert report.label_coverage_at_k == 1.0
    assert report.precision_at_k == pytest.approx(3 / DEFAULT_K)


def test_ordering_matters_to_ndcg_but_not_to_precision() -> None:
    """The reason nDCG is the metric to tune on.

    Two rankings containing exactly the same ten occupations score identically
    on precision@10 and differently on nDCG, because only one of them put the
    best answer where the user will actually see it.
    """
    profile = _profile()
    rows = [_label("good", "primary"), _label("ok", "acceptable")]
    filler = [f"x{i}" for i in range(8)]

    best = ProfileRun(profile.id, _results("good", "ok", *filler), 0.0)
    worst = ProfileRun(profile.id, _results(*filler, "ok", "good"), 0.0)

    top = score_profile(profile, best, rows)
    bottom = score_profile(profile, worst, rows)

    assert top.precision_at_k == bottom.precision_at_k
    assert top.ndcg_at_k > bottom.ndcg_at_k
    assert top.mrr > bottom.mrr


def test_precision_denominator_is_k_not_the_result_count() -> None:
    """Returning fewer results must not inflate precision.

    A scorer that shows one correct card has answered a tenth of the question,
    not all of it.  Dividing by len(results) would score that 1.0 and reward
    returning less.
    """
    profile = _profile()
    rows = [_label("a", "primary")]
    run = ProfileRun(profile.id, _results("a"), 0.0)
    report = score_profile(profile, run, rows)
    assert report.precision_at_k == pytest.approx(1 / DEFAULT_K)
    assert report.mrr == 1.0


def test_harm_is_counted_separately_from_relevance() -> None:
    """A good precision score can coexist with a trust-destroying suggestion."""
    profile = _profile()
    rows = [
        _label("a", "primary"),
        _label("b", "primary"),
        _label("nope", "harmful"),
    ]
    run = ProfileRun(profile.id, _results("a", "b", "nope"), 0.0)
    report = score_profile(profile, run, rows)
    assert report.precision_at_k == pytest.approx(2 / DEFAULT_K)
    # abs= rather than the default relative tolerance: the report rounds to
    # four decimals so the JSON stays readable by a human, which is coarser
    # than pytest.approx's 1e-6 default.
    assert report.harmful_rate_at_k == pytest.approx(1 / 3, abs=1e-4)
    assert report.harms == ["nope"]
    # Harmful must not count as a hit, and must not earn DCG gain either.
    assert "nope" not in report.hits


def test_anchor_is_excluded_from_every_metric() -> None:
    """The user's own occupation neither helps nor hurts.

    `path_scoring._deduplicate` removes it from the pool by construction, and
    "you should be what you already are" has no product value -- so it is
    stripped before scoring and only recorded as a flag.
    """
    profile = _profile()
    rows = [_label("self", "anchor"), _label("a", "primary")]

    without = score_profile(profile, ProfileRun(profile.id, _results("a"), 0.0), rows)
    with_anchor = score_profile(profile, ProfileRun(profile.id, _results("self", "a"), 0.0), rows)

    assert with_anchor.anchor_returned is True
    assert without.anchor_returned is False
    assert with_anchor.mrr == without.mrr == 1.0
    assert with_anchor.ndcg_at_k == without.ndcg_at_k
    assert with_anchor.precision_at_k == without.precision_at_k
    assert with_anchor.label_coverage_at_k == without.label_coverage_at_k


def test_unlabelled_results_are_unjudged_not_wrong() -> None:
    """Coverage is the honesty metric.

    The labels cover ~12 of ~1,016 occupations, so precision is a lower bound.
    Coverage says how much of the shortfall is ignorance rather than error --
    low precision with low coverage and low precision with high coverage are
    different failures with different fixes.
    """
    profile = _profile()
    rows = [_label("a", "primary"), _label("bad", "harmful")]
    run = ProfileRun(profile.id, _results("a", "unknown1", "unknown2", "bad"), 0.0)
    report = score_profile(profile, run, rows)
    assert report.label_coverage_at_k == pytest.approx(2 / 4)
    assert report.precision_at_k == pytest.approx(1 / DEFAULT_K)


def test_empty_result_scores_zero_without_dividing_by_zero() -> None:
    """The ACC-4 shape must produce a number, not a traceback."""
    profile = _profile()
    rows = [_label("a", "primary")]
    report = score_profile(profile, ProfileRun(profile.id, [], 0.0), rows)
    assert report.returned == 0
    assert report.precision_at_k == 0.0
    assert report.mrr == 0.0
    assert report.ndcg_at_k == 0.0
    assert report.harmful_rate_at_k == 0.0
    assert report.label_coverage_at_k == 0.0
    assert report.missed_primaries == ["a"]


def test_degenerate_profiles_are_reported_but_never_averaged_in() -> None:
    """A structural zero must not drag the headline down.

    p19 carries no labels by design.  Folding its inevitable 0.0 into the mean
    would make every number worse for a reason that has nothing to do with
    ranking quality, and would move the moment F-8 lands for reasons unrelated
    to F-4's rewrite.
    """
    ordinary = _profile("p_real")
    degenerate = _profile("p_degenerate", degenerate=True)
    labels = {"p_real": [_label("a", "primary")], "p_degenerate": []}
    run = ScorerRun(
        scorer_name="t",
        recorded_at="now",
        runs=[
            ProfileRun("p_real", _results("a"), 0.0),
            ProfileRun("p_degenerate", [], 0.0),
        ],
    )
    report = evaluate(run, [ordinary, degenerate], labels)
    assert report.headline["profiles_scored"] == 1.0
    assert report.headline["mrr"] == 1.0
    assert [r.profile_id for r in report.degenerate] == ["p_degenerate"]
    assert "p_degenerate" in report.empty_result_profiles


def test_a_scorer_that_raises_is_recorded_not_propagated() -> None:
    """One profile failing must not cost the other nineteen."""

    def _boom(profile: EvalProfile) -> list[RankedResult]:
        raise RuntimeError("O*NET said no")

    run = record_run(_boom, [_profile("p1"), _profile("p2")], scorer_name="boom")
    assert len(run.runs) == 2
    assert all(r.error and "O*NET said no" in r.error for r in run.runs)

    report = evaluate(run, [_profile("p1"), _profile("p2")], {"p1": [], "p2": []})
    assert report.errored_profiles == ["p1", "p2"]


# ---------------------------------------------------------------------------
# End-to-end over the real fixtures, with synthetic scorers
# ---------------------------------------------------------------------------


def test_oracle_scorer_tops_the_ruler_on_the_real_label_set(
    profiles: list[EvalProfile], labels: dict[str, list[Label]]
) -> None:
    """A scorer that has read the answers must score 1.0 and cause no harm.

    If it does not, the metric is wrong -- not the scorer.
    """
    run = record_run(make_oracle_scorer(labels), profiles, scorer_name="oracle")
    report = evaluate(run, profiles, labels)
    assert report.headline["ndcg_at_k"] == pytest.approx(1.0)
    assert report.headline["mrr"] == pytest.approx(1.0)
    assert report.headline["harmful_rate_at_k"] == 0.0
    assert report.headline["label_coverage_at_k"] == pytest.approx(1.0)


def test_random_scorer_bottoms_the_ruler(
    profiles: list[EvalProfile],
    labels: dict[str, list[Label]],
    occupations: dict[str, str],
) -> None:
    """Pins the other end.

    Guessing over ~1,016 occupations with ~12 labelled should land near zero.
    This is what makes a real score interpretable: "precision@10 = 0.21" only
    means something once you know the floor.
    """
    run = record_run(
        make_random_scorer(occupations, seed=7), profiles, scorer_name="random"
    )
    report = evaluate(run, profiles, labels)
    assert report.headline["precision_at_k"] < 0.05
    assert report.headline["ndcg_at_k"] < 0.05
    assert report.headline["mrr"] < 0.10


def test_oracle_beats_random_on_every_headline_metric(
    profiles: list[EvalProfile],
    labels: dict[str, list[Label]],
    occupations: dict[str, str],
) -> None:
    """The measuring stick must order the two things it can already order.

    A metric that cannot separate a perfect ranking from a random one is not
    going to separate F-4's rewrite from today's scorer either.
    """
    oracle = evaluate(
        record_run(make_oracle_scorer(labels), profiles, "oracle"), profiles, labels
    )
    chance = evaluate(
        record_run(make_random_scorer(occupations, seed=3), profiles, "random"),
        profiles,
        labels,
    )
    for metric in ("precision_at_k", "mrr", "ndcg_at_k", "primary_recall_at_k"):
        assert oracle.headline[metric] > chance.headline[metric], metric


def test_a_run_survives_a_round_trip_through_disk(
    tmp_path: Path, profiles: list[EvalProfile], labels: dict[str, list[Label]]
) -> None:
    """The expensive half runs once; the cheap half must be able to re-read it."""
    run = record_run(make_oracle_scorer(labels), profiles, scorer_name="oracle")
    path = tmp_path / "run.json"
    save_run(run, path)
    reloaded = load_run(path)
    assert reloaded.scorer_name == run.scorer_name
    assert [r.profile_id for r in reloaded.runs] == [r.profile_id for r in run.runs]
    assert evaluate(reloaded, profiles, labels).headline == evaluate(
        run, profiles, labels
    ).headline


def test_report_renders_without_blowing_up(
    profiles: list[EvalProfile], labels: dict[str, list[Label]]
) -> None:
    run = record_run(make_oracle_scorer(labels), profiles, scorer_name="oracle")
    text = format_report(evaluate(run, profiles, labels))
    assert "MACRO MEAN" in text
    assert "p01_backend_eng_stay" in text
    # The degenerate row is visible in the report, never silently dropped.
    assert "p19_degenerate_no_title_no_skills" in text


# ---------------------------------------------------------------------------
# The live baseline run stays under an explicit lock
# ---------------------------------------------------------------------------


def test_record_run_checkpoints_after_every_profile(tmp_path: Path) -> None:
    """A ~3,000-request run must not lose everything when the last one fails.

    The live baseline takes tens of minutes and spends a shared rate limit.
    Without a checkpoint, a timeout on the twentieth profile means paying for
    the first nineteen again.
    """
    saved: list[int] = []

    def _on_progress(latest: ProfileRun, so_far: list[ProfileRun]) -> None:
        path = tmp_path / "partial.json"
        save_run(ScorerRun("t", "(in progress)", list(so_far)), path)
        saved.append(len(load_run(path).runs))

    profiles = [_profile("p1"), _profile("p2"), _profile("p3")]
    run = record_run(
        lambda p: _results("a"), profiles, scorer_name="t", on_progress=_on_progress
    )
    assert saved == [1, 2, 3], "every profile must be checkpointed, not just the last"
    assert len(run.runs) == 3


def test_funnel_ceiling_separates_a_ranking_miss_from_an_unreachable_answer(
    profiles: list[EvalProfile], labels: dict[str, list[Label]]
) -> None:
    """Records what today's candidate funnel can even reach, before ranking.

    `_filter_candidate_pool`'s SOC allow-list admits only 11/13/15/17/23/25/41/43
    unless a skill keyword unlocks more, so entire families are invisible to the
    scorer regardless of how it ranks.  Without this, a profile scoring zero on
    the baseline looks like a ranking failure when the right answer was never a
    candidate -- and F-4 would tune weights against a problem F-3 owns.
    """
    rows = path_eval.funnel_ceiling(profiles, labels)
    by_id = {row["profile_id"]: row for row in rows}

    # A tech profile's answers are all inside the default allow-list.
    tech = by_id["p01_backend_eng_stay"]
    assert tech["reachable_primary"] == tech["primary_labels"]

    # A skilled-trade profile's are entirely outside it: 47- and 49- are not
    # admitted and no skill keyword unlocks them.  This is a real product
    # defect, recorded here so the baseline run confirms rather than discovers it.
    trade = by_id["p14_electrician_stay"]
    assert trade["primary_labels"] > 0
    assert trade["reachable_primary"] == 0, (
        "if this starts passing, the allow-list changed -- re-read the baseline "
        "before comparing it to anything"
    )

    # Healthcare is reachable only because the profile carries an unlocking
    # skill keyword; that conditional path is worth pinning too.
    nurse = by_id["p11_rn_stay"]
    assert "29-" in nurse["allowed_soc_prefixes"]


def test_cost_projection_is_stated_and_makes_no_calls(
    profiles: list[EvalProfile],
) -> None:
    cost = project_cost(len(profiles))
    assert cost["profiles"] == len(profiles)
    assert isinstance(cost["onet_requests_estimate"], int)
    assert cost["onet_requests_estimate"] > 1000, (
        "if this ever looks cheap, re-derive it before anyone fires it"
    )
    assert "estimate" in str(cost["basis"]) or "§1.2" in str(cost["basis"])


def test_record_live_refuses_without_explicit_confirmation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The live run spends a shared O*NET budget and must never happen by accident.

    Two agents racing the same rate limit is how both fail, so `record-live`
    exits non-zero and prints the projected cost unless the caller has said
    plainly that they mean it.  The refusal path makes no imports of the
    scorer, so this test needs neither an O*NET key nor OpenAI.
    """
    rc = path_eval.main(["record-live", "--out", "unused.json"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "REFUSING TO RUN" in out
    assert "onet_requests_estimate" in out
    assert not Path("unused.json").exists()


def test_live_scorer_wiring_is_correct_without_making_a_single_call(
    monkeypatch: pytest.MonkeyPatch, profiles: list[EvalProfile]
) -> None:
    """The live path must not discover a signature mistake mid-baseline.

    `score_paths` itself is stubbed -- it is the O*NET/OpenAI boundary and the
    one thing CLAUDE.md's "prefer real dependencies" rule exempts -- but
    everything either side of it is real: the fixture row becomes a genuine
    `UserProfile`, and `ScoredPath` becomes `RankedResult`.  Those two
    conversions are the whole of what could break when the overseer finally
    fires the run, and a 3,000-request run is not the place to find out.
    """
    from backend.services import path_scoring

    seen: list[object] = []

    def _fake_score_paths(user_profile, onet_client, openai_client):  # type: ignore[no-untyped-def]
        seen.append(user_profile)
        assert onet_client == "ONET"
        assert openai_client == "OPENAI"
        return [path_scoring.ScoredPath(onet_code="15-1252.00", title="Software Developers", score=0.8)]

    monkeypatch.setattr(path_scoring, "score_paths", _fake_score_paths)

    scorer = path_eval.make_live_scorer("ONET", "OPENAI")
    results = scorer(profiles[0])

    assert len(seen) == 1
    assert isinstance(seen[0], path_scoring.UserProfile)
    assert seen[0].current_title == profiles[0].raw_profile["current_title"]
    assert results == [
        RankedResult(onet_code="15-1252.00", title="Software Developers", score=0.8)
    ]


def test_cost_and_review_subcommands_run_offline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert path_eval.main(["cost"]) == 0
    assert "onet_requests_estimate" in capsys.readouterr().out

    assert path_eval.main(["review"]) == 0
    assert "flagged confidence=low" in capsys.readouterr().out

    assert path_eval.main(["ceiling"]) == 0
    assert "reachable/primary" in capsys.readouterr().out


def test_control_scorers_run_from_the_command_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert path_eval.main(["record-control", "oracle"]) == 0
    assert "MACRO MEAN" in capsys.readouterr().out


def test_the_harness_does_not_import_the_scorer_to_evaluate(
    tmp_path: Path, profiles: list[EvalProfile], labels: dict[str, list[Label]]
) -> None:
    """`evaluate` must stay dependency-light.

    Metric work should never need numpy, an OpenAI key or an O*NET key.  This
    checks the seam holds by scoring a recorded run read from disk with nothing
    but the fixtures.
    """
    payload = {
        "scorer_name": "synthetic",
        "recorded_at": "2026-09-16T00:00:00Z",
        "notes": "",
        "runs": [
            {
                "profile_id": "p01_backend_eng_stay",
                "results": [
                    {"onet_code": "15-1252.00", "title": "Software Developers", "score": 0.9}
                ],
                "elapsed_s": 0.0,
                "error": None,
            }
        ],
    }
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = evaluate(load_run(path), profiles, labels)
    assert report.headline["profiles_scored"] == 1.0
    assert report.headline["mrr"] == 1.0
