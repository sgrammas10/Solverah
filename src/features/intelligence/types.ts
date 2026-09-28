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
  /**
   * W-16. The user's own skills this occupation uses, as the scorer found
   * them. On the wire so the server can write the fallback sentence after the
   * card; the SPA does not render it. Optional for `reasons`' reason.
   */
  overlapping_skills?: string[];
  /**
   * W-16, CLIENT-SIDE ONLY -- the server never sends it. Set by the page on a
   * card whose `why_text` is still being written, so the card shows a
   * placeholder line in its place instead of a sentence that would change
   * under the reader. See `PathIntelligencePage`'s `narrating`.
   */
  sentence_pending?: boolean;
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
  /**
   * W-16. True while some card's `why_text` is still being written: the list
   * is scored and shown first, and the sentences land in place a few seconds
   * later. Optional because every payload written before W-16 lacks it, and
   * absent reads as false -- the correct default for those.
   */
  narration_pending?: boolean;
}
