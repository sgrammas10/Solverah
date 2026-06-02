export interface WpOption {
  id: string;
  text: string;
}

export interface WpQuestion {
  id: string;
  dimension: string;
  text: string;
  options: [WpOption, WpOption, WpOption, WpOption];
}

export const WP_QUESTIONS: WpQuestion[] = [
  {
    id: "wp-q1",
    dimension: "Fragmentation",
    text: "When you're pulled off a task mid-way through, how long does it typically take you to rebuild your focus?",
    options: [
      { id: "wp-q1-a", text: "A few minutes — I pick back up pretty quickly" },
      { id: "wp-q1-b", text: "10–20 minutes — it takes real effort to re-orient" },
      { id: "wp-q1-c", text: "30+ minutes — I often never quite get back into flow" },
      { id: "wp-q1-d", text: "I've mostly stopped expecting deep focus — it rarely happens" },
    ],
  },
  {
    id: "wp-q2",
    dimension: "Sustainability",
    text: "After a tough stretch — a demanding week, a big push — how do you typically recover?",
    options: [
      { id: "wp-q2-a", text: "A good night's sleep or a weekend usually restores me" },
      { id: "wp-q2-b", text: "It takes a few lighter days before I feel like myself" },
      { id: "wp-q2-c", text: "I struggle to fully recover before the next demand hits" },
      { id: "wp-q2-d", text: "I don't really recover — I just keep pushing through" },
    ],
  },
  {
    id: "wp-q3",
    dimension: "Environmental Friction",
    text: "How much of your workday feels like it exists to support other people's processes rather than your own actual work?",
    options: [
      { id: "wp-q3-a", text: "Not much — most of my time is on real output" },
      { id: "wp-q3-b", text: "Some — maybe 20–30% feels like overhead" },
      { id: "wp-q3-c", text: "A lot — I feel like I work for the calendar, not my work" },
      { id: "wp-q3-d", text: "Almost all of it — I can barely find time to do the work itself" },
    ],
  },
  {
    id: "wp-q4",
    dimension: "Recognition Friction",
    text: "When your contribution feeds into a team outcome, how often does your specific role in that result get acknowledged?",
    options: [
      { id: "wp-q4-a", text: "Usually — people know what I brought to it" },
      { id: "wp-q4-b", text: "Sometimes — depends on who's paying attention" },
      { id: "wp-q4-c", text: "Rarely — team results tend to flatten individual contributions" },
      { id: "wp-q4-d", text: "Almost never — I feel largely invisible in group work" },
    ],
  },
  {
    id: "wp-q5",
    dimension: "Work Pace",
    text: "How often do you find yourself working urgently toward a deadline that, in retrospect, wasn't actually urgent?",
    options: [
      { id: "wp-q5-a", text: "Rarely — urgency in my environment is usually real" },
      { id: "wp-q5-b", text: "Sometimes — maybe once or twice a month" },
      { id: "wp-q5-c", text: "Regularly — manufactured urgency is part of the culture" },
      { id: "wp-q5-d", text: "Constantly — everything is treated as high priority" },
    ],
  },
  {
    id: "wp-q6",
    dimension: "Autonomy",
    text: "When you're given a clear goal, how much say do you have in how you actually get there?",
    options: [
      { id: "wp-q6-a", text: "Full autonomy — I define the approach and execute it" },
      { id: "wp-q6-b", text: "Significant input — my preferences shape the method" },
      { id: "wp-q6-c", text: "Limited — I work within a fairly defined playbook" },
      { id: "wp-q6-d", text: "Very little — the process is usually dictated to me" },
    ],
  },
  {
    id: "wp-q7",
    dimension: "Autonomy",
    text: "How much control do you have over when and where you do your most focused work?",
    options: [
      { id: "wp-q7-a", text: "A lot — I structure my day around how I work best" },
      { id: "wp-q7-b", text: "Some — I have flexibility but within real constraints" },
      { id: "wp-q7-c", text: "Not much — my schedule is largely set by others" },
      { id: "wp-q7-d", text: "None — I have no real say in my work structure" },
    ],
  },
  {
    id: "wp-q8",
    dimension: "Collaboration Style",
    text: "When it comes to doing your best work, you tend to…",
    options: [
      { id: "wp-q8-a", text: "Work alone for most of it, then share when it's ready" },
      { id: "wp-q8-b", text: "Collaborate closely throughout — input at every stage" },
      { id: "wp-q8-c", text: "Start solo, then bring others in at key decision points" },
      { id: "wp-q8-d", text: "Think out loud with others — real-time collaboration is where I do my best thinking" },
    ],
  },
  {
    id: "wp-q9",
    dimension: "Feedback Orientation",
    text: "When someone gives you critical feedback on your work, your first instinct is…",
    options: [
      { id: "wp-q9-a", text: "To listen and adapt — I find it genuinely useful" },
      { id: "wp-q9-b", text: "To understand their perspective before deciding what to do with it" },
      { id: "wp-q9-c", text: "To evaluate whether the source is credible before I weight it" },
      { id: "wp-q9-d", text: "To feel it first, then process it over time" },
    ],
  },
  {
    id: "wp-q10",
    dimension: "Role Clarity",
    text: "How clearly do you understand what success looks like in your current role?",
    options: [
      { id: "wp-q10-a", text: "Very clearly — I know exactly what good looks like" },
      { id: "wp-q10-b", text: "Mostly — there are a few areas that feel ambiguous" },
      { id: "wp-q10-c", text: "Not very — success seems to shift depending on who's asking" },
      { id: "wp-q10-d", text: "Not at all — I'm often uncertain whether I'm doing well" },
    ],
  },
  {
    id: "wp-q11",
    dimension: "Growth Alignment",
    text: "How closely does your day-to-day work align with the skills or direction you actually want to grow in?",
    options: [
      { id: "wp-q11-a", text: "Closely — I'm building the things I care about" },
      { id: "wp-q11-b", text: "Partially — some of it tracks, some of it doesn't" },
      { id: "wp-q11-c", text: "Not much — I'm developing skills I don't particularly want" },
      { id: "wp-q11-d", text: "Barely — my growth is almost entirely incidental" },
    ],
  },
  {
    id: "wp-q12",
    dimension: "Growth Alignment",
    text: "When you picture yourself two years from now, does your current work feel like it's moving you there?",
    options: [
      { id: "wp-q12-a", text: "Yes — I can draw a clear line from here to there" },
      { id: "wp-q12-b", text: "Somewhat — I can see a path but it's indirect" },
      { id: "wp-q12-c", text: "Not really — I'm not sure this trajectory leads where I want" },
      { id: "wp-q12-d", text: "No — I feel like I'm moving in a different or unclear direction" },
    ],
  },
];
