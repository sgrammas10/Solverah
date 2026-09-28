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
  /**
   * W-4. At most two plain-words phrases saying what is distinctive about this
   * card against the user's own job -- the line that goes where the percentage
   * was until W-1.
   *
   * Optional for `feedback`'s reason and one more: a payload cached before W-4
   * shipped will not carry it, and an empty list is the normal answer rather
   * than an error. A phrase that would read the same on most of the page says
   * nothing about any card and is dropped from all of them, and a user who has
   * stated no wants gets no reason line at all -- so a card renders with none
   * far more often than it renders with two.
   */
  reasons?: string[];
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
