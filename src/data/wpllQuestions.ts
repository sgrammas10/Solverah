export interface WpllOption {
  id: string;
  text: string;
}

export interface WpllQuestion {
  id: string;
  dimension: string;
  text: string;
  options: [WpllOption, WpllOption, WpllOption, WpllOption];
}

export const WPLL_QUESTIONS: WpllQuestion[] = [
  {
    id: "wpll-q1",
    dimension: "Fragmentation",
    text: "How often do you find yourself switching between unrelated tasks throughout a typical workday?",
    options: [
      { id: "wpll-q1-a", text: "Rarely — I can usually stay focused on one thing" },
      { id: "wpll-q1-b", text: "Sometimes — a few times a day" },
      { id: "wpll-q1-c", text: "Often — it feels constant" },
      { id: "wpll-q1-d", text: "Almost always — I rarely finish anything in one sitting" },
    ],
  },
  {
    id: "wpll-q2",
    dimension: "Sustainability",
    text: "How would you describe your energy level at the end of a typical workday?",
    options: [
      { id: "wpll-q2-a", text: "Strong — I often have energy left over" },
      { id: "wpll-q2-b", text: "Okay — a little tired but fine" },
      { id: "wpll-q2-c", text: "Drained — I need significant recovery time" },
      { id: "wpll-q2-d", text: "Depleted — running on empty by the end" },
    ],
  },
  {
    id: "wpll-q3",
    dimension: "Environmental Friction",
    text: "When your environment is noisy or disorganized around you, how does it affect your output?",
    options: [
      { id: "wpll-q3-a", text: "Barely at all — I can tune it out" },
      { id: "wpll-q3-b", text: "Somewhat — it slows me down a little" },
      { id: "wpll-q3-c", text: "Noticeably — it takes real effort to push through" },
      { id: "wpll-q3-d", text: "Significantly — I can't do my best work in chaos" },
    ],
  },
  {
    id: "wpll-q4",
    dimension: "Recognition Friction",
    text: "How often do you feel your best work goes unnoticed or isn't fully understood by the people around you?",
    options: [
      { id: "wpll-q4-a", text: "Rarely — I usually feel seen and recognized" },
      { id: "wpll-q4-b", text: "Sometimes — it happens but doesn't bother me much" },
      { id: "wpll-q4-c", text: "Often — it's a real source of frustration" },
      { id: "wpll-q4-d", text: "Almost always — it feels like a persistent gap" },
    ],
  },
  {
    id: "wpll-q5",
    dimension: "Work Pace",
    text: "When you think about the overall pace of your current work, it feels…",
    options: [
      { id: "wpll-q5-a", text: "Just right — energizing without being overwhelming" },
      { id: "wpll-q5-b", text: "A bit slow — I could handle more" },
      { id: "wpll-q5-c", text: "Too fast — I'm struggling to keep up" },
      { id: "wpll-q5-d", text: "Unsustainable — I'm burning through my reserves" },
    ],
  },
];
