export type MMDimension = 'autonomy' | 'feedback_style' | 'relationship' | 'growth_focus';

export interface MMQuestion {
  id: string;
  optionA: string;
  optionB: string;
  dimension: MMDimension;
}

export const MM_QUESTIONS: MMQuestion[] = [
  {
    id: "mm-q1",
    optionA: "Your manager provides a detailed brief for every task, including how to approach it.",
    optionB: "Your manager gives you the goal and leaves the approach entirely up to you.",
    dimension: "autonomy",
  },
  {
    id: "mm-q2",
    optionA: "Your manager checks in with you daily to monitor progress.",
    optionB: "Your manager trusts you to flag them when you need input.",
    dimension: "autonomy",
  },
  {
    id: "mm-q3",
    optionA: "When you’re stuck, you prefer your manager to guide you step-by-step to the answer.",
    optionB: "When you’re stuck, you prefer to solve it yourself and report back with the outcome.",
    dimension: "autonomy",
  },
  {
    id: "mm-q4",
    optionA: "You prefer knowing exactly what success looks like before you start a task.",
    optionB: "You prefer to define success as you go, based on what you discover.",
    dimension: "autonomy",
  },
  {
    id: "mm-q5",
    optionA: "You want feedback delivered as soon as your manager notices something, even mid-task.",
    optionB: "You prefer feedback bundled into scheduled check-ins – not delivered in the moment.",
    dimension: "feedback_style",
  },
  {
    id: "mm-q6",
    optionA: "Direct, blunt feedback – even if it stings – is more useful to you than softened feedback.",
    optionB: "You need feedback framed constructively before you can absorb and act on it.",
    dimension: "feedback_style",
  },
  {
    id: "mm-q7",
    optionA: "You want your manager to review your work before you consider it done.",
    optionB: "You consider your work done when you’re satisfied with it, regardless of manager review.",
    dimension: "feedback_style",
  },
  {
    id: "mm-q8",
    optionA: "Frequent positive reinforcement from your manager meaningfully affects your motivation.",
    optionB: "Your own judgment of your work is what motivates you – you don’t need external validation.",
    dimension: "feedback_style",
  },
  {
    id: "mm-q9",
    optionA: "You prefer a manager relationship that stays professional – minimal personal overlap.",
    optionB: "You perform better when your manager knows you as a person, not just a direct report.",
    dimension: "relationship",
  },
  {
    id: "mm-q10",
    optionA: "You’d rather have a manager who advocates strongly for your interests in the org.",
    optionB: "You’d rather have a manager who holds you to high standards without softening expectations.",
    dimension: "relationship",
  },
  {
    id: "mm-q11",
    optionA: "A manager who is available and accessible gives you confidence.",
    optionB: "A manager who trusts you enough to be hard to reach gives you confidence.",
    dimension: "relationship",
  },
  {
    id: "mm-q12",
    optionA: "You want your manager to actively plan your development – setting learning goals with you.",
    optionB: "You take full ownership of your own development and don’t need your manager’s direction.",
    dimension: "growth_focus",
  },
  {
    id: "mm-q13",
    optionA: "Regular career conversations with your manager make you more invested in your work.",
    optionB: "Career conversations feel like overhead – you’d rather focus on doing excellent work.",
    dimension: "growth_focus",
  },
  {
    id: "mm-q14",
    optionA: "Being pushed outside your comfort zone by your manager energizes you.",
    optionB: "You do your best work in areas where you already have confidence and established skills.",
    dimension: "growth_focus",
  },
  {
    id: "mm-q15",
    optionA: "You want a manager who challenges your ideas and pushes back when they disagree.",
    optionB: "You want a manager who supports your ideas and helps you execute them.",
    dimension: "growth_focus",
  },
];
