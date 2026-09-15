"""Re-score stored ManagerMatch sittings under the corrected relationship key.

    python -m Scripts.backfill_manager_match_scoring_key --dry-run
    python -m Scripts.backfill_manager_match_scoring_key

WHAT THIS CORRECTS
------------------
`mm-q11` keyed `relationship` opposite to `mm-q9` and `mm-q10`: the high pole
scored the *distant* option ("trusts you enough to be hard to reach") 0.80 while
the other two items scored closeness and advocacy high. One of three items on the
scale ran backwards, depressing a genuinely high relational need by up to 0.183
for reasons unrelated to the construct -- MANAGER_PROFILE_ITEMS_BIAS_REVIEW.md,
Finding 7. `manager_match/questions.py` now keys it with the other two.

Every sitting stored before that flip carries a `relationship` score computed
under the old key, and a stored score is what `GET /me/assessments/manager_match/
result`, the profile document's `manager_match_result`, and the agent's context
block all serve. This script is what makes those rows say what the instrument now
means.

WHY RE-DERIVING FROM STORED ANSWERS IS SOUND, AND NOT A GUESS
-------------------------------------------------------------
Scores are derived; answers are the source of truth. `assessment_submissions.
answers` holds the payload the respondent actually sent for each of the four
non-`core` kinds -- see `AssessmentSubmission`'s "answers IS AN ADDITION TO PART
4.4" docstring, which names re-derivation as one of the reasons the column
exists. The culture-preference backfill (`matching_service.backfill_culture_
preferences`) already re-derives from stored Work Pulse answers; this is the same
move against the same column.

Nothing here re-interprets an answer. `score_manager_match` is called on exactly
the bytes the respondent submitted, under the corrected key, and the deterministic
half of the stored result is replaced with what a fresh submission of those same
answers produces today. `tests/test_manager_match_rescore.py` asserts that
equality rather than trusting it.

WHAT IT REFUSES TO TOUCH
------------------------
* **`core`, always.** The query names `manager_match` and nothing else. `core`
  answers and dimension scores live behind `assessment_store` (D-01) and are not
  in this table at all -- a `core` row carries null `result` and null `answers`
  under a check constraint.
* **Rows whose answers are missing or malformed.** They are counted and their
  public ids printed, never rewritten. A row that cannot be re-derived stays
  unmarked, which is the honest state: it *is* scored under the old key and
  nothing here can correct it. Silently stamping it v2 would be the one outcome
  worse than leaving it v1.
* **Rows with no result yet** (enqueued, in flight, or failed). There is nothing
  stored to correct; the next successful scoring writes v2 on its own.
* **Timestamps.** `completed_at` and `scored_at` describe the sitting, not this
  rewrite. What era the stored numbers belong to is `scoring_key`'s job, and
  that is the whole reason it was added.

IDEMPOTENT
----------
`result["scoring_key"]` is the marker, absent on every row written before the
correction. A row already carrying `manager_match.score.SCORING_KEY` is counted
and skipped, so a second run over a finished backfill rescores nothing. The one
category that stays visible run after run is the unusable-answers rows -- by
design, since those are the rows an operator has to decide about.

A NARRATIVE CAVEAT, STATED RATHER THAN PAPERED OVER
---------------------------------------------------
A sitting's `narrative`, `what_to_look_for`, `red_flags` and
`archetype_description` are LLM prose generated at submit time from the *old*
archetype and dimension scores. This script cannot regenerate them -- a backfill
that made an OpenAI call per user is a different piece of work with a different
cost -- so it preserves them verbatim and reports how many rows had their
archetype change underneath that prose. Those are the rows whose copy is now
describing a profile the numbers no longer say.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: The only kind this script may read or write. Named as a constant so the
#: "never touches core" property is one grep away rather than buried in a filter.
KIND = "manager_match"


def rescore_answers(answers):
    """The corrected deterministic scoring for *answers*, or None if unusable.

    "Unusable" is every shape `score_manager_match` cannot score: not a list, an
    entry that is not a mapping, the wrong number of answers, an unknown
    `question_id`, a `choice` that is not 'a' or 'b'. All of them mean the same
    thing here -- this row cannot be re-derived -- so they collapse to one
    return value and the caller counts it.
    """
    from manager_match.score import score_manager_match

    if not isinstance(answers, list) or not all(isinstance(a, dict) for a in answers):
        return None
    try:
        return score_manager_match(answers)
    except (ValueError, KeyError, TypeError):
        return None


def backfill(*, limit: int | None = None, dry_run: bool = False) -> dict:
    """Re-score every un-marked ManagerMatch sitting. Returns a census.

    Runs inside an existing Flask application context -- `main` opens one, and
    the tests call this directly inside theirs.

    Args:
        limit: Stop after this many rows have been *rescored*. The bound an
            operator actually wants is on writes, not on rows looked at; when it
            trips, the census describes the rows examined before the stop and
            `stopped_at_limit` says so.
        dry_run: Compute and report, write nothing.

    Returns:
        ``{"considered", "rescored", "already_v2", "no_result",
        "unusable_answers", "archetype_changed", "unusable_public_ids",
        "stopped_at_limit"}``
    """
    import sqlalchemy as sa

    from manager_match.score import SCORING_KEY
    from model import AssessmentSubmission, db

    counts = {
        "considered": 0,
        "rescored": 0,
        "already_v2": 0,
        "no_result": 0,
        "unusable_answers": 0,
        "archetype_changed": 0,
        "stopped_at_limit": False,
    }
    unusable: list[str] = []

    # Materialised rather than streamed: the loop commits per row, and committing
    # mid-iteration over a live cursor is how a backfill starts skipping rows.
    submissions = (
        db.session.execute(
            sa.select(AssessmentSubmission)
            .where(AssessmentSubmission.kind == KIND)
            .order_by(AssessmentSubmission.id)
        )
        .scalars()
        .all()
    )

    for submission in submissions:
        if limit is not None and counts["rescored"] >= limit:
            counts["stopped_at_limit"] = True
            break

        counts["considered"] += 1
        result = submission.result
        if not isinstance(result, dict):
            counts["no_result"] += 1
            continue
        if result.get("scoring_key") == SCORING_KEY:
            counts["already_v2"] += 1
            continue

        scoring = rescore_answers(submission.answers)
        if scoring is None:
            counts["unusable_answers"] += 1
            unusable.append(str(submission.public_id))
            continue

        if result.get("archetype") != scoring.get("archetype"):
            counts["archetype_changed"] += 1

        if not dry_run:
            # The LLM half of the result is preserved verbatim; the deterministic
            # half -- archetype, dimension_scores, scoring_key -- is replaced by
            # what a fresh submission of these answers produces today. A new dict
            # rather than a mutation, so SQLAlchemy sees the JSONB column change.
            submission.result = {**result, **scoring}
            db.session.commit()

        counts["rescored"] += 1

    counts["unusable_public_ids"] = unusable
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be rescored, write nothing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="stop after this many rows are rescored (default: no bound)",
    )
    args = parser.parse_args(argv)

    from app import app

    with app.app_context():
        from manager_match.score import SCORING_KEY

        print(
            "%sre-scoring %s submissions to scoring_key=%s"
            % ("DRY RUN: " if args.dry_run else "", KIND, SCORING_KEY)
        )
        counts = backfill(limit=args.limit, dry_run=args.dry_run)

    print(
        "considered=%(considered)d rescored=%(rescored)d already_v2=%(already_v2)d "
        "no_result=%(no_result)d unusable_answers=%(unusable_answers)d "
        "archetype_changed=%(archetype_changed)d" % counts
    )
    if counts["unusable_public_ids"]:
        print(
            "LEFT UNMARKED -- answers missing or malformed, cannot be re-derived:\n  %s"
            % "\n  ".join(counts["unusable_public_ids"])
        )
    if counts["archetype_changed"]:
        print(
            "NOTE: %d row(s) changed archetype. Their stored narrative copy was "
            "generated under the old one and is not regenerated here."
            % counts["archetype_changed"]
        )
    if counts["stopped_at_limit"]:
        print("STOPPED at --limit; rows remain. Re-run to continue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
