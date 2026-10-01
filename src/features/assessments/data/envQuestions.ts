/**
 * The environment-side instrument: sixteen questions about the user's ROLE
 * (BUILD_PLAN A-1 / A-7).
 *
 * Mirrors `work_pulse/situation_items.py` verbatim -- same item ids, same
 * option keys, same prompts, same option text in both tenses. That module is
 * the scoring authority; this is its client-rendered twin, exactly the
 * relationship `mpQuestions.ts` has to `manager_match/manager_profile.py`.
 * No generator script exists in the repo (checked 2026-09-11 and 2026-10-01).
 * `tests/test_question_data_parity.py` is the guard: it fails on any drift
 * between this file and the Python module.
 *
 * TWO ORDERINGS ARE LOAD-BEARING AND NEITHER IS A PRESENTATION CHOICE.
 *
 *  1. `ENV_FORM_STEPS` is the form order: the three neutral context facts
 *     (stage/size, pay posture, industry), then the twelve descriptive dimension
 *     items, then the single evaluative item. `experienced` is last on
 *     purpose -- it is the model's outcome node and the only evaluative item
 *     in the instrument, so its verdict must not colour the twelve
 *     descriptions that precede it. `comp` sits at position two rather than
 *     beside `experienced` for the same family of reason: adjacency between a
 *     pay question and the outcome question inflates a correlation the causal
 *     model is later asked to estimate.
 *
 *  2. Option order WITHIN a dimension item alternates: exactly one item per
 *     dimension is presented low-pole-first and one high-pole-first, so a
 *     respondent who straight-lines a position lands every dimension on the
 *     midpoint rather than at an anchor. The pole -- which is the score -- is
 *     NOT carried here; the server derives it from the option key. Rendering
 *     these arrays in any order but the one written, or sorting them, breaks
 *     both defences at once.
 *
 * The past-tense variants exist because a `between_jobs` user describes the
 * role they most recently held. `first_job` never reaches this form at all
 * (`POST /me/environment-report` refuses it with `first_job_no_role`); the
 * variants are carried for that status only because the Python item bank
 * carries them.
 */


export type EnvDimension =
  | "autonomy"
  | "pace"
  | "collaboration"
  | "feedback"
  | "innovation"
  | "decision";

/** Positional option key. The server maps key -> pole -> score; the client never does. */
export type EnvOptionKey = "a" | "b" | "c" | "d" | "e";

export type EnvContextItemId = "stage_size" | "comp" | "industry" | "experienced";

/** `situation_items.INDUSTRY_LEVELS`: the causal model's `industry` levels, in config order. */
export type EnvIndustry = "tech" | "finance" | "healthcare" | "retail" | "other";

export interface EnvOption {
  key: EnvOptionKey;
  text: string;
  textPast: string;
}

export interface EnvItem {
  itemId: string;
  dimension: EnvDimension;
  prompt: string;
  promptPast: string;
  /** Rendered in this order. Do not sort. See the header's point 2. */
  options: EnvOption[];
}

export interface EnvContextOption {
  /** 1..5 stored raw, or a level key for `industry` (the one categorical item).
   *  `null` is the "not sure" option, which only comp and industry carry. */
  value: number | string | null;
  text: string;
  textPast: string;
}

export interface EnvContextItem {
  itemId: EnvContextItemId;
  prompt: string;
  promptPast: string;
  options: EnvContextOption[];
}

/** `EnvironmentReport.version` -- which item set produced a stored answer blob. */
export const ENV_FORM_VERSION = "env-v2-2026-10-01";


/** The twelve dimension items, in `item_list_in_form_order()` order. */
export const ENV_ITEMS: EnvItem[] = [
  {
    itemId: "env-autonomy-1",
    dimension: "autonomy",
    prompt: "How much say do you have over how your work gets done?",
    promptPast: "How much say did you have over how your work got done?",
    options: [
      {
        key: "a",
        text: "Your work is assigned and specified for you, and most decisions go up for sign-off before you act.",
        textPast: "Your work was assigned and specified for you, and most decisions went up for sign-off before you acted.",
      },
      {
        key: "b",
        text: "Your manager sets the direction and the priorities; you choose your own tactics inside clear guardrails.",
        textPast: "Your manager set the direction and the priorities; you chose your own tactics inside clear guardrails.",
      },
      {
        key: "c",
        text: "Direction is set at the team level, and within that you pick how the work gets done.",
        textPast: "Direction was set at the team level, and within that you picked how the work got done.",
      },
      {
        key: "d",
        text: "You own the outcome and choose your own approach, with only light approval along the way.",
        textPast: "You owned the outcome and chose your own approach, with only light approval along the way.",
      },
      {
        key: "e",
        text: "You set your own priorities and your own methods, and almost nothing needs approval.",
        textPast: "You set your own priorities and your own methods, and almost nothing needed approval.",
      },
    ],
  },
  {
    itemId: "env-autonomy-2",
    dimension: "autonomy",
    prompt: "Who decides what you work on, and in what order?",
    promptPast: "Who decided what you worked on, and in what order?",
    options: [
      {
        key: "a",
        text: "You decide what you take on and in what order; nobody hands you a queue.",
        textPast: "You decided what you took on and in what order; nobody handed you a queue.",
      },
      {
        key: "b",
        text: "You’re given the outcomes to hit, and the sequence and the timing are yours.",
        textPast: "You were given the outcomes to hit, and the sequence and the timing were yours.",
      },
      {
        key: "c",
        text: "You and your manager set your priorities together, and either of you can move them.",
        textPast: "You and your manager set your priorities together, and either of you could move them.",
      },
      {
        key: "d",
        text: "Your priorities are set for you, though you can make the case for changing them.",
        textPast: "Your priorities were set for you, though you could make the case for changing them.",
      },
      {
        key: "e",
        text: "What you work on and when is scheduled for you, and changing it takes permission.",
        textPast: "What you worked on and when was scheduled for you, and changing it took permission.",
      },
    ],
  },
  {
    itemId: "env-pace-1",
    dimension: "pace",
    prompt: "What is the tempo of the work?",
    promptPast: "What was the tempo of the work?",
    options: [
      {
        key: "a",
        text: "The tempo is fast: aggressive deadlines, quick turnaround, and an intense week.",
        textPast: "The tempo was fast: aggressive deadlines, quick turnaround, and an intense week.",
      },
      {
        key: "b",
        text: "Urgency is regular — timelines are tight-ish and work goes out often, without being relentless.",
        textPast: "Urgency was regular — timelines were tight-ish and work went out often, without being relentless.",
      },
      {
        key: "c",
        text: "The tempo is ordinary: some stretches of crunch, some stretches of calm.",
        textPast: "The tempo was ordinary: some stretches of crunch, some stretches of calm.",
      },
      {
        key: "d",
        text: "The tempo is generally measured, with occasional pushes; deadlines exist but rarely dominate the week.",
        textPast: "The tempo was generally measured, with occasional pushes; deadlines existed but rarely dominated the week.",
      },
      {
        key: "e",
        text: "The tempo is deliberate: long planning horizons and an unhurried week.",
        textPast: "The tempo was deliberate: long planning horizons and an unhurried week.",
      },
    ],
  },
  {
    itemId: "env-pace-2",
    dimension: "pace",
    prompt: "How quickly are things expected to happen?",
    promptPast: "How quickly were things expected to happen?",
    options: [
      {
        key: "a",
        text: "Nothing is expected in a hurry — requests can wait until you get to them.",
        textPast: "Nothing was expected in a hurry — requests could wait until you got to them.",
      },
      {
        key: "b",
        text: "Most things can wait a day or two; a genuine rush is the exception.",
        textPast: "Most things could wait a day or two; a genuine rush was the exception.",
      },
      {
        key: "c",
        text: "Some things need an answer the same day, some can sit for a week.",
        textPast: "Some things needed an answer the same day, some could sit for a week.",
      },
      {
        key: "d",
        text: "Quick turnaround is the norm — you’re expected to respond and move within the day.",
        textPast: "Quick turnaround was the norm — you were expected to respond and move within the day.",
      },
      {
        key: "e",
        text: "Requests land expecting an answer now, and your week can be rearranged overnight.",
        textPast: "Requests landed expecting an answer now, and your week could be rearranged overnight.",
      },
    ],
  },
  {
    itemId: "env-collaboration-1",
    dimension: "collaboration",
    prompt: "How does the work actually get produced?",
    promptPast: "How did the work actually get produced?",
    options: [
      {
        key: "a",
        text: "You produce your work heads-down and alone; meetings are rare and there is no pairing or joint working time.",
        textPast: "You produced your work heads-down and alone; meetings were rare and there was no pairing or joint working time.",
      },
      {
        key: "b",
        text: "You produce the work alone and bring it to periodic syncs; those meetings are status and handoff, not joint problem-solving.",
        textPast: "You produced the work alone and brought it to periodic syncs; those meetings were status and handoff, not joint problem-solving.",
      },
      {
        key: "c",
        text: "Roughly half the work is done alone and half of it in a group; neither mode dominates how the work gets made.",
        textPast: "Roughly half the work was done alone and half of it in a group; neither mode dominated how the work got made.",
      },
      {
        key: "d",
        text: "Cross-functional work is common and meetings are frequent; most problems get worked through as a group.",
        textPast: "Cross-functional work was common and meetings were frequent; most problems got worked through as a group.",
      },
      {
        key: "e",
        text: "Almost everything is produced together — constant pairing, standing group sessions, a team you are working alongside all day.",
        textPast: "Almost everything was produced together — constant pairing, standing group sessions, a team you were working alongside all day.",
      },
    ],
  },
  {
    itemId: "env-collaboration-2",
    dimension: "collaboration",
    prompt: "How much of your working day is spent working with other people?",
    promptPast: "How much of your working day was spent working with other people?",
    options: [
      {
        key: "a",
        text: "Most of the day is live time with other people — calls, working sessions, back-and-forth throughout.",
        textPast: "Most of the day was live time with other people — calls, working sessions, back-and-forth throughout.",
      },
      {
        key: "b",
        text: "You’re in live working sessions with others most days, with time in between to work on your own.",
        textPast: "You were in live working sessions with others most days, with time in between to work on your own.",
      },
      {
        key: "c",
        text: "It is an even mix of live group time and written, work-on-your-own time.",
        textPast: "It was an even mix of live group time and written, work-on-your-own time.",
      },
      {
        key: "d",
        text: "It is mostly written and asynchronous, with a live session when something needs one.",
        textPast: "It was mostly written and asynchronous, with a live session when something needed one.",
      },
      {
        key: "e",
        text: "Written updates stand in for meetings almost entirely, and long stretches of solo time are the norm.",
        textPast: "Written updates stood in for meetings almost entirely, and long stretches of solo time were the norm.",
      },
    ],
  },
  {
    itemId: "env-feedback-1",
    dimension: "feedback",
    prompt: "How often do you hear how your work is landing?",
    promptPast: "How often did you hear how your work was landing?",
    options: [
      {
        key: "a",
        text: "Rarely — you hear about your work occasionally, and often only when something has gone wrong.",
        textPast: "Rarely — you heard about your work occasionally, and often only when something had gone wrong.",
      },
      {
        key: "b",
        text: "Feedback arrives mainly on a fixed cycle: a review, or a scheduled check-in.",
        textPast: "Feedback arrived mainly on a fixed cycle: a review, or a scheduled check-in.",
      },
      {
        key: "c",
        text: "A normal mix: scheduled reviews, plus comment in the moment when something comes up.",
        textPast: "A normal mix: scheduled reviews, plus comment in the moment when something came up.",
      },
      {
        key: "d",
        text: "Often — you get comment on your work well outside any review cycle.",
        textPast: "Often — you got comment on your work well outside any review cycle.",
      },
      {
        key: "e",
        text: "Constantly — you hear how the work is landing as you go, from whoever is looking at it.",
        textPast: "Constantly — you heard how the work was landing as you went, from whoever was looking at it.",
      },
    ],
  },
  {
    itemId: "env-feedback-2",
    dimension: "feedback",
    prompt: "How is criticism of your work delivered?",
    promptPast: "How was criticism of your work delivered?",
    options: [
      {
        key: "a",
        text: "Criticism is delivered straight and unsoftened, and open disagreement about the work is routine.",
        textPast: "Criticism was delivered straight and unsoftened, and open disagreement about the work was routine.",
      },
      {
        key: "b",
        text: "Criticism is fairly direct and debate about the work is normal; a thick skin helps.",
        textPast: "Criticism was fairly direct and debate about the work was normal; a thick skin helped.",
      },
      {
        key: "c",
        text: "Criticism is delivered plainly and in moderation — neither blunt nor heavily cushioned.",
        textPast: "Criticism was delivered plainly and in moderation — neither blunt nor heavily cushioned.",
      },
      {
        key: "d",
        text: "Criticism is delivered diplomatically; directness is the exception.",
        textPast: "Criticism was delivered diplomatically; directness was the exception.",
      },
      {
        key: "e",
        text: "Criticism is cushioned or indirect when it comes, and open disagreement is rare.",
        textPast: "Criticism was cushioned or indirect when it came, and open disagreement was rare.",
      },
    ],
  },
  {
    itemId: "env-innovation-1",
    dimension: "innovation",
    prompt: "What kind of work is it — improving what exists, or making what doesn’t?",
    promptPast: "What kind of work was it — improving what existed, or making what didn’t?",
    options: [
      {
        key: "a",
        text: "Creating things that don’t exist yet — new offerings, new capabilities, bets that may not come off.",
        textPast: "Creating things that didn’t exist yet — new offerings, new capabilities, bets that might not come off.",
      },
      {
        key: "b",
        text: "Building something new comes up often, alongside the work of running what already exists.",
        textPast: "Building something new came up often, alongside the work of running what already existed.",
      },
      {
        key: "c",
        text: "A real split: part of the work improves what exists, part of it creates something new.",
        textPast: "A real split: part of the work improved what existed, part of it created something new.",
      },
      {
        key: "d",
        text: "Mostly improving what already exists, with the occasional genuinely new thing at the edges.",
        textPast: "Mostly improving what already existed, with the occasional genuinely new thing at the edges.",
      },
      {
        key: "e",
        text: "Making something that already exists work better — improvement and scale, not new territory.",
        textPast: "Making something that already existed work better — improvement and scale, not new territory.",
      },
    ],
  },
  {
    itemId: "env-innovation-2",
    dimension: "innovation",
    prompt: "How much of the work is a bet that might not pay off?",
    promptPast: "How much of the work was a bet that might not pay off?",
    options: [
      {
        key: "a",
        text: "Almost none — work that doesn’t pan out isn’t planned for, and what gets started is expected to land.",
        textPast: "Almost none — work that didn’t pan out wasn’t planned for, and what got started was expected to land.",
      },
      {
        key: "b",
        text: "The occasional experiment is tolerated, but the bulk of the effort goes to things with a known payoff.",
        textPast: "The occasional experiment was tolerated, but the bulk of the effort went to things with a known payoff.",
      },
      {
        key: "c",
        text: "Some of the work is a known quantity and some of it is a bet; both are normal.",
        textPast: "Some of the work was a known quantity and some of it was a bet; both were normal.",
      },
      {
        key: "d",
        text: "Experiments are a planned part of the work, and some of them are expected not to pan out.",
        textPast: "Experiments were a planned part of the work, and some of them were expected not to pan out.",
      },
      {
        key: "e",
        text: "Exploration is the point — a good share of what is tried is expected to fail, and that is budgeted for.",
        textPast: "Exploration was the point — a good share of what was tried was expected to fail, and that was budgeted for.",
      },
    ],
  },
  {
    itemId: "env-decision-1",
    dimension: "decision",
    prompt: "What do decisions actually rest on?",
    promptPast: "What did decisions actually rest on?",
    options: [
      {
        key: "a",
        text: "Taste, experience and vision — someone’s judgement carries the call.",
        textPast: "Taste, experience and vision — someone’s judgement carried the call.",
      },
      {
        key: "b",
        text: "Judgement leads, and numbers are brought in afterwards to confirm it.",
        textPast: "Judgement led, and numbers were brought in afterwards to confirm it.",
      },
      {
        key: "c",
        text: "Judgement and evidence both carry weight, depending on the call.",
        textPast: "Judgement and evidence both carried weight, depending on the call.",
      },
      {
        key: "d",
        text: "Measurement usually settles it, with judgement filling the gaps the numbers don’t cover.",
        textPast: "Measurement usually settled it, with judgement filling the gaps the numbers didn’t cover.",
      },
      {
        key: "e",
        text: "Numbers settle it — measured, tested, and not decided until the evidence is in.",
        textPast: "Numbers settled it — measured, tested, and not decided until the evidence was in.",
      },
    ],
  },
  {
    itemId: "env-decision-2",
    dimension: "decision",
    prompt: "When you want to make a case for something, what carries it?",
    promptPast: "When you wanted to make a case for something, what carried it?",
    options: [
      {
        key: "a",
        text: "Numbers — you’re expected to bring measurements, tests or analysis.",
        textPast: "Numbers — you were expected to bring measurements, tests or analysis.",
      },
      {
        key: "b",
        text: "Usually evidence, though a well-argued judgement call can carry.",
        textPast: "Usually evidence, though a well-argued judgement call could carry.",
      },
      {
        key: "c",
        text: "Either a strong argument or good numbers will carry a case; both are ordinary currency.",
        textPast: "Either a strong argument or good numbers would carry a case; both were ordinary currency.",
      },
      {
        key: "d",
        text: "Mostly reasoning and experience; numbers are supporting material.",
        textPast: "Mostly reasoning and experience; numbers were supporting material.",
      },
      {
        key: "e",
        text: "Argument and instinct — the numbers are rarely what decides it.",
        textPast: "Argument and instinct — the numbers were rarely what decided it.",
      },
    ],
  },
];

export const STAGE_SIZE_ITEM: EnvContextItem = {
  itemId: "stage_size",
  prompt: "How big is the organization you work for — the whole organization, not your team?",
  promptPast: "How big was the organization you worked for in that role — the whole organization, not your team?",
  options: [
    {
      value: 1,
      text: "An early-stage startup — a handful of people, still finding its footing.",
      textPast: "An early-stage startup — a handful of people, still finding its footing.",
    },
    {
      value: 2,
      text: "A small company that has found its footing and is growing — tens of people.",
      textPast: "A small company that had found its footing and was growing — tens of people.",
    },
    {
      value: 3,
      text: "A mid-sized organization — hundreds of people, with real structure in place.",
      textPast: "A mid-sized organization — hundreds of people, with real structure in place.",
    },
    {
      value: 4,
      text: "A large organization — thousands of people, established in its market.",
      textPast: "A large organization — thousands of people, established in its market.",
    },
    {
      value: 5,
      text: "A very large enterprise — tens of thousands of people and many layers.",
      textPast: "A very large enterprise — tens of thousands of people and many layers.",
    },
  ],
};

export const COMP_ITEM: EnvContextItem = {
  itemId: "comp",
  prompt: "Compared with what you could earn elsewhere doing similar work, how does this role pay?",
  promptPast: "Compared with what you could have earned elsewhere doing similar work, how did that role pay?",
  options: [
    {
      value: 1,
      text: "Well below what you could get elsewhere for similar work.",
      textPast: "Well below what you could have got elsewhere for similar work.",
    },
    {
      value: 2,
      text: "Somewhat below.",
      textPast: "Somewhat below.",
    },
    {
      value: 3,
      text: "About the same — at market.",
      textPast: "About the same — at market.",
    },
    {
      value: 4,
      text: "Somewhat above.",
      textPast: "Somewhat above.",
    },
    {
      value: 5,
      text: "Well above what you could get elsewhere for similar work.",
      textPast: "Well above what you could have got elsewhere for similar work.",
    },
    {
      value: null,
      text: "Not sure how this compares.",
      textPast: "Not sure how that compared.",
    },
  ],
};

export const INDUSTRY_ITEM: EnvContextItem = {
  itemId: "industry",
  prompt: "Which industry is the organization you work for in?",
  promptPast: "Which industry did the organization you worked for in that role belong to?",
  options: [
    {
      value: "tech",
      text: "Technology — software, hardware, internet or IT services.",
      textPast: "Technology — software, hardware, internet or IT services.",
    },
    {
      value: "finance",
      text: "Finance — banking, insurance, investment or accounting.",
      textPast: "Finance — banking, insurance, investment or accounting.",
    },
    {
      value: "healthcare",
      text: "Healthcare — hospitals, clinics, pharma or health services.",
      textPast: "Healthcare — hospitals, clinics, pharma or health services.",
    },
    {
      value: "retail",
      text: "Retail — shops, e-commerce or consumer goods.",
      textPast: "Retail — shops, e-commerce or consumer goods.",
    },
    {
      value: "other",
      text: "Something else.",
      textPast: "Something else.",
    },
    {
      value: null,
      text: "Not sure, or I’d rather not say.",
      textPast: "Not sure, or I’d rather not say.",
    },
  ],
};

export const EXPERIENCED_ITEM: EnvContextItem = {
  itemId: "experienced",
  prompt: "Overall, how well is this role working for you?",
  promptPast: "Overall, how well was that role working for you?",
  options: [
    {
      value: 1,
      text: "It isn’t working at all.",
      textPast: "It wasn’t working at all.",
    },
    {
      value: 2,
      text: "It isn’t working well.",
      textPast: "It wasn’t working well.",
    },
    {
      value: 3,
      text: "A mixed picture.",
      textPast: "A mixed picture.",
    },
    {
      value: 4,
      text: "It’s working well.",
      textPast: "It was working well.",
    },
    {
      value: 5,
      text: "It’s working very well.",
      textPast: "It was working very well.",
    },
  ],
};

/** One step of the form: a context item or a dimension item, discriminated. */
export type EnvStep =
  | { kind: "context"; item: EnvContextItem }
  | { kind: "dimension"; item: EnvItem };

/**
 * The sixteen steps in form order -- `work_pulse.situation_items`' own
 * ordering comment, made executable. See the header's point 1 for why this
 * order is a correctness requirement rather than a layout decision.
 */
export const ENV_FORM_STEPS: EnvStep[] = [
  { kind: "context", item: STAGE_SIZE_ITEM },
  { kind: "context", item: COMP_ITEM },
  { kind: "context", item: INDUSTRY_ITEM },
  ...ENV_ITEMS.map((item) => ({ kind: "dimension" as const, item })),
  { kind: "context", item: EXPERIENCED_ITEM },
];
