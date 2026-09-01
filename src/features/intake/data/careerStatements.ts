export interface CareerStatement {
  id: string;
  text: string;
  category: string;
}

export const CAREER_STATEMENTS: CareerStatement[] = [
  { id: "dir-1",  text: "I'm not sure what I want to do next professionally",                               category: "Career Direction & Growth" },
  { id: "job-1",  text: "I'm trying to find companies or environments that actually fit me",               category: "Job Search & Career Movement" },
  { id: "sus-1",  text: "I feel pulled in too many directions at work",                                    category: "Work & Sustainability" },
  { id: "sus-2",  text: "I'm doing fine professionally, but I don't feel as engaged or fulfilled as I used to", category: "Work & Sustainability" },
  { id: "ldr-1",  text: "Different managers bring out different versions of me",                           category: "Leadership & Environment" },
  { id: "stb-1",  text: "I'm trying to understand what a sustainable long-term career path looks like now", category: "Stability, Change & Future Risk" },
  { id: "self-1", text: "I want to better understand how I naturally operate",                             category: "Self-Understanding" },
];
