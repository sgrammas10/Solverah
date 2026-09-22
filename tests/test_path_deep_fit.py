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

import backend.services.occupation_fit as occupation_fit
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


@pytest.fixture(autouse=True)
def _clear_fit_memo():
    """W-9's sidecar memo is a module global, so it must not cross tests.

    Every test above `TestTheFitSidecar` runs with **no** sidecar -- the
    synthetic corpus has no `.fit.json` beside it -- which is why the four-call
    budget below is still four.
    """
    occupation_fit.reset_fit_cache()
    yield
    occupation_fit.reset_fit_cache()


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


def outsider_profile(**kwargs):
    """A user who owns NONE of the tools the `onet` double returns.

    W-12 made `tech_stack` the tools *no other section already showed*, so a
    test about what that list carries -- where it came from, what order it is in
    -- must be run by someone whose own skills take nothing out of it.
    `fitted_profile`'s "Python" is one of the two tools the double returns, and
    a test asserting the list still reads `["Python", "Git"]` for that user
    would be asserting the defect.  Nothing here is about the dedup itself; the
    three cases that are live in `TestThePanel`.
    """
    return profile(skills=[user_skill("Bookkeeping", "advanced")], **kwargs)


def outsider_fit(user, onet, code: str = CODE):
    """`deep_fit` for an outsider, with no OpenAI client.

    No client is the point rather than a shortcut.  WITH embeddings every role
    item is either something a user skill reached (a match) or something none of
    them did (a gap), so "a tool in neither list" is a narrow state to arrange
    and a brittle thing to assert around -- and the synthetic double answers
    every text it does not know with one shared vector, which makes any user
    skill match anything at cosine 1.0.  Without a client there are no cosines,
    no matches, and -- by :func:`_gap_skills`' own degrade rule -- no measurable
    gaps, so `tech_stack` is the raw list O*NET ranked.  That is the state the
    tests below are about: where the list came from and what order it is in.

    The `search_occupations` stub is the no-client anchor fallback: without
    embeddings, `_resolve_current_zone` cannot read the user's own title off the
    corpus and asks O*NET instead.
    """
    onet.search_occupations.side_effect = None
    onet.search_occupations.return_value = []
    return deep_fit(user, code, onet, None)


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
# W-9: the same four answers, out of a file
# ---------------------------------------------------------------------------
#
# Everything the four calls return is static per occupation, so `flask corpus
# fit` fetches the catalog once and `_stored_occupation` reads it. The claim is
# not "it is faster" -- that is measured offline, against the real artifact, and
# recorded in W-9's landing note. The claim these tests make is the one a test
# can make: the sidecar path spends NOTHING at O*NET and produces the SAME
# `DeepFit` the live path produces from the same data.


def fit_table_matching(onet_double, code: str = CODE) -> occupation_fit.FitTable:
    """A `FitTable` holding exactly what the `onet` double would have answered.

    Built from the double's own return values rather than restated, so the
    equivalence assertion below is about the two code paths and cannot pass
    because two hand-written fixtures happened to agree.
    """
    return occupation_fit.FitTable(
        fits={
            code: occupation_fit.OccupationFit(
                generic_skills=tuple(
                    occupation_fit.FitElement(
                        s.element_id, s.name, s.importance, s.level
                    )
                    for s in onet_double.get_skills_profile.return_value
                ),
                hot_tech=tuple(onet_double.get_hot_technologies.return_value),
                work_activities=tuple(
                    occupation_fit.FitElement(
                        a.element_id, a.name, a.importance, a.level
                    )
                    for a in onet_double.get_work_activities.return_value
                ),
                tasks=tuple(
                    occupation_fit.FitTask(
                        t.task_id, t.title, t.importance, t.category
                    )
                    for t in onet_double.get_tasks.return_value
                ),
                parts=occupation_fit.FIT_PARTS,
            )
        }
    )


class TestTheFitSidecar:
    def test_a_hit_costs_no_onet_call_at_all(self, world, onet, monkeypatch) -> None:
        table = fit_table_matching(onet)
        monkeypatch.setattr(occupation_fit, "get_fit_table", lambda corpus: table)
        user = fitted_profile()

        fit = deep_fit(user, CODE, onet, tech_openai(user))

        assert onet.get_skills_profile.call_count == 0
        assert onet.get_hot_technologies.call_count == 0
        assert onet.get_work_activities.call_count == 0
        assert onet.get_tasks.call_count == 0
        assert fit.onet_calls == 0

    def test_a_hit_still_costs_exactly_one_embedding_request(
        self, world, onet, monkeypatch
    ) -> None:
        """The embeddings batch is what is left of the click, so it must not
        quietly become two."""
        table = fit_table_matching(onet)
        monkeypatch.setattr(occupation_fit, "get_fit_table", lambda corpus: table)
        user = fitted_profile()
        client = tech_openai(user)

        deep_fit(user, CODE, onet, client)

        assert client.calls == 1

    def test_the_two_paths_produce_the_same_fit(
        self, world, onet, monkeypatch
    ) -> None:
        """The equivalence, as an assertion rather than an argument.

        Same user, same corpus, same four answers -- once through O*NET and once
        through the file. Everything the panel renders has to match; the only
        field allowed to differ is the one that reports what was spent.
        """
        user = fitted_profile()
        live = deep_fit(user, CODE, onet, tech_openai(user)).to_dict()

        table = fit_table_matching(onet)
        monkeypatch.setattr(occupation_fit, "get_fit_table", lambda corpus: table)
        ps._EMBED_CACHE.clear()
        stored = deep_fit(user, CODE, onet, tech_openai(user)).to_dict()

        assert live.pop("onet_calls") == 4
        assert stored.pop("onet_calls") == 0
        assert stored == live

    def test_the_read_applies_the_same_filters_the_live_path_applies(
        self, world, onet, monkeypatch
    ) -> None:
        """Nothing is filtered at BUILD time, so everything must be filtered at
        READ time -- otherwise the sidecar path scores a role the live path
        never would. `Filing` is under the work-activity threshold and `Trivia`
        under the generic-skill one.
        """
        table = fit_table_matching(onet)
        monkeypatch.setattr(occupation_fit, "get_fit_table", lambda corpus: table)

        data = pdf._fetch_occupation(CODE, onet)

        assert data.work_activities == [("Analyzing Data", 80.0)]
        # Importance descending: Programming 90, the two tools at the flat
        # _HOT_TECH_IMPORTANCE of 75 in O*NET's own order, Critical Thinking 70.
        assert [name for name, _ in pdf._role_items_for(data)] == [
            "Programming", "Python", "Git", "Critical Thinking"
        ]

    def test_a_partial_record_is_used_rather_than_refetched(
        self, world, onet, monkeypatch
    ) -> None:
        """Three answers is a thinner panel. Going back to O*NET for the fourth
        would reintroduce the latency for the occupations most likely to be
        clicked twice."""
        table = occupation_fit.FitTable(
            fits={
                CODE: occupation_fit.OccupationFit(
                    hot_tech=("Python",), parts=("hot_technologies",)
                )
            }
        )
        monkeypatch.setattr(occupation_fit, "get_fit_table", lambda corpus: table)
        user = outsider_profile()

        fit = outsider_fit(user, onet)

        assert fit.onet_calls == 0
        assert fit.tech_stack == ["Python"]
        assert fit.tasks == []
        assert onet.get_tasks.call_count == 0

    def test_a_code_the_table_lacks_falls_through_to_the_live_path(
        self, world, onet, monkeypatch
    ) -> None:
        table = fit_table_matching(onet, code="29-1141.00")
        monkeypatch.setattr(occupation_fit, "get_fit_table", lambda corpus: table)
        user = fitted_profile()

        fit = deep_fit(user, CODE, onet, tech_openai(user))

        assert fit.onet_calls == 4
        assert onet.get_skills_profile.call_count == 1

    def test_no_sidecar_at_all_is_the_live_path(self, world, onet) -> None:
        """The degrade. The synthetic corpus has no `.fit.json` beside it, which
        is the state every other test in this file runs in."""
        user = fitted_profile()

        fit = deep_fit(user, CODE, onet, tech_openai(user))

        assert fit.onet_calls == 4

    def test_a_sidecar_with_the_wrong_schema_version_is_the_live_path(
        self, monkeypatch, onet, tmp_path
    ) -> None:
        """Through the real loader, not a stub: a file this build cannot read is
        a slow click, never a wrong one or a 500."""
        import dataclasses
        import json

        corpus = dataclasses.replace(
            build_corpus(WORLD_ROWS, WORLD_ZONES),
            matrix_path=tmp_path / "onet_corpus_x.npy",
        )
        monkeypatch.setattr(pdf, "get_corpus", lambda: corpus)
        monkeypatch.setattr(ps, "get_corpus", lambda: corpus)
        (tmp_path / "onet_corpus_x.fit.json").write_text(
            json.dumps({"schema_version": 99, "fits": {CODE: {"parts": ["tasks"]}}}),
            encoding="utf-8",
        )
        user = fitted_profile()

        fit = deep_fit(user, CODE, onet, tech_openai(user))

        assert fit.onet_calls == 4
        assert onet.get_tasks.call_count == 1

    def test_a_real_sidecar_beside_the_artifact_is_read_by_the_real_loader(
        self, monkeypatch, onet, tmp_path
    ) -> None:
        """The other half of the previous test: the whole chain, file included."""
        import dataclasses

        corpus = dataclasses.replace(
            build_corpus(WORLD_ROWS, WORLD_ZONES),
            matrix_path=tmp_path / "onet_corpus_x.npy",
        )
        monkeypatch.setattr(pdf, "get_corpus", lambda: corpus)
        monkeypatch.setattr(ps, "get_corpus", lambda: corpus)
        occupation_fit.write_fit_sidecar(
            corpus.matrix_path, fit_table_matching(onet)
        )
        user = outsider_profile()

        fit = outsider_fit(user, onet)

        assert fit.onet_calls == 0
        assert fit.tech_stack == ["Python", "Git"]


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

    def test_no_openai_client_degrades_to_zone_title_and_exact_matches(
        self, world, onet
    ) -> None:
        """The same promise `score_paths` makes for a missing OPENAI_API_KEY.

        **Improved by F-8 box 5, and this test changed with it.** It used to
        assert `matched_skills == []`, because every match went through a
        cosine and there were no vectors. Identity needs none: a user who
        listed "Python" against a role that names "Python" is a match whatever
        the embedding provider is doing. The SCORES still degrade to zero --
        those genuinely need both centroids -- so what the panel loses in an
        outage is the numbers, not the plain facts.
        """
        onet.search_occupations.side_effect = None
        onet.search_occupations.return_value = []
        fit = deep_fit(fitted_profile(), CODE, onet, None)

        assert fit.title == "Computer Programmers"
        assert fit.matched_skills == ["Python"]
        assert fit.gap_skills == [], (
            "without embeddings there are no MEASURABLE gaps -- reporting every "
            "requirement as missing would read as a judgement about the person"
        )
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
        user = outsider_profile()
        fit = outsider_fit(user, onet)
        assert fit.tasks == ["Write and test code.", "Review pull requests."]
        assert fit.tech_stack == ["Python", "Git"]

    # -- W-12: a tool is shown once, in the most specific section that applies --
    #
    # The first browser test read "Skills you already have: SQL, Amazon Web
    # Services", then "Worth picking up" repeating most of the role's tools,
    # then "Tools people use: Structured query language SQL, Amazon Web Services
    # AWS software" -- the tester's own two skills a second time, under O*NET's
    # cataloguing names, beside the short names they had just been shown.

    def test_a_tool_the_user_has_by_identity_is_shown_once_under_their_own_name(
        self, world, onet
    ) -> None:
        """The tester's SQL, with O*NET's real spelling of it.

        No OpenAI client on purpose: the match that has to hold here is the
        identity one -- F-8's `skill_aliases` -- and an embedding double would
        let a cosine make the test pass for a reason this half does not rely on.
        """
        onet.get_hot_technologies.return_value = ["Structured query language SQL", "Git"]
        user = profile(skills=[user_skill("SQL", "advanced")])
        onet.search_occupations.side_effect = None  # the no-client anchor fallback
        onet.search_occupations.return_value = []

        fit = deep_fit(user, CODE, onet, None)

        assert fit.matched_skills == ["SQL"], "the user's own name, not O*NET's"
        assert fit.tech_stack == ["Git"], "'Structured query language SQL' came back"

    def test_a_tool_the_user_has_by_cosine_is_shown_once_too(
        self, world, onet
    ) -> None:
        """The tester's AWS, and the reason the dedup cannot work on names.

        "Amazon Web Services" and "Amazon Web Services AWS software" share no
        alias -- nothing shortens the catalogue name to the vendor's own phrase
        -- so the only thing that knows they are one tool is the cosine that
        matched them.  A dedup comparing spellings would leave this one on the
        screen twice, which is what the tester saw.
        """
        onet.get_hot_technologies.return_value = ["Amazon Web Services AWS software"]
        user = profile(skills=[user_skill("Amazon Web Services", "advanced")])
        client = tech_openai(user)
        client.embeddings.table.update(
            {
                "amazon web services": TECH,
                "Amazon Web Services AWS software": TECH,
            }
        )
        assert not (
            pdf.skill_aliases("Amazon Web Services")
            & pdf.skill_aliases("Amazon Web Services AWS software")
        ), "if these ever alias, this test is no longer about the cosine"

        fit = deep_fit(user, CODE, onet, client)

        assert fit.matched_skills == ["Amazon Web Services"]
        assert fit.tech_stack == []

    def test_a_hot_tech_in_the_gap_list_is_not_repeated_in_the_tech_list(
        self, world, onet
    ) -> None:
        """The gap list is the more specific of the two, so it keeps the tool."""
        user = fitted_profile()
        client = tech_openai(user)
        # The user points one way and every role item the other, so Git -- a hot
        # technology -- comes out as a gap rather than as a match.
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

        assert "Git" in [gap.name for gap in fit.gap_skills]
        assert fit.matched_skills == ["Python"], "matched by identity, not cosine"
        assert fit.tech_stack == []

    def test_a_tool_in_neither_list_still_appears_in_onet_order(
        self, world, onet
    ) -> None:
        """The dedup removes; it does not reorder, and it is not a blanket empty."""
        user = outsider_profile()

        fit = outsider_fit(user, onet)

        assert fit.matched_skills == []
        assert fit.gap_skills == []
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

    # -- W-13: O*NET's expansion-plus-acronym names, as a person writes them --

    def test_a_tool_named_expansion_then_acronym_shows_the_acronym_alone(
        self, world, onet
    ) -> None:
        """The third browser test: "Hypertext markup language HTML" on the panel.

        Display only. The list is still O*NET's, in O*NET's order, and the
        occupation still has exactly the tools it had.
        """
        onet.get_hot_technologies.return_value = [
            "Hypertext markup language HTML",
            "Cascading style sheets CSS",
            "Oracle Java",
        ]
        fit = outsider_fit(outsider_profile(), onet)
        assert fit.tech_stack == ["HTML", "CSS", "Oracle Java"]

    def test_a_gap_named_expansion_then_acronym_shows_the_acronym_alone(
        self, world, onet
    ) -> None:
        """"Worth picking up" is the other section the tester saw them in."""
        ps._EMBED_CACHE["bookkeeping"] = unit(1, 0)
        ps._EMBED_CACHE["Border Gateway Protocol BGP"] = unit(0, 1)
        ps._EMBED_CACHE["Extensible markup language XML"] = unit(0, 1)
        data = pdf._OccupationData(
            hot_tech=["Border Gateway Protocol BGP", "Extensible markup language XML"]
        )
        gaps = pdf._gap_skills(
            [user_skill("Bookkeeping", "advanced")], pdf._role_items_for(data)
        )
        assert [gap.name for gap in gaps] == [
            "Border Gateway Protocol BGP",
            "Extensible markup language XML",
        ], "the matching still runs on O*NET's own spelling"
        assert [pdf._display_name(gap.name) for gap in gaps] == ["BGP", "XML"]

    def test_the_rename_does_not_break_the_dedup_it_runs_after(
        self, world, onet
    ) -> None:
        """W-12's dedup compares role names against role names.

        It has to see O*NET's spelling or it cannot tell that the tool the user
        matched and the tool in the hot list are the same tool -- so the rename
        is applied to what comes OUT of it and never to what goes in.
        """
        onet.get_hot_technologies.return_value = [
            "Structured query language SQL",
            "Hypertext markup language HTML",
        ]
        user = profile(skills=[user_skill("SQL", "advanced")])
        onet.search_occupations.side_effect = None
        onet.search_occupations.return_value = []

        fit = deep_fit(user, CODE, onet, None)

        assert fit.matched_skills == ["SQL"], "the user's own name, untouched"
        assert fit.tech_stack == ["HTML"], "SQL deduped out, HTML renamed"

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
        """The score needs both centroids. The matched list does not.

        F-8 box 5 separated the two: returning `[]` alongside the honest 0.0
        would tell a user whose embedding provider blinked that this role uses
        none of their skills, which is a different and false claim.
        """
        assert pdf._compute_centroid_score(
            [user_skill("Python")], [("Python", 90.0)]
        ) == (0.0, ["Python"])

    def test_the_matched_list_needs_no_embeddings_at_all(self) -> None:
        assert pdf._find_matched_skills(
            [user_skill("SQL")], [("Structured query language SQL", 90.0)]
        ) == ["SQL"]
        assert pdf._find_matched_skills(
            [user_skill("R")], [("React", 90.0)]
        ) == []

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


# ---------------------------------------------------------------------------
# Skill-name normalisation (BUILD_PLAN F-8 box 5)
# ---------------------------------------------------------------------------


class TestSkillAliases:
    """The naming conventions O*NET actually uses, undone.

    Every example here is a real name from the corpus build's own
    `documents.jsonl` -- 176 distinct hot-technology names, mined 2026-09-16 --
    not a string invented to make a rule look good.
    """

    @pytest.mark.parametrize(
        "user_term,onet_name",
        [
            # The reported defect, verbatim.
            ("SQL", "Structured query language SQL"),
            # The same shape, 25 more times in the real vocabulary.
            ("CSS", "Cascading style sheets CSS"),
            ("XML", "Extensible markup language XML"),
            ("VBA", "Microsoft Visual Basic for Applications VBA"),
            ("MATLAB", "The MathWorks MATLAB"),
            # Vendor prefixes.
            ("Excel", "Microsoft Excel"),
            ("Photoshop", "Adobe Photoshop"),
            ("Kafka", "Apache Kafka"),
            ("iOS", "Apple iOS"),
            # The " software" suffix, and a name that needs three rules at once.
            ("SAP", "SAP software"),
            ("AWS", "Amazon Web Services AWS software"),
            # Parentheticals. Zero of the 176 hot-technology names use them, but
            # O*NET's wider vocabulary does and the rule is free.
            ("XML", "Extensible markup language (XML)"),
        ],
    )
    def test_the_same_thing_said_two_ways(self, user_term, onet_name) -> None:
        assert pdf.skill_aliases(user_term) & pdf.skill_aliases(onet_name), (
            "%r and %r did not alias to each other" % (user_term, onet_name)
        )

    @pytest.mark.parametrize(
        "left,right",
        [
            # The false-positive guard the brief names. Nothing shortens a
            # single bare token, so these can never meet.
            ("R", "React"),
            ("R", "Ruby"),
            ("C", "C++"),
            # A genuinely different product that merely ends the same way.
            ("SQL", "MySQL"),
            ("SQL", "PostgreSQL"),
            ("SQL", "Oracle PL/SQL"),
            # The reason rule A is restricted to ALL-CAPS tokens. O*NET's ~35
            # generic skills are title-cased two-word English phrases, exactly
            # like its two-word product names, so a "last token" rule would
            # credit a user who listed "Design Thinking" with "Critical
            # Thinking". Shape alone cannot separate those two vocabularies.
            ("Design Thinking", "Critical Thinking"),
            ("Systems Analysis", "Data Analysis"),
            ("Active Listening", "Passive Listening"),
            # And the reason the vendor threshold is 3 and not 2: at 2, "Red"
            # is a vendor, and "Red Hat Enterprise Linux" becomes an alias for
            # "Hat Enterprise Linux".
            ("Linux", "Red Hat Enterprise Linux"),
        ],
    )
    def test_things_that_must_not_be_confused(self, left, right) -> None:
        assert not (pdf.skill_aliases(left) & pdf.skill_aliases(right)), (
            "%r was aliased onto %r" % (left, right)
        )

    def test_a_name_always_aliases_to_itself(self) -> None:
        for name in ("Python", "R", "Structured query language SQL", "Excel"):
            assert name.casefold() in pdf.skill_aliases(name)

    def test_empty_and_punctuation_only_names_alias_to_nothing(self) -> None:
        for name in ("", "   ", "...", " , "):
            assert pdf.skill_aliases(name) == frozenset()

    def test_case_and_spacing_do_not_matter(self) -> None:
        assert pdf.skill_aliases("  microsoft   EXCEL ") & pdf.skill_aliases("Excel")


class TestTheGapListDoesNotNameWhatTheUserHas:
    """F-8 box 5, at the level the user met it.

    F-5 shipped this defect knowingly and the frontend renders it rather than
    filtering it, so that the only people who could report it could see it. This
    is the backend fix, and it is identity rather than a tuned threshold --
    `_EMBED_THRESHOLD` is unchanged, because there is no Tier-2 harness and a
    threshold moved by feel is a number nothing can falsify.
    """

    @staticmethod
    def _onet_with(hot_tech, skills=()):
        client = MagicMock(spec=OnetClient)
        client.get_skills_profile.return_value = list(skills)
        client.get_hot_technologies.return_value = list(hot_tech)
        client.get_work_activities.return_value = []
        client.get_tasks.return_value = []
        client.search_occupations.side_effect = AssertionError("unexpected search")
        client.get_job_zone.side_effect = AssertionError("unexpected get_job_zone")
        return client

    @staticmethod
    def _openai(user, role_names):
        """Every role item embeds FAR from the user's skill, deliberately.

        The cosine is then incapable of matching anything, so whatever the panel
        reports as matched is the alias rule's doing and nothing else. A double
        that put them close would prove the embedder, not the fix.
        """
        client = tech_openai(user)
        client.embeddings.table.update({name: TRADE for name in role_names})
        for us in user.skills:
            client.embeddings.table[us.name.lower()] = TECH
        return client

    def test_a_user_with_sql_is_not_told_sql_is_a_gap(self, world) -> None:
        """The exact sentence from F-5's routing note, as a test."""
        role = ["Structured query language SQL", "Snowflake"]
        onet = self._onet_with(role)
        user = profile(skills=[user_skill("SQL", "advanced")])

        fit = deep_fit(user, CODE, onet, self._openai(user, role))

        gaps = [gap.name for gap in fit.gap_skills]
        assert "Structured query language SQL" not in gaps, (
            "the panel still names a skill the user listed: %s" % gaps
        )
        assert "Snowflake" in gaps, "a real gap was swept up with the fix"
        assert "SQL" in fit.matched_skills

    def test_a_user_with_excel_is_not_told_microsoft_excel_is_a_gap(
        self, world
    ) -> None:
        role = ["Microsoft Excel", "Tableau"]
        onet = self._onet_with(role)
        user = profile(skills=[user_skill("Excel", "intermediate")])

        fit = deep_fit(user, CODE, onet, self._openai(user, role))

        assert "Microsoft Excel" not in [gap.name for gap in fit.gap_skills]
        assert "Tableau" in [gap.name for gap in fit.gap_skills]
        assert "Excel" in fit.matched_skills

    def test_r_does_not_match_react(self, world) -> None:
        """The guard, end to end and not only on the alias sets.

        A user who knows R is a statistician, not a frontend developer. If the
        normaliser ever starts shortening single tokens, this is where it shows.
        """
        role = ["React", "Node.js"]
        onet = self._onet_with(role)
        user = profile(skills=[user_skill("R", "advanced")])

        fit = deep_fit(user, CODE, onet, self._openai(user, role))

        assert "React" in [gap.name for gap in fit.gap_skills]
        assert fit.matched_skills == []

    def test_identity_works_with_no_embeddings_at_all(self, world) -> None:
        """An OpenAI outage degrades to exact matching, not to silence.

        The alias check runs before the cache is consulted, so the panel still
        knows the user has SQL when nothing can be embedded. That is strictly
        better than the pre-F-8 behaviour, where an outage meant no matches and
        no measurable gaps.

        No title on this profile: without an embedder, anchor resolution falls
        back to O*NET's keyword search, and the `onet` double raises on it. That
        fallback is F-4's and is not what this test is about.
        """
        onet = self._onet_with(["Structured query language SQL"])
        user = profile(current_title=None, skills=[user_skill("SQL", "advanced")])

        fit = deep_fit(user, CODE, onet, None)

        assert fit.matched_skills == ["SQL"]
        assert [gap.name for gap in fit.gap_skills] == []

    def test_the_fit_score_is_not_what_changed(self, world) -> None:
        """Recorded as an asymmetry, deliberately, rather than fixed blind.

        `_role_coverage_score` and `_compute_centroid_score` produce the fit
        NUMBER and still use the cosine alone. So a user can be told SQL is
        matched while the coverage term does not count it. Closing that gap
        changes a score, and there is no Tier-2 harness to say whether the
        change is an improvement -- which is the same reason the threshold was
        not tuned. This test exists so the asymmetry is a decision on the record
        and not a thing somebody discovers.
        """
        role_items = [("Structured query language SQL", 90.0)]
        skills = [user_skill("SQL", "advanced")]

        assert pdf._find_matched_skills(skills, role_items) == ["SQL"]
        assert pdf._role_coverage_score(skills, role_items) == 0.0


class TestDisplayNames:
    """W-13: O*NET writes "Hypertext markup language HTML"; the panel says HTML.

    The five the third browser test found, and three names that are not this
    pattern and must survive exactly as the catalogue wrote them.
    """

    @pytest.mark.parametrize(
        "catalogued, shown",
        [
            ("Hypertext markup language HTML", "HTML"),
            ("Extensible markup language XML", "XML"),
            ("Cascading style sheets CSS", "CSS"),
            ("Border Gateway Protocol BGP", "BGP"),
            ("Amazon Web Services AWS software", "AWS"),
        ],
    )
    def test_the_acronym_stands_alone(self, catalogued, shown) -> None:
        assert pdf._display_name(catalogued) == shown

    @pytest.mark.parametrize(
        "untouched",
        [
            "Oracle Java",
            "Microsoft Azure software",
            "Node.js",
            # The initials do not spell it -- "EC2" is not letters-only anyway,
            # and no reading of the words before it produces the 2.
            "Amazon Elastic Compute Cloud EC2",
            # Three capitals at the end that the preceding words do not spell.
            "Adobe Systems Adobe AIR",
            # Nothing before the acronym to collapse.
            "IBM",
            # The acronym is not at the end.
            "Microsoft SQL Server",
        ],
    )
    def test_anything_else_is_left_exactly_as_onet_wrote_it(self, untouched) -> None:
        assert pdf._display_name(untouched) == untouched

    def test_the_initials_rule_alone_would_miss_html_and_xml(self) -> None:
        """Why the check is not "first letters of the words".

        "Hypertext markup language" gives H-M-L and "Extensible markup
        language" gives E-M-L. Both are the pattern; neither passes an initials
        test. This pins the reason the rule is written the way it is.
        """
        assert "".join(w[0] for w in "Hypertext markup language".split()).upper() == "HML"
        assert "".join(w[0] for w in "Extensible markup language".split()).upper() == "EML"
        assert pdf._display_name("Hypertext markup language HTML") == "HTML"
        assert pdf._display_name("Extensible markup language XML") == "XML"

    def test_every_word_must_contribute_a_letter(self) -> None:
        """The tightening that keeps the subsequence rule from being a sieve.

        A word may carry more than one letter -- it has to, or "Hypertext" could
        not supply the H and the T -- but no word may carry none. That is what
        rules out an expansion with more words than the acronym has letters, and
        what leaves "Adobe Systems Adobe AIR" alone: "systems" has no I.
        """
        assert pdf._spells_out(["Cascading", "style", "sheets"], "CSS")
        assert pdf._spells_out(["Hypertext", "markup", "language"], "HTML")
        assert not pdf._spells_out(["Adobe", "Systems", "Adobe"], "AIR")
        assert not pdf._spells_out(
            ["Cascading", "style", "sheets", "level", "two"], "CSS"
        ), "five words cannot each contribute to a three-letter acronym"


@pytest.mark.skipif(
    not os.environ.get("SOLVERAH_CORPUS_PATH"),
    reason="SOLVERAH_CORPUS_PATH is unset; CI has no corpus artifact",
)
class TestTheConventionsAreTheCorpusOwn:
    """The patterns are derived from the real vocabulary and stay derived.

    `_VENDOR_PREFIXES` is the one part of box 5 that could rot into a hand list,
    so it is re-derived here from the artifact the builder wrote and compared.
    """

    @staticmethod
    def _technology_names() -> set[str]:
        import json
        from pathlib import Path

        root = Path(os.environ["SOLVERAH_CORPUS_PATH"])
        docs = sorted(root.glob("*.documents.jsonl"))
        if not docs:
            pytest.skip("the artifact directory has no documents.jsonl")
        names: set[str] = set()
        with docs[-1].open(encoding="utf-8") as fh:
            for line in fh:
                names.update(
                    str(n) for n in (json.loads(line).get("hot_technologies") or [])
                )
        return names

    def test_the_vendor_prefixes_are_what_the_corpus_says_they_are(self) -> None:
        from collections import defaultdict

        groups: defaultdict[str, set[str]] = defaultdict(set)
        for name in self._technology_names():
            core = pdf._SOFTWARE_SUFFIX.sub("", name).strip()
            tokens = core.split()
            if len(tokens) >= 2:
                groups[tokens[0].casefold()].add(core)

        derived = {
            token
            for token, group in groups.items()
            if len(group) >= pdf._VENDOR_MIN_DISTINCT_NAMES
        }

        assert derived == set(pdf._VENDOR_PREFIXES), (
            "the vendor set no longer matches the corpus: missing %s, extra %s"
            % (sorted(derived - set(pdf._VENDOR_PREFIXES)),
               sorted(set(pdf._VENDOR_PREFIXES) - derived))
        )

    def test_the_acronym_rule_only_ever_fires_on_real_acronyms(self) -> None:
        """Every name the rule shortens, checked against the whole vocabulary.

        The risk is a rule that looks right on twelve examples and mangles the
        thirteenth. Measured: it fires on 26 of 176 names, and every alias it
        produces is a term somebody would actually type.
        """
        fired = {}
        for name in self._technology_names():
            aliases = pdf.skill_aliases(name)
            short = {a for a in aliases if a != name.casefold() and " " not in a}
            if short:
                fired[name] = short

        assert fired, "the rules fired on nothing at all"
        for name, aliases in fired.items():
            for alias in aliases:
                assert len(alias) >= 2, "%r produced the alias %r" % (name, alias)
                assert alias in name.casefold(), (
                    "%r produced %r, which is not a substring of it" % (name, alias)
                )

    def test_no_two_distinct_technologies_collide(self) -> None:
        """The false-positive guard, over the entire real vocabulary.

        Two different O*NET technologies must never alias onto each other --
        that is what would let the panel credit a user with something they do
        not have. 176 names, every pair.
        """
        names = sorted(self._technology_names())
        alias_sets = {name: pdf.skill_aliases(name) for name in names}
        collisions = []
        for i, left in enumerate(names):
            for right in names[i + 1:]:
                shared = alias_sets[left] & alias_sets[right]
                if shared:
                    collisions.append((left, right, sorted(shared)))

        assert not collisions, "distinct technologies aliased together: %s" % collisions
