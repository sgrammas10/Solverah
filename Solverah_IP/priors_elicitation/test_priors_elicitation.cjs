/* End-to-end check on the elicitation form, in the style of rater_app/test_rater_page.js.
 *
 * The seam this exists for: the converter is tested against JSON, and the form emits
 * JSON, and nothing otherwise proves those are the same JSON. A field renamed on one
 * side and not the other would show up as "she didn't answer that dimension" rather
 * than as an error.
 *
 * Named .cjs because the repo package.json sets "type": "module" and Solverah_IP now
 * lives inside the repo -- a plain .js here is parsed as an ES module.
 *
 * jsdom is vendored under ground_truth/rater_app/node_modules, so point NODE_PATH at it:
 *
 *   NODE_PATH=../ground_truth/rater_app/node_modules node test_priors_elicitation.cjs
 *
 * Writes the captured payload to captured_payload.json so convert_priors_response.py can
 * be run against output the form actually produced, not output a human imagined.
 */
const {JSDOM} = require('jsdom');
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'priors_elicitation.html'), 'utf8');

function boot(opts = {}) {
  return new JSDOM(html, {
    runScripts: "dangerously",
    url: "file:///t/priors_elicitation.html",
    beforeParse(w) {
      if (opts.killStorage) {
        Object.defineProperty(w, 'localStorage', {
          get() { throw new Error('SecurityError'); }
        });
      } else {
        const m = opts.store || {};
        Object.defineProperty(w, 'localStorage', {
          value: {
            getItem: k => (k in m ? m[k] : null),
            setItem: (k, v) => { m[k] = String(v); },
            removeItem: k => { delete m[k]; },
            clear: () => { for (const k in m) delete m[k]; }
          }
        });
      }
      w.URL.createObjectURL = () => "blob:fake";
      w.URL.revokeObjectURL = () => {};
      const oc = w.document.createElement.bind(w.document);
      w.document.createElement = (t) => {
        const el = oc(t);
        if (t === 'a') el.click = () => {};
        return el;
      };
    }
  });
}

const R = [];
const check = (name, cond, extra = "") => R.push([cond ? "PASS" : "FAIL", name, extra]);

function pick(w, id) {
  const el = w.document.getElementById(id);
  if (!el) throw new Error("no such control: " + id);
  el.checked = true;
  el.dispatchEvent(new w.Event('change'));
}
function type(w, id, text) {
  const el = w.document.getElementById(id);
  if (!el) throw new Error("no such field: " + id);
  el.value = text;
  el.dispatchEvent(new w.Event('input'));
}

const DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"];

/* ---- 1. the page builds ------------------------------------------------ */
{
  const w = boot({store: {}}).window;
  check("all six dimensions rendered",
    DIMS.every(d => w.document.getElementById(d + "_above-0") &&
                    w.document.getElementById(d + "_below-0")));
  check("baseline scale rendered", !!w.document.getElementById("baseline-7"));
  check("recheck scale rendered", !!w.document.getElementById("recheck-4"));
  check("confounder scales rendered",
    !!w.document.getElementById("stage_size_large-7") &&
    !!w.document.getElementById("comp_below_market-5"));
  check("every dimension offers abstention",
    DIMS.every(d => !!w.document.getElementById("conf-" + d + "-abstain")));
  const labels = w.document.querySelectorAll(".scale label").length;
  check("11 buttons per scale x 18 scales", labels === 11 * 18, "got " + labels);
}

/* ---- 2. answers persist across a close-and-reopen ---------------------- */
{
  const store = {};
  const w1 = boot({store}).window;
  pick(w1, "baseline-7");
  pick(w1, "autonomy_above-3");
  type(w1, "note-autonomy", "biggest one by far");
  check("something was written to storage", Object.keys(store).length === 1);

  const w2 = boot({store}).window;
  check("baseline survived reload", w2.document.getElementById("baseline-7").checked);
  check("scenario answer survived reload", w2.document.getElementById("autonomy_above-3").checked);
  check("note survived reload",
    w2.document.getElementById("note-autonomy").value === "biggest one by far");
  check("progress reflects restored answers",
    /^2 of \d+ answered$/.test(w2.document.getElementById("count").textContent),
    w2.document.getElementById("count").textContent);
}

/* ---- 3. storage blocked -> still usable, and says so ------------------- */
{
  let w;
  let threw = false;
  try { w = boot({killStorage: true}).window; } catch (e) { threw = true; }
  check("page survives localStorage throwing", !threw);
  if (!threw) {
    pick(w, "baseline-6");
    check("answer still recorded in memory", w.document.getElementById("baseline-6").checked);
    check("user is warned auto-save failed",
      /auto-save/i.test(w.document.getElementById("saved").textContent),
      w.document.getElementById("saved").textContent);
  }
}

/* ---- 4. a full sitting, then the payload the converter will receive ---- */
{
  const w = boot({store: {}}).window;

  pick(w, "baseline-7");

  const ANSWERS = {
    autonomy:      {above: 3, below: 5, conf: "confident"},
    pace:          {above: 5, below: 4, conf: "fairly"},
    collaboration: {above: 5, below: 4, conf: "fairly"},
    feedback:      {above: 6, below: 3, conf: "unsure"},
    innovation:    {above: 4, below: 6, conf: "fairly"},
    decision:      {abstain: true, conf: "abstain"}
  };

  for (const [dim, a] of Object.entries(ANSWERS)) {
    if (!a.abstain) {
      pick(w, dim + "_above-" + a.above);
      pick(w, dim + "_below-" + a.below);
    }
    pick(w, "conf-" + dim + "-" + a.conf);
  }
  type(w, "note-autonomy", "Biggest one by far in my experience.");
  type(w, "note-decision", "I genuinely don't know on this one.");

  // a plausible range on one scenario, driven through the real selects
  const scen = w.document.getElementById("collaboration_above-5").closest(".scenario");
  const sels = scen.querySelectorAll("select");
  check("range controls exist on a scenario", sels.length === 2, "got " + sels.length);
  sels[0].value = "4"; sels[0].dispatchEvent(new w.Event('change'));
  sels[1].value = "7"; sels[1].dispatchEvent(new w.Event('change'));

  pick(w, "recheck-4");
  pick(w, "stage_size_large-7");
  pick(w, "stage_size_small-6");
  pick(w, "comp_above_market-8");
  pick(w, "comp_below_market-5");
  pick(w, "ind-a_little");
  type(w, "free_note", "Level matters more than any of this for early-career people.");

  check("progress reaches 100% even with a dimension declined",
    w.document.getElementById("bar").style.width === "100%",
    w.document.getElementById("count").textContent);

  w.document.getElementById("dl").click();
  const raw = w.document.getElementById("outbox").value;
  check("download produced output", raw.length > 0);

  let payload = null;
  try { payload = JSON.parse(raw); } catch (e) {}
  check("output is valid JSON", payload !== null);

  if (payload) {
    check("instrument stamped", payload.instrument === "priors_elicitation_v1");
    check("baseline in the shape the converter reads",
      payload.baseline && payload.baseline.out_of_10 === 7);
    check("all six dimensions present",
      DIMS.every(d => payload.dimensions && payload.dimensions[d]));
    check("scenario keys are above/below",
      DIMS.every(d => "above" in payload.dimensions[d] && "below" in payload.dimensions[d]));
    check("answered scenario carries out_of_10",
      payload.dimensions.autonomy.above.out_of_10 === 3 &&
      payload.dimensions.autonomy.below.out_of_10 === 5);
    check("abstained dimension carries nulls, not junk",
      payload.dimensions.decision.above.out_of_10 === null &&
      payload.dimensions.decision.confidence === "abstain");
    check("range emitted as [lo, hi]",
      JSON.stringify(payload.dimensions.collaboration.above.range) === "[4,7]",
      JSON.stringify(payload.dimensions.collaboration.above.range));
    check("unranged scenario omits range",
      !("range" in payload.dimensions.autonomy.above));
    check("recheck names its dimension and scenario",
      payload.recheck.dimension === "pace" && payload.recheck.scenario === "above" &&
      payload.recheck.answer.out_of_10 === 4);
    check("confounders keyed as the converter expects",
      payload.confounders.stage_size.large.out_of_10 === 7 &&
      payload.confounders.stage_size.small.out_of_10 === 6 &&
      payload.confounders.comp.above_market.out_of_10 === 8 &&
      payload.confounders.comp.below_market.out_of_10 === 5);
    check("industry answer captured", payload.confounders.industry_matters === "a_little");
    check("notes captured", payload.notes.free.startsWith("Level matters"));

    fs.writeFileSync(path.join(__dirname, "captured_payload.json"),
                     JSON.stringify(payload, null, 2), "utf8");
  }
}

/* ---- 5. a half-finished sitting is still emittable --------------------- */
{
  const w = boot({store: {}}).window;
  pick(w, "baseline-7");
  pick(w, "pace_above-5");
  w.document.getElementById("dl").click();
  let payload = null;
  try { payload = JSON.parse(w.document.getElementById("outbox").value); } catch (e) {}
  check("partial sitting still emits JSON", payload !== null);
  if (payload) {
    check("unanswered scenarios are null, not missing",
      payload.dimensions.feedback.above.out_of_10 === null);
  }
}

/* ---- report ------------------------------------------------------------ */
const fails = R.filter(r => r[0] === "FAIL");
for (const [status, name, extra] of R) {
  console.log(`${status}  ${name}${extra ? "   [" + extra + "]" : ""}`);
}
console.log("");
console.log(`${R.length - fails.length}/${R.length} passed`);
if (fails.length) process.exit(1);
