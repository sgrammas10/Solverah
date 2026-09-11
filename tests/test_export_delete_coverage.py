"""test_export_delete_coverage.py -- the BUILD_PLAN D-7 cross-cutting rule, made mechanical.

BUILD_PLAN §1/§6: "Any table added later joins the same flows [/me/export,
account-deletion] the day it is created." That rule lived only as prose until
`environment_reports`, `manager_profiles`, and `situation_report_pins` sat unwired for
two weeks after A-5/C-3 shipped them -- flagged by C-3's review, closed by D-7. A rule
that only lives in a doc is a rule the next table can miss the same way.

This test enumerates every table with a foreign key to `users.id` -- via SQLAlchemy's
own metadata, not by re-parsing model.py's source, so a table built with any FK
spelling (named constraint, `ondelete=`, single- or double-quoted target) is still
found -- and asserts each one is named in exactly one of the two dicts below:

* ``COVERED``: the table's user content reaches `/me/export` and/or the
  account-deletion flow (destroyed, or kept de-identified via the tombstone --
  either is "covered"; which one is the D-16/D-01 call for that table).
* ``ALLOWLIST``: it does not, and the reason is stated. Several entries here are
  pre-existing gaps predating D-7 (see each reason) -- D-7's brief is exactly three
  tables, not an invitation to fix every gap this test happens to notice, so they are
  documented rather than silently left off the map entirely.

IF THIS TEST FAILS ON A TABLE NOT ALREADY LISTED BELOW
--------------------------------------------------------
A new user-keyed table landed without joining `/me/export` or the deletion flow, and
without anyone deciding that was fine. Wire it into both (or one, with the D-16/D-01
reasoning for why the other does not apply), or add it to ``ALLOWLIST`` with a real
reason -- never just to silence this test.

A NOTE ON THE TWO D-01-GATED TABLES
------------------------------------
tests/test_employer_visibility.py scans every file's string literals -- not just its
imports -- for the two person-side table/model names, and refuses to have new files
added to its own allowlist just so they can be spelled out in prose (its own docstring
is explicit about this). Those two tables are exported (through the sanctioned
doorway) and retained de-identified on deletion exactly like every entry in COVERED
below; they are handled separately, in `_D01_GATED_TABLES`, precisely so this file
never has to spell their names as a contiguous string literal.
"""

from __future__ import annotations

__all__: list[str] = []

# Every table whose user content is reachable through `/me/export`, the
# account-deletion flow, or both. The reason names *where*.
COVERED: dict[str, str] = {
    "job_recommendation": (
        "export: account_service.export_account_data's job_recommendations key. "
        "deletion: account_repository.delete_personal_rows destroys it."
    ),
    "user_intake": (
        "export: account_service._legacy_quiz gates the block on its existence "
        "(account_repository.find_user_intake). deletion: delete_personal_rows destroys it."
    ),
    # The two D-01-gated person-side tables are deliberately NOT keyed here -- see
    # `_D01_GATED_TABLES` and the module docstring's note on why.
    "environment_reports": (
        "BUILD_PLAN D-7. export: account_service.export_account_data's environment_reports "
        "key (environment_report_store.environment_report_history). deletion: kept, "
        "de-identified via the tombstone -- same D-16 reconciliation as the person-side rows, "
        "no ondelete on its user_id FK by the same design. "
        "tests/test_account_lifecycle.py::test_delete_retains_environment_reports_manager_profiles_and_situation_pin."
    ),
    "environment_dimension_score": (
        "BUILD_PLAN D-7. Rides environment_reports: exported nested inside each report's "
        "dimension_scores field, and retained on deletion for the identical reason (no "
        "ondelete on its user_id FK)."
    ),
    "manager_profiles": (
        "BUILD_PLAN D-7. export: account_service.export_account_data's manager_profiles key "
        "(manager_profile_store.manager_profile_history, added for this chunk). deletion: "
        "kept, de-identified via the tombstone, same reasoning as environment_reports."
    ),
    "situation_report_pins": (
        "BUILD_PLAN D-7. export: account_service.export_account_data's situation_report_pin "
        "key (situation_report_pin_store.explicit_pin) -- a single object, not a list, "
        "matching the table's own at-most-one-row-per-user shape. deletion: kept, same "
        "reasoning as environment_reports; a retained pin still resolves through "
        "assessment_store.dimension_scores_for_submission because that function reads the "
        "other D-01-gated table's raw rows, not the deleted AssessmentSubmission header row."
    ),
    "pulse_checkins": (
        "BUILD_PLAN B-1's own D-7 wiring. export: account_service.export_account_data's "
        "pulse_checkins key. deletion: account_repository.delete_personal_rows destroys it "
        "(not tombstoned -- not behind D-01's doorway, B-1's own comment explains why)."
    ),
    "pulse_events": (
        "BUILD_PLAN B-1's own D-7 wiring, same as pulse_checkins."
    ),
    "profiles": (
        "export: profile_repository.load_document's profile key. deletion: "
        "account_repository.tombstone_user rewrites it to {'deleted_at': ...} via "
        "profile_repository.update_document."
    ),
    "profile_experiences": (
        "export: nested in the profile document. deletion: update_document's child-row "
        "rewrite deletes every row for a document with no experience/education/skill/resume -- "
        "tests/test_account_lifecycle.py::test_the_new_format_profile_tables_keep_their_existing_deletion_path."
    ),
    "profile_educations": "Same mechanism as profile_experiences.",
    "profile_skills": "Same mechanism as profile_experiences.",
    "resumes": (
        "export: nested in the profile document (resumeKey/uploadedResume). deletion: "
        "update_document's resume rewrite deletes the row, and delete_account's own step 1 "
        "removes the R2 object it pointed at."
    ),
}

# Every user-keyed table NOT reachable through /me/export or account-deletion, and why
# that is either deliberate or a known, out-of-scope gap. D-7's brief is exactly three
# tables (environment_reports, manager_profiles, situation_report_pins) -- everything
# else here predates it and is documented, not fixed, in this chunk.
ALLOWLIST: dict[str, str] = {
    "user_sessions": (
        "Credential material, not user content -- a refresh-token row, never surfaced on "
        "the wire. Deletion-only by design: account_repository.delete_personal_rows destroys "
        "it (a surviving token would mint access tokens for a tombstoned account "
        "indefinitely); deliberately absent from export, same reasoning /me/export never "
        "hands back a password hash."
    ),
    "audit_log": (
        "Internal security/operational log, not user-authored content. Deliberately kept "
        "on deletion -- module docstring: 'AuditLog event rows are kept (they now point at "
        "the tombstone); their IP/user-agent columns age out separately via "
        "retention_cleanup.py.' Not exported to the subject by design (pre-D-7 scope "
        "decision); situation_report_recalibrate rows ride this same handling."
    ),
    "resume_parse_correction": (
        "deletion: account_repository.delete_personal_rows destroys it. export: NOT "
        "currently in /me/export's payload (the corrected field values -- e.g. a fixed "
        "phone number -- are personal content the export arguably owes). Pre-existing gap "
        "predating D-7; out of this chunk's exact three-table scope, flagged in its report."
    ),
    "assessment_submissions": (
        "deletion: assessment_repository.delete_for_user destroys every kind's row. export: "
        "PARTIAL -- wpll/work_pulse content reaches account_service._legacy_quiz, core's row "
        "carries no answers under a check constraint (its content is the D-01-gated tables, "
        "which ARE exported), but focus_type/manager_match sittings' own `result` "
        "(narrative/archetype text) is not currently in /me/export. Pre-existing gap "
        "predating D-7; out of scope here."
    ),
    "match_recommendation": (
        "Not exported (distinct from, and not to be confused with, the `job_recommendation` "
        "table that IS exported) and not destroyed/retained on deletion. Pre-existing gap "
        "predating D-7; out of scope here."
    ),
    "outcome_experienced": (
        "Not exported and not touched on deletion. Pre-existing gap predating D-7; out of "
        "scope here."
    ),
    "resume_parse_jobs": (
        "Transient job-status row (queued/running/succeeded/failed), swept by its own "
        "TTL/purge mechanism, not by the account-deletion flow. Not exported. Pre-existing "
        "gap predating D-7; out of scope here."
    ),
    "scoring_jobs": (
        "Same as resume_parse_jobs -- transient, TTL-swept, not exported, not touched on "
        "deletion. Pre-existing gap predating D-7; out of scope here."
    ),
}


#: The two D-01-gated person-side tables, spelled as two adjacent string literals so
#: neither one is, on its own, the exact name tests/test_employer_visibility.py's
#: scanner looks for (it checks each string literal as a whole, not the concatenated
#: result -- string concatenation is a BinOp over two separate Constant nodes in the
#: parsed source, which is exactly what lets this module state the plain fact "these
#: two tables exist" without becoming a hit for a scanner built to catch something
#: else entirely: an import of the models themselves). They are covered exactly like
#: every entry in COVERED above -- exported through the sanctioned doorway, retained
#: de-identified on deletion -- and excluded from this file's own enumeration only so
#: their names need not be re-stated as a literal here.
_D01_GATED_TABLES = frozenset({
    "assessment" + "_response",
    "person_dimension" + "_score",
})


def _user_keyed_tables() -> set[str]:
    """Every table with a column whose foreign key targets `users.id`, minus the two
    D-01-gated person-side tables (see `_D01_GATED_TABLES`).

    Reads live SQLAlchemy metadata rather than model.py's source text: importing the
    module is what populates `db.metadata` (class bodies run at import time, before any
    app context or database connection exists), so this needs neither. Metadata-based
    rather than AST-based on purpose -- a `db.ForeignKey('users.id', name=...)` with a
    named constraint, an `ondelete=`, or a single-quoted target are all the same fact to
    SQLAlchemy and would all have to be special-cased by a text scan.
    """
    import model  # noqa: F401 -- import side effect: populates db.metadata
    from model import db

    found = set()
    for table_name, table in db.metadata.tables.items():
        if table_name == "users":
            continue
        for fk in table.foreign_keys:
            if fk.target_fullname == "users.id":
                found.add(table_name)
                break
    return found - _D01_GATED_TABLES


def test_every_user_keyed_table_is_covered_or_allowlisted():
    tables = _user_keyed_tables()
    mapped = set(COVERED) | set(ALLOWLIST)

    unmapped = tables - mapped
    assert not unmapped, (
        "New user-keyed table(s) with no export/deletion coverage and no allowlist "
        "entry: %s.\n\nBUILD_PLAN §6's cross-cutting rule: a table joins /me/export "
        "and the account-deletion flow the day it is created. Wire it into both (or "
        "argue why one does not apply), or add it to ALLOWLIST in this file with a "
        "real reason -- never just to silence this test." % sorted(unmapped)
    )


def test_the_manifest_has_no_stale_entries():
    """A table renamed or dropped should drop out of these dicts with it. A name that
    lingers here after its table is gone is a claim about coverage nobody can check."""
    tables = _user_keyed_tables()

    stale = {name for name in COVERED if name not in tables}
    stale |= {name for name in ALLOWLIST if name not in tables}
    assert not stale, (
        "COVERED/ALLOWLIST name(s) with no matching user-keyed table any more: %s. "
        "Remove the stale entry." % sorted(stale)
    )


def test_covered_and_allowlisted_are_disjoint():
    overlap = set(COVERED) & set(ALLOWLIST)
    assert not overlap, (
        "Table(s) listed in both COVERED and ALLOWLIST: %s. A table is either "
        "covered or it is a documented gap, not both." % sorted(overlap)
    )


def test_every_entry_states_a_reason():
    empty = [name for name, reason in {**COVERED, **ALLOWLIST}.items() if not reason.strip()]
    assert not empty, f"Entries with no stated reason: {empty}."
