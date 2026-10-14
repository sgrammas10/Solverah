"""Build confirm_sheet.html -- Julie's short, resumable check of the anchors v3.1 edits.

Generated from make_anchors_v3.V3_1_CHANGES, the same list that writes
anchors_v3_1_PROPOSED.json, so the sheet cannot drift from the file. One item per ruling
(ruling 2's three field edits and ruling 3's two are shown together under one question), plus
one item per DERIVED edit -- the two changes she did not rule on. R4-rule (how a skipped cell
counts in rater agreement) is method, not rubric wording, so it is not on the sheet.

    python build_confirm_sheet.py        # writes confirm_sheet.html beside this file

Stdlib only. Every print is ASCII.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RATER_APP = HERE.parent / "ground_truth" / "rater_app"
sys.path.insert(0, str(RATER_APP))
import make_anchors_v3 as mav  # noqa: E402

OUT = HERE / "confirm_sheet.html"
SHEET_ID = "anchors_v3_1_confirm"
RULING_TITLES = {
    1: "Ruling 1 -- Feedback's lowest band",
    2: "Ruling 2 -- Raising concerns: Collaboration or Feedback?",
    3: "Ruling 3 -- Decision: following a procedure vs. a procedure for deciding",
    4: "Ruling 4 -- Recording \"insufficient evidence\" instead of a score",
    5: "Ruling 5 -- When Decision's middle band (0.5) applies",
}


def items() -> list[dict]:
    """Group V3_1_CHANGES into the sheet's questions, in ruling order, derived last."""
    groups: dict[str, dict] = {}
    for ch in mav.V3_1_CHANGES:
        if ch["ask"] is None:
            continue
        key = ch["id"] if ch["derived"] else f"ruling-{ch['ruling']}"
        g = groups.setdefault(key, {
            "id": key,
            "ruling": ch["ruling"],
            "derived": ch["derived"],
            "title": ch["title"] if ch["derived"] else RULING_TITLES[ch["ruling"]],
            "her_words": ch["her_words"],
            "ask": ch["ask"],
            "edits": [],
        })
        # The group's question is its most specific one: the first that is not a bare "Right?".
        if g["ask"] in ("Right?",) and ch["ask"] not in ("Right?",):
            g["ask"] = ch["ask"]
        g["edits"].append({
            "change_id": ch["id"],
            "where": ch["title"],
            "was": ch.get("old"),
            "now": ch["new"] if isinstance(ch["new"], str)
            else f"{ch['new']['label']}: {ch['new']['text']}",
        })
    ruled = sorted((g for g in groups.values() if not g["derived"]), key=lambda g: g["ruling"])
    derived = [g for g in groups.values() if g["derived"]]
    return ruled + derived


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rubric v3.1 check</title>
<style>
  :root { --ink:#1b1d22; --muted:#667085; --line:#e3e6eb; --bg:#faf9f6; --card:#fff;
          --was:#9aa1ad; --now:#fff4c2; --accent:#1f4e79; --ok:#1a6b3c; --okbg:#eef7f1;
          --flag:#8a5a00; --flagbg:#fff8e6; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .wrap { max-width:760px; margin:0 auto; padding:18px 16px 60px; }
  h1 { font-size:20px; margin:4px 0 6px; }
  .lede { color:var(--muted); font-size:14.5px; margin:0 0 10px; }
  .bar { position:sticky; top:0; z-index:2; background:var(--bg); padding:8px 0;
         border-bottom:1px solid var(--line); display:flex; gap:10px; align-items:center;
         flex-wrap:wrap; margin-bottom:14px; }
  .bar .count { font-size:14px; }
  .bar .saved { font-size:12.5px; color:var(--muted); }
  .bar button { margin-left:auto; }
  .warn { background:#fdecea; border:1px solid #f1b5ae; color:#5f1512; padding:10px 12px;
          border-radius:8px; font-size:14px; margin-bottom:12px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:14px 16px; margin-bottom:14px; }
  .card.done { border-color:#b8dcc6; }
  .card h2 { font-size:16px; margin:0 0 6px; }
  .tag { display:inline-block; font-size:12px; padding:1px 7px; border-radius:10px;
         background:var(--flagbg); color:var(--flag); border:1px solid #e8d9a8; margin-left:6px; }
  .her { font-size:14px; color:var(--muted); border-left:3px solid var(--line);
         padding:2px 0 2px 10px; margin:6px 0 10px; font-style:italic; }
  .edit { margin:8px 0 10px; }
  .edit .where { font-size:12.5px; color:var(--muted); margin-bottom:3px; }
  .was { color:var(--was); text-decoration:line-through; font-size:14px; margin:0 0 4px; }
  .now { background:var(--now); padding:6px 8px; border-radius:6px; font-size:14.5px; margin:0; }
  .ask { font-weight:600; margin:10px 0 8px; }
  .choices { display:flex; gap:8px; flex-wrap:wrap; }
  .choices button { font:inherit; font-size:14px; padding:8px 12px; border-radius:8px;
                    border:1px solid #c3cad4; background:#fff; cursor:pointer; }
  .choices button[aria-pressed="true"] { border-color:var(--accent); background:#eaf2fa;
                                         box-shadow:inset 0 0 0 1px var(--accent); }
  textarea { width:100%; margin-top:8px; font:inherit; font-size:14px; padding:8px;
             border:1px solid var(--line); border-radius:8px; resize:vertical; }
  .hidden { display:none !important; }
  button.primary { font:inherit; font-size:14px; padding:8px 14px; border-radius:8px; border:none;
                   background:var(--accent); color:#fff; cursor:pointer; }
  pre.fallback { white-space:pre-wrap; word-break:break-word; background:#fff;
                 border:1px solid var(--line); border-radius:8px; padding:10px; font-size:12px; }
  .end { color:var(--muted); font-size:14px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Rubric v3.1: did I apply your rulings the way you meant?</h1>
  <p class="lede">__N__ short questions, about 10 minutes. Each one shows what you said, the old
    wording, and the new wording. Answer in any order and stop whenever you like: every click
    saves, so you can close this and pick up later. "I'd rather not say" is always a fine answer.
    The last two are changes I made that you didn't rule on.</p>
  <div id="warn" class="warn hidden"></div>
  <div class="bar">
    <span class="count" id="count"></span>
    <span class="saved" id="saved"></span>
    <button class="primary" id="send">Download my answers so far</button>
  </div>
  <div id="items"></div>
  <p class="end">When you're done (or done for now), press <b>Download my answers so far</b> and
    send Sebastian the file. A half-finished sheet is still useful.</p>
  <pre id="fallback" class="fallback hidden"></pre>
</div>
<script>
var ITEMS = __ITEMS__;
var SHEET = { id: "__SHEET_ID__", rubric_version: "__RUBRIC_VERSION__", changes: __CHANGE_IDS__ };
var STORE_KEY = "solverah_" + SHEET.id;

var state = { started_at: null, answers: {} };
var STORAGE_OK = (function(){
  try { var k = "__probe__" + Math.random(); window.localStorage.setItem(k, "1");
        var ok = window.localStorage.getItem(k) === "1"; window.localStorage.removeItem(k); return ok; }
  catch(e){ return false; }
})();

function warn(msg){ var w = document.getElementById("warn"); w.textContent = msg; w.classList.remove("hidden"); }
function load(){
  if(!STORAGE_OK) return;
  try { var raw = window.localStorage.getItem(STORE_KEY);
        if(raw){ var p = JSON.parse(raw); if(p && p.answers) state = p; } } catch(e){}
}
function save(){
  if(!state.started_at) state.started_at = new Date().toISOString();
  state.saved_at = new Date().toISOString();
  if(!STORAGE_OK){ return; }
  try { window.localStorage.setItem(STORE_KEY, JSON.stringify(state));
        document.getElementById("saved").textContent = "saved"; }
  catch(e){ STORAGE_OK = false;
    warn("Your answers stopped saving in this browser. They are still on screen -- press " +
         "\"Download my answers so far\" before closing this page."); }
}

var CHOICES = [["yes", "Yes, as written"], ["change", "Change this"], ["decline", "I'd rather not say"]];

function el(tag, cls, text){ var e = document.createElement(tag); if(cls) e.className = cls;
  if(text !== undefined && text !== null) e.textContent = text; return e; }

function answered(id){ var a = state.answers[id]; return !!(a && a.choice); }

function renderCount(){
  var n = ITEMS.filter(function(it){ return answered(it.id); }).length;
  document.getElementById("count").textContent = n + " of " + ITEMS.length + " answered";
}

function renderItem(it){
  var a = state.answers[it.id] || {};
  var card = el("section", "card" + (a.choice ? " done" : "")); card.id = "item_" + it.id;
  var h = el("h2", null, it.title);
  if(it.derived) h.appendChild(el("span", "tag", "my inference, not your ruling"));
  card.appendChild(h);
  if(it.her_words) card.appendChild(el("p", "her", "You said: “" + it.her_words + "”"));
  it.edits.forEach(function(ed){
    var box = el("div", "edit");
    if(it.edits.length > 1) box.appendChild(el("div", "where", ed.where));
    if(ed.was) box.appendChild(el("p", "was", ed.was));
    box.appendChild(el("p", "now", ed.now));
    card.appendChild(box);
  });
  card.appendChild(el("p", "ask", it.ask));
  var row = el("div", "choices");
  CHOICES.forEach(function(c){
    var b = el("button", null, c[1]); b.type = "button"; b.dataset.choice = c[0];
    b.setAttribute("aria-pressed", a.choice === c[0] ? "true" : "false");
    b.onclick = function(){ choose(it.id, c[0]); };
    row.appendChild(b);
  });
  card.appendChild(row);
  var ta = el("textarea"); ta.rows = 3; ta.id = "text_" + it.id;
  ta.placeholder = "What should it say instead? A rough version is fine.";
  ta.value = a.text || "";
  if(a.choice !== "change") ta.classList.add("hidden");
  ta.oninput = function(){ var cur = state.answers[it.id] || {}; cur.text = ta.value;
                           state.answers[it.id] = cur; save(); };
  card.appendChild(ta);
  return card;
}

function choose(id, choice){
  var cur = state.answers[id] || {};
  cur.choice = choice; cur.at = new Date().toISOString();
  state.answers[id] = cur; save();
  var it = ITEMS.filter(function(x){ return x.id === id; })[0];
  var old = document.getElementById("item_" + id);
  old.parentNode.replaceChild(renderItem(it), old);
  if(choice === "change") document.getElementById("text_" + id).focus();
  renderCount();
}

function payload(){
  return JSON.stringify({
    sheet: SHEET.id, rubric_version: SHEET.rubric_version, changes_covered: SHEET.changes,
    started_at: state.started_at, saved_at: state.saved_at,
    answered: ITEMS.filter(function(it){ return answered(it.id); }).length, of: ITEMS.length,
    answers: ITEMS.map(function(it){ var a = state.answers[it.id] || {};
      return { item: it.id, changes: it.edits.map(function(e){ return e.change_id; }),
               choice: a.choice || null, text: a.choice === "change" ? (a.text || "") : "" }; })
  }, null, 2);
}

document.getElementById("send").onclick = function(){
  var text = payload();
  try {
    var blob = new Blob([text], {type: "application/json"});
    var a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = "solverah_rubric_v31_julie.json";
    document.body.appendChild(a); a.click(); a.remove();
    document.getElementById("saved").textContent = "downloaded -- please send it to Sebastian";
  } catch(e){
    var pre = document.getElementById("fallback"); pre.textContent = text; pre.classList.remove("hidden");
    warn("The download didn't work in this browser. Copy the text at the bottom of the page into an email.");
  }
};

load();
if(!STORAGE_OK) warn("This browser won't save your answers between visits. You can still answer -- " +
                     "just press \"Download my answers so far\" before you close the page.");
var host = document.getElementById("items");
ITEMS.forEach(function(it){ host.appendChild(renderItem(it)); });
renderCount();
</script>
</body>
</html>
"""


def build() -> str:
    its = items()
    change_ids = [e["change_id"] for it in its for e in it["edits"]]
    return (PAGE
            .replace("__ITEMS__", json.dumps(its, ensure_ascii=True))
            .replace("__CHANGE_IDS__", json.dumps(change_ids))
            .replace("__SHEET_ID__", SHEET_ID)
            .replace("__RUBRIC_VERSION__", mav.V3_1_VERSION)
            .replace("__N__", {7: "Seven"}.get(len(its), str(len(its)))))


def main() -> int:
    html = build()
    OUT.write_text(html, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.name}: {len(items())} items, {len(html):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
