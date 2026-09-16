"""Tests for the F-5 Tier-2 deep fit.

The six maths helpers here arrived from `path_scoring` unchanged, and so did
their tests -- the four cases at the bottom of this file are byte-identical to
the ones `tests/test_path_scoring.py::TestTierTwoHelpers` held before the move,
because a move whose tests were rewritten on the way is not a move you can
check.

Everything above them is new: the four-call budget, the degrade-don't-fail
behaviour of each call, the three `UnknownOccupation` reasons, and the fact that
the retrieval cosine reported here is the same number Tier 1 ranked the card by.

The corpus is the same hand-written synthetic world `test_path_scoring` builds,
imported rather than rebuilt so a change to one cannot silently diverge from the
other.  Anything reaching the real 1,016-row artifact is marked `real_corpus`
and skips cleanly when `SOLVERAH_CORPUS_PATH` is unset -- CI has no artifact.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import numpy as np
import pytest

import backend.services.path_deep_fit as pdf
import backend.services.path_scoring as ps
from backend.services.occupation_retrieval import CorpusUnavailable
from backend.services.onet_client import OnetAPIError, OnetClient, Skill, Task
from backend.services.path_deep_fit import UnknownOccupation, deep_fit
from backend.services.path_scoring import InsufficientProfile

from tests.test_path_scoring import (  # the one synthetic world, not a second
    TECH,
    TRADE,
    WORLD_ROWS,
    WORLD_ZONES,
    FakeOpenAI,
    build_corpus,
    profile,
    tech_openai,
    unit,
    user_skill,
)

CODE = "15-1251.00"          # Computer Programmers -- a real row, not the anchor
RESIDUAL = "15-1299.99"      # "Computer Occupations, All Other"
ABSENT = "99-9999.00"        # well-formed, not in the corpus


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


def onet_skill(name: str, importance: float = 50.0, level: float = 3.0) -> Skill:
    return Skill(element_id="2.A.1.a", name=name, importance=importance, level=level)


def onet_task(title: str, importance: float = 80.0) -> Task:
    return Task(task_id="1", title=title, importance=importance, category="Core")


@pytest.fixture(autouse=True)
def _clear_embed_cache():
    ps._EMBED_CACHE.clear()
    yield
    ps._EMBED_CACHE.clear()


@pytest.fixture()
def world(monkeypatch):
    """The synthetic corpus, installed for both modules' `get_corpus`."""
    corpus = build_corpus(WORLD_ROWS, WORLD_ZONES)
    monkeypatch.setattr(pdf, "get_corpus", lambda: corpus)
    monkeypatch.setattr(ps, "get_corpus", lambda: corpus)
    return corpus


@pytest.fixture()
def onet() -> MagicMock:
    """An O*NET client answering the four Tier-2 calls and nothing else.

    `search_occupations` and `get_job_zone` raise: anchor resolution is supposed
    to come from the corpus, and a test that quietly started paying for it would
    otherwise pass.
    """
    client = MagicMock(spec=OnetClient)
    client.get_skills_profile.return_value = [
        onet_skill("Programming", 90.0),
        onet_skill("Critical Thinking", 70.0),
        onet_skill("Trivia", 10.0),
    ]
    client.get_hot_technologies.return_value = ["Python", "Git"]
    client.get_work_activities.return_value = [
        onet_skill("Analyzing Data", 80.0),
        onet_skill("Filing", 20.0),
    ]
    client.get_tasks.return_value = [
        onet_task("Write and test code."),
        onet_task("Review pull requests.", 60.0),
    ]
    client.search_occupations.side_effect = AssertionError("unexpected O*NET search")
    client.get_job_zone.side_effect = AssertionError("unexpected get_job_zone")
    return client


def fitted_profile(**kwargs):
    return profile(skills=[user_skill("Python", "advanced")], **kwargs)


# ---------------------------------------------------------------------------
# The call budget -- the whole reason this tier is a second tier
# ---------------------------------------------------------------------------


class TestCallBudget:
    def test_exactly_four_onet_calls_for_one_occupation(self, world, onet) -> None:
        user = fitted_profile()
        fit = deep_fit(user, CODE, onet, tech_openai(user))

        assert onet.get_skills_profile.call_count == 1
        assert onet.get_hot_technologies.call_count == 1
        assert onet.get_work_activities.call_count == 1
        assert onet.get_tasks.call_count == 1
        assert fit.onet_calls == 4

    def test_every_call_names_the_one_requested_code(self, world, onet) -> None:
        user = fitted_profile()
        deep_fit(user, CODE, onet, tech_openai(user))

        for method in (
            onet.get_skills_profile,
            onet.get_hot_technologies,
            onet.get_work_activities,
            onet.get_tasks,
        ):
            assert method.call_args.args == (CODE,), "a call fanned out off the code"

    def test_one_embedding_request(self, world, onet) -> None:
        """Every text the fit needs goes in one batch, so nothing later blocks."""
        user = fitted_profile()
        client = tech_openai(user)
        deep_fit(user, CODE, onet, client)
        assert client.calls == 1

    def test_get_tech_skills_is_not_used(self, world, onet) -> None:
        """`get_hot_technologies` is ordered; `get_tech_skills(hot_only=True)` is a set.

        F-1 added the former for exactly this reason -- "the top N" is
        unanswerable over a set, and Python's per-process string hash
        randomisation would reorder the panel between workers.
        """
        user = fitted_profile()
        deep_fit(user, CODE, onet, tech_openai(user))
        assert onet.get_tech_skills.call_count == 0


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


class TestRefusals:
    @pytest.mark.parametrize(
        "code, reason",
        [
            ("not-a-code", "malformed"),
            ("15-1252", "malformed"),
            ("", "malformed"),
            ("15-1252.00.00", "malformed"),
            (ABSENT, "unknown"),
            (RESIDUAL, "residual"),
        ],
    )
    def test_reason_is_typed_so_the_ui_can_branch(
        self, world, onet, code: str, reason: str
    ) -> None:
        user = fitted_profile()
        with pytest.raises(UnknownOccupation) as excinfo:
            deep_fit(user, code, onet, tech_openai(user))
        assert excinfo.value.reason == reason
        assert excinfo.value.code == code

    def test_a_refusal_costs_no_onet_calls(self, world, onet) -> None:
        """The corpus answers "does this exist", so a bad code is free."""
        user = fitted_profile()
        with pytest.raises(UnknownOccupation):
            deep_fit(user, ABSENT, onet, tech_openai(user))
        assert onet.get_skills_profile.call_count == 0

    def test_no_title_and_no_skills_is_typed_not_empty(self, world, onet) -> None:
        """The F-4 branch: `profile_incomplete`, not a 500 the user can only retry."""
        empty = profile(current_title=None, skills=[], career_status="first_job")
        with pytest.raises(InsufficientProfile):
            deep_fit(empty, CODE, onet, None)

    def test_a_corpus_outage_propagates_as_its_own_typed_error(
        self, monkeypatch, onet
    ) -> None:
        def _boom():
            raise CorpusUnavailable("no artifact")

        monkeypatch.setattr(pdf, "get_corpus", _boom)
        with pytest.raises(CorpusUnavailable):
            deep_fit(fitted_profile(), CODE, onet, None)


# ---------------------------------------------------------------------------
# Degrading rather than failing
# ---------------------------------------------------------------------------


class TestDegradation:
    def test_a_failed_task_fetch_empties_one_list_and_nothing_else(
        self, world, onet
    ) -> None:
        onet.get_tasks.side_effect = OnetAPIError("502")
        user = fitted_profile()
        fit = deep_fit(user, CODE, onet, tech_openai(user))

        assert fit.tasks == []
        assert fit.tech_stack, "an unrelated call was dropped with it"
        assert fit.fit_score > 0.0
        assert fit.onet_calls == 4, "a failed call still spent a request"

    def test_a_failed_skills_fetch_leaves_the_rest_of_the_panel(
        self, world, onet
    ) -> None:
        onet.get_skills_profile.side_effect = OnetAPIError("502")
        user = fitted_profile()
        fit = deep_fit(user, CODE, onet, tech_openai(user))

        assert fit.tasks and fit.tech_stack
        assert fit.zone.occupation_zone == WORLD_ZONES[CODE]

    def test_no_openai_client_degrades_to_zone_and_title(self, world, onet) -> None:
        """The same promise `score_paths` makes for a missing OPENAI_API_KEY."""
        onet.search_occupations.side_effect = None
        onet.search_occupations.return_value = []
        fit = deep_fit(fitted_profile(), CODE, onet, None)

        assert fit.title == "Computer Programmers"
        assert fit.matched_skills == []
        assert fit.gap_skills == []
        assert fit.coverage_score == 0.0

    def test_an_occupation_with_no_data_at_all_still_returns_a_fit(
        self, world, onet
    ) -> None:
        onet.get_skills_profile.return_value = []
        onet.get_hot_technologies.return_value = []
        onet.get_work_activities.return_value = []
        onet.get_tasks.return_value = []
        user = fitted_profile()
        fit = deep_fit(user, CODE, onet, tech_openai(user))

        assert fit.onet_code == CODE
        assert 0.0 <= fit.fit_score <= 1.0


# ---------------------------------------------------------------------------
# What the panel says
# ---------------------------------------------------------------------------


class TestThePanel:
    def test_matched_skills_name_the_users_own_skills(self, world, onet) -> None:
        user = fitted_profile()
        client = tech_openai(user)
        # Every text embeds to TECH, so the user's Python matches every role item.
        client.embeddings.table.update({"python": TECH, "Python": TECH, "Git": TECH})
        fit = deep_fit(user, CODE, onet, client)
        assert fit.matched_skills == ["Python"]

    def test_gaps_are_role_items_the_user_does_not_reach(self, world, onet) -> None:
        """A user whose skills point one way and a role that points the other."""
        user = fitted_profile()
        client = tech_openai(user)
        client.embeddings.table.update(
            {
                "python": TECH,
                "Python": TRADE,
                "Git": TRADE,
                "Programming": TRADE,
                "Critical Thinking": TRADE,
            }
        )
        fit = deep_fit(user, CODE, onet, client)

        names = [gap.name for gap in fit.gap_skills]
        assert "Programming" in names
        assert "Trivia" not in names, "an unimportant item became a gap"
        importances = [gap.importance for gap in fit.gap_skills]
        assert importances == sorted(importances, reverse=True)

    def test_gaps_are_empty_when_no_user_skill_could_be_embedded(
        self, world, onet
    ) -> None:
        """Not "everything is a gap" -- that would read as a judgement about the
        person when the truth is that the embedding provider was unreachable."""
        assert pdf._gap_skills([user_skill("Python")], [("Programming", 90.0)]) == []

    def test_tasks_and_tech_are_carried_in_the_order_onet_ranked_them(
        self, world, onet
    ) -> None:
        user = fitted_profile()
        fit = deep_fit(user, CODE, onet, tech_openai(user))
        assert fit.tasks == ["Write and test code.", "Review pull requests."]
        assert fit.tech_stack == ["Python", "Git"]

    def test_role_items_keep_onets_ranking_not_the_alphabet(self, world, onet) -> None:
        """`_build_role_profile` takes a set, and a set has no order.

        Two runs over one occupation must produce the same panel, so the items
        are sorted after building -- and the tie-break is O*NET's own ranking,
        because every hot technology carries the same flat importance and
        falling through to the name spends the panel on whatever starts with A.
        See `_role_items_for` for the live measurement that says so.
        """
        data = pdf._OccupationData(
            generic_skills=[onet_skill("Zebra", 90.0), onet_skill("Apple", 90.0)],
            hot_tech=["Snowflake", "Airflow"],
        )
        items = pdf._role_items_for(data)
        assert items == pdf._role_items_for(data)
        # Importance descending first: the generic skills at 90 outrank the two
        # tools at _HOT_TECH_IMPORTANCE. Inside each tie, the order O*NET gave.
        assert [name for name, _ in items] == ["Zebra", "Apple", "Snowflake", "Airflow"]

    def test_gaps_are_listed_in_onets_order_within_an_importance_tie(self) -> None:
        """The defect this file's sort exists to stop, as a test.

        Two equally important tools the user has neither of: the one O*NET ranks
        first is the one the panel names first, whatever the letters say.
        """
        ps._EMBED_CACHE["python"] = unit(1, 0)
        ps._EMBED_CACHE["Snowflake"] = unit(0, 1)
        ps._EMBED_CACHE["Airflow"] = unit(0, 1)
        data = pdf._OccupationData(hot_tech=["Snowflake", "Airflow"])
        gaps = pdf._gap_skills(
            [user_skill("Python", "advanced")], pdf._role_items_for(data)
        )
        assert [gap.name for gap in gaps] == ["Snowflake", "Airflow"]

    def test_the_payload_is_plain_json(self, world, onet) -> None:
        import json

        user = fitted_profile()
        fit = deep_fit(user, CODE, onet, tech_openai(user))
        # Round-trips, so it can go into a JSONB column and back out unchanged.
        assert json.loads(json.dumps(fit.to_dict())) == fit.to_dict()


# ---------------------------------------------------------------------------
# Zone feasibility
# ---------------------------------------------------------------------------


class TestZoneFit:
    def test_the_users_zone_comes_from_the_corpus_at_no_cost(
        self, world, onet
    ) -> None:
        user = fitted_profile()
        fit = deep_fit(user, CODE, onet, tech_openai(user))

        assert fit.zone.user_zone == WORLD_ZONES["15-1252.00"]
        assert fit.zone.user_zone_resolved is True
        assert fit.zone.occupation_zone == WORLD_ZONES[CODE]
        assert fit.zone.delta == 0
        assert onet.get_job_zone.call_count == 0

    def test_a_missing_occupation_zone_is_neutral_not_a_penalty(
        self, monkeypatch, onet
    ) -> None:
        corpus = build_corpus(WORLD_ROWS, {"15-1252.00": 4})  # CODE has no zone
        monkeypatch.setattr(pdf, "get_corpus", lambda: corpus)
        monkeypatch.setattr(ps, "get_corpus", lambda: corpus)

        user = fitted_profile()
        fit = deep_fit(user, CODE, onet, tech_openai(user))

        assert fit.zone.occupation_zone is None
        assert fit.zone.delta is None
        assert fit.zone.score == pytest.approx(
            ps._zone_delta_score(4, None, None), abs=1e-4
        )
        assert fit.zone.score > 0.0, "a missing zone was scored as a penalty"


# ---------------------------------------------------------------------------
# The retrieval cosine is the card's own number
# ---------------------------------------------------------------------------


class TestRetrievalCosine:
    def test_it_matches_what_tier_one_ranked_the_card_by(self, world, onet) -> None:
        """Not a second, differently-defined similarity.

        A panel whose headline number disagreed with the list the user just
        clicked in would be a bug report, so this uses `path_scoring._build_query`
        itself -- the same query vector, dotted against the same corpus row.
        """
        user = fitted_profile(move_intent="stay_in_field")
        fit = deep_fit(user, CODE, onet, tech_openai(user))

        corpus = world
        anchor_vec = corpus.vector_for("15-1252.00")   # stay_in_field anchors here
        expected = float(np.dot(corpus.matrix[corpus.index_of(CODE)], anchor_vec))
        assert fit.retrieval_cosine == pytest.approx(expected, abs=1e-4)

    def test_the_weight_split_is_tier_ones(self, world, onet) -> None:
        user = fitted_profile()
        fit = deep_fit(user, CODE, onet, tech_openai(user))
        assert sum(fit.weights.values()) == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------------------
# The six moved functions -- cases unchanged from test_path_scoring.py
# ---------------------------------------------------------------------------


class TestTierTwoHelpers:
    def test_build_role_profile_merges_hot_tech_and_important_generic(self) -> None:
        items = pdf._build_role_profile(
            {"Python"}, [onet_skill("Active Listening", 80.0), onet_skill("Trivia", 10.0)]
        )
        assert ("Python", pdf._HOT_TECH_IMPORTANCE) in items
        assert ("Active Listening", 80.0) in items
        assert not any(name == "Trivia" for name, _ in items)

    def test_centroid_score_reads_the_embedding_cache(self) -> None:
        ps._EMBED_CACHE["python"] = unit(1, 0)
        ps._EMBED_CACHE["Python"] = unit(1, 0)
        score, matched = pdf._compute_centroid_score(
            [user_skill("Python", "advanced")], [("Python", 90.0)]
        )
        assert score == pytest.approx(1.0)
        assert matched == ["Python"]

    def test_centroid_score_is_zero_when_nothing_is_cached(self) -> None:
        assert pdf._compute_centroid_score(
            [user_skill("Python")], [("Python", 90.0)]
        ) == (0.0, [])

    def test_role_coverage_full_and_empty(self) -> None:
        ps._EMBED_CACHE["python"] = unit(1, 0)
        ps._EMBED_CACHE["Python"] = unit(1, 0)
        assert pdf._role_coverage_score(
            [user_skill("Python", "advanced")], [("Python", 90.0)]
        ) == 1.0
        assert pdf._role_coverage_score([user_skill("Python")], []) == 0.0

    def test_work_style_similarity_degrades_to_zero(self) -> None:
        assert pdf._work_style_similarity(
            "profile text", [("Analyzing Data", 80.0)], None
        ) == 0.0
        assert pdf._work_style_similarity("profile text", [], FakeOpenAI()) == 0.0

    def test_the_shared_embedding_cache_is_path_scorings(self) -> None:
        """One cache across both tiers, not two.

        `path_scoring`'s `_EMBED_CACHE` comment budgets 32 MB for exactly one of
        these, and `tests/test_cache_bounds.py` measures that one.  A second
        dict here would double the resident cost of the tier that caused the
        2026-09-15 OOM while halving nothing.
        """
        assert pdf._EMBED_CACHE is ps._EMBED_CACHE


# ---------------------------------------------------------------------------
# Against the real 1,016-row artifact
# ---------------------------------------------------------------------------

real_corpus = pytest.mark.skipif(
    not os.environ.get("SOLVERAH_CORPUS_PATH"),
    reason="SOLVERAH_CORPUS_PATH is unset; CI has no corpus artifact",
)


@real_corpus
class TestAgainstTheRealCorpus:
    def test_every_all_other_row_is_refused(self) -> None:
        """75 residual rows, and retrieval already keeps them off shortlists."""
        from backend.services.occupation_retrieval import get_corpus, is_all_other_title

        corpus = get_corpus()
        residuals = [
            code for code in corpus.codes
            if is_all_other_title(corpus.titles[corpus.index_of(code)])
        ]
        assert len(residuals) > 50
        for code in residuals[:20]:
            with pytest.raises(UnknownOccupation) as excinfo:
                pdf._resolve_row(code, corpus)
            assert excinfo.value.reason == "residual"

    def test_a_real_code_resolves_to_its_real_title(self) -> None:
        from backend.services.occupation_retrieval import get_corpus

        corpus = get_corpus()
        row = pdf._resolve_row("15-1252.00", corpus)
        assert corpus.titles[row] == "Software Developers"


def test_a_malformed_code_is_refused_before_the_corpus_is_loaded(monkeypatch, onet):
    """A permanent 404 must not hide behind a transient 503.

    `get_corpus` raises here, as it does in CI and during an S3 outage. A
    malformed code still answers `malformed` -- if the order were the other way
    round the caller would spend the whole outage retrying a code that will
    never work.
    """
    def _boom():
        raise CorpusUnavailable("no artifact")

    monkeypatch.setattr(pdf, "get_corpus", _boom)
    with pytest.raises(UnknownOccupation) as excinfo:
        deep_fit(profile(skills=[user_skill("Python")]), "not-a-code", onet, None)
    assert excinfo.value.reason == "malformed"
