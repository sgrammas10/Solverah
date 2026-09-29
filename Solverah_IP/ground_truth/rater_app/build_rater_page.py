#!/usr/bin/env python3
"""
Generate a self-contained rater scoring page from a scrubbed packet.

    python build_rater_page.py --packet ../anonymization/P-01_packet_RATER_DRAFT.txt \
                              --packet-id P-01 --rater A --out ./out

Design constraints this implements, and why:

  * ONE PACKET PER FILE, no cross-company view. Scores are absolute positions on a
    shared person-company scale, not a ranking of these six. A rater who can see two
    packets scores the second relative to the first and the scale silently becomes
    ordinal within the set.
  * ALL SIX DIMENSIONS VISIBLE, SCORED IN ANY ORDER, EACH LOCKING ON COMMIT.
    Raters asked to hold all six in mind so they read the packet once - reasonable,
    and re-reading 18k characters six times is its own source of error through fatigue.
    The control that survives is the lock: a committed dimension cannot be reopened,
    so the six scores cannot be retro-tuned into a coherent-looking profile after the
    fact. Known cost, recorded deliberately: a single overall impression will still
    correlate the six scores, so a wide A-vs-B gap cannot be cleanly attributed to
    anchor ambiguity rather than to one rater's read of the whole company. The blind
    re-score is the only remaining purchase on that, and is therefore not optional.
  * CLICK-TO-CITE, MULTI-TAG. Evidence is selected from the packet text, never typed,
    and one quote can be filed against several dimensions. Guarantees the citation
    string-matches for the verification harness, leaves "I just know this company"
    with no field to go in, and yields a per-rater quote-to-dimension matrix as a
    by-product - which is the thing to compare BEFORE comparing scores.
  * LOCK ON SUBMIT. After submit the file is read-only. Prevents a rater revisiting
    P-01 after reading P-05: the comparison contamination, just delayed.
  * TIMESTAMPS. Session start, per-dimension commit, submit. A four-minute sitting and
    a fifty-minute sitting are different instruments; you want to see which you got.
    Commit order is also recorded - which dimension a rater felt able to score first
    is worth knowing.

Anchor text lives in anchors.json and is a swap-in. Regenerate after Julie rewrites it.
"""

import argparse
import hashlib
import html as htmllib
import json
import pathlib
import re as _re


# ---------------------------------------------------------------------------
# Packet -> addressable excerpts
#
# The packet used to be dropped into the page as one escaped text blob, so a citation was
# whatever characters the rater happened to drag over. Whether the source attribution came
# with it was luck of the drag — and the <=0.7 measurement turns on whether a
# NON-COMPANY-AUTHORED source supports a score. Reading that off the tail of a quote string
# is inference; it should be recorded.
#
# So: wrap every excerpt line in a span carrying its section, its index and its source class.
# A citation then reports where it came from no matter how sloppily it was selected.
# ---------------------------------------------------------------------------

_SECTION_RE = _re.compile(r"^\s*---\s*([A-F])\.\s")
_EXCERPT_RE = _re.compile(r"^\s*[•·]\s")

# All six rater-facing content ends at this structural marker, identical byte-for-byte
# across every packet: "########## END OF PACKET ##########". Cutting on the literal
# string "SCRUB LOG" instead (the old approach) is fragile: it only works because all six
# scrub logs today happen to use that exact heading. If a future scrub log used any other
# heading, the whole operator log -- which has already been shown to carry a company name
# inside a defect note (P-06) -- would ship silently into a rater's page. scorer_variance_
# test_v2.py already anchors on this same "END OF PACKET" marker for the identical reason
# and refuses to guess if it's missing; do the same here rather than falling back to
# "include everything," which is the more dangerous failure mode of the two.
_END_OF_PACKET_RE = _re.compile(r"^#{3,}\s*END OF PACKET\s*#{3,}\s*$", _re.MULTILINE)


# A company-run outlet is "company/employer" + a publication noun, in either order and with
# anything between. A fixed substring list missed P-01's "[company engineering/design blog]"
# because of the slash — the kind of near-miss that would have silently mis-measured a whole
# section, so match the structure instead of enumerating the phrasings.
_COMPANY_RUN_PUBLICATION_RE = _re.compile(
    r"(company|employer)[^\]]{0,40}?(blog|newsroom|magazine|microsite|publication)"
    r"|(blog|newsroom|magazine|microsite|publication)[^\]]{0,20}?(company|employer)")
_EXEC_BYLINE = ("chief executive", "ceo,", "founder", "(executive)")


def classify_source(attribution: str, byline: str = None) -> str:
    """company | noncompany | disputed | unknown.

    'unknown' is a build-time error and is never shipped silently.

    'disputed' exists because of an OPEN QUESTION, not because of ambiguity in the text:
    does employee-bylined writing published on a company-run site count as company-authored
    for the <=0.7 measurement? (08-15 handoff, open question 5.) If yes, a company can never
    be supported by its own engineers writing about their work. If no, any company can evade
    the measurement by publishing employee bylines. P-05's whole Section D is this case, as
    are P-02's interns and P-06's field manager. The page RECORDS the class rather than
    resolving it, so the answer can be applied to existing scores without re-rating.
    """
    a = attribution.lower()
    # Order matters. An employee review can name the company; a 10-K can describe
    # "independent contractor advisors"; a trade-press piece can quote a company document.
    if "researcher observation" in a or "absence recorded" in a:
        # P-05's section C records ABSENCE — four pages checked, zero open roles — as dated
        # evidence. It is a real and deliberate packet entry, but it is the builder speaking,
        # not a source. It must never count toward the <=0.7 measurement in either direction.
        return "researcher"
    if "employee review" in a:
        return "noncompany"
    if ("independent," in a or "trade press" in a or "business press" in a
            or "not company-authored" in a):
        return "noncompany"
    # Test the SOURCE-CLASS BRACKET only, not the whole attribution. Scanning the full string
    # matched P-06's careers-page lines on the words "no publication date shown", which would
    # have marked eight company-authored excerpts as disputed.
    bracket = _re.match(r"\s*—\s*\[([^\]]*)\]", attribution)
    pub_field = bracket.group(1).lower() if bracket else a
    if _COMPANY_RUN_PUBLICATION_RE.search(pub_field):
        # Company-run outlet. Executive voice is unambiguously the company speaking;
        # an individual employee byline is the disputed case.
        #
        # Byline is checked SEPARATELY from publication, because in P-05 the two live in
        # different places: the publication is named in the section note, the byline in each
        # group's preamble. The section note also happens to say "the founder and CEO" while
        # describing the section's mix — which, checked together, marked two engineer-written
        # posts as executive voice.
        b = (byline if byline is not None else attribution).lower()
        return "company" if any(e in b for e in _EXEC_BYLINE) else "disputed"
    if ("company-authored" in a or "employer-authored" in a or "employer," in a
            or "regulatory filing" in a or "10-k" in a or "company website" in a
            or "company careers" in a or "company code" in a or "job posting" in a
            or "company values" in a or "attributed on the page" in a):
        return "company"
    return "unknown"


def build_packet_markup(text: str):
    """Return (html, stats). Excerpt blocks become addressable spans; everything else is plain.

    Works on BLANK-LINE-SEPARATED BLOCKS, not lines, because the six packets use three
    different excerpt shapes and all three have to classify correctly:
      * one line per excerpt, attribution inline            (P-02, P-03, P-06)
      * excerpt body wrapped over several lines, attribution on a later line   (P-01, P-04)
      * a group of excerpts sharing one preamble line       (P-05 section D)
    The variation is itself a finding about the collector prompt. It is recorded in the
    handoff rather than smoothed over here.
    """
    out = []
    stats = {"excerpts": 0, "company": 0, "noncompany": 0, "disputed": 0, "researcher": 0, "unknown": []}
    section, idx = "?", 0
    section_note, group_preamble = "", ""

    lines = text.split("\n")
    blocks, cur = [], []
    for line in lines:
        if line.strip():
            cur.append(line)
        else:
            if cur: blocks.append(cur); cur = []
            blocks.append(None)          # preserves the blank line
    if cur: blocks.append(cur)

    for blk in blocks:
        if blk is None:
            out.append("")
            continue
        joined = "\n".join(blk)
        m = _SECTION_RE.match(blk[0])
        if m:
            section, idx = m.group(1), 0
            section_note, group_preamble = "", ""
            out.append(htmllib.escape(joined))
            continue
        # An excerpt block starts with a bullet AND carries a quoted body. A bullet without a
        # quote is prose (P-05's section C exemption note), not evidence.
        if _EXCERPT_RE.match(blk[0]) and '"' in joined:
            idx += 1
            eid = f"{section}{idx}"
            # The source class is the FIRST em-dash-bracket group in the block; everything
            # from there on is attribution. Anchoring on the body's closing quote instead
            # fails on real packets: P-01 puts a truncation marker between the quote and the
            # dash ("…" […]  — [employee review]), and P-04 puts a bracketed note there.
            bm = _re.search(r"—\s*\[", joined)
            if bm:
                attribution = joined[bm.start():]
                src = classify_source(attribution)
            else:
                # Inherited attribution: publication comes from the section note, byline from
                # this group's own preamble. Keep them apart.
                src = classify_source(group_preamble + " || " + section_note,
                                      byline=group_preamble)
            stats["excerpts"] += 1
            if src == "unknown":
                stats["unknown"].append((eid, blk[0][:100]))
            else:
                stats[src] += 1
            out.append(
                f'<span class="ex" data-eid="{eid}" data-sec="{section}" '
                f'data-ix="{idx}" data-src="{src}">{htmllib.escape(joined)}</span>')
            continue
        group_preamble = " ".join(x.strip() for x in blk)
        if not section_note:
            section_note = group_preamble
        out.append(htmllib.escape(joined))
    return "\n".join(out), stats


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solverah scoring &mdash; packet __PACKET_ID__ &mdash; rater __RATER__</title>
<style>
  :root {
    --ink:#16181d; --muted:#6b7280; --line:#e2e5ea; --bg:#fbfbfc;
    --accent:#1f4e79; --warn:#8a5a00; --warnbg:#fff8e6;
    --ok:#1a6b3c; --okbg:#eef7f1; --okline:#b8dcc6; --sel:#fff3b0;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .wrap { max-width:1560px; margin:0 auto; padding:20px; }
  header { border-bottom:2px solid var(--ink); padding-bottom:12px; margin-bottom:18px; }
  header h1 { margin:0 0 4px; font-size:19px; }
  header .meta { color:var(--muted); font-size:13px; }
  .cols { display:grid; grid-template-columns: 1fr 1fr; gap:22px; align-items:start; }
  @media (max-width:1150px){ .cols{ grid-template-columns:1fr; } }

  .panel { background:#fff; border:1px solid var(--line); border-radius:8px; margin-bottom:16px; }
  .panel > h2 { margin:0; padding:11px 15px; font-size:13px; text-transform:uppercase;
                letter-spacing:.08em; color:var(--muted); border-bottom:1px solid var(--line); }
  .panel .body { padding:15px; }

  #packet { position:sticky; top:20px; max-height:calc(100vh - 40px);
            display:flex; flex-direction:column; margin-bottom:0; }
  #packetText { overflow:auto; white-space:pre-wrap; word-wrap:break-word;
                font:12.5px/1.65 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
                padding:15px; flex:1; }
  #packetText::selection { background:var(--sel); }

  #tagbar { border-top:1px solid var(--line); padding:10px 13px; background:#f7f9fb;
            border-radius:0 0 8px 8px; }
  #tagbar.off { display:none; }
  #tagbar .lead { font-size:12px; color:var(--muted); margin-bottom:7px; }
  #tagbar .quo { font:11.5px/1.45 ui-monospace,Menlo,Consolas,monospace; background:var(--sel);
                 padding:5px 7px; border-radius:4px; margin-bottom:8px;
                 max-height:52px; overflow:auto; }
  #tagbar .btns { display:flex; gap:6px; flex-wrap:wrap; }
  #tagbar button { border:1px solid #c3cad4; background:#fff; border-radius:5px;
                   padding:6px 10px; font-size:12px; cursor:pointer; }
  #tagbar button:hover:not(:disabled) { border-color:var(--accent); background:#f2f7fc; }
  #tagbar button:disabled { opacity:.4; cursor:not-allowed; }
  #tagbar button.added { background:var(--okbg); border-color:var(--okline); color:var(--ok); }

  .gate { background:var(--warnbg); border:1px solid #e8d9a8; border-radius:8px;
          padding:16px 18px; margin-bottom:18px; }
  .gate h2 { margin:0 0 10px; font-size:14px; color:var(--warn);
             text-transform:uppercase; letter-spacing:.06em; }
  .gate ol { margin:0; padding-left:20px; }
  .gate li { margin-bottom:7px; }

  .dimhead { display:flex; justify-content:space-between; align-items:baseline; gap:12px; flex-wrap:wrap; }
  .dimhead h3 { margin:0; font-size:17px; }
  .poles { color:var(--muted); font-size:12.5px; }
  .prose { font-size:13px; margin:8px 0; }
  .prose b { color:var(--accent); }

  details.dim > summary { list-style:none; cursor:pointer; padding:12px 15px;
                          display:flex; justify-content:space-between; align-items:center;
                          gap:10px; border-radius:8px; }
  details.dim > summary::-webkit-details-marker { display:none; }
  details.dim > summary:hover { background:#fafbfc; }
  details.dim { border:1px solid var(--line); border-radius:8px; background:#fff; margin-bottom:11px; }
  details.dim[open] > summary { border-bottom:1px solid var(--line); }
  details.dim.done { border-color:var(--okline); background:var(--okbg); }
  details.dim.done > summary { background:transparent; }
  .sname { font-weight:600; font-size:15px; }
  .sstat { font-size:12px; color:var(--muted); }
  .sstat.ok { color:var(--ok); font-weight:600; }
  .dimbody { padding:0 15px 15px; }

  .bands { display:flex; flex-direction:column; gap:6px; margin:12px 0; }
  .band { display:flex; gap:10px; align-items:flex-start; padding:9px 11px;
          border:1px solid var(--line); border-radius:6px; cursor:pointer; background:#fff; }
  .band:hover { border-color:#b9c2cf; background:#fafbfc; }
  .band input { margin-top:3px; flex:none; }
  .band .lbl { font-weight:600; display:block; margin-bottom:2px; font-size:13px; }
  .band .txt { color:#3d434d; font-size:12.5px; }
  .band.chosen { border-color:var(--accent); background:#f2f7fc; box-shadow:inset 3px 0 0 var(--accent); }
  .band.insuff { border-style:dashed; margin-top:6px; }
  .noconf { color:var(--muted); font-size:12.5px; font-style:italic; margin:6px 0 4px; }
  .storagewarn { margin:0; padding:14px 18px; background:#fdecea; border-bottom:3px solid #b3261e;
                 color:#5f1512; font-size:15px; line-height:1.5; }
  .selnote { padding:0 15px 8px; color:#b3261e; font-size:13px; min-height:0; }
  #tagbar .prov { font-size:12px; color:var(--muted); margin:2px 0 8px; }
  .ex:hover { background:#fbfcfd; }
  .val { color:var(--muted); font-weight:400; font-size:11.5px; }

  .cite { border:1px dashed #c3cad4; border-radius:6px; padding:10px 12px; margin:11px 0;
          background:#fcfcfd; min-height:56px; }
  .cite .hint { color:var(--muted); font-size:12.5px; font-style:italic; }
  .q { background:var(--sel); padding:6px 8px; border-radius:4px; margin-bottom:6px;
       font:11.5px/1.5 ui-monospace,Menlo,Consolas,monospace; position:relative; padding-right:26px; }
  .q button { position:absolute; right:4px; top:4px; border:none; background:transparent;
              cursor:pointer; color:#a33; font-size:14px; line-height:1; padding:2px 4px; }

  .conf { display:flex; gap:6px; flex-wrap:wrap; margin:8px 0 4px; }
  .conf label { flex:1; min-width:108px; border:1px solid var(--line); border-radius:6px;
                padding:7px 9px; cursor:pointer; font-size:12px; background:#fff; }
  .conf label:hover { border-color:#b9c2cf; }
  .conf label.chosen { border-color:var(--accent); background:#f2f7fc; }
  .conf .cl { font-weight:600; display:block; }
  .conf .ct { color:var(--muted); font-size:11px; }

  textarea { width:100%; border:1px solid var(--line); border-radius:6px; padding:9px;
             font:inherit; font-size:13px; resize:vertical; }
  button.act { background:var(--accent); color:#fff; border:none; border-radius:6px;
               padding:9px 18px; font-size:13.5px; font-weight:600; cursor:pointer; }
  button.act:disabled { background:#c2c8d0; cursor:not-allowed; }
  button.ghost { background:#fff; color:var(--ink); border:1px solid var(--line);
                 border-radius:6px; padding:9px 16px; cursor:pointer; font-size:13px; }

  .summary { font-size:13px; }
  .summary .row { display:flex; gap:10px; padding:4px 0; border-bottom:1px solid #eef0f3; }
  .summary .row:last-child { border-bottom:none; }
  .summary .k { color:var(--muted); min-width:76px; }
  .err { color:#a33; font-size:12.5px; margin-top:7px; min-height:17px; }
  .fine { color:var(--muted); font-size:12px; }
  fieldset { border:1px solid var(--line); border-radius:6px; padding:12px 14px; margin:0 0 14px; }
  legend { font-size:12px; text-transform:uppercase; letter-spacing:.06em;
           color:var(--muted); padding:0 6px; }
  .radiorow { display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  .locked { background:var(--okbg); border:1px solid var(--okline); border-radius:6px;
            padding:11px 13px; margin-bottom:11px; font-size:13px; }
  .locked b { color:var(--ok); }
  .hidden { display:none !important; }
  .counter { font-size:12.5px; color:var(--muted); margin-bottom:11px; }
  .counter b { color:var(--ink); }
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>Solverah &mdash; company culture scoring</h1>
  <div class="meta">
    Packet <b>__PACKET_ID__</b> &nbsp;·&nbsp; Rater <b>__RATER__</b> &nbsp;·&nbsp;
    Rubric <b>__RUBRIC_VERSION__</b> &nbsp;·&nbsp;
    <span id="clock">session not started</span>
  </div>
</header>

<div id="storageWarn" class="storagewarn hidden"></div>

<div id="gatePanel" class="gate">
  <h2>Read before you start &mdash; every session</h2>
  <ol id="gateList"></ol>
  <p class="fine" style="margin:12px 0 0">
    <b>Finish this company before you open the next one</b>, and take a proper break between
    packets &mdash; the reading is dense and the last packet of a long day is not the same
    instrument as the first. All six dimensions are open at once so you only read the packet
    once &mdash; score them in whatever order the evidence supports. But <b>committing a
    dimension is final</b>, and once you submit, the packet cannot be reopened. That is
    deliberate: a company you read later must not be able to change a company you read first.
  </p>
  <p style="margin:14px 0 0"><button class="act" id="startBtn">I have read these &mdash; start the session</button></p>
</div>

<div id="main" class="hidden">
<div class="cols">

  <section class="panel" id="packet">
    <h2>Evidence packet &mdash; highlight text to cite it</h2>
    <div id="packetText">__PACKET_TEXT__</div>
    <div id="selNote" class="selnote"></div>
    <div id="tagbar" class="off">
      <div class="lead">File this quote under &mdash; pick as many dimensions as it supports:</div>
      <div class="quo" id="tagQuote"></div>
      <div class="prov" id="tagProv"></div>
      <div class="btns" id="tagBtns"></div>
    </div>
  </section>

  <section id="right">
    <div class="counter" id="counter"></div>
    <div id="dims"></div>

    <div class="panel hidden" id="finalPanel">
      <h2>Close out the sitting</h2>
      <div class="body">
        <fieldset>
          <legend>Recognition</legend>
          <p class="fine" style="margin-top:0">
            Recognising the company is <b>expected and is not a failure</b>. It is recorded as a
            variable, not held against you. Answer honestly &mdash; a hidden yes damages the data
            far more than an admitted one.
          </p>
          <div class="radiorow">
            <label><input type="radio" name="recog" value="yes"> I recognised the company</label>
            <label><input type="radio" name="recog" value="suspect"> A suspicion, not a firm identification</label>
            <label><input type="radio" name="recog" value="no"> No idea who this is</label>
          </div>
          <div id="recogDetailWrap" class="hidden" style="margin-top:11px">
            <label class="fine" for="recogDetail">What gave it away, and at roughly what point?</label>
            <textarea id="recogDetail" rows="2" placeholder="e.g. the values wording in Section A, second excerpt"></textarea>
          </div>
        </fieldset>

        <fieldset>
          <legend>Protocol check</legend>
          <div class="radiorow">
            <label><input type="radio" name="searched" value="no"> I did not search for anything in this packet</label>
            <label><input type="radio" name="searched" value="yes"> I searched (say what, below)</label>
          </div>
          <div id="searchDetailWrap" class="hidden" style="margin-top:11px">
            <textarea id="searchDetail" rows="2" placeholder="What did you look up?"></textarea>
          </div>
        </fieldset>

        <fieldset>
          <legend>Anything the rubric could not capture</legend>
          <textarea id="freeNote" rows="3" placeholder="Anchors that did not fit, evidence you wanted and did not have, dimensions the packet could not support. This is how the rubric gets fixed — be blunt."></textarea>
        </fieldset>

        <div class="err" id="finalErr"></div>
        <button class="act" id="submitBtn">Submit and lock this packet</button>
      </div>
    </div>

    <div class="panel hidden" id="donePanel">
      <h2>Submitted</h2>
      <div class="body">
        <div class="locked"><b>This packet is locked.</b> Download the result file and send it to
          Sebastian. Do not open another packet today.</div>
        <button class="act" id="dlBtn">Download result file</button>
        <button class="ghost" id="copyBtn">Copy to clipboard</button>
        <p class="fine" id="dlNote" style="margin-bottom:0"></p>
      </div>
    </div>
  </section>

</div>
</div>
</div>

<script>
const CFG = __CONFIG_JSON__;
const DIMS = CFG.dimensions, CONF = CFG.confidence_bands;
/* Julie's ruling 4 (anchors v3.1+): a rater may record "insufficient evidence" instead of a
   score. Offered ONLY when the anchors file defines it -- a page built from the frozen v1
   anchors behaves exactly as round 1's did. In a draft the choice is the string INSUFF_V,
   because null already means "no band picked yet"; committed, it is score:null,
   confidence:null, insufficient_evidence:true. */
const INSUFF = CFG.insufficient_evidence || null, INSUFF_V = "insufficient";
const isInsuff = v => v === INSUFF_V;
const PACKET_ID = "__PACKET_ID__", RATER = "__RATER__";
const STORE_KEY = "solverah_" + PACKET_ID + "_" + RATER;

let state = {
  packet_id: PACKET_ID, rater: RATER, rubric_version: CFG.rubric_version,
  session_start: null, submitted_at: null, duration_seconds: null,
  scores: {}, drafts: {}, commit_order: [],
  recognition: null, recognition_detail: "", searched: null, search_detail: "", free_note: ""
};

/* ---------- storage availability ----------
   Both the resume-after-crash behaviour AND the submit lock ride on localStorage. On a
   file:// page it is the flakiest thing in the browser: some configurations refuse it
   outright. The old code swallowed that failure silently, so a rater could score for forty
   minutes into memory that vanishes on refresh, and the "already submitted" lock would not
   persist either. Probe once, up front, and say so loudly if it is not there. */
let STORAGE_OK = (function(){
  try { const k = "__probe__" + Math.random();
        localStorage.setItem(k, "1"); const v = localStorage.getItem(k);
        localStorage.removeItem(k); return v === "1"; }
  catch(e){ return false; }
})();
let SAVE_FAILED = false;

function showStorageWarning(msg){
  const el = document.getElementById("storageWarn");
  if(!el) return;
  el.innerHTML = msg;
  el.classList.remove("hidden");
}

function save(){
  if(!STORAGE_OK) return;
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); }
  catch(e){
    /* Quota, private mode, or permission revoked mid-session. Fail loudly, once. */
    if(!SAVE_FAILED){
      SAVE_FAILED = true; STORAGE_OK = false;
      showStorageWarning("<b>Your progress has stopped saving.</b> The browser refused to store " +
        "it mid-session. Your answers are still on screen and will still download correctly — " +
        "but <b>do not refresh or close this tab</b> before you submit and download the result " +
        "file, or the work is lost.");
    }
  }
}
function load(){
  if(!STORAGE_OK) return null;
  try { const r = localStorage.getItem(STORE_KEY);
        if(r){ const p = JSON.parse(r); if(p && p.packet_id === PACKET_ID) return p; } } catch(e){}
  return null;
}
function draft(k){ if(!state.drafts[k]) state.drafts[k] = {quotes:[], band:null, conf:null, note:""}; return state.drafts[k]; }
function committedCount(){ return Object.keys(state.scores).length; }

function fmtDur(ms){ const s = Math.round(ms/1000);
  return Math.floor(s/60) + "m " + String(s%60).padStart(2,"0") + "s"; }
function tick(){
  if(!state.session_start || state.submitted_at) return;
  document.getElementById("clock").textContent =
    "session running · " + fmtDur(Date.now() - new Date(state.session_start).getTime());
}
setInterval(tick, 1000);

/* ---------- gates ---------- */
const gl = document.getElementById("gateList");
CFG.gates.forEach(g => { const li = document.createElement("li"); li.textContent = g; gl.appendChild(li); });

document.getElementById("startBtn").onclick = () => {
  if(!state.session_start) state.session_start = new Date().toISOString();
  document.getElementById("gatePanel").classList.add("hidden");
  document.getElementById("main").classList.remove("hidden");
  save(); renderAll(); tick();
};

/* ---------- selection -> tag bar ---------- */
let selText = null;
const tagbar = document.getElementById("tagbar");

const MIN_CITE = 25;
const SRC_LABEL = s => ({company:"company-authored", noncompany:"not company-authored",
  disputed:"employee byline, company-run outlet", researcher:"researcher observation"}[s] || s);

/* Grow a selection out to whole words. A raw drag ends wherever the mouse stopped, which
   produced citations like "e and ask for direct feedback. Be grateful for and" — a real
   result from the first smoke test. Verification still passed, because matching is
   substring-based; it was simply unreadable as evidence. */
function snapToWords(container, raw){
  const full = container.textContent;
  let i = full.indexOf(raw);
  if(i === -1) return raw.trim();
  let j = i + raw.length;
  const word = c => /[A-Za-z0-9'’-]/.test(c);
  while(i > 0 && word(full[i-1]) && word(full[i])) i--;
  while(j < full.length && word(full[j]) && word(full[j-1])) j++;
  return full.slice(i, j).replace(/^[\s—–.,;:]+|[\s—–,;:]+$/g, "");
}

document.getElementById("packetText").addEventListener("mouseup", () => {
  const sel = window.getSelection();
  const raw = sel ? sel.toString() : "";
  if(!raw.trim()){ return; }

  /* Provenance. The excerpt a citation came from carries its source class, and the <=0.7
     measurement turns on whether NON-COMPANY-AUTHORED evidence supports a score. Reading
     that off the tail of the quote string only works when the rater happened to drag far
     enough to include the attribution — five times out of six in the smoke test. Record it
     instead of inferring it. */
  let node = sel.anchorNode;
  if(node && node.nodeType === 3) node = node.parentNode;
  const ex = node && node.closest ? node.closest(".ex") : null;

  const note = document.getElementById("selNote");
  if(!ex){
    note.textContent = "That selection is outside the evidence excerpts — cite a bulleted excerpt.";
    tagbar.classList.add("off"); selText = null; return;
  }
  const text = snapToWords(ex, raw).replace(/\s+/g," ").trim();
  if(text.length < MIN_CITE){
    note.textContent = "Too short to be evidence — select at least a phrase (" +
                       MIN_CITE + " characters).";
    tagbar.classList.add("off"); selText = null; return;
  }
  note.textContent = "";
  selText = { text: text, eid: ex.dataset.eid, sec: ex.dataset.sec, src: ex.dataset.src };
  document.getElementById("tagQuote").textContent = '"' + text + '"';
  document.getElementById("tagProv").textContent =
    "section " + ex.dataset.sec + " · excerpt " + ex.dataset.eid + " · " +
    ({company:"company-authored", noncompany:"not company-authored",
      disputed:"employee byline on a company-run outlet",
      researcher:"researcher observation"}[ex.dataset.src] || ex.dataset.src);
  renderTagBtns();
  tagbar.classList.remove("off");
});

function renderTagBtns(){
  const box = document.getElementById("tagBtns"); box.innerHTML = "";
  DIMS.forEach(d => {
    const b = document.createElement("button");
    const done = !!state.scores[d.key];
    const already = !done && selText &&
      draft(d.key).quotes.some(q => q.text === selText.text && q.eid === selText.eid);
    b.textContent = d.name + (done ? " (locked)" : (already ? " ✓" : ""));
    b.disabled = done || already;
    if(already) b.className = "added";
    b.onclick = () => {
      draft(d.key).quotes.push(Object.assign({}, selText));
      save(); renderTagBtns(); renderDim(d.key); renderCounter();
    };
    box.appendChild(b);
  });
  const close = document.createElement("button");
  close.textContent = "done"; close.style.marginLeft = "auto";
  close.onclick = () => { tagbar.classList.add("off"); selText = null; };
  box.appendChild(close);
}

/* ---------- render ---------- */
function renderCounter(){
  const n = committedCount(), tot = DIMS.length;
  const tagged = DIMS.filter(d => !state.scores[d.key] && draft(d.key).quotes.length).length;
  document.getElementById("counter").innerHTML =
    "<b>" + n + " of " + tot + "</b> dimensions committed" +
    (tagged ? " · " + tagged + " more have evidence tagged and are ready to score" : "") +
    " · score them in any order.";
}

function renderAll(){
  const host = document.getElementById("dims"); host.innerHTML = "";
  DIMS.forEach(d => {
    const el = document.createElement("details");
    el.className = "dim"; el.id = "dim_" + d.key;
    host.appendChild(el);
    renderDim(d.key);
  });
  renderCounter(); checkComplete();
}

function renderDim(key){
  const d = DIMS.find(x => x.key === key);
  const el = document.getElementById("dim_" + key);
  if(!el) return;
  const wasOpen = el.open;
  const sc = state.scores[key];

  if(sc){
    const skipped = sc.insufficient_evidence === true;
    el.className = "dim done"; el.open = false;
    el.innerHTML =
      '<summary><span class="sname">' + d.name + '</span>' +
      '<span class="sstat ok">committed &nbsp;·&nbsp; ' +
      (skipped ? esc(INSUFF ? INSUFF.label : "insufficient evidence").toLowerCase()
               : 'score ' + sc.score.toFixed(1) + ' &nbsp;·&nbsp; confidence ' + sc.confidence.toFixed(1)) +
      ' &nbsp;·&nbsp; ' + sc.quotes.length + ' quote' + (sc.quotes.length===1?'':'s') + '</span></summary>' +
      '<div class="dimbody"><div class="summary">' +
        '<div class="row"><span class="k">Band</span><span>' +
          (skipped ? esc(INSUFF ? INSUFF.label : "Insufficient evidence") + ' &mdash; no score'
                   : d.bands.find(b => b.value === sc.score).reads_as) + '</span></div>' +
        '<div class="row"><span class="k">Evidence</span><span>' +
          (sc.quotes.length ? sc.quotes.map(q => '&ldquo;' + esc(q.text) + '&rdquo;<br><span class="fine">' + q.eid + ' &middot; ' + SRC_LABEL(q.src) + '</span>').join('<br><br>')
                            : '<span class="fine">none filed</span>') + '</span></div>' +
        (sc.note ? '<div class="row"><span class="k">Note</span><span>' + esc(sc.note) + '</span></div>' : '') +
        '<div class="row"><span class="k">Locked</span><span class="fine">' +
          new Date(sc.committed_at).toLocaleTimeString() + ' &mdash; cannot be changed</span></div>' +
      '</div></div>';
    return;
  }

  const dr = draft(key);
  el.className = "dim"; el.open = wasOpen;
  let h = '<summary><span class="sname">' + d.name + '</span><span class="sstat">' +
          d.low_pole + ' &rarr; ' + d.high_pole +
          (dr.quotes.length ? ' &nbsp;·&nbsp; ' + dr.quotes.length + ' quote' + (dr.quotes.length===1?'':'s') + ' tagged' : '') +
          '</span></summary><div class="dimbody">';

  h += '<p class="prose"><b>Measures.</b> ' + d.measures + '</p>';
  h += '<p class="prose"><b>Where to look.</b> ' + d.where_to_look + '</p>';
  h += '<p class="prose"><b>Keep distinct.</b> ' + d.keep_distinct + '</p>';

  h += '<div class="bands">';
  d.bands.forEach(b => {
    h += '<label class="band' + (dr.band === b.value ? ' chosen' : '') + '" data-v="' + b.value + '">' +
         '<input type="radio" name="band_' + key + '" value="' + b.value + '"' +
         (dr.band === b.value ? ' checked' : '') + '>' +
         '<span><span class="lbl">' + b.reads_as + ' <span class="val">' + b.value.toFixed(1) + '</span></span>' +
         '<span class="txt">' + b.text + '</span></span></label>';
  });
  if(INSUFF){
    const on = isInsuff(dr.band);
    h += '<label class="band insuff' + (on ? ' chosen' : '') + '" data-v="' + INSUFF_V + '">' +
         '<input type="radio" name="band_' + key + '" value="' + INSUFF_V + '"' + (on ? ' checked' : '') + '>' +
         '<span><span class="lbl">' + esc(INSUFF.label) + ' <span class="val">no score</span></span>' +
         '<span class="txt">' + esc(INSUFF.text) + '</span></span></label>';
  }
  h += '</div>';

  h += '<div><b style="font-size:13px">Evidence for this score</b><div class="cite" id="cite_' + key + '"></div></div>';

  if(isInsuff(dr.band)){
    h += '<div class="noconf">No confidence rating: you are recording that the packet cannot ' +
         'support a score on this dimension.</div>';
  } else {
    h += '<div><b style="font-size:13px">How confident are you in this score?</b><div class="conf">';
    CONF.forEach(c => {
      h += '<label' + (dr.conf === c.value ? ' class="chosen"' : '') + ' data-v="' + c.value + '">' +
           '<input type="radio" name="conf_' + key + '" value="' + c.value + '"' +
           (dr.conf === c.value ? ' checked' : '') + '>' +
           '<span class="cl">' + c.label + ' <span class="val">' + c.value.toFixed(1) + '</span></span>' +
           '<span class="ct">' + c.text + '</span></label>';
    });
    h += '</div></div>';
  }

  h += '<div style="margin-top:11px"><label class="fine" for="note_' + key + '">One line on your reasoning (optional)</label>' +
       '<textarea id="note_' + key + '" rows="2">' + esc(dr.note) + '</textarea></div>';
  h += '<div class="err" id="err_' + key + '"></div>';
  h += '<div style="margin-top:10px"><button class="act" id="commit_' + key + '">Commit ' +
       d.name + ' &mdash; final</button></div></div>';

  el.innerHTML = h;

  el.querySelectorAll(".band").forEach(b => {
    b.onclick = ev => { ev.preventDefault();
      const was = dr.band;
      dr.band = isInsuff(b.dataset.v) ? INSUFF_V : parseFloat(b.dataset.v);
      if(isInsuff(dr.band)) dr.conf = null;   /* a skip carries no confidence */
      if(isInsuff(was) !== isInsuff(dr.band)){ save(); renderDim(key); return; }
      el.querySelectorAll(".band").forEach(x => x.classList.remove("chosen"));
      b.classList.add("chosen"); b.querySelector("input").checked = true;
      save(); validate(key); };
  });
  el.querySelectorAll(".conf label").forEach(b => {
    b.onclick = ev => { ev.preventDefault();
      dr.conf = parseFloat(b.dataset.v);
      el.querySelectorAll(".conf label").forEach(x => x.classList.remove("chosen"));
      b.classList.add("chosen"); b.querySelector("input").checked = true;
      save(); validate(key); };
  });
  el.querySelector("#note_" + key).oninput = e => { dr.note = e.target.value; save(); };
  el.querySelector("#commit_" + key).onclick = () => commit(key);

  renderCites(key); validate(key);
}

function esc(s){ return (s||"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

function renderCites(key){
  const box = document.getElementById("cite_" + key); if(!box) return;
  const dr = draft(key);
  if(!dr.quotes.length){
    box.innerHTML = '<div class="hint">Highlight a line in the packet on the left, then file it ' +
                    'under this dimension. ' +
                    (isInsuff(dr.band) ? 'Optional when recording insufficient evidence.'
                                       : 'At least one quote is required.') + '</div>';
    return;
  }
  box.innerHTML = "";
  dr.quotes.forEach((q, i) => {
    const div = document.createElement("div");
    div.className = "q"; div.textContent = '"' + q.text + '" (' + q.eid + ')';
    const b = document.createElement("button");
    b.textContent = "×"; b.title = "remove";
    b.onclick = () => { dr.quotes.splice(i,1); save(); renderCites(key); validate(key);
                        renderCounter(); if(selText) renderTagBtns(); };
    div.appendChild(b); box.appendChild(div);
  });
}

function validate(key){
  const dr = draft(key);
  const btn = document.getElementById("commit_" + key), err = document.getElementById("err_" + key);
  if(!btn) return;
  let msg = "";
  if(dr.band === null) msg = INSUFF ? "Pick a band, or record insufficient evidence." : "Pick a band.";
  else if(isInsuff(dr.band)) msg = "";   /* quotes optional, no confidence */
  else if(!dr.quotes.length) msg = "File at least one quote from the packet under this dimension.";
  else if(dr.conf === null) msg = "Record your confidence.";
  err.textContent = msg; btn.disabled = msg !== "";
}

function commit(key){
  const dr = draft(key);
  const skip = isInsuff(dr.band);
  state.scores[key] = {
    dimension: key, score: skip ? null : dr.band, confidence: skip ? null : dr.conf,
    quotes: dr.quotes.slice(), note: (dr.note || "").trim(),
    committed_at: new Date().toISOString(),
    commit_position: state.commit_order.length + 1
  };
  /* The key exists only on a skip, so a scored row is shaped exactly as in round 1. */
  if(skip) state.scores[key].insufficient_evidence = true;
  state.commit_order.push(key);
  delete state.drafts[key];
  save(); renderDim(key); renderCounter(); checkComplete();
  if(selText) renderTagBtns();
}

function checkComplete(){
  const done = committedCount() === DIMS.length;
  document.getElementById("finalPanel").classList.toggle("hidden", !done || !!state.submitted_at);
}

/* ---------- close out ---------- */
document.querySelectorAll('input[name="recog"]').forEach(r => r.onchange = () => {
  state.recognition = r.value;
  document.getElementById("recogDetailWrap").classList.toggle("hidden", r.value === "no"); save(); });
document.querySelectorAll('input[name="searched"]').forEach(r => r.onchange = () => {
  state.searched = r.value;
  document.getElementById("searchDetailWrap").classList.toggle("hidden", r.value === "no"); save(); });

document.getElementById("submitBtn").onclick = () => {
  state.recognition_detail = (document.getElementById("recogDetail").value || "").trim();
  state.search_detail = (document.getElementById("searchDetail").value || "").trim();
  state.free_note = (document.getElementById("freeNote").value || "").trim();
  const err = document.getElementById("finalErr");
  if(!state.recognition){ err.textContent = "Answer the recognition question."; return; }
  if(!state.searched){ err.textContent = "Answer the protocol question."; return; }
  err.textContent = "";
  state.submitted_at = new Date().toISOString();
  state.duration_seconds = Math.round(
    (new Date(state.submitted_at) - new Date(state.session_start)) / 1000);
  save(); lockDown();
  /* Fire the download automatically. The button stays as a fallback for browsers that
     block programmatic downloads, and dlNote reports which of the two happened. */
  const auto = downloadResult();
  document.getElementById("dlNote").textContent = auto
    ? "Saved automatically to your Downloads folder as solverah_" + PACKET_ID + "_rater" +
      RATER + ".json — please send Sebastian that file."
    : "Automatic save did not run in this browser. Press “Download result file” below now.";
};

function lockDown(){
  document.getElementById("finalPanel").classList.add("hidden");
  document.getElementById("dims").classList.add("hidden");
  document.getElementById("counter").classList.add("hidden");
  document.getElementById("packet").classList.add("hidden");
  document.getElementById("donePanel").classList.remove("hidden");
  document.getElementById("clock").textContent = state.duration_seconds
    ? "submitted · sitting lasted " + fmtDur(state.duration_seconds * 1000)
    : "submitted and locked";
  document.getElementById("dlNote").textContent =
    "File name: solverah_" + PACKET_ID + "_rater" + RATER + ".json";
}

function payload(){
  const rows = DIMS.map(d => state.scores[d.key]).filter(Boolean);
  return JSON.stringify({
    packet_id: state.packet_id, rater: state.rater,
    rubric_version: state.rubric_version, anchors_hash: CFG._anchors_hash || null,
    session_start: state.session_start, submitted_at: state.submitted_at,
    duration_seconds: state.duration_seconds, commit_order: state.commit_order,
    recognition: state.recognition, recognition_detail: state.recognition_detail,
    searched: state.searched, search_detail: state.search_detail,
    free_note: state.free_note,
    scores: rows.map(r => {
      /* Source mix is derived here rather than left to whoever reads the file, so the
         <=0.7 MEASUREMENT (08-10 decision 3: record whether non-company-authored evidence
         supports the score; do NOT enforce it as a ceiling) is a recorded field.
         'disputed' is reported separately and deliberately not folded into either side —
         open question 5 decides which way it goes, and that answer can then be applied to
         these files without re-rating anyone. */
      const mix = {company:0, noncompany:0, disputed:0, researcher:0};
      r.quotes.forEach(q => { if(q.src in mix) mix[q.src]++; });
      return Object.assign({}, r, {
        source_mix: mix,
        noncompany_support: mix.noncompany > 0,
        excerpts_cited: r.quotes.map(q => q.eid)
      });
    })
  }, null, 2);
}

/* The result file is the ONLY artifact that leaves this machine. Everything else lives in
   browser storage that the rater may clear, and on file:// pages may never have worked.
   Do not make the handover depend on remembering to press a button. */
let DOWNLOADED = false;

function downloadResult(){
  try {
    const blob = new Blob([payload()], {type:"application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "solverah_" + PACKET_ID + "_rater" + RATER + ".json";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    DOWNLOADED = true;
    return true;
  } catch(e){ return false; }
}

document.getElementById("dlBtn").onclick = () => {
  const ok = downloadResult();
  document.getElementById("dlNote").textContent = ok
    ? "Downloaded. Check your Downloads folder for solverah_" + PACKET_ID + "_rater" + RATER + ".json"
    : "Download failed — use Copy to clipboard and paste the text into an email.";
};
document.getElementById("copyBtn").onclick = () => {
  navigator.clipboard.writeText(payload()).then(
    () => { document.getElementById("dlNote").textContent = "Copied to clipboard."; },
    () => { document.getElementById("dlNote").textContent = "Copy failed — use the download button."; });
};

window.addEventListener("beforeunload", e => {
  /* Two distinct losses to guard: an unfinished sitting, and — the one the old code missed —
     a finished sitting whose result file was never actually saved anywhere. */
  const unfinished = state.session_start && !state.submitted_at;
  const unsaved    = state.submitted_at && !DOWNLOADED;
  if(unfinished || unsaved){ e.preventDefault(); e.returnValue = ""; }
});

/* ---------- boot ---------- */
if(!STORAGE_OK){
  showStorageWarning(
    "<b>This browser will not save your progress.</b> Your answers are kept on screen only, so " +
    "<b>refreshing or closing this tab will lose everything</b>, and the packet will not stay " +
    "locked after you submit. You can still score normally and the result file will still " +
    "download correctly — but finish this packet in one sitting without reloading, and tell " +
    "Sebastian you saw this message.");
}

/* ---------- resume ---------- */
(function(){
  const prev = load();
  if(prev && prev.session_start){
    state = Object.assign(state, prev);
    if(!state.drafts) state.drafts = {};
    if(!state.commit_order) state.commit_order = [];
    if(state.submitted_at){
      /* Reopening a packet submitted in an earlier sitting. The download already happened
         then, so do not re-arm the unsaved-result guard — but leave the buttons live so a
         lost file can be re-downloaded. */
      DOWNLOADED = true;
      document.getElementById("gatePanel").classList.add("hidden");
      document.getElementById("main").classList.remove("hidden");
      renderAll(); lockDown();
      document.getElementById("clock").textContent = "already submitted and locked";
      document.getElementById("dlNote").textContent =
        "Already submitted. If you lost the result file, press “Download result file” again — " +
        "it will be identical.";
      return;
    }
    document.getElementById("startBtn").textContent =
      "Resume this sitting (" + committedCount() + " of " + DIMS.length + " committed)";
  }
})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", required=True, help="scrubbed packet .txt")
    ap.add_argument("--packet-id", required=True)
    ap.add_argument("--rater", required=True)
    ap.add_argument("--anchors", default=str(pathlib.Path(__file__).parent / "anchors.json"))
    ap.add_argument("--out", default=".")
    a = ap.parse_args()

    packet_raw = pathlib.Path(a.packet).read_text(encoding="utf-8")
    # (markup is built after the scrub-log cut, below)

    # The scrub log is operator material, not rater material -- cut everything from the
    # "END OF PACKET" marker onward. Fail the build rather than guess if the marker is
    # missing: a silent fallback to "ship the whole file" is how operator notes (which can
    # include a company name) reach a rater's page unreviewed.
    m = _END_OF_PACKET_RE.search(packet_raw)
    if not m:
        raise SystemExit(
            f"'END OF PACKET' marker not found in {a.packet!r} -- refusing to guess where "
            "rater-facing content ends. If the packet format changed, update "
            "_END_OF_PACKET_RE deliberately; do not silently ship unbounded content.")
    packet_raw = packet_raw[:m.end()].rstrip() + "\n"

    cfg = json.loads(pathlib.Path(a.anchors).read_text(encoding="utf-8"))
    # Hash EVERY rater-facing element, not just the dimension anchors. The confidence bands,
    # the bias gates, the band values and the agreement rule all shape the numbers a rater
    # produces, so a change to any of them means a different instrument. Hashing only
    # cfg["dimensions"] let the confidence-band wording change while the hash stayed
    # identical — a score row would then claim an instrument version it was not produced
    # under. Same reasoning as recording model_run on every LLM score.
    _hashable = {k: v for k, v in cfg.items() if not k.startswith("_")}
    cfg["_anchors_hash"] = hashlib.sha256(
        json.dumps(_hashable, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]

    packet_html, pstats = build_packet_markup(packet_raw)
    if pstats["unknown"]:
        # A citation whose source class is unknown cannot feed the <=0.7 measurement. Fail the
        # build rather than ship a page that silently produces unusable evidence.
        print(f"  !! {len(pstats['unknown'])} excerpt(s) could not be classified in {a.packet_id}:")
        for eid, snippet in pstats["unknown"]:
            print(f"       {eid}: {snippet}")
        raise SystemExit("unclassified excerpts — extend classify_source() before generating")

    out = (TEMPLATE
           .replace("__CONFIG_JSON__", json.dumps(cfg))
           .replace("__PACKET_TEXT__", packet_html)
           .replace("__PACKET_ID__", a.packet_id)
           .replace("__RATER__", a.rater)
           .replace("__RUBRIC_VERSION__", cfg.get("rubric_version", "?")))

    outdir = pathlib.Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    dest = outdir / f"{a.packet_id}_rater{a.rater}.html"
    dest.write_text(out, encoding="utf-8")
    print(f"wrote {dest}  ({len(out):,} bytes, anchors {cfg['_anchors_hash']}, "
          f"{pstats['excerpts']} excerpts: {pstats['company']} company / "
          f"{pstats[chr(39)+chr(39)] if False else pstats['noncompany']} non-company / {pstats['disputed']} disputed / {pstats['researcher']} researcher)")


if __name__ == "__main__":
    main()
