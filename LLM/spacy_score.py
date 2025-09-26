import re
import spacy
from spacy.matcher import PhraseMatcher
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer

nlp = spacy.load("en_core_web_sm")

# --- 1) Candidate phrase extraction ---
def extract_candidates(text, min_len=3, max_len=6):
    doc = nlp(text)
    cands = []

    # (a) noun chunks
    for chunk in doc.noun_chunks:
        toks = [t.lemma_.lower() for t in chunk if not t.is_stop and t.is_alpha]
        if 1 <= len(toks) <= max_len:
            cands.append(" ".join(toks))

    # (b) adjective/compound + NOUN/PROPN spans
    for token in doc:
        if token.pos_ in {"NOUN","PROPN"}:
            left_mods = [t for t in token.lefts if t.dep_ in {"amod","compound"}]
            if left_mods:
                toks = [t.lemma_.lower() for t in left_mods + [token] if t.is_alpha and not t.is_stop]
                if min_len <= len(toks) <= max_len:
                    cands.append(" ".join(toks))

    # (c) verb + direct object (actionable competencies)
    for token in doc:
        if token.pos_ == "VERB":
            dobj = [c for c in token.children if c.dep_ in {"dobj","obj"} and c.pos_ in {"NOUN","PROPN"}]
            if dobj:
                span = [token.lemma_.lower()] + [d.lemma_.lower() for d in dobj]
                if len(span) <= max_len:
                    cands.append(" ".join(span))

    # keep phrases with digits/specials too (e.g., iso 9001) via regex scan
    for m in re.finditer(r"\b([A-Za-z0-9]+(?:[-/ ][A-Za-z0-9]+){0,4})\b", text):
        s = m.group(1).strip()
        if any(ch.isdigit() for ch in s) and len(s) >= 4:
            cands.append(s.lower())

    # normalize & filter
    cands = [re.sub(r"\s+", " ", c.strip()) for c in cands]
    cands = [c for c in cands if len(c.split()) <= max_len and len(c) >= 3]
    return cands

# --- 2) Rank candidates from JD via TF-IDF ---
def rank_candidates_tfidf(jd_text, candidates, top_n=60):
    # de-duplicate while keeping order
    uniq = list(dict.fromkeys(candidates))
    if not uniq:
        return []

    # simple TF-IDF on the JD only (acts like term frequency with smoothing)
    vect = TfidfVectorizer(vocabulary=uniq, ngram_range=(1,3), analyzer="word")
    X = vect.fit_transform([jd_text])
    scores = X.toarray()[0]
    items = sorted(zip(vect.get_feature_names_out(), scores), key=lambda x: x[1], reverse=True)
    # filter out zero-score and take top_n
    items = [w for w,s in items if s > 0][:top_n]
    return items

# --- 3) Experience extraction around phrases ---
def extract_years_map(text):
    out = {}
    for m in re.finditer(r"(\d+)\s*\+?\s*years?\b.{0,40}?\b(of|in)?\b\s*([A-Za-z][A-Za-z0-9+\-/ ]{0,40})", text, re.I):
        yrs = int(m.group(1))
        area = m.group(3).lower().strip()
        out[area] = max(out.get(area, 0), yrs)
    return out

def experience_match_dynamic(jd_phrases, jd_text, resume_text):
    jd_years = extract_years_map(jd_text)
    resume_years = extract_years_map(resume_text)

    # loose containment: if a jd phrase appears in a jd_years key, compare; otherwise skip
    need = 0; hits = 0
    for area, yrs in jd_years.items():
        need += 1
        # find any resume key that overlaps the area tokens
        found_keys = [k for k in resume_years if area in k or k in area]
        if found_keys and max(resume_years[k] for k in found_keys) >= yrs:
            hits += 1
    return hits / max(1, need)

# --- 4) Coverage using dynamic phrase set ---
def dynamic_coverage(jd_phrases, resume_text):
    pm = PhraseMatcher(nlp.vocab, attr="LOWER")
    patterns = [nlp.make_doc(p) for p in jd_phrases]
    if not patterns:
        return 0.0, set(), set()
    pm.add("DYN", patterns)

    doc_r = nlp(resume_text)
    found = set(doc_r[st:en].text.lower() for _, st, en in pm(doc_r))

    jd_set = set([p.lower() for p in jd_phrases])
    matched = jd_set & found
    missing = jd_set - found
    cov = len(matched) / max(1, len(jd_set))
    return cov, matched, missing

# --- 5) End-to-end: build dynamic set + compute features ---
def dynamic_skill_features(jd_text, resume_text, top_n=60):
    cands = extract_candidates(jd_text)
    jd_phrases = rank_candidates_tfidf(jd_text, cands, top_n=top_n)

    coverage, matched, missing = dynamic_coverage(jd_phrases, resume_text)
    exp = experience_match_dynamic(jd_phrases, jd_text, resume_text)

    return {
        "dynamic_phrases": jd_phrases,
        "coverage": round(coverage, 3),
        "experience_match": round(exp, 3),
        "matched": sorted(matched),
        "missing": sorted(missing)
    }


    