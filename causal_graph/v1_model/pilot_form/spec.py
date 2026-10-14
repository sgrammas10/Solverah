"""The pilot form as data, built from the app's live item banks.

Nothing in this file types a question. Every prompt and option text is read from:

    core          causal_graph/v1_model/assessment_items_v2.yaml through present_items.build_form,
                  the same presentation layer the app serves the core form from
    environment   work_pulse/situation_items.py (`item_list_in_form_order`, CONTEXT_ITEMS),
                  the scoring authority that src/.../envQuestions.ts mirrors

and the generator turns this spec into the Apps Script and the import mapping. A change to
either bank therefore changes the generated files, and the parity test fails until they are
regenerated -- the form cannot drift from the app silently.

The only words authored here are the framing the app's own screens carry and a form needs
in written form: the consent intro, page titles, the career-status question, the
previous-job gate and the optional email. Best-guess copy; Julie owns copy.

WHAT A GOOGLE FORM CANNOT DO THAT THE APP DOES, and what this does instead
-------------------------------------------------------------------------
* **Core item order is per-respondent in the app** (present_items: shuffled within dimension,
  interleaved across dimensions, seeded by respondent). A Google Form has one order for
  everyone (its own "shuffle question order" would break the interleave rule, so it stays
  off). The pilot uses ONE order -- exactly what the app would show a respondent whose id is
  CORE_ORDER_SEED -- so the rung order is still hidden and no two same-dimension items are
  adjacent, but every pilot respondent sees the same sequence. Scoring is order-invariant.
* **The app shows one question per screen.** The form groups them into pages. Core pages
  break at 8 and 16, NOT at the app's internal block boundaries (6/12/18): a page holding
  exactly one item of each dimension would hand back the grouping the interleave hides.
* **Tense is chosen live in the app.** A form cannot switch wording, so the job section is
  generated twice (present for `employed`, past for `between_jobs`) and the career-status
  answer branches to the right one.
* **`experienced` sits on its own final page** of each job section, so the descriptions are
  answered and paged past before the one evaluative item appears -- the form's version of
  the stepper's anti-halo ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from . import MODEL_DIR  # noqa: F401  -- sys.path side effects

#: Bumped whenever the generated form's STRUCTURE changes (not when a bank changes -- the
#: bank versions are recorded beside it in the mapping and checked on import).
#: pilot-v2-2026-10-13: added the five optional exploratory outcome items after
#: `experienced` in every job section (Amendment 3). The previous structure,
#: pilot-v1-2026-10-01, is snapshotted under legacy/ -- see responses.py's
#: LEGACY_MAPPING_PATHS -- because a form built from it may already be in the field.
PILOT_FORM_VERSION = "pilot-v2-2026-10-13"

#: The respondent id whose app-side core order the pilot reuses. Any fixed string works;
#: fixed is the point. Changing it reorders the committed form.
CORE_ORDER_SEED = "pilot-form-v1"

#: present_items.build_form insists on a token secret. The tokens it mints are discarded
#: here (the form addresses items by title, not token) and the ORDER does not depend on the
#: secret, so this is not a credential -- only a value that satisfies the signature.
CORE_ORDER_SECRET = b"pilot-form-order-only-not-a-secret"

#: Core items per page. 24 / 8 = 3 pages, breaking at 8 and 16 -- never at a multiple of
#: the 6-item block, see the module docstring.
CORE_ITEMS_PER_PAGE = 8

#: How the 12 dimension items of a job section are paged: two pages of six, in form order.
DIMENSION_ITEMS_PER_PAGE = 6

#: Navigation target meaning "submit the form" rather than a page.
SUBMIT = "SUBMIT"

Answer = Union[str, int, None]


@dataclass(frozen=True)
class Choice:
    """One option. `answer` is what the app would store for it: a core option key
    ('A'/'B'), an environment option key ('a'..'e'), a context value (1..5, an industry
    level, or None for "not sure"), a career status, or the gate's 'yes'/'no'."""

    text: str
    answer: Answer
    go_to: Optional[str] = None  # page_id or SUBMIT; only on branching questions


@dataclass(frozen=True)
class Question:
    #: Unique within the form, stable across regenerations: "<role>:<slot>:<item_id>".
    qid: str
    title: str
    kind: str  # "choice" | "email"
    required: bool
    role: str  # "core" | "career_status" | "context" | "env" | "gate" | "email"
    item_id: Optional[str] = None
    slot: Optional[str] = None  # job slot for context/env items
    help_text: str = ""
    choices: tuple = ()


@dataclass(frozen=True)
class Page:
    page_id: str
    title: str
    description: str = ""
    questions: tuple = ()
    #: Where to go after this page when it is reached linearly. None = the next page.
    go_to: Optional[str] = None


@dataclass(frozen=True)
class FormSpec:
    title: str
    description: str
    confirmation: str
    pages: tuple
    core_form_version: str
    env_form_version: str
    pilot_form_version: str = PILOT_FORM_VERSION
    core_item_order: tuple = field(default=())

    def questions(self) -> list:
        return [q for page in self.pages for q in page.questions]

    def page(self, page_id: str) -> Page:
        for page in self.pages:
            if page.page_id == page_id:
                return page
        raise KeyError(page_id)


# ---------------------------------------------------------------------------
# Job slots: which section of the form describes which report
# ---------------------------------------------------------------------------
#: slot -> (career status whose TENSE the wording uses, environment_reports.subject)
SLOT_CURRENT_PRESENT = "current_present"   # employed, describing the job they have
SLOT_CURRENT_PAST = "current_past"         # between_jobs, describing the job just left
SLOT_PREVIOUS = "previous"                 # the job before that, always past tense
SLOTS = {
    SLOT_CURRENT_PRESENT: ("employed", "current"),
    SLOT_CURRENT_PAST: ("between_jobs", "current"),
    SLOT_PREVIOUS: ("between_jobs", "past"),
}

#: The app's career-status vocabulary, with the labels its own prompt uses
#: (ProfileCompletenessNudge.tsx), in the same order.
CAREER_STATUS_CHOICES = (
    ("Currently employed", "employed"),
    ("Between jobs", "between_jobs"),
    ("Looking for my first job", "first_job"),
)

GATE_YES = "yes"
GATE_NO = "no"

CONTACT_LINE = (
    "Questions, or want your answers removed? Reply to the person who sent you this link."
)

FORM_TITLE = "How you work, and how your job works"

FORM_DESCRIPTION = (
    "This is a short research questionnaire from Solverah, a career tool that is still in "
    "development. It asks how you like to work and, if you have or recently had a job, how "
    "that job actually runs. Your answers are used to improve how Solverah compares people "
    "with jobs.\n\n"
    "- It's anonymous. We don't ask your name, and we never ask which company you work for.\n"
    "- It takes about 15 minutes. Questions marked optional can be skipped.\n"
    "- There are no right answers. Every question runs between two legitimate ways of "
    "working.\n"
    "- If you'd like a short written report on your answers, you can leave an email at the "
    "end. It's optional and kept separately from your answers. We use it to send your "
    "report and, only if you say yes at the end, to check in once a few months later.\n\n"
    "By continuing you agree to your answers being used this way.\n\n" + CONTACT_LINE
)

CONFIRMATION = (
    "Thank you, your answers are in. If you left an email, your report will follow."
)

CORE_DESCRIPTION = (
    "Short situations, two answers each. Pick the one closer to what you'd actually do, "
    "not what you think you should do."
)

CAREER_STATUS_TITLE = "Where are you in your career?"
CAREER_STATUS_HELP = "This decides which questions come next."

_SLOT_FRAMING = {
    SLOT_CURRENT_PRESENT: (
        "Your job",
        "These ask what your role actually offers: how much of the how is yours, what the "
        "tempo is, how decisions get made. Describe the job as it actually is, not as it was "
        "advertised or as it ought to be. Both ends of every question are a legitimate way "
        "to organise work.",
    ),
    SLOT_CURRENT_PAST: (
        "The job you most recently left",
        "These ask what your most recent role actually offered: how much of the how was "
        "yours, what the tempo was, how decisions got made. Describe the role as it actually "
        "was, not as the job description had it. Both ends of every question are a "
        "legitimate way to organise work.",
    ),
    SLOT_PREVIOUS: (
        "The job before that",
        "The same questions, asked about the job before your current or most recent one. "
        "Describe it as it actually was.",
    ),
}

GATE_TITLE = "Describe a previous job too?"
GATE_HELP = (
    "Optional. The same questions about the job before your current or most recent one. "
    "About five minutes."
)
GATE_CHOICES = (
    ("Yes, describe the job before that one", GATE_YES),
    ("No, finish here", GATE_NO),
)

EMAIL_TITLE = "Your email, if you'd like your report emailed to you"
EMAIL_HELP = (
    "Optional. Reports are built from the job questions, so we can only send one if you "
    "described a job. Your email is stored apart from your answers and used only to send "
    "your report and, if you say yes below, one check-in."
)

FOLLOWUP_YES = "yes"
FOLLOWUP_NO = "no"
FOLLOWUP_TITLE = "Can we check in once in a few months?"
FOLLOWUP_HELP = (
    "Optional. One short email asking how the job is going now. Only if you left an email "
    "above. You can say no and still get your report."
)
FOLLOWUP_CHOICES = (
    ("Yes, you can check in", FOLLOWUP_YES),
    ("No thanks", FOLLOWUP_NO),
)


# ---------------------------------------------------------------------------
# Building it
# ---------------------------------------------------------------------------
def core_items_in_pilot_order() -> tuple[str, list[dict]]:
    """(form_version, [{"item_id", "prompt", "options": [{"key", "text"}]}]) -- the app's
    own payload for respondent CORE_ORDER_SEED, flattened block by block."""
    import present_items

    payload, token_map = present_items.build_form(
        CORE_ORDER_SEED, present_items.DEFAULT_ITEMS_PATH, secret=CORE_ORDER_SECRET
    )
    items = []
    for block in payload["blocks"]:
        for item in block["items"]:
            items.append(
                {
                    "item_id": token_map[item["token"]],
                    "prompt": item["prompt"],
                    "options": [
                        {"key": o["key"], "text": o["text"]} for o in item["options"]
                    ],
                }
            )
    return payload["form_version"], items


def _core_pages(items: list[dict]) -> list[Page]:
    pages = []
    n_pages = -(-len(items) // CORE_ITEMS_PER_PAGE)
    for index in range(n_pages):
        chunk = items[index * CORE_ITEMS_PER_PAGE:(index + 1) * CORE_ITEMS_PER_PAGE]
        pages.append(
            Page(
                page_id="core_%d" % (index + 1),
                title="How you work (%d of %d)" % (index + 1, n_pages),
                description=CORE_DESCRIPTION if index == 0 else "",
                questions=tuple(
                    Question(
                        qid="core::%s" % item["item_id"],
                        title=item["prompt"],
                        kind="choice",
                        required=True,
                        role="core",
                        item_id=item["item_id"],
                        choices=tuple(Choice(o["text"], o["key"]) for o in item["options"]),
                    )
                    for item in chunk
                ),
            )
        )
    return pages


def _context_question(item: dict, slot: str) -> Question:
    return Question(
        qid="context:%s:%s" % (slot, item["item_id"]),
        title=item["prompt"],
        kind="choice",
        required=True,  # the app's stepper needs an answer; "not sure" IS an answer
        role="context",
        item_id=item["item_id"],
        slot=slot,
        choices=tuple(Choice(o["text"], o["value"]) for o in item["options"]),
    )


def _outcome_question(item: dict, slot: str) -> Question:
    """One of the five optional exploratory outcome items (Amendment 3, 2026-10-13).
    Shaped like `_context_question` -- a 1..5 value, not an option key -- but
    `required=False` and its own role so the importer and the completeness check
    never treat a skip as a gap in the instrument."""
    return Question(
        qid="outcome:%s:%s" % (slot, item["item_id"]),
        title=item["prompt"],
        kind="choice",
        required=False,
        role="outcome",
        item_id=item["item_id"],
        slot=slot,
        choices=tuple(Choice(o["text"], o["value"]) for o in item["options"]),
    )


OUTCOME_PAGE_DESCRIPTION = (
    "Optional. These are exploratory -- skip any or all of them. They never change "
    "your report."
)


def _job_pages(slot: str, *, after: Optional[str]) -> list[Page]:
    """Context page, two dimension pages, `experienced` alone, then the five optional
    outcome items on their own page. `after` is where the last page leads when it is
    not simply the next page -- now the outcomes page, since it comes after
    `experienced` (situation_items module doc: outcomes come after `experienced`,
    never between it and the twelve)."""
    from work_pulse import situation_items

    tense_status, _subject = SLOTS[slot]
    heading, intro = _SLOT_FRAMING[slot]
    context = {i["item_id"]: i for i in situation_items.render_context_items(tense_status)}
    dims = situation_items.render_items(tense_status)
    outcomes = situation_items.render_outcome_items(tense_status)

    pages = [
        Page(
            page_id="%s_context" % slot,
            title="%s: the setup" % heading,
            description=intro,
            questions=tuple(
                _context_question(context[item_id], slot)
                for item_id in ("stage_size", "comp", "industry")
            ),
        )
    ]
    n_dim_pages = -(-len(dims) // DIMENSION_ITEMS_PER_PAGE)
    for index in range(n_dim_pages):
        chunk = dims[index * DIMENSION_ITEMS_PER_PAGE:(index + 1) * DIMENSION_ITEMS_PER_PAGE]
        pages.append(
            Page(
                page_id="%s_work_%d" % (slot, index + 1),
                title="%s: how the work runs (%d of %d)" % (heading, index + 1, n_dim_pages),
                questions=tuple(
                    Question(
                        qid="env:%s:%s" % (slot, item["item_id"]),
                        title=item["prompt"],
                        kind="choice",
                        required=True,
                        role="env",
                        item_id=item["item_id"],
                        slot=slot,
                        # Authored order, never sorted: the alternating pole order is
                        # load-bearing (envQuestions.ts header, point 2).
                        choices=tuple(Choice(o["text"], o["key"]) for o in item["options"]),
                    )
                    for item in chunk
                ),
            )
        )
    pages.append(
        Page(
            page_id="%s_overall" % slot,
            title="%s: one last question" % heading,
            questions=(_context_question(context["experienced"], slot),),
        )
    )
    pages.append(
        Page(
            page_id="%s_outcomes" % slot,
            title="%s: a few optional extras" % heading,
            description=OUTCOME_PAGE_DESCRIPTION,
            questions=tuple(_outcome_question(item, slot) for item in outcomes),
            go_to=after,
        )
    )
    return pages


def build_spec() -> FormSpec:
    """The whole form. Page order (Google Forms is linear unless told otherwise):

        intro (the form description)
        core_1 .. core_3
        status            employed -> current_present_context
                          between  -> current_past_context
                          first    -> final
        current_present_* (5 pages), then -> gate
        current_past_*    (5 pages), then the gate (next page)
        gate              yes -> previous_context, no -> final
        previous_*        (5 pages), then final (next page)
        final             optional email
    """
    from work_pulse import situation_items

    core_version, core_items = core_items_in_pilot_order()

    status = Page(
        page_id="status",
        title="About you",
        questions=(
            Question(
                qid="career_status",
                title=CAREER_STATUS_TITLE,
                kind="choice",
                required=True,
                role="career_status",
                help_text=CAREER_STATUS_HELP,
                choices=(
                    Choice(CAREER_STATUS_CHOICES[0][0], "employed",
                           go_to="%s_context" % SLOT_CURRENT_PRESENT),
                    Choice(CAREER_STATUS_CHOICES[1][0], "between_jobs",
                           go_to="%s_context" % SLOT_CURRENT_PAST),
                    Choice(CAREER_STATUS_CHOICES[2][0], "first_job", go_to="final"),
                ),
            ),
        ),
    )
    gate = Page(
        page_id="gate",
        title="One more job (optional)",
        questions=(
            Question(
                qid="gate_previous",
                title=GATE_TITLE,
                kind="choice",
                required=True,
                role="gate",
                help_text=GATE_HELP,
                choices=(
                    Choice(GATE_CHOICES[0][0], GATE_YES, go_to="%s_context" % SLOT_PREVIOUS),
                    Choice(GATE_CHOICES[1][0], GATE_NO, go_to="final"),
                ),
            ),
        ),
    )
    final = Page(
        page_id="final",
        title="Last thing (optional)",
        questions=(
            Question(
                qid="email",
                title=EMAIL_TITLE,
                kind="email",
                required=False,
                role="email",
                help_text=EMAIL_HELP,
            ),
            # Explicit consent for ONE later re-ask of `experienced` (Sebastian,
            # 2026-10-02). Optional; a blank, or a yes with no email, means no.
            Question(
                qid="followup",
                title=FOLLOWUP_TITLE,
                kind="choice",
                required=False,
                role="followup",
                help_text=FOLLOWUP_HELP,
                choices=tuple(Choice(text, answer) for text, answer in FOLLOWUP_CHOICES),
            ),
        ),
    )

    pages = (
        _core_pages(core_items)
        + [status]
        + _job_pages(SLOT_CURRENT_PRESENT, after="gate")
        + _job_pages(SLOT_CURRENT_PAST, after=None)
        + [gate]
        + _job_pages(SLOT_PREVIOUS, after=None)
        + [final]
    )
    spec = FormSpec(
        title=FORM_TITLE,
        description=FORM_DESCRIPTION,
        confirmation=CONFIRMATION,
        pages=tuple(pages),
        core_form_version=core_version,
        env_form_version=situation_items.FORM_VERSION,
        core_item_order=tuple(item["item_id"] for item in core_items),
    )
    validate_spec(spec)
    return spec


class SpecError(ValueError):
    """The spec would produce a form whose answers cannot be mapped back unambiguously."""


def validate_spec(spec: FormSpec) -> None:
    """Every rule the importer relies on, checked at generation time:

    * qids unique;
    * option texts unique within a question (Google Forms requires it, and the CSV
      carries only the text);
    * every branch target names a real page;
    * a title may repeat across questions only between the past-tense current section
      and the previous-job section, which are told apart by column order (see
      responses.resolve_columns) -- anything else repeating would be a real ambiguity.
    """
    qids = [q.qid for q in spec.questions()]
    if len(qids) != len(set(qids)):
        raise SpecError("duplicate question ids")

    page_ids = {p.page_id for p in spec.pages}
    if len(page_ids) != len(spec.pages):
        raise SpecError("duplicate page ids")

    for page in spec.pages:
        if page.go_to not in (None, SUBMIT) and page.go_to not in page_ids:
            raise SpecError("page %s goes to unknown page %s" % (page.page_id, page.go_to))
        for q in page.questions:
            texts = [_norm(c.text) for c in q.choices]
            if len(texts) != len(set(texts)):
                raise SpecError("question %s has duplicate option texts" % q.qid)
            for c in q.choices:
                if c.go_to not in (None, SUBMIT) and c.go_to not in page_ids:
                    raise SpecError("%s branches to unknown page %s" % (q.qid, c.go_to))

    by_title: dict = {}
    for q in spec.questions():
        by_title.setdefault(_norm(q.title), []).append(q)
    for title, group in by_title.items():
        if len(group) == 1:
            continue
        slots = sorted(q.slot or "" for q in group)
        same_item = len({q.item_id for q in group}) == 1
        if not (same_item and slots == [SLOT_CURRENT_PAST, SLOT_PREVIOUS]):
            raise SpecError(
                "title repeats across %s; only the past-tense current and previous-job "
                "sections may share wording" % [q.qid for q in group]
            )


def _norm(text: str) -> str:
    """Whitespace-collapsed, stripped. Google trims and the CSV may re-wrap; nothing
    else about the text is changed (curly quotes and dashes are compared as-is)."""
    return " ".join(str(text).split())


def items_path() -> Path:
    import present_items

    return Path(present_items.DEFAULT_ITEMS_PATH)
