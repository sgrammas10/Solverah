"""Static guidance content for the Situation Report (BUILD_PLAN A-6).

Content, not code. Sibling of `manager_match/playbook_content.py` and built to
the same rule: drafted once, human-reviewed once, served by deterministic
lookup. Nothing here is generated per user, and nothing here reaches a request
path that calls a provider. `work_pulse/situation.py` (A-3) will hold the gap
engine; this file holds only the words, so the content review has a single
surface — the `insight_engine.py` pattern at full scale.

Three tables, deliberately separate
-----------------------------------
`DIAGNOSES` is keyed by ``(dimension, direction)`` — twelve entries, one per
gap cell. It carries the *situation* sentence in two renderings: `current_role`
for an employed user, `needs_forward` for a between-jobs or first-job user
(`career_status`). A-5/A-7 swap the sentence; they do not rewrite it.

`GUIDANCE_CELLS` is keyed by ``(dimension, direction, register)`` — thirty-six
entries — and carries *only* the actions. Nothing in a guidance cell restates
the diagnosis, so the needs-forward rendering can drop or keep each register
independently without leaving a dangling half-sentence. That separation is the
whole reason those are two tables rather than one.

`ALIGNED_NOTES` is keyed by ``(dimension, band)`` — eighteen entries — and is
the only table an `aligned` dimension reaches. It exists because the other
two are keyed on a direction and an aligned dimension has none, which left
A-7 with a blank row for every dimension that is *fine*; C-2 answered the
identical blank half of its own map with `MESH_NOTES`, and this is that,
ported. One short note apiece — never a register cell, because there is no
problem here to run an experiment against.

Keys
----
  * dimension — the six model dimensions, same strings as the rater rubric and
    `causal_graph`: autonomy, pace, collaboration, feedback, innovation,
    decision. High pole is self-directed / fast / collective / frequent-blunt /
    invent / data.
  * direction — `under_supplied` (the environment runs *lower* on this
    dimension than the person needs) or `over_supplied` (higher). Same strings
    and same sense as `manager_match.decoder`; a tripwire test asserts they
    have not drifted apart.
  * register — `change_in_place`, `negotiate`, `rarely_moves`.
  * band — `low` / `mid` / `high`, where the person and the environment
    jointly sit on the scale. Aligned dimensions only; the same three-word
    vocabulary `manager_match.decoder` bands a mesh with, on A-1's anchors
    rather than the decoder's.

Six dimensions × two directions × three registers = the thirty-six cells; six
dimensions × three bands = the eighteen aligned notes.

How A-3/A-5 look this up
------------------------
A-3 returns a coarse gap *bucket* per dimension — ``aligned`` / ``notable`` /
``straining`` — and a separate *direction* — ``under`` / ``over`` / ``None``
(2026-09-10 rename, PRODUCT_DECISIONS.md §2: "the bucket names change before
any API ships them ... magnitude only ... plus a separate direction field").
Before the rename the two non-aligned bucket names doubled as both magnitude
and sign, which let a bucket alone determine a direction; since the rename `notable`
and `straining` are magnitude-only and each pairs with *either* direction
(the same shape `manager_match.decoder`'s `notable`/`acute` *severities*
already have, independent of ITS `direction` field), so a bucket alone no
longer determines one. `direction_for_bucket` is the join: an A-3 report
entry's own `(bucket, direction)` in, this file's `under_supplied` /
`over_supplied` vocabulary out, or `None` where `aligned` shows no
*directional* guidance — an aligned dimension resolves to `ALIGNED_NOTES`
through `aligned_note_for` instead, which needs no direction at all.
`BUCKET_TO_DIRECTION` carries the one fact a bucket alone still decides:
whether a direction is expected at all.

Both directions get cells. An over-supplied dimension is a real mismatch (a
pace above the one you can hold, a day more shared than you need) and
eighteen of the thirty-six cells exist for it, so a consumer that renders
guidance only for `under_supplied` would silently drop half this file.

No threshold, score or magnitude lives here, and none should — that is what
keeps the D-15 conformance argument in one place.

Tone rules, binding, inherited from the C-2 content review (approved
2026-09-10) and PRODUCT_DECISIONS §1–2:

  * **Fit, not fault.** Every dimension runs between two legitimate ways to
    organise work. A directed, fast-paced, low-autonomy shop is a real and
    often deliberate way to run a business, not a bad company. The strain is
    the distance between the person and the place, never the place.
  * **Describe the situation, not the employer.** Cells describe what the work
    is like and what the distance costs. No cell characterises the company, and
    no cell contains a fault word — including one introduced only to deny it,
    which leaves the word with the reader either way.
  * **`rarely_moves` is honest, not bleak.** It names a ceiling, names what
    staying costs, and ends on the fit question the way C-2's acute cells do —
    "a question about fit and not a failure on either side". It never tells the
    user to leave and never promises the ceiling will lift.
  * **Manager behaviour defers to the Decoder (⚑4, A-6's second bullet).** The
    whole `feedback` dimension defers: how critique reaches you is enacted by
    one person, so its six cells name the situation at the environment level
    and route to the Manager Decoder rather than duplicating protocol.
    `autonomy` carries a cross-reference instead of a deferral, because the
    environment lever there is real (sign-offs, scope, process) even when the
    manager is the proximate one. The other four dimensions have no Decoder
    counterpart, so they point at nothing and say nothing.
"""
from __future__ import annotations

from typing import TypedDict

# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

DIMENSIONS: tuple[str, ...] = (
    "autonomy",
    "pace",
    "collaboration",
    "feedback",
    "innovation",
    "decision",
)

# Deliberately the same strings as `manager_match.decoder`, and the same sense:
# the supplier (manager there, environment here) runs above or below the need.
UNDER_SUPPLIED = "under_supplied"
OVER_SUPPLIED = "over_supplied"
GAP_DIRECTIONS: tuple[str, ...] = (UNDER_SUPPLIED, OVER_SUPPLIED)

CHANGE_IN_PLACE = "change_in_place"
NEGOTIATE = "negotiate"
RARELY_MOVES = "rarely_moves"
REGISTERS: tuple[str, ...] = (CHANGE_IN_PLACE, NEGOTIATE, RARELY_MOVES)

# Which buckets carry a direction at all. `aligned` never does; `notable` and
# `straining` always do, but -- since the 2026-09-10 rename made buckets
# magnitude-only -- WHICH direction is no longer decided by the bucket alone,
# so this cannot map straight to `under_supplied`/`over_supplied` the way it
# did before the rename. `direction_for_bucket` reads the real direction off
# the same A-3 report entry the bucket came from. Kept here rather than in
# A-3 because it is a fact about which content to serve, not about how to
# score; a tripwire test asserts it stays total over A-3's three buckets.
BUCKET_TO_DIRECTION: dict[str, bool] = {
    "aligned": False,
    "notable": True,
    "straining": True,
}

# A-3's own direction vocabulary (`work_pulse.situation.UNDER`/`.OVER`, i.e.
# `under`/`over`) is shorter than this file's, which stays `under_supplied` /
# `over_supplied` to keep matching `manager_match.decoder`. The translation,
# total over A-3's vocabulary.
_DIRECTION_FROM_GAP_ENGINE: dict[str, str] = {
    "under": UNDER_SUPPLIED,
    "over": OVER_SUPPLIED,
}

# Dimensions whose lever is a person rather than the environment, and which
# therefore hand the protocol to C-2 instead of writing a second one.
DEFERRED_DIMENSIONS: frozenset[str] = frozenset({"feedback"})

# The name the deferral cells and cross-references use for C-2's surface. Kept
# as a constant so the test can assert the link is really there and so a rename
# is one edit.
DECODER_REFERENCE = "Manager Decoder"


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

class Diagnosis(TypedDict):
    """The situation, in the two renderings `career_status` selects between."""

    headline: str
    current_role: str
    needs_forward: str


class ChangeInPlaceCell(TypedDict):
    """A runnable two-week change. `experiment_name` and `signal` seed B-5."""

    experiment_name: str
    experiment: str
    steps: list[str]
    signal: str


class NegotiateCell(TypedDict):
    """What to say, to whom, in what setting."""

    who_and_where: str
    opening: str
    scripts: list[str]
    if_no: str


class RarelyMovesCell(TypedDict):
    """The honest register: the ceiling, its cost, and what it implies."""

    why_fixed: str
    cost_of_staying: str
    what_it_implies: str


GuidanceCell = ChangeInPlaceCell | NegotiateCell | RarelyMovesCell


# ---------------------------------------------------------------------------
# Scope notice (the C-2 PRIVACY_NOTICE analogue)
# ---------------------------------------------------------------------------

GUIDANCE_NOTICE: str = (
    "This guidance is general, not personal. Every one of these suggestions was "
    "written before we knew anything about you; the report picks them by looking "
    "at the distance between what you told us about how you work and what you "
    "told us about your job. Nothing here is a judgement about your employer. "
    "Every dimension runs between two legitimate ways to organise work, and a "
    "company sitting at one end of one is not doing it wrong — what the report "
    "says is that you and the job are set differently on that dimension, which "
    "is a fact about the pair of you and not about either one alone. It is a "
    "private working note, and nobody at your company can see it."
)


# ---------------------------------------------------------------------------
# The twelve diagnoses
# ---------------------------------------------------------------------------

DIAGNOSES: dict[tuple[str, str], Diagnosis] = {

    ("autonomy", UNDER_SUPPLIED): {
        "headline": "The role decides more of the how than you want decided",
        "current_role": (
            "You work best when someone sets the outcome and leaves the route to "
            "you. This role settles more of that before it reaches you — the "
            "approach, the order, sometimes the timing. Running work through "
            "defined process and approval chains is a legitimate way to run a "
            "company, in several industries the only lawful one, and in plenty of "
            "well-run places a deliberate choice. The strain is the distance, not "
            "the design: the part of the job you are strongest at, working out "
            "how, is already done by the time the work arrives."
        ),
        "needs_forward": (
            "What to seek: a role that hands you the outcome and leaves the route "
            "open. The useful question in an interview is not whether the role has "
            "autonomy — everyone says yes — but who signs off on what, and how a "
            "decision like the one you would own actually got made last month."
        ),
    },

    ("autonomy", OVER_SUPPLIED): {
        "headline": "The role leaves more open than you want left open",
        "current_role": (
            "You do your best work when the direction is set and you can put your "
            "effort into executing it well. This role leaves more of that to you — "
            "what to work on, in what order, to what standard. Handing people a "
            "blank page is a legitimate way to run work and it is exactly what a "
            "lot of people want most; it also assumes context you may never have "
            "been given. The strain is the distance: effort you would rather spend "
            "on the work goes into deciding what the work is."
        ),
        "needs_forward": (
            "What to seek: a role with a defined remit and a named owner for the "
            "calls above your line. Worth asking what the first ninety days are "
            "specified down to, and who decides when something is above you — a "
            "role that cannot answer either question is the same shape again."
        ),
    },

    ("pace", UNDER_SUPPLIED): {
        "headline": "The work runs steadier than you would choose",
        "current_role": (
            "You are at your best with things moving: short turnarounds, real "
            "deadlines, the next thing already coming. This role runs at a more "
            "deliberate cadence than that. A steady tempo is a legitimate choice "
            "and usually a deliberate one — it is how careful work gets done and "
            "how people stay somewhere for a decade. The strain is the distance: a "
            "tempo you have to slow down to match, sustained, reads as flatness "
            "rather than as calm."
        ),
        "needs_forward": (
            "What to seek: a role where the tempo is structurally quick — short "
            "cycles, real deadlines, a queue that refills. Ask how often something "
            "ships and what the last genuinely urgent week looked like. "
            "\"Fast-paced\" on a careers page is the weakest evidence there is."
        ),
    },

    ("pace", OVER_SUPPLIED): {
        "headline": "The tempo is set higher than you can hold",
        "current_role": (
            "You do your best work at a cadence you can sustain — thinking time, a "
            "finish before the next start. This role runs faster and hotter than "
            "that. High tempo is a legitimate way to run a business, some of the "
            "best work in the world is made that way, and the people who make it "
            "there mostly prefer it. The strain is the distance: a pace that is "
            "someone else's normal is, for you, a pace you are recovering from."
        ),
        "needs_forward": (
            "What to seek: a role whose normal cadence is one you would choose "
            "rather than one you would survive. The question that gets a real "
            "answer is what the last crunch was, how long it ran, and what happened "
            "afterwards — a place with no answer has not noticed that it has one."
        ),
    },

    ("collaboration", UNDER_SUPPLIED): {
        "headline": "You are working more alone than suits you",
        "current_role": (
            "You think best out loud, with someone in the room; that is where your "
            "good ideas actually come from. This role produces work the other way "
            "round: the pieces are split up first and each one belongs to somebody "
            "on their own, with the joining-up left to the end. Individual "
            "ownership is a legitimate way to organise work, it is what a great "
            "many people want, and it costs far less coordination. The strain is "
            "the distance: the thinking you do best has nowhere to happen."
        ),
        "needs_forward": (
            "What to seek: a role where joint work is the default shape of the day "
            "rather than a scheduled exception. Ask how the last significant piece "
            "of work actually got made — who was in the room, and how often — "
            "rather than whether the team would describe itself as collaborative."
        ),
    },

    ("collaboration", OVER_SUPPLIED): {
        "headline": "The day is more shared than you need it to be",
        "current_role": (
            "You do your best work with a stretch of the day that belongs to you "
            "and a piece of work that is yours end to end. This role produces work "
            "in the room: standing sessions, cross-functional groups, decisions "
            "made together. Collective working is a legitimate design and it is how "
            "a lot of complex work stays coherent — the coordination buys something "
            "real. The strain is the distance: the joint time is charged to the "
            "hours you would have used to do the work."
        ),
        "needs_forward": (
            "What to seek: a role with clear individual ownership and a meeting load "
            "you would sign up for. Worth asking how many hours of standing meetings "
            "a week the role carries, and whether anyone owns a deliverable on their "
            "own — the number is more honest than the adjective."
        ),
    },

    ("feedback", UNDER_SUPPLIED): {
        "headline": "You hear less about where you stand than you need",
        "current_role": (
            "You want to know how you are doing, often and straight. This workplace "
            "passes feedback more sparingly and more gently than that. Both are "
            "legitimate feedback cultures — sparing feedback is frequently a "
            "deliberate position about not rattling people, and plenty of strong "
            "places run that way. Where this actually gets settled, though, is with "
            "one person: whoever gives you feedback week to week. That is what the "
            "Manager Decoder is for, and this report does not duplicate it."
        ),
        "needs_forward": (
            "What to seek: not \"a good feedback culture\" — the phrase means nothing "
            "until you know who delivers it. Ask how you would find out you were off "
            "track, and how quickly. The Manager Decoder covers the same ground "
            "properly once you have a manager to profile."
        ),
    },

    ("feedback", OVER_SUPPLIED): {
        "headline": "Feedback arrives more often and more bluntly than you would choose",
        "current_role": (
            "You would rather have feedback considered and well timed than constant. "
            "This workplace runs the other way: frequent, direct, often with other "
            "people present. A blunt, high-frequency feedback culture is a "
            "legitimate one and many people seek it out specifically; it is not "
            "carelessness. Again, though, this dimension is enacted by a person "
            "rather than by a policy, and the protocol for it belongs to the Manager "
            "Decoder rather than here."
        ),
        "needs_forward": (
            "What to seek: a place where critique is timed and private by default, "
            "and say so early rather than absorbing it. What to ask: where feedback "
            "normally gets given — in the room, or afterwards. The Manager Decoder "
            "handles the person-level half once you are in a role."
        ),
    },

    ("innovation", UNDER_SUPPLIED): {
        "headline": "The work refines more than it builds",
        "current_role": (
            "You are at your best inventing: the thing that does not exist yet, the "
            "approach nobody here has tried. This role's work sits on the other side "
            "of that axis — improving, scaling and maintaining what already works. "
            "Refinement is legitimate work, it is most of the work that matters in a "
            "mature business, and it is harder than it looks from outside. The strain "
            "is the distance: the appetite you brought has nothing here to spend "
            "itself on."
        ),
        "needs_forward": (
            "What to seek: a role where something genuinely new is on the roadmap and "
            "somebody is expected to build it. Ask what the team built from scratch in "
            "the last year and what happened to it — \"innovative\" is a claim, a "
            "shipped new thing is evidence."
        ),
    },

    ("innovation", OVER_SUPPLIED): {
        "headline": "More gets rebuilt here than you would rebuild",
        "current_role": (
            "You do your best work making a thing good — taking what exists and "
            "getting it right. This role keeps starting over: new approaches, new "
            "directions, work you finished being discarded. An exploratory stance is "
            "legitimate and it is the only way some problems get solved at all; the "
            "discarded work is the price of finding out. The strain is the distance: "
            "the craft you are best at needs something to stay still long enough to "
            "be improved."
        ),
        "needs_forward": (
            "What to seek: a role with a product or a process that is expected to last "
            "and to get better. Ask what the team has been improving for two years and "
            "how often the direction changes — a place that cannot name a long-running "
            "thing does not have one."
        ),
    },

    ("decision", UNDER_SUPPLIED): {
        "headline": "Calls get made on judgement where you would want evidence",
        "current_role": (
            "You want a decision to rest on something you can point at: a number, a "
            "test, a comparison. This workplace decides more on experience and taste "
            "than that. Judgement-led decision-making is legitimate and frequently "
            "both faster and better, particularly where the data would be thin or "
            "misleading anyway. The strain is the distance: you are asked to commit "
            "to calls whose basis you cannot inspect."
        ),
        "needs_forward": (
            "What to seek: a role where evidence is expected to be produced before a "
            "call rather than after it. Ask how the last significant decision got made "
            "and what was looked at — the answer is either specific or it is not."
        ),
    },

    ("decision", OVER_SUPPLIED): {
        "headline": "Everything needs a number before it can move",
        "current_role": (
            "You decide well on read and experience, and you are used to being right "
            "in ways the figures only confirm later. This workplace wants the analysis "
            "first: metrics, experiments, a written case. Evidence-led "
            "decision-making is legitimate and it is how organisations avoid repeating "
            "expensive instincts; it also selects for a different kind of person. The "
            "strain is the distance: the judgement that is your actual contribution is "
            "not the currency here."
        ),
        "needs_forward": (
            "What to seek: a role where experienced judgement is an accepted basis for "
            "a decision rather than a step before the real one. Ask what someone is "
            "trusted to call without a deck, and at what level that starts."
        ),
    },
}


# ---------------------------------------------------------------------------
# The thirty-six guidance cells
# ---------------------------------------------------------------------------

GUIDANCE_CELLS: dict[tuple[str, str, str], GuidanceCell] = {

    # ── autonomy · under-supplied ────────────────────────────────────────────

    ("autonomy", UNDER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "One piece, your method, for a fortnight",
        "experiment": (
            "Pick one live piece of work — small enough that nobody has to approve "
            "the choice, real enough that it matters — and run the approach yourself "
            "for two weeks. Tell whoever normally sets it that you are taking the "
            "method on this one and will bring back the result plus a checkpoint at "
            "the halfway mark. Bounded and reversible is what makes it easy to agree "
            "to."
        ),
        "steps": [
            "Name the piece before you start, and write down the decisions you "
            "expect to make on it: approach, order, what finished looks like.",
            "Put one checkpoint in the middle and volunteer it. A checkpoint is what "
            "buys the room; an open door is not reassurance, it is a burden.",
            "Keep a two-line log every time you would normally have asked and did "
            "not. That log is the evidence for the next conversation.",
            "At the end of the fortnight bring the result and the log to the same "
            "person, together.",
        ],
        "signal": (
            "How many decisions you made without waiting, and how long the ones you "
            "did route sat before coming back. Both are countable, and both move "
            "quickly once this dimension is set right."
        ),
    },

    ("autonomy", UNDER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "Whoever sets the approach on your work — usually your manager, "
            "sometimes a process owner or a lead who is not your manager at all. A "
            "scheduled one-to-one, not a corridor. Bring a written draft: this is a "
            "proposal, not a request for a discussion."
        ),
        "opening": (
            "Open on the work rather than on how it feels. You are proposing a change "
            "to where decisions sit, and you have already done the thinking about "
            "where each one should sit."
        ),
        "scripts": [
            "I'd like to own the approach on X end to end and come back to you at "
            "the halfway mark. Would that work?",
            "I've written out the decisions on this — the ones I think I should just "
            "make, the ones I'd make and tell you about, and the ones I'd bring to "
            "you first. Can we sanity-check that split?",
            "What would you need to see from me for more of these to sit on my side?",
        ],
        "if_no": (
            "A no that comes with a reason you can work with — a sign-off the client "
            "requires, a regulator, one thing that went sideways before — is a "
            "different answer from a no with nothing behind it, so ask which it is. "
            "Where the constraint is real the useful ask changes: not for the "
            "decision itself, but for the reasoning behind it, so that at least you "
            "are not guessing."
        ),
    },

    ("autonomy", UNDER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "Decision rights are usually set well above the person you would ask. "
            "Sign-off chains exist because of a regulator, a client contract, an "
            "insurer or an incident that predates you, and they are typically the "
            "last thing a company loosens. A place that runs on defined process is "
            "not doing it badly — it is doing something else, and doing it on "
            "purpose."
        ),
        "cost_of_staying": (
            "The cost is specific and it compounds: the judgement you are best at "
            "does not get exercised, so it does not visibly develop, so the case for "
            "handing you more of it gets weaker each year. Staying is a real option — "
            "the work may be good and the people may be worth it — but it is a choice "
            "to spend this stretch of your career on something other than this."
        ),
        "what_it_implies": (
            "If you have asked cleanly, more than once, and the answer stayed the "
            "same for reasons that sit above your manager, you have learned something "
            "rather than failed at something. It means the way this place decides and "
            "the way you work are further apart than a conversation can close, which "
            "is a question about fit and not a failure on either side."
        ),
    },

    # ── autonomy · over-supplied ─────────────────────────────────────────────

    ("autonomy", OVER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "Borrow a brief for two weeks",
        "experiment": (
            "You are not going to get the organisation to start specifying things. "
            "What you can do in a fortnight is manufacture the specification yourself "
            "and get it confirmed cheaply: write the brief you wish you had been "
            "handed, send it, and work to it. The point is not the document — it is "
            "converting an open question into a yes or no somebody can answer in a "
            "minute."
        ),
        "steps": [
            "Before starting anything sizeable, write five lines: what you think "
            "finished looks like, the two calls you are making, the one you are "
            "unsure about, and when you will be done.",
            "Send it and ask for a yes or a correction rather than for a meeting. "
            "Make it faster to reply than to ignore.",
            "Do this for every piece of work for two weeks, including the ones you "
            "would normally just start.",
            "Keep the replies. The pattern of what gets corrected is the direction "
            "you were missing.",
        ],
        "signal": (
            "How long you spend at the start of a task working out what the task is, "
            "and how often finished work gets redirected afterwards. Where the remit "
            "is set right, both are close to zero."
        ),
    },

    ("autonomy", OVER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "Your manager, in a one-to-one, and ideally near a planning boundary — a "
            "quarter, a project kickoff — when defining scope is on the agenda "
            "anyway. Framed as wanting to aim at the right thing, which is true."
        ),
        "opening": (
            "Ask for the priority order and the standard, not for supervision. What "
            "you want is context, and people hand over context far more readily than "
            "they hand over oversight."
        ),
        "scripts": [
            "If I could only finish two of these this quarter, which two would you "
            "pick?",
            "I'd rather aim at the right thing than guess well. Can you tell me what "
            "good looks like on this one?",
            "Who makes the call when something is above my line? I'd like to know "
            "where to take it rather than working it out each time.",
        ],
        "if_no": (
            "Sometimes the honest answer is that nobody knows the priority order, and "
            "that is worth hearing: it tells you the openness is not a philosophy, it "
            "is an absence. If so the ask changes from \"tell me\" to \"here is my "
            "order, correct it if it is wrong\". Proposing beats waiting, and it puts "
            "the correction on a timer."
        ),
    },

    ("autonomy", OVER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "An organisation that has not specified the work usually cannot yet. "
            "Early-stage companies, thin management layers and roles created before "
            "anyone knew what they were for all produce the same blank page. A place "
            "that leaves it blank is not being careless with you; it is running on "
            "the assumption that the people it hires will fill it in, which is a "
            "legitimate bet and a very common one."
        ),
        "cost_of_staying": (
            "The cost is that a large share of your effort goes into deciding rather "
            "than doing, and that share is invisible in every performance "
            "conversation — you are judged on the output, not on the work of working "
            "out what the output should be. Over a long stretch, working without a "
            "defined standard also makes it hard to tell whether you are getting "
            "better."
        ),
        "what_it_implies": (
            "If you have asked for the remit and it genuinely does not exist, the "
            "mismatch is not with a person you can persuade. Some people want the "
            "blank page and some people want a brief, and both are entirely "
            "reasonable things to want. That makes it a question about fit — and, "
            "more often than not, about the stage of company — rather than a failure "
            "on either side."
        ),
    },

    # ── pace · under-supplied ────────────────────────────────────────────────

    ("pace", UNDER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "Put a clock on your own work",
        "experiment": (
            "If the environment will not supply urgency, supply it yourself for two "
            "weeks and find out whether that is enough. Take the three things on your "
            "list with the softest deadlines and give each a hard one, published to "
            "someone. Self-imposed deadlines only work when somebody else knows about "
            "them, which is the whole trick."
        ),
        "steps": [
            "Pick three pieces of work and commit a date on each to a specific "
            "person, out loud.",
            "Cut each one down until the date is genuinely achievable. The goal is "
            "finishing early, not heroics.",
            "Take one thing that normally waits for a scheduled meeting and close it "
            "the same day instead.",
            "At two weeks, count what shipped — and notice whether anyone minded. "
            "Steadiness is often habit rather than requirement.",
        ],
        "signal": (
            "How long a finished piece of work waits before anything happens to it, "
            "and how much of the week goes on waiting rather than working. Those two "
            "numbers describe a tempo better than any adjective does."
        ),
    },

    ("pace", UNDER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "Your manager, and separately whoever owns the queue you are waiting on — "
            "often not the same person, and the second one matters more here. A "
            "one-to-one for the first, a direct message for the second."
        ),
        "opening": (
            "Ask for more work or for faster cycles, not for the company to speed up. "
            "The first is a request anyone can grant; the second is a critique nobody "
            "can act on."
        ),
        "scripts": [
            "I've got more capacity than the current load is using. What else could "
            "I take on?",
            "This is finished on my side and waiting for review — is there a way to "
            "get a faster turnaround on these, even a rougher one?",
            "I work best against real deadlines. Would you be comfortable setting "
            "harder dates on my work than the schedule strictly needs?",
        ],
        "if_no": (
            "If the answer is that the cadence is fixed by something outside — a "
            "release train, a client's calendar, a regulator's clock — then more work "
            "is the only lever left, and there may be a limit on that too. Ask "
            "directly whether more work is available. A no to that is a far bigger "
            "piece of information than a no to a tighter deadline."
        ),
    },

    ("pace", UNDER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "Tempo is mostly structural. It is set by how long the product cycle is, "
            "how often the customer buys, how much review the work legally requires "
            "and how many people have to touch a thing before it is done. A "
            "deliberate cadence is a legitimate way to run a business and usually a "
            "deliberately chosen one — it is how quality survives and how people stay "
            "for a decade. None of that responds to one person wanting to move "
            "faster."
        ),
        "cost_of_staying": (
            "The specific cost is that your capacity goes unused, and unused capacity "
            "is uncomfortable in a way that is hard to name: it reads first as "
            "boredom and then as doubt about whether you are any good. It compounds "
            "quietly, too — fewer cycles means fewer repetitions, and fewer "
            "repetitions means slower development than a peer somewhere quicker."
        ),
        "what_it_implies": (
            "If there is genuinely no more work and no faster cycle, you have found a "
            "structural feature rather than a fixable one. Wanting a quick tempo is "
            "not impatience and running a steady one is not slowness; they are two "
            "different ways for work to be organised. That makes it a question about "
            "fit and not a failure on either side."
        ),
    },

    # ── pace · over-supplied ─────────────────────────────────────────────────

    ("pace", OVER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "Defend one block, for two weeks",
        "experiment": (
            "Rather than asking for the tempo to drop, take one protected block back "
            "and prove it costs nothing. Two hours at the same time each day, or "
            "three mornings a week — whatever you can actually defend — with "
            "everything else running as normal. Two weeks is long enough to show the "
            "work did not suffer and short enough that nobody has to approve a "
            "policy."
        ),
        "steps": [
            "Pick the block and put it in the calendar with a name that says what it "
            "is for, not \"busy\".",
            "Decide in advance what happens when something urgent lands in it: move "
            "the block, do not delete it.",
            "Tell one person it exists, so it is not invisible when someone tries to "
            "book you.",
            "At two weeks, check what actually broke. Usually nothing did, and that "
            "is the argument.",
        ],
        "signal": (
            "How much of the week is reactive rather than planned, and whether there "
            "is any stretch you can count on. That is the observable, and it is the "
            "one that predicts whether a pace is survivable across a year."
        ),
    },

    ("pace", OVER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "Your manager, in a one-to-one — and this is a conversation for a calm "
            "week rather than the worst one. Raised mid-crunch it gets heard as not "
            "coping; raised in a quiet week it gets heard as planning."
        ),
        "opening": (
            "Negotiate over what gets dropped, not over how hard you will work. A "
            "pace conversation that does not name a trade-off just moves the same "
            "load around."
        ),
        "scripts": [
            "I can hold this pace on the things that matter most. Which of these "
            "would you rather I let slip?",
            "I want to keep the quality where it is on X. To do that I need the date "
            "on Y to move — which would you prefer?",
            "I'd like a protected block a few mornings a week for the work that "
            "needs concentration. Nothing else changes.",
        ],
        "if_no": (
            "If the answer is that all of it is urgent, that is an answer about the "
            "company rather than about you, and it is worth taking at face value "
            "rather than testing again. Ask what the quieter part of the year looks "
            "like. If there is not one, this is the tempo rather than a phase."
        ),
    },

    ("pace", OVER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "Pace is usually the last thing a company changes, because it is set by "
            "the business model rather than by the schedule: how the money comes in, "
            "what the customers were promised, what the competition is doing. "
            "High-tempo places tend to know they are high-tempo and to have selected "
            "for people who want that, which is a legitimate way to build a company "
            "and produces some of the best work there is. A quieter version would be "
            "a different company."
        ),
        "cost_of_staying": (
            "The cost of a pace above your sustainable one is not that a given week "
            "is hard; it is that the recovery never quite completes, so the baseline "
            "drifts down while the demand stays flat. It generally shows up outside "
            "work before it shows up in it, which is why it goes unnamed for a long "
            "time."
        ),
        "what_it_implies": (
            "Wanting a cadence you can hold is not a lack of ambition, and running "
            "fast is not carelessness — people are genuinely built for different "
            "tempos and good work gets done at both. If the tempo here is structural "
            "and it sits above yours, that is a question about fit rather than a "
            "failure on either side, and it is better answered deliberately than by "
            "attrition."
        ),
    },

    # ── collaboration · under-supplied ───────────────────────────────────────

    ("collaboration", UNDER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "Two standing conversations",
        "experiment": (
            "You cannot make the organisation collective, but you can manufacture the "
            "two conversations you are missing. For two weeks, set up one recurring "
            "slot with a peer to think out loud about live work, and take one piece "
            "you would normally do alone and do it with someone. Small, cheap, and it "
            "needs nobody's permission."
        ),
        "steps": [
            "Ask one person whose thinking you rate for a standing thirty minutes a "
            "week. Frame it as useful to both of you, because it is.",
            "Take one current problem and ask someone to work through it with you for "
            "an hour, rather than reviewing it at the end.",
            "Say what you are doing and why. \"I think better out loud\" is a "
            "perfectly normal thing to tell a colleague.",
            "After two weeks, notice whether the work got better or just the week "
            "did. Both count, but they mean different things.",
        ],
        "signal": (
            "How many hours a week go into making something jointly, as opposed to "
            "reviewing it or reporting on it. Joint production is the thing here; a "
            "meeting count is not a proxy for it."
        ),
    },

    ("collaboration", UNDER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "Your manager for the shape of the work, and your peers directly for the "
            "rest — most of what you need here is a colleague's yes, not a manager's. "
            "Raise the structural half at a planning point, when work is being carved "
            "up."
        ),
        "opening": (
            "Ask for work to be assigned jointly, not for more meetings. The "
            "distinction matters: everyone is tired of meetings, and almost nobody "
            "objects to two people owning a hard thing together."
        ),
        "scripts": [
            "Could X and I take this one together rather than splitting it? I think "
            "it comes out better and it'd take about the same time.",
            "I do my best thinking with someone in the room. Is there a piece of work "
            "coming up that's shaped for a pair?",
            "Would you be up for a standing half hour to talk through what we're each "
            "working on? I'd get a lot from it.",
        ],
        "if_no": (
            "Where the work genuinely arrives pre-split — a pipeline, a caseload, a "
            "queue — pairing on delivery may not be available at all. The ask then "
            "moves upstream: be in the room when the work is carved up rather than "
            "when it is done. That is a smaller request, and it is often available "
            "when the other one is not."
        ),
    },

    ("collaboration", UNDER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "How much joint work happens is mostly determined by how the work "
            "arrives. Caseloads, queues, territories, individually billed time and "
            "specialised handoffs all produce solo work regardless of how friendly "
            "the team is, and warmth is not the same thing as working together. "
            "Organising work around individual ownership is legitimate, cheaper in "
            "coordination and frequently faster: it is a design, not an oversight."
        ),
        "cost_of_staying": (
            "The cost is not loneliness so much as a narrower ceiling: your ideas only "
            "ever get tested by you, so they improve at the speed of one person. Solo "
            "structures also make it harder for anyone to see how you think, which "
            "matters more than it should when opportunities are handed out."
        ),
        "what_it_implies": (
            "If the work arrives in single-owner pieces and always will, no amount of "
            "goodwill converts it into joint work. Thinking best with people is not "
            "neediness and heads-down structures are not unfriendly; they are two "
            "different ways of producing work. That makes this a question about fit "
            "and not a failure on either side."
        ),
    },

    # ── collaboration · over-supplied ────────────────────────────────────────

    ("collaboration", OVER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "Reclaim a third of the calendar",
        "experiment": (
            "Take two weeks and treat your standing meetings as a budget rather than "
            "a given. Pick the three you would miss least, step back from them in the "
            "cheapest way available — decline, read the notes, send someone else, ask "
            "for the summary — and put the time into a named piece of work you own. "
            "The output is the argument."
        ),
        "steps": [
            "List every recurring meeting and mark each one decide, inform or "
            "produce. The inform ones are the negotiable ones.",
            "Step back from three, and ask for the notes rather than simply "
            "disappearing. The goal is fewer hours, not less visibility.",
            "Block the reclaimed hours immediately or they will be taken back inside "
            "a week.",
            "At two weeks, be able to say what you produced with the time. That is "
            "what makes it permanent.",
        ],
        "signal": (
            "Hours a week in standing meetings, and whether any piece of work is yours "
            "end to end. Where this dimension is set right the second answer is always "
            "yes."
        ),
    },

    ("collaboration", OVER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "Your manager for the standing commitments, and the meeting owners for the "
            "rest — going to the owner directly is usually faster and much less "
            "loaded. Best raised alongside a deliverable you are committing to, so "
            "that the trade is visible."
        ),
        "opening": (
            "Trade time for output rather than asking to be excused. \"I'd get more "
            "done\" is a claim; \"here is what I will deliver with those hours\" is an "
            "offer."
        ),
        "scripts": [
            "I'd like to step back from the Tuesday session and use those hours on X. "
            "I'll read the notes and flag anything I disagree with.",
            "Is there a piece of work I could own end to end? I do my best work with a "
            "clear run at something on my own.",
            "Happy to be in the room for the decisions — could I skip the parts that "
            "are updates?",
        ],
        "if_no": (
            "If attendance is genuinely required — a regulated handover, a "
            "client-facing standing call, a team where presence is how trust gets kept "
            "— then the hours are not recoverable and the ask changes: not fewer "
            "meetings, but one protected stretch and one deliverable that is yours. "
            "Get the second thing even where you cannot get the first."
        ),
    },

    ("collaboration", OVER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "Meeting density is a property of how an organisation coordinates, and it "
            "grows with the number of people who have to agree. Cross-functional "
            "structures, matrix reporting and shared ownership all produce it, and "
            "they produce it deliberately — collective working is how a lot of complex "
            "work stays coherent, and the coordination cost buys something real. It "
            "rarely comes down because one person asks, because the meetings are not "
            "there for one person."
        ),
        "cost_of_staying": (
            "The specific cost is that the work you are best at gets done in the "
            "margins — early, late or in fragments — which is both slower and worse "
            "than doing it in a single run. Over time the deep work migrates out of "
            "the working day entirely, and that arrangement does not hold."
        ),
        "what_it_implies": (
            "Needing solitude to produce is not being difficult, and a collective "
            "operating model is not inefficiency; they are two different theories of "
            "how good work happens and there is plenty of evidence behind both. If the "
            "density here is structural, that is a question about fit rather than a "
            "failure on either side."
        ),
    },

    # ── feedback · under-supplied (deferral: ⚑4, the lever is one person) ─────

    ("feedback", UNDER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "Profile the person, not the policy",
        "experiment": (
            "How much feedback reaches you is settled almost entirely by one person, "
            "so the runnable version of this change lives in the Manager Decoder "
            "rather than here. Profile the manager you actually have and it returns "
            "the specific protocol for this direction — what to ask for, and how to "
            "make it easy to say yes to."
        ),
        "steps": [
            "Complete the Manager Decoder if you have not; it is the same shape of "
            "questionnaire and takes a few minutes.",
            "Work the feedback protocol it returns for your manager rather than a "
            "generic one.",
        ],
        "signal": (
            "How long you can go without knowing whether you are on track, and "
            "whether that read comes to you or has to be inferred. That is the "
            "observable, here and in the Decoder both."
        ),
    },

    ("feedback", UNDER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "One person, not a policy. How often you hear where you stand is set by "
            "your manager week to week, so this is a one-to-one conversation and the "
            "Manager Decoder is where its sentences live — written against your "
            "manager's actual profile rather than against an average."
        ),
        "opening": (
            "Do not open this with the organisation. There is no addressee for \"the "
            "feedback culture here is too sparse\", and there is a very specific one "
            "for \"could I get a five-minute read on this before I take it further?\"."
        ),
        "scripts": [
            "The Manager Decoder carries the literal sentences for this direction — "
            "use those rather than a general script, because what is worth asking for "
            "depends on how your manager already operates.",
        ],
        "if_no": (
            "A manager who cannot give you more of it is frequently a manager who is "
            "not present while you work, which is a setup problem rather than "
            "something being withheld. The Decoder makes that distinction explicitly "
            "and changes the ask accordingly."
        ),
    },

    ("feedback", UNDER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "A sparing feedback culture is usually a real position rather than an "
            "absence, and often a deliberate one about not rattling people. What can "
            "move is the single relationship that supplies most of your feedback, "
            "which is exactly why this dimension hands over to the Manager Decoder. "
            "What rarely moves is the surrounding norm, because it was set well above "
            "whoever you would ask."
        ),
        "cost_of_staying": (
            "Going long stretches without knowing where you stand costs calibration: "
            "you either overestimate or underestimate, and both are expensive when a "
            "promotion or a project assignment is being decided. It also means "
            "corrections arrive late, when they are bigger and harder to hear."
        ),
        "what_it_implies": (
            "If the Decoder's protocol has been worked and the answer is still "
            "silence, the norm is the thing, and it was not built for you or against "
            "you. Wanting frequent, straight feedback is legitimate; running a sparing "
            "culture is legitimate too. That is a question about fit and not a failure "
            "on either side."
        ),
    },

    # ── feedback · over-supplied (deferral) ──────────────────────────────────

    ("feedback", OVER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "Take the delivery question to the Decoder",
        "experiment": (
            "Frequency and bluntness are delivered by a person rather than by a "
            "policy, so the runnable change for this direction lives in the Manager "
            "Decoder. Profile your actual manager and it returns the protocol, "
            "including how to ask for better timing and a smaller audience without "
            "asking for less honesty."
        ),
        "steps": [
            "Complete the Manager Decoder if you have not, and read the feedback "
            "section of the playbook it returns.",
            "Run that protocol rather than a general one — the framing that works "
            "here depends on how your manager already gives feedback.",
        ],
        "signal": (
            "Where and when critique reaches you: in the room or afterwards, "
            "immediately or at a considered moment. Those two observables describe "
            "this direction completely, in this report and in the Decoder alike."
        ),
    },

    ("feedback", OVER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "Your manager, one-to-one, and the Manager Decoder carries the sentences. "
            "This is not an ask for less honesty and should not be raised as one: the "
            "negotiable parts are timing and audience, and the Decoder's version says "
            "so in a way that lands."
        ),
        "opening": (
            "Ask about the setting rather than the substance. \"Not in front of the "
            "team\" is a request most people grant immediately; \"less feedback\" is "
            "one most people hear as something else entirely."
        ),
        "scripts": [
            "The Manager Decoder holds this direction's literal sentences, written "
            "against how your manager actually gives feedback — use those, because "
            "the wrong framing here reads as not wanting to hear it.",
        ],
        "if_no": (
            "Some settings cannot be changed: a review that happens in a group because "
            "the work is reviewed in a group. The Decoder separates the part that is "
            "the setup from the part that is the person, and gives you a different ask "
            "for each."
        ),
    },

    ("feedback", OVER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "A frequent, direct feedback culture is usually a point of pride and often "
            "the thing a place believes makes it good; people are recruited into it on "
            "purpose and many of them specifically wanted it. That makes it one of the "
            "least movable norms in a company, because it is not an accident anyone is "
            "looking to correct. The person-level version can move, which is why the "
            "Manager Decoder is the right tool here; the norm around it generally does "
            "not."
        ),
        "cost_of_staying": (
            "Constant unfiltered critique costs more when you are wired for the "
            "considered kind: the useful part still lands, but it arrives with a tax, "
            "and the tax is paid in the hours afterwards. Over time it can also make "
            "you quieter in exactly the rooms where you would have been most useful."
        ),
        "what_it_implies": (
            "Preferring feedback timed and private is not thin skin, and a blunt "
            "culture is not carelessness; they are two legitimate settings and people "
            "do their best work at both. If the Decoder's protocol has been worked and "
            "the culture around it is still the culture, that is a question about fit "
            "rather than a failure on either side."
        ),
    },

    # ── innovation · under-supplied ──────────────────────────────────────────

    ("innovation", UNDER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "One small new thing, built and shown",
        "experiment": (
            "Rather than arguing for a mandate to invent, spend two weeks building the "
            "smallest real version of something new alongside your actual work, and "
            "show it to someone who could use it. A working thing changes a "
            "conversation that a proposal cannot, and a rough one is enough."
        ),
        "steps": [
            "Pick the smallest genuinely new thing you could get working in two weeks "
            "beside the day job. Smaller than feels worth it.",
            "Build it against a real problem somebody actually has rather than a "
            "hypothetical — the demonstration needs an audience with a stake.",
            "Show it to one person who would benefit before you show it to anyone who "
            "would approve it.",
            "Ask for the next fortnight, not for a programme. New work gets funded in "
            "increments in places like this, or not at all.",
        ],
        "signal": (
            "Whether anything genuinely new was built in the last quarter by anyone, "
            "and whether the person who built it had to do it in the margins. Those "
            "two answers describe an innovation stance more honestly than a strategy "
            "document does."
        ),
    },

    ("innovation", UNDER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "Your manager for the time, and whoever owns the roadmap for the mandate — "
            "often different people, and the second conversation is the one that "
            "counts. Best raised at a planning boundary with something already built "
            "to point at."
        ),
        "opening": (
            "Ask for a bounded slice of time against a named problem, not for "
            "permission to be creative. The first is a scheduling question; the second "
            "sounds like a request to be excused from the work."
        ),
        "scripts": [
            "I've built a rough version of X. Could I have two weeks to get it to "
            "something we could actually try?",
            "Is there anything on the roadmap that hasn't been done before? I'd like "
            "to be on that one.",
            "What would have to be true for us to build something new here rather "
            "than improve what we've got?",
        ],
        "if_no": (
            "A no here is usually about risk rather than about appetite: an installed "
            "base, a certification, a customer who would notice. Ask what the actual "
            "constraint is. If new work only happens elsewhere in the company, that is "
            "the most useful thing this conversation can tell you, and it points at an "
            "internal move rather than a fight."
        ),
    },

    ("innovation", UNDER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "Where a company sits on the create-versus-refine axis is set by its stage "
            "and its obligations rather than by its ambitions. A business with "
            "customers depending on what already exists will keep most of its people "
            "improving it, and that is the correct decision: refinement is legitimate "
            "work, it is most of the work that matters in a mature business, and it is "
            "harder than it looks from outside. Careers-page language about innovation "
            "almost never moves this."
        ),
        "cost_of_staying": (
            "The cost is that the appetite does not go away, it just stops having "
            "anywhere to go — which usually shows up as restlessness and then as "
            "disengagement from work you are perfectly capable of doing well. There is "
            "a skills cost too: building the new thing is a distinct muscle and it "
            "fades without repetitions."
        ),
        "what_it_implies": (
            "If the roadmap is refinement all the way down and the company's "
            "obligations mean it will stay that way, that is structural. Wanting to "
            "build the thing that does not exist is not impatience with good work, and "
            "choosing to refine is not a lack of ambition. It is a question about fit "
            "and not a failure on either side — and often a question about which part "
            "of the company before it is a question about which company."
        ),
    },

    # ── innovation · over-supplied ───────────────────────────────────────────

    ("innovation", OVER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "Make one thing stay still",
        "experiment": (
            "You will not slow the rebuilding down, but you can claim one piece of it "
            "and make it durable. For two weeks take a single component, process or "
            "document that keeps getting redone and get it to a standard where redoing "
            "it stops being the obvious move. Quality is the only argument that "
            "reliably survives a change of direction."
        ),
        "steps": [
            "Pick the thing that gets rebuilt most often and is smallest. Frequency "
            "matters more than size here.",
            "Get it genuinely right: the edge cases, the documentation, the part that "
            "makes the next person leave it alone.",
            "Tell people it is done and what it now handles. Undocumented quality gets "
            "rebuilt like anything else.",
            "At two weeks, check whether it survived the last change of direction. If "
            "it did, that is the pattern to repeat.",
        ],
        "signal": (
            "How long a finished piece of work stays in use before it is replaced, and "
            "how much of last quarter's output is still standing. That is measurable, "
            "and it is the measure that predicts whether craft is worth anything in a "
            "given place."
        ),
    },

    ("innovation", OVER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "Your manager, and whoever keeps setting the new direction if that is "
            "somebody else. A planning conversation rather than a grievance: the ask "
            "is about what gets kept, which is a legitimate planning question."
        ),
        "opening": (
            "Argue for a stability commitment on a named thing, with a date. Arguing "
            "against exploration in general puts you on the wrong side of what the "
            "place believes about itself, and you will lose."
        ),
        "scripts": [
            "Can we agree X is settled for the next quarter? I'd like to make it "
            "properly good rather than adequate-for-now.",
            "I'd rather be the person who makes things solid than the person who "
            "prototypes. Is there a place for that here?",
            "Before we start over on this — what would we have to see to keep it "
            "instead?",
        ],
        "if_no": (
            "If nothing can be committed to for a quarter, that is an honest answer "
            "about the stage the company is at and it is worth believing the first "
            "time. The remaining move is to find the one part of the business that "
            "does have to stay still. There usually is one, and it is often the part "
            "closest to the customers."
        ),
    },

    ("innovation", OVER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "An exploratory stance is usually tied to a company's whole theory of "
            "itself: an early stage, a market that has not settled, or a "
            "founder-level conviction that the current thing is not the answer yet. "
            "Discarded work is the price of finding out, and the people who choose "
            "these places largely know that and accept it. It is a legitimate way to "
            "work and the only way some problems ever get solved; it also rarely "
            "changes short of a change in stage."
        ),
        "cost_of_staying": (
            "The cost is that finished work keeps getting unmade, so the satisfaction "
            "of having made something good never quite arrives. It is also hard to "
            "build a track record out of: work that was thrown away is difficult to "
            "point at later, however good it was."
        ),
        "what_it_implies": (
            "Wanting something to last is not resistance to change, and rebuilding is "
            "not indecision; they are two different bets about where value comes from "
            "and both pay off in the right setting. If the churn here is the strategy "
            "rather than a phase, that is a question about fit rather than a failure "
            "on either side."
        ),
    },

    # ── decision · under-supplied ────────────────────────────────────────────

    ("decision", UNDER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "Bring the number, once",
        "experiment": (
            "Rather than asking for the culture to become evidence-led, attach "
            "evidence to one decision that is about to be made anyway and watch what "
            "happens to it. Two weeks, one decision, one page of actual numbers — "
            "offered as help rather than as a correction."
        ),
        "steps": [
            "Find a decision coming up in the next fortnight where a number is cheaply "
            "available.",
            "Pull it and put it on one page: what the data says, what it does not "
            "cover, and what you would still be deciding on judgement.",
            "Bring it before the decision, not after. Afterwards it reads as "
            "second-guessing; beforehand it reads as contribution.",
            "Watch what happens to it. Used, ignored, or welcomed-then-ignored are "
            "three different results and they mean three different things.",
        ],
        "signal": (
            "Whether anyone can say what the last significant decision rested on, and "
            "whether evidence is expected before a call or assembled after it. Those "
            "two answers place a company on this axis immediately."
        ),
    },

    ("decision", UNDER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "The person making the call, more than your own manager — and in the "
            "meeting where the decision happens rather than afterwards. This dimension "
            "gets negotiated by participation rather than by policy."
        ),
        "opening": (
            "Ask what would change someone's mind. It is a real question rather than a "
            "challenge, and it gets you the decision's actual basis, which is the "
            "thing you are missing."
        ),
        "scripts": [
            "What would we need to see to know this was working? I'd like to get that "
            "in place before we commit.",
            "I'd find it easier to get behind this if I understood what it's resting "
            "on — what are you reading that I'm not?",
            "Could I put the numbers together on this one before we decide? It'd take "
            "me a day.",
        ],
        "if_no": (
            "If the reply is that the data would be thin or misleading, take it "
            "seriously: that is frequently true, and judgement is the correct "
            "instrument when the evidence is poor. The real question is whether it is "
            "a considered position or a habit, and asking what would change their mind "
            "twice usually settles which."
        ),
    },

    ("decision", UNDER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "How a company decides sits close to its self-image, and judgement-led "
            "places usually got that way because judgement worked: a founder whose "
            "instincts built the business, a trade where experience genuinely beats "
            "measurement, a market too fast or too thin to measure well. That is a "
            "legitimate basis for decisions and often the better one — a taste-led "
            "company is not a worse company, it selects for different people. It does "
            "not convert because one person brought a spreadsheet."
        ),
        "cost_of_staying": (
            "The cost is being repeatedly asked to commit to calls whose basis you "
            "cannot inspect, which is uncomfortable in a way that is easy to mistake "
            "for a problem with the individuals involved. It also means your own "
            "strongest contribution — building the case — is not the currency, so it "
            "gets neither recognised nor developed."
        ),
        "what_it_implies": (
            "If the basis for decisions is stable and it is not evidence, you have "
            "learned what kind of place this is rather than failed to improve it. "
            "Wanting to see the case is not distrust, and deciding on experience is "
            "not recklessness. That makes this a question about fit and not a failure "
            "on either side."
        ),
    },

    # ── decision · over-supplied ─────────────────────────────────────────────

    ("decision", OVER_SUPPLIED, CHANGE_IN_PLACE): {
        "experiment_name": "Two weeks of showing your working",
        "experiment": (
            "The lever here is not getting the company to trust instinct; it is "
            "getting your instinct into a form the company already trusts. For two "
            "weeks, take the calls you would normally make on read and spend twenty "
            "minutes each translating them into the local language — a number, a "
            "comparison, a small test — before you put them forward."
        ),
        "steps": [
            "Each time you have a clear view, write the one line of evidence that "
            "would most support it, then go and get that line.",
            "Lead with the conclusion and put the evidence behind it. You are not "
            "becoming an analyst; you are supplying the receipt.",
            "Where nothing measurable exists, propose the cheapest test that would "
            "settle it rather than defending the instinct.",
            "At two weeks, count how many of your calls went through first time. That "
            "number usually moves a long way.",
        ],
        "signal": (
            "How much elapsed time sits between a view being formed and a decision "
            "being made, and what has to be produced in between. That gap is the cost "
            "of this dimension, and it is countable."
        ),
    },

    ("decision", OVER_SUPPLIED, NEGOTIATE): {
        "who_and_where": (
            "Your manager, and whoever sets the bar for what a decision needs. Best "
            "raised as a question about proportionality — which decisions need the "
            "full treatment — rather than about the standard itself."
        ),
        "opening": (
            "Negotiate the threshold, not the principle. Almost nobody will agree that "
            "evidence matters less; most people will happily agree that a reversible "
            "decision does not need a deck."
        ),
        "scripts": [
            "Which of these calls actually needs the full analysis? Some of them are "
            "reversible in a week and I'd rather just make them.",
            "I've got a strong read on this one and the data would take three weeks. "
            "Can we go on the read and check it afterwards?",
            "What's the smallest piece of evidence that would let this move?",
        ],
        "if_no": (
            "Where the bar is set by something external — a regulator, a board, a "
            "customer's procurement process — it is not negotiable at any level you "
            "can reach, and knowing that saves you from asking three more times. The "
            "remaining lever is speed: getting quicker at producing what the process "
            "wants, so the gap between your read and the decision narrows."
        ),
    },

    ("decision", OVER_SUPPLIED, RARELY_MOVES): {
        "why_fixed": (
            "An evidence-led standard is usually load-bearing. It exists because a "
            "decision made on instinct went badly once, or because a regulator, a "
            "board or an investor requires the paper trail. It is a legitimate and "
            "often expensive discipline to maintain, and it is how organisations avoid "
            "repeating costly instincts. Places rarely loosen it, and the ones that do "
            "usually did so after something went wrong."
        ),
        "cost_of_staying": (
            "The cost is latency and the feeling that goes with it: you can see where a "
            "thing is going and you have to wait for the process to arrive at the same "
            "place. Experienced judgement also accumulates no credit in an environment "
            "that does not count it, so the thing you are best at stays invisible in "
            "the record."
        ),
        "what_it_implies": (
            "Deciding well on read is a real capability rather than a shortcut, and "
            "requiring the analysis is not process for its own sake; they select for "
            "different people and both produce good decisions. If the bar here is "
            "structural, that is a question about fit rather than a failure on either "
            "side."
        ),
    },
}


# ---------------------------------------------------------------------------
# Decoder cross-references (⚑4 — link, do not duplicate)
# ---------------------------------------------------------------------------
# Keyed by (dimension, direction), attached at assembly rather than baked into
# a cell, exactly as C-2's CONSTRAINT_NOTES are. Only `autonomy` carries one:
# `feedback` defers wholesale (see DEFERRED_DIMENSIONS) and the remaining four
# dimensions have no Decoder counterpart, so a pointer there would point at
# nothing.

DECODER_CROSSREFS: dict[tuple[str, str], str] = {
    ("autonomy", UNDER_SUPPLIED): (
        "Some of what limits your latitude may be your manager rather than the "
        "role, and the two look identical from inside — an approval you are "
        "waiting on could be a process requirement or a personal preference, and "
        "you cannot tell which from the waiting. The Manager Decoder separates "
        "them: it profiles the manager you actually have and returns the protocol "
        "for that half. If that is the case here, work this cell for the part the "
        "process sets and take the rest there."
    ),
    ("autonomy", OVER_SUPPLIED): (
        "Some of the missing direction may be your manager's rather than the "
        "role's. A remit nobody has written and a manager who would rather not "
        "specify produce exactly the same blank page. The Manager Decoder tells "
        "you which one you are looking at and returns the protocol for the manager "
        "half. If that is the case here, use this cell for the structural part and "
        "take the rest there."
    ),
}


# ---------------------------------------------------------------------------
# Aligned notes (the C-2 MESH_NOTES analogue)
# ---------------------------------------------------------------------------
# The third table, and the smallest. `DIAGNOSES` and `GUIDANCE_CELLS` between
# them cover the two non-aligned buckets; a dimension A-3 calls `aligned` has
# no direction, so it reaches neither, and without this table A-7 renders an
# empty row for every dimension that is fine. C-2 hit the same blank half of
# its own map and answered it with MESH_NOTES: one short note per dimension
# per band, "not protocol cells". Same answer here, same shape, same voice.
#
# Keyed by ``(dimension, band)`` -- eighteen entries -- where band is where the
# person and the environment jointly sit on the 0-1 scale: `low`, `mid` or
# `high`. The band is load-bearing content, not decoration: aligned-low on
# pace is a match on calm and aligned-high is a match on intensity, and those
# are different sentences with different things to watch. A single "you match
# here" note per dimension would be wrong in one of the two registers every
# time.
#
# **No `needs_forward` rendering, deliberately.** These are `str`, not the
# two-rendering `Diagnosis` shape, because there is no needs-forward reading
# of an aligned dimension: every note's second half is an instruction about a
# job the reader currently holds ("worth protecting", "keep an eye on it"),
# and a user reading the needs-forward report answered A-1 in the past tense
# about a role that is over. A-5/A-7 drop aligned dimensions from that
# rendering rather than translating them -- `aligned_note_for`'s docstring
# carries the full reasoning. A test asserts the values stay plain strings, so
# the ruling has to be confronted rather than drifted past.

BAND_LOW = "low"
BAND_MID = "mid"
BAND_HIGH = "high"
BANDS: tuple[str, ...] = (BAND_LOW, BAND_MID, BAND_HIGH)

# Band edges, thirds of A-1's instrument scale. `work_pulse.situation_items`
# anchors every item at 0.1 (low pole) and 0.9 (high pole), so the attainable
# range of a dimension score is [0.1, 0.9] and the thirds of *that* -- not of
# a notional [0, 1] -- are what put a real answer sheet in the middle band.
# `manager_match.decoder.MESH_BAND_LOW_MAX` does the identical arithmetic on
# its own instrument's anchors (0.25 / 0.80); a test asserts the two files
# still agree on the method even though the anchors differ.
_ENV_ANCHOR_LOW = 0.1
_ENV_ANCHOR_HIGH = 0.9
_BAND_WIDTH = (_ENV_ANCHOR_HIGH - _ENV_ANCHOR_LOW) / 3
ALIGNED_BAND_LOW_MAX = _ENV_ANCHOR_LOW + _BAND_WIDTH    # ≈ 0.3667
ALIGNED_BAND_HIGH_MIN = _ENV_ANCHOR_HIGH - _BAND_WIDTH  # ≈ 0.6333

ALIGNED_NOTES: dict[tuple[str, str], str] = {

    ("autonomy", BAND_LOW): (
        "You like knowing the shape of the work before you start, and this role "
        "specifies it. That is a match, and an underrated one — almost none of "
        "your effort goes into working out what you are supposed to be doing. "
        "The thing to watch is drift: the specification usually thins out as "
        "people get more senior, and a role can stop being this one without "
        "anyone announcing that it has."
    ),
    ("autonomy", BAND_MID): (
        "You want the call made for you on some things and left to you on "
        "others, and that is roughly how this role splits it. What is worth "
        "doing here is naming which decisions sit on which side while it is "
        "still going well — that boundary is unwritten in most jobs, and the "
        "moment it gets discovered is usually the moment somebody crosses it."
    ),
    ("autonomy", BAND_HIGH): (
        "You want the route left to you, and this role leaves it. Worth "
        "protecting on purpose: latitude is usually the first of these matches "
        "to go when a team gets busy or something goes wrong, and it goes a "
        "step at a time rather than all at once, which is what makes it easy "
        "to miss until it is gone."
    ),

    ("pace", BAND_LOW): (
        "This is a match on calm. You do your best work at a tempo you can "
        "sustain, and that is the tempo the work arrives at — a finish before "
        "the next start, thinking time that is genuinely there. What is worth "
        "keeping an eye on is that a steady tempo reads from outside as spare "
        "capacity, so the case for working this way is one worth being able to "
        "make out loud."
    ),
    ("pace", BAND_MID): (
        "Neither you nor the work wants a permanent sprint or a flat week, and "
        "the two of you are landing in much the same place. Worth watching what "
        "the busy stretches do to it: a tempo that suits you in an ordinary "
        "month is not the one you are agreeing to in a bad quarter, and it is "
        "the bad quarter that tells you whether this match holds."
    ),
    ("pace", BAND_HIGH): (
        "This is a match on intensity. You want things moving and this work "
        "moves — short turnarounds, a queue that refills, the next thing "
        "already coming. It is a real match and the one with the shortest shelf "
        "life: what you can hold at this tempo moves with everything else going "
        "on in your life, so it is worth revisiting rather than assuming."
    ),

    ("collaboration", BAND_LOW): (
        "You want a piece of work that is yours end to end and a stretch of the "
        "day to do it in, and that is how the work is divided here. A clean "
        "match, and a cheap one — very little of the week goes on coordinating. "
        "What is worth watching is the other side of that: nothing joins your "
        "work up to anyone else's by default, so what you know about the wider "
        "picture is whatever you go and get."
    ),
    ("collaboration", BAND_MID): (
        "You want company for the thinking and quiet for the making, and the "
        "day here divides about that way. The part worth watching is the ratio "
        "rather than the total: it moves with the project and with who else is "
        "on it, and it has usually moved some way before anyone notices it has "
        "moved at all."
    ),
    ("collaboration", BAND_HIGH): (
        "This is a match on working in the room. You think best out loud and "
        "this work is made out loud — standing sessions, decisions taken "
        "together. Worth saying plainly that it suits you, because the people "
        "around you are far more often told the opposite. The one thing to "
        "keep an eye on is that the shared hours still leave the unbroken block "
        "the work itself needs."
    ),

    ("feedback", BAND_LOW): (
        "You would rather have a read on your work when it is considered and "
        "well timed than have a running commentary, and that is how it reaches "
        "you here. The match is real. What it costs is that quiet is "
        "ambiguous — no news does mean no news in a place that runs this way, "
        "but you cannot tell that from inside it, so the habit worth building "
        "is asking at the specific points where you do want a read."
    ),
    ("feedback", BAND_MID): (
        "You want to know where you stand without it being a running "
        "conversation, and that is about the rhythm this place keeps. Worth "
        "holding on to through the busy stretches: feedback is one of the first "
        "things a stretched team stops making time for, and its absence tends "
        "to register only in hindsight."
    ),
    ("feedback", BAND_HIGH): (
        "This is a match on directness. You want to know where you stand, often "
        "and straight, and that is how it circulates here. Worth naming as a "
        "preference rather than assuming it reads as one — a place that runs "
        "blunt usually has people in it working hard to soften, and being told "
        "you do not need that softening is useful information for them."
    ),

    ("innovation", BAND_LOW): (
        "You would rather make a known thing work properly than start a new "
        "one, and that is what the work here is. An underrated match: depth "
        "compounds, and the people who are good at this are generally the ones "
        "holding the thing up. The watch item is your own record — refinement "
        "leaves a fainter trail than invention does, so what you have improved "
        "is worth writing down as you go."
    ),
    ("innovation", BAND_MID): (
        "You want some new ground without the whole job being new ground, and "
        "that is roughly the mix here. The mix is the thing to watch rather "
        "than either half of it: it swings with what is on and what has just "
        "broken, and it can sit at one end for a couple of quarters before "
        "anyone calls that a change."
    ),
    ("innovation", BAND_HIGH): (
        "This is a match on new ground. You want to be making things that did "
        "not exist before and that is what this work is. Worth protecting "
        "deliberately: exploratory work is the easiest thing to reallocate when "
        "something urgent lands, and once the time has gone elsewhere it rarely "
        "comes back on its own."
    ),

    ("decision", BAND_LOW): (
        "You back experience and judgement to make the call, and calls get made "
        "that way here. A real match, and a quick one — a decision does not sit "
        "waiting on a number that was never going to change it. What is worth "
        "doing anyway is leaving a short trace of the reasoning: judgement "
        "travels badly to people who were not in the room, and that is where it "
        "gets questioned."
    ),
    ("decision", BAND_MID): (
        "You want evidence where evidence exists and a judgement call where it "
        "does not, and that is about where decisions land here. The line "
        "between the two is what is worth watching: it is almost never written "
        "down anywhere, and it moves depending on who is in the room and how "
        "the last call of its kind turned out."
    ),
    ("decision", BAND_HIGH): (
        "This is a match on evidence. You want the numbers in front of you "
        "before the call, and that is how a call gets made here. Worth "
        "protecting when the pressure is on: analysis is the first step skipped "
        "once a decision goes urgent, and a place that measures well in an "
        "ordinary week can still end up deciding on instinct in a bad one."
    ),
}


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

class AssembledGuidance(TypedDict):
    """What A-5 hands the report page for one straining dimension."""

    dimension: str
    direction: str
    diagnosis: Diagnosis
    registers: dict[str, GuidanceCell]
    defers_to_decoder: bool
    decoder_crossref: str | None


def _validate(dimension: str, direction: str) -> None:
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension '{dimension}'")
    if direction not in GAP_DIRECTIONS:
        raise ValueError(f"Unknown gap direction '{direction}'")


def direction_for_bucket(bucket: str, direction: str | None = None) -> str | None:
    """One A-3 report entry's `(bucket, direction)` → this file's direction
    vocabulary, or `None` where `aligned` shows no guidance.

    `direction` must come from the same report entry the bucket did
    (`work_pulse.situation.build_situation_report`'s own `direction` field) —
    see the module docstring's "How A-3/A-5 look this up" for why a bucket
    alone no longer determines it since the 2026-09-10 rename.
    """
    if bucket not in BUCKET_TO_DIRECTION:
        raise ValueError(f"Unknown gap bucket '{bucket}'")
    if not BUCKET_TO_DIRECTION[bucket]:
        if direction is not None:
            raise ValueError(f"'{bucket}' bucket carries no direction")
        return None
    if direction not in _DIRECTION_FROM_GAP_ENGINE:
        raise ValueError(f"Unknown gap direction '{direction}'")
    return _DIRECTION_FROM_GAP_ENGINE[direction]


def is_deferred(dimension: str) -> bool:
    """True where the lever is a person and the protocol belongs to C-2."""
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension '{dimension}'")
    return dimension in DEFERRED_DIMENSIONS


def diagnosis_for(dimension: str, direction: str) -> Diagnosis:
    """The situation in both renderings. A-5 picks one by `career_status`."""
    _validate(dimension, direction)
    return dict(DIAGNOSES[(dimension, direction)])  # type: ignore[return-value]


def band_for_env_score(env_score: float) -> str:
    """Which third of A-1's scale a dimension sits in: `low`, `mid` or `high`.

    Takes the environment score alone, and deliberately not the midpoint of
    the pair the way `manager_match.decoder._mesh_band` does. Two reasons, and
    the second is the binding one:

      * It is only ever called on an `aligned` dimension, where
        ``|env - person| < 0.15`` by construction
        (`work_pulse.situation.ALIGNED_THRESHOLDS`), so the environment score
        already locates the pair to inside a fifth of a band. The pair really
        does sit here.
      * `env_score` is the *only* one of the two numbers D-15 lets out of A-3
        (`SituationDimensionReport` carries `env_score` and no
        `person_score`, on purpose). Selecting content off the person-side
        number would put a person-side quantity back into the render path
        through the side door, for a three-valued gain. C-2 has no such rule
        to keep, which is why its own band function may take both.

    The trade is a near-boundary disagreement with the midpoint method — an
    aligned pair straddling 0.3667 or 0.6333 can band one step differently
    from the way C-2 would band it. Both notes are true of that pair; neither
    is worth a D-15 exception.
    """
    if isinstance(env_score, bool) or not isinstance(env_score, (int, float)):
        raise ValueError(f"env_score is not a number: {env_score!r}")
    if not 0.0 <= env_score <= 1.0:
        raise ValueError(f"env_score out of [0, 1]: {env_score}")
    if env_score <= ALIGNED_BAND_LOW_MAX:
        return BAND_LOW
    if env_score >= ALIGNED_BAND_HIGH_MIN:
        return BAND_HIGH
    return BAND_MID


def aligned_note_for(dimension: str, env_score: float) -> str:
    """The note for a dimension A-3 bucketed `aligned`, banded by `env_score`.

    Total over `DIMENSIONS` × every score in [0, 1], so A-7 cannot ask for a
    note that does not exist: pass the report entry's own `dimension` and
    `env_score` and a string always comes back. The caller checks the bucket —
    this file has no thresholds and does not learn any (see the module
    docstring's last line) — exactly as C-2's `_entry` checks `MESH` before
    reaching `MESH_NOTES`.

    **Not called in the needs-forward rendering.** Who reaches that rendering
    with environment scores at all is `between_jobs`, plus a `first_job` user
    who does have a most-recent role to describe — a `first_job` user with no
    employment history skips the environment form entirely
    (SITUATION_ITEMS_BIAS_REVIEW.md Finding 7, ratified 2026-09-10), so no
    scores and no aligned dimensions exist for them and the question does not
    arise. For the ones who do reach it, A-1 was answered in the past tense
    about a role that is over, and three things follow:

      * Every note's second half instructs someone who still holds the job.
        "Worth protecting on purpose" has no referent once the job is gone.
      * The match it names is in the past tense too. Calling it a match, in a
        report the reader is using to choose what comes next, reads as a
        present-tense fact about their situation, and it is not one.
      * Turned forward it becomes "seek this again", which is an inference the
        report cannot support. An aligned dimension says the *fit* on that
        axis was fine; it says nothing about why the reader left, and the
        report cannot see that reason. A `needs_forward` diagnosis is safe
        because a gap survives the move — it is a thing to look for in the
        next place. An alignment does not survive it.

    So A-5/A-7 drop aligned dimensions from that rendering rather than
    rewording them, which is why `ALIGNED_NOTES` has no `needs_forward` twin
    the way `DIAGNOSES` does. If the section needs something in place of the
    dropped rows, it is one line about the set of them, written once at A-7 —
    not six notes, and not a per-dimension row with nothing in it.
    """
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension '{dimension}'")
    return ALIGNED_NOTES[(dimension, band_for_env_score(env_score))]


def guidance_for(dimension: str, direction: str) -> AssembledGuidance:
    """Deterministic lookup — the whole of A-6's request-path behaviour.

    Returns copies throughout so a caller mutating the response cannot reach
    back into the module-level content.
    """
    _validate(dimension, direction)

    registers: dict[str, GuidanceCell] = {}
    for register in REGISTERS:
        cell = GUIDANCE_CELLS[(dimension, direction, register)]
        copied = dict(cell)
        for field, value in copied.items():
            if isinstance(value, list):
                copied[field] = list(value)
        registers[register] = copied  # type: ignore[assignment]

    return {
        "dimension": dimension,
        "direction": direction,
        "diagnosis": diagnosis_for(dimension, direction),
        "registers": registers,
        "defers_to_decoder": is_deferred(dimension),
        "decoder_crossref": DECODER_CROSSREFS.get((dimension, direction)),
    }
