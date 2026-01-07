"""Resume parser (rule-based, offline).

Public API:
- parse_resume(text: str) -> dict

Key heuristics (high-level):
- Section-scoped extraction: skills are parsed only inside the Skills section; experience
  only inside the Experience section. This prevents "skills" pollution from summary/contact.
- Experience entries are anchored on *date range lines* and infer title/company from nearby
  header lines above the date.

Deterministic and offline by construction.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict, Counter
from collections.abc import Mapping, Sequence

from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# ---------------------------- Normalization helpers ----------------------------


def _normalize_text(text: str) -> str:
    """Normalize bullets/dashes/whitespace for PDF-extracted text."""
    replacements = {
        "·": "-",
        "": "-",
        "●": "-",
        "•": "-",
        "–": "-",
        "—": "-",
        " ": " ",
        # common PDF extraction artifacts
        "Š": "-",
        "Œ": "-",
    }
    for src, tgt in replacements.items():
        text = text.replace(src, tgt)

    # De-hyphenate common PDF line breaks: "co-\nmputer" -> "computer"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Collapse whitespace
    text = re.sub(r"[\t\f\r]+", " ", text)
    text = re.sub(r" +", " ", text)
    return text


def _lines(text: str) -> List[str]:
    normalized = _normalize_text(text)
    return [line.strip() for line in normalized.split("\n")]


def _strip_bullet(line: str) -> str:
    return re.sub(r"^(?:[-*]\s+)+", "", line).strip()


# ---------------------------- Shared patterns ----------------------------------


MONTHS = {
    "jan",
    "january",
    "feb",
    "february",
    "mar",
    "march",
    "apr",
    "april",
    "may",
    "jun",
    "june",
    "jul",
    "july",
    "aug",
    "august",
    "sep",
    "sept",
    "september",
    "oct",
    "october",
    "nov",
    "november",
    "dec",
    "december",
}

MONTH_PATTERN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{2,4}"
)
NUMERIC_PATTERN = r"\d{1,2}/\d{2,4}"
YEAR_PATTERN = r"\d{4}"
RANGE_SEP = r"\s*(?:to|-)\s*"

DATE_PATTERN = re.compile(
    rf"(?:(?:{MONTH_PATTERN}|{NUMERIC_PATTERN}){RANGE_SEP}(?:Present|Current|Now|{MONTH_PATTERN}|{NUMERIC_PATTERN}|{YEAR_PATTERN})"
    rf"|{YEAR_PATTERN}{RANGE_SEP}(?:Present|Current|Now|{YEAR_PATTERN})"
    rf"|{MONTH_PATTERN}|{NUMERIC_PATTERN})",
    flags=re.IGNORECASE,
)

DEGREE_PATTERN = re.compile(
    r"\b((b\.?a\.?|b\.?s\.?|b\.tech|bachelor|bs|ba|ms|m\.?s\.?|m\.sc|master|mba|ph\.?d|phd|associate|beng|meng|jd|md))\b",
    flags=re.IGNORECASE,
)

EDU_INSTITUTION_PATTERN = re.compile(
    r"\b(university|college|institute|school|academy|polytechnic|tech)\b",
    flags=re.IGNORECASE,
)

CLEARANCE_PATTERN = re.compile(
    r"\b(clearance|secret|ts/sci|public trust|us citizen|citizenship|work authorization|authorized to work)\b",
    flags=re.IGNORECASE,
)

# Headings
HEADING_EXPERIENCE = re.compile(r"^(professional\s+experience|work\s+experience|experience)\b", re.I)
HEADING_SKILLS = re.compile(r"^(technical\s+skills|skills|technologies|tools)\b", re.I)
HEADING_EDU = re.compile(r"^education\b", re.I)
HEADING_PROJECTS = re.compile(r"^projects?\b", re.I)
HEADING_CERTS = re.compile(r"^certifications?\b", re.I)

MASTER_HEADING = re.compile(
    r"^(professional\s+summary|summary|technical\s+skills|skills|technologies|tools|"
    r"professional\s+experience|work\s+experience|experience|education|projects?|"
    r"certifications?|publications?|volunteer\s+experience|additional\s+information)\b",
    re.I,
)

STOPWORDS: Set[str] = {
    "and",
    "or",
    "of",
    "in",
    "for",
    "the",
    "with",
    "to",
    "on",
    "at",
    "a",
    "an",
    "by",
    "from",
    "as",
    "&",
}

INLINE_TITLE_DATE = re.compile(
    r"^(?P<title>[A-Za-z][A-Za-z /&\-]{3,60})\s*\((?P<dates>[^)]+)\)$"
)
INLINE_TITLE_PIPE_DATE = re.compile(
    r"^(?P<title>[A-Za-z][A-Za-z /&\-]{3,60})\s*\|\s*(?P<dates>.+)$"
)



# ---------------------------- Utility functions --------------------------------


def _looks_like_heading(line: str) -> bool:
    """True only for *section* headings (not job titles)."""
    stripped = line.strip()
    if not stripped:
        return False
    return bool(MASTER_HEADING.match(stripped))


def _is_month_or_year_token(s: str) -> bool:
    token = re.sub(r"[^\w]", "", s.strip().lower())
    if token in MONTHS:
        return True
    return bool(re.fullmatch(r"\d{4}", token))


def _is_bad_title_candidate(line: str) -> bool:
    """Reject lines that look like dates or fillers when used as job titles."""
    s = line.strip()
    if not s:
        return True
    if DATE_PATTERN.fullmatch(s) or DATE_PATTERN.search(s):
        return True
    if _is_month_or_year_token(s):
        return True
    if re.fullmatch(r"(present|current|now)", s, flags=re.I):
        return True
    if re.search(r"\b(graduated|relevant coursework)\b", s, flags=re.I):
        return True
    return False


US_STATE = re.compile(r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b", re.I)

def _split_company_location(line: str) -> str:
    """Return company name from a 'Company - Location' or 'Company, Location' style line."""
    cleaned = line.strip().strip(" -|•")
    if not cleaned:
        return ""

    # 1) Split on dash-like separators first: "Company — City, ST" / "Company – City" / "Company - City"
    dash_parts = re.split(r"\s*(?:—|–|-)\s+", cleaned, maxsplit=1)
    left = dash_parts[0].strip()

    # 2) If there's a comma and the RHS looks like a location, drop it: "Company, Hartford CT"
    if "," in left:
        maybe_company, maybe_loc = [p.strip() for p in left.split(",", 1)]
        # Heuristic: treat as location if it contains a US state code or is short (e.g., "Hartford CT")
        if US_STATE.search(maybe_loc) or len(maybe_loc.split()) <= 4:
            return maybe_company

    # Also handle the case where the comma is in the original cleaned string, not the dash-left:
    if "," in cleaned:
        maybe_company, maybe_loc = [p.strip() for p in cleaned.split(",", 1)]
        if US_STATE.search(maybe_loc) or len(maybe_loc.split()) <= 4:
            return maybe_company

    return left



def _unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            ordered.append(item.strip())
    return ordered


def _find_section_span(lines: Sequence[str], heading_re: re.Pattern[str]) -> Tuple[int, int] | None:
    """Return (start, end) span of a section (excluding heading line).

    Section termination uses only *known* section headings, not generic ALL-CAPS
    lines (job titles are often ALL-CAPS).
    """
    start = None
    for i, line in enumerate(lines):
        if heading_re.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return None

    end = len(lines)
    for j in range(start, len(lines)):
        if MASTER_HEADING.match(lines[j].strip()):
            end = j
            break
    return start, end


def _parse_skill_categories(lines: Sequence[str]) -> Dict[str, List[str]]:
    span = _find_section_span(lines, HEADING_SKILLS)
    scoped = lines[span[0] : span[1]] if span else []
    if not scoped:
        return {}

    categories: Dict[str, List[str]] = defaultdict(list)
    inline_label_re = re.compile(r"^([A-Za-z0-9][A-Za-z0-9 &/+\-]{0,60}):\s*(\S.*)$")

    current_label: str | None = None
    for line in scoped:
        s = line.strip()
        if not s or _looks_like_heading(s):
            current_label = None
            continue

        m = inline_label_re.match(s)
        if m:
            current_label = m.group(1).strip()
            content = m.group(2).strip()
            for tok in _tokenize_list_content(content):
                if _is_plausible_skill_item(tok):
                    categories[current_label].append(tok)
            continue

        if current_label:
            for tok in _tokenize_list_content(s):
                if _is_plausible_skill_item(tok):
                    categories[current_label].append(tok)
        else:
            for tok in _tokenize_list_content(s):
                if _is_plausible_skill_item(tok):
                    categories["Skills"].append(tok)

    for k, v in list(categories.items()):
        categories[k] = _unique_preserve_order(v)

    return dict(categories)

def _flatten_skill_categories(categories: Mapping[str, Sequence[str]]) -> List[str]:
    skills: List[str] = []
    for items in categories.values():
        skills.extend(items)
    return _unique_preserve_order(skills)

def _is_plausible_skill_item(token: str) -> bool:
    """Heuristic filter for list-like skill/tool items (industry-agnostic)."""
    t = re.sub(r"\s+", " ", token.strip(" \t-•*")).strip()
    if not t:
        return False

    if _looks_like_contact_or_noise(t):
        return False

    # Reject headings/labels accidentally tokenized as items
    if t.endswith(":") or _looks_like_heading(t):
        return False

    lower = t.lower()

    # Reject pure stopwords / very short junk
    if lower in STOPWORDS:
        return False
    if len(t) < 2:
        return False

    # Reject long sentences / obviously not a “list item”
    if len(t) > 70:
        return False
    if len(t.split()) > 7:
        return False

    # Reject “Location: …” style fragments
    if re.match(r"^(location|phone|email|linkedin|github)\b", lower):
        return False

    # Reject standalone years/months
    if _is_month_or_year_token(t):
        return False

    return True



# ---------------------------- Years of experience -------------------------------


def _parse_years_experience(text: str) -> int | float | None:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs)\b", text, flags=re.IGNORECASE)
    numeric = [float(m) for m in matches]
    if not numeric:
        return None
    max_years = max(numeric)
    return int(max_years) if max_years.is_integer() else max_years

def _years_from_duration(duration: str) -> float | None:
    """
    Convert duration strings like:
    - 2014-2018
    - 2018-Present
    - June 2019 - May 2021
    into approximate years.
    """
    if not duration:
        return None

    now_year = datetime.now().year

    # Normalize separators
    s = duration.lower().replace("–", "-").replace("—", "-")

    # Year-year or year-present
    m = re.search(r"(\d{4})\s*-\s*(present|current|now|\d{4})", s)
    if m:
        start = int(m.group(1))
        end = now_year if not m.group(2).isdigit() else int(m.group(2))
        if end >= start:
            return float(end - start)

    return None


# ---------------------------- Experience extraction -----------------------------


def _collect_date_anchors(lines: Sequence[str]) -> List[int]:
    return [i for i, line in enumerate(lines) if DATE_PATTERN.search(line)]


def _infer_title_company_from_context(
    lines: Sequence[str],
    date_idx: int,
    lookback: int = 6,
) -> Tuple[str, str]:
    
    """Infer (title, company) from lines immediately above a date line."""
    title = ""
    company = ""
    date_line = lines[date_idx].strip()

    m = INLINE_TITLE_DATE.match(date_line)
    if m:
        title = m.group("title").strip()
    else:
        m2 = INLINE_TITLE_PIPE_DATE.match(date_line)
        if m2:
            title = m2.group("title").strip()
        else:
            title = ""

    start = max(0, date_idx - lookback)
    window = [l for l in lines[start:date_idx] if l.strip()]

    
    if date_idx + 1 < len(lines):
        below = lines[date_idx + 1].strip()
        if below and not _looks_like_heading(below) and not below.lstrip().startswith(("-", "*")):
            company = _split_company_location(below)

    for cand in reversed(window):
        if cand.isupper() and len(cand.split()) <= 8 and not _looks_like_heading(cand) and not _is_bad_title_candidate(cand):
            title = cand.title()
            break

    if not company:
        for cand in reversed(window):
            if _looks_like_heading(cand):
                continue
            lower = cand.lower()
            if any(s in lower for s in (" inc", " llc", " ltd", " technologies", " labs", " analytics", " corp", " company")) or " - " in cand:
                company = _split_company_location(cand)
                break

    if not company and window:
        for cand in reversed(window):
            s = cand.strip()
            if not s:
                continue
            if _looks_like_heading(s):
                continue
            if _is_bad_title_candidate(s):
                continue
            # Avoid swallowing competency labels / prose / bullets
            if ":" in s:
                continue
            if s.lstrip().startswith(("-", "*")):
                continue
            if len(s) > 80 or len(s.split()) > 12:
                continue
            company = _split_company_location(s)
            break

    if _is_bad_title_candidate(title):
        title = ""
    if _is_bad_title_candidate(company):
        company = ""

    return title, company


def _parse_experience(lines: Sequence[str]) -> List[Dict[str, object]]:
    experiences: List[Dict[str, object]] = []

    span = _find_section_span(lines, HEADING_EXPERIENCE)
    scoped = lines[span[0] : span[1]] if span else lines

    date_idxs = _collect_date_anchors(scoped)
    if not date_idxs:
        return experiences

    for k, date_idx in enumerate(date_idxs):
        date_line = scoped[date_idx]
        duration_match = DATE_PATTERN.search(date_line)
        duration = duration_match.group(0).strip() if duration_match else ""

        title, company = _infer_title_company_from_context(scoped, date_idx)

        end_idx = date_idxs[k + 1] if k + 1 < len(date_idxs) else len(scoped)
        impact_bullets: List[str] = []
        for line in scoped[date_idx + 1 : end_idx]:
            if _looks_like_heading(line):
                break

            # Stop when the next role header starts.
            if line.isupper() and len(line.split()) <= 8 and not line.lstrip().startswith(("-", "*")):
                break

            # Prefer true bullets to avoid swallowing the next role's header lines.
            if not re.match(r"^\s*[-*]\s+", line):
                continue

            cleaned = _strip_bullet(line)
            if cleaned:
                impact_bullets.append(cleaned)

        if not (title or company or impact_bullets):
            continue

        experiences.append(
            {
                "title": title,
                "company": company,
                "duration": duration,
                "impact_bullets": impact_bullets,
            }
        )

    return experiences


# ---------------------------- Education extraction ------------------------------


def _parse_education(lines: Sequence[str]) -> str:
    span = _find_section_span(lines, HEADING_EDU)
    scoped = lines[span[0] : span[1]] if span else lines

    edu_lines: List[str] = []
    for idx, line in enumerate(scoped):
        if DEGREE_PATTERN.search(line) or EDU_INSTITUTION_PATTERN.search(line):
            combined = line
            if idx + 1 < len(scoped) and scoped[idx + 1] and len(scoped[idx + 1]) < 140 and not _looks_like_heading(scoped[idx + 1]):
                combined = combined + " " + scoped[idx + 1].strip()
            edu_lines.append(combined.strip())

    return "\n".join(_unique_preserve_order(edu_lines))


# ---------------------------- Skills extraction -------------------------


def _looks_like_contact_or_noise(token: str) -> bool:
    lower = token.lower()
    if "@" in token or "http" in lower or "www." in lower:
        return True
    if re.search(r"\b\d{3}[\s.-]?\d{3}[\s.-]?\d{4}\b", token):
        return True
    if re.search(r"\b(present|current)\b", lower):
        return True
    if token.strip().lower() in MONTHS:
        return True
    letters = sum(c.isalpha() for c in token)
    digits = sum(c.isdigit() for c in token)
    return digits > letters and digits >= 2


def _tokenize_list_content(s: str) -> List[str]:
    """Tokenize comma/pipe/semicolon separated lists without breaking hyphenated tech."""
    parts = re.split(r"\s*(?:,|;|\||/|\\)\s*", s)
    out: List[str] = []

    for part in parts:
        cleaned = re.sub(r"\s+", " ", part.strip().strip("•* -"))
        if not cleaned:
            continue

        # Handle "AWS (EC2" split artifact from "AWS (EC2, S3, Lambda)"
        if " (" in cleaned and cleaned.count("(") == 1 and cleaned.count(")") == 0:
            left, right = cleaned.split(" (", 1)
            left = left.strip()
            right = right.strip()
            if left:
                out.append(left)
            if right:
                out.append(right)
            continue

        # Only strip orphan parentheses produced by splitting.
        if cleaned.startswith("(") and cleaned.count(")") == 0:
            cleaned = cleaned[1:].strip()
        if cleaned.endswith(")") and cleaned.count("(") == 0:
            cleaned = cleaned[:-1].strip()

        out.append(cleaned)

    return out


# ---------------------------- Projects / certifications -------------------------


def _parse_projects(lines: Sequence[str]) -> List[str]:
    span = _find_section_span(lines, HEADING_PROJECTS)
    scoped = lines[span[0] : span[1]] if span else []
    projects: List[str] = []
    for line in scoped:
        cleaned = _strip_bullet(line)
        if cleaned and not _looks_like_heading(cleaned):
            projects.append(cleaned)
    return _unique_preserve_order(projects)


def _parse_certifications(lines: Sequence[str]) -> List[str]:
    span = _find_section_span(lines, HEADING_CERTS)
    scoped = lines[span[0] : span[1]] if span else []
    certs: List[str] = []
    for line in scoped:
        cleaned = _strip_bullet(line)
        if cleaned and not _looks_like_heading(cleaned):
            certs.append(cleaned)
    return _unique_preserve_order(certs)


# ---------------------------- Clearance / work auth -----------------------------


def _parse_clearances(text: str) -> str:
    match = CLEARANCE_PATTERN.search(text)
    return match.group(0) if match else ""


# ---------------------------- Main parse function -------------------------------


def parse_resume(text: str) -> Dict[str, object]:
    """Parse resume text into structured fields."""
    line_list = _lines(text)

    explicit_years = _parse_years_experience(text)
    experience = _parse_experience(line_list)

    if explicit_years is not None:
        years_experience = explicit_years
    else:
        years = []
        for exp in experience:
            y = _years_from_duration(exp.get("duration", ""))
            if y:
                years.append(y)
        years_experience = int(sum(years)) if years else 0

    education = _parse_education(line_list)
    projects = _parse_projects(line_list)
    certifications = _parse_certifications(line_list)
    clearances_or_work_auth = _parse_clearances(text)
    skill_categories = _parse_skill_categories(line_list)
    skills = _flatten_skill_categories(skill_categories)

    return {
        "years_experience": years_experience,
        "education": education,
        "skills": skills,
        "skills_by_category": skill_categories,
        "experience": experience,
        "projects": projects,
        "certifications": certifications,
        "clearances_or_work_auth": clearances_or_work_auth,
    }


# ---------------------------- Evaluation harness --------------------------------


def evaluate_on_jsonl(path: Path, sample_size: int | None = 200) -> Dict[str, float]:
    """Run quick recall-oriented metrics over a JSONL of resumes."""
    totals = Counter()
    experience_counts: List[int] = []

    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            if sample_size is not None and idx >= sample_size:
                break
            record = json.loads(line)
            parsed = parse_resume(record.get("text", ""))

            totals["resumes"] += 1
            totals["nonempty_experience"] += bool(parsed["experience"])
            totals["nonempty_skills"] += bool(parsed["skills"])
            totals["nonempty_education"] += bool(parsed["education"])
            experience_counts.append(len(parsed["experience"]))

    resumes = totals.get("resumes", 1)
    return {
        "% with non-empty experience": totals["nonempty_experience"] / resumes,
        "% with non-empty skills/tools": totals["nonempty_skills"] / resumes,
        "% with non-empty education": totals["nonempty_education"] / resumes,
        "avg # experience entries": (sum(experience_counts) / resumes) if experience_counts else 0.0,
    }


__all__ = ["parse_resume", "evaluate_on_jsonl"]
