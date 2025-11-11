# Optional but recommended: pip install spacy==3.7.2 && python -m spacy download en_core_web_sm

from __future__ import annotations
import re
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
import pdfplumber

_NLP = None
try:
    import spacy
    _NLP = spacy.load("en_core_web_sm")
except Exception:
    _NLP = None  # graceful fallback to regex-only

# -----------------------------
# Generic regex patterns (domain-agnostic)
# -----------------------------
MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*"
DATE_TOKEN = rf"(?:{MONTHS})\s+\d{{4}}"
DATE_RANGE = re.compile(rf"({DATE_TOKEN})\s*(?:-|–|—|to|through)\s*(Present|{DATE_TOKEN})", re.I)

# Education kept generic but necessary to identify education reliably
DEGREE_PAT = r"(?:Bachelor(?:'s)?|Master(?:'s)?|B\.?S\.?|M\.?S\.?|B\.?A\.?|M\.?A\.?|MBA|Ph\.?D\.?|PhD|Associate(?:'s)?)"
EDU_RE = re.compile(rf"\b{DEGREE_PAT}\b(?:[^.\n,;:]*)", re.I)

# Bullets/separators (generic)
SEP = re.compile(r"[•·\-\u2022;/,\u2013\u2014]")

# Achievement cues (generic)
IMPACT_VERB = r"(improv|increas|decreas|reduc|grow|save|cut|boost|optimi|accelerat|lower|raise|expand|shrank)"
ACHIEVEMENT_LINE = re.compile(
    rf"(?P<sent>[^.\n]*?(?:\b\d[\d,]*(?:\.\d+)?%|\$\s?\d[\d,]*|\b\d[\d,]*(?:\.\d+)?\b)[^.\n]*?(?:{IMPACT_VERB})?[^.\n]*[.\n])",
    re.I
)

# Section header heuristics (no domain dependence)
HEADER_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z &/]+)\s*:?\s*$")

# -----------------------------
# RAKE-like keyphrase extraction (unsupervised; no lists)
# -----------------------------
STOPWORDS = set("""
a an and the of for to in on at from with without by as into above below over under out up down about across after before during
is are was were be been being have has had do does did can could should would may might must will
this that these those there here it they them he she we you i me my our your their his her its
""".split())

def read_pdf_text(path):
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def tokenize_words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9\-\+_/]*", text)

def split_phrases(text: str) -> List[str]:
    # Split by punctuation/line breaks; keep hyphenated phrases intact
    parts = re.split(r"[^\w+/\- ]+", text)
    return [p.strip() for p in parts if p.strip()]

def rake_candidates(text: str) -> List[str]:
    # Break text into candidate phrases separated by stopwords
    candidates = []
    for sent in split_phrases(text):
        words = tokenize_words(sent)
        chunk = []
        for w in words:
            lw = w.lower()
            if lw in STOPWORDS:
                if chunk:
                    candidates.append(" ".join(chunk))
                    chunk = []
            else:
                chunk.append(w)
        if chunk:
            candidates.append(" ".join(chunk))
    # filter overly short/long
    out = [c.strip() for c in candidates if 2 <= len(c.split()) <= 6]
    return out

def rake_rank(text: str) -> List[Tuple[str, float]]:
    # Score words by degree/frequency, then sum for phrase score
    words = [w.lower() for w in tokenize_words(text)]
    freq = {}
    deg  = {}
    for sent in split_phrases(text):
        toks = [t.lower() for t in tokenize_words(sent) if t.lower() not in STOPWORDS]
        for i, w in enumerate(toks):
            freq[w] = freq.get(w, 0) + 1
            deg[w]  = deg.get(w, 0) + (len(toks) - 1)
    for w in list(freq.keys()):
        deg[w] = deg[w] + freq[w]  # degree includes itself
    word_score = {w: (deg.get(w, 0) / float(freq.get(w, 1))) for w in freq}

    phrases = rake_candidates(text)
    scored: Dict[str, float] = {}
    for p in phrases:
        s = 0.0
        for w in p.lower().split():
            if w in STOPWORDS: 
                continue
            s += word_score.get(w, 0.0)
        # position bonus (earlier phrases weigh more)
        first_idx = text.lower().find(p.lower())
        pos_bonus = 1.5 if 0 <= first_idx <= max(30, int(len(text) * 0.05)) else 1.0
        scored[p] = s * pos_bonus
    # return sorted unique phrases
    uniq = sorted(scored.items(), key=lambda x: x[1], reverse=True)
    return uniq

# -----------------------------
# Data structures
# -----------------------------
@dataclass
class ExperienceItem:
    company: Optional[str]
    title: Optional[str]
    start: Optional[str]
    end: Optional[str]
    location: Optional[str] = None

@dataclass
class ResumeFacts:
    profession: Optional[str]
    years_experience: Optional[float]
    skills: List[str]
    education: List[str]
    experience: List[ExperienceItem]
    achievements: List[str]
    certifications: List[str]

# -----------------------------
# Utilities
# -----------------------------
def _normalize(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def _lines(text: str) -> List[str]:
    return [ln.strip() for ln in text.split("\n")]

def detect_sections(text: str) -> Dict[str, Tuple[int, int]]:
    """
    Generic section detector: any standalone line of letters/&/spaces is treated as a header.
    Returns {lowercased_header: (start_line, end_line)} for the content span.
    """
    lines = _lines(text)
    idx = []
    for i, ln in enumerate(lines):
        if HEADER_LINE.match(ln):
            # avoid false positives like single words inside bullet lines
            if (i == 0 and len(ln.split()) <= 2):  # often name header—skip
                continue
            idx.append((HEADER_LINE.match(ln).group(1).strip().lower(), i))
    spans = {}
    for j, (name, start) in enumerate(idx):
        end = idx[j+1][1] if j+1 < len(idx) else len(lines)
        spans[name] = (start + 1, end)
    return spans

def find_date_blocks(lines: List[str]) -> List[Tuple[int, str, str]]:
    hits = []
    for i, ln in enumerate(lines):
        m = DATE_RANGE.search(ln)
        if m:
            hits.append((i, m.group(1), m.group(2)))
    return hits

def extract_years_experience(text: str) -> Optional[float]:
    # explicit "X years of experience"
    yrs = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?(?:experience|exp)\b", text, re.I):
        try: yrs.append(float(m.group(1)))
        except: pass
    if yrs:
        return max(yrs)
    # estimate from date ranges (very generic)
    def to_year(mon_year: str) -> Optional[float]:
        mo_map = {m:i for i,m in enumerate(["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"], 1)}
        m = re.match(rf"({MONTHS})\s+(\d{{4}})", mon_year, re.I)
        if not m: return None
        mo = mo_map.get(m.group(1).lower()[:3], 1)
        return int(m.group(2)) + (mo-1)/12.0
    spans = [(to_year(a), None if b.lower()=="present" else to_year(b)) for a,b in DATE_RANGE.findall(text)]
    spans = [(s, e if e is not None else s) for s, e in spans if s is not None]
    if not spans: return None
    spans.sort()
    total = 0.0
    cur_s, cur_e = spans[0]
    for s, e in spans[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += (cur_e - cur_s); cur_s, cur_e = s, e
    total += (cur_e - cur_s)
    return round(total, 1) if total > 0 else None

def extract_experience(text: str) -> List[ExperienceItem]:
    items: List[ExperienceItem] = []
    lines = _lines(text)
    blocks = find_date_blocks(lines)
    for idx, start, end in blocks:
        # Search around the date line for title/company using capitalization & separators
        prev = lines[idx-1] if idx-1 >= 0 else ""
        curr = lines[idx]
        nextl = lines[idx+1] if idx+1 < len(lines) else ""
        window = " | ".join([prev, curr, nextl])

        # Company: prefer ALL CAPS or Title Case segment before a dash or after "at"
        comp = None
        m_at = re.search(r"\b(?:at|@)\s+([A-Z][\w&.,'() ]{1,60})", window)
        if m_at:
            comp = m_at.group(1).strip(" -|,.;")
        if not comp:
            m_dash = re.search(r"([A-Z][A-Za-z0-9&.,'() ]{2,})\s+[–—-]\s+", window)
            if m_dash: comp = m_dash.group(1).strip()
        if not comp:
            # fallback: two Capitalized words
            cand = re.findall(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z&]+)+)\b", window)
            comp = cand[0] if cand else None

        # Title: look for Capitalized phrase with verbs like Engineer/Manager/etc. (but no fixed list)
        title = None
        # Use spaCy if available to grab first NOUN/PROPN chunk near " as " or leading segment
        if _NLP:
            doc = _NLP(window)
            # pattern: (as|role|position)\s+(NOUN/PROPN+)
            for i,tok in enumerate(doc):
                if tok.text.lower() in {"as","role","position","served"} and i+1 < len(doc):
                    span = []
                    for j in range(i+1, min(i+8, len(doc))):
                        if doc[j].pos_ in {"PROPN","NOUN","ADJ"}:
                            span.append(doc[j].text)
                        elif span:
                            break
                    if span:
                        title = " ".join(span)
                        break
            if not title:
                # otherwise take first capitalized chunk from prev/curr lines
                for ln in [prev, curr]:
                    cap = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4})\b", ln)
                    if cap:
                        title = cap[0]
                        break
        else:
            # regex-only guess: initial Capitalized phrase on previous line or current line
            for ln in [prev, curr]:
                cap = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4})\b", ln)
                if cap:
                    title = cap[0]; break

        # Location: "City, ST" or "City, Country"
        loc = None
        for ln in [curr, prev, nextl]:
            mloc = re.search(r"\b([A-Z][a-zA-Z]+,\s*[A-Z]{2,}|[A-Z][a-zA-Z]+,\s*[A-Z][a-zA-Z]+)\b", ln)
            if mloc: loc = mloc.group(1); break

        items.append(ExperienceItem(company=comp, title=title, start=start, end=end, location=loc))
    return items

def extract_education(text: str) -> List[str]:
    return sorted({m.group(0).strip(" .,:;") for m in EDU_RE.finditer(text)})

def extract_certifications(text: str) -> List[str]:
    # Domain-agnostic heuristic: lines containing 'certified' or 'certification'
    certs = set()
    for m in re.finditer(r"\b(certified|certification)\b[^.\n,;:]*", text, re.I):
        certs.add(m.group(0).strip(" .,:;"))
    return sorted(certs)

def extract_achievements(text: str, k: int = 3) -> List[str]:
    cand = set()
    for m in ACHIEVEMENT_LINE.finditer(text):
        sent = re.sub(r"\s+", " ", m.group("sent")).strip()
        # prefer lines that mention a metric AND an action word
        score = 0
        if re.search(r"%|\$", sent): score += 1
        if re.search(IMPACT_VERB, sent, re.I): score += 1
        if len(sent) < 200: score += 1
        cand.add((sent, score))
    ranked = sorted(cand, key=lambda x: (x[1], len(x[0])), reverse=True)
    return [s for s,_ in ranked[:k]]

def extract_skills(text: str, sections: Dict[str, Tuple[int,int]]) -> List[str]:
    """
    1) If a 'skills-like' section exists, split by separators/bullets.
    2) Otherwise, build candidates via spaCy noun chunks (if available) + RAKE (unsupervised).
    3) Rank by frequency + early-position bonus; normalize & deduplicate.
    """
    lines = _lines(text)
    # try to find a skills-ish section by name only (generic)
    skill_like = None
    for name, (s,e) in sections.items():
        if re.search(r"\bskills?\b", name):  # e.g., "Skills", "Technical Skills"
            skill_like = "\n".join(lines[s:e]).strip()
            break

    candidates = []

    if skill_like:
        # Split by bullets / commas / slashes / semicolons
        raw = SEP.split(skill_like)
        for tok in raw:
            tok = tok.strip(" .|·•-").strip()
            if 1 < len(tok) <= 64:
                candidates.append(tok)
    else:
        # 2a) spaCy noun chunks (if available)
        if _NLP:
            doc = _NLP(text)
            for chunk in doc.noun_chunks:
                ph = chunk.text.strip()
                # prune trivial chunks (stopwords-only or single-character)
                words = [w for w in tokenize_words(ph)]
                if not words or len(" ".join(words)) < 3: 
                    continue
                if len(words) > 7: 
                    continue
                candidates.append(" ".join(words))
        # 2b) RAKE (unsupervised)
        for p, _score in rake_rank(text)[:80]:
            candidates.append(p)

    # Rank & clean
    low_text = text.lower()
    seen = {}
    for c in candidates:
        c = re.sub(r"\s+", " ", c).strip(" .,:;").strip()
        if len(c) < 2: 
            continue
        # frequency & position
        freq = len(re.findall(re.escape(c), low_text, re.I))
        pos  = low_text.find(c.lower())
        pos_bonus = 1.5 if 0 <= pos <= max(40, int(len(text)*0.05)) else 1.0
        score = freq * pos_bonus
        prev = seen.get(c.lower())
        if not prev or score > prev[0]:
            seen[c.lower()] = (score, c)

    # Deduplicate by substring containment (keep longer)
    items = [v[1] for v in sorted(seen.values(), key=lambda x: (x[0], len(x[1])), reverse=True)]
    filtered: List[str] = []
    for cand in items:
        if any(cand.lower() in f.lower() and cand.lower()!=f.lower() for f in filtered):
            continue
        filtered.append(cand)

    # Normalize capitalization (keep acronyms uppercase)
    def nice_cap(s: str) -> str:
        parts = s.split()
        out = []
        for w in parts:
            if len(w) <= 4 and w.isupper():
                out.append(w)
            elif re.match(r"^[A-Za-z]+[A-Z0-9+/_-]*$", w) and sum(ch.isupper() for ch in w) >= 2:
                out.append(w)  # likely acronym/mixed
            else:
                out.append(w.capitalize())
        return " ".join(out)

    cleaned = [nice_cap(s) for s in filtered]
    # Take top N diverse phrases
    return cleaned[:30]

def infer_profession(text: str, sections: Dict[str, Tuple[int,int]]) -> Optional[str]:
    # Try first line or "Summary" section’s first sentence; otherwise, most frequent head noun from spaCy
    lines = _lines(text)
    candidates = []
    if lines:
        candidates.append(lines[0])
    for k,(s,e) in sections.items():
        if "summary" in k:
            candidates.append(" ".join(lines[s:e])[:200])
            break
    blob = " ".join(candidates)
    if _NLP:
        doc = _NLP(blob)
        nouns = [t.text for t in doc if t.pos_ in {"NOUN","PROPN"}]
        if nouns:
            # choose most frequent multi-char noun
            from collections import Counter
            common = [w for w,c in Counter([n.lower() for n in nouns if len(n) > 2]).most_common(20)]
            return common[0].capitalize() if common else None
    # fallback: take first Capitalized bigram from first line
    m = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", blob)
    return m.group(1) if m else None

def compose_summary(facts: ResumeFacts) -> str:
    parts = []
    prof = facts.profession or "Professional"
    yrs = f"{facts.years_experience:.1f}".rstrip("0").rstrip(".") if facts.years_experience is not None else None
    parts.append(
        f"Summary: {prof} with {yrs} years of hands-on experience." if yrs
        else f"Summary: {prof} with proven hands-on experience."
    )
    if facts.skills:
        parts.append("Skills: " + ", ".join(facts.skills[:18]) + ("," if len(facts.skills) > 18 else "."))
    if facts.education:
        parts.append("Education: " + "; ".join(facts.education) + ".")
    if facts.certifications:
        parts.append("Certifications: " + "; ".join(facts.certifications) + ".")
    if facts.achievements:
        parts.append(facts.achievements[0].rstrip(".") + ".")
    return " ".join(parts)

def parse_resume(text: str) -> ResumeFacts:
    text = _normalize(text)
    sections = detect_sections(text)

    experience = extract_experience(text)
    years = extract_years_experience(text)
    education = extract_education(text)
    certifications = extract_certifications(text)
    achievements = extract_achievements(text)
    skills = extract_skills(text, sections)
    profession = infer_profession(text, sections)

    return ResumeFacts(
        profession=profession,
        years_experience=years,
        skills=skills,
        education=education,
        experience=experience,
        achievements=achievements,
        certifications=certifications
    )

def preprocess_resume(text: str) -> Dict:
    facts = parse_resume(text)
    summary = compose_summary(facts)
    return {
        "summary": summary,
        "facts": {
            **asdict(facts),
            "experience": [asdict(e) for e in facts.experience]
        }
    }

if __name__ == "__main__":
    path = "Sebastian Grammas .pdf"
    text = read_pdf_text(path)
    result = preprocess_resume(text)
    print(result["summary"])
    print(json.dumps(result, indent=2))
