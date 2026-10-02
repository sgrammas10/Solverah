"""Record the exact bytes the identity and profile endpoints return.

Phase 2c moves the user row: `user` becomes `users`, `email_confirmed` becomes a
nullable `email_confirmed_at`, `password` becomes `password_hash`, the primary key
becomes an identity column, and a `public_id` appears alongside the integer `id`.
None of that is allowed to reach the wire. This script and its pair,
`verify_contract.py`, are the evidence.

    # on the commit before the change
    python -m Scripts.capture_contract

    # after it
    python -m Scripts.verify_contract

Both **destroy every object** in the database they run against -- the same
`DROP SCHEMA public CASCADE` a fresh start requires -- so the guard
`tests/conftest.py` uses is imported and applied here rather than re-implemented,
because a second copy of a safety check is a copy that drifts. Left alone they
use `solverah_contract`, which is theirs alone; `DATABASE_URL` overrides it, and
pointing that at the database another tool is using is the one way to get the
2026-08-27 failure back.

**Why raw text and not parsed JSON.** `json.loads(a) == json.loads(b)` is blind to
key order, to `1` versus `1.0`, and to the whitespace a serializer emits. "Byte-identical"
has to mean bytes, so the comparison is on the response body as a string.

**What is masked, and why that is safe.** Two classes of value change on every run
and would drown the diff: the CSRF token, and timestamps. Each is replaced with a
sentinel (`<CSRF>`, `<TS>`) rather than deleted. Replacement rather than deletion is
what keeps the mask honest: a boolean `true` that regressed into a timestamp string
still diffs, because `true` and `"<TS>"` are not the same text. Nothing else is
masked -- `id` in particular is recorded verbatim, since "the id on the wire is
still the integer" is one of the things being proved.

The scenario deliberately includes the failure paths. `403 Email not confirmed`
exercises the `email_confirmed_at IS NOT NULL` derivation from the side where it
returns false, which the happy path never reaches.

**Extended for Phase 2d (assessment storage unification).** The 2c scenario never
touched an assessment, so every `session` capture in it had `wpl_completed`,
`wpll_completed` and `wp_v2_completed` false -- three booleans that are trivially
byte-identical when nothing ever sets them. 2d moves all five instruments onto
`assessment_forms` + `assessment_submissions`, so the scenario now submits all
five, re-reads the three that store a result, claims an anonymous WPLL session
onto the account (the path that actually writes the `wpll_*` state), and captures
the catalogue and the session with the flags **true**. `export` and
`me-profile-after-write` are captured after all of that rather than before, so the
`legacy_quiz` block and the two profile-document result keys are in the diff too.

**Extended for Phase 3 (async and caching).** Two reads gain a Redis cache --
`GET /companies/{id}` and `GET /me/dashboard` -- and a cached response is served
without the handler running, so a cache that reshapes a payload is a defect only
a byte comparison can see. Company detail was not in the 2c/2d scenario at all,
which meant the diff protected exactly nothing about it, so the scenario now
seeds a company and reads it. Each of the two cached routes is read **twice in a
row**: the second read is the one that can come from Redis, and it has to be the
same bytes as the first. With no `REDIS_URL` set the cache is inert and the pair
proves the handler is deterministic instead -- which is why the verify step is
worth running once each way.

**Extended for Phase 3c (the first deliberate contract change).** Every prior
capture proved zero diff; this one records a surface that changed on purpose,
and A21 (docs/ARCHITECTURE.md) is the ledger of exactly what moved. The three
provider-scored instruments no longer submit synchronously: the old submit
steps are kept as captures of their 410 problem documents -- the refusal and
its ``replaced_by`` pointer are contract now -- and the scoring itself is
driven the way the SPA drives it, ``POST /assessments/{kind}/scoring-jobs``
plus a poll. Under this script's eager execution the job runs inline, so the
202 already reads ``succeeded`` and one poll returns the result; both bodies
are captured. ``GET /me/path-suggestions`` is captured on a cache miss, where
computing nothing and answering 404 with ``start_job_url`` is the new promise.
Job handles are random per run and masked as ``<JID>`` -- in bodies and in the
recorded poll *path*, which is the first path here to embed a per-run value.

**Extended for S3 (database-backed refresh tokens).**  The second deliberate
contract change in the project's history, and A24 (docs/ARCHITECTURE.md) is the
ledger of what moved.  One of the sixty steps above changed on its own --
``login`` now sets a third cookie -- and eleven steps are appended for the
surface that did not exist: the rotation, the concurrency grace answer, reuse
detection, the two halves of the CSRF guard on the refresh POST, and a logout
that revokes.

Two of those records exist to be read as a *pair*, in the way A23's
anti-enumeration records do.  ``refresh`` and ``refresh-replayed-in-grace`` are
both ``200``, and the whole property is that their ``cookies_set`` differ: the
first rotates and hands back a new refresh cookie, the second is the second tab
in a stampede and must NOT, because the successor is already in the shared
cookie jar.  A future diff that made them the same is a design regression that
no unit test phrases as a wire fact.

**Re-baselined for the mm-q11 keying fix (2026-09-10).** The third deliberate
contract change, and A25 (docs/ARCHITECTURE.md) is the ledger of what moved.
No step was added or removed -- the fix corrects a stored value, not a route --
but `manager_match_result` is merged into the profile document on every read,
so the new `relationship` score and the new `scoring_key` field surface in six
of the 71 steps, not only the two most obviously named: `poll-manager-match-job`
and `result-manager-match` carry it directly, and `me-profile-after-write`,
`export`, `login-for-refresh` and `login-for-logout` carry it embedded in the
profile document. Verified before the recapture, on the standing baseline:
6 differences, all six the same two-field substitution and nothing else.

**Re-baselined for BUILD_PLAN D-7b (2026-09-11).** The fourth deliberate contract
change, and A26 (docs/ARCHITECTURE.md) is the ledger of what moved. No step was
added or removed and no route changed -- `export_account_data` grew three new
payload keys (`resume_parse_corrections`, `focus_type_answers`,
`manager_match_answers`), so exactly one of the (by then 82) steps was affected:
`export`. Verified before the recapture, on the standing baseline: 1 difference,
and the diff is purely additive -- three new keys present with real content this
scenario already produces (it submits FocusType and ManagerMatch before reaching
`export`), every previously-existing key byte-identical. The scored `result` for
both instruments is NOT part of that diff: it already reached the wire before
this chunk, nested inside the `profile` key the mm-q11 paragraph above describes
-- this chunk closes the narrower gap of the raw submitted `answers`, which
reached neither `export` nor `profile` before now.

**Re-baselined for BUILD_PLAN B-4 (2026-09-14).** The fifth deliberate contract
change. No route changed and no step was removed -- `get_situation_report`'s
`complete` state grew one additive key, `events_since_report` (a list of
`{'type', 'date'}`, never a `note`), so `situation-report-complete` above now
carries an empty list on top of its previous keys, and every other step is
untouched. Verified before the recapture, on the standing baseline: 1
difference, purely that addition. One step is new -- `pulse-event` above
already logs a `new_manager` event for EMAIL *after* `submit-environment-report`,
so `situation-report-after-pulse-event` is what captures `events_since_report`
non-empty for the first time, appended at the very end so the 89 records above
it keep their positions.

**Extended for BUILD_PLAN B-5 (2026-09-14): condition experiments.** A new
surface, not a change to any existing one -- every record above keeps its
position, exactly as the Pulse block appended after the Situation Report
block. `EMAIL` already has everything this needs: a completed `core` sitting
and a submitted environment report, both from the Situation Report block
above. `post-experiment-malformed` pins the business-rule 422 (a dimension
that names no real `change_in_place` cell) -- schema-level 422s are already
covered by `enforce=True`, the same reasoning every other `-malformed` step in
this script gives for capturing only the other failure mode.
`post-experiment-conflict` captures the 409 a second `POST` gets while the
first is still active -- the methodological one-active-at-a-time rule
(`model.Experiment`'s docstring) made visible on the wire. `readout` reads
`not_enough_data` throughout this block: EMAIL has never completed a Pulse
check-in in this scenario, and inventing one only to backdate it would cost a
real check-in's worth of Pulse-block state for a readout word this script does
not need to prove -- `tests/test_experiment_api.py` proves every other verdict
word against real, controlled check-in timestamps instead.

**Extended for BUILD_PLAN F-5 (2026-09-16): the Tier-2 deep fit.** A new surface,
not a change to any existing one -- every record above keeps its position, exactly
as the experiments block appended after the Situation Report <-> Pulse block.
Verified before the recapture, on the standing baseline: **0 differences across 97
responses**.

Two steps, and neither of them reaches a provider, which is the point. This
environment has no corpus artifact (`SOLVERAH_CORPUS_PATH` is unset here exactly
as it is on the CI runner), so the two answers a deep fit can give without one
are the two worth pinning: `path-fit-malformed-code` is the permanent `404
invalid_onet_code`, and `path-fit-corpus-unavailable` is the transient `503
corpus_unavailable`. That they differ is the property -- the code is validated
*before* the corpus is loaded, so an S3 outage cannot turn a client bug into
something the client retries forever. A future diff that made both 503 would be
that ordering silently reversed, which no unit test phrases as a wire fact.

`ONET_API_KEY` is set below for the same reason `SOLVERAH_FORM_TOKEN_SECRET` is:
`OnetClient()` refuses to construct without one, and both steps would otherwise
be 500s on both sides of the diff -- identical bytes proving nothing. No request
is made with it; both steps refuse before the client is used.

**Re-baselined for the real dashboard feed (2026-09-28).** A deliberate change,
and A28 (docs/ARCHITECTURE.md) is the ledger. `dashboard_data` stopped returning
static placeholder `recentActivity`/`recommendations` and now derives both from
the user's own rows. No step added, removed or reordered. Verified before the
recapture, on the standing baseline: 2 differences, `dashboard` and
`dashboard-cached`, both body-only; every other step byte-identical.

**Extended for BUILD_PLAN W-4 (2026-09-21): the "what should change" panel.** A
new surface, not a change to any existing one -- every record above keeps its
position, exactly as the F-6 block appended after the F-5 one. Verified before
the recapture, on the standing baseline: **0 differences across 103 responses.**

Eight steps, and this is the first block in the file that runs in **two**
environments. Everything above it is captured with no corpus artifact at all --
`SOLVERAH_CORPUS_PATH` is unset here exactly as it is on the CI runner -- so the
first two steps pin the degrade: `GET` and `PUT` must BOTH answer `503
corpus_unavailable`, because the panel's questions are the user's own
occupation's tasks and neither method can decide what this user was asked
without resolving that occupation. A diff where the PUT started answering 200 or
422 while the GET still answered 503 would mean a write had found some other way
to decide what to store, which is the one failure this table's keying discipline
exists to prevent.

`_install_panel_corpus` then copies the committed 26-row test fixture into a
scratch directory, writes the two sidecars beside it, and stubs the embedder --
so the remaining steps pin the panel itself. What is captured there is mostly
what is ABSENT: `tasks` carries plain-words labels and never the O*NET statements
they were written from, because the statement is what the scorer embeds (design
doc 8.7) and a client that could read one might send it back as a key. The 422
is the business-rule one (a key this occupation does not offer, which is what a
client holding a panel across a job change sends) and the clear that follows it
is what makes "nothing was written" visible on the wire: it puts back a panel
with one answer on it rather than two.

The last two steps are a third account with no profile, on its own client. Its
registration and login are deliberately NOT captured -- those three responses are
already pinned for EMAIL at the top of this scenario.

**Extended for W-19 (2026-09-29): the path-suggestion job pair.** A new surface,
not a change to any existing one -- every record above keeps its position.
Verified after the recapture: **0 differences across 113 responses**, and the
baseline diff is the two appended records and nothing else. `POST
/me/path-suggestion-jobs` had no step, so DB ledger Package I's defect -- the
eager-mode 202 reading the job's terminal status instead of `queued` -- went
unseen here. `_remove_panel_corpus` first puts the environment back to no
corpus, so the job reads everything, ends its read transaction (the rollback
that expired the route's row), and fails on the corpus with the typed
`corpus_unavailable`: deterministic, and the poll records it. Proven to catch
the defect: with `detach_before_run` taken off `create_path_suggestions`, verify
reports exactly one difference, `queue-path-suggestions`, `queued` -> `failed`.

**Not captured, and the reason is the environment rather than the chunk:**
`reasons` on a suggestion card. It is on `PathSuggestion` in `docs/openapi.json`,
but reaching a non-empty `suggestions` payload here needs a scoring run and the
narrator on top of the corpus, and `GET /me/path-suggestions` is captured on a
cache miss by design. It is pinned in `tests/test_path_wants_api.py` and
`tests/test_path_scoring.py` instead.

**The LLM is stubbed, and the prompt builders with it.** Three instruments call a
provider; a fixture that depended on one could not produce stable bytes, and the
narrative text is the whole payload for two of them. `_chat_json` is replaced by a
lookup keyed off a marker the stubbed prompt builders emit, so Work Pulse and
ManagerMatch -- which share `OPENAI_WP_MODEL` -- stay distinguishable. The
builders are still *called* with whatever the handler passes them, so a handler
that stopped being able to read its inputs still fails here; what those inputs
contain is not on the wire and is asserted in `tests/test_assessment_storage.py`
instead.

**Re-baselined for the environment report's `industry` item (2026-10-01).** A
deliberate change, and A29 (docs/ARCHITECTURE.md) is the ledger. The
`submit-environment-report` step now sends `"industry": "tech"`, so the new field
is pinned with a real value rather than its null default. No step was added,
removed or reordered. Verified before the recapture, on the standing baseline:
1 difference, `submit-environment-report`, body only (`"industry":"tech"` added,
`version` moved from `env-v1-2026-09-10` to `env-v2-2026-10-01`); every other
step byte-identical. `export` does not move because it runs before EMAIL has
submitted an environment report, so its `environment_reports` list is empty.
After the recapture: 0 differences across 113.

**Extended and re-baselined for the past-job environment report (2026-10-01).** A
deliberate change, and A30 (docs/ARCHITECTURE.md) is the ledger. `POST
/me/environment-report` takes an optional `subject` ("current" by default, or
"past") and echoes it; `GET /me/situation-report` carries `past_job_report_filed`
in every state. Verified before the recapture, on the standing baseline: 4
differences, all body-only and all additive -- `submit-environment-report`
(`"subject":"current"` added) and the three situation-report reads
(`situation-report-needs-environment-report`, `situation-report-complete`,
`situation-report-after-pulse-event`: `"past_job_report_filed":false` added);
every other step byte-identical. Three steps are appended at the very end so every
record above keeps its position: `submit-past-environment-report` (EMAIL is
employed and already has a current report), `situation-report-after-past-report`
-- which must equal `situation-report-after-pulse-event` byte for byte except
that the flag reads `true`, because a past report never reaches the report itself
-- and `submit-past-environment-report-limit`, the 409 `past_report_limit` a
second past report gets. `export` still does not move: it runs before any
environment report exists.

**Re-baselined for the 2026-10-02 bug-fix wave.** A deliberate change, and A31
(docs/ARCHITECTURE.md) is the ledger. `GET /me/situation-report`'s `complete`
state gained one additive key, `career_status_changed` (bool): it is true when
the caller's live career status reads in a different tense from the snapshot the
report was filed under. No step was added, removed or reordered. Verified twice
before the recapture on the standing baseline, before and after the wave's
last follow-ups landed: 3 differences, all body-only, and each body equals its
baseline byte for byte once `"career_status_changed":false,` is removed --
`situation-report-complete`, `situation-report-after-pulse-event` and
`situation-report-after-past-report`. EMAIL is `employed` live and in the
snapshot, so the flag reads `false` in all three. The rest of the wave does not
reach this scenario. There is no agent or quiz-insight step, so `LlmErrorResponse`
and the agent's 422 -> 503 for an unavailable model are not pinned here. The
dashboard's recommendation backstop moved from 3 to 6, but this scenario never
has more than three, so `dashboard` and `dashboard-cached` stay byte-identical.
After the recapture: 0 differences across 116.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "docs" / "contract_baseline.json"

EMAIL = "contract-primary@example.test"
UNCONFIRMED_EMAIL = "contract-unconfirmed@example.test"
#: An address no scenario step ever registers.  It exists so the two
#: anti-enumeration endpoints can be asked about a stranger and about a real
#: user in the same run, and the answers compared.
ABSENT_EMAIL = "contract-absent@example.test"
#: A third account with no profile at all, so the wants panel has a subject with
#: no current job.  Registered at the very end of the scenario and on its own
#: client, so EMAIL's cookie jar and every record above are untouched.
NO_JOB_EMAIL = "contract-nojob@example.test"
PASSWORD = "Strongpass1!"

#: Same literal every person-side test uses. `respondent_id_for_user` has no
#: default by design (D-05) and this script runs with SOLVERAH_IGNORE_DOTENV=1,
#: so without it `/assessments/core/form` is a 500 on both sides of the diff --
#: identical bytes proving nothing.
FORM_TOKEN_SECRET = "test-secret-not-a-real-one"

#: This script's own database -- not the suite's `solverah_test`, and not the
#: `solverah` that `make dev` uses.
#:
#: `_reset_schema` below runs DROP SCHEMA public CASCADE. Until 2026-08-27 this
#: script inherited its URL from `tests/conftest.py`'s setdefault, which was the
#: dev database, which `make test-pg` also used: running a capture while a suite
#: was in flight dropped the schema out from under it, and vice versa. What that
#: produced was 132 collection errors naming `user_role` -- the first enum
#: create_all emits, so the first object two racing processes collide on, and
#: nothing at all to do with the phase it was blamed on for hours.
#:
#: setdefault, not a hard assignment: capturing against a scratch database is a
#: reasonable thing to want, and DATABASE_URL is how you ask for it. The guard
#: borrowed from conftest still refuses anything non-local either way.
#:
#: Created by infra/docker/initdb/02-lane-databases.sql on the stack's first
#: start, on port 5433 -- see infra/docker/compose.yml for why not 5432.
CONTRACT_DATABASE_URL = "postgresql://solverah:solverah@localhost:5433/solverah_contract"

WPLL_ANSWERS = [
    {"question_id": "wpll-q%d" % i, "option_id": "wpll-q%d-c" % i} for i in range(1, 6)
]
WP_ANSWERS = [
    {"question_id": "wp-q%d" % i, "option_id": "wp-q%d-b" % i} for i in range(1, 13)
]
MM_ANSWERS = [{"question_id": "mm-q%d" % i, "choice": "a"} for i in range(1, 16)]
MP_ANSWERS = [{"question_id": "mp-q%d" % i, "choice": "a"} for i in range(1, 17)]

FOCUS_TYPE_PAYLOAD = {
    "scene_1": ["big_project", "planning_doc", "urgent_client", "teammate_feedback",
                "emails", "admin_tasks"],
    "scene_2": {
        "now": ["email_client_important", "slack_mentioned"],
        "later": ["slack_teammate_question"],
        "ignore": ["email_newsletter", "calendar_meeting_invite", "task_new_ticket",
                   "task_planning_doc", "slack_team_channel", "email_system_report",
                   "calendar_team_lunch"],
    },
    "scene_3": {"deep_solo": 2.5, "planning": 0.5, "social": 0.5, "breaks": 0.25,
                "exploring": 0.25},
    "scene_4": {
        "now": ["deep_research"],
        "tomorrow": ["reply_teammate", "write_report_draft", "update_task_tracker",
                     "quick_call_unblock", "send_followup_email", "review_others_work",
                     "sketch_tomorrow_plan"],
        "avg_decision_time_ms": 500,
    },
    "scene_5": ["deep_work", "wind_down"],
}

#: Canned provider replies, keyed by the marker the stubbed prompt builders emit.
#: Work Pulse and ManagerMatch both run on `OPENAI_WP_MODEL`, so the model
#: environment variable cannot tell them apart and the marker is what does.
_LLM_REPLIES = {
    "WP": {
        "narrative": "You do your best work in long uninterrupted stretches.",
        "emerging_signals": ["depth over breadth", "low tolerance for context switching"],
        "archetype": "The Deep Worker",
        "archetype_description": "Sustained focus is where your output comes from.",
    },
    "MM": {
        "narrative": "You want a manager who sets direction and then gets out of the way.",
        "what_to_look_for": ["clear written goals", "few standing meetings"],
        "red_flags": ["decisions that only happen in the room"],
        "archetype_description": "Autonomy with an explicit target.",
    },
    "WPLL": {"insight_text": "You are drawn to work with a visible finish line."},
}

# Order matters: CSRF tokens hold no timestamp, but masking timestamps first would
# not touch them either. Doing CSRF first keeps each pattern responsible for one thing.
_CSRF_VALUE = re.compile(r'("csrf_?[Tt]oken"\s*:\s*)"[^"]*"')
_ISO_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
#: A sitting's id is random per run and cannot be compared literally. The
#: character class is the assertion: 32 lowercase hex, no dashes, which is what
#: `uuid4().hex` produced before 2d and what `assessment_submissions.public_id`
#: (a uuidv7 -- same 128 bits, same `.hex`) produces after it. If the format ever
#: moves -- a dashed UUID, a bare integer, a longer token -- this pattern stops
#: matching and the raw value lands in the diff as a difference. That is the
#: whole reason the masks replace rather than delete.
_SUBMISSION_ID = re.compile(r'("submission_id"\s*:\s*)"[0-9a-f]{32}"')
#: Every RFC 7807 problem body carries the request id that produced it, so it
#: joins to the logs. It is new to this baseline only because the 2c scenario
#: never reached a route that answers with one -- the errors it captured are the
#: legacy `{"error": "..."}` shape, which carries no id.
_REQUEST_ID = re.compile(r'("request_id"\s*:\s*)"[0-9a-f]{32}"')
#: A scoring-job handle (Phase 3c): `uuid.hex`, same 32-lowercase-hex format as
#: the submission id, appearing as `job_id` and as the tail of `status_url`.
#: The character class is the assertion, exactly as `_SUBMISSION_ID` documents.
_JOB_ID = re.compile(r'("job_id"\s*:\s*)"[0-9a-f]{32}"')
_STATUS_URL_ID = re.compile(r'("status_url"\s*:\s*"[^"]*/)[0-9a-f]{32}(")')


def _mask(text: str) -> str:
    """Replace the values that legitimately differ between runs."""
    text = _CSRF_VALUE.sub(r'\1"<CSRF>"', text)
    text = _SUBMISSION_ID.sub(r'\1"<SID>"', text)
    text = _REQUEST_ID.sub(r'\1"<RID>"', text)
    text = _JOB_ID.sub(r'\1"<JID>"', text)
    text = _STATUS_URL_ID.sub(r"\g<1><JID>\g<2>", text)
    return _ISO_TIMESTAMP.sub("<TS>", text)


#: The poll paths embed the handle, so the recorded `path` needs the same mask
#: the bodies get -- the first path in the scenario to carry a per-run value.
_HEX_PATH_SEGMENT = re.compile(r"/[0-9a-f]{32}(?=/|$)")


def _mask_path(path: str) -> str:
    return _HEX_PATH_SEGMENT.sub("/<JID>", path)


def _load_conftest_guard():
    """Borrow `tests/conftest.py`'s non-local-database guard.

    Imported rather than copied. This script calls `DROP SCHEMA public CASCADE`,
    which is strictly more destructive than the `db.drop_all()` that guard was
    written for, so it must not be possible for the two to disagree about which
    hosts are safe. Importing the module also applies conftest's `setdefault`
    environment, which is the same environment the suite runs under.
    """
    spec = importlib.util.spec_from_file_location(
        "_solverah_conftest", REPO_ROOT / "tests" / "conftest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # runs the guard against DATABASE_URL
    return module


def _reset_schema(db) -> None:
    """Return the database to the state a first-ever run would find.

    `db.drop_all()` only drops what the *current* metadata declares, and the two
    sides of this diff have different metadata -- Phase 2c adds two enum types and
    a trigger function that the pre-change side has never heard of. A leftover
    `user_role` type would make the second run's `create_all` fail on a name
    collision, and a leftover row would make its ids start somewhere else. The
    schema goes, and the extensions Part 4 depends on come back.
    """
    from sqlalchemy import text

    db.session.remove()
    with db.engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        for extension in ("citext", "pg_trgm", "vector"):
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS %s" % extension))
    db.create_all()


def _reset_cache() -> None:
    """Drop every cached payload, for the same reason `_reset_schema` exists.

    `_reset_schema` returns the database to a first-ever-run state, and until
    Phase 3 that was the whole of the state a run inherited. It is not any more:
    two reads are cached in Redis, and Redis is not dropped with the schema. A
    second run against the same instance would therefore be served company and
    dashboard payloads built from the *previous* run's rows -- which is a way to
    both mask a real change and invent one that is not there, and it would look
    like a flaky diff rather than a stale cache.

    Scoped to the `solverah:` prefix rather than FLUSHDB: this script is pointed
    at whatever `REDIS_URL` names, and that may be an instance holding a
    developer's rate-limit counters.

    A no-op with no Redis configured, which is how this script normally runs --
    `SOLVERAH_IGNORE_DOTENV=1` and no REDIS_URL means the cache is inert and
    there is nothing to clear. Set REDIS_URL to exercise the cached path, which
    is the run that can catch a cache reshaping a payload.
    """
    from solverah.infra import cache

    client = cache._get_client()
    if client is None:
        return
    keys = list(client.scan_iter("solverah:*"))
    if keys:
        client.delete(*keys)


def _silence_outbound_email() -> None:
    """No scenario step may depend on an SMTP server being reachable."""
    from solverah.infra import email as email_infra

    for name in dir(email_infra):
        if name.startswith("send_"):
            setattr(email_infra, name, lambda *_a, **_k: None)


def _stub_llm() -> None:
    """Make the three provider-backed instruments deterministic.

    Two things are replaced, and the split matters.

    The **prompt builders** become markers. That is what lets one `_chat_json`
    stub serve Work Pulse and ManagerMatch, which share `OPENAI_WP_MODEL` and are
    therefore indistinguishable by the argument the real function dispatches on.
    Replacing them here does *not* stop the handlers reading their inputs -- the
    call site still evaluates `intake.wpll_answers` and
    `intake.selected_statement_ids` before handing them over, so a handler that
    lost access to them still fails this script.

    `_chat_json` itself becomes a dict lookup. It is patched on the service
    module rather than on the OpenAI client because the client is constructed
    lazily inside it, and a stub at the client layer would have to imitate the
    SDK's response object to reach the same three lines.
    """
    from solverah.services import assessment_prompts, assessment_service

    assessment_prompts.build_wp_narrative_prompt = (
        lambda *_a, **_k: [{"role": "system", "content": "WP"}]
    )
    assessment_prompts.build_mm_narrative_prompt = (
        lambda *_a, **_k: [{"role": "system", "content": "MM"}]
    )
    assessment_prompts.build_wpll_insight_prompt = lambda *_a, **_k: ("WPLL", "WPLL")

    def _canned(messages, _model_env, _default_model):
        marker = messages[0]["content"] if isinstance(messages, list) else "WPLL"
        return dict(_LLM_REPLIES[marker])

    assessment_service._chat_json = _canned


#: The one company the scenario reads. Minimal on purpose: `profile_json` is
#: echoed to the client verbatim, so every key in it is a key the diff compares,
#: and the point is to detect a *changed* payload rather than to model a real
#: research profile.
CONTRACT_COMPANY = {
    "overview": {"name": "Contract Industries", "industry": "Testing"},
    "culture": {"pace": "steady"},
}


#: Where the W-4 panel block borrows a corpus from.  The committed test fixture,
#: not a new file: 26 rows of eight-dimensional synthetic vectors that
#: `tests/test_occupation_tasks.py` already loads through the real loader.
PANEL_CORPUS_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "corpus"
PANEL_CORPUS_FILES = (
    "onet_corpus_testfix.npy",
    "onet_corpus_testfix.json",
    "onet_corpus_testfix.zones.json",
)
PANEL_ANCHOR_CODE = "15-1243.00"

#: The task rows the panel offers for that code.  Written here rather than read
#: from anywhere, because the real sidecar is built by an offline LLM pass over
#: an artifact this environment does not have.  The pairing is what matters and
#: it is the real one: `task` is the formal statement the scorer would embed,
#: `label` is the plain-words prose the panel shows, and only the second reaches
#: the wire.
PANEL_TASKS = (
    (
        "Develop and document data standards, policies, and procedures.",
        "Write down how the data is meant to work",
    ),
    (
        "Set up and maintain databases to support business applications.",
        "Set up and look after the databases",
    ),
)


def _panel_task_key(index: int) -> str:
    """The wire key of one offered task row.

    Derived here the way the server derives it rather than copied as a literal:
    the key is a digest of the statement, and a literal would go stale silently
    the day the digest changed -- recording a 422 where the baseline says 200 and
    blaming the route.
    """
    from solverah.repositories import path_wants_repository

    return path_wants_repository.item_key_for_task(PANEL_TASKS[index][0])


class _FixedEmbedder:
    """An OpenAI double whose every text embeds to one corpus row.

    Anchor resolution is a dot product against the corpus, so a stub that
    returns a real row's own vector resolves to that row every time.  The
    alternative -- leaving the embedder absent -- falls back to
    `OnetClient.search_occupations`, which in this environment is a live HTTP
    request answered 403 by a placeholder key, after which the panel would record
    `no_anchor` for a reason that has nothing to do with the contract.

    Stubbed for `_stub_llm`'s reason and at the same layer as its prompt
    builders: what the provider returns is not on the wire, and a capture that
    depended on one could not produce stable bytes.
    """

    def __init__(self, vector: list) -> None:
        self.vector = vector
        self.embeddings = self

    def create(self, *, model: str, input: list):  # noqa: A002 -- the SDK's name
        from unittest.mock import MagicMock

        return MagicMock(
            data=[
                MagicMock(index=i, embedding=list(self.vector))
                for i, _ in enumerate(input)
            ]
        )


def _install_panel_corpus() -> None:
    """Give the W-4 block a corpus, both sidecars, and a fixed embedder.

    Called BETWEEN the two halves of that block, which is the whole shape of it:
    every step above this line was captured with no corpus at all -- the state
    the CI runner and this script are otherwise always in -- so the degrade
    answers are pinned first and the working panel second.  Nothing captured
    earlier can be affected, because nothing runs after.

    The artifact and its two sidecars are written into a scratch directory rather
    than beside the committed fixture: this script must not leave files in the
    repository, and a sidecar left behind would change what
    `tests/test_occupation_tasks.py` loads.
    """
    import tempfile

    from backend.services import (
        occupation_conditions,
        occupation_retrieval,
        occupation_tasks,
    )
    from backend.services.occupation_conditions import ConditionsTable
    from backend.services.occupation_tasks import OccupationTask, TasksTable
    from solverah.infra import llm

    scratch = Path(tempfile.mkdtemp(prefix="solverah-contract-corpus-"))
    for name in PANEL_CORPUS_FILES:
        (scratch / name).write_bytes((PANEL_CORPUS_FIXTURE / name).read_bytes())
    matrix_path = scratch / PANEL_CORPUS_FILES[0]

    occupation_tasks.write_tasks_sidecar(
        matrix_path,
        TasksTable(
            tasks={
                PANEL_ANCHOR_CODE: tuple(
                    OccupationTask(task=task, label=label)
                    for task, label in PANEL_TASKS
                )
            },
            source="contract-fixture",
            built_at="2026-09-21T00:00:00+00:00",
            label_model="contract-fixture",
        ),
    )
    occupation_conditions.write_conditions_sidecar(
        matrix_path,
        ConditionsTable(
            percentiles={
                PANEL_ANCHOR_CODE: {
                    "people": 0.07,
                    "public": 0.10,
                    "leading": 0.30,
                    "desk": 1.00,
                }
            },
            source="contract-fixture",
            built_at="2026-09-21T00:00:00+00:00",
        ),
    )

    os.environ["SOLVERAH_CORPUS_PATH"] = str(matrix_path)
    occupation_retrieval.reset_corpus_cache()
    occupation_tasks.reset_tasks_cache()
    occupation_conditions.reset_conditions_cache()

    corpus = occupation_retrieval.get_corpus()
    row = corpus.index_of(PANEL_ANCHOR_CODE)
    _PANEL_SAVED["get_openai_client"] = llm.get_openai_client
    llm.get_openai_client = lambda: _FixedEmbedder(
        [float(value) for value in corpus.matrix[row]]
    )


#: What `_install_panel_corpus` replaced, so `_remove_panel_corpus` can put it back.
_PANEL_SAVED: Dict[str, Any] = {}


def _remove_panel_corpus() -> None:
    """Undo `_install_panel_corpus`: no corpus, and the real OpenAI factory again.

    For the W-19 block, which must run in the state every step before the panel
    block ran in -- the CI runner's state. With the panel corpus and its fixed
    embedder still installed, a path-suggestion job would score for real, reach
    O*NET with a placeholder key, and start the narrator on a thread, and none of
    that produces stable bytes.
    """
    from backend.services import (
        occupation_conditions,
        occupation_retrieval,
        occupation_tasks,
    )
    from solverah.infra import llm

    os.environ.pop("SOLVERAH_CORPUS_PATH", None)
    occupation_retrieval.reset_corpus_cache()
    occupation_tasks.reset_tasks_cache()
    occupation_conditions.reset_conditions_cache()
    if "get_openai_client" in _PANEL_SAVED:
        llm.get_openai_client = _PANEL_SAVED.pop("get_openai_client")


def _seed_company(db) -> None:
    """Insert the company `company-detail` reads. Requires an app context."""
    from model import Company

    db.session.add(
        Company(
            name="Contract Industries",
            slug="contract-industries",
            profile_json=CONTRACT_COMPANY,
        )
    )
    db.session.commit()


#: The refresh cookie and the path it is scoped to.  Both are configuration in
#: the app (`JWT_REFRESH_COOKIE_NAME`, `JWT_REFRESH_COOKIE_PATH`); spelled out
#: here because the test client's jar is keyed on the path, so a capture that
#: guessed it would silently read `None` and record a scenario in which no
#: token was ever presented.
REFRESH_COOKIE = "refresh_token_cookie"
REFRESH_PATH = "/api/v1/auth/refresh"


def _put_refresh_cookie(client, raw: str) -> None:
    """Put a specific refresh token back in the jar.

    Replaying an ancestor is the only way to capture reuse detection, and the
    jar holds one token at a time.
    """
    client.set_cookie(REFRESH_COOKIE, raw, path=REFRESH_PATH, domain="localhost")


def _age_retirements(app) -> None:
    """Move every retirement out of the rotation grace window.

    The alternative is `time.sleep(31)` in a fixture that runs on every capture,
    for a constant chosen by the application. This moves the clock instead.
    """
    import datetime

    import sqlalchemy as sa

    from model import UserSession, db

    table = UserSession.__table__
    with app.app_context():
        db.session.execute(
            sa.update(table)
            .where(table.c.retired_at.isnot(None))
            .values(
                retired_at=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(minutes=5)
            )
        )
        db.session.commit()


def run_scenario() -> List[Dict[str, Any]]:
    """Drive the endpoints and return one masked record per request.

    Returns:
        A list of ``{step, method, path, status, mimetype, cookies_set, body}``
        dicts, in execution order. ``cookies_set`` is the cookie *names* the
        response sets: the names are contract, the values are secrets that differ
        every run.
    """
    os.environ.setdefault("APP_ENV", "testing")
    os.environ.setdefault("SOLVERAH_IGNORE_DOTENV", "1")
    # Before `_load_conftest_guard()`, which setdefaults the *suite's* database.
    # Whichever runs first wins, and this script must not be the one that ends up
    # dropping the schema the suite is using.
    os.environ.setdefault("DATABASE_URL", CONTRACT_DATABASE_URL)
    # Set, not setdefault: the value seeds the shuffle and salts the item tokens,
    # so a different one in the shell would reorder `/assessments/core/form` and
    # make the two sides of the diff disagree for a reason that is not a change.
    os.environ["SOLVERAH_FORM_TOKEN_SECRET"] = FORM_TOKEN_SECRET
    # `OnetClient()` refuses to construct without a key and `POST /me/path-fit`
    # builds one before it can refuse the request -- so without this the two
    # F-5 steps are 500s on both sides of the diff. Nothing is sent with it.
    os.environ.setdefault("ONET_API_KEY", "contract-not-a-real-key")
    _load_conftest_guard()

    from app import app
    from model import User, db

    app.config["TESTING"] = True
    _silence_outbound_email()
    _stub_llm()

    records: List[Dict[str, Any]] = []

    def record(step: str, resp, method: str, path: str) -> None:
        records.append(
            {
                "step": step,
                "method": method,
                "path": _mask_path(path),
                "status": resp.status_code,
                "mimetype": resp.mimetype,
                "cookies_set": sorted(
                    {
                        value.split("=", 1)[0]
                        for key, value in resp.headers
                        if key.lower() == "set-cookie"
                    }
                ),
                "body": _mask(resp.get_data(as_text=True)),
            }
        )

    with app.app_context():
        _reset_schema(db)
        _reset_cache()
        _seed_company(db)

    client = app.test_client()

    def call(step, method, path, **kwargs):
        resp = getattr(client, method.lower())(path, **kwargs)
        record(step, resp, method, path)
        return resp

    # -- registration and confirmation -------------------------------------
    call(
        "register",
        "POST",
        "/api/v1/auth/register",
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "name": "Contract User",
            "role": "job-seeker",
            "terms_accepted": True,
        },
    )
    call(
        "register-duplicate",
        "POST",
        "/api/v1/auth/register",
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "name": "Contract User",
            "role": "job-seeker",
            "terms_accepted": True,
        },
    )
    # A second account that is never confirmed, so the 403 branch below has a
    # subject. Its login attempt is the only step that reads
    # `email_confirmed` while it is false.
    call(
        "register-second",
        "POST",
        "/api/v1/auth/register",
        json={
            "email": UNCONFIRMED_EMAIL,
            "password": PASSWORD,
            "name": "Unconfirmed User",
            "role": "job-seeker",
            "terms_accepted": True,
        },
    )
    call(
        "login-before-confirmation",
        "POST",
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )

    with app.app_context():
        code = User.query.filter_by(email=EMAIL).first().confirmation_token

    call(
        "verify-email-wrong-code",
        "POST",
        "/api/v1/auth/email/verify",
        json={"email": EMAIL, "code": "000000"},
    )
    call(
        "verify-email",
        "POST",
        "/api/v1/auth/email/verify",
        json={"email": EMAIL, "code": code},
    )

    # -- login and the three endpoints under the governing rule ------------
    call(
        "login-wrong-password",
        "POST",
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": "Wrongpass1!"},
    )
    login = call(
        "login", "POST", "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    csrf = {"X-CSRF-TOKEN": login.get_json()["csrfToken"]}

    call("session", "GET", "/api/v1/auth/session")
    call("me", "GET", "/api/v1/me")
    call("me-profile-empty", "GET", "/api/v1/me/profile")

    # -- writes, then the same three again ---------------------------------
    call("patch-me", "PATCH", "/api/v1/me", json={"name": "Renamed User"}, headers=csrf)
    call(
        "patch-me-profile",
        "PATCH",
        "/api/v1/me/profile",
        json={
            "profile": {
                "firstName": "Contract",
                "lastName": "User",
                "summary": "A profile that exercises every promoted column.",
                "phone": "",
                "linkedinUrl": "https://example.test/in/contract",
                "location": "Austin, TX",
                "career_status": "employed",
                "experience": [
                    {
                        "id": 1,
                        "company": "Acme",
                        "title": "Engineer",
                        "startDate": "2019-01-01",
                        "endDate": "Present",
                        "description": "Built things.",
                    }
                ],
                "education": [
                    {
                        "id": 2,
                        "school": "State University",
                        "degree": "BS",
                        "field": "Computer Science",
                        "endDate": "2018",
                        "gpa": "3.8",
                    }
                ],
                "skills": ["Python", "Node.js", "C++"],
                "certifications": ["AWS SAA"],
            }
        },
        headers=csrf,
    )
    call(
        "patch-career-status",
        "PATCH",
        "/api/v1/me/career-status",
        json={"status": "employed"},
        headers=csrf,
    )
    call("get-skills-before-rating", "GET", "/api/v1/me/skills")
    call(
        "put-skills",
        "PUT",
        "/api/v1/me/skills",
        json={
            "skills": [
                {"name": "Python", "proficiency": "advanced"},
                {"name": "Node.js", "proficiency": "intermediate"},
            ]
        },
        headers=csrf,
    )
    call("get-skills", "GET", "/api/v1/me/skills")

    # -- the five assessments (Phase 2d) -----------------------------------
    #
    # Ordered so the not-yet-completed answers are recorded before the
    # completed ones. A 404 from `/me/assessments/work_pulse/result` is as much
    # a part of the contract as the 200 that follows it, and it is the one an
    # unmigrated read path would turn into a 500.
    call("assessments-catalogue-before", "GET", "/api/v1/assessments")
    call("assessment-form-unknown-kind", "GET", "/api/v1/assessments/nope/form")
    call("assessment-form-no-server-form", "GET", "/api/v1/assessments/work_pulse/form")
    core_form = call("assessment-form-core", "GET", "/api/v1/assessments/core/form")
    call("result-work-pulse-before", "GET", "/api/v1/me/assessments/work_pulse/result")
    call("result-focus-type-before", "GET", "/api/v1/me/assessments/focus_type/result")
    call("result-core-absent-by-design", "GET", "/api/v1/me/assessments/core/result")

    # `wpll` is the one instrument whose submit route persists nothing: the
    # stored state arrives from the anonymous session being claimed onto the
    # account, which is the write path 2d moves off `user_intake`.
    call(
        "claim-wpll-session",
        "POST",
        "/api/v1/intake/claims",
        json={
            "mode": "session",
            "selected_statement_ids": ["dir-1", "sus-2"],
            "wpll_answers": WPLL_ANSWERS,
            "wpll_insight_text": "Claimed from the anonymous session.",
        },
        headers=csrf,
    )

    # The three provider-scored instruments, each captured through both doors
    # (Phase 3c): the 410 tombstone on the old synchronous submit -- the
    # refusal and its `replaced_by` pointer are contract -- and the job pair
    # that took the scoring. Eager execution runs the job inside the enqueue,
    # so the 202 already reads `succeeded` and one poll carries the result.
    def queue_and_poll(kind: str, body: dict, headers=None) -> None:
        queued = call(
            "queue-%s" % kind.replace("_", "-"),
            "POST",
            "/api/v1/assessments/%s/scoring-jobs" % kind,
            json=body,
            **({"headers": headers} if headers else {}),
        )
        job_id = queued.get_json()["job_id"]
        call(
            "poll-%s-job" % kind.replace("_", "-"),
            "GET",
            "/api/v1/assessments/%s/scoring-jobs/%s" % (kind, job_id),
        )

    call(
        "submit-wpll-sync-gone",
        "POST",
        "/api/v1/assessments/wpll/submissions",
        json={"answers": WPLL_ANSWERS},
    )
    queue_and_poll("wpll", {"answers": WPLL_ANSWERS})

    call(
        "submit-work-pulse-sync-gone",
        "POST",
        "/api/v1/assessments/work_pulse/submissions",
        json={"answers": WP_ANSWERS},
        headers=csrf,
    )
    call(
        "queue-work-pulse-too-few-answers",
        "POST",
        "/api/v1/assessments/work_pulse/scoring-jobs",
        json={"answers": WP_ANSWERS[:3]},
        headers=csrf,
    )
    queue_and_poll("work_pulse", {"answers": WP_ANSWERS}, headers=csrf)

    call(
        "submit-focus-type",
        "POST",
        "/api/v1/assessments/focus_type/submissions",
        json=FOCUS_TYPE_PAYLOAD,
        headers=csrf,
    )
    call(
        "submit-manager-match-sync-gone",
        "POST",
        "/api/v1/assessments/manager_match/submissions",
        json={"answers": MM_ANSWERS},
        headers=csrf,
    )
    queue_and_poll("manager_match", {"answers": MM_ANSWERS}, headers=csrf)

    # `core` answers the form it was just served: the tokens are salted per
    # respondent, so they cannot be hard-coded here.
    core_responses = {
        item["token"]: item["options"][0]["key"]
        for block in (core_form.get_json() or {}).get("blocks", [])
        for item in block["items"]
    }
    call(
        "submit-core",
        "POST",
        "/api/v1/assessments/core/submissions",
        json={"responses": core_responses},
        headers=csrf,
    )

    call("result-work-pulse", "GET", "/api/v1/me/assessments/work_pulse/result")
    call("result-focus-type", "GET", "/api/v1/me/assessments/focus_type/result")
    call("result-manager-match", "GET", "/api/v1/me/assessments/manager_match/result")
    call("result-wpll-not-stored", "GET", "/api/v1/me/assessments/wpll/result")
    call("assessments-catalogue-after", "GET", "/api/v1/assessments")

    # Phase 3c: a cache miss computes nothing and answers 404 with a pointer at
    # the job pair. The cache is in-process and nothing in this scenario warms
    # it, so the miss is deterministic -- and this capture is what notices if
    # the inline fan-out ever comes back as a different status or body.
    call("path-suggestions-miss", "GET", "/api/v1/me/path-suggestions")

    call("me-after-write", "GET", "/api/v1/me")
    call("me-profile-after-write", "GET", "/api/v1/me/profile")
    call("session-after-write", "GET", "/api/v1/auth/session")
    call("dashboard", "GET", "/api/v1/me/dashboard")
    # Immediately again. Phase 3 caches this read, so the second call is the one
    # that can be answered from Redis without the handler running at all.
    call("dashboard-cached", "GET", "/api/v1/me/dashboard")
    call("export", "GET", "/api/v1/me/export")

    # -- company detail, the other cached read -----------------------------
    #
    # New to the scenario in Phase 3. It was never captured before, so nothing
    # stood between a change to this payload and production.
    call("company-detail", "GET", "/api/v1/companies/1")
    call("company-detail-cached", "GET", "/api/v1/companies/1")
    call("company-detail-missing", "GET", "/api/v1/companies/424242")

    # -- the unconfirmed account, and logout -------------------------------
    call(
        "login-unconfirmed",
        "POST",
        "/api/v1/auth/login",
        json={"email": UNCONFIRMED_EMAIL, "password": PASSWORD},
    )
    call("logout", "POST", "/api/v1/auth/logout", headers=csrf)
    call("session-after-logout", "GET", "/api/v1/auth/session")

    # -- the two anti-enumeration endpoints (S1, audit 2.3) ----------------
    #
    # These five steps exist for a different reason from every step above.
    # Elsewhere the baseline's job is to notice when a response changes; here
    # it is to notice when two responses stop being *the same as each other*.
    # S1 made forgot-password and resend-verification answer identically
    # whether or not the address exists, which is the entire fix -- a 404 for
    # an unknown address is an oracle that sorts a mailing list into "has a
    # Solverah account" and "does not".  That identity is invisible to every
    # other guard in the repo: the unit tests assert it directly, but nothing
    # would catch a future handler that reintroduced a distinguishing branch
    # in some path the unit tests do not construct.  Recording both answers
    # here means the diff shows it.
    #
    # Read these records in PAIRS.  `forgot-password-known` and
    # `forgot-password-unknown` must stay byte-identical to each other, and so
    # must the three `resend-verification-*` records.  A future diff that
    # changes both halves of a pair together is a deliberate wording change; a
    # diff that changes only one half is the security regression.
    #
    # Appended rather than inserted so the 55 records above keep their
    # positions, and placed after logout so the reset token these mint cannot
    # affect an earlier step.  Counts fit the live limits: forgot is 3/minute
    # and gets 2 calls, resend is 5/minute and gets 3.
    call(
        "forgot-password-known",
        "POST",
        "/api/v1/auth/password/forgot",
        json={"email": EMAIL},
    )
    call(
        "forgot-password-unknown",
        "POST",
        "/api/v1/auth/password/forgot",
        json={"email": ABSENT_EMAIL},
    )
    # Three populations, one answer.  The confirmed account is the case that
    # used to answer `400 Email already confirmed`, and the unconfirmed one is
    # the only address here for which the endpoint does real work.
    call(
        "resend-verification-unconfirmed",
        "POST",
        "/api/v1/auth/email/verify/resend",
        json={"email": UNCONFIRMED_EMAIL},
    )
    call(
        "resend-verification-confirmed",
        "POST",
        "/api/v1/auth/email/verify/resend",
        json={"email": EMAIL},
    )
    call(
        "resend-verification-unknown",
        "POST",
        "/api/v1/auth/email/verify/resend",
        json={"email": ABSENT_EMAIL},
    )

    # -- refresh tokens (S3, audit 1.1) ------------------------------------
    #
    # Appended after the anti-enumeration block so the 60 records above keep
    # their positions, exactly as A23 appended after `logout`.  These nine need
    # a session of their own -- `logout` ended the one the scenario had -- and
    # they leave the account logged out again at the end, which is where they
    # found it.
    #
    # Every call sends `json={}`.  That is not padding: the refresh endpoint
    # requires `application/json`, which is half of its CSRF control (a
    # cross-site HTML form can send three content types and none of them is
    # this one).  `refresh-form-content-type` below captures the refusal.
    #
    # Well inside the live limit -- the endpoint allows 30 per minute per IP and
    # this block makes seven calls to it -- so a scenario step can never record
    # a 429 as if it were the contract (A23's rule).
    call(
        "login-for-refresh",
        "POST",
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    login_token = client.get_cookie(
        REFRESH_COOKIE, path=REFRESH_PATH, domain="localhost"
    ).value

    call("refresh", "POST", REFRESH_PATH, json={})
    call("refresh-rotated", "POST", REFRESH_PATH, json={})
    live_token = client.get_cookie(
        REFRESH_COOKIE, path=REFRESH_PATH, domain="localhost"
    ).value

    # The stampede's second request: a token this scenario rotated past seconds
    # ago.  200, and -- the part that is the property -- no `refresh_token_cookie`
    # in `cookies_set`.  Read this record against `refresh` above.
    _put_refresh_cookie(client, login_token)
    call("refresh-replayed-in-grace", "POST", REFRESH_PATH, json={})

    # The same token, now outside the grace window.  Ageing the retirements
    # rather than sleeping thirty seconds, and rather than lowering the constant
    # -- a capture taken with the window set to zero would record the behaviour
    # of a design without a grace window, which is the design being ruled out.
    _age_retirements(app)
    call("refresh-replayed-after-grace", "POST", REFRESH_PATH, json={})

    # Reuse detection revoked the family, so the token that WAS live is dead
    # too.  Identical bytes to the record above it: every refusal answers the
    # same thing, so the endpoint cannot be used to tell a stale token from a
    # stolen one from one that never existed.
    _put_refresh_cookie(client, live_token)
    call("refresh-after-family-revoked", "POST", REFRESH_PATH, json={})

    # The two halves of the CSRF guard.  Neither reaches the token at all.
    call(
        "refresh-cross-site-origin",
        "POST",
        REFRESH_PATH,
        json={},
        headers={"Origin": "https://evil.example"},
    )
    call(
        "refresh-form-content-type",
        "POST",
        REFRESH_PATH,
        data="not-json",
        content_type="text/plain",
    )

    # Logout, and the finding itself: the refresh token minted by this sign-in
    # is worthless afterwards.  `logout-revoking` is byte-identical to the
    # `logout` record above -- the revocation is server-side and shows up in the
    # database, not in the response -- and `refresh-after-logout` is what makes
    # it visible on the wire.
    login = call(
        "login-for-logout",
        "POST",
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    call(
        "logout-revoking",
        "POST",
        "/api/v1/auth/logout",
        headers={"X-CSRF-TOKEN": login.get_json()["csrfToken"]},
    )
    _put_refresh_cookie(client, login_token)
    call("refresh-after-logout", "POST", REFRESH_PATH, json={})

    # -- Manager Decoder storage (C-3) -------------------------------------
    #
    # Appended after the refresh-token block so every record above keeps its
    # position, exactly as S3 appended after the anti-enumeration block. `logout`
    # ended the session the refresh block was using, so this needs a login of its
    # own too.
    #
    # EMAIL already completed a ManagerMatch sitting earlier in this scenario
    # (`queue_and_poll("manager_match", ...)`), so the account reaching this block
    # already has one -- which is what lets `submit-manager-profile` capture a
    # non-null `playbook` on its first call. The two 409 branches
    # (`GET /me/manager-playbook` with no ManagerMatch, and with a ManagerMatch but
    # no manager profile) are exhaustively covered by
    # tests/test_manager_playbook_api.py instead of here: this script's job is to
    # pin the wire shape of a response, not to enumerate every branch a route can
    # take, and reaching the no-ManagerMatch state honestly would cost a whole
    # second account (register, confirm, login) for one more captured 409 the
    # pytest suite already proves byte-for-byte in its own assertions.
    mp_login = call(
        "login-for-manager-profile",
        "POST",
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    mp_csrf = {"X-CSRF-TOKEN": mp_login.get_json()["csrfToken"]}

    call(
        "submit-manager-profile-malformed",
        "POST",
        "/api/v1/assessments/manager-profile",
        json={"answers": MP_ANSWERS[:10]},
        headers=mp_csrf,
    )
    call(
        "submit-manager-profile",
        "POST",
        "/api/v1/assessments/manager-profile",
        json={"answers": MP_ANSWERS},
        headers=mp_csrf,
    )
    call("manager-playbook", "GET", "/api/v1/me/manager-playbook")

    # A retake: same shape, a fresh row underneath. `manager-playbook-after-retake`
    # is compared against `manager-playbook` above precisely because both should be
    # structurally identical -- what changes is which values are inside, not the
    # envelope, and a diff here would mean a retake had somehow changed the shape.
    mp_retake = [dict(a, choice="b") for a in MP_ANSWERS]
    call(
        "submit-manager-profile-retake",
        "POST",
        "/api/v1/assessments/manager-profile",
        json={"answers": mp_retake},
        headers=mp_csrf,
    )
    call("manager-playbook-after-retake", "GET", "/api/v1/me/manager-playbook")

    # -- Situation Report (A-5) --------------------------------------------
    #
    # Appended after the Manager Decoder block, exactly as that block appended after
    # the refresh-token block: every record above keeps its position. Reuses
    # `mp_login`'s still-open session rather than a fresh one -- EMAIL already carries
    # everything this block needs by this point in the scenario: `career_status:
    # "employed"` (the `patch-me-profile` step), a completed `core` sitting
    # (`submit-core`), and now a `manager_profiles` row (the block just above), so
    # `manager.has_profile` is captured `true` without a second account.
    #
    # `submit-environment-report-malformed` pins the business-rule 400 shape (a
    # missing item id), the same class of capture `submit-manager-profile-malformed`
    # is above -- schema-level 422s are already covered by the routes that carry an
    # `enforce=True` body validator, so this is deliberately the OTHER failure mode.
    # `situation-report-recalibrate` is captured `recalibrated: false`: EMAIL has sat
    # `core` exactly once in this scenario, so the pin is already at the only sitting
    # there is -- the ⚑5 idempotence branch, not the move. The move itself, and the
    # `AuditLog` row it writes, are proven byte-for-byte in
    # tests/test_situation_report_api.py instead: capturing it here would need a
    # second `core` sitting for an account already carrying five other instruments'
    # worth of state, for a shape this script already pins the other half of.
    call("situation-report-needs-environment-report", "GET", "/api/v1/me/situation-report")

    # Every environment item answered on its "mixed" pole -- picked for the same
    # reason MM_ANSWERS/MP_ANSWERS pick one fixed choice: a stable, uninteresting
    # middle answer whose only job is to exercise the wire shape.
    from work_pulse import situation_items

    env_answers = {
        item["item_id"]: next(o for o in item["options"] if o["pole"] == "mixed")["key"]
        for item in situation_items.ENVIRONMENT_ITEMS
    }

    incomplete_env_answers = dict(env_answers)
    del incomplete_env_answers["env-autonomy-1"]
    call(
        "submit-environment-report-malformed",
        "POST",
        "/api/v1/me/environment-report",
        json={
            "answers": incomplete_env_answers, "stage_size": 3, "comp": 3, "experienced": 3,
        },
        headers=mp_csrf,
    )
    call(
        "submit-environment-report",
        "POST",
        "/api/v1/me/environment-report",
        json={
            "answers": env_answers, "stage_size": 3, "comp": 3, "industry": "tech",
            "experienced": 3,
        },
        headers=mp_csrf,
    )
    call("situation-report-complete", "GET", "/api/v1/me/situation-report")
    call(
        "situation-report-recalibrate",
        "POST",
        "/api/v1/me/situation-report/recalibrate",
        headers=mp_csrf,
    )

    # -- Pulse (B-2) --------------------------------------------------------
    #
    # Appended after the Situation Report block, exactly as that block appended
    # after the Manager Decoder block: every record above keeps its position.
    # Reuses `mp_csrf`'s still-open EMAIL session -- this account has never
    # touched Pulse, so it is a fresh `sequence: 0` account, the same reasoning
    # `pulse-next-checkin`'s capture below depends on.
    #
    # `pulse-checkin-malformed` pins the business-rule 422 (the served-set
    # refusal) -- schema-level 422s (an unknown event_type, a note over 280
    # characters, a cadence outside the four the user can set) are already
    # covered by the routes' `enforce=True` body validators, the same reasoning
    # `submit-manager-profile-malformed` above gives for capturing only the
    # OTHER failure mode here.
    from work_pulse.pulse_items import dimensions_for_checkin

    with app.app_context():
        pulse_user_id = User.query.filter_by(email=EMAIL).first().id

    call("pulse-next-checkin", "GET", "/api/v1/me/pulse/next-checkin")
    call("pulse-settings", "GET", "/api/v1/me/pulse/settings")

    # sequence 1's dims, submitted as sequence 0 -- the served-set refusal.
    wrong_dims = dimensions_for_checkin(pulse_user_id, 1)
    call(
        "pulse-checkin-malformed",
        "POST",
        "/api/v1/me/pulse/checkins",
        json={"item_scores": {dim: 3 for dim in wrong_dims}, "experienced": 3},
        headers=mp_csrf,
    )

    checkin_dims = dimensions_for_checkin(pulse_user_id, 0)
    call(
        "pulse-checkin",
        "POST",
        "/api/v1/me/pulse/checkins",
        json={"item_scores": {dim: 3 for dim in checkin_dims}, "experienced": 4},
        headers=mp_csrf,
    )
    call("pulse-history", "GET", "/api/v1/me/pulse/history")
    call(
        "pulse-event",
        "POST",
        "/api/v1/me/pulse/events",
        json={"event_type": "new_manager"},
        headers=mp_csrf,
    )
    call(
        "pulse-settings-update",
        "PATCH",
        "/api/v1/me/pulse/settings",
        json={"cadence": "biweekly"},
        headers=mp_csrf,
    )

    # -- Situation Report <-> Pulse wiring (B-4) ---------------------------
    #
    # Appended after the Pulse block so every record above keeps its position,
    # exactly as that block appended after the Situation Report block. `EMAIL`
    # already carries everything this needs by this point: a submitted
    # environment report (`submit-environment-report`, above) and, just now,
    # `pulse-event` logged a `new_manager` event *after* that submission -- so
    # re-reading the report is what captures `events_since_report` non-empty
    # for the first time. `situation-report-complete` above still captures the
    # empty-list case, which is the common one.
    call("situation-report-after-pulse-event", "GET", "/api/v1/me/situation-report")

    # -- Condition experiments (B-5) ---------------------------------------
    #
    # Appended after the Situation Report <-> Pulse block so every record above
    # keeps its position. Reuses `mp_csrf`'s still-open EMAIL session -- this
    # account already carries a completed core sitting and a submitted
    # environment report from the Situation Report block above, which is all
    # `POST /me/experiments`'s cell-pair validation needs.
    call(
        "post-experiment-malformed",
        "POST",
        "/api/v1/me/experiments",
        json={"dimension": "nonexistent", "direction": "under"},
        headers=mp_csrf,
    )
    call(
        "post-experiment",
        "POST",
        "/api/v1/me/experiments",
        json={"dimension": "autonomy", "direction": "under"},
        headers=mp_csrf,
    )
    call(
        "post-experiment-conflict",
        "POST",
        "/api/v1/me/experiments",
        json={"dimension": "pace", "direction": "over"},
        headers=mp_csrf,
    )
    call("get-experiments", "GET", "/api/v1/me/experiments")
    call(
        "post-experiment-abandon",
        "POST",
        "/api/v1/me/experiments/1/abandon",
        headers=mp_csrf,
    )
    # Idempotent: the same call again is still 200, unchanged.
    call(
        "post-experiment-abandon-again",
        "POST",
        "/api/v1/me/experiments/1/abandon",
        headers=mp_csrf,
    )
    call("get-experiments-after-abandon", "GET", "/api/v1/me/experiments")

    # -- Tier-2 deep fit (F-5) ---------------------------------------------
    #
    # Appended after the experiments block so every record above keeps its
    # position. Reuses `mp_csrf`'s still-open EMAIL session. Neither step
    # reaches O*NET or OpenAI -- see this module's docstring for why these two
    # and why they must not answer alike.
    call(
        "path-fit-malformed-code",
        "POST",
        "/api/v1/me/path-fit/not-an-onet-code",
        headers=mp_csrf,
    )
    call(
        "path-fit-corpus-unavailable",
        "POST",
        "/api/v1/me/path-fit/15-1252.00",
        headers=mp_csrf,
    )

    # -- inline card feedback (F-6) -----------------------------------------
    #
    # Appended after the F-5 block, so every record above keeps its position.
    # Same session, same reason none of these reaches a provider: there is no
    # corpus artifact in this environment, exactly as there is none on the CI
    # runner.
    #
    # THE THREE POSTS PIN AN ORDERING, WHICH IS THE PROPERTY WORTH A WIRE TEST.
    # The route checks the verdict vocabulary, then the shape of the code, then
    # the corpus -- and the three have to answer differently or a client cannot
    # tell a bug it should fix from an outage it should retry. A future diff that
    # made any two of them agree would be that ordering silently collapsing,
    # which no unit test phrases as a fact about the wire.
    call(
        "path-feedback-invalid-verdict",
        "POST",
        "/api/v1/me/path-feedback",
        json={"onet_code": "15-1252.00", "verdict": "sort-of"},
        headers=mp_csrf,
    )
    call(
        "path-feedback-malformed-code",
        "POST",
        "/api/v1/me/path-feedback",
        json={"onet_code": "not-an-onet-code", "verdict": "interesting"},
        headers=mp_csrf,
    )
    call(
        "path-feedback-corpus-unavailable",
        "POST",
        "/api/v1/me/path-feedback",
        json={"onet_code": "15-1252.00", "verdict": "interesting"},
        headers=mp_csrf,
    )
    # The reset, on the wire. It reaches the rescore rather than refusing early,
    # so without a corpus it is the transient answer -- which is the point: DELETE
    # and POST fail the same way for the same reason, and a diff where one of them
    # started answering 200 with an empty list would be a real behaviour change.
    call(
        "delete-path-feedback",
        "DELETE",
        "/api/v1/me/path-feedback",
        headers=mp_csrf,
    )

    # -- "what should change": the wants panel (W-4) -------------------------
    #
    # Appended after the F-6 block, so every record above keeps its position.
    # This block is the first in the file to run in TWO environments, and the
    # order is the point: the degrade answers are captured with no corpus, which
    # is the state every step above was captured in and the state the CI runner
    # is in, and only then is a scratch corpus installed for the working panel.
    #
    # BOTH METHODS MUST FAIL THE SAME WAY WITHOUT A CORPUS. The panel resolves
    # the user's own occupation out of the corpus, so a PUT cannot validate a key
    # without one either -- and a diff where the PUT started answering 200, or
    # 422, while the GET still answered 503 would mean a write had found some
    # other way to decide what this user was asked, which is the one bug this
    # table's whole keying discipline exists to prevent.
    panel_body = {
        "answers": [{"kind": "condition", "key": "people", "verdict": "more"}]
    }
    call("path-wants-corpus-unavailable", "GET", "/api/v1/me/path-wants")
    call(
        "path-wants-put-corpus-unavailable",
        "PUT",
        "/api/v1/me/path-wants",
        json=panel_body,
        headers=mp_csrf,
    )

    _install_panel_corpus()

    # The panel itself. `tasks` carries the plain-words labels and NOT the O*NET
    # statements they were written from: the statement is what the scorer embeds
    # (design doc 8.7) and a client that could read one might send it back as a
    # key. That absence is contract, which is why it is captured rather than only
    # unit-tested.
    call("path-wants", "GET", "/api/v1/me/path-wants")
    call(
        "path-wants-put",
        "PUT",
        "/api/v1/me/path-wants",
        json={
            "answers": [
                {"kind": "task", "key": _panel_task_key(0), "verdict": "less"},
                {"kind": "condition", "key": "people", "verdict": "more"},
            ]
        },
        headers=mp_csrf,
    )
    # A key the user's CURRENT occupation does not offer -- what a client holding
    # a panel across a job change sends. 422, and nothing is written, which the
    # clear below makes visible: it puts back a panel with ONE answer on it, not
    # two.
    call(
        "path-wants-put-unknown-key",
        "PUT",
        "/api/v1/me/path-wants",
        json={"answers": [{"kind": "task", "key": "t_000000000000", "verdict": "more"}]},
        headers=mp_csrf,
    )
    call(
        "path-wants-put-clear",
        "PUT",
        "/api/v1/me/path-wants",
        json={"answers": [{"kind": "task", "key": _panel_task_key(0), "verdict": None}]},
        headers=mp_csrf,
    )

    # -- and the user with no current job ------------------------------------
    #
    # A third account, on its own client so EMAIL's cookie jar is untouched, and
    # with no profile at all. `no_anchor` is a 200 rather than an error because
    # having no current job is not a failure -- design doc 8.3: no panel, and
    # card taps alone steer the page. The PUT answers the same way and writes
    # nothing, which is the pair worth capturing: a client that had a panel
    # cached from a previous job must not be able to store an answer against a
    # user who now has none.
    no_job = app.test_client()
    no_job.post(
        "/api/v1/auth/register",
        json={
            "email": NO_JOB_EMAIL,
            "password": PASSWORD,
            "name": "No Job User",
            "role": "job-seeker",
            "terms_accepted": True,
        },
    )
    with app.app_context():
        no_job_user = User.query.filter_by(email=NO_JOB_EMAIL).first()
        no_job_user.email_confirmed = True
        no_job_user.confirmation_token = None
        db.session.commit()
    no_job_csrf = {
        "X-CSRF-TOKEN": no_job.post(
            "/api/v1/auth/login",
            json={"email": NO_JOB_EMAIL, "password": PASSWORD},
        ).get_json()["csrfToken"]
    }
    # Registered and logged in WITHOUT capturing any of it: those three responses
    # are already pinned for EMAIL at the top of this scenario, and recording
    # them again would be three more records saying nothing new.
    record(
        "path-wants-no-anchor",
        no_job.get("/api/v1/me/path-wants"),
        "GET",
        "/api/v1/me/path-wants",
    )
    record(
        "path-wants-put-no-anchor",
        no_job.put("/api/v1/me/path-wants", json=panel_body, headers=no_job_csrf),
        "PUT",
        "/api/v1/me/path-wants",
    )

    # -- the path-suggestion job pair (W-19) ---------------------------------
    #
    # Appended last, so every record above keeps its position. The only way
    # suggestions are computed since 3c had no step until now, which is why the
    # DB ledger Package I defect -- the eager-mode 202 saying the terminal
    # status instead of "queued" -- was invisible here and caught only in
    # review. EMAIL again, on `mp_csrf`'s session.
    #
    # Back to no corpus first, the state the CI runner is in. The job then runs
    # past the reads -- career status set, skills on file, wants stored -- ends
    # its read transaction (the rollback that expired the route's row), and fails
    # on the corpus with the typed `corpus_unavailable`. That rollback is the
    # point: a job that failed earlier would leave the row loaded and the 202
    # would say "queued" with or without the fix.
    #
    # THE 202 MUST SAY "queued" EVEN THOUGH THE JOB HAS ALREADY FINISHED. Under
    # eager execution the job runs inside the POST, so the poll that follows is
    # already terminal: `failed`, `corpus_unavailable`, no `result`.
    _remove_panel_corpus()
    suggestion_job = call(
        "queue-path-suggestions",
        "POST",
        "/api/v1/me/path-suggestion-jobs",
        headers=mp_csrf,
    )
    suggestion_job_id = suggestion_job.get_json()["job_id"]
    call(
        "poll-path-suggestions-job",
        "GET",
        "/api/v1/me/path-suggestion-jobs/%s" % suggestion_job_id,
    )

    # -- the past-job environment report (A30) -------------------------------
    #
    # Appended last, so every record above keeps its position. EMAIL again, on
    # `mp_csrf`'s session: employed, with a current report already filed by the
    # Situation Report block, which is what a past report requires. The answers
    # sit on the "high" pole, NOT the current report's "mixed", so a past report
    # that leaked into the Situation Report would move every dimension -- and
    # `situation-report-after-past-report` must instead equal
    # `situation-report-after-pulse-event` except for `past_job_report_filed`.
    past_env_answers = {
        item["item_id"]: next(o for o in item["options"] if o["pole"] == "high")["key"]
        for item in situation_items.ENVIRONMENT_ITEMS
    }
    past_env_body = {
        "answers": past_env_answers, "stage_size": 2, "comp": 2, "industry": "retail",
        "experienced": 2, "subject": "past",
    }
    call(
        "submit-past-environment-report",
        "POST",
        "/api/v1/me/environment-report",
        json=past_env_body,
        headers=mp_csrf,
    )
    call("situation-report-after-past-report", "GET", "/api/v1/me/situation-report")
    call(
        "submit-past-environment-report-limit",
        "POST",
        "/api/v1/me/environment-report",
        json=past_env_body,
        headers=mp_csrf,
    )

    return records


def main(argv: List[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else BASELINE
    records = run_scenario()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("captured %d responses -> %s" % (len(records), target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
