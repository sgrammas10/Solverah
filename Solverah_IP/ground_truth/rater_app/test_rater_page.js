const {JSDOM}=require('jsdom'); const fs=require('fs');
const html=fs.readFileSync('/tmp/t2/P-01_raterA.html','utf8');
function boot(opts={}){
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

// 1 — storage present
{ const d=boot({store:{}}); const w=d.window;
  check("storage OK → banner hidden", w.document.getElementById("storageWarn").classList.contains("hidden"));
  check("STORAGE_OK true", w.eval("STORAGE_OK")===true); }

// 2 — storage denied
{ const d=boot({killStorage:true}); const w=d.window;
  const warn=w.document.getElementById("storageWarn");
  check("storage denied → banner VISIBLE", !warn.classList.contains("hidden"));
  check("banner says work can be lost", /lose everything/i.test(warn.textContent));
  check("STORAGE_OK false", w.eval("STORAGE_OK")===false);
  check("page still startable", !!w.document.getElementById("startBtn"));
  let threw=false; try{ w.eval("save()"); }catch(e){ threw=true; }
  check("save() does not throw when storage denied", !threw); }

// 3 — full run + auto-download
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
  check("payload anchors_hash", p.anchors_hash==="55c4501b25c5", p.anchors_hash);
  check("payload 6 scores", (p.scores||[]).length===6);
  check("payload identifies packet+rater", p.packet_id==="P-01"&&p.rater==="A");
  check("payload carries recognition + searched", p.recognition==="no"&&p.searched==="no");
  check("persisted to storage", !!store["solverah_P-01_A"]);
  check("manual button still works", (w.document.getElementById("dlBtn").click(), w.__downloads.length===2)); }

// 4 — reopen already-submitted
{ const store={}; const d1=boot({store}); const w1=d1.window;
  w1.document.getElementById("startBtn").click();
  w1.eval(`DIMS.forEach(dm=>{const dr=draft(dm.key); dr.quotes=[{text:"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",eid:"A1",sec:"A",src:"noncompany"}]; dr.band=dm.bands[2].value; dr.conf=CONF[1].value; commit(dm.key);});
    state.recognition="no";state.searched="no";save();`);
  w1.document.getElementById("submitBtn").click();
  const d2=boot({store}); const w2=d2.window;
  check("reopen → locked panel shown", !w2.document.getElementById("donePanel").classList.contains("hidden"));
  check("reopen → DOWNLOADED pre-set, no false alarm", w2.eval("DOWNLOADED")===true);
  check("reopen → clock says already submitted", /already submitted/i.test(w2.document.getElementById("clock").textContent));
  check("reopen → offers re-download", /Download result file/i.test(w2.document.getElementById("dlNote").textContent)); }

// 5 — mid-session storage failure degrades loudly
{ const store={}; let n=0; const d=boot({store:new Proxy(store,{})}); const w=d.window;
  w.document.getElementById("startBtn").click();
  w.eval(`STORAGE_OK=true;`);
  Object.defineProperty(w,'localStorage',{configurable:true,value:{setItem(){throw new Error("QuotaExceeded")},getItem:()=>null,removeItem(){}}});
  w.eval("save()");
  const warn=w.document.getElementById("storageWarn");
  check("mid-session save failure → banner appears", !warn.classList.contains("hidden"));
  check("banner tells them not to refresh", /do not refresh/i.test(warn.textContent)); }


// ---- 6. excerpt markup, provenance and selection guards ----
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
  // word snapping
  const snap=w.eval("snapToWords");
  const ex=exs[0]; const full=ex.textContent;
  const midStart=full.slice(9, 44);            // deliberately starts+ends mid-word
  const snapped=w.eval(`snapToWords(document.querySelectorAll('#packetText .ex')[0], ${JSON.stringify(midStart)})`);
  check("snapToWords grows a mid-word fragment", snapped.length>=midStart.length, JSON.stringify(snapped.slice(0,40)));
  check("snapped text still occurs in the excerpt", full.indexOf(snapped)!==-1);
  check("MIN_CITE guard is 25", w.eval("MIN_CITE")===25);
}

// ---- 7. payload records provenance + the 0.7 measurement ----
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

console.log("");
for(const [s,n,e] of R) console.log(`  ${s}  ${n}${e?"   ["+e+"]":""}`);
const f=R.filter(r=>r[0]==="FAIL").length;
console.log(`\n${R.length-f}/${R.length} passed`);
process.exit(f?1:0);
