import re
import spacy
from spacy.matcher import PhraseMatcher, Matcher

nlp = spacy.load("en_core_web_sm")

LEX = {
    "research": [
        "research", "prototype", "prototyped", "experiment", "experimental",
        "analyze", "analysis", "investigate", "algorithm", "benchmark",
        "paper", "publication", "literature review"
    ],
    "learning": [
        "coursework", "certification", "certified", "completed course",
        "competition", "ctf", "self-taught", "bootcamp", "learned", "quickly learned"
    ],
    "communication": [
        "presented", "presentation", "documented", "documentation", "wrote",
        "report", "explained", "taught", "mentored", "communicated"
    ],
    "teamwork": [
        "collaborated", "cross-functional", "worked with", "stakeholders",
        "pair programming", "peer review", "with designers", "with pm", "with product"
    ],
    "leadership": [
        "led", "lead", "organized", "spearheaded", "owned", "drove", "recruited",
        "managed", "coordinated", "mentored"
    ],
    "impact": [
        "improved", "optimized", "reduced", "increased", "accelerated",
        "scaled", "decreased", "boosted"
    ],
    "reliability": [
        "tested", "tests", "unit tests", "integration tests", "ci/cd", "code review",
        "on-call", "playbook", "runbook", "sop", "monitoring", "observability"
    ]
}

def build_phrase_matcher(nlp, lexicon):
    pm = PhraseMatcher(nlp.vocab, attr="LOWER")
    for label, phrases in lexicon.items():
        pm.add(label.upper(), [nlp.make_doc(p) for p in phrases])
    return pm

def build_impact_number_matcher(nlp):
    m = Matcher(nlp.vocab)
    # e.g., "improved X by 25 %", "reduced latency 30%", "increased by 2x"
    m.add("IMPACT_NUM", [
        [{"LEMMA": {"IN": ["improve","reduce","increase","optimize","boost","scale","decrease","accelerate"]}},
         {"OP": "*", "IS_ALPHA": True, "OP": "*"},
         {"LOWER": {"IN": ["by"]}, "OP": "?"},
         {"LIKE_NUM": True},
         {"LOWER": {"IN": ["%","percent","x","times","ms","s","hrs","hours","days","kb","mb","gb"]}, "OP": "?"}]
    ])
    return m

PM = build_phrase_matcher(nlp, LEX)
IMPACT_NUM = build_impact_number_matcher(nlp)

def soft_skills_score(text):
    doc = nlp(text)

    # Count phrase matches
    counts = {k: 0 for k in LEX}
    spans = []
    for label, start, end in PM(doc):
        cat = nlp.vocab.strings[label].lower()
        counts[cat] += 1
        spans.append((cat, doc[start:end].text))


    # Impact numbers near impact verbs
    impact_hits = IMPACT_NUM(doc)
    counts["impact"] += len(impact_hits)

    # Normalize per category (cap at 5 so long resumes don't dominate)
    norm = {k: min(v, 5)/5.0 for k, v in counts.items()}

    # Weights (tune as you like; must sum ~1.0)
    W = {
        "research": 0.20,
        "learning": 0.15,
        "communication": 0.15,
        "teamwork": 0.15,
        "leadership": 0.10,
        "impact": 0.15,
        "reliability": 0.10
    }
    composite = sum(W[k]*norm[k] for k in W)

    # Collect evidence snippets for explainability
    evidence = {k: [] for k in LEX}
    for cat, span_text in spans:
        if len(evidence[cat]) < 6:
            evidence[cat].append(span_text)

    return {
        "category_raw_counts": counts,
        "category_scores": {k: round(norm[k], 3) for k in norm},
        "soft_skills_score": round(composite, 3),
        "impact_numeric_mentions": len(impact_hits),
        "evidence": evidence
    }
