/* test_fit_page.cjs -- jsdom checks over a built fit-pairs rater page.

   House style of rater_app/test_rater_page.cjs and priors_elicitation/test_priors_elicitation.cjs.
   The seam this exists for: the page emits JSON and fit_pairs_analysis.py reads JSON, and
   nothing else proves those are the same JSON. It also proves the repeats are the same
   question on screen, not only in the spec.

   Build a page for the TEST rater Z, then run (node is on fnm, off PATH; jsdom is vendored
   under rater_app/node_modules):

     python build_fit_pages.py --rater Z --roster fixtures/roster_test.json --out <DIR> --spec-out <DIR>/pair_specs.json
     NODE_PATH=../rater_app/node_modules node test_fit_page.cjs <DIR>/fit_pairs_raterZ.html [PAYLOAD_OUT]

   PAYLOAD_OUT (default fixtures/captured_payload_raterZ.json) receives a full run's real
   page output; test_fit_pairs.py feeds it through fit_pairs_analysis.load_return.
   Exit code 1 on any FAIL.
*/
const {JSDOM} = require('jsdom');
const fs = require('fs');
const path = require('path');
const [PAGE, PAYLOAD_OUT_ARG] = process.argv.slice(2);
if (!PAGE) { console.error("usage: node test_fit_page.cjs <page> [payload out]"); process.exit(2); }
const PAYLOAD_OUT = PAYLOAD_OUT_ARG || path.join(__dirname, 'fixtures', 'captured_payload_raterZ.json');
const HTML = fs.readFileSync(PAGE, 'utf8');

function boot(opts = {}) {
  return new JSDOM(HTML, {runScripts: "dangerously", url: "file:///t/fit_pairs_raterZ.html",
    beforeParse(w) {
      if (opts.killStorage) {
        Object.defineProperty(w, 'localStorage', {get() { throw new Error('SecurityError'); }});
      } else {
        const m = opts.store || {};
        Object.defineProperty(w, 'localStorage', {configurable: true, value: {
          getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },
          removeItem: k => { delete m[k]; }, clear: () => { for (const k in m) delete m[k]; }}});
      }
      w.URL.createObjectURL = () => "blob:fake"; w.URL.revokeObjectURL = () => {};
      w.__downloads = [];
      const oc = w.document.createElement.bind(w.document);
      w.document.createElement = (t) => { const el = oc(t); if (t === 'a') { el.click = () => { w.__downloads.push(el.download); }; } return el; };
    }});
}
const R = []; const check = (n, c, e = "") => R.push([c ? "PASS" : "FAIL", n, e]);
const $ = (w, id) => w.document.getElementById(id);
const click = (w, sel) => w.document.querySelector(sel).click();
const rate = (w, v) => click(w, '#scale button[data-value="' + v + '"]');

// 1 -- storage present / denied
{ const w = boot({store: {}}).window;
  check("storage OK -> banner hidden", $(w, "storageWarn").classList.contains("hidden"));
  check("STORAGE_OK true", w.eval("STORAGE_OK") === true);
  check("intro thanks the rater first", /^Thank you/.test($(w, "intro").querySelector("p").textContent.trim()));
  check("54 items embedded (10 blocks x 5 + 4 repeats)", w.eval("DATA.items.length") === 54, w.eval("DATA.items.length"));
  check("intro states the part count", new RegExp("There are " + w.eval("DATA.parts") + " parts").test($(w, "intro").textContent));
  check("rater id embedded", w.eval("DATA.rater") === "Z"); }
{ const w = boot({killStorage: true}).window;
  check("storage denied -> banner VISIBLE", !$(w, "storageWarn").classList.contains("hidden"));
  check("banner says work can be lost", /lose everything/i.test($(w, "storageWarn").textContent));
  let threw = false; try { w.eval("save()"); } catch (e) { threw = true; }
  check("save() does not throw when storage denied", !threw);
  $(w, "startBtn").click();
  check("page still usable without storage", !$(w, "itemPanel").classList.contains("hidden")); }

// 2 -- answering, gating, abstaining, resuming
{ const store = {}; const w = boot({store}).window;
  $(w, "startBtn").click();
  check("first screen shown", !$(w, "itemPanel").classList.contains("hidden"));
  check("Next disabled before an answer", $(w, "nextBtn").disabled === true);
  check("note disabled before an answer", $(w, "note").disabled === true);
  check("six options (5 + can't say)", w.document.querySelectorAll("#scale button").length === 6);
  check("ask names the person", /If \w+ took a job at this company/.test($(w, "ask").textContent));
  rate(w, 4);
  check("Next enabled after an answer", $(w, "nextBtn").disabled === false);
  $(w, "note").value = "pace gap"; $(w, "note").dispatchEvent(new w.Event("input"));
  $(w, "nextBtn").click();
  rate(w, "abstain"); $(w, "nextBtn").click();
  const first = w.eval("DATA.items[0].item_id"), second = w.eval("DATA.items[1].item_id");
  const saved = JSON.parse(store[w.eval("KEY")]);
  check("rating persisted", saved.ratings[first].rating === 4 && saved.ratings[first].note === "pace gap");
  check("abstain persisted as null + abstain", saved.ratings[second].rating === null && saved.ratings[second].abstain === true);
  check("position persisted", saved.pos === 2);
  const w2 = boot({store}).window;
  check("reopen offers to carry on", /Carry on/.test($(w2, "startBtn").textContent));
  $(w2, "startBtn").click();
  check("reopen resumes at screen 3", w2.eval("state.pos") === 2 && /screen 3 of/.test($(w2, "where").textContent));
  $(w2, "backBtn").click();
  check("Back shows the abstained answer selected",
        w2.document.querySelector('#scale button[data-value="abstain"]').classList.contains("on"));
  // half-finished export is valid and keyed as the analysis reads it
  $(w2, "dlBtn").click();
  check("manual download works mid-way", w2.__downloads[0] === "solverah_fitpairs_raterZ.json", w2.__downloads[0]);
  const p = JSON.parse(w2.eval("payload()"));
  check("half-finished payload: complete=false, 2 ratings", p.complete === false && p.ratings.length === 2);
  check("payload top-level keys", ["instrument", "design_version", "spec_sha256", "rater", "order", "ratings"]
        .every(k => k in p) && p.instrument === "fit_pairs_v1" && /^[0-9a-f]{64}$/.test(p.spec_sha256));
  check("rating row keys", p.ratings.every(r => ["item_id", "pair_id", "is_repeat", "rating", "abstain", "position"].every(k => k in r)));
  check("order lists every item", p.order.length === w2.eval("DATA.items.length")); }

// 3 -- part boundary: a stopping point after each part
{ const w = boot({store: {}}).window; $(w, "startBtn").click();
  const n1 = w.eval("DATA.items.filter(function(x){return x.part===1}).length");
  for (let i = 0; i < n1; i++) { rate(w, 3); $(w, "nextBtn").click(); }
  check("part-done panel after part 1", !$(w, "partDone").classList.contains("hidden"));
  check("part-done says it is a good place to stop", /good place to stop/.test($(w, "partDoneText").textContent));
  $(w, "continueBtn").click();
  check("carry on -> part 2 screen 1", new RegExp("Part 2 of " + w.eval("DATA.parts") + ", screen 1 of").test($(w, "where").textContent)); }

// 4 -- repeats are the same question on screen
{ const w = boot({store: {}}).window; $(w, "startBtn").click();
  const items = w.eval("DATA.items");
  const reps = items.filter(x => x.is_repeat);
  check("four repeats", reps.length === 4);
  let same = true, dom = true, later = true;
  reps.forEach(r => {
    const iOrig = items.findIndex(x => !x.is_repeat && x.pair_id === r.pair_id);
    const iRep = items.indexOf(r);
    if (items[iOrig].card !== r.card || items[iOrig].name !== r.name) same = false;
    if (iRep - iOrig < 10) later = false;
    w.eval("state.pos=" + iOrig + "; render()"); const a = $(w, "card").innerHTML + "|" + $(w, "ask").textContent;
    w.eval("state.pos=" + iRep + "; render()"); const b = $(w, "card").innerHTML + "|" + $(w, "ask").textContent;
    if (a !== b) dom = false;
  });
  check("repeat card string identical to original", same);
  check("repeat renders identically (card + question)", dom);
  check("every repeat at least 10 screens after its original", later);
  check("repeat screen does not announce itself", !/repeat|again|seen/i.test($(w, "where").textContent)); }

// 5 -- full run, auto-download, captured payload
{ const store = {}; const w = boot({store}).window; $(w, "startBtn").click();
  const n = w.eval("DATA.items.length");
  for (let i = 0; i < n; i++) {
    if (!$(w, "partDone").classList.contains("hidden")) $(w, "continueBtn").click();
    rate(w, i % 7 === 6 ? "abstain" : String(1 + (i % 5)));
    $(w, "nextBtn").click();
  }
  check("done panel shown", !$(w, "donePanel").classList.contains("hidden"));
  check("auto-download on finishing", w.__downloads.length === 1 && w.__downloads[0] === "solverah_fitpairs_raterZ.json");
  check("dlNote confirms auto-save", /Saved automatically/.test($(w, "dlNote").textContent));
  const p = JSON.parse(w.eval("payload()"));
  check("complete=true, one row per item", p.complete === true && p.ratings.length === n);
  check("repeat rows carry original pair_id", p.ratings.filter(r => r.is_repeat).every(r => /^R\d$/.test(r.item_id) && /^B\d-C\d$/.test(r.pair_id)));
  check("first-showing rows: item_id == pair_id", p.ratings.filter(r => !r.is_repeat).every(r => r.item_id === r.pair_id));
  check("ratings are ints 1..5 or null", p.ratings.every(r => r.abstain ? r.rating === null : Number.isInteger(r.rating) && r.rating >= 1 && r.rating <= 5));
  check("finished_at set", !!p.finished_at);
  fs.writeFileSync(PAYLOAD_OUT, JSON.stringify(p, null, 2) + "\n"); }

// 6 -- mid-session storage failure degrades loudly
{ const w = boot({store: {}}).window; $(w, "startBtn").click();
  Object.defineProperty(w, 'localStorage', {configurable: true, value: {setItem() { throw new Error("QuotaExceeded"); }, getItem: () => null, removeItem() {}}});
  rate(w, 2);
  check("mid-session save failure -> banner appears", !$(w, "storageWarn").classList.contains("hidden"));
  check("banner says do not refresh", /do not refresh/i.test($(w, "storageWarn").textContent)); }

let fail = 0;
for (const [s, n, e] of R) { if (s === "FAIL") fail++; console.log(s + "  " + n + (e !== "" && s === "FAIL" ? "  [" + e + "]" : "")); }
console.log("\n" + (R.length - fail) + "/" + R.length + " passed");
process.exit(fail ? 1 : 0);
