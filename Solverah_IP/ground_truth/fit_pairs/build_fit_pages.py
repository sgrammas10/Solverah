"""build_fit_pages.py -- one offline HTML page per fit-pairs rater.

The rater-app pattern (rater_app/build_rater_page.py, priors_elicitation.html): a single
self-contained file, no network, autosave to localStorage as they go, resumable, valid
half-finished, a download button that works at any point, and a loud banner when the
browser blocks saving.

    python build_fit_pages.py --rater E            # out/fit_pairs_raterE.html
    python build_fit_pages.py --preview            # out/fit_pairs_PREVIEW.html (analysis refuses it)

Refuses any rater who is not in roster.json, is not eligible, or set the weights. Also
(re)writes pair_specs.json, the hook matching-model scores, so the page and the hook can
never come from different designs: the page carries the spec's sha256 and the analysis
refuses a return whose sha does not match.

Each card is rendered HERE, in Python, from the person and company objects. A repeat item
carries the very string its original carries (same function, same inputs), so "the repeat
is the same question" is a byte comparison, tested in test_fit_pairs.py and in the jsdom
test.
"""

from __future__ import annotations

import argparse
import html
import json
import random
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import design  # noqa: E402

PREVIEW_ID = "PREVIEW"


class RosterError(Exception):
    pass


def check_rater(rater: str, roster_path: Path) -> None:
    doc = json.loads(roster_path.read_text(encoding="utf-8"))
    entry = {r["rater_id"]: r for r in doc["raters"]}.get(rater)
    if entry is None:
        raise RosterError("rater %r is not in %s. Add them to the roster first." % (rater, roster_path.name))
    if entry.get("sets_weights"):
        raise RosterError("rater %r (%s) helps set the weights and must not rate the fit pairs: %s"
                          % (rater, entry.get("name"), entry.get("why_excluded")))
    if not entry.get("eligible"):
        raise RosterError("rater %r (%s) is not eligible: %s"
                          % (rater, entry.get("name"), entry.get("why_excluded")))


# ---------------------------------------------------------------------------
# Card rendering (pure; the same inputs always give the same string)
# ---------------------------------------------------------------------------

def _e(s: str) -> str:
    return html.escape(s, quote=True)


def _tolerance_cell(person: dict[str, Any], trait: str) -> str:
    score = person["scores"][trait]
    tol = person["tolerance"][trait]
    less, more = design.DIRECTION_WORDS[trait]
    lines = []
    if score > 0.0:      # at the low pole a job cannot be "less" than wanted
        lines.append("%s: %s" % (less, design.TOLERANCE_WORDS[tol["under_steps"]]))
    if score < 1.0:
        lines.append("%s: %s" % (more, design.TOLERANCE_WORDS[tol["over_steps"]]))
    return "<br>".join(_e(x) for x in lines)


def _company_cell(trait: str, rec: dict[str, Any]) -> str:
    if rec["status"] == "unknown":
        return '<span class="read unknown">Not enough evidence found</span>'
    ev = "".join('<li><span class="src">%s:</span> %s</li>' % (_e(x["label"]), _e(x["text"]))
                 for x in rec["evidence"])
    if rec["status"] == "known":
        return '<span class="read">%s</span><ul class="ev">%s</ul>' % (
            _e(design.band_phrase(trait, rec["estimate"])), ev)
    return ('<span class="read mixed">Evidence disagrees: %s, or %s</span>'
            '<span class="why">%s</span><ul class="ev">%s</ul>') % (
        _e(design.band_phrase(trait, rec["low_end"])), _e(design.band_phrase(trait, rec["high_end"])),
        _e(design.SPLIT_WHY[rec["split_explained_by"]]), ev)


def render_card(person: dict[str, Any], company: dict[str, Any]) -> str:
    rows = []
    for k in design.TRAIT_KEYS:
        t = design.TRAITS[k]
        badge = ' <span class="must">must-have</span>' if k in person["must_haves"] else ""
        rows.append(
            '<tr><th scope="row"><span class="tl">%s</span>%s<span class="poles">%s / %s</span></th>'
            '<td data-h="What they want">%s</td><td data-h="How far the job can be from that">%s</td>'
            '<td data-h="What we found at the company">%s</td></tr>' % (
                _e(t["label"]), badge, _e(t["low"]), _e(t["high"]),
                _e(design.person_phrase(k, person["scores"][k])),
                _tolerance_cell(person, k), _company_cell(k, company["traits"][k])))
    statuses = [company["traits"][k]["status"] for k in design.TRAIT_KEYS]
    coverage = "We could read %d of the 6 traits clearly; %d had split evidence; %d had too little." % (
        statuses.count("known"), statuses.count("mixed"), statuses.count("unknown"))
    mh = person["must_haves"]
    mh_line = ("Must-haves (non-negotiable for them): %s." % ", ".join(design.TRAITS[k]["label"] for k in mh)
               if mh else "No must-haves: no single trait is non-negotiable for them.")
    return ('<div class="pair"><p class="who"><b>%s</b>. %s</p>'
            '<table class="traits"><thead><tr><th>Trait</th><th>What they want</th>'
            '<th>How far the job can be from that</th><th>What we found at the company</th></tr></thead>'
            '<tbody>%s</tbody></table><p class="coverage">%s</p></div>') % (
        _e(person["name"]), _e(mh_line), "".join(rows), _e(coverage))


# ---------------------------------------------------------------------------
# Presentation order: fixed block order for everyone (a stopped rater leaves a prefix);
# company order shuffled inside each block per rater (seeded, reproducible); each repeat
# appended after its block.
# ---------------------------------------------------------------------------

def presentation(spec: dict[str, Any], rater: str) -> list[dict[str, Any]]:
    persons = {p["person_id"]: p for p in spec["persons"]}
    companies = {c["company_id"]: c for c in spec["companies"]}
    pairs = {p["pair_id"]: p for p in spec["pairs"]}
    cards = {pid: render_card(persons[p["person_id"]], companies[p["company_id"]])
             for pid, p in pairs.items()}
    items = []
    for bi, block in enumerate(spec["blocks"], start=1):
        ids = list(block["pair_ids"])
        random.Random("%s|%s|%s" % (spec["design_version"], rater, block["block_id"])).shuffle(ids)
        for pid in ids:
            items.append({"item_id": pid, "pair_id": pid, "is_repeat": False, "part": bi,
                          "name": persons[pairs[pid]["person_id"]]["name"], "card": cards[pid]})
        for r in spec["repeats"]:
            if r["shown_after_block"] == block["block_id"]:
                pid = r["of_pair"]
                items.append({"item_id": r["repeat_id"], "pair_id": pid, "is_repeat": True, "part": bi,
                              "name": persons[pairs[pid]["person_id"]]["name"], "card": cards[pid]})
    return items


def build_page(spec: dict[str, Any], spec_sha: str, rater: str) -> str:
    data = {
        "instrument": "fit_pairs_v1",
        "design_version": spec["design_version"],
        "spec_sha256": spec_sha,
        "rater": rater,
        "parts": len(spec["blocks"]),
        "items": presentation(spec, rater),
    }
    blob = json.dumps(data, ensure_ascii=True).replace("</", "<\\/")
    return (TEMPLATE.replace("__DATA__", blob).replace("__RATER__", _e(rater))
            .replace("__PARTS__", str(len(spec["blocks"]))))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build fit-pairs rater pages.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--rater")
    g.add_argument("--preview", action="store_true")
    ap.add_argument("--roster", type=Path, default=HERE / "roster.json")
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--spec-out", type=Path, default=HERE / "pair_specs.json")
    a = ap.parse_args(argv)
    rater = PREVIEW_ID if a.preview else a.rater
    if not a.preview:
        check_rater(rater, a.roster)
    spec = design.build_spec()
    a.out.mkdir(parents=True, exist_ok=True)
    a.spec_out.parent.mkdir(parents=True, exist_ok=True)
    sha = design.write_spec(a.spec_out)
    path = a.out / ("fit_pairs_%s.html" % ("PREVIEW" if a.preview else "rater" + rater))
    path.write_text(build_page(spec, sha, rater), encoding="utf-8", newline="\n")
    print("wrote %s (%d items, spec %s)" % (path.name, len(presentation(spec, rater)), sha[:12]))
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solverah - Fit Judgements</title>
<style>
  :root{--ink:#1a1d21;--ink-soft:#5b6470;--line:#dde2e8;--line-soft:#eef1f5;--bg:#fbfcfd;--card:#fff;
        --accent:#2f5d8a;--accent-soft:#eaf1f8;--warn:#8a5a2f;--warn-bg:#fdf3e7;--ok:#2f7a52}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  .wrap{max-width:960px;margin:0 auto;padding:32px 16px 140px}
  h1{font-size:26px;line-height:1.25;margin:0 0 6px}
  .sub{color:var(--ink-soft);margin:0 0 22px}
  .panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px 22px;margin-bottom:18px}
  .panel p{margin:0 0 10px}.panel p:last-child{margin-bottom:0}
  .hidden{display:none!important}
  .banner{background:var(--warn-bg);border:1px solid var(--warn);color:var(--warn);border-radius:8px;padding:12px 16px;margin-bottom:16px;font-weight:600}
  .eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-soft);font-weight:600;margin-bottom:6px}
  .who{margin:0 0 12px}
  table.traits{width:100%;border-collapse:collapse;font-size:15px}
  table.traits th,table.traits td{border-top:1px solid var(--line);padding:9px 8px;text-align:left;vertical-align:top}
  table.traits thead th{font-size:13px;color:var(--ink-soft);font-weight:600;border-top:0}
  .tl{font-weight:600;display:block}.poles{display:block;font-size:12px;color:var(--ink-soft);font-weight:400}
  .must{display:inline-block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;background:var(--ink);color:#fff;border-radius:4px;padding:1px 6px;margin:2px 0}
  .read{font-weight:600;display:block}.read.unknown{color:var(--ink-soft);font-weight:500}.read.mixed{color:var(--warn)}
  .why{display:block;font-size:13px;color:var(--ink-soft)}
  ul.ev{margin:4px 0 0;padding-left:18px;font-size:13px;color:var(--ink-soft)}
  .src{font-weight:600}
  .coverage{font-size:14px;color:var(--ink-soft);margin:10px 0 0}
  .ask{font-weight:600;margin:18px 0 10px}
  .scale{display:flex;flex-wrap:wrap;gap:8px}
  .scale button{flex:1 1 150px;font:inherit;text-align:left;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);cursor:pointer}
  .scale button:hover{border-color:var(--accent);background:var(--accent-soft)}
  .scale button.on{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
  .scale button.abstain{flex-basis:100%}
  textarea{width:100%;font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:7px;min-height:52px;margin-top:10px}
  .nav{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
  button.btn{font:inherit;font-weight:600;padding:10px 18px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer}
  button.btn.ghost{background:#fff;color:var(--accent)}
  button.btn:disabled{opacity:.4;cursor:default}
  .status{position:fixed;left:0;right:0;bottom:0;background:rgba(255,255,255,.97);border-top:1px solid var(--line);padding:10px 16px}
  .status .inner{max-width:960px;margin:0 auto;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
  .bar{flex:1 1 160px;height:7px;background:var(--line-soft);border-radius:4px;overflow:hidden}
  .bar i{display:block;height:100%;width:0;background:var(--accent)}
  .saved{font-size:13px;color:var(--ok)}
  @media (max-width:700px){
    table.traits thead{display:none}
    table.traits tr{display:block;border-top:1px solid var(--line);padding:8px 0}
    table.traits th,table.traits td{display:block;border:0;padding:3px 0}
    table.traits td::before{content:attr(data-h);display:block;font-size:12px;color:var(--ink-soft)}
  }
</style>
</head>
<body>
<div class="wrap">
  <div id="storageWarn" class="banner hidden">Your browser is not letting this page save as you go. If you close or refresh it you will lose everything since your last download. Please use "Download my answers" before you close it.</div>
  <h1>How well would it work for them?</h1>
  <p class="sub">Fit judgements for Solverah. Rater __RATER__.</p>

  <div id="intro" class="panel">
    <p><b>Thank you for doing this.</b> It is unpaid, and it is the only way we have to check our model against people who had no hand in building it.</p>
    <p>Each screen shows one made-up person and one made-up company. On the left is what the person says they want from a job, on each of six traits, and how far a job can be from that before it bothers them. Up to two traits may be must-haves for them. On the right is what research found about the company on the same six traits, with a short paraphrase of the evidence. Sometimes the evidence disagrees, and sometimes there is too little to say.</p>
    <p>Your question each time: <b>if this person took a job at this company, how well do you think it would work for them?</b> Use your own judgement. There are no right answers, and we are not checking you against anything. "Can't say from what's here" is a real answer: use it whenever you mean it.</p>
    <p>Judge only from the page. Assume everything else (pay, manager, location, the work itself) is fine and the same at every company. Please don't look anything up, and don't compare notes with other raters until you have finished.</p>
    <p>There are __PARTS__ parts of 5 or 6 screens, about 6 to 8 minutes a part. <b>You can stop after any part</b>, or in the middle of one. Your answers save in this browser as you go, and whatever you have done is useful. When you are finished for now, press "Download my answers" and email us the file.</p>
    <div class="nav"><button id="startBtn" class="btn">Start</button></div>
  </div>

  <div id="itemPanel" class="panel hidden">
    <div class="eyebrow" id="where"></div>
    <div id="card"></div>
    <p class="ask" id="ask"></p>
    <div class="scale" id="scale"></div>
    <textarea id="note" placeholder="Optional: anything that drove your answer (one line is plenty)"></textarea>
    <div class="nav">
      <button id="backBtn" class="btn ghost">Back</button>
      <button id="nextBtn" class="btn">Next</button>
    </div>
  </div>

  <div id="partDone" class="panel hidden">
    <p id="partDoneText"></p>
    <p>Your answers are saved in this browser. If you are stopping here, press "Download my answers" below and email us the file. You can come back to this page later and carry on where you left off.</p>
    <div class="nav"><button id="continueBtn" class="btn">Carry on</button></div>
  </div>

  <div id="donePanel" class="panel hidden">
    <p><b>That's all of them. Thank you.</b></p>
    <p id="dlNote">Your answers file has been downloaded. Please email it to us. If nothing downloaded, press "Download my answers" below.</p>
  </div>
</div>

<div class="status"><div class="inner">
  <div class="bar"><i id="barFill"></i></div>
  <span id="progress"></span>
  <span class="saved" id="savedMsg"></span>
  <button id="dlBtn" class="btn ghost">Download my answers</button>
</div></div>

<script>
var DATA = __DATA__;
var OPTIONS = [
  {value:1, text:"It wouldn't work at all."},
  {value:2, text:"It wouldn't work well."},
  {value:3, text:"A mixed picture."},
  {value:4, text:"It would work well."},
  {value:5, text:"It would work very well."}
];
var KEY = "solverah_fitpairs_" + DATA.design_version + "_" + DATA.rater;
var STORAGE_OK = true;
var state = {ratings:{}, pos:0, started_at:null, finished_at:null};
var $ = function(id){ return document.getElementById(id); };

function probeStorage(){
  try { var t = "__probe__"; window.localStorage.setItem(t, "1"); window.localStorage.removeItem(t); return true; }
  catch(e){ return false; }
}
function load(){
  try { var raw = window.localStorage.getItem(KEY); if(raw){ var s = JSON.parse(raw); if(s && s.ratings){ state = s; } } }
  catch(e){}
}
function save(){
  try { window.localStorage.setItem(KEY, JSON.stringify(state)); $("savedMsg").textContent = "Saved"; }
  catch(e){
    STORAGE_OK = false;
    var w = $("storageWarn");
    w.textContent = "Saving just failed in this browser. Do not refresh or close this page: press \"Download my answers\" now so nothing is lost.";
    w.classList.remove("hidden");
  }
}
function answered(){ return Object.keys(state.ratings).length; }
function rec(item){ return state.ratings[item.item_id]; }

function setRating(value){
  var item = DATA.items[state.pos];
  var r = rec(item) || {note:""};
  if(value === null){ r.rating = null; r.abstain = true; } else { r.rating = value; r.abstain = false; }
  r.answered_at = new Date().toISOString();
  state.ratings[item.item_id] = r;
  save(); render();
}
function setNote(text){
  var item = DATA.items[state.pos];
  var r = rec(item);
  if(!r){ return; }             // a note alone is not an answer
  r.note = text; save();
}

function show(panel){
  ["intro","itemPanel","partDone","donePanel"].forEach(function(p){ $(p).classList.toggle("hidden", p !== panel); });
}
function render(){
  var n = DATA.items.length;
  $("barFill").style.width = Math.round(100*answered()/n) + "%";
  $("progress").textContent = answered() + " of " + n + " answered";
  if(state.pos >= n){ show("donePanel"); return; }
  var item = DATA.items[state.pos];
  var inPart = DATA.items.filter(function(x){ return x.part === item.part; });
  var k = inPart.indexOf(item) + 1;
  $("where").textContent = "Part " + item.part + " of " + DATA.parts + ", screen " + k + " of " + inPart.length;
  $("card").innerHTML = item.card;
  $("ask").textContent = "If " + item.name + " took a job at this company, how well do you think it would work for them?";
  var r = rec(item);
  var sc = $("scale"); sc.innerHTML = "";
  OPTIONS.concat([{value:null, text:"Can't say from what's here."}]).forEach(function(o){
    var b = document.createElement("button");
    b.type = "button"; b.textContent = o.text;
    b.setAttribute("data-value", o.value === null ? "abstain" : String(o.value));
    if(o.value === null){ b.className = "abstain"; }
    if(r && ((o.value === null && r.abstain) || (o.value !== null && r.rating === o.value))){ b.classList.add("on"); }
    b.addEventListener("click", function(){ setRating(o.value); });
    sc.appendChild(b);
  });
  $("note").value = r && r.note ? r.note : "";
  $("note").disabled = !r;
  $("backBtn").disabled = state.pos === 0;
  $("nextBtn").disabled = !r;
  show("itemPanel");
}
function next(){
  var item = DATA.items[state.pos];
  if(!rec(item)){ return; }
  var last = state.pos === DATA.items.length - 1;
  var endOfPart = !last && DATA.items[state.pos + 1].part !== item.part;
  state.pos += 1;
  if(last){ state.finished_at = new Date().toISOString(); save(); render(); download(true); return; }
  save();
  if(endOfPart){
    $("partDoneText").innerHTML = "<b>Part " + item.part + " of " + DATA.parts + " done.</b> This is a good place to stop if you want to.";
    show("partDone"); return;
  }
  render();
}
function back(){ if(state.pos > 0){ state.pos -= 1; save(); render(); } }

function payload(){
  var rows = [];
  DATA.items.forEach(function(item, i){
    var r = state.ratings[item.item_id];
    if(!r){ return; }
    rows.push({item_id:item.item_id, pair_id:item.pair_id, is_repeat:item.is_repeat, position:i+1,
               rating:r.abstain ? null : r.rating, abstain:!!r.abstain, note:r.note || "",
               answered_at:r.answered_at || null});
  });
  return JSON.stringify({
    instrument:DATA.instrument, design_version:DATA.design_version, spec_sha256:DATA.spec_sha256,
    rater:DATA.rater, saved_at:new Date().toISOString(), started_at:state.started_at,
    finished_at:state.finished_at, complete:rows.length === DATA.items.length,
    order:DATA.items.map(function(x){ return x.item_id; }), ratings:rows
  }, null, 2);
}
function download(auto){
  var text = payload();
  try {
    var blob = new Blob([text], {type:"application/json"});
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "solverah_fitpairs_rater" + DATA.rater + ".json";
    document.body.appendChild(a); a.click(); a.remove();
    if(auto){ $("dlNote").textContent = "Saved automatically: your answers file has been downloaded. Please email it to us."; }
  } catch(e){
    $("dlNote").textContent = "The download did not work in this browser. Copy everything below and paste it into an email.";
    var pre = document.createElement("pre"); pre.textContent = text; $("donePanel").appendChild(pre); show("donePanel");
  }
}

STORAGE_OK = probeStorage();
if(!STORAGE_OK){ $("storageWarn").classList.remove("hidden"); }
load();
$("startBtn").addEventListener("click", function(){ if(!state.started_at){ state.started_at = new Date().toISOString(); save(); } render(); });
$("nextBtn").addEventListener("click", next);
$("backBtn").addEventListener("click", back);
$("continueBtn").addEventListener("click", render);
$("dlBtn").addEventListener("click", function(){ download(false); });
$("note").addEventListener("input", function(e){ setNote(e.target.value); });
if(state.started_at){
  $("startBtn").textContent = answered() ? "Carry on where you left off" : "Start";
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RosterError as exc:
        print("REFUSED: %s" % exc)
        sys.exit(2)
