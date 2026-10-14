"""The three prompts the CompanyLens pipeline sends, each with a version string.

Versions are written to the database on every run (``company_research_run.prompt_version``,
``scorer_run.packet_version`` / ``rubric_version``) so a wording change is a visible,
re-runnable event rather than an invisible drift -- the same rule rubric v4.11 applies
to its own builds ("Pin and record the exact model string on every build").

**Reviewer: research-ground-truth**, for fidelity to
``Solverah_IP/ground_truth/rubric/Company_Culture_Evidence_Collector_v4.11.md`` (the
research prompt) and ``Solverah_IP/ground_truth/rater_app/anchors_v3_1_PROPOSED.json``
(the scoring prompt). Every deviation from the source instrument is listed in the
docstring of the function that makes it.

Contract reminders that are enforced elsewhere but worth repeating where the text lives:

* The research prompt carries a COMPANY NAME and public URLs only
  (``solverah.infra.llm.get_research_client``). Nothing about a Solverah user may ever
  be interpolated into it. ``build_research_prompt`` takes a name and a domain; it has
  no parameter through which user content could arrive.
* A pasted job posting is user content and goes to the SCORER client (OpenAI, an
  existing vendor), never to the research client. ``build_posting_extraction_prompt``
  is the only prompt that carries posting text.
"""

from __future__ import annotations

import json
from typing import Optional, Sequence

__all__ = [
    "PARAPHRASE_RULE",
    "POSTING_EXTRACT_PROMPT_VERSION",
    "RESEARCH_PROMPT_VERSION",
    "RESEARCH_SYSTEM",
    "RUBRIC_TEXT_SHA256",
    "SCORING_PROMPT_VERSION",
    "SOURCE_TYPE_GUIDE",
    "build_posting_extraction_prompt",
    "build_research_prompt",
    "build_scoring_instruction",
]

#: The paraphrase rule as the two extraction prompts state it. The gate that enforces it
#: is textcheck.paraphrase_gate; the numbers are constants.PARAPHRASE_*.
PARAPHRASE_RULE = (
    "your own words, for display: no quotation marks of any kind, no run of more than "
    "seven consecutive words copied from the excerpt (fewer for a short excerpt: at most "
    "half its length), and no more than about a third of its three-word phrases reused"
)

# ---------------------------------------------------------------------------
# 1. Research: company name -> evidence items (Anthropic, web search + fetch)
# ---------------------------------------------------------------------------

#: Derived from Collector v4.11 (its source sections A-F, nine hard rules, retrieval
#: guide, scope declaration, two-retrieval-methods rule and the plain-fetch quotation
#: mark warning), adapted to a structured list. Bump on any wording change.
#: v2 (C5b, 2026-10-13): the paraphrase rule as the tightened gate enforces it, the
#: speaker field's employer-reply marking, open postings dated at access, and the
#: careers-page date rule, after research-ground-truth's review.
RESEARCH_PROMPT_VERSION = "cl-research-v2-2026-10-13/collector-v4.11"

#: The source vocabulary the store accepts (model.EVIDENCE_SOURCE_TYPES minus the user
#: paste), each mapped to the v4.11 section it comes from.
SOURCE_TYPE_GUIDE: tuple[tuple[str, str], ...] = (
    ("careers_page", "section A: the company's own careers, values or culture page"),
    ("employee_review", "section B: one employee review on a review site, the reviewer's own prose"),
    ("job_posting", "section C: a currently open job posting, the employer's own sentences"),
    ("first_person", "section D: a first-person account of how they work (handbook, engineering "
                     "blog, culture microsite, leadership interview, repository discussion, "
                     "long-form press profile with direct quotes, conference talk)"),
    ("news", "section E: independent reporting from the last 12 months on an event that bears "
             "on how the company operates"),
    ("disclosure", "section F: the Human Capital part of Item 1 in the most recent 10-K "
                   "(public companies only)"),
)

RESEARCH_SYSTEM = """You are an evidence collector building a sourced evidence record about how one company actually works, so that a separate scorer can later read it on six culture dimensions. You are a RESEARCHER, not a scorer. Your only job is to find and quote real evidence and say exactly where it came from. You do NOT rate the company, rank it, or characterise it on any dimension.

Everything you output must be traceable to a live, current web source. This record will be checked against the original sources, so fidelity is the whole point.

HARD RULES -- a violation makes an item unusable:

1. NO SCORES, NO RATINGS, NO DIMENSION PLACEMENT. Never say a company is "high autonomy", "fast-paced", "collaborative", "leans blunt", and never summarise its culture. If you catch yourself writing an adjective that judges the company, delete it and quote the source instead.

2. VERBATIM ONLY, FROM THE OPENED PAGE. The excerpt field is source text exactly, word for word -- no paraphrasing, tidying or merging. Reproduce the source's own typographical errors. A search engine's result summary is a PARAPHRASE and is never an acceptable excerpt: open (fetch) the page and quote from the page itself. A description of what a set of sources contains is NOT a quote. Machine-written summaries on aggregator pages ("Summary generated by ...") are not quotable; quote the employer's own words beneath them.

   Quotation marks are part of the verbatim content. A fetched rendition of a page can summarise, compress and even invent quotation marks around reported speech. If the page does not put quote marks around a clause, you may not either: a reporter's sentence attributed to a named executive as if spoken is a fabricated quote, and it passes a URL-level check. Where you cannot confirm the exact wording of a passage, quote nothing from it.

3. EVERY EXCERPT IS SOURCED AND ATTRIBUTED. Each item carries the exact URL, the source type, a date, and WHO is speaking. Never blend an employee's words with the company's response to it. No URL + date: do not include it. Do not use training-data memory for any factual claim. When a first-party page publishes no date, use the date you accessed it and mark it as an access date (the date_is_access_date flag), never as a bare publication date.

4. WORK THE SOURCE MIX BEFORE YOU DECLARE ABSENCE. Sections A, B and C exist for essentially every employer; a shortfall there means go back and collect more. Sections D, E and F must be attempted; a zero yield after a real attempt is a finding about the company, not a failure.

5. REPORT GENUINE ABSENCE HONESTLY. Never invent, estimate, or backfill from reputation.

6. BALANCE, AND NO CURATION. For reviews, include BOTH positive and critical excerpts. Take the most recent ones in date order -- do not select the most interesting, most culture-revealing or most representative. Selecting on content biases the record in a way nobody downstream can detect.

7. DATE EVERYTHING, AND NEVER HIDE AGE. Evidence age is itself evidence.

8. RECORD WHICH POPULATION YOUR EVIDENCE DESCRIBES. Large companies contain several genuinely different working environments. Do not narrow your research to one division, office or function, and do not rebalance to compensate -- record the scope of each item (company / division / location / role, with a label) and state in the scope declaration which population the reviews come from.

9. AN EVALUATIVE METRIC IS NEVER EVIDENCE. Recommendation rates, CEO approval, star ratings and similar measure how a writer FEELS; the dimensions describe what an environment IS. Do not include them as items. Any percentage must be achievable at its stated sample size or it is struck.

NEVER sign in to resolve a wall, and never collect anything behind a login. Content only reachable while authenticated cannot be reproduced and must not be used.

Employer responses on review sites are company-authored: tag them as careers_page in spirit (source_type careers_page), never as employee_review, record the response date rather than the review date, and make the speaker field BEGIN with "employer response". The speaker field is how a reader tells the company's voice from an employee's: for a review it names the reviewer's role ("employee review, Sales Associate"), for company material it names the page or the person ("company careers page", "CEO, interview"), and for an employer's reply it says so.

Interview write-ups mis-filed among reviews are about getting hired, not working there: exclude them.

Job postings: open every posting individually and check it is still open. Quote the posting's own sentences from the "what you'll do", "how you work", responsibilities and expectations blocks. Do not quote salary bands, office locations or site names.

News: recruiting-SEO pages, interview-prep sites, job aggregators, content farms and encyclopedia entries are not reporting. Company-authored material (press releases, earnings releases, company blogs) is not reporting either; it is the company's own voice and belongs under careers_page or first_person, never under news.

Disclosure: public companies only. Quote only the Human Capital part of Item 1 of the latest 10-K, and strip every headcount, dollar figure and percentage as you collect. Quote the sentences describing practice, not the metrics attached to them.

You are a researcher and the people reading your record are not. Where a source is unreachable or a section is thin, record the limitation precisely and move on. A recorded limitation is a usable record; an unrecorded one is a corrupt record."""


def build_research_prompt(company_name: str, domain: Optional[str] = None) -> str:
    """The user turn for one company. Company name and official domain only.

    Deviations from Collector v4.11, each deliberate:

    * OUTPUT is a JSON object, not the packet's plain-text sections, because the
      consumer is the scorer rather than a rater. Sections A-F survive as
      ``source_type``; the scope block survives as a per-item ``scope`` + ``scope_label``
      and a one-line ``scope_declaration``; Section 3's headcount survives as the
      ``company`` block. Section 2 (researcher QA) is not requested: its audit lines
      exist for a human reviewer, and the verification here is mechanical.
    * Each item also carries a PARAPHRASE. v4.11 forbids paraphrase in the packet
      (rule 2) because the packet is scored verbatim; here the verbatim excerpt is still
      what gets scored, and the paraphrase is the only text a user may ever see
      (GAP-14). The pipeline rejects a paraphrase that carries a quotation mark, shares
      too long a run of words with its excerpt (or with anything else cited from the
      same page) or reuses too many of its phrases (``PARAPHRASE_RULE``), so the model
      is told the rule.
    * Open job postings are dated at access: a posting confirmed open is current by
      construction, like a pasted one. A careers page whose only date is the access
      date is recorded as access-dated, never as published that day.
    * The model is asked to write each excerpt as a cited line BEFORE the JSON. The
      research API attaches a citation (the verbatim cited_text) to text it quotes from a
      search result or a fetched page, and the pipeline verifies every excerpt against
      those citations, dropping any it cannot match -- the production stand-in for
      v4.11's "every excerpt confirmed on a rendered copy of the page".
    * Per-section minimums are v4.11's (A 5-8, B 12-15, C 6-10 from 3+ open postings
      across functions, D target 3, E target 2 max 4, F target 3 max 6); the two review
      sites rule (Indeed text, Glassdoor recency cross-check only) is stated in one line.
    """
    name = (company_name or "").strip()
    if not name:
        raise ValueError("build_research_prompt needs a company name")
    about = "Company: %s" % name
    if domain:
        about += "\nOfficial website: %s" % domain

    guide = "\n".join("  - %s: %s" % (key, text) for key, text in SOURCE_TYPE_GUIDE)
    example = {
        "company": {
            "official_domain": "example.com or null",
            "headcount": "integer or null -- approximate total employees",
            "headcount_as_of": "YYYY-MM-DD or null -- the date the figure is from",
            "headcount_source": "where the figure came from, or null",
        },
        "scope_declaration": (
            "One sentence: which population the employee reviews come from, which parts "
            "of the company are not represented in them, and that company-authored "
            "sources describe the whole organisation."
        ),
        "items": [
            {
                "source_type": "one of the six source types",
                "scope": "company | division | location | role",
                "scope_label": "e.g. 'Engineering', 'Austin office', 'Store associate'; null at company scope",
                "url": "the exact URL you opened",
                "date": "YYYY-MM-DD, or null if none could be established",
                "date_is_access_date": "true when the page publishes no date and 'date' is the day you accessed it",
                "speaker": "who is speaking: 'company careers page', 'employee review, Sales Associate', 'CEO, interview', 'employer response', ...",
                "excerpt": "the verbatim source text, exactly as it appears on the opened page",
                "paraphrase": "the same point in " + PARAPHRASE_RULE,
            }
        ],
    }

    return f"""{about}

Collect sourced, verbatim evidence about how this company actually works, following the rules you have been given. Source mix and minimum yield (counts are verbatim excerpts, not pages opened):

  A. careers_page: minimum 5, maximum 8 excerpts from the official careers, values or culture pages. Abundant and low-value; do not over-collect.
  B. employee_review: minimum 12 reviews, target 15, one review per item, most recent first company-wide, with the reviewer's job title in scope_label where stated. First establish how many employer entities the review site holds for this company (renamed, parent, subsidiary and auto-generated variants) and collect across all of them newest-first. Take review TEXT from Indeed (continuous prose); use Glassdoor only to check whether Indeed's newest review is materially older, and never quote Glassdoor's Pros/Cons fragments. Record each review's date, title and location. Mark a review truncated at source with [...] where the text ends mid-review.
  C. job_posting: minimum 6 excerpts, target 10, from at least 3 CURRENTLY OPEN postings across different functions, at least one outside engineering. Open (fetch) each posting and confirm it is open; a listing page's recency label is not proof, and a posting you did not open is not usable. Date each posting item with the day you opened it and set date_is_access_date to true: an open posting is current by construction. If the company affirmatively has no open roles anywhere (an empty rendered list on its live board, confirmed on two independent sources), record that as a finding instead.
  D. first_person: target 3 substantive passages, working down this ladder: public handbook or "how we work" docs; engineering/product/design blog (open the most recent substantive post from the index, not a topic search); values manifesto or culture microsite with narrative text; leadership interview or podcast transcript on how decisions get made; public repository discussions, RFCs, contribution guidelines; long-form press profile with direct employee or executive quotes; conference talks. Anything older than about 18 months is stale: note it and continue down the ladder. If every passage is an executive voice, work one more rung looking for a non-executive account.
  E. news: target 2, maximum 4 excerpts of independent reporting from the last 12 months on events that bear on how the company operates (reorganisation, layoffs, new leadership, strategy shift, ownership change, return-to-office, funding). Run at least two differently phrased searches before concluding there is none.
  F. disclosure: public companies only, target 3, maximum 6 excerpts from the Human Capital part of Item 1 of the most recent 10-K, figures stripped. Private company: skip.

Source types:
{guide}

What evidence to look for (a retrieval guide only, NOT things to score): how work gets directed (job-post verbs, approval layers, process language, micromanagement vs freedom, decision rights, remote-trust language); tempo and intensity (ship frequency, deadlines, on-call, hours, crunch, burnout vs calm); solo vs group work (team structure, meetings and pairing, open-plan vs deep work, "we win together" vs "own your area"); feedback style (candor and directness in values, review-cycle frequency, blunt vs supportive delivery, debate norms); execute/optimise vs invent/explore (R&D emphasis, 0-to-1 vs operational excellence, tolerance for failed bets); and how decisions get made (data-driven language, A/B testing and metrics-gated launches vs founder judgement or design-led calls).

Two retrieval methods exist and reach different pages: first-party sites are often JavaScript apps that return an empty shell to a plain fetch, and review and job aggregators often show a sign-in wall to a rendering browser. Before recording any source as absent, try the other route. Also find the company's official website domain and an approximate current headcount with its date and source.

Work in two parts.

PART 1 -- EVIDENCE LINES. For every excerpt you intend to include, write one line quoting it exactly from the page you opened, so that your quotation carries a citation to that page. One excerpt per line.

PART 2 -- THE RECORD. After the evidence lines, output exactly one JSON object and nothing after it, in this shape (the values here describe what goes in each field):

{json.dumps(example, indent=2)}

Every item in the JSON must be one of the excerpts you quoted in Part 1, with the same wording, and each excerpt must be quoted whole from the page you opened: an excerpt is checked word by word against what you cited from that page, and an excerpt that is only partly in the citation, or that comes from a page you only saw in search results, is discarded. The excerpt and the paraphrase are different texts: the excerpt is the source's words, the paraphrase is {PARAPHRASE_RULE}."""


# ---------------------------------------------------------------------------
# 2. Scoring: evidence items -> per-item, per-dimension bands (OpenAI, structured)
# ---------------------------------------------------------------------------

#: The rubric text itself is `causal_graph.scorer_pipeline.build_rubric_text(anchors)`
#: on anchors v3.1 -- imported, byte-identical to the validated harness. This version
#: names the per-item INSTRUCTION wrapped around it. v2 (C5b, 2026-10-13): the
#: item-level abstain clauses (review F10), the speaker line and the scrub note.
SCORING_PROMPT_VERSION = "cl-score-v2-2026-10-13/anchors-v3.1"

#: SHA-256 of `build_rubric_text(anchors_v3_1)` as served under SCORING_PROMPT_VERSION.
#: `build_rubric_text` lives in research-ground-truth's harness and is IMPORTED here, so
#: an edit there would otherwise change production scoring without a version bump.
#: tests/test_company_research_pipeline.py recomputes this; a mismatch means the words
#: the scorer reads have changed and SCORING_PROMPT_VERSION must move with them.
RUBRIC_TEXT_SHA256 = "d2ef4dc9c33faf111623bd1f5652cda74257ef3e01dedc279d7ff2da8fbc0ebe"


def build_scoring_instruction(item_keys: Sequence[str], dimensions: Sequence[str],
                              score_bands: Sequence[float],
                              confidence_bands: Sequence[float],
                              scrub_replacement: Optional[str] = None) -> str:
    """The instruction after the rubric and the items, for one batch.

    Deviations from ``scorer_pipeline.score_packet``'s instruction, each deliberate:

    * The unit scored is ONE EVIDENCE ITEM, not a packet. The rubric's gates and bands
      are unchanged; what changes is that the model is told an item usually bears on one
      or two dimensions and must abstain (insufficient evidence) on the rest, which is
      the v3.1 skip used as designed rather than as an escape hatch.
    * At item level, a band whose text says "no strong signal" or "no dominant signal"
      (the 0.5 text on autonomy and pace) means ABSTAIN, not 0.5: one item either
      speaks to a dimension or it does not. The rubric preamble's caution against
      over-using the skip is about a whole packet and does not apply per item. Neither
      sentence edits the anchors (v3.1 is frozen); both are said here, around them.
    * Items are scored INDEPENDENTLY: an item's score may not draw on another item in
      the batch, nor on anything the model knows about the company. The batch shares
      the rubric text and nothing else. The company's name and domain are replaced by
      *scrub_replacement* in the items before the model sees them, and it is told so.
    * No evidence quotes are requested per item: the item IS the quote. The rubric text
      still mentions quoting (it is the validated text, unchanged); this instruction
      says quotes are not part of the answer here.
    """
    keys = ", ".join(item_keys)
    dims = ", ".join(dimensions)
    scrub = (
        f" The company's name has been replaced by '{scrub_replacement}' throughout the "
        "items; do not try to work out which company it is."
        if scrub_replacement else ""
    )
    return (
        "Score EACH evidence item above separately against the rubric on these six "
        f"dimensions: {dims}. The items are keyed {keys}; answer under the same keys. "
        f"For each item and each dimension, choose a score from exactly these band values: "
        f"{list(score_bands)}, and a confidence from exactly these band values: "
        f"{list(confidence_bands)} -- OR record insufficient evidence for that dimension "
        "by setting BOTH score and confidence to null. A single item usually bears on one "
        "or two dimensions and says nothing about the others: for those, record "
        "insufficient evidence. Never choose 0.5 as a stand-in for 'this item does not "
        "speak to it'; 0.5 means the item genuinely describes a mixed or balanced position. "
        "Where a band's text says 'no strong signal' or 'no dominant signal', that "
        "describes a whole packet with nothing decisive in it; for ONE item it means the "
        "item does not speak to the dimension, so record insufficient evidence rather "
        "than that band. The rubric's caution against over-using insufficient evidence "
        "is about a whole packet and does not apply to a single item: abstaining on most "
        "dimensions for most items is the expected answer here. "
        "Each item names its speaker (the reviewer's role, the company's page, the "
        "executive interviewed, or an employer's response); read it as the rubric's gate "
        "on who is speaking asks, and give your confidence as the rubric's confidence "
        "bands define it, about the evidence in that one item. "
        "Score each item ONLY from its own text, its speaker, its source type, its scope "
        "and its date. Do not let one item inform another, do not use outside knowledge, "
        "web search or tools, even if you recognise the company." + scrub +
        " Evidence quotes are not part of this answer: each item is itself the quote."
    )


# ---------------------------------------------------------------------------
# 3. Posting extraction: a pasted posting -> role-scope excerpts (OpenAI, structured)
# ---------------------------------------------------------------------------

#: v2 (C5b, 2026-10-13): the paraphrase rule as the tightened gate enforces it.
POSTING_EXTRACT_PROMPT_VERSION = "cl-posting-v2-2026-10-13/collector-v4.11-C"


def build_posting_extraction_prompt(posting_text: str, title: Optional[str] = None) -> str:
    """The user's pasted posting, to be cut into verbatim role-scope excerpts.

    Follows Collector v4.11 section C ("quote the posting's own sentences from the
    'what you'll do', 'how you work', responsibilities and expectations blocks; do not
    quote salary bands, office locations or site names") and rule 2 (verbatim only).
    Every excerpt is verified by containment against the pasted text before it is
    written, so an invented sentence is dropped rather than scored. SCORER CLIENT
    ONLY: this text is user content.
    """
    head = "Job posting"
    if title:
        head += " (title as given by the user: %s)" % title.strip()
    example = {
        "items": [
            {
                "excerpt": "one verbatim sentence or bullet from the posting, exactly as pasted",
                "paraphrase": "the same point in " + PARAPHRASE_RULE,
            }
        ],
    }
    return f"""{head}. The text below was pasted by a user; treat it as the posting's own words and nothing else.

Extract between 0 and 10 verbatim excerpts that bear on how the role actually works: how work is directed (approval, process, ownership language), tempo and intensity, solo vs group work, feedback and communication style, execute/optimise vs invent/explore, and how decisions are made. Quote only sentences from the responsibilities, expectations, "what you'll do" and "how you work" parts. Do NOT quote salary or pay ranges, office locations, site names, benefits lists, equal-opportunity boilerplate, or application instructions. Do not place the role on any dimension and do not use judging adjectives of your own. If nothing in the posting bears on how the role works (a pure requirements list), return an empty items list.

Each excerpt must appear in the posting text exactly, character for character apart from whitespace. Each paraphrase is {PARAPHRASE_RULE}.

Answer with one JSON object in this shape:
{json.dumps(example, indent=2)}

POSTING TEXT:
{posting_text}"""
