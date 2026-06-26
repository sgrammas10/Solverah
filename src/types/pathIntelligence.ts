export type CareerStatus = "employed" | "between_jobs" | "first_job";

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
