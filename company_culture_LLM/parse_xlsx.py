"""Parse the Solverah Company Profiles spreadsheet into CompanyProfile objects.

Public API:
    parse_all(path) -> list[CompanyProfile]

The spreadsheet layout uses a vertical key-value format per company:
    Row:  '  COMPANY NAME'       <- company header
    Row:  '  SECTION NAME'       <- section header
    Row:  'Field Label', 'Value' <- data row
    Row:  'Name · Title', 'LinkedIn Profile'  <- executive row
"""

from __future__ import annotations

import json
import re
import string
from pathlib import Path
from typing import Optional

import openpyxl

from company import (
    CompanyOverview, CompanyProfile, CultureValues, Compensation,
    Executive, GlassdoorRatings, InternshipProgram, InterviewProcess,
    NewsControversies, RecruitingContacts, RemotePolicy, TechStack,
    WorkforceSignals,
)

# ---------------------------------------------------------------------------
# Known section headers (uppercase, as they appear stripped in the sheet)
# ---------------------------------------------------------------------------

SECTION_HEADERS = {
    "COMPANY OVERVIEW",
    "EXECUTIVE LEADERSHIP",
    "CULTURE & VALUES",
    "COMPENSATION",
    "INTERVIEW PROCESS",
    "REMOTE / HYBRID POLICY",
    "GLASSDOOR / EMPLOYEE RATINGS",
    "RECENT NEWS & CONTROVERSIES",
    "RECRUITING & CONTACTS",
    "TECH STACK",
    "INTERNSHIP PROGRAM",
    "WORKFORCE SIGNALS",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

_BRAND_OVERRIDES = {
    "Openai": "OpenAI",
    "Hubspot": "HubSpot",
    "Palantir Technologies": "Palantir Technologies",
    "Google (Alphabet)": "Google (Alphabet)",
}


def _title(name: str) -> str:
    """Convert ALL-CAPS spreadsheet name to title case, with brand overrides."""
    titled = name.title()
    return _BRAND_OVERRIDES.get(titled, titled)


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> Optional[int]:
    """Parse first integer from a string like '5–6 total'."""
    if val is None:
        return None
    m = re.search(r"\d+", str(val))
    return int(m.group()) if m else None


def _safe_bool(val) -> Optional[bool]:
    if val is None:
        return None
    return str(val).strip().lower().startswith("y")


def _glassdoor_rating(val) -> Optional[float]:
    """Parse '4.3 / 5.0' or '4.3' → 4.3."""
    if val is None:
        return None
    m = re.search(r"\d+\.\d+", str(val))
    return float(m.group()) if m else None


def _system_design(val) -> Optional[bool]:
    if val is None:
        return None
    return str(val).strip().lower().startswith("y")


def _core_values(val) -> list[str]:
    if not val:
        return []
    try:
        parsed = json.loads(str(val))
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    # Fallback: comma-separated
    return [v.strip().strip('"') for v in str(val).split(",") if v.strip()]


# ---------------------------------------------------------------------------
# Row classification
# ---------------------------------------------------------------------------

def _is_header_row(row) -> bool:
    """True if col A starts with two spaces and cols B–D are empty."""
    val = row[0]
    rest = row[1:]
    return (
        isinstance(val, str)
        and val.startswith("  ")
        and all(v is None for v in rest)
    )


def _classify_header(val: str) -> tuple[str, str]:
    """Returns ('company', name) or ('section', name)."""
    stripped = val.strip().upper()
    if stripped in SECTION_HEADERS:
        return "section", stripped
    return "company", val.strip()


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _kv(rows: list[tuple]) -> dict[str, str]:
    """Build a label→value dict from data rows."""
    d: dict[str, str] = {}
    for row in rows:
        label = row[0]
        value = row[1] if len(row) > 1 else None
        if label and value is not None:
            d[str(label).strip()] = str(value).strip()
        elif label:
            d[str(label).strip()] = ""
    return d


def _parse_overview(rows: list[tuple], company_name: str) -> CompanyOverview:
    kv = _kv(rows)
    return CompanyOverview(
        name=_title(company_name),
        founded=_safe_int(kv.get("Founded")),
        website=kv.get("Website") or None,
        industry=kv.get("Industry") or None,
        size=kv.get("Size") or None,
        headquarters=kv.get("Headquarters") or None,
        ownership=kv.get("Ownership") or None,
        revenue_est=kv.get("Revenue (est.)") or None,
        headcount_est=kv.get("Headcount (est.)") or None,
    )


def _parse_executives(rows: list[tuple]) -> list[Executive]:
    execs = []
    for row in rows:
        val = row[0]
        if val and "·" in str(val):
            parts = str(val).split("·", 1)
            name = parts[0].strip()
            title = parts[1].strip() if len(parts) > 1 else ""
            execs.append(Executive(name=name, title=title))
    return execs


def _parse_culture(rows: list[tuple]) -> CultureValues:
    kv = _kv(rows)
    return CultureValues(
        culture_narrative=kv.get("Culture Narrative") or None,
        core_values=_core_values(kv.get("Core Values")),
        work_environment=kv.get("Work Environment") or None,
        pace=kv.get("Pace") or None,
        empathy=_safe_float(kv.get("Empathy")),
        creative_drive=_safe_float(kv.get("Creative Drive")),
        adaptability=_safe_float(kv.get("Adaptability")),
        futuristic=_safe_float(kv.get("Futuristic")),
        harmony=_safe_float(kv.get("Harmony")),
        data_orientation=_safe_float(kv.get("Data Orientation")),
    )


def _parse_compensation(rows: list[tuple]) -> Compensation:
    kv = _kv(rows)
    return Compensation(
        new_grad_swe_total=kv.get("New Grad SWE Total") or None,
        mid_level_total=kv.get("Mid-Level Total") or None,
        senior_total=kv.get("Senior Total") or None,
        base_range=kv.get("Base Range") or None,
        equity_notes=kv.get("Equity Notes") or None,
        bonus=kv.get("Bonus") or None,
        levels=kv.get("Levels") or None,
        notes=kv.get("Notes") or None,
    )


def _parse_interview(rows: list[tuple]) -> InterviewProcess:
    kv = _kv(rows)
    return InterviewProcess(
        difficulty=kv.get("Difficulty") or None,
        process_overview=kv.get("Process Overview") or None,
        coding_focus=kv.get("Coding Focus") or None,
        system_design=_system_design(kv.get("System Design")),
        behavioral=kv.get("Behavioral") or None,
        avg_rounds=_safe_int(kv.get("Avg Rounds")),
        timeline=kv.get("Timeline") or None,
        notes=kv.get("Notes") or None,
    )


def _parse_remote(rows: list[tuple]) -> RemotePolicy:
    kv = _kv(rows)
    return RemotePolicy(
        policy=kv.get("Policy") or None,
        remote_friendly=kv.get("Remote Friendly") or None,
        details=kv.get("Details") or None,
    )


def _parse_glassdoor(rows: list[tuple]) -> GlassdoorRatings:
    kv = _kv(rows)
    return GlassdoorRatings(
        overall_rating=_glassdoor_rating(kv.get("Overall Rating")),
        ceo_approval=kv.get("CEO Approval") or None,
        recommend_to_friend=kv.get("Recommend to Friend") or None,
        work_life_balance=_safe_float(kv.get("Work-Life Balance")),
        compensation_score=_safe_float(kv.get("Compensation Score")),
        culture_score=_safe_float(kv.get("Culture Score")),
        key_positives=kv.get("Key Positives") or None,
        key_negatives=kv.get("Key Negatives") or None,
        source=kv.get("Source") or None,
    )


def _parse_news(rows: list[tuple]) -> NewsControversies:
    kv = _kv(rows)
    return NewsControversies(
        controversy_level=kv.get("Controversy Level") or None,
        key_topics=kv.get("Key Topics") or None,
        recent_news=kv.get("Recent News") or None,
    )


def _parse_recruiting(rows: list[tuple]) -> RecruitingContacts:
    kv = _kv(rows)
    return RecruitingContacts(
        key_programs=kv.get("Key Programs") or None,
        university_recruiting_url=kv.get("University Recruiting") or None,
        general_jobs_url=kv.get("General Jobs Page") or None,
        linkedin_search_tip=kv.get("LinkedIn Search Tip") or None,
        recruiter_tip=kv.get("Recruiter Tip") or None,
    )


def _parse_tech_stack(rows: list[tuple]) -> TechStack:
    kv = _kv(rows)
    return TechStack(
        frontend=kv.get("Frontend") or None,
        backend=kv.get("Backend") or None,
        infrastructure=kv.get("Infrastructure") or None,
        data_ml=kv.get("Data / ML") or None,
        devtools_cicd=kv.get("DevTools / CI/CD") or None,
        notable_oss=kv.get("Notable OSS") or None,
        primary_languages=kv.get("Primary Languages") or None,
        notes=kv.get("Notes") or None,
    )


def _parse_internship(rows: list[tuple]) -> InternshipProgram:
    kv = _kv(rows)
    return InternshipProgram(
        program_exists=_safe_bool(kv.get("Program Exists")),
        program_name=kv.get("Program Name") or None,
        duration_weeks=kv.get("Duration") or None,
        roles_available=kv.get("Roles Available") or None,
        weekly_comp_usd=kv.get("Weekly Comp (USD)") or None,
        return_offer_rate=kv.get("Return Offer Rate") or None,
        pipeline_to_fulltime=kv.get("Pipeline to Full-Time") or None,
        application_timeline=kv.get("Application Timeline") or None,
        intern_headcount_est=kv.get("Intern Headcount Est.") or None,
        notes=kv.get("Notes") or None,
    )


def _parse_workforce(rows: list[tuple]) -> WorkforceSignals:
    kv = _kv(rows)
    return WorkforceSignals(
        warn_activity=kv.get("WARN Activity") or None,
        warn_risk_level=kv.get("WARN Risk Level") or None,
        warn_analyst_note=kv.get("WARN Analyst Note") or None,
        reddit_glassdoor_themes=kv.get("Reddit / Glassdoor Themes") or None,
        linkedin_signals=kv.get("LinkedIn Signals") or None,
        news_press_signals=kv.get("News / Press Signals") or None,
        overall_workforce_risk=kv.get("Overall Workforce Risk") or None,
        signal_confidence=kv.get("Signal Confidence") or None,
        analyst_summary=kv.get("Analyst Summary") or None,
    )


# ---------------------------------------------------------------------------
# Block assembler
# ---------------------------------------------------------------------------

_SECTION_PARSERS = {
    "COMPENSATION": _parse_compensation,
    "INTERVIEW PROCESS": _parse_interview,
    "REMOTE / HYBRID POLICY": _parse_remote,
    "GLASSDOOR / EMPLOYEE RATINGS": _parse_glassdoor,
    "RECENT NEWS & CONTROVERSIES": _parse_news,
    "RECRUITING & CONTACTS": _parse_recruiting,
    "TECH STACK": _parse_tech_stack,
    "INTERNSHIP PROGRAM": _parse_internship,
    "WORKFORCE SIGNALS": _parse_workforce,
}


def _build_profile(company_name: str, sections: dict[str, list[tuple]]) -> CompanyProfile:
    overview = _parse_overview(sections.get("COMPANY OVERVIEW", []), company_name)
    executives = _parse_executives(sections.get("EXECUTIVE LEADERSHIP", []))
    culture = _parse_culture(sections.get("CULTURE & VALUES", []))

    kwargs: dict = {
        "overview": overview,
        "executives": executives,
        "culture": culture,
    }

    for section_key, parser_fn in _SECTION_PARSERS.items():
        rows = sections.get(section_key, [])
        if rows:
            field = {
                "COMPENSATION": "compensation",
                "INTERVIEW PROCESS": "interview",
                "REMOTE / HYBRID POLICY": "remote_policy",
                "GLASSDOOR / EMPLOYEE RATINGS": "glassdoor",
                "RECENT NEWS & CONTROVERSIES": "news",
                "RECRUITING & CONTACTS": "recruiting",
                "TECH STACK": "tech_stack",
                "INTERNSHIP PROGRAM": "internship",
                "WORKFORCE SIGNALS": "workforce_signals",
            }[section_key]
            kwargs[field] = parser_fn(rows)

    return CompanyProfile(**kwargs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_all(path: str | Path = None) -> list[CompanyProfile]:
    """Parse all company profiles from the xlsx and return CompanyProfile list.

    Args:
        path: Path to the xlsx file. Defaults to docs/Solverah Company Profiles SEB.xlsx
              relative to the project root (two levels up from this file).
    """
    if path is None:
        path = Path(__file__).resolve().parent.parent / "docs" / "Solverah Company Profiles SEB.xlsx"

    wb = openpyxl.load_workbook(str(path), read_only=True)
    ws = wb["Company Profiles"]
    all_rows = [tuple(row) for row in ws.iter_rows(values_only=True)]

    profiles: list[CompanyProfile] = []
    current_company: str | None = None
    current_section: str | None = None
    sections: dict[str, list[tuple]] = {}

    def _flush():
        nonlocal current_company, current_section, sections
        if current_company:
            profiles.append(_build_profile(current_company, sections))
        current_company = None
        current_section = None
        sections = {}

    for row in all_rows:
        if _is_header_row(row):
            kind, name = _classify_header(row[0])
            if kind == "company":
                _flush()
                current_company = name
                sections = {}
            else:
                current_section = name
                sections[current_section] = []
        elif current_section is not None and any(v is not None for v in row):
            sections[current_section].append(row)

    _flush()  # last company
    return profiles
