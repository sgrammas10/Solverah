from pydantic import BaseModel
from typing import Optional


class CompanyOverview(BaseModel):
    name: str
    founded: Optional[int] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None                  # e.g. "enterprise", "mid-size", "startup"
    headquarters: Optional[str] = None
    ownership: Optional[str] = None             # e.g. "Public (NASDAQ: GOOGL)"
    revenue_est: Optional[str] = None
    headcount_est: Optional[str] = None


class Executive(BaseModel):
    name: str
    title: str
    linkedin_url: Optional[str] = None


class CultureValues(BaseModel):
    culture_narrative: Optional[str] = None
    core_values: list[str] = []
    work_environment: Optional[str] = None
    pace: Optional[str] = None
    empathy: Optional[float] = None             # 0.0 – 1.0
    creative_drive: Optional[float] = None
    adaptability: Optional[float] = None
    futuristic: Optional[float] = None
    harmony: Optional[float] = None
    data_orientation: Optional[float] = None


class Compensation(BaseModel):
    new_grad_swe_total: Optional[str] = None
    mid_level_total: Optional[str] = None
    senior_total: Optional[str] = None
    base_range: Optional[str] = None
    equity_notes: Optional[str] = None
    bonus: Optional[str] = None
    levels: Optional[str] = None               # e.g. "L3 → L4 → L5 → L6 → L7"
    notes: Optional[str] = None


class InterviewProcess(BaseModel):
    difficulty: Optional[str] = None           # e.g. "Very High"
    process_overview: Optional[str] = None
    coding_focus: Optional[str] = None
    system_design: Optional[bool] = None
    behavioral: Optional[str] = None
    avg_rounds: Optional[int] = None
    timeline: Optional[str] = None             # e.g. "4–8 weeks"
    notes: Optional[str] = None


class RemotePolicy(BaseModel):
    policy: Optional[str] = None               # e.g. "Hybrid (3 days in office)"
    remote_friendly: Optional[str] = None      # e.g. "Limited", "Yes", "No"
    details: Optional[str] = None


class GlassdoorRatings(BaseModel):
    overall_rating: Optional[float] = None     # out of 5.0
    ceo_approval: Optional[str] = None         # e.g. "87%"
    recommend_to_friend: Optional[str] = None
    work_life_balance: Optional[float] = None
    compensation_score: Optional[float] = None
    culture_score: Optional[float] = None
    key_positives: Optional[str] = None
    key_negatives: Optional[str] = None
    source: Optional[str] = None


class NewsControversies(BaseModel):
    controversy_level: Optional[str] = None    # e.g. "High", "Medium", "Low"
    key_topics: Optional[str] = None
    recent_news: Optional[str] = None


class RecruitingContacts(BaseModel):
    key_programs: Optional[str] = None
    university_recruiting_url: Optional[str] = None
    general_jobs_url: Optional[str] = None
    linkedin_search_tip: Optional[str] = None
    recruiter_tip: Optional[str] = None


class TechStack(BaseModel):
    frontend: Optional[str] = None
    backend: Optional[str] = None
    infrastructure: Optional[str] = None
    data_ml: Optional[str] = None
    devtools_cicd: Optional[str] = None
    notable_oss: Optional[str] = None
    primary_languages: Optional[str] = None
    notes: Optional[str] = None


class InternshipProgram(BaseModel):
    program_exists: Optional[bool] = None
    program_name: Optional[str] = None
    duration_weeks: Optional[str] = None
    roles_available: Optional[str] = None
    weekly_comp_usd: Optional[str] = None
    return_offer_rate: Optional[str] = None    # e.g. "~85%"
    pipeline_to_fulltime: Optional[str] = None
    application_timeline: Optional[str] = None # e.g. "Aug–Jan"
    intern_headcount_est: Optional[str] = None
    notes: Optional[str] = None


class WorkforceSignals(BaseModel):
    warn_activity: Optional[str] = None
    warn_risk_level: Optional[str] = None      # e.g. "Medium"
    warn_analyst_note: Optional[str] = None
    reddit_glassdoor_themes: Optional[str] = None
    linkedin_signals: Optional[str] = None
    news_press_signals: Optional[str] = None
    overall_workforce_risk: Optional[str] = None
    signal_confidence: Optional[str] = None    # e.g. "Pattern-based"
    analyst_summary: Optional[str] = None


class CompanyProfile(BaseModel):
    overview: CompanyOverview
    executives: list[Executive] = []
    culture: Optional[CultureValues] = None
    compensation: Optional[Compensation] = None
    interview: Optional[InterviewProcess] = None
    remote_policy: Optional[RemotePolicy] = None
    glassdoor: Optional[GlassdoorRatings] = None
    news: Optional[NewsControversies] = None
    recruiting: Optional[RecruitingContacts] = None
    tech_stack: Optional[TechStack] = None
    internship: Optional[InternshipProgram] = None
    workforce_signals: Optional[WorkforceSignals] = None
