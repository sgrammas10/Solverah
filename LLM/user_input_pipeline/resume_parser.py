"""Robust, heading-agnostic resume parser.

This module keeps the original public API ``parse_resume`` while replacing the
previous heading-only approach with a hybrid heuristic pipeline designed to
handle messy real-world resumes (PDF extracted text, missing headings,
multi-column ordering, etc.).

Key design points:
* Normalize text aggressively (bullets, dashes, whitespace, hyphenation).
* Infer sections via lightweight line classification rather than strict
  headings.
* Experience extraction is anchored on date ranges and nearby title/company
  cues, then gathers subsequent bullets.
* Skills/tools use lexicon-driven tokenization over comma/pipe/bullet lists.
* Education and clearances are detected with keyword heuristics even when no
  section exists.
* Deterministic and offline by construction; gracefully returns empty fields
  when uncertain.

An optional ``evaluate_on_jsonl`` helper at the bottom provides quick recall
metrics on a JSONL resume file.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------- Normalization helpers ----------------------------


def _normalize_text(text: str) -> str:
    """Normalize bullet characters, dashes, and whitespace for downstream parsing."""

    replacements = {
        "·": "-",
        "": "-",
        "●": "-",
        "•": "-",
        "–": "-",
        "—": "-",
        " ": " ",
    }
    for src, tgt in replacements.items():
        text = text.replace(src, tgt)

    # De-hyphenate common PDF line breaks: "co-
    # mputer" -> "computer"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Collapse long whitespace sequences
    text = re.sub(r"[\t\f\r]+", " ", text)
    text = re.sub(r" +", " ", text)
    return text


def _lines(text: str) -> List[str]:
    normalized = _normalize_text(text)
    return [line.strip() for line in normalized.split("\n")]


def _strip_bullet(line: str) -> str:
    return re.sub(r"^(?:[-*]\s+)+", "", line).strip()


# ---------------------------- Shared patterns ----------------------------------


MONTH_PATTERN = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{2,4}"
NUMERIC_PATTERN = r"\d{1,2}/\d{2,4}"
YEAR_PATTERN = r"\d{4}"
RANGE_SEP = r"\s*(?:to|-|–|—)\s*"

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

SECTION_BREAK_PATTERN = re.compile(
    r"^(skills?|projects?|certifications?|education|summary|technical summary|tools)\b",
    flags=re.IGNORECASE,
)


# Lexicons stay as soft priors, but skill detection is primarily heuristic so
# new terms can be captured without updating these lists.
SKILL_TERMS: Set[str] = {
    "project management",
    "program management",
    "leadership",
    "communication",
    "operations",
    "logistics",
    "supply chain",
    "budgeting",
    "forecasting",
    "training",
    "mentoring",
    "quality assurance",
    "process improvement",
    "data analysis",
    "analytics",
    "research",
    "marketing",
    "sales",
    "customer service",
    "manufacturing",
    "maintenance",
    "clinical",
    "patient care",
    "classroom management",
}

TOOL_TERMS: Set[str] = {
    "excel",
    "tableau",
    "power bi",
    "salesforce",
    "sap",
    "oracle",
    "quickbooks",
    "autocad",
    "solidworks",
    "matlab",
    "simulink",
    "jira",
    "confluence",
    "slack",
    "asana",
    "trello",
    "smartsheet",
    "crm",
    "erp",
    "lms",
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "git",
}

# Lightweight linguistic priors to identify skill-like tokens without a fixed
# vocabulary. These sets stay small and interpretable.
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

SKILL_SUFFIXES: Set[str] = {
    "management",
    "operations",
    "analysis",
    "design",
    "support",
    "training",
    "strategy",
    "marketing",
    "planning",
    "research",
    "compliance",
    "safety",
    "analytics",
    "testing",
    "development",
    "leadership",
    "writing",
}

TOOL_HINTS: Set[str] = {
    "sql",
    "crm",
    "erp",
    "lms",
    "cad",
    "gis",
    "bi",
    "lab",
    "analytics",
    "automation",
}

EXPERIENCE_VERBS = {
    "built",
    "developed",
    "designed",
    "led",
    "managed",
    "created",
    "presented",
    "implemented",
    "launched",
    "improved",
    "migrated",
    "optimized",
}


# ---------------------------- Utility functions --------------------------------


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped.split()) <= 5 and stripped.isupper():
        return True
    if len(stripped) <= 18 and re.match(r"^[A-Za-z /&]+$", stripped) and stripped.istitle():
        return True
    return False


def _split_title_company(text: str) -> Tuple[str, str]:
    text = text.strip("-|")
    if not text:
        return "", ""

    parts = re.split(r"\s+(?:@|at|\-|\||,|\u2013|\u2014)\s+", text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()

    tokens = text.split(",")
    if len(tokens) >= 2 and len(tokens[0].split()) <= 6:
        return tokens[0].strip(), " ".join(tokens[1:]).strip()

    # Fallback: treat first capitalized chunk as company, remaining as title
    words = text.split()
    if words and words[0][0].isupper():
        company = " ".join(words[:2]).strip()
        title = " ".join(words[2:]).strip()
        if title:
            return title, company
    return text, ""


def _unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for item in items:
        key = item.lower()
        if key not in seen and item:
            seen.add(key)
            ordered.append(item)
    return ordered


# ---------------------------- Years of experience -------------------------------


def _parse_years_experience(text: str) -> int | float | None:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs)\b", text, flags=re.IGNORECASE)
    numeric = [float(m) for m in matches]
    if not numeric:
        return None
    max_years = max(numeric)
    return int(max_years) if max_years.is_integer() else max_years


# ---------------------------- Experience extraction -----------------------------


def _collect_experience_blocks(lines: Sequence[str]) -> List[Tuple[int, int]]:
    """Return (start_idx, end_idx_exclusive) blocks anchored around date lines."""

    blocks: List[Tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if DATE_PATTERN.search(lines[i]):
            start = i
            j = i + 1
            while j < len(lines):
                if DATE_PATTERN.search(lines[j]):
                    break
                if _looks_like_heading(lines[j]) or SECTION_BREAK_PATTERN.search(lines[j]):
                    break
                j += 1
            blocks.append((start, j))
            i = j
        else:
            i += 1
    return blocks


def _parse_experience(lines: Sequence[str]) -> List[Dict[str, object]]:
    experiences: List[Dict[str, object]] = []
    blocks = _collect_experience_blocks(lines)

    if not blocks:
        logger.info("No date-anchored experience blocks detected")
        return experiences

    for start, end in blocks:
        header_line = lines[start]
        duration_match = DATE_PATTERN.search(header_line)
        duration = duration_match.group(0).strip() if duration_match else ""
        header_without_dates = DATE_PATTERN.sub("", header_line).strip()

        # Look backward for context if header is sparse
        context_line = ""
        if not header_without_dates:
            for back in range(start - 1, -1, -1):
                if lines[back].strip():
                    context_line = lines[back]
                    break

        header_source = header_without_dates or context_line
        title, company = _split_title_company(header_source)

        impact_bullets: List[str] = []
        for line in lines[start + 1 : end]:
            cleaned = _strip_bullet(line)
            if cleaned:
                impact_bullets.append(cleaned)

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
    edu_lines: List[str] = []
    for idx, line in enumerate(lines):
        if DEGREE_PATTERN.search(line) or EDU_INSTITUTION_PATTERN.search(line):
            combined = line
            if idx + 1 < len(lines) and len(lines[idx + 1]) < 120 and not CLEARANCE_PATTERN.search(lines[idx + 1]):
                combined = combined + " " + lines[idx + 1].strip()
            edu_lines.append(combined.strip())
    if not edu_lines:
        logger.info("No education cues found (degree or institution keywords)")
    return "\n".join(_unique_preserve_order(edu_lines))


# ---------------------------- Skills / tools extraction -------------------------


def _tokenize_skill_line(line: str) -> List[str]:
    parts = re.split(r"[,;|/\\-]\s*|\s+\u2022\s+", line)
    tokens = []
    for part in parts:
        cleaned = part.strip().strip("-•*")
        cleaned = re.sub(r"^(skills?|tools?|technologies|tech)[:\-]\s*", "", cleaned, flags=re.IGNORECASE)
        if cleaned:
            tokens.append(cleaned)
    return tokens


def _looks_like_contact_or_noise(token: str) -> bool:
    lower = token.lower()
    if "@" in token or "http" in lower or "www." in lower:
        return True
    if re.search(r"\b\d{3}[\s.-]?\d{3}[\s.-]?\d{4}\b", token):
        return True
    if re.search(r"\b(present|current)\b", lower):
        return True
    if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b", lower):
        return True
    # Disqualify tokens dominated by digits or punctuation
    letters = sum(c.isalpha() for c in token)
    digits = sum(c.isdigit() for c in token)
    if digits > letters and digits >= 2:
        return True
    return False


def _is_skill_rich_line(line: str) -> bool:
    lower_line = line.lower()
    separators = line.count(",") + line.count("|") + line.count(";")
    cue_phrases = (
        "skill",
        "tool",
        "technology",
        "languages",
        "expertise",
        "competenc",
        "strengths",
        "experience with",
        "proficient in",
        "familiar with",
    )
    if separators >= 1 or any(cue in lower_line for cue in cue_phrases):
        return True

    raw_tokens = [tok.strip(",.;:()[]{}") for tok in line.split()]
    tokens = [tok.lower() for tok in raw_tokens if tok]
    overlap = sum(1 for tok in tokens if tok in SKILL_TERMS)

    if overlap >= 2:
        return True
    if len(tokens) >= 4 and overlap >= 1:
        return True

    phrase_tokens = _tokenize_skill_line(line)
    short_phrases = [p for p in phrase_tokens if len(p.split()) <= 4]
    if separators >= 1 and len(short_phrases) >= 3:
        return True
    if len(short_phrases) >= 4:
        return True
    return False


def _score_token_as_skill(token: str) -> int:
    """Heuristic score indicating how likely a token is to be a skill phrase."""

    normalized = token.lower()
    if not re.search(r"[a-zA-Z]", token):
        return 0
    if _looks_like_contact_or_noise(token):
        return 0
    if normalized in STOPWORDS:
        return 0
    if normalized in SKILL_TERMS:
        return 3
    if normalized in TOOL_TERMS:
        return 2

    words = normalized.split()
    score = 0

    if len(words) == 1:
        word = words[0]
        if len(word) >= 3:
            score += 1
        for suffix in SKILL_SUFFIXES:
            if word.endswith(suffix):
                score += 1
                break
        if word.isupper() and len(word) <= 6:
            score += 1
    else:
        if len(words) <= 5:
            score += 2
        if any(w.endswith(tuple(SKILL_SUFFIXES)) for w in words):
            score += 1

    capitalized_ratio = sum(1 for w in token.split() if w[:1].isupper()) / max(len(token.split()), 1)
    if capitalized_ratio >= 0.5:
        score += 1

    return score


def _is_tool_token(token: str) -> bool:
    normalized = token.lower()
    if not re.search(r"[a-zA-Z]", token) and not re.match(r"^v?\d+(?:\.\d+)*$", token.strip()):
        return False
    if _looks_like_contact_or_noise(token):
        return False
    if normalized in TOOL_TERMS:
        return True
    if any(hint in normalized for hint in TOOL_HINTS):
        return True
    if re.search(r"\b(v?\d+(?:\.\d+)*)\b", normalized):
        return True
    if normalized.isupper() and len(normalized) <= 5:
        return True
    return False


def _parse_skills_and_tools(lines: Sequence[str]) -> Tuple[List[str], List[str]]:
    skill_bucket: List[str] = []
    tool_bucket: List[str] = []

    for line in lines:
        if not line or DEGREE_PATTERN.search(line) or DATE_PATTERN.search(line) or not _is_skill_rich_line(line):
            continue

        if re.search(r"@|www\.|http", line) or re.search(r"\b\d{3}[\s.-]?\d{3}[\s.-]?\d{4}\b", line):
            continue

        lower_line = line.lower()
        separators = line.count(",") + line.count("|") + line.count(";")
        if "skill" not in lower_line and separators <= 2 and any(v in lower_line for v in EXPERIENCE_VERBS):
            continue

        tokens = _tokenize_skill_line(line)
        for token in tokens:
            if not token:
                continue

            if len(token) > 60:
                continue
            if token.lower().startswith(("activities", "experience", "summary", "objective", "education")):
                continue
            if _looks_like_contact_or_noise(token):
                continue

            if _is_tool_token(token):
                tool_bucket.append(token)
                continue

            score = _score_token_as_skill(token)
            if score >= 2:
                skill_bucket.append(token)
            elif score == 1 and len(token.split()) <= 3:
                skill_bucket.append(token)

    if not skill_bucket:
        logger.info("No likely skill lines detected")
    if not tool_bucket:
        logger.info("No likely tool/platform lines detected")

    return _unique_preserve_order(skill_bucket), _unique_preserve_order(tool_bucket)


# ---------------------------- Projects / certifications -------------------------


def _parse_projects(lines: Sequence[str]) -> List[str]:
    projects: List[str] = []
    for line in lines:
        cleaned = _strip_bullet(line)
        if SECTION_BREAK_PATTERN.match(cleaned):
            continue
        if re.search(r"project", cleaned, flags=re.IGNORECASE):
            projects.append(cleaned)
    return _unique_preserve_order(projects)


def _parse_certifications(lines: Sequence[str]) -> List[str]:
    certs: List[str] = []
    for line in lines:
        cleaned = _strip_bullet(line)
        if SECTION_BREAK_PATTERN.match(cleaned):
            continue
        if re.search(r"cert|certificate|certification", cleaned, flags=re.IGNORECASE):
            certs.append(cleaned)
    return _unique_preserve_order(certs)


# ---------------------------- Clearance / work auth -----------------------------


def _parse_clearances(text: str) -> str:
    match = CLEARANCE_PATTERN.search(text)
    return match.group(0) if match else ""


# ---------------------------- Main parse function -------------------------------


def parse_resume(text: str) -> Dict[str, object]:
    """Parse normalized resume text into structured sections.

    The function is deterministic, offline, and returns default values when
    uncertain to maintain schema stability.
    """

    line_list = _lines(text)

    years_experience = _parse_years_experience(text) or 0
    experience = _parse_experience(line_list)
    education = _parse_education(line_list)
    skills, tools_platforms = _parse_skills_and_tools(line_list)
    projects = _parse_projects(line_list)
    certifications = _parse_certifications(line_list)
    clearances_or_work_auth = _parse_clearances(text)

    missing_fields: List[str] = []
    for name, value in [
        ("education", education),
        ("skills", skills),
        ("tools_platforms", tools_platforms),
        ("experience", experience),
        ("projects", projects),
        ("certifications", certifications),
        ("clearances_or_work_auth", clearances_or_work_auth),
    ]:
        if not value:
            missing_fields.append(name)

    if missing_fields:
        logger.info("Resume missing or uncertain sections: %s", ", ".join(missing_fields))

    return {
        "years_experience": years_experience,
        "education": education,
        "skills": skills,
        "tools_platforms": tools_platforms,
        "experience": experience,
        "projects": projects,
        "certifications": certifications,
        "clearances_or_work_auth": clearances_or_work_auth,
    }


# ---------------------------- Evaluation harness --------------------------------


def evaluate_on_jsonl(path: Path, sample_size: int | None = 200) -> Dict[str, float]:
    """Run quick recall-oriented metrics over a JSONL of resumes.

    Returns a dict of metrics. Designed for offline diagnostics, not training.
    """

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
            totals["nonempty_skills"] += bool(parsed["skills"] or parsed["tools_platforms"])
            totals["nonempty_education"] += bool(parsed["education"])
            experience_counts.append(len(parsed["experience"]))

    resumes = totals.get("resumes", 1)  # avoid divide-by-zero
    metrics = {
        "% with non-empty experience": totals["nonempty_experience"] / resumes,
        "% with non-empty skills/tools": totals["nonempty_skills"] / resumes,
        "% with non-empty education": totals["nonempty_education"] / resumes,
        "avg # experience entries": (sum(experience_counts) / resumes) if experience_counts else 0.0,
    }

    logger.info("Evaluation metrics: %s", metrics)
    return metrics


__all__ = ["parse_resume", "evaluate_on_jsonl"]
