from pathlib import Path
from typing import List, Dict, Optional, Tuple, Iterable
from collections import Counter
import re, json, sys
def _get_spacy():
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except Exception:
        return None

def _get_dateparser():
    try:
        import dateparser
        return dateparser
    except Exception:
        return None

def _get_docx():
    try:
        import docx
        return docx
    except Exception:
        return None

# Patterns
DEGREE_PAT = r"(b\.?a\.?|b\.?s\.?|bsc|ba|bs|bachelor|m\.?a\.?|m\.?s\.?|msc|ma|ms|master|mba|ph\.?d\.?|phd|associate|b\.?eng\.?|m\.?eng\.?|jd|md|do|dnp|edd|dpt)"
DATE_PAT = r"(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4})"

HEADER_PATTERNS = {
    "summary": r"(?i)^\s*(summary|profile|objective)\s*$",
    "experience": r"(?i)^\s*(experience|work experience|professional experience|employment)\s*$",
    "education": r"(?i)^\s*(education|academics|academic background)\s*$",
    "skills": r"(?i)^\s*(skills|core skills|competencies|technical skills|proficiencies|areas of expertise)\s*$",
    "projects": r"(?i)^\s*(projects|selected projects|portfolio)\s*$",
    "certifications": r"(?i)^\s*(certifications|licenses|licences|clearances|registrations)\s*$",
    "affiliations": r"(?i)^\s*(affiliations|memberships|professional associations)\s*$",
    "publications": r"(?i)^\s*(publications|presentations)\s*$",
    "awards": r"(?i)^\s*(awards|honors|honours)\s*$",
}

GENERIC_SOFT_SKILLS = {
    "communication","leadership","collaboration","teamwork","problem solving","critical thinking",
    "time management","adaptability","customer service","stakeholder management","mentorship",
    "attention to detail","organization","conflict resolution","initiative","ownership"
}

STOPWORDS = set("""a an the and or but if then else for with without in on at by to from of into over under between during before after above below up down off out about against further more most some any each both few many such nor not only own same so than too very can will just don dont should shouldnt could couldnt would wouldnt is are was were be been being have has had do does did doing this that these those as it its they them he she we you your our their""".split())

def normalize_ws(s:str)->str:
    return re.sub(r"[ \t]+", " ", s).strip()

def normalize_text_pretty(text:str)->str:
    t = text.replace("•", "- ").replace("–", "-").replace("—", "-")
    t = re.sub(r"(?m)^\s*o\s+", "- ", t)  # convert stray 'o ' bullets to dashes
    for hdr in ["Relevant Experience","Experience","Relevant Skills","Skills","Education","Projects","Certifications","Affiliations","Awards","Publications","Summary","Profile","Objective"]:
        t = re.sub(rf"(?i){hdr}", f"\n{hdr}\n", t)
    t = re.sub(r"\b([a-z0-9]+)\.c\s+om\b", r"\1.com", t, flags=re.I)  # fix 'gmail.c om'
    t = re.sub(r"(?:\+?\d{1,2}\s*)?(?:\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4})", " ", t)  # strip phones
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()

def split_lines(text:str)->List[str]:
    return [normalize_ws(l) for l in text.splitlines()]

def detect_sections(text:str)->Dict[str,str]:
    markers = ["Relevant Experience","Experience","Work Experience","Professional Experience",
               "Relevant Skills","Skills","Education","Projects","Certifications","Affiliations",
               "Awards","Publications","Summary","Profile","Objective"]
    pattern = r"(?i)(" + "|".join([re.escape(m) for m in markers]) + r")\b"
    parts = re.split(pattern, text)
    if len(parts) > 1:
        sections = {}
        for i in range(1, len(parts), 2):
            hdr = parts[i].strip().lower()
            body = parts[i+1].strip()
            key = "skills" if "skill" in hdr else \
                  "experience" if "experience" in hdr else \
                  "education" if "education" in hdr else \
                  "projects" if "project" in hdr else \
                  "certifications" if "certif" in hdr or "license" in hdr or "licence" in hdr else \
                  "affiliations" if "affiliation" in hdr or "membership" in hdr else \
                  "awards" if "award" in hdr or "honor" in hdr else \
                  "publications" if "publication" in hdr or "presentation" in hdr else \
                  "summary"
            sections[key] = (sections.get(key,"") + ("\n" if sections.get(key) else "") + body).strip()
        if sections:
            return sections
    # Fallback to line-based
    lines = split_lines(text)
    indices = []
    for i, line in enumerate(lines):
        for key, pat in HEADER_PATTERNS.items():
            if re.match(pat, line):
                indices.append((i, key)); break
    if not indices:
        return {"unknown": text}
    indices.sort()
    sections = {}
    for j, (i, key) in enumerate(indices):
        start = i+1
        end = indices[j+1][0] if j+1 < len(indices) else len(lines)
        sections[key] = "\n".join(lines[start:end]).strip()
    return sections

def simple_dateparse(s:str)->Optional[str]:
    dp = _get_dateparser()
    if not dp:
        return None
    s = s.replace("Sept","Sep")
    dt = dp.parse(s, settings={"PREFER_DAY_OF_MONTH":"first"})
    return dt.strftime("%Y-%m") if dt else None

def extract_contact(text:str)->Dict[str, Optional[str]]:
    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    phones = re.findall(r"(?:\+?\d{1,2}\s*)?(?:\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4})", text)
    urls = re.findall(r"(https?://[^\s)]+|www\.[^\s)]+)", text)
    linkedin = next((u for u in urls if "linkedin.com" in u.lower()), None)

    name = location = None
    nlp = _get_spacy()
    if nlp:
        doc = nlp(text[:400])
        persons = [ent.text.strip() for ent in doc.ents if ent.label_=="PERSON"]
        gpe = [ent.text.strip() for ent in doc.ents if ent.label_ in {"GPE","LOC"}]
        name = persons[0] if persons else None
        location = gpe[0] if gpe else None

    return {
        "name": name,
        "emails": sorted(set(emails))[:3] or None,
        "phones": sorted(set(phones))[:3] or None,
        "urls": sorted(set(urls))[:5] or None,
        "linkedin": linkedin,
        "location": location,
    }

def extract_education(section_text:str)->List[Dict]:
    out = []
    if not section_text: return out
    text = section_text.replace("Major:", "\nMajor:").replace("Minor:", "\nMinor:")
    lines = [l.strip(" .") for l in text.splitlines() if l.strip()]
    school = degree = field = None
    start = end = None
    for line in lines:
        if re.search(r"(?i)\b(Institute|University|College)\b", line) or re.search(r"\b[A-Z][a-z]+,\s*[A-Z]{2}\b", line):
            school = line
        m_deg = re.search(rf"(?i)\b{DEGREE_PAT}\b", line)
        if m_deg:
            degree = m_deg.group(0)
        if "Major:" in line:
            field = re.sub(r"(?i)major:\s*", "", line).strip()
        elif re.search(r"(?i)\b(BS|BA|MS|MA)\b\s+([A-Za-z &/+#\.-]{2,})", line):
            field = re.sub(r"(?i)\b(BS|BA|MS|MA)\b\s+", "", line).strip()
        m_date = re.search(r"(?i)expected\s+graduation[:\s]+\b([A-Za-z]{3,9}\s+\d{4}|\d{4})", line)
        if m_date:
            end = simple_dateparse(m_date.group(1))
    if school or degree or field or end:
        out.append({"degree": degree, "field": field, "school": school, "start": start, "end": end})
    return out

def tokenize_lower(text:str)->List[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9+\.#/-]*", text.lower())

def ngrams(tokens:List[str], n:int)->List[str]:
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]

def load_lexicons(paths:Optional[List[str]])->set:
    terms = set()
    if not paths: return terms
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    t = line.strip().lower()
                    if t and not t.startswith("#"): terms.add(t)
        except Exception:
            pass
    return terms

def extract_skills_generic(text:str, skills_section:Optional[str]=None, extra_lex:Optional[Iterable[str]]=None)->Dict[str, List[str]]:
    """
    Domain-agnostic skill discovery:
      0) "Programming Languages:" lines
      1) explicit Skills lines (comma/semicolon/pipe)
      2) noun chunks
      3) verb + direct object
      4) external lexicons
      5) soft skills + human languages
    """
    blob = (skills_section + "\n" if skills_section else "") + text
    cand = set()

    # 0) Programming Languages:
    for m in re.finditer(r"(?i)programming languages?\s*:?\s*([^\n]+)", blob):
        items = re.split(r"[,;/]|\band\b", m.group(1))
        for it in items:
            t = normalize_ws(it).lower().strip(".")
            if t and 1 <= len(t) <= 40:
                cand.add(t)

    # 1) Skills lines
    for m in re.finditer(r"(?i)skills?\s*:?\s*(.+)", blob):
        frag = m.group(1)
        parts = re.split(r"[•|,;/]", frag)
        for p in parts:
            t = normalize_ws(p.lower())
            if 1 <= len(t) <= 60 and re.search(r"[a-z0-9]", t):
                cand.add(t)

    # 2) Noun chunks + 3) verb-object
    nlp = _get_spacy()
    if nlp:
        doc = nlp(blob)
        for chunk in doc.noun_chunks:
            toks = [t.lemma_.lower() for t in chunk if not t.is_stop and (t.is_alpha or t.like_num)]
            if 1 <= len(toks) <= 5:
                cand.add(" ".join(toks))
        for tok in doc:
            if tok.pos_ == "VERB":
                objs = [c for c in tok.children if c.dep_ in {"dobj","obj"}]
                if objs:
                    phrase = [tok.lemma_.lower()] + [o.lemma_.lower() for o in objs]
                    cand.add(" ".join(phrase))

    # 4) External lexicons
    extra = set(extra_lex or [])
    if extra:
        text_low = blob.lower()
        for term in extra:
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text_low):
                cand.add(term)

    # 5) Soft skills + human languages
    soft = sorted([s for s in GENERIC_SOFT_SKILLS if re.search(rf"(?i)\b{re.escape(s)}\b", blob)])
    human_langs = ["english","spanish","french","german","mandarin","chinese","hindi","arabic","russian","japanese","korean","italian","portuguese","vietnamese","tagalog"]
    langs = sorted({L for L in human_langs if re.search(rf"(?i)\b{L}\b", blob)})

    GENERIC_JUNK = {"company","document","analysis","experience","assistant","engineering","systems","software","website","through","frequency","hand","minor","august"}
    cand = {c for c in cand if c not in GENERIC_JUNK and len(c) > 2}

    return {
        "skills_all": sorted(cand),
        "soft_skills": soft,
        "languages_human": langs
    }

def _is_acronym(tok:str)->bool:
    return tok.isupper() and 2 <= len(tok) <= 6 and tok.isalpha()

def _valid_token(tok:str)->bool:
    if len(tok) <= 2 and not _is_acronym(tok):
        return False
    if tok in STOPWORDS:
        return False
    if re.fullmatch(r"[0-9\W_]+", tok):
        return False
    return True

def compute_top_phrases(text:str, k:int=50):
    nlp = _get_spacy()
    if nlp:
        doc = nlp(text)
        freq = {}
        # Noun chunks
        for ch in doc.noun_chunks:
            toks = [t.text for t in ch if _valid_token(t.text.lower())]
            if 1 <= len(toks) <= 5:
                key = " ".join([t.lower() for t in toks])
                freq[key] = freq.get(key, 0) + 1
        # Verb + direct object
        for t in doc:
            if t.pos_ == "VERB":
                objs = [c for c in t.children if c.dep_ in {"dobj","obj"}]
                if objs:
                    phrase = [t.lemma_.lower()] + [o.lemma_.lower() for o in objs if _valid_token(o.lemma_.lower())]
                    key = " ".join(phrase)
                    if key.strip():
                        freq[key] = freq.get(key, 0) + 1
        items = sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:k]
        return items
    # Fallback: filtered bigrams/trigrams
    toks = re.findall(r"[A-Za-z][A-Za-z0-9+\.#/-]*", text.lower())
    toks = [t for t in toks if _valid_token(t)]
    def _ngrams(tokens,n):
        return [" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]
    freq = {}
    for n in (2,3):
        for g in _ngrams(toks,n):
            freq[g] = freq.get(g,0)+1
    items = sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:k]
    return items

def extract_certifications(text:str)->List[str]:
    hits = set()
    for m in re.finditer(r"(?i)\b(certified|certification|credential)\b(?:\s+in)?[:\-]?\s*([A-Za-z0-9 +#\-/\.()\[\]]{3,})", text):
        val = normalize_ws(m.group(2)).strip(".,;:()[]").lower()
        if val in {"in","of","license plate","plate"}:
            continue
        hits.add(val)
    for m in re.finditer(r"(?i)\b(license|licence|licensure|registration)\b[:\-]?\s*([A-Za-z0-9 +#\-/\.()\[\]]{3,})", text):
        val = normalize_ws(m.group(2)).strip(".,;:()[]").lower()
        if "license plate" in val or val in {"in","of","plate"}:
            continue
        hits.add(val)
    for m in re.finditer(r"(?i)\b(RN|LPN|CNA|CPA|CFA|PMP|SHRM-CP|SHRM-SCP|SPHR|PE|CFE|PHR|CHFM|CISSP|ITIL|CC)\b", text):
        hits.add(m.group(1).lower())
    return sorted(hits)

def extract_affiliations(section_text:str, whole_text:str)->List[str]:
    hits = set()
    blob = (section_text or "") + "\n" + whole_text
    for m in re.finditer(r"(?i)\b(member|membership|affiliation|association|society|union)\b[^:\n]*[:\-]?\s*([A-Za-z0-9 &\.,\-()]{2,})", blob):
        val = normalize_ws(m.group(2)).strip(".,;")
        val = re.sub(r"^(?i)(of|at|in)\s+", "", val).strip()
        if val and val.lower() not in {"of","at","in"}:
            hits.add(val)
    return sorted(hits)

def parse_experience_section(section_text:str)->List[Dict]:
    if not section_text: return []
    lines = [l for l in section_text.splitlines() if l.strip()]
    exp = []; i = 0
    while i < len(lines):
        line = lines[i]
        m = re.search(r"^(?P<title>[^@\-|•–—]+?)\s+(?:at\s+)?(?P<company>[^|•–—]+?)\s*[|•–—-]\s*(?P<dates>.+)$", line, re.I)
        if not m:
            m = re.search(r"^(?P<company>[^|•–—]+?)\s*[|•–—-]\s*(?P<title>[^|•–—]+?)\s*[|•–—-]\s*(?P<dates>.+)$", line, re.I)
        if m:
            title = normalize_ws(m.group("title"))
            company = normalize_ws(m.group("company"))
            dates = m.group("dates")
            rng = re.search(rf"({DATE_PAT})\s*[-–—]\s*(Present|Current|{DATE_PAT})", dates, re.I)
            start = end = None
            if rng:
                g1 = rng.group(1)
                start = g1 if isinstance(g1, str) else " ".join([x for x in g1 if x])
                start = start.strip()
                dp = _get_dateparser()
                if dp:
                    start = dp.parse(start, settings={"PREFER_DAY_OF_MONTH":"first"})
                    start = start.strftime("%Y-%m") if start else None
                end_token = rng.group(2)
                if isinstance(end_token, tuple): end_token = " ".join(end_token)
                if re.search(r"(?i)present|current", str(end_token)):
                    end = None
                else:
                    if dp:
                        dt = dp.parse(str(end_token), settings={"PREFER_DAY_OF_MONTH":"first"})
                        end = dt.strftime("%Y-%m") if dt else None
            bullets = []
            j = i+1
            while j < len(lines) and re.match(r"^\s*[-•*]", lines[j]):
                bullets.append(re.sub(r"^\s*[-•*]\s*", "", lines[j]).strip()); j += 1
            exp.append({"company": company or None, "title": title or None, "start": start, "end": end, "bullets": bullets})
            i = j
        else:
            i += 1
    return exp

def estimate_years_of_experience(text:str)->float:
    yrs = 0.0
    for m in re.finditer(r"(?i)(\d+)\s*\+?\s*years?", text):
        yrs = max(yrs, float(m.group(1)))
    return yrs

def _clean_skill_phrase(s:str)->bool:
    if re.search(r"\b\d{3}\s*\d{3}\s*\d{4}\b", s):
        return False
    if len(s) <= 2 and not s.isupper():
        return False
    if s in {"o","nx"}:
        return False
    return True

def extract_resume_info(text:str, lexicons:Optional[List[str]]=None)->Dict:
    text = normalize_text_pretty(text)
    extra_terms = load_lexicons(lexicons)
    sections = detect_sections(text)

    info = {}
    info["contact"] = extract_contact(text)
    info["education"] = extract_education(sections.get("education",""))
    info["experience"] = parse_experience_section(sections.get("experience",""))
    skills = extract_skills_generic(text, sections.get("skills"), extra_terms)
    skills["skills_all"] = [s for s in skills["skills_all"] if _clean_skill_phrase(s)]
    info["skills"] = skills
    info["certifications"] = extract_certifications(text)
    info["affiliations"] = extract_affiliations(sections.get("affiliations",""), text)
    info["languages"] = skills.get("languages_human",[])

    info["totals"] = {
        "years_of_experience_est": estimate_years_of_experience(text),
        "top_phrases": compute_top_phrases(text, k=50)
    }

    info["sections"] = {k: v[:2000] for k,v in sections.items()}
    return info

# --- CLI helpers ---
def read_text_from_file(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".pdf":
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""
    if suf == ".docx":
        docx = _get_docx()
        if docx is not None:
            try:
                d = docx.Document(str(path))
                return "\n".join(p.text for p in d.paragraphs)
            except Exception:
                return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

if __name__ == "__main__":
    # Input file path (default to "Sebastian Grammas .pdf" if none provided)
    default_file = "Sebastian Grammas .pdf"
    if len(sys.argv) >= 2:
        in_path = Path(sys.argv[1])
        lexicons = sys.argv[2:] if len(sys.argv) > 2 else None
    else:
        in_path = Path(default_file)
        lexicons = None

    raw = read_text_from_file(in_path)
    result = extract_resume_info(raw, lexicons=lexicons)
    print(json.dumps(result, indent=2, ensure_ascii=False))
