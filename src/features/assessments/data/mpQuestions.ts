/**
 * The 16 manager-profile forced-choice items (BUILD_PLAN C-1).
 *
 * Mirrors `manager_match/manager_profile.py` verbatim -- same ids, same option
 * text, same dimensions. That module is the scoring authority; this is its
 * client-rendered twin, the same relationship `mmQuestions.ts` has to
 * `manager_match/questions.py`.
 *
 * `optionA`/`optionB` are the AUTHORED option identity: `choice: 'a'` always
 * means "the option written here as `optionA`", regardless of which side of
 * the screen it renders on. `ManagerProfilePage` renders them in this fixed
 * order and submits the identity of whichever card was clicked, so authored
 * identity and presentation position happen to coincide here -- but a future
 * change that randomizes card position must keep submitting the identity, not
 * the side.
 */
export type MPDimension = "autonomy" | "feedback_style" | "relationship" | "growth_focus";

export interface MPQuestion {
  id: string;
  optionA: string;
  optionB: string;
  dimension: MPDimension;
}

export const MP_QUESTIONS: MPQuestion[] = [
  {
    id: "mp-q1",
    optionA: "Your manager sets both the goal and the method for your work.",
    optionB: "Your manager sets the goal and leaves the method to you.",
    dimension: "autonomy",
  },
  {
    id: "mp-q2",
    optionA: "Your manager hears how you handled a problem after you’ve handled it.",
    optionB: "Your manager works through a problem with you while you’re still in it.",
    dimension: "autonomy",
  },
  {
    id: "mp-q3",
    optionA: "Your manager signs off on your decisions before you act on them.",
    optionB: "Your manager expects you to make the call and tell them afterwards.",
    dimension: "autonomy",
  },
  {
    id: "mp-q4",
    optionA: "Your manager tells you what has to be done by when, and leaves the order to you.",
    optionB: "Your manager tells you what to do in what order as the work goes along.",
    dimension: "autonomy",
  },
  {
    id: "mp-q5",
    optionA: "Your manager saves feedback for scheduled reviews or set check-ins.",
    optionB: "Your manager tells you the moment they notice something, mid-task if need be.",
    dimension: "feedback_style",
  },
  {
    id: "mp-q6",
    optionA: "Your manager states the problem with your work plainly, without cushioning it.",
    optionB: "Your manager frames criticism carefully, and leads with what worked.",
    dimension: "feedback_style",
  },
  {
    id: "mp-q7",
    optionA: "Your manager comments on your work often — small things as well as large.",
    optionB: "Your manager comments on your work rarely, and only when something matters a lot.",
    dimension: "feedback_style",
  },
  {
    id: "mp-q8",
    optionA: "Your manager speaks up when something needs to change, and otherwise leaves you to it.",
    optionB: "Your manager tells you where you stand either way — when the work is on track and when it isn’t.",
    dimension: "feedback_style",
  },
  {
    id: "mp-q9",
    optionA: "Your manager keeps out of your life outside work unless you bring it up.",
    optionB: "Your manager asks about things outside the work — how you’re doing generally.",
    dimension: "relationship",
  },
  {
    id: "mp-q10",
    optionA: "Your manager speaks up for you when decisions about you get made without you there.",
    optionB: "Your manager expects your record to speak for you in those decisions.",
    dimension: "relationship",
  },
  {
    id: "mp-q11",
    optionA: "Your manager runs things the same way with everyone they manage.",
    optionB: "Your manager adapts how they work with you to suit you specifically.",
    dimension: "relationship",
  },
  {
    id: "mp-q12",
    optionA: "Your manager talks with you about the job you’re doing now.",
    optionB: "Your manager talks with you about where you’re heading after this job.",
    dimension: "growth_focus",
  },
  {
    id: "mp-q13",
    optionA: "Your manager puts you on work you haven’t done before.",
    optionB: "Your manager puts you on work you’re already good at.",
    dimension: "growth_focus",
  },
  {
    id: "mp-q14",
    optionA: "Your manager pushes back on your ideas and makes you defend them.",
    optionB: "Your manager takes your ideas as given and helps you get them done.",
    dimension: "growth_focus",
  },
  {
    id: "mp-q15",
    optionA: "Your manager leaves your learning to you and manages the work in front of you.",
    optionB: "Your manager sets goals with you for what you’ll learn next, and asks about them later.",
    dimension: "growth_focus",
  },
  {
    id: "mp-q16",
    optionA: "Your manager keeps track of how you’re doing personally, whether or not you raise it.",
    optionB: "Your manager takes you at your word about how you’re doing.",
    dimension: "relationship",
  },
];
