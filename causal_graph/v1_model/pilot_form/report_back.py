"""Write one pilot respondent's Situation Report as plain text, for pasting into an email.

    SOLVERAH_IGNORE_DOTENV=1 APP_ENV=development \\
    DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah_pilot \\
    python -m causal_graph.v1_model.pilot_form.report_back <pilot_id>

The CONTENT is the app's: `situation_report_service.get_situation_report` builds the report
exactly as `GET /me/situation-report` would for this respondent (same pin, same weights
source, same ranking, same guidance cells, same needs-forward slicing for someone between
jobs), and this file only lays it out as text with the labels the app's own report page
uses (situation/format.ts, DimensionCard.tsx).

D-15 holds here as it does on every payload: bucket WORDS and a direction PHRASE, never a
number. The service's payload carries `env_score` and `rank` for the page's own use; neither
is read here, the order of the list is the ranking, and `render_report` refuses to return
text containing any digit at all -- the guidance content has none, so a digit can only be a
leak.

Writes UTF-8 to a file OUTSIDE the repo (default Desktop/solverah-pilot/reports/<id>.txt)
and prints only the path: the guidance text has curly quotes and dashes, and this console
is cp1252.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

from . import DEFAULT_PRIVATE_DIR
from .import_responses import assert_outside_repo, open_app, pilot_email

from ..devfit.guard import PILOT_DB_PREFIX, require_database_url

DIMENSION_LABELS = {
    "autonomy": "Autonomy",
    "pace": "Pace",
    "collaboration": "Collaboration",
    "feedback": "Feedback",
    "innovation": "Innovation",
    "decision": "Decision-making",
}

BUCKET_LABELS = {"straining": "Straining", "notable": "Notable", "aligned": "Aligned"}

#: DimensionCard.tsx's FEEDBACK_DEFERRAL, the line shown when a dimension defers to the
#: Manager Decoder.
FEEDBACK_DEFERRAL = (
    "How feedback reaches you is set by one person more than by the company, so the "
    "playbook for it lives in the Manager Decoder."
)

RULE = "-" * 60


class ReportLeak(RuntimeError):
    """The rendered text carries a digit. Never sent; see the module docstring."""


def direction_label(direction: str, past: bool) -> str:
    if direction == "under":
        return "Less than you needed" if past else "Less than you need"
    return "More than you needed" if past else "More than you need"


def _wrap(text: str, indent: str = "") -> list:
    import textwrap

    return textwrap.wrap(" ".join(str(text).split()), width=78,
                         initial_indent=indent, subsequent_indent=indent) or [indent]


def _registers(entry: dict, past: bool) -> list:
    out: list = []
    registers = entry.get("registers") or {}
    change = registers.get("change_in_place")
    if change:
        out += ["", "  " + ("What to look for" if past else "Try a change")]
        if change.get("experiment_name"):
            out += _wrap(change["experiment_name"], "    ")
        if change.get("experiment"):
            out += _wrap(change["experiment"], "    ")
        for step in change.get("steps") or []:
            out += _wrap("- " + step, "    ")
        out += _wrap(("What to watch for next time: " if past else "How you'll know it worked: ")
                     + change["signal"], "    ")
    negotiate = registers.get("negotiate")
    if negotiate:
        out += ["", "  Negotiate it"]
        out += _wrap("Who, and where: " + negotiate["who_and_where"], "    ")
        out += _wrap("How to open: " + negotiate["opening"], "    ")
        for script in negotiate.get("scripts") or []:
            out += _wrap('What to say: "%s"' % script, "    ")
        out += _wrap("If the answer is no: " + negotiate["if_no"], "    ")
    rarely = registers.get("rarely_moves")
    if rarely:
        out += ["", "  " + ("Why it rarely moves" if past else "If it won't move")]
        out += _wrap("Why it's usually fixed: " + rarely["why_fixed"], "    ")
        out += _wrap("What staying costs: " + rarely["cost_of_staying"], "    ")
        out += _wrap("What that means: " + rarely["what_it_implies"], "    ")
    return out


def render_report(body: dict) -> str:
    """The report body (`get_situation_report`'s payload) as plain text. Reads words only;
    raises ReportLeak if a digit reaches the output anyway."""
    state = body.get("state")
    if state != "complete":
        text = (
            "No report for this respondent (state: %s). A report needs both the "
            "how-you-work questions and a described job; someone looking for their "
            "first job has no job to describe, so the app makes no report for them."
            % state
        )
        return _no_digits(text + "\n")

    past = bool(body.get("needs_forward"))
    lines = ["What to look for next" if past else "You, and this job", ""]
    if past:
        lines += _wrap(
            "Because that role is behind you, this report faces forward: what to look "
            "for next, rather than what to change where you are.")
        lines.append("")
    lines += _wrap(
        "Each part below is one way work can be organised, compared between how you "
        "work and how the job works. The most pressing comes first.")
    lines += ["", "Dimension by dimension", RULE]

    for entry in body.get("dimensions") or []:
        name = DIMENSION_LABELS.get(entry["dimension"], entry["dimension"])
        bucket = BUCKET_LABELS.get(entry["bucket"], entry["bucket"])
        lines.append("")
        if entry["bucket"] == "aligned":
            lines.append("%s -- %s" % (name, bucket))
            lines += _wrap(entry["aligned_note"], "  ")
            continue
        lines.append("%s -- %s, %s" % (name, bucket, direction_label(entry["direction"], past)))
        diagnosis = entry.get("diagnosis") or {}
        lines += _wrap(diagnosis.get("headline", ""), "  ")
        lines += _wrap(diagnosis.get("text", ""), "  ")
        lines += _registers(entry, past)
        if entry.get("defers_to_decoder"):
            lines += [""] + _wrap(FEEDBACK_DEFERRAL, "  ")
        if entry.get("decoder_crossref"):
            lines += [""] + _wrap(entry["decoder_crossref"], "  ")
        lines.append(RULE)

    lines += ["", "About this report"] + _wrap(body.get("guidance_notice", ""))
    return _no_digits("\n".join(lines) + "\n")


def _no_digits(text: str) -> str:
    match = re.search(r"\d", text)
    if match:
        raise ReportLeak(
            "the rendered report contains a digit near %r -- D-15 forbids numbers in a "
            "report; refusing to write it"
            % text[max(0, match.start() - 20):match.end() + 20].encode("ascii", "replace")
        )
    return text


def report_for_pilot_id(pilot_id: str) -> Optional[str]:
    """Inside an app context: the respondent's report text, or None if no such pilot id."""
    from model import User
    from solverah.services import situation_report_service

    user = User.query.filter_by(email=pilot_email(pilot_id)).first()
    if user is None:
        return None
    result = situation_report_service.get_situation_report(user)
    return render_report(result.body)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Write one pilot respondent's Situation Report as plain text."
    )
    parser.add_argument("pilot_id", help="from emails.csv (the respondent's row)")
    parser.add_argument("--database-url", default=None,
                        help="a LOCAL solverah_pilot* database; falls back to $DATABASE_URL")
    parser.add_argument("--out", default=None,
                        help="output file (outside the repo). Default %s"
                             % str(Path(DEFAULT_PRIVATE_DIR) / "reports" / "<pilot_id>.txt"))
    args = parser.parse_args(argv)

    pilot_id = args.pilot_id.strip().lower()
    pilot_email(pilot_id)  # validates the shape
    out = Path(args.out) if args.out else Path(DEFAULT_PRIVATE_DIR) / "reports" / (
        "%s.txt" % pilot_id)
    assert_outside_repo(out, "respondent reports")
    url = require_database_url(args.database_url, prefix=PILOT_DB_PREFIX)

    app, _db = open_app(url)
    with app.app_context():
        text = report_for_pilot_id(pilot_id)
    if text is None:
        print("no pilot respondent with id %s in %s" % (pilot_id, url.rsplit("/", 1)[-1]))
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print("wrote %s" % str(out).encode("ascii", "replace").decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
