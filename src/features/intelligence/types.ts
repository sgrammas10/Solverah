export type CareerStatus = "employed" | "between_jobs" | "first_job";

export type MoveIntent = "stay_in_field" | "adjacent" | "fresh_start";
export type SeniorityIntent = "move_up" | "stay_lateral" | "open";
export type Priority = "pay_title" | "interesting_work" | "work_life_balance" | "learning_growth";

export interface PathPreferences {
  move_intent: MoveIntent;
  seniority_intent: SeniorityIntent;
  priority: Priority;
}

export interface PathSuggestion {
  onet_code: string;
  title: string;
  why_text: string;
  profile_dimensions: string[];
  match_score: number;
}

export interface PathSuggestionsResponse {
  suggestions: PathSuggestion[];
  career_status: CareerStatus;
  generated_at: string;
  /**
   * F-6. Every inline judgement standing for this user, `onet_code -> verdict`.
   *
   * Optional because a payload cached before F-6 shipped will not carry it, and
   * because `POST /me/path-suggestion-jobs` results are read through this same
   * shape. Absent reads as "no judgements", which is the correct default.
   */
  feedback?: Record<string, string>;
}
