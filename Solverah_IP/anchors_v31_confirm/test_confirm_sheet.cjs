/* jsdom checks over confirm_sheet.html, in the style of priors_elicitation's test.

   The constraint this sheet is built around (memory: solverah-julie-async-only): self-paced,
   resumable, saves as it goes, valid half-finished, "rather not say" on every item.
   Each of those is a check below.

   jsdom is vendored under ground_truth/rater_app/node_modules:

     NODE_PATH=../ground_truth/rater_app/node_modules node test_confirm_sheet.cjs
*/
const {JSDOM} = require('jsdom');
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'confirm_sheet.html'), 'utf8');

function boot(opts = {}) {
  return new JSDOM(html, { runScripts: "dangerously", url: "file:///t/confirm_sheet.html",
    beforeParse(w) {
      if (opts.killStorage) {
        Object.defineProperty(w, 'localStorage', { get() { throw new Error('SecurityError'); } });
      } else {
        const m = opts.store || {};
        Object.defineProperty(w, 'localStorage', { value: {
          getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },
          removeItem: k => { delete m[k]; }, clear: () => { for (const k in m) delete m[k]; } } });
      }
      w.URL.createObjectURL = () => "blob:fake"; w.URL.revokeObjectURL = () => {};
      w.__downloads = [];
      const oc = w.document.createElement.bind(w.document);
      w.document.createElement = t => { const el = oc(t);
        if (t === 'a') el.click = () => { w.__downloads.push(el.download); }; return el; };
    } });
}
const R = []; const check = (n, c, e = "") => R.push([c ? "PASS" : "FAIL", n, e]);
const btn = (doc, id, choice) => doc.querySelector('#item_' + id + ' button[data-choice="' + choice + '"]');
const payloadOf = w => JSON.parse(w.eval("payload()"));

// 1 -- renders, first item answerable without reading anything else
{ const w = boot().window; const doc = w.document;
  const cards = doc.querySelectorAll(".card");
  const n = w.eval("ITEMS.length");
  check("one card per item", cards.length === n && n === 7, cards.length + " cards");
  check("first card is ruling 1", /^Ruling 1/.test(cards[0].querySelector("h2").textContent));
  check("first card is the first thing after the intro",
        doc.getElementById("items").firstElementChild === cards[0]);
  check("every card offers yes / change / rather not say",
        [...cards].every(c => c.querySelectorAll("button[data-choice]").length === 3 &&
                              /rather not say/.test(c.textContent)));
  check("derived items say they are my inference",
        ["D1", "D2"].every(id => /my inference, not your ruling/.test(doc.getElementById("item_" + id).textContent)));
  check("rulings quote her words", /You said:/.test(doc.getElementById("item_ruling-1").textContent));
  check("old wording shown struck through where it existed",
        !!doc.querySelector("#item_ruling-1 .was") && !doc.querySelector("#item_ruling-4 .was"));
  check("ruling 2 shows all three of its edits", doc.querySelectorAll("#item_ruling-2 .edit").length === 3);
  check("counter starts at 0", /^0 of 7 answered/.test(doc.getElementById("count").textContent));
  check("says how long it takes", /about 10 minutes/.test(doc.body.textContent)); }

// 2 -- answering saves on every click; resume restores everything
{ const store = {}; const w = boot({store}).window; const doc = w.document;
  btn(doc, "ruling-1", "yes").click();
  btn(doc, "ruling-3", "change").click();
  const ta = doc.getElementById("text_ruling-3");
  check("'change' reveals a text box", !ta.classList.contains("hidden"));
  ta.value = "Escalation should count as judgement only when no analysis is required.";
  ta.dispatchEvent(new w.Event("input"));
  btn(doc, "D1", "decline").click();
  check("saved to storage on click", !!store["solverah_anchors_v3_1_confirm"]);
  check("counter moves", /^3 of 7 answered/.test(doc.getElementById("count").textContent));

  const w2 = boot({store}).window; const d2 = w2.document;
  check("resume: yes restored", btn(d2, "ruling-1", "yes").getAttribute("aria-pressed") === "true");
  check("resume: change restored with its text",
        btn(d2, "ruling-3", "change").getAttribute("aria-pressed") === "true" &&
        /Escalation should count/.test(d2.getElementById("text_ruling-3").value) &&
        !d2.getElementById("text_ruling-3").classList.contains("hidden"));
  check("resume: decline restored", btn(d2, "D1", "decline").getAttribute("aria-pressed") === "true");
  check("resume: counter restored", /^3 of 7 answered/.test(d2.getElementById("count").textContent));

  // 3 -- a half-finished sheet emits a complete, honest payload
  const p = payloadOf(w2);
  check("payload: 3 answered of 7", p.answered === 3 && p.of === 7);
  check("payload: one row per item, unanswered are null",
        p.answers.length === 7 && p.answers.filter(a => a.choice === null).length === 4);
  const r3 = p.answers.find(a => a.item === "ruling-3");
  check("payload: change text carried", /Escalation should count/.test(r3.text));
  check("payload: items name the change ids they cover",
        JSON.stringify(r3.changes) === JSON.stringify(["R3a", "R3b"]));
  check("payload: rubric version", /^v3\.1-PROPOSED/.test(p.rubric_version));
  check("payload: R4-rule is not on the sheet", !p.changes_covered.includes("R4-rule"));

  // 4 -- changing an answer away from 'change' drops the text from the payload
  btn(d2, "ruling-3", "yes").click();
  check("switching to yes hides the box", d2.getElementById("text_ruling-3").classList.contains("hidden"));
  check("and the payload carries no stale text", payloadOf(w2).answers.find(a => a.item === "ruling-3").text === "");

  // 5 -- download
  d2.getElementById("send").click();
  check("download fires with a named file", w2.__downloads[0] === "solverah_rubric_v31_julie.json", w2.__downloads[0]); }

// 6 -- storage blocked: still usable, says so, still downloads
{ const w = boot({killStorage: true}).window; const doc = w.document;
  check("blocked storage: warning shown", !doc.getElementById("warn").classList.contains("hidden"));
  let threw = false; try { btn(doc, "ruling-2", "yes").click(); } catch (e) { threw = true; }
  check("blocked storage: answering does not throw", !threw);
  check("blocked storage: answer held on screen", btn(doc, "ruling-2", "yes").getAttribute("aria-pressed") === "true");
  doc.getElementById("send").click();
  check("blocked storage: download still works", w.__downloads.length === 1); }

console.log("");
for (const [s, n, e] of R) console.log(`  ${s}  ${n}${e ? "   [" + e + "]" : ""}`);
const f = R.filter(r => r[0] === "FAIL").length;
console.log(`\n${R.length - f}/${R.length} passed`);
process.exit(f ? 1 : 0);
