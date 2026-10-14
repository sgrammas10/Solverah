/* test_rater_page.cjs -- jsdom checks over generated rater pages.

   Ported 2026-09-29 from test_rater_page.js, which read a hard-coded /tmp/t2 path and used
   require() in a .js file under the repo's "type":"module" -- so it could not run as it stood.
   Sections 1-7 are the original checks, unchanged in substance, against a page built from the
   FROZEN v1 anchors. Sections 8-12 cover "insufficient evidence" (Julie's ruling 4) against a
   page built from anchors v3.1.

   Build the two pages, then run (node is on fnm, off PATH -- see memory feedback_env_constraints):

     python build_rater_page.py --packet ../anonymization/P-01_packet_ANON.txt --packet-id P-01 \
         --rater A --out <DIR>/v1
     python build_rater_page.py --packet ../anonymization/P-01_packet_ANON.txt --packet-id P-01 \
         --rater A --anchors anchors_v3_1_PROPOSED.json --out <DIR>/v31
     node test_rater_page.cjs <DIR>/v1/P-01_raterA.html <DIR>/v31/P-01_raterA.html [PAYLOAD_OUT]

   PAYLOAD_OUT, if given, receives the section-11 mixed payload: real page output that
   test_insufficient_evidence.py feeds through rater_agreement (fixtures/v31_page_payload.json).
*/
const {JSDOM}=require('jsdom'); const fs=require('fs');
const [V1_PAGE, V31_PAGE, PAYLOAD_OUT]=process.argv.slice(2);
if(!V1_PAGE||!V31_PAGE){ console.error("usage: node test_rater_page.cjs <v1 page> <v3.1 page> [payload out]"); process.exit(2); }
const V1_HTML=fs.readFileSync(V1_PAGE,'utf8'), V31_HTML=fs.readFileSync(V31_PAGE,'utf8');

function boot(opts={}, html=V1_HTML){
  return new JSDOM(html,{runScripts:"dangerously",url:"file:///t/P-01_raterA.html",
    beforeParse(w){
      if(opts.killStorage){ Object.defineProperty(w,'localStorage',{get(){throw new Error('SecurityError');}}); }
      else if(opts.store){ const m=opts.store;
        Object.defineProperty(w,'localStorage',{value:{getItem:k=>k in m?m[k]:null,
          setItem:(k,v)=>{m[k]=String(v)},removeItem:k=>{delete m[k]},clear:()=>{for(const k in m)delete m[k]}}}); }
      w.URL.createObjectURL=()=>"blob:fake"; w.URL.revokeObjectURL=()=>{};
      w.__downloads=[];
      const oc=w.document.createElement.bind(w.document);
      w.document.createElement=(t)=>{const el=oc(t); if(t==='a'){ el.click=()=>{w.__downloads.push(el.download);} } return el;};
    }});
}
const R=[]; const check=(n,c,e="")=>R.push([c?"PASS":"FAIL",n,e]);

// 1 -- storage present
{ const d=boot({store:{}}); const w=d.window;
  check("storage OK -> banner hidden", w.document.getElementById("storageWarn").classList.contains("hidden"));
  check("STORAGE_OK true", w.eval("STORAGE_OK")===true); }

// 2 -- storage denied
{ const d=boot({killStorage:true}); const w=d.window;
  const warn=w.document.getElementById("storageWarn");
  check("storage denied -> banner VISIBLE", !warn.classList.contains("hidden"));
  check("banner says work can be lost", /lose everything/i.test(warn.textContent));
  check("STORAGE_OK false", w.eval("STORAGE_OK")===false);
  check("page still startable", !!w.document.getElementById("startBtn"));
  let threw=false; try{ w.eval("save()"); }catch(e){ threw=true; }
  check("save() does not throw when storage denied", !threw); }

// 3 -- full run + auto-download
{ const store={}; const d=boot({store}); const w=d.window;
  w.document.getElementById("startBtn").click();
  w.eval(`DIMS.forEach(dm=>{ const dr=draft(dm.key); dr.quotes=[{text:"Decent company to work for",eid:"A1",sec:"A",src:"company"}];
      dr.band=dm.bands[2].value; dr.conf=CONF[1].value; dr.note=""; commit(dm.key); });
    state.recognition="no"; state.searched="no"; save();`);
  check("6 committed", w.eval("Object.keys(state.scores).length")===6);
  check("DOWNLOADED false before submit", w.eval("DOWNLOADED")===false);
  w.document.getElementById("submitBtn").click();
  check("submitted_at set", !!w.eval("state.submitted_at"));
  check("AUTO-DOWNLOAD fired on submit", w.__downloads.length===1, JSON.stringify(w.__downloads));
  check("filename correct", w.__downloads[0]==="solverah_P-01_raterA.json", w.__downloads[0]);
  check("DOWNLOADED true after submit", w.eval("DOWNLOADED")===true);
  check("dlNote confirms auto-save", /Saved automatically/i.test(w.document.getElementById("dlNote").textContent));
  const p=JSON.parse(w.eval("payload()"));
  check("payload anchors_hash (frozen v1)", p.anchors_hash==="55c4501b25c5", p.anchors_hash);
  check("payload 6 scores", (p.scores||[]).length===6);
  check("payload identifies packet+rater", p.packet_id==="P-01"&&p.rater==="A");
  check("payload carries recognition + searched", p.recognition==="no"&&p.searched==="no");
  check("v1 rows carry no insufficient_evidence key", p.scores.every(r=>!("insufficient_evidence" in r)));
  check("persisted to storage", !!store["solverah_P-01_A"]);
  check("manual button still works", (w.document.getElementById("dlBtn").click(), w.__downloads.length===2)); }

// 4 -- reopen already-submitted
{ const store={}; const d1=boot({store}); const w1=d1.window;
  w1.document.getElementById("startBtn").click();
  w1.eval(`DIMS.forEach(dm=>{const dr=draft(dm.key); dr.quotes=[{text:"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",eid:"A1",sec:"A",src:"noncompany"}]; dr.band=dm.bands[2].value; dr.conf=CONF[1].value; commit(dm.key);});
    state.recognition="no";state.searched="no";save();`);
  w1.document.getElementById("submitBtn").click();
  const d2=boot({store}); const w2=d2.window;
  check("reopen -> locked panel shown", !w2.document.getElementById("donePanel").classList.contains("hidden"));
  check("reopen -> DOWNLOADED pre-set, no false alarm", w2.eval("DOWNLOADED")===true);
  check("reopen -> clock says already submitted", /already submitted/i.test(w2.document.getElementById("clock").textContent));
  check("reopen -> offers re-download", /Download result file/i.test(w2.document.getElementById("dlNote").textContent)); }

// 5 -- mid-session storage failure degrades loudly
{ const store={}; const d=boot({store:new Proxy(store,{})}); const w=d.window;
  w.document.getElementById("startBtn").click();
  w.eval(`STORAGE_OK=true;`);
  Object.defineProperty(w,'localStorage',{configurable:true,value:{setItem(){throw new Error("QuotaExceeded")},getItem:()=>null,removeItem(){}}});
  w.eval("save()");
  const warn=w.document.getElementById("storageWarn");
  check("mid-session save failure -> banner appears", !warn.classList.contains("hidden"));
  check("banner tells them not to refresh", /do not refresh/i.test(warn.textContent)); }

// 6 -- excerpt markup, provenance and selection guards
{ const d=boot({store:{}}); const w=d.window; const doc=w.document;
  const exs=doc.querySelectorAll("#packetText .ex");
  check("packet is marked up into excerpts", exs.length>0, exs.length+" excerpts");
  const srcs=new Set([...exs].map(e=>e.dataset.src));
  check("every excerpt carries a source class", [...exs].every(e=>e.dataset.src&&e.dataset.eid&&e.dataset.sec));
  check("no excerpt is unclassified", !srcs.has("unknown"), [...srcs].join(","));
  check("both company and non-company present in P-01", srcs.has("company")&&srcs.has("noncompany"));
  check("P-01 D section is disputed (company blog, employee byline)",
        [...exs].filter(e=>e.dataset.sec==="D").every(e=>e.dataset.src==="disputed"));
  check("selNote element exists", !!doc.getElementById("selNote"));
  check("tagProv element exists", !!doc.getElementById("tagProv"));
  const ex=exs[0]; const full=ex.textContent;
  const midStart=full.slice(9, 44);            // deliberately starts+ends mid-word
  const snapped=w.eval(`snapToWords(document.querySelectorAll('#packetText .ex')[0], ${JSON.stringify(midStart)})`);
  check("snapToWords grows a mid-word fragment", snapped.length>=midStart.length, JSON.stringify(snapped.slice(0,40)));
  check("snapped text still occurs in the excerpt", full.indexOf(snapped)!==-1);
  check("MIN_CITE guard is 25", w.eval("MIN_CITE")===25);
}

// 7 -- payload records provenance + the 0.7 measurement
{ const store={}; const d=boot({store}); const w=d.window;
  w.document.getElementById("startBtn").click();
  w.eval(`
    const exs=[...document.querySelectorAll('#packetText .ex')];
    const nc=exs.find(e=>e.dataset.src==='noncompany');
    const co=exs.find(e=>e.dataset.src==='company');
    DIMS.forEach((dm,i)=>{ const dr=draft(dm.key);
      const src = (i===0? nc : co);
      dr.quotes=[{text:src.textContent.trim().slice(0,60), eid:src.dataset.eid, sec:src.dataset.sec, src:src.dataset.src}];
      dr.band=dm.bands[2].value; dr.conf=CONF[1].value; commit(dm.key); });
    state.recognition="no"; state.searched="no"; save();`);
  w.document.getElementById("submitBtn").click();
  const p=JSON.parse(w.eval("payload()"));
  const first=p.scores[0], second=p.scores[1];
  check("quotes are objects with eid/sec/src", !!(first.quotes[0].eid&&first.quotes[0].sec&&first.quotes[0].src));
  check("excerpts_cited listed per dimension", Array.isArray(first.excerpts_cited)&&first.excerpts_cited.length===1);
  check("source_mix counted", first.source_mix.noncompany===1);
  check("noncompany_support TRUE where non-company cited", first.noncompany_support===true);
  check("noncompany_support FALSE where only company cited", second.noncompany_support===false);
  check("disputed reported separately, not folded in", second.source_mix.disputed===0);
}

// ======================= insufficient evidence (anchors v3.1) =======================
const openDim=(w,key)=>{ w.document.getElementById("dim_"+key).open=true; };
const insuffLabel=(w,key)=>w.document.querySelector("#dim_"+key+" .band.insuff");

// 8 -- a v1 page never offers the skip
{ const d=boot({store:{}}); const w=d.window;
  w.document.getElementById("startBtn").click();
  check("v1: INSUFF is null", w.eval("INSUFF")===null);
  check("v1: no insufficient-evidence option anywhere", w.document.querySelectorAll(".band.insuff").length===0);
  check("v1: every dimension still asks for a confidence", w.document.querySelectorAll(".noconf").length===0); }

// 9 -- a v3.1 page offers it once per dimension, under its own hash
{ const d=boot({store:{}},V31_HTML); const w=d.window;
  w.document.getElementById("startBtn").click();
  check("v3.1: one option per dimension", w.document.querySelectorAll(".band.insuff").length===6);
  check("v3.1: option shows the rubric's label", /Insufficient evidence/.test(insuffLabel(w,"decision").textContent));
  const h=w.eval("CFG._anchors_hash");
  check("v3.1: its own anchors hash, not v1's", /^[0-9a-f]{12}$/.test(h) && h!=="55c4501b25c5", h);
  check("v3.1: rubric version shown", /v3\.1-PROPOSED/.test(w.eval("state.rubric_version"))); }

// 10 -- skipping by CLICK: no quote, no confidence, commit, locked view
{ const store={}; const d=boot({store},V31_HTML); const w=d.window; const doc=w.document;
  doc.getElementById("startBtn").click(); openDim(w,"decision");
  const btn=()=>doc.getElementById("commit_decision");
  check("before choosing: commit disabled", btn().disabled===true);
  check("before choosing: prompt mentions the skip", /insufficient evidence/i.test(doc.getElementById("err_decision").textContent));
  insuffLabel(w,"decision").click();
  check("click sets the draft to the skip sentinel", w.eval("draft('decision').band")==="insufficient");
  check("confidence block replaced by a note", !!doc.querySelector("#dim_decision .noconf") && !doc.querySelector("#dim_decision .conf"));
  check("evidence hint says quotes are optional", /Optional when recording insufficient evidence/.test(doc.getElementById("cite_decision").textContent));
  check("commit ENABLED with zero quotes and no confidence", btn().disabled===false, doc.getElementById("err_decision").textContent);
  check("dimension stays open after the re-render", doc.getElementById("dim_decision").open===true);
  btn().click();
  const sc=w.eval("state.scores.decision");
  check("committed row: score null", sc.score===null);
  check("committed row: confidence null", sc.confidence===null);
  check("committed row: insufficient_evidence true", sc.insufficient_evidence===true);
  let threw=false; try{ w.eval("renderDim('decision')"); }catch(e){ threw=true; }
  check("committed view renders without toFixed(null) crash", !threw);
  check("committed view says insufficient evidence", /insufficient evidence/i.test(doc.getElementById("dim_decision").textContent));
  check("skip persisted to storage", JSON.parse(store["solverah_P-01_A"]).scores.decision.insufficient_evidence===true); }

// 11 -- changing your mind: skip then a band brings the confidence question back
{ const d=boot({store:{}},V31_HTML); const w=d.window; const doc=w.document;
  doc.getElementById("startBtn").click(); openDim(w,"pace");
  insuffLabel(w,"pace").click();
  doc.querySelector('#dim_pace .band[data-v="0.5"]').click();
  check("band after skip: draft is the number", w.eval("draft('pace').band")===0.5);
  check("band after skip: confidence block back", !!doc.querySelector("#dim_pace .conf") && !doc.querySelector("#dim_pace .noconf"));
  check("band after skip: confidence not carried over", w.eval("draft('pace').conf")===null);
  check("band after skip: commit needs a quote again", doc.getElementById("commit_pace").disabled===true); }

// 12 -- resume: a half-finished skip survives close-and-reopen
{ const store={}; const d1=boot({store},V31_HTML); const w1=d1.window;
  w1.document.getElementById("startBtn").click(); openDim(w1,"feedback");
  insuffLabel(w1,"feedback").click();
  const d2=boot({store},V31_HTML); const w2=d2.window;
  check("resume: button offers to resume", /Resume this sitting/.test(w2.document.getElementById("startBtn").textContent));
  w2.document.getElementById("startBtn").click();
  check("resume: skip draft restored", w2.eval("draft('feedback').band")==="insufficient");
  check("resume: skip option shown chosen", insuffLabel(w2,"feedback").classList.contains("chosen")); }

// 13 -- mixed sitting: five scored, one skipped, submit, payload
{ const store={}; const d=boot({store},V31_HTML); const w=d.window; const doc=w.document;
  doc.getElementById("startBtn").click();
  w.eval(`
    const co=[...document.querySelectorAll('#packetText .ex')].find(e=>e.dataset.src==='company');
    DIMS.filter(dm=>dm.key!=='decision').forEach(dm=>{ const dr=draft(dm.key);
      dr.quotes=[{text:co.textContent.trim().slice(0,60), eid:co.dataset.eid, sec:co.dataset.sec, src:co.dataset.src}];
      dr.band=dm.bands[1].value; dr.conf=CONF[2].value; commit(dm.key); });`);
  openDim(w,"decision"); insuffLabel(w,"decision").click(); doc.getElementById("commit_decision").click();
  check("all six committed with one skip", w.eval("Object.keys(state.scores).length")===6);
  check("final panel shown: a skip counts as done", !doc.getElementById("finalPanel").classList.contains("hidden"));
  w.eval(`state.recognition="no"; state.searched="no"; save();`);
  doc.getElementById("submitBtn").click();
  check("submitted", !!w.eval("state.submitted_at"));
  const p=JSON.parse(w.eval("payload()"));
  const skip=p.scores.find(r=>r.dimension==="decision"), scored=p.scores.filter(r=>r.dimension!=="decision");
  check("payload: 6 rows", p.scores.length===6);
  check("payload skip row: score null, confidence null, flag true",
        skip.score===null && skip.confidence===null && skip.insufficient_evidence===true, JSON.stringify(skip));
  check("payload skip row: empty evidence fields", skip.excerpts_cited.length===0 && skip.noncompany_support===false);
  check("payload scored rows: numbers, no skip key",
        scored.every(r=>typeof r.score==="number" && typeof r.confidence==="number" && !("insufficient_evidence" in r)));
  check("payload carries the v3.1 hash", p.anchors_hash===w.eval("CFG._anchors_hash"));
  check("payload carries the packet file hash (equivalence gate 1)",
        /^[0-9a-f]{64}$/.test(p.packet_sha256) && p.packet_sha256===w.eval("CFG._packet_sha256"), p.packet_sha256);
  if(PAYLOAD_OUT){ fs.writeFileSync(PAYLOAD_OUT, JSON.stringify(p,null,2)+"\n"); }
}

console.log("");
for(const [s,n,e] of R) console.log(`  ${s}  ${n}${e?"   ["+e+"]":""}`);
const f=R.filter(r=>r[0]==="FAIL").length;
console.log(`\n${R.length-f}/${R.length} passed`);
process.exit(f?1:0);
