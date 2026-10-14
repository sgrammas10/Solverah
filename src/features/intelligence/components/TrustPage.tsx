/**
 * TrustPage.tsx — the authenticated transparency page (BUILD_PLAN D-3).
 *
 * Static text only. No hooks, no queries, no per-user content: nothing here
 * reads a submission, a score, or a profile document, which is what makes the
 * page D-15-compatible rather than a carve-out from it. The compliance mirror
 * (COMPLIANCE_GAP_ANALYSIS_AND_PLAN.md, GAP-08) blesses candidate-facing
 * transparency text on exactly that basis — "how this is computed, what it
 * doesn't mean" is a description of the mechanism in general, never an
 * individual's numbers.
 *
 * WHY THIS PAGE EXISTS AT ALL. The completion state after Work Pulse is a
 * decision (D-15), but from the outside an assessment that returns nothing
 * looks like an assessment that broke, or one whose payoff is being withheld
 * to sell something. Explaining the withholding is the only version of this
 * that builds trust rather than spending it. That is the register the copy is
 * written in: the longest section is the one about what we do NOT show, and it
 * leads with the objection rather than answering it late.
 *
 * COPY RULES, and each one is load-bearing:
 *
 *  1. Nothing on this page promises a feature that does not exist. Matching is
 *     described as live (CompanyLens, PRODUCT_DECISIONS §2 six-trait entry):
 *     evidence-backed reads, coverage stated, never a score, percentage or
 *     probability, paraphrased evidence only. The Situation Report is not
 *     named at all — its decision entry is still a draft awaiting sign-off.
 *  2. The calibration section ends in a limits paragraph rather than a claim.
 *     "Two blind raters" is real (round 1, six packets) and small; saying so
 *     here costs nothing and is the difference between transparency and
 *     marketing wearing its clothes.
 *  3. No defensive register. No "we take your privacy seriously". The reader
 *     should be able to disagree with a decision on this page and still
 *     believe it was made honestly.
 *  4. Claims are scoped to the instrument they are actually true of, and the
 *     first draft of this page got two of them wrong in a way worth recording
 *     so the next edit does not repeat it. FocusType is NOT forced-choice —
 *     it is card sorting and ranking (see components/focustype/Scene1.tsx), so
 *     the two-options sentence names Work Pulse and ManagerMatch only. And
 *     reverse-keyed items exist in Work Pulse, NOT in ManagerMatch:
 *     MANAGER_PROFILE_ITEMS_BIAS_REVIEW.md Finding 1 shows three of
 *     ManagerMatch's four dimensions are perfectly straight-keyed. Widening
 *     either sentence back to "every instrument" makes this page false, which
 *     is the one failure mode it cannot survive.
 *
 * The PUBLIC twin of this page is deliberately not built: it waits on the
 * publicity gate (PRODUCT_DECISIONS §4). `/how-matching-works` is the existing
 * public transparency page and stays the shorter, pre-signup one.
 */
import { sectionId } from "../../../shared/lib/sectionId";
import DocLayout from "../../../shared/ui/DocLayout";
import { DOC_H2, DOC_P } from "../../../shared/ui/publicStyles";

interface TrustSection {
  /** Heading text, and the handle the tests assert on. */
  title: string;
  /** Body paragraphs, in order. */
  body: string[];
  /**
   * An optional set-aside paragraph rendered in a bordered callout under the
   * body — used where a section has to answer the obvious objection to itself
   * without burying it in the run of prose.
   */
  aside?: { title: string; body: string };
}

const SECTIONS: TrustSection[] = [
  {
    title: "The questions are forced choices, and both answers are real",
    body: [
      "Work Pulse and ManagerMatch show you two options and ask which is more true of you. There is no scale, no neutral middle and no “it depends”. That is mildly annoying by design: a scale lets everyone sit safely near the middle, and a forced choice makes an answer cost something. FocusType works differently — you arrange and rank things rather than pick between two — but the same rule governs it: there is no arrangement that comes out as the right one.",
      "Both options are written to be legitimate. Wanting a manager who checks in every week is not better or worse than wanting one who leaves you alone until you surface. Preferring to decide from data is not more professional than preferring to decide and adjust. If an item ever reads as though one side is the answer a good employee gives, that item is broken — and we treat it as broken rather than as a question you failed.",
      "Some Work Pulse items are deliberately reversed: the same underlying question asked from the direction of what frustrates you rather than what you prefer. They are there so that answering the same way straight down the list contradicts itself, and so we can tell when it has.",
    ],
  },
  {
    title: "There is no score to see, and that is the point",
    body: [
      "When you finish Work Pulse you get a completion screen. No six numbers, no profile paragraph, no archetype. That is not a feature we have not got to yet. It is a decision, and it is going to hold.",
      "The reasoning is short. A visible score becomes a target. If we showed you where you landed on autonomy, you would learn — not dishonestly, just by paying attention — which kind of answer moves that number. The next sitting would be slightly less about you and slightly more about the profile you would rather have. Do that across everyone who uses Solverah and the measurement stops measuring anything, including for the people who never tried to move it.",
      "It is also why there is no narrative. A paragraph about you that regenerates every time you retake is a score with adjectives: change an answer, watch the description shift, and the gradient is back.",
      "Your results are not lost, and they are not sitting in a drawer. They are doing the thing you filled them in for — working underneath the parts of Solverah that use them. The trade is real and worth stating plainly: you give up the small satisfaction of seeing your numbers, and you get a measurement that still means something the third time you take it.",
    ],
    aside: {
      title: "Then why does FocusType show me a result?",
      body: "Because that asymmetry is deliberate. FocusType and ManagerMatch hand you something to read, since they are built to be read and acted on by you. Work Pulse is the instrument the matching model reads, so Work Pulse is the one that stays quiet. The rule is not “users see nothing”; it is that the measurement the model is calibrated against does not get a dial attached to it.",
    },
  },
  {
    title: "What matching means, and what it does not",
    body: [
      "Company matching is live in CompanyLens, as one signal among others. For each trait it gives you a read on how a company lines up with what you have told us you need, the evidence behind that read, and how much evidence there is: it tells you when it is working from only some of the six traits. It never shows a score, a percentage or a probability, because a plausible-looking number would claim more than the evidence can carry. The evidence it shows is paraphrased, not quoted.",
      "It is an estimate with uncertainty attached, not a verdict. A match says two profiles line up on the dimensions we can actually measure. It does not say you would be happy there, that you would be hired, or that you would do well — those turn on a particular manager, a particular team and a particular year, none of which are in the data.",
      "It is one output, not the product. The question underneath every instrument here is what conditions let you work well, how far your current situation sits from them, and what you can change. A ranked list of companies is one answer to that question. It is not the only one, and the rest of Solverah is not holding its breath for it.",
      "And it is never something done to you. Employers do not see your answers or your dimension scores. No employer decision about you is made through Solverah. Matching exists so that you can look outward — not so that anyone can rank you.",
    ],
  },
  {
    title: "How we check our own instruments",
    body: [
      "Three disciplines, in plain terms.",
      "Item sets are read for bias before people answer them. Someone goes through each question hunting for the option that sounds like the answer a better person would give, and for questions that quietly assume an office, a seniority or a particular kind of team. What turns up is written down and fixed — or written down and accepted, with the reason it was not fixed. These reviews are documents that name the items they could not repair, not a box anybody ticks. The most recent one found a real flaw in one of our own shipped instruments, which is the only evidence worth having that a review is doing anything.",
      "Company evidence is scored by more than one trained rater, working blind. They read the same material, they cannot see each other’s scores, and where they disagree we keep the disagreement. We do not average it away or drop the odd one out. Two careful people reading the same evidence differently is information about the evidence, and discarding it would make the profiles look more certain than they are. That is how the scoring rubric is calibrated. The company reads you see in CompanyLens are scored automatically, by an AI scorer applying that same rubric to each piece of evidence, and each read tells you how much evidence it rests on. Checking that automatic scoring against the human raters is part of the unfinished work below.",
      "We attack our own anonymisation. The material raters read has the company’s identity stripped out of it, so that their scores describe evidence rather than a reputation they already hold. Stripping is easy to do badly, so we read the scrubbed version back and hunt for whatever still gives the company away — and we record what we find, including the leaks we decide not to close and why. Then we ask every rater afterwards whether they recognised the company anyway. When someone did, that goes down next to their scores instead of being quietly dropped.",
    ],
    aside: {
      title: "The honest limits of all that",
      body: "This work is real and it is not finished. Not every instrument has had the same depth of review, the calibration set is small, the model it feeds runs on expert estimates and has not yet been trained on real outcomes (which is why it never shows you a probability), and none of it has yet been checked against how people actually answer at scale — which is something we can only learn once enough people have. That evidence will change some of these items. We would rather write that here than imply a finished science.",
    },
  },
  {
    title: "Your answers",
    body: [
      "The Privacy Policy is the binding version and it is short; this is the part of it that bears on this page. Employers never see your individual answers or your dimension scores. Your answers are not sold and are not used for advertising. You can delete your account and the data behind it.",
      "You can retake Work Pulse from its page whenever your work has changed. A retake does not overwrite the sitting before it — each one is stored as its own. Your newest sitting is the one Solverah works from, with one exception: your Situation Report stays on the sitting it was built from until you choose to re-read it, so a retake never quietly rewrites a report you have already read. Keeping every sitting is what makes it possible, later, to tell a genuine change in your working life from ordinary noise.",
    ],
  },
];

const CONTENTS = SECTIONS.map(({ title }) => ({ id: sectionId(title), title }));

function TrustPage() {
  return (
    <DocLayout
      title="How this works, and what we hold back"
      meta="Last reviewed 14 October 2026"
      lead={
        <p>
          Solverah measures the conditions you do your best work in. This page covers how those
          measurements are made, what we do with them, and why one of them is never shown back to
          you. That last part is the one most likely to read as evasion, so it gets the longest
          section.
        </p>
      }
      back={{ to: "/intelligence", label: "Back to your Intelligence hub" }}
      sections={CONTENTS}
      related={[
        { to: "/how-matching-works", label: "How matching works" },
        { to: "/privacy", label: "Privacy policy" },
        { to: "/terms", label: "Terms of service" },
      ]}
    >
      {SECTIONS.map(({ title, body, aside }, i) => (
        <section key={title} className={i ? "mt-14" : ""}>
          <h2 id={sectionId(title)} className={`${DOC_H2} mb-4`}>
            {title}
          </h2>
          {body.map((paragraph) => (
            <p key={paragraph.slice(0, 48)} className={`${DOC_P} mb-5`}>
              {paragraph}
            </p>
          ))}
          {aside && (
            <div className="mt-6 border-l-[3px] border-forest-dark bg-white px-5 py-4">
              <h3 className="text-[0.95rem] font-semibold text-ink-primary">{aside.title}</h3>
              <p className="mt-1 text-[0.95rem] leading-[1.6] text-ink-secondary">{aside.body}</p>
            </div>
          )}
        </section>
      ))}

      <p className="mt-14 border-t border-cream-muted pt-8 text-[1.05rem] font-medium leading-[1.7] text-ink-primary">
        Nothing on this page describes something that does not exist yet. Where a thing is still
        being built, it says so, and when that changes, this page changes with it.
      </p>
    </DocLayout>
  );
}

export default TrustPage;
