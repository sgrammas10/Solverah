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
}
