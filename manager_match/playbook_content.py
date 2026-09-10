"""Static playbook content for the Manager Decoder (BUILD_PLAN C-2, ruling ⚑1).

Template-first by decision: these cells are drafted once, human-reviewed, and
served by deterministic lookup. Nothing here is generated per user and nothing
here reaches a request path that calls a provider. `decoder.py` holds the diff
rule and the assembly; this file holds only the words, so the content review has
a single surface.

Keys are `(dimension, direction, severity)`:
  * dimension — the four shared by `questions.py` and `manager_profile.py`
  * direction — `over_supplied` (the manager runs higher on this dimension than
    the user needs) or `under_supplied` (lower than the user needs)
  * severity  — `notable` or `acute`, set by the per-dimension thresholds in
    `decoder.py`

Four dimensions × two directions × two severity bands = the sixteen cells.

Tone rules, binding, from `MANAGER_PROFILE_ITEMS_BIAS_REVIEW.md` (Findings 4
and 6) and PRODUCT_DECISIONS §6:

  * **Fit, not fault.** Both the user's need and the manager's style are
    legitimate positions a thoughtful person could hold. The grind is the
    distance between them, never the person on either end.
  * **Behavior, not character.** Cells describe what the manager does and what
    it costs the user. No cell characterizes the manager as a person, and no
    cell contains a trait word — including a trait word introduced only to deny
    it, which leaves the word in the reader's head either way.
  * **The environment may be the cause.** Finding 4: sign-offs, fixed
    sequences, a manager who is not present while the work happens, and
    narrowly-scoped roles are set by the industry, not chosen by the manager.
    `CONSTRAINT_NOTES` carries that hedge on the three under-supplied
    directions where the finding applies.
  * **Acute is a bigger ask, not a louder complaint.** The acute band escalates
    what the user asks for — a working arrangement rather than a favour — and
    ends by naming the fit question honestly, because a user who asks well
    twice and sees nothing move is owed that.
"""
from __future__ import annotations

from typing import TypedDict


class ProtocolCell(TypedDict):
    """One grind protocol. `constraint_note` is attached at assembly time."""

    headline: str
    why: str
    ask: str
    agenda: list[str]
    scripts: list[str]


PRIVACY_NOTICE: str = (
    "This playbook is yours. It was built from two things you told us: what you "
    "need from a manager, and your own read on how your manager works. It is a "
    "private working note, not an assessment of them. Nobody at your company can "
    "see it, your manager is never shown it and is never told it exists, and "
    "nothing in it is shared with anyone. It describes the fit between two ways "
    "of working, both of which are legitimate — it is not a verdict on either "
    "of you."
)


# ---------------------------------------------------------------------------
# The sixteen protocol cells
# ---------------------------------------------------------------------------

PROTOCOL_CELLS: dict[tuple[str, str, str], ProtocolCell] = {

    # ── autonomy ─────────────────────────────────────────────────────────────
    # High pole: the manager grants latitude over goal, method and timing.

    ("autonomy", "under_supplied", "notable"): {
        "headline": "You want more room than the work currently gives you",
        "why": (
            "You do your best work when someone sets the outcome and leaves the "
            "route to you. Your manager works closer in than that — weighing in "
            "on method, on order, on when things happen. Both are real ways to "
            "run work, and plenty of strong managers run the close-in version on "
            "purpose. The grind is the distance between them: the part of the job "
            "you are best at, deciding how, is the part that keeps getting decided "
            "before you reach it. It tends to show up as flatness rather than as "
            "conflict, which is why it can run for a long time unnamed."
        ),
        "ask": (
            "Ask for method latitude on one named piece of work rather than in "
            "general. Pick something live, propose that you own the approach end "
            "to end, and offer a checkpoint instead of an open door. Bounded and "
            "reversible is what makes it easy to say yes to — and a yes on one "
            "piece of work is worth more than agreement in principle."
        ),
        "agenda": [
            "One deliverable where you would own the method — which one, what "
            "you would bring back, and when.",
            "What your manager would need to see to stay comfortable: a "
            "checkpoint, an early warning on risk, a clear \"come to me if\".",
            "What sits behind the current closeness. It is often one thing that "
            "went sideways once rather than a standing view of you.",
        ],
        "scripts": [
            "I'd like to run the approach on X myself and come back to you at the "
            "halfway mark with where it's got to — would that work?",
            "I work best when I know the outcome you want and can find my own "
            "route to it. Could we try that on X and see how it goes?",
            "What would you want to see from me along the way for that to feel "
            "safe on your side?",
        ],
    },

    ("autonomy", "under_supplied", "acute"): {
        "headline": "The route, the order and the timing all arrive decided",
        "why": (
            "This is the wide version of the same mismatch. What you need is the "
            "outcome and then room; what the work gives you is the method, the "
            "sequence and the timing already settled. Close direction is right "
            "for some work and some people, and it is a demanding way to manage "
            "rather than an easy one. At this distance, though, it stops being a "
            "preference you can absorb quietly: decisions wait on someone else's "
            "availability, ownership thins out, and a real share of your effort "
            "goes into getting clearance rather than getting the result."
        ),
        "ask": (
            "Ask for a change to how the work is set up, not a favour on one "
            "task. Propose an explicit three-tier split — what you decide alone, "
            "what you decide and report, what you bring first — with your own "
            "draft of where each decision sits. Run it for a fixed period and put "
            "a review date on it. If you make that ask cleanly and nothing moves "
            "across a couple of cycles, that is worth knowing rather than "
            "repeating: it means the way this role is run and the way you work "
            "are further apart than a conversation can close, which is a question "
            "about fit and not a failure on either side."
        ),
        "agenda": [
            "Your draft of the three-tier split, decision by decision, brought "
            "already written rather than worked out in the room.",
            "A trial length and a review date — you are proposing an experiment, "
            "not a permanent handover.",
            "What would have to be true for more decisions to move up a tier.",
            "What you will do to make it safe: what you flag, and how fast.",
        ],
        "scripts": [
            "I'd like to try something for the next six weeks — I take these "
            "calls myself, tell you about these ones after, and bring these to "
            "you first. Can we work out where the lines should sit?",
            "I don't think either of us is running this wrong. I want to find the "
            "version that still gets you what you need to see and gets me room to "
            "move.",
            "If the trial goes well, what's the next step? And if it isn't "
            "working, what would show us that early?",
        ],
    },

    ("autonomy", "over_supplied", "notable"): {
        "headline": "More room than you actually want",
        "why": (
            "You do better with the ground marked out — a clear picture of what "
            "good looks like, a sense of the order, someone to think with when "
            "you are stuck. Your manager runs hands-off: outcome set, everything "
            "after it yours. That is a deliberate way to manage and it is what a "
            "lot of people most want. For you it lands as being left to guess, "
            "and the cost turns up as rework and second-guessing rather than as "
            "freedom — you can spend a great deal of energy building the brief "
            "you were hoping to be handed."
        ),
        "ask": (
            "Ask for definition, not supervision. Make that distinction out loud, "
            "because \"I'd like more direction\" is easily heard as \"I want to be "
            "checked on\" and will get you the opposite of what you want. What you "
            "are after is the target described more sharply up front and a "
            "standing slot to think out loud in — neither of which takes any "
            "latitude away from you."
        ),
        "agenda": [
            "What \"done well\" looks like on your current work, described "
            "concretely enough to aim at.",
            "A short standing slot to talk through work in progress — you bring "
            "the agenda, so it reads as thinking time rather than a check-in.",
            "Whether an example of this work done well already exists somewhere "
            "you could look at.",
        ],
        "scripts": [
            "Before I start on X, can we spend ten minutes on what a good version "
            "of this looks like to you? I'd rather aim at it than approximate it.",
            "I'm not asking you to check my work — I just think better with "
            "someone in the room. Could we keep a short weekly slot where I bring "
            "what I'm chewing on?",
            "Is there a version of this that's been done well before that I could "
            "look at?",
        ],
    },

    ("autonomy", "over_supplied", "acute"): {
        "headline": "You are building your own brief every time",
        "why": (
            "The gap here is wide. You want the shape of the work set before you "
            "start; the way it currently runs, almost all of that is yours to "
            "invent. Hands-off management is a real style and it works well for "
            "people who want the blank page — it usually comes from trust in the "
            "person rather than from distance. But at this distance you are doing "
            "two jobs: defining the work and then doing it. That surfaces as slow "
            "starts, as work redone once expectations finally become visible, and "
            "as a quiet sense that you are being tested when you are actually "
            "just under-briefed."
        ),
        "ask": (
            "Ask for structure to be built into the work rather than requested "
            "each time. A written definition of done for your main pieces, a "
            "regular slot with a fixed shape, and an agreed way to raise "
            "something early. Ask for it as a standing arrangement so you are not "
            "spending credibility on the same request over and over. If you ask "
            "and the structure does not materialise, that is real information: "
            "some roles are built around people who want the blank page, and "
            "knowing that about this one is worth more to you than asking again."
        ),
        "agenda": [
            "A written definition of done for your two or three main pieces of "
            "work — offer to draft it and have your manager mark it up.",
            "A recurring slot with a fixed shape: what is on track, what is "
            "ambiguous, what you need decided.",
            "An agreed route for raising something early without it reading as "
            "escalation.",
            "Which parts of the work genuinely have no defined right answer — so "
            "you stop hunting for one that was never there.",
        ],
        "scripts": [
            "I'd like to write down what done looks like for X and have you mark "
            "it up. It'd save us both the round trip later.",
            "I do my best work when the target is clear and then I'm left alone. "
            "Right now a lot of my time goes into working out the target. Can we "
            "fix that end of it?",
            "Some of these calls may genuinely be mine to make — can we go "
            "through which ones are, so I stop waiting on an answer that isn't "
            "coming?",
        ],
    },

    # ── feedback_style ───────────────────────────────────────────────────────
    # High pole: the manager gives frequent, immediate, unsoftened feedback.

    ("feedback_style", "under_supplied", "notable"): {
        "headline": "You want to know where you stand more often than you're told",
        "why": (
            "You calibrate off feedback — fast, plain, and often enough to steer "
            "by. Your manager comments sparingly, saves it for the right moment, "
            "or leads with the softer framing. Neither is wrong: measured "
            "feedback keeps people from being managed by every passing reaction, "
            "and a lot of people need it delivered exactly that way. The grind is "
            "that you are left filling the silence yourself, and most people fill "
            "it with the least generous reading available. That is the real cost "
            "here — not the missing praise, but the guessing."
        ),
        "ask": (
            "Ask for cadence and directness separately, because they are "
            "different requests and one is much easier to grant than the other. "
            "Cadence first: a short regular moment for how the work is landing. "
            "Then directness: say plainly that you would rather have the "
            "unsoftened version and that it does not knock you off course."
        ),
        "agenda": [
            "A short, regular \"how is this landing\" moment, kept separate from "
            "anything about status or delivery.",
            "A direct statement that you want the blunt version — with an example "
            "of hard feedback you took well, so it is credible.",
            "One current piece of work you would like an honest read on now.",
        ],
        "scripts": [
            "I'd find it useful to hear how my work's landing more often — even a "
            "couple of minutes, even when the answer is that it's fine.",
            "You don't have to soften things for me. I'd rather have it straight "
            "and early than tidy and late.",
            "Can I get your honest read on X? Including what you'd have done "
            "differently.",
        ],
    },

    ("feedback_style", "under_supplied", "acute"): {
        "headline": "You are working without a signal",
        "why": (
            "This is the wide version. You need frequent, direct, unhedged "
            "feedback to steer by; what reaches you is rare, carefully framed, or "
            "only arrives when something has gone wrong. Both ends of this are "
            "legitimate — some managers hold back on purpose so that what they do "
            "say carries weight, and some people are undone by a running "
            "commentary. At this distance, though, you are navigating on your own "
            "estimate of how you are doing, and that estimate drifts. This is the "
            "gap that produces surprises at review time, in both directions."
        ),
        "ask": (
            "Ask for a mechanism, not a change of temperament. People rarely "
            "change how much feedback they naturally give, but almost anyone will "
            "fill in a structure that already exists. Propose a specific "
            "recurring form — a standing fifteen minutes, three questions you ask "
            "every time, a written note you send that they mark up — and take "
            "responsibility for running it yourself. If it gets agreed and then "
            "does not happen twice running, that is something to act on rather "
            "than to keep waiting through."
        ),
        "agenda": [
            "The mechanism itself: how often, how long, what you bring, what you "
            "are asking them for.",
            "Three standing questions you will ask every time — what is working, "
            "what is not, what you would change.",
            "Where you currently think you stand, said out loud, so any gap "
            "between your read and theirs surfaces now rather than at review.",
            "Your explicit permission for the blunt version, in your own words.",
        ],
        "scripts": [
            "I'd like to set up fifteen minutes every couple of weeks where I "
            "bring you something and you tell me what you actually think of it. "
            "I'll set it up and I'll bring the questions.",
            "Here's my own read on how I'm doing — where does that match yours, "
            "and where doesn't it?",
            "I can take it straight. If something's off, I'd much rather hear it "
            "in the moment than find out later that it had been building.",
        ],
    },

    ("feedback_style", "over_supplied", "notable"): {
        "headline": "More commentary, and blunter, than you work well with",
        "why": (
            "You take feedback best when it comes at a considered moment with the "
            "reasoning attached — the whole picture once, rather than a running "
            "stream of reactions. Your manager works the other way: says it as "
            "they see it, in the moment, without much cushioning. That is a "
            "legitimate style and usually a sign of taking your work seriously "
            "enough to react to it. The grind is that in-flight commentary lands "
            "on you as course-correction when you had not finished setting the "
            "course, and unhedged delivery reads as a verdict when it was meant "
            "as a note."
        ),
        "ask": (
            "Ask for timing and framing, not for less honesty. Asking someone to "
            "hold back rarely goes well and is not really what you want anyway. "
            "What works is naming the point in a piece of work where input helps, "
            "and asking for the weight of a comment to come with it — whether "
            "this is change course or just noticing."
        ),
        "agenda": [
            "When in a piece of work you want input — the point at which it is "
            "useful rather than disruptive.",
            "A request that in-flight notes get flagged as notes: is this \"stop "
            "and change this\" or \"noting for later\"?",
            "How you would like the larger pieces of feedback delivered — sat "
            "down, with the reasoning, rather than in passing.",
        ],
        "scripts": [
            "Can I come to you at the draft stage rather than while I'm still "
            "assembling it? I take it in much better once the shape's there.",
            "When you flag something mid-task, it helps me to know whether it's "
            "\"stop and change this\" or \"noting for later\".",
            "I do want the honest version — I just take it in better when we sit "
            "down with it than when it comes past the desk.",
        ],
    },

    ("feedback_style", "over_supplied", "acute"): {
        "headline": "The commentary is constant and it's drowning the signal",
        "why": (
            "The distance here is wide. You need feedback bundled, timed and "
            "framed; what you get is frequent, immediate and unsoftened. Neither "
            "of those is the wrong way round — running feedback is how a lot of "
            "very good managers keep work on track, and it suits people who want "
            "to know instantly. But at this distance the volume becomes the "
            "problem in itself: everything arrives at the same weight, so the "
            "significant note is indistinguishable from the passing one, and the "
            "effect is that you stop starting things until you are sure of them. "
            "That is a cost to the work, not only to how you feel about it."
        ),
        "ask": (
            "Ask for triage and for a container. Triage: a way of marking which "
            "notes are directional and which are thinking out loud. Container: a "
            "regular slot where substantial feedback gets given properly, so it "
            "does not all have to happen in flight. Frame it as wanting to act on "
            "the important things rather than as wanting fewer of them — that is "
            "both truer and far easier to hear. If you ask twice and nothing "
            "shifts, it is fair to conclude that this is simply how this manager "
            "works, and to weigh whether it is a way of working you can do your "
            "best inside."
        ),
        "agenda": [
            "A shared shorthand for weight — \"this one matters\" against "
            "\"thinking aloud\" — so you can act on the right ones.",
            "A standing slot for substantive feedback, so less of it has to "
            "happen mid-task.",
            "The point in your process where input helps and the point where it "
            "costs, named on a specific real piece of work.",
            "What you will do in return: bring things earlier, so waiting for "
            "input never looks like avoiding it.",
        ],
        "scripts": [
            "I want to act on the things that matter most, and right now I can't "
            "always tell which those are. Could you flag the ones you'd want me "
            "to change course on?",
            "Could we hold the bigger pieces of this for our one-to-one? I'll "
            "bring the work, and I'd rather go through it properly than catch it "
            "in passing.",
            "I'm not asking you to hold back. I'm asking for it in a shape I can "
            "actually do something with.",
        ],
    },

    # ── relationship ─────────────────────────────────────────────────────────
    # High pole: the manager engages with and advocates for the person, and
    # adapts to them individually — not only to the output.

    ("relationship", "under_supplied", "notable"): {
        "headline": "You want to be known here, and the relationship runs professional",
        "why": (
            "You do better when your manager knows something about who you are "
            "and will speak for you when you are not in the room. Your manager "
            "keeps the relationship squarely on the work — no intrusion, no "
            "assumptions, your record left to make its own case. That is a "
            "considered position rather than an absence of interest: many "
            "managers hold that line deliberately, out of respect for privacy and "
            "to keep things even across a team. The grind is that the things you "
            "would want them to know — what you are stretching toward, what is "
            "hard at the moment, what you would want argued for on your behalf — "
            "have no natural door to arrive through."
        ),
        "ask": (
            "Two asks, and it helps to keep them apart. The advocacy one is "
            "concrete and easy: make sure your manager knows what you want to be "
            "put forward for. The personal one has to be offered rather than "
            "requested — you cannot ask someone to take an interest, but you can "
            "give them something to take an interest in, and most managers meet "
            "that halfway."
        ),
        "agenda": [
            "What you want to be considered for, said explicitly, so it can be "
            "repeated in rooms you are not in.",
            "A short account of what you are working toward beyond this job.",
            "One thing about how you are doing at the moment that you are "
            "content to share — offered, not extracted.",
        ],
        "scripts": [
            "When my name comes up for something like X, I'd want to be in that "
            "conversation. Can I make sure you know what I'm aiming at?",
            "You don't have to manage this for me — I just want you to know it, "
            "so it's there when it's relevant.",
            "Here's what's going on for me at the moment. For context, not for "
            "action.",
        ],
    },

    ("relationship", "under_supplied", "acute"): {
        "headline": "You are a set of outputs here, and you need to be a person",
        "why": (
            "This is the wide version of the same distance. What you need is a "
            "manager who knows you, adapts to you, and puts your name forward; "
            "what you have is a relationship conducted entirely through the work. "
            "Running an even, boundaried, output-focused relationship with "
            "everyone is a real philosophy, held on purpose — some managers hold "
            "it precisely because they think treating people differently does the "
            "greater harm. But at this distance the effects are practical rather "
            "than only emotional: nobody is carrying your case into the rooms "
            "where those cases get made, and the read on you across the org is "
            "whatever your last visible piece of work suggested."
        ),
        "ask": (
            "Make the advocacy ask directly and in the open, because that is the "
            "half you can actually move. Say what you want to be put forward for "
            "and what you would want said about you. Then make yourself legible "
            "in ways that do not depend on the relationship warming up — a short "
            "written update they can forward, a standing record of what you have "
            "delivered — so the case for you exists whether or not someone is "
            "making it out loud. If the closeness never comes, that is likely how "
            "this manager works with everyone, and the live question becomes "
            "where else in the org you get that — a mentor, a skip-level, a peer "
            "— rather than how to change them."
        ),
        "agenda": [
            "The specific things you want to be put forward for, named, with the "
            "reasons you would give for them.",
            "A short regular written update you will send that your manager can "
            "pass on unedited.",
            "Who else, besides your manager, should know what you are working on.",
            "What you would want said about you if you were not in the room — "
            "said plainly, once.",
        ],
        "scripts": [
            "I'd like you to know what I want next, so that when it comes up you "
            "can say it. Here it is.",
            "I'll send you a short note each month with what I've shipped — use "
            "it however's useful, including forwarding it.",
            "Is there anyone else here I should be making sure knows what I'm "
            "working on?",
        ],
    },

    ("relationship", "over_supplied", "notable"): {
        "headline": "More personal engagement than you want at work",
        "why": (
            "You would rather the relationship stayed on the work — clean lines, "
            "your record making your case, your life outside kept outside unless "
            "you bring it in. Your manager works closer than that: asks how you "
            "are doing, adapts to people individually, gets involved on your "
            "behalf. That is a warm and entirely legitimate way to manage, and "
            "many people would be glad of it. The grind is that closeness offered "
            "is never neutral — declining it can look like a problem where there "
            "is none, so you end up either performing an openness you do not want "
            "or seeming remote for no reason you can name."
        ),
        "ask": (
            "Redirect rather than refuse. The useful move is to give your manager "
            "a clear, positive account of how you like to work, so the distance "
            "reads as a preference rather than as a withdrawal. And where they "
            "want to get involved on your behalf, point that energy somewhere you "
            "actually want it — that is advocacy, and it is worth having even "
            "when the personal warmth is not."
        ),
        "agenda": [
            "How you like to work, stated as a preference rather than as a "
            "boundary — \"I keep work and home fairly separate\" lands very "
            "differently from \"I'd rather not discuss it\".",
            "Where their involvement on your behalf would genuinely help — so the "
            "engagement has somewhere useful to go.",
            "Anything currently being read as a signal that is not one.",
        ],
        "scripts": [
            "I tend to keep work and the rest of my life fairly separate. Nothing "
            "is wrong — that's just how I run.",
            "The place I'd really value your backing is X. That's worth more to "
            "me than the check-ins.",
            "I'm good, honestly. If something were up I'd tell you.",
        ],
    },

    ("relationship", "over_supplied", "acute"): {
        "headline": "The relationship is closer than you want it to be",
        "why": (
            "The gap here is wide. You want a professional relationship with "
            "clear edges; what is on offer is a personal one — regular interest "
            "in how you are doing, individual adaptation, active involvement in "
            "things concerning you. The closer style comes from genuine "
            "investment and it is what a great many people most want from a "
            "manager. At this distance, though, the mismatch has visible costs: "
            "warmth you do not reciprocate tends to get read as something being "
            "wrong, so you spend energy managing an impression instead of doing "
            "the work, and information about you travels further than you would "
            "choose."
        ),
        "ask": (
            "Name the preference explicitly and early, once, and pair it with "
            "something to put in its place. Unstated distance gets interpreted; "
            "stated distance is usually just accepted. Say plainly that you keep "
            "work and personal separate, that it is not about them, and that what "
            "you would value is professional backing. Then give the relationship "
            "a real professional shape — a regular slot with a fixed agenda — so "
            "there is a defined channel and less pull toward the informal one. If "
            "the closeness continues after you have named it clearly, the "
            "mismatch is a genuine one about how this manager relates to people, "
            "and it belongs in your thinking about whether this is the right "
            "manager for you to work under."
        ),
        "agenda": [
            "The preference itself, said once, plainly, with the explicit note "
            "that it is not personal.",
            "A regular slot with a fixed agenda, so the relationship has a "
            "professional channel that is actually working.",
            "What you do want from them — backing, air cover, visibility — named "
            "specifically.",
            "Anything you have shared that you would like kept where it was said.",
        ],
        "scripts": [
            "I want to say this once so it doesn't get misread: I keep work and "
            "personal life pretty separate. It isn't about you, and it doesn't "
            "mean anything's wrong.",
            "What I'd really value from you is backing when decisions about my "
            "work get made. That matters to me much more than the personal side.",
            "I'd rather keep that one between us, if that's alright.",
        ],
    },

    # ── growth_focus ─────────────────────────────────────────────────────────
    # High pole: the manager invests in what the user becomes, not only in what
    # they deliver.

    ("growth_focus", "under_supplied", "notable"): {
        "headline": "You want to be developed and you're being managed",
        "why": (
            "You are motivated by getting better — stretch work, ideas pushed "
            "back on, someone paying attention to where you are heading after "
            "this job. Your manager focuses on the work in front of you: the job, "
            "done well, now. That is a defensible way to manage and often a "
            "respectful one, treating your development as yours to own rather "
            "than something done to you. The grind is that your growth then "
            "depends entirely on what you can arrange for yourself, while the "
            "things that would move you fastest — a stretch assignment, a hard "
            "conversation about your thinking, a word in the right room — are "
            "mostly in your manager's gift rather than in yours."
        ),
        "ask": (
            "Bring the development ask as a work ask. \"I want to grow\" is hard "
            "to act on; \"I'd like to take X, which I haven't done before\" is a "
            "staffing decision your manager can actually make. Pick one concrete "
            "stretch and ask for it. Then ask for the harder version of their "
            "attention: that they push back on your thinking rather than approve "
            "it."
        ),
        "agenda": [
            "One specific piece of upcoming work you would like to take that "
            "would stretch you, and why you think you could carry it.",
            "A request that they argue with your ideas rather than accept them — "
            "said explicitly, because most people will not unless invited.",
            "Where they think you are weakest. Ask directly; it is the most "
            "useful question available to you.",
        ],
        "scripts": [
            "When X comes up, I'd like to take it. I haven't done one before, "
            "which is exactly why I want it.",
            "You'd help me more by pushing back on this than by agreeing with it. "
            "Where's it weak?",
            "If I wanted to be doing this job's next version in two years, what "
            "would I need to get good at?",
        ],
    },

    ("growth_focus", "under_supplied", "acute"): {
        "headline": "You are being kept where you're already good",
        "why": (
            "This is the wide version. You want to be built — put on unfamiliar "
            "work, argued with, pointed at what comes next. What you are getting "
            "is the job you already do, managed well, with your development "
            "treated as your own business. That is a real philosophy, "
            "deliberately held: some managers do not steer people's careers "
            "because they think it presumptuous to. But the compounding matters. "
            "Staying where you are already good is comfortable across a quarter "
            "and expensive across two years, and the work you would learn most "
            "from is being handed out by someone with no particular reason to "
            "send it your way."
        ),
        "ask": (
            "Ask for one concrete thing, not for a development conversation. "
            "Development conversations are easy to agree to and easy to let "
            "lapse; a named assignment with a date is neither. In the same "
            "conversation, say what you want to be doing in two years and ask "
            "directly whether this role is a route to it — you need the honest "
            "answer more than the encouraging one. If the answer is that it is "
            "not, that is not a bad outcome. It is the piece of information that "
            "lets you plan, and you are far better off holding it now than in "
            "eighteen months."
        ),
        "agenda": [
            "A named, unfamiliar piece of work, with a date, brought as a "
            "proposal rather than as a wish.",
            "Where you want to be in two years, said out loud.",
            "The direct question: can this role take you there, and what would "
            "have to change if it cannot?",
            "Their honest read on the gap between where you are and where you "
            "want to be.",
        ],
        "scripts": [
            "I'd like to own X when it comes round. I haven't done it before — "
            "I'd want your help, and I'd want the work.",
            "Here's what I want to be doing in two years. Straight answer: is "
            "this role a route to it?",
            "What's the thing I'm not good enough at yet? I'd rather know than "
            "guess.",
        ],
    },

    ("growth_focus", "over_supplied", "notable"): {
        "headline": "You're being developed when you'd rather be delivering",
        "why": (
            "You want to do the work you are good at, well. Your manager is "
            "invested in what you become next — putting you on unfamiliar things, "
            "setting learning goals, arguing with your ideas rather than backing "
            "them. That is an engaged and generous way to manage, and most people "
            "would take it over indifference. The grind is that development has a "
            "cost the person paying it feels most: unfamiliar work is slower, "
            "being challenged in front of others is tiring, and when you are not "
            "currently reaching for the next thing, all of it reads as pressure "
            "rather than as investment."
        ),
        "ask": (
            "Say the quiet part, because your manager almost certainly cannot "
            "tell. From the outside, content-where-you-are and lacking-ambition "
            "look identical, and most managers assume the second and push harder. "
            "Tell them plainly that mastery of the current role is what you are "
            "after right now, and give them a horizon — \"for the next year\" "
            "makes it a season rather than a permanent refusal, and that is far "
            "easier to hear."
        ),
        "agenda": [
            "What you actually want from the next year, said plainly.",
            "Which stretch you would take if you took one — chosen by you rather "
            "than picked for you.",
            "How you would like your ideas handled: where you want the pushback, "
            "and where you would rather have backing.",
        ],
        "scripts": [
            "I want to get properly good at what I'm doing now before I take on "
            "something new. That's a choice, not a lack of interest.",
            "If I'm taking one new thing this year, I'd want it to be X.",
            "On this one I'm after your support rather than a debate — I've "
            "thought it through and I'd like to run at it.",
        ],
    },

    ("growth_focus", "over_supplied", "acute"): {
        "headline": "Constant stretch, and you wanted depth",
        "why": (
            "The distance here is wide. You want to consolidate — do work you are "
            "good at, be backed rather than examined, keep the job about the job. "
            "What is coming at you is continuous development: new things, "
            "learning goals, your thinking pushed on. It is worth naming that "
            "this is what an invested manager looks like and that plenty of "
            "people are trying to get managed this way. It still does not fit "
            "you, and the mismatch has a real cost: constant unfamiliar work "
            "suppresses the thing you are actually best at, and being challenged "
            "as a default makes it harder to build any conviction worth "
            "challenging."
        ),
        "ask": (
            "Ask for a season of consolidation, with a shape and an end. An "
            "open-ended request to stop developing you is hard for an invested "
            "manager to accept and honestly hard to act on. A defined period — "
            "two quarters of depth in your current work, with agreed outcomes you "
            "will be measured on and a date to revisit — gives them something to "
            "say yes to and gives you the ground you want. Ask for the pushback "
            "to be selective rather than constant, and name the decisions you "
            "would like simply backed. If the pushing continues regardless, the "
            "mismatch is about what this manager understands their job to be, and "
            "that is fair to weigh when you decide whether to keep working under "
            "them."
        ),
        "agenda": [
            "A defined consolidation period with agreed outcomes and a revisit "
            "date.",
            "Which one new thing, if any, you would take inside that period — "
            "chosen by you.",
            "Where you want your ideas challenged and where you want them backed, "
            "drawn as a line you can both see.",
            "How your progress gets judged during the period, so depth counts as "
            "progress rather than as standing still.",
        ],
        "scripts": [
            "I'd like the next two quarters to be about getting deep rather than "
            "broad. Can we agree what good looks like on that basis?",
            "I know you're pushing me because you rate me, and I'd rather have "
            "that than the opposite. What I need right now is a run at depth.",
            "On the big calls, argue with me. On the day-to-day ones, I'd rather "
            "just have your backing.",
        ],
    },
}


# ---------------------------------------------------------------------------
# Environment hedges (bias review, Finding 4)
# ---------------------------------------------------------------------------
# Keyed by (dimension, direction) because the hedge is the same at either
# severity. Only the three directions the finding actually implicates carry one:
# a hedge attached everywhere would read as boilerplate and get skipped.

CONSTRAINT_NOTES: dict[tuple[str, str], str] = {
    ("autonomy", "under_supplied"): (
        "Some of this may not be your manager's to change. Sign-offs, fixed "
        "sequences and approval steps are set by the industry, the client or the "
        "regulator in a great many workplaces, and a manager operating inside "
        "them has no latitude to hand you. If that is the case here, the useful "
        "ask is a smaller one: not for the control itself, but for the reasoning "
        "behind it, and for room on the parts of the work that genuinely are "
        "discretionary."
    ),
    ("feedback_style", "under_supplied"): (
        "Worth checking whether this is style or circumstance. If your manager "
        "is not around while you are working — a different site, a different "
        "shift, a spread-out team, a lot of people to cover — then immediate "
        "feedback is not something being withheld from you, it is something the "
        "setup does not allow. If that is the case, ask for a deliberate "
        "substitute rather than for more presence: a standing slot, or a way to "
        "send work over for a quick read."
    ),
    ("growth_focus", "under_supplied"): (
        "Some of this may be the shape of the role rather than a choice your "
        "manager is making. Where a job is defined narrowly, there may genuinely "
        "be no unfamiliar work to hand you. If that is the case, the honest "
        "version of the ask is a different one: not for stretch inside the role, "
        "but for sight of what exists beyond it, and for their view on how people "
        "actually move from here to there."
    ),
}


# ---------------------------------------------------------------------------
# Mesh notes
# ---------------------------------------------------------------------------
# Not protocol cells — one sentence apiece, so the mesh half of the map says
# something rather than sitting blank. Keyed by (dimension, band), where band is
# where the two of you jointly sit on the scale: `low`, `mid` or `high`.

MESH_NOTES: dict[tuple[str, str], str] = {
    ("autonomy", "high"): (
        "You want room to decide how, and that is how the work reaches you. "
        "Worth protecting on purpose — this is usually the first match to go "
        "when a team gets busy or something goes wrong."
    ),
    ("autonomy", "mid"): (
        "You want direction on some things and room on others, and that is "
        "roughly how the work runs. The conversation worth having here is not "
        "about more or less latitude; it is about agreeing which decisions sit "
        "where."
    ),
    ("autonomy", "low"): (
        "You like knowing the shape of the work before you start, and your "
        "manager sets it. That is a match, and an underrated one: very little of "
        "your effort goes into working out what you are supposed to be doing."
    ),
    ("feedback_style", "high"): (
        "You want to know where you stand, often and straight, and that is how "
        "your manager operates. Worth saying out loud that it works for you — "
        "direct managers are usually told the opposite."
    ),
    ("feedback_style", "mid"): (
        "Neither of you wants a running commentary or a long silence, and you "
        "are landing in much the same place. Keep an eye on it through busy "
        "periods, when feedback is the first thing to get dropped."
    ),
    ("feedback_style", "low"): (
        "You would both rather have feedback considered and well-timed than "
        "constant, and that is how it arrives. The one thing worth doing is "
        "asking explicitly at the points where you do want a read, since neither "
        "of you will default to it."
    ),
    ("relationship", "high"): (
        "You want a manager who knows you and speaks for you, and that is the "
        "relationship you have. Keep the advocacy half sharp — make sure they "
        "know what you want to be put forward for, because warmth does not carry "
        "that information by itself."
    ),
    ("relationship", "mid"): (
        "You both keep the relationship somewhere between personal and strictly "
        "professional, and you are reading it the same way. Little to fix here."
    ),
    ("relationship", "low"): (
        "You both keep it on the work, and that suits you. The thing to watch is "
        "that a boundaried relationship still has to carry the practical "
        "information — what you want next, what you would want argued for — "
        "because it will not come up by itself."
    ),
    ("growth_focus", "high"): (
        "You want to be stretched and your manager invests in that. This is the "
        "match with the shortest shelf life: appetite for stretch moves with "
        "whatever else is going on in your life, so it is worth revisiting rather "
        "than assuming."
    ),
    ("growth_focus", "mid"): (
        "You want some development without it taking over, and that is roughly "
        "what you are getting. Worth naming the one thing you would most like to "
        "get better at, so the investment lands somewhere useful."
    ),
    ("growth_focus", "low"): (
        "You are here to do the work well, and your manager manages the work. "
        "That is a clean match. The only cost is that nobody is watching the "
        "longer arc on your behalf, so if that starts to matter, it will be you "
        "who raises it."
    ),
}
