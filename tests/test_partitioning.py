"""Phase 2, item 5: the three partitioned tables, and what partitioning must not cost.

Most of this file asserts things the database is responsible for rather than
things the application is, and that is the point. Partitioning is invisible from
the application side -- the same ORM calls, the same responses -- so a rebuild
that silently dropped a CHECK, or replaced an enforced foreign key with a column
that merely holds an integer, would leave every existing test passing.

The foreign key cases all use a *valid* `recommendation_id` with a **wrong**
`shown_at`. That pair is the one only a composite key catches: a single-column
key would accept it, and the row would look correct while pointing at nothing.

Everything here inserts through raw SQL rather than the ORM. The claim being
tested is that Postgres rejects these rows; going through the ORM would leave it
open that SQLAlchemy did.
"""

import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

#: Table -> the column it is range-partitioned on.
PARTITIONED = {
    "audit_log": "created_at",
    "match_recommendation": "shown_at",
    "rec_action": "acted_at",
}

#: A timestamp no monthly partition will ever be created for on purpose. If the
#: partition strategy has a gap, this is where a row falls through it.
FAR_FUTURE = datetime.datetime(2999, 12, 31, 23, 59, 59)
FAR_PAST = datetime.datetime(1970, 1, 1, 0, 0, 0)

#: Any timestamp that is not the parent's. Used to build a `(recommendation_id,
#: shown_at)` pair that names a recommendation which does not exist.
WRONG_SHOWN_AT = datetime.datetime(2001, 9, 9, 1, 46, 40)


@pytest.fixture()
def recommendation(client):
    """One `match_recommendation` row, with the user and company it needs.

    Returns `(recommendation_id, shown_at)` -- the composite key every table in
    this file has to name in full.
    """
    from app import app
    from model import Company, MatchRecommendation, User, db

    with app.app_context():
        user = User(email="partition@example.test", password_hash="not-a-real-hash")
        company = Company(name="Partition Co", slug="partition-co", profile_json={})
        db.session.add_all([user, company])
        db.session.commit()

        rec = MatchRecommendation(
            user_id=user.id, company_id=company.id, p_fit=0.5, channel="onsite"
        )
        db.session.add(rec)
        db.session.commit()
        return rec.id, rec.shown_at, user.id, company.id


def _execute(sql, **params):
    """Run one statement in its own transaction and return the result rows."""
    from app import app
    from model import db

    with app.app_context():
        try:
            result = db.session.execute(text(sql), params)
            # INSERTs return no rows, and asking one for them raises rather than
            # yielding an empty list.
            rows = result.all() if result.returns_rows else []
            db.session.commit()
            return rows
        except Exception:
            db.session.rollback()
            raise


# ---------------------------------------------------------------------------
# the tables are partitioned, and the fourth one deliberately is not
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", sorted(PARTITIONED))
def test_the_table_is_partitioned(client, table):
    """`relkind = 'p'` is the only proof that survives `db.create_all()`.

    The declaration lives in `model.py` rather than only in the migration
    precisely so this assertion can be made against the schema the suite builds.
    """
    rows = _execute(
        "SELECT relkind FROM pg_class WHERE relname = :t AND relnamespace = "
        "'public'::regnamespace",
        t=table,
    )
    assert rows and rows[0][0] == "p", "%s is not a partitioned table" % table


@pytest.mark.parametrize("table,key", sorted(PARTITIONED.items()))
def test_the_partition_key_is_the_expected_column(client, table, key):
    rows = _execute(
        "SELECT pg_get_partkeydef(CAST(:t AS regclass))",
        t=table,
    )
    assert rows[0][0] == "RANGE (%s)" % key


@pytest.mark.parametrize("table", sorted(PARTITIONED))
def test_the_table_has_at_least_one_partition(client, table):
    """A partitioned parent with no partitions accepts no rows at all.

    Every insert against one fails with "no partition of relation ... found for
    row", which would take the whole suite down rather than one test.
    """
    rows = _execute(
        "SELECT c.relname FROM pg_class c JOIN pg_inherits i ON i.inhrelid = c.oid "
        "WHERE i.inhparent = CAST(:t AS regclass)",
        t=table,
    )
    assert rows, "%s has no partitions, so it can hold no rows" % table


def test_no_other_table_became_partitioned(client):
    """Exactly three tables are partitioned, asserted as a whole set.

    Part 4 names a fourth high-volume table -- the per-item response table on the
    person side -- which is deliberately left alone. Partitioning it would drag
    its answer timestamp into the uniqueness guarantee over (submission, item),
    and a duplicate answer there changes `mean_pole`'s denominator: a score moves
    and nothing raises.

    Asserted as set equality rather than by naming that table, for two reasons.
    `tests/test_employer_visibility.py` holds the person-side names to an
    allowlist (D-01) and this file has no business being on it. And the set is the
    stronger claim regardless -- it fails for *any* table that becomes partitioned
    without a decision behind it, not only the one that was tempting.
    """
    rows = _execute(
        "SELECT relname FROM pg_class WHERE relkind = 'p' "
        "AND relnamespace = 'public'::regnamespace"
    )
    assert sorted(row[0] for row in rows) == sorted(PARTITIONED)


# ---------------------------------------------------------------------------
# the primary keys widened, and the foreign keys widened with them
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table,key", sorted(PARTITIONED.items()))
def test_the_primary_key_contains_the_partition_key(client, table, key):
    rows = _execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = CAST(:t AS regclass) AND contype = 'p'",
        t=table,
    )
    assert rows, "%s lost its primary key" % table
    assert "id" in rows[0][0] and key in rows[0][0], rows[0][0]


@pytest.mark.parametrize(
    "table", ["rec_action", "outcome_appeal", "outcome_experienced"]
)
def test_the_reference_to_match_recommendation_is_composite(client, table):
    """The foreign key survived the rebuild, and names both columns.

    Dropping these would have been the smaller change. All three feed the causal
    model, where a dangling recommendation reference is not an error anyone sees
    -- it is training data that is quietly wrong.
    """
    rows = _execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = CAST(:t AS regclass) AND contype = 'f' "
        "AND confrelid = 'match_recommendation'::regclass",
        t=table,
    )
    assert rows, "%s no longer references match_recommendation at all" % table
    definition = rows[0][0]
    assert "recommendation_id" in definition and "shown_at" in definition, definition


def test_a_rec_action_naming_no_recommendation_is_rejected(client, recommendation):
    rec_id, _shown_at, _user_id, _company_id = recommendation
    with pytest.raises(IntegrityError):
        _execute(
            "INSERT INTO rec_action (recommendation_id, shown_at, action, acted_at) "
            "VALUES (:r, :s, 'viewed', now())",
            r=rec_id,
            s=WRONG_SHOWN_AT,
        )


def test_an_outcome_appeal_naming_no_recommendation_is_rejected(
    client, recommendation
):
    rec_id, _shown_at, _user_id, _company_id = recommendation
    with pytest.raises(IntegrityError):
        _execute(
            "INSERT INTO outcome_appeal "
            "(recommendation_id, shown_at, fit_yes, channel, responded_at) "
            "VALUES (:r, :s, true, 'onsite', now())",
            r=rec_id,
            s=WRONG_SHOWN_AT,
        )


def test_an_outcome_experienced_naming_no_recommendation_is_rejected(
    client, recommendation
):
    rec_id, _shown_at, user_id, company_id = recommendation
    with pytest.raises(IntegrityError):
        _execute(
            "INSERT INTO outcome_experienced "
            "(user_id, company_id, recommendation_id, shown_at, checkin_at, "
            "working_scale) VALUES (:u, :c, :r, :s, now(), 4)",
            u=user_id,
            c=company_id,
            r=rec_id,
            s=WRONG_SHOWN_AT,
        )


@pytest.mark.parametrize(
    "table", ["rec_action", "outcome_appeal", "outcome_experienced"]
)
def test_the_matching_pair_is_accepted(client, recommendation, table):
    """The mirror of the three tests above: the right pair still gets in.

    A foreign key that rejected everything would pass all three rejection tests.
    """
    rec_id, shown_at, user_id, company_id = recommendation
    statements = {
        "rec_action": (
            "INSERT INTO rec_action (recommendation_id, shown_at, action, acted_at) "
            "VALUES (:r, :s, 'viewed', now())"
        ),
        "outcome_appeal": (
            "INSERT INTO outcome_appeal "
            "(recommendation_id, shown_at, fit_yes, channel, responded_at) "
            "VALUES (:r, :s, true, 'onsite', now())"
        ),
        "outcome_experienced": (
            "INSERT INTO outcome_experienced "
            "(user_id, company_id, recommendation_id, shown_at, checkin_at, "
            "working_scale) VALUES (:u, :c, :r, :s, now(), 4)"
        ),
    }
    _execute(statements[table], r=rec_id, s=shown_at, u=user_id, c=company_id)
    assert _execute("SELECT count(*) FROM %s" % table)[0][0] == 1


def test_a_placement_with_no_recommendation_behind_it_is_still_legal(
    client, recommendation
):
    """`outcome_experienced.recommendation_id` is nullable and stays that way.

    A composite foreign key with any NULL member is not checked, which is what
    keeps this case legal while a *stated* recommendation still has to exist.
    """
    _rec_id, _shown_at, user_id, company_id = recommendation
    _execute(
        "INSERT INTO outcome_experienced "
        "(user_id, company_id, recommendation_id, shown_at, checkin_at, working_scale) "
        "VALUES (:u, :c, NULL, NULL, now(), 3)",
        u=user_id,
        c=company_id,
    )
    assert _execute("SELECT count(*) FROM outcome_experienced")[0][0] == 1


def test_one_appeal_per_recommendation_is_still_the_rule(client, recommendation):
    """The uniqueness stayed on `recommendation_id` alone.

    Widening it to `(recommendation_id, shown_at)` -- which partitioning invites,
    since every other key here had to widen -- would accept a second appeal for
    the same recommendation, and only one of them can be about a real event.
    """
    rec_id, shown_at, _user_id, _company_id = recommendation
    insert = (
        "INSERT INTO outcome_appeal "
        "(recommendation_id, shown_at, fit_yes, channel, responded_at) "
        "VALUES (:r, :s, true, 'onsite', now())"
    )
    _execute(insert, r=rec_id, s=shown_at)
    with pytest.raises(IntegrityError):
        _execute(insert, r=rec_id, s=shown_at)


# ---------------------------------------------------------------------------
# every CHECK constraint the rebuild had to carry across
# ---------------------------------------------------------------------------


CHECKS = [
    (
        "ck_mrec_pfit_range",
        "INSERT INTO match_recommendation (user_id, company_id, p_fit, shown_at) "
        "VALUES (:u, :c, 1.7, now())",
    ),
    (
        "ck_mrec_pfit_low_range",
        "INSERT INTO match_recommendation (user_id, company_id, p_fit_low, shown_at) "
        "VALUES (:u, :c, -0.2, now())",
    ),
    (
        "ck_mrec_pfit_high_range",
        "INSERT INTO match_recommendation (user_id, company_id, p_fit_high, shown_at) "
        "VALUES (:u, :c, 42, now())",
    ),
    (
        "ck_mrec_channel_vocab",
        "INSERT INTO match_recommendation (user_id, company_id, channel, shown_at) "
        "VALUES (:u, :c, 'carrier-pigeon', now())",
    ),
]


@pytest.mark.parametrize("name,statement", CHECKS, ids=[c[0] for c in CHECKS])
def test_the_check_constraint_still_rejects(client, recommendation, name, statement):
    """A rebuild that quietly lost one of these is a regression nothing else sees.

    `p_fit` is a probability. Without its CHECK the column will hold 1.7, the
    model publishes a certainty it never computed, and no test fails.
    """
    _rec_id, _shown_at, user_id, company_id = recommendation
    with pytest.raises(IntegrityError) as caught:
        _execute(statement, u=user_id, c=company_id)
    assert name in str(caught.value)


def test_the_rec_action_vocabulary_still_rejects(client, recommendation):
    rec_id, shown_at, _user_id, _company_id = recommendation
    with pytest.raises(IntegrityError) as caught:
        _execute(
            "INSERT INTO rec_action (recommendation_id, shown_at, action, acted_at) "
            "VALUES (:r, :s, 'teleported', now())",
            r=rec_id,
            s=shown_at,
        )
    assert "ck_raction_action_vocab" in str(caught.value)


# ---------------------------------------------------------------------------
# no gaps: a row with an implausible timestamp still has somewhere to go
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("when", [FAR_PAST, FAR_FUTURE], ids=["far_past", "far_future"])
def test_an_out_of_range_audit_row_still_lands(client, when):
    """No monthly partition covers 1970 or 2999. The DEFAULT partition does.

    This is the failure mode that makes partitioning dangerous on a table with a
    live writer: a range with a hole in it turns a clock-skewed or backdated row
    into a failed request rather than a stored row.
    """
    _execute(
        "INSERT INTO audit_log (action, resource, created_at) "
        "VALUES ('read', 'profile', :t)",
        t=when,
    )
    rows = _execute(
        "SELECT count(*) FROM audit_log WHERE created_at = :t", t=when
    )
    assert rows[0][0] == 1


@pytest.mark.parametrize("when", [FAR_PAST, FAR_FUTURE], ids=["far_past", "far_future"])
def test_an_out_of_range_recommendation_still_lands(client, recommendation, when):
    _rec_id, _shown_at, user_id, company_id = recommendation
    _execute(
        "INSERT INTO match_recommendation (user_id, company_id, p_fit, shown_at) "
        "VALUES (:u, :c, 0.5, :t)",
        u=user_id,
        c=company_id,
        t=when,
    )
    assert _execute(
        "SELECT count(*) FROM match_recommendation WHERE shown_at = :t", t=when
    )[0][0] == 1


# ---------------------------------------------------------------------------
# the one partitioned table with a live writer
# ---------------------------------------------------------------------------


def test_the_audit_write_path_still_works(client):
    """`solverah/services/audit.py` is the only application writer of these three.

    So `audit_log` is the only one where partitioning can break a running code
    path, and the ORM insert -- not a hand-written INSERT -- is what that path
    actually does.
    """
    from app import app
    from model import User, db
    from solverah.services.audit import log_audit_event

    with app.app_context():
        user = User(email="audit-writer@example.test", password_hash="not-a-real-hash")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with app.test_request_context("/", headers={"User-Agent": "partition-test"}):
        with app.app_context():
            log_audit_event("read", user_id, "profile", {"partitioned": True})
            db.session.commit()

    rows = _execute(
        "SELECT action, resource, actor_user_id FROM audit_log WHERE actor_user_id = :u",
        u=user_id,
    )
    assert rows == [("read", "profile", user_id)]


def test_an_audit_row_lands_in_a_real_partition(client):
    """Not merely accepted -- actually routed to a partition, which is the point."""
    _execute(
        "INSERT INTO audit_log (action, resource, created_at) "
        "VALUES ('read', 'profile', now())"
    )
    rows = _execute("SELECT tableoid::regclass::text FROM audit_log")
    assert rows and rows[0][0] != "audit_log", (
        "the row reports the parent as its home, which no partitioned row should"
    )
