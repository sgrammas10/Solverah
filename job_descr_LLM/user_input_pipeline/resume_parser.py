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
        "?": "-",
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

    # Join stacked headings like "PROFESSIONAL\nSUMMARY".
    text = re.sub(r"(?mi)\bPROFESSIONAL\s*\n\s*SUMMARY\b", "PROFESSIONAL SUMMARY", text)
    text = re.sub(r"(?mi)\bSKILLS\s*\n\s*SUMMARY\b", "SKILLS SUMMARY", text)
    text = re.sub(r"(?mi)\bWORK\s*\n\s*HISTORY\b", "WORK HISTORY", text)

    # If a heading shares a line with content, split it onto its own line.
    inline_headings = [
        "PROFESSIONAL SUMMARY",
        "SUMMARY",
        "SKILLS SUMMARY",
        "SKILLS",
        "WORK HISTORY",
        "EXPERIENCE",
        "PROFESSIONAL EXPERIENCE",
        "WORK EXPERIENCE",
        "RELEVANT EXPERIENCE",
        "EDUCATION",
        "PROJECTS",
        "CERTIFICATIONS",
        "LICENSURE & CERTIFICATIONS",
        "LICENSES & CERTIFICATIONS",
        "TECHNICAL SKILLS",
        "RELEVANT SKILLS",
        "CLINICAL SKILLS",
        "TOOLS",
        "TECHNOLOGIES",
        "ADDITIONAL INFORMATION",
        "PUBLICATIONS",
        "VOLUNTEER EXPERIENCE",
    ]
    for heading in inline_headings:
        if heading == "SKILLS":
            pattern = re.compile(r"(?im)^(?P<h>SKILLS)(?!\s+SUMMARY)\s+(?=\S)")
        else:
            pattern = re.compile(rf"(?im)^(?P<h>{re.escape(heading)})\s+(?=\S)")
        text = pattern.sub(r"\g<h>\n", text)

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

MULTI_SUMMER_RANGE = re.compile(
    rf"(?P<start>{MONTH_PATTERN})\s*[–—-]\s*(?P<end>{MONTH_PATTERN})\s+(?P<y1>\d{{4}})\s*,\s*(?P<y2>\d{{4}})",
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
HEADING_EXPERIENCE = re.compile(
    r"^(professional\s+experience|work\s+experience|relevant\s+experience|experience|work\s+history)\b",
    re.I,
)
HEADING_SKILLS = re.compile(
    r"^(skills\s+summary|technical\s+skills|relevant\s+skills|clinical\s+skills|skills|technologies|tools)\b",
    re.I,
)
HEADING_EDU = re.compile(r"^education\b", re.I)
HEADING_PROJECTS = re.compile(r"^projects?\b", re.I)
HEADING_CERTS = re.compile(r"^(licensure\s*&\s*certifications|licensure|licenses?\s*&\s*certifications|certifications?)\b", re.I)
HEADING_VOLUNTEER = re.compile(r"^volunteer\s+experience\b", re.I)

MASTER_HEADING = re.compile(
    r"^(professional\s+summary|summary|skills\s+summary|technical\s+skills|clinical\s+skills|skills|technologies|tools|"
    r"relevant\s+skills|professional\s+experience|work\s+experience|relevant\s+experience|experience|work\s+history|education|projects?|"
    r"(licensure\s*&\s*certifications|licensure|licenses?\s*&\s*certifications|certifications?)|publications?|volunteer\s+experience|additional\s+information)\b",
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
    return _is_clean_heading_line(stripped, MASTER_HEADING)


def _is_clean_heading_line(line: str, heading_re: re.Pattern[str]) -> bool:
    stripped = line.strip()
    match = heading_re.match(stripped)
    if not match:
        return False
    remainder = stripped[match.end() :].strip(" :|-")
    return remainder == ""


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
    dash_parts = re.split(r"\s*(?:-|\|)\s+", cleaned, maxsplit=1)
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

def _looks_like_location_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if "," not in s:
        return False
    if not US_STATE.search(s):
        return False
    return len(s.split()) <= 5


def _looks_like_cert_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    lower = s.lower()
    if re.search(r"\b(cert|certified|certification|license|licensed|licensure|credential|registered)\b", lower):
        return True
    if re.search(r"\([A-Z]{2,6}\)", s):
        return True
    return False



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
        if _is_clean_heading_line(line, heading_re):
            start = i + 1
            break
    if start is None:
        return None

    end = len(lines)
    for j in range(start, len(lines)):
        if _is_clean_heading_line(lines[j], MASTER_HEADING):
            end = j
            break
    return start, end


def _parse_skill_categories(lines: Sequence[str]) -> Dict[str, List[str]]:
    span = _find_section_span(lines, HEADING_SKILLS)
    scoped = lines[span[0] : span[1]] if span else []
    if not scoped:
        return {}

    def _should_merge_skill_lines(prev: str, nxt: str) -> bool:
        prev_s = prev.strip()
        nxt_s = nxt.strip()
        if not prev_s or not nxt_s:
            return False
        if _looks_like_heading(prev_s) or _looks_like_heading(nxt_s):
            return False
        if re.search(r":\s*\S", prev_s) or re.search(r":\s*\S", nxt_s):
            return False
        if prev_s.lstrip().startswith(("-", "*")) or nxt_s.lstrip().startswith(("-", "*")):
            return False
        if "," in prev_s and nxt_s and nxt_s[0].islower():
            return True
        if prev_s.endswith(("and", "&")):
            return True
        return False

    merged_scoped: List[str] = []
    buffer = ""
    for line in scoped:
        s = line.strip()
        if not s or _looks_like_heading(s):
            if buffer:
                merged_scoped.append(buffer)
                buffer = ""
            continue
        if buffer and _should_merge_skill_lines(buffer, s):
            buffer = f"{buffer} {s}"
            continue
        if buffer:
            merged_scoped.append(buffer)
        buffer = s
    if buffer:
        merged_scoped.append(buffer)

    categories: Dict[str, List[str]] = defaultdict(list)
    inline_label_re = re.compile(r"^([A-Za-z0-9][A-Za-z0-9 &/+\-]{0,60}):\s*(\S.*)$")

    current_label: str | None = None
    for line in merged_scoped:
        s = line.strip()
        if not s or _looks_like_heading(s):
            current_label = None
            continue

        m = inline_label_re.match(s)
        if m:
            current_label = m.group(1).strip()
            content = _strip_skill_leadin(m.group(2).strip())
            for tok in _tokenize_list_content(content):
                if _is_plausible_skill_item(tok):
                    categories[current_label].append(tok)
            continue

        if current_label:
            for tok in _tokenize_list_content(_strip_skill_leadin(s)):
                if _is_plausible_skill_item(tok):
                    categories[current_label].append(tok)
        else:
            for tok in _tokenize_list_content(_strip_skill_leadin(s)):
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

def _strip_skill_leadin(s: str) -> str:
    """Remove common lead-in phrases to surface list-like skill fragments."""
    if not s:
        return s
    lower = s.lower()
    leadins = [
        r"\bwell-versed in(?: the use of)?\b",
        r"\bexperienced in\b",
        r"\bexperience in\b",
        r"\bproficient in\b",
        r"\bskilled in\b",
        r"\bknowledge of\b",
        r"\bfamiliar with\b",
        r"\bexpertise in\b",
        r"\busing\b",
        r"\butilizing\b",
        r"\bincluding\b",
    ]
    # Strip everything up to the last lead-in if the remainder looks list-like.
    last_match = None
    for pat in leadins:
        for m in re.finditer(pat, lower):
            last_match = m
    if last_match:
        remainder = s[last_match.end() :].strip(" :;-")
        if "." in remainder:
            remainder = remainder.split(".", 1)[0].strip()
        if re.search(r"[;,]|\\band\\b", remainder, flags=re.IGNORECASE):
            return remainder
    return s

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
        if lower in {"location", "phone", "email", "linkedin", "github"}:
            return False
        if ":" in lower:
            return False

    # Reject standalone years/months
    if _is_month_or_year_token(t):
        return False

    return True



# ---------------------------- Years of experience -------------------------------


def _parse_years_experience(text: str) -> int | float | None:
    patterns = [
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs)\s+of\s+experience\b",
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs)\s+experience\b",
        r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs)\b",
    ]
    matches: list[str] = []
    for pat in patterns:
        matches.extend(re.findall(pat, text, flags=re.IGNORECASE))
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
    - 08/2020 to CURRENT
    - 02/2019 to 08/2020
    - June 2019 - May 2021
    into approximate years.
    """
    if not duration:
        return None

    now = datetime.now()
    now_year = now.year
    now_month = now.month

    # Normalize separators
    s = duration.lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+to\s+", " - ", s)

    # Year-year or year-present
    m = re.search(r"(\d{4})\s*-\s*(present|current|now|\d{4})", s)
    if m:
        start = int(m.group(1))
        end = now_year if not m.group(2).isdigit() else int(m.group(2))
        if end >= start:
            return float(end - start)

    m = re.search(r"(\d{1,2})/(\d{4})\s*-\s*(present|current|now|(\d{1,2})/(\d{4}))", s)
    if m:
        start_month = int(m.group(1))
        start_year = int(m.group(2))
        if m.group(4) and m.group(5):
            end_month = int(m.group(4))
            end_year = int(m.group(5))
        else:
            end_month = now_month
            end_year = now_year
        if 1 <= start_month <= 12 and 1 <= end_month <= 12:
            start_total = start_year * 12 + (start_month - 1)
            end_total = end_year * 12 + (end_month - 1)
            if end_total >= start_total:
                return (end_total - start_total) / 12.0

    # Month/year short format (e.g., "3/15-present", "12/14-3/15")
    m = re.search(r"(\d{1,2})/(\d{2})\s*-\s*(present|current|now|(\d{1,2})/(\d{2}))", s)
    if m:
        start_month = int(m.group(1))
        start_year_2 = int(m.group(2))
        if m.group(4) and m.group(5):
            end_month = int(m.group(4))
            end_year_2 = int(m.group(5))
        else:
            end_month = now_month
            end_year_2 = now_year % 100
        # Interpret two-digit years with a sliding window around current year.
        def _to_year(two_digit: int) -> int:
            pivot = (now_year % 100) + 5
            century = now_year - (now_year % 100)
            year = century + two_digit
            if two_digit > pivot:
                year -= 100
            return year
        start_year = _to_year(start_year_2)
        end_year = _to_year(end_year_2)
        if 1 <= start_month <= 12 and 1 <= end_month <= 12:
            start_total = start_year * 12 + (start_month - 1)
            end_total = end_year * 12 + (end_month - 1)
            if end_total >= start_total:
                return (end_total - start_total) / 12.0

    # Month-name year ranges (e.g., "September 2020 - Current")
    month_regex = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    m = re.search(
        rf"(?P<sm>{month_regex})\s+(?P<sy>\d{{4}})\s*-\s*(?:(?P<em>{month_regex})\s+(?P<ey>\d{{4}})|(?P<now>present|current|now))",
        s,
        flags=re.I,
    )
    if m:
        sm = m.group("sm").lower()[:3]
        sy = int(m.group("sy"))
        if m.group("now"):
            em = now_month
            ey = now_year
        else:
            em = m.group("em").lower()[:3]
            ey = int(m.group("ey"))
            em = {
                "jan": 1,
                "feb": 2,
                "mar": 3,
                "apr": 4,
                "may": 5,
                "jun": 6,
                "jul": 7,
                "aug": 8,
                "sep": 9,
                "oct": 10,
                "nov": 11,
                "dec": 12,
            }.get(em, 0)
        sm = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }.get(sm, 0)
        if 1 <= sm <= 12 and 1 <= em <= 12:
            start_total = sy * 12 + (sm - 1)
            end_total = ey * 12 + (em - 1)
            if end_total >= start_total:
                return (end_total - start_total) / 12.0

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
    prefix = ""
    suffix = ""

    m = INLINE_TITLE_DATE.match(date_line)
    if m:
        title = m.group("title").strip()
    else:
        m2 = INLINE_TITLE_PIPE_DATE.match(date_line)
        if m2:
            title = m2.group("title").strip()
        else:
            title = ""

    if not title or not company:
        date_match = DATE_PATTERN.search(date_line)
        if date_match:
            prefix = date_line[: date_match.start()].strip(" -|")
            suffix = date_line[date_match.end() :].strip(" -|")
            candidate = prefix or suffix
            if candidate:
                parts = re.split(r"\s*(?:—|–)\s*|\s+-\s+|\s*\|\s*", candidate, maxsplit=1)
                if len(parts) == 2:
                    if not title:
                        title = parts[0].strip()
                    if not company:
                        company = _split_company_location(parts[1].strip())
                else:
                    if not title:
                        title = candidate.strip()

    start = max(0, date_idx - lookback)
    window = [l for l in lines[start:date_idx] if l.strip()]

    def _looks_like_company_line(s: str) -> bool:
        lower = s.lower()
        if re.search(r"-\s+", s):
            return True
        if "|" in s:
            return True
        if re.search(r",\s*[A-Z]{2}\b", s):
            return True
        return bool(
            re.search(
                r"\b(inc|llc|ltd|company|schools?|university|college|hospital|clinic|department|county|city|state|agency|association|foundation|center|centre|district|public|government)\b",
                lower,
            )
        )

    def _looks_like_title_line(s: str) -> bool:
        lower = s.lower()
        if "/" in s:
            return True
        return bool(
            re.search(
                r"\b(manager|director|engineer|developer|analyst|specialist|coordinator|assistant|teacher|counselor|consultant|intern|lead|supervisor|officer|administrator|facilitator)\b",
                lower,
            )
        )

    
    if date_idx + 1 < len(lines):
        below = lines[date_idx + 1].strip()
        if below and not _looks_like_heading(below) and not below.lstrip().startswith(("-", "*")):
            # If the date line already implies a company, treat the next line as title.
            if prefix and not title and not _is_bad_title_candidate(below) and not DATE_PATTERN.search(below):
                title = below
                if not company:
                    company = _split_company_location(prefix)
            elif _looks_like_title_line(below) and not _is_bad_title_candidate(below):
                if not title:
                    title = below
                if not company:
                    for look_ahead in range(2, 5):
                        if date_idx + look_ahead >= len(lines):
                            break
                        candidate = lines[date_idx + look_ahead].strip()
                        if not candidate or _looks_like_heading(candidate):
                            continue
                        if candidate.lstrip().startswith(("-", "*")):
                            continue
                        if DATE_PATTERN.search(candidate):
                            continue
                        if _looks_like_title_line(candidate):
                            continue
                        company = _split_company_location(candidate)
                        if company:
                            break
            elif not company:
                company = _split_company_location(below)

    if window:
        last = window[-1].strip()
        prev = window[-2].strip() if len(window) > 1 else ""
        if (
            last
            and prev
            and not _looks_like_heading(last)
            and not _looks_like_heading(prev)
            and not last.lstrip().startswith(("-", "*"))
            and not prev.lstrip().startswith(("-", "*"))
            and not DATE_PATTERN.search(last)
            and not DATE_PATTERN.search(prev)
        ):
            if not title and _looks_like_title_line(last) and (_looks_like_company_line(prev) or not company):
                title = last
                if not company:
                    company = _split_company_location(prev)
            if not title and _looks_like_company_line(last) and _looks_like_title_line(prev):
                title = prev
                if not company:
                    company = _split_company_location(last)

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
        duration = ""
        multi_match = MULTI_SUMMER_RANGE.search(date_line)
        if multi_match:
            start = multi_match.group("start").strip()
            end = multi_match.group("end").strip()
            y1 = multi_match.group("y1")
            y2 = multi_match.group("y2")
            duration = f"{start} {y1} - {end} {y2}"
        else:
            duration_match = DATE_PATTERN.search(date_line)
            duration = duration_match.group(0).strip() if duration_match else ""

        title, company = _infer_title_company_from_context(scoped, date_idx)
        if not title and duration:
            duration_match = DATE_PATTERN.search(date_line)
            if duration_match:
                remainder = date_line[duration_match.end() :].strip(" -|")
                if remainder and not _looks_like_heading(remainder):
                    title = remainder.title()

        if not company:
            for look_ahead in range(1, 3):
                if date_idx + look_ahead >= len(scoped):
                    break
                candidate = scoped[date_idx + look_ahead].strip()
                if not candidate or _looks_like_heading(candidate):
                    continue
                if candidate.lstrip().startswith(("-", "*")):
                    continue
                if DATE_PATTERN.search(candidate):
                    continue
                if " | " in candidate or "," in candidate or " - " in candidate:
                    company = _split_company_location(candidate)
                    if company:
                        break

        end_idx = date_idxs[k + 1] if k + 1 < len(date_idxs) else len(scoped)
        impact_bullets: List[str] = []
        first_company_line = company.strip().lower() if company else ""
        for i, line in enumerate(scoped[date_idx + 1 : end_idx], start=date_idx + 1):
            if _looks_like_heading(line):
                break

            # Stop when the next role header starts.
            if line.isupper() and len(line.split()) <= 8 and not line.lstrip().startswith(("-", "*")):
                break

            # Stop if this looks like the header of the next role (company/title lines) before its date.
            cleaned_line = line.strip()
            if cleaned_line and not cleaned_line.lstrip().startswith(("-", "*")) and not DATE_PATTERN.search(cleaned_line):
                lower_line = cleaned_line.lower()
                looks_like_header_candidate = (
                    len(cleaned_line.split()) <= 6
                    and (
                        "/" in cleaned_line
                        or cleaned_line.isupper()
                        or cleaned_line.istitle()
                        or re.search(
                            r"\b(inc|llc|ltd|company|schools?|university|college|hospital|clinic|department|county|city|state|agency|association|foundation|center|centre|district|public|government|group|garden)\b",
                            lower_line,
                        )
                        or re.search(
                            r"\b(manager|director|engineer|developer|analyst|specialist|coordinator|assistant|teacher|counselor|consultant|intern|lead|supervisor|officer|administrator|facilitator)\b",
                            lower_line,
                        )
                    )
                )
                next_line = ""
                next_next = ""
                for j in range(i + 1, min(end_idx + 1, len(scoped))):
                    if scoped[j].strip():
                        next_line = scoped[j].strip()
                        for k2 in range(j + 1, min(end_idx + 1, len(scoped))):
                            if scoped[k2].strip():
                                next_next = scoped[k2].strip()
                                break
                        break
                if (
                    looks_like_header_candidate
                    and next_line
                    and not next_line.lstrip().startswith(("-", "*"))
                    and not DATE_PATTERN.search(next_line)
                    and next_next
                    and DATE_PATTERN.search(next_next)
                ):
                    break

            is_bullet = bool(re.match(r"^\s*[-*]\s+", line))
            if is_bullet:
                cleaned = _strip_bullet(line)
                if cleaned and cleaned not in {"-"} and not _looks_like_location_line(cleaned):
                    impact_bullets.append(cleaned)
                continue
            cleaned = line.strip()
            if not cleaned or DATE_PATTERN.search(cleaned):
                continue
            if cleaned in {"-"}:
                continue
            if _looks_like_location_line(cleaned):
                continue

            # Skip duplicate company line in bullets when it appears immediately after the date line.
            if first_company_line and cleaned.lower() == first_company_line:
                continue
            if company:
                compact_company = re.sub(r"\s+", "", company).lower()
                compact_line = re.sub(r"\s+", "", cleaned).lower()
                if compact_company and compact_company in compact_line:
                    continue

            # Treat non-bulleted lines as bullet text (common in resumes without bullets)
            if not impact_bullets:
                impact_bullets.append(cleaned)
                continue

            prev = impact_bullets[-1].rstrip()
            role_header = bool(
                re.match(r"^[A-Z][A-Za-z0-9 /&().'-]{3,80}[–—-].*\b(19|20)\d{2}\b", cleaned)
            )
            is_wrap = (
                cleaned[:1].islower()
                or prev.endswith((",", "and", "&", "+", "/"))
                or role_header
            )
            if is_wrap:
                # Continuation of the previous bullet (wrapped line)
                impact_bullets[-1] = f"{impact_bullets[-1]} {cleaned}"
            else:
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
        if re.search(r"\bcredentials?\b", line, flags=re.IGNORECASE):
            continue
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
    if re.search(r"[;,|/\\\\]", s):
        s = re.sub(r"\band\b", ",", s, flags=re.IGNORECASE)
    parts = re.split(r"\s*(?:,|;|\||/|\\)\s*", s)
    out: List[str] = []

    for part in parts:
        cleaned = re.sub(r"\s+", " ", part.strip().strip("•* -"))
        cleaned = re.sub(r"^(and|&)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" .;:")
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
        if cleaned:
            cleaned = re.split(
                r"\b(systems?\s+exposure|other\s+notes|eligible\s+to\s+work|available\s+for|professional\s+interests)\b",
                cleaned,
                flags=re.IGNORECASE,
            )[0].strip()
        if cleaned and not _looks_like_heading(cleaned):
            if re.search(r"[;,|/\\]", cleaned):
                for token in _tokenize_list_content(cleaned):
                    if _looks_like_cert_line(token):
                        certs.append(token)
            elif _looks_like_cert_line(cleaned):
                certs.append(cleaned)

    if not certs:
        # Fallback: pull explicit "Credentials:" lines found anywhere (often under Education & Training)
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.search(r"\bcredentials?\b", line, flags=re.IGNORECASE):
                cleaned = _strip_bullet(line)
                if ":" in cleaned:
                    cleaned = cleaned.split(":", 1)[1].strip()
                # Join continuation lines until blank/heading.
                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()
                    if not next_line or _looks_like_heading(next_line):
                        break
                    if re.match(r"^\s*[-*]\s+", next_line):
                        break
                    cleaned = f"{cleaned} {next_line}".strip()
                    j += 1
                if cleaned:
                    for token in _tokenize_list_content(cleaned):
                        if _looks_like_cert_line(token):
                            certs.append(token)
                i = j
                continue
            i += 1

    return _unique_preserve_order(certs)


def _parse_volunteer_experience(lines: Sequence[str]) -> List[Dict[str, object]]:
    span = _find_section_span(lines, HEADING_VOLUNTEER)
    scoped = lines[span[0] : span[1]] if span else []
    if not scoped:
        return []

    experiences: List[Dict[str, object]] = []
    i = 0
    while i < len(scoped):
        line = scoped[i].strip()
        if not line:
            i += 1
            continue
        if _looks_like_heading(line):
            break

        title = line
        company = ""
        impact_bullets: List[str] = []

        j = i + 1
        while j < len(scoped) and not scoped[j].strip():
            j += 1

        if j < len(scoped):
            next_line = scoped[j].strip()
            if next_line and not next_line.lstrip().startswith(("-", "*")) and not _looks_like_heading(next_line):
                company = _split_company_location(next_line)
                j += 1

        while j < len(scoped):
            cur = scoped[j]
            if not cur.strip():
                break
            if _looks_like_heading(cur):
                break
            if re.match(r"^\s*[-*]\s+", cur):
                cleaned = _strip_bullet(cur)
                if cleaned:
                    impact_bullets.append(cleaned)
                j += 1
                continue
            # Treat non-bullet text as a bullet if none exist; otherwise append.
            if impact_bullets:
                impact_bullets[-1] = f"{impact_bullets[-1]} {cur.strip()}"
            else:
                impact_bullets.append(cur.strip())
            j += 1

        experiences.append(
            {
                "title": title,
                "company": company,
                "duration": "",
                "impact_bullets": impact_bullets,
            }
        )
        i = j + 1

    return experiences


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
    volunteer_experience = _parse_volunteer_experience(line_list)
    if volunteer_experience:
        experience.extend(volunteer_experience)

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
