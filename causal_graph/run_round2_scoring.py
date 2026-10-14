"""
run_round2_scoring.py -- the round-2 LLM runs, three draws per packet, under anchors v3.1.

PREREG_ROUND2_2026-09-29.md section 3 + addendum A1. DRY RUN BY DEFAULT: it checks every gate
and prints the call count and a token estimate, and spends nothing. A live run needs BOTH
`--live` AND `SOLVERAH_ALLOW_LIVE_CALLS=1`, and each packet must still pass every gate:

  1. Scripts/verify_scrub.py PASSES for the packet today.
  2. Rater D (Sebastian) has submitted it: returned/round2/*.json holds a D reading for it.
     The LLM never runs on a packet the reference has not finished (A1.6 gate 6).
  3. That reading was taken on THIS packet file: its packet_sha256 matches (gate 1).

Output: one JSON per draw in Solverah_IP/analysis_s58/results/round2/<packet>_draw<n>.json,
the input round2_analysis.py reads. Existing draw files are never overwritten.

    python causal_graph/run_round2_scoring.py P-07 P-11            # dry run
    SOLVERAH_ALLOW_LIVE_CALLS=1 python causal_graph/run_round2_scoring.py P-07 --live

Named so it matches no pytest pattern, and guarded by main(): importing it calls nothing.
Every print is ASCII.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scorer_pipeline as sp  # noqa: E402

REPO = HERE.parent
RATER_APP = sp.REPO_IP / "ground_truth" / "rater_app"
ANCHORS_V31 = RATER_APP / "anchors_v3_1_PROPOSED.json"
RETURNED = RATER_APP / "returned" / "round2"
OUT = sp.REPO_IP / "analysis_s58" / "results" / "round2"
DRAWS = 3  # D-21
REFERENCE = "D"

# Company names for verify_scrub's identifier check. Extend as P-14..P-19 are harvested.
ROUND2_COMPANIES: dict[str, list[str]] = {
    "P-07": ["Cummins"],
    "P-08": ["DigitalOcean", "Digital Ocean"],
    "P-09": ["Warby Parker", "Warby"],
    "P-10": ["Twilio"],
    "P-11": ["Regeneron", "Regeneron Pharmaceuticals", "REGN"],
    "P-12": ["Duke Energy", "Duke Energy Corporation"],
    "P-13": ["Schneider National", "Schneider"],
}


def packet_sha256(path: Path) -> str:
    """Must equal build_rater_page.packet_sha256 -- the rater page records this for gate 1."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def anchors_hash(cfg: dict) -> str:
    """Must equal build_rater_page's _anchors_hash for the same anchors file."""
    blob = json.dumps({k: v for k, v in cfg.items() if not k.startswith("_")},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def verify_scrub(pid: str) -> bool:
    names = ROUND2_COMPANIES.get(pid)
    if not names:
        return False
    cmd = [sys.executable, str(REPO / "Scripts" / "verify_scrub.py"), pid]
    for n in names:
        cmd += ["--company", n]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace").returncode == 0


def reference_reading(pid: str, returned: Path) -> dict | None:
    if not returned.is_dir():
        return None
    for p in sorted(returned.glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        if doc.get("packet_id") == pid and doc.get("rater") == REFERENCE:
            return doc
    return None


def plan(packets: list[str], *, returned: Path = RETURNED, verify=verify_scrub,
         anchors_path: Path = ANCHORS_V31) -> tuple[list[dict], dict]:
    """Check every gate for every packet. Spends nothing. -> (per-packet plan, anchors)."""
    anchors = sp.load_anchors(anchors_path)
    rubric = sp.build_rubric_text(anchors)
    rows = []
    for pid in packets:
        reasons: list[str] = []
        path = sp.packet_path_for(pid) if pid in sp.VALID_PACKETS + sp.ROUND2_PACKETS else None
        if pid not in sp.ROUND2_PACKETS:
            reasons.append("not a round-2 packet")
        elif not path.exists():
            reasons.append(f"{path.name} not in anonymization/ yet")
        else:
            if not verify(pid):
                reasons.append("verify_scrub did not PASS today")
            d = reference_reading(pid, returned)
            if d is None:
                reasons.append("rater D has not submitted this packet")
            elif d.get("packet_sha256") != packet_sha256(path):
                reasons.append("rater D's packet_sha256 does not match this packet file")
        est = 0
        if not reasons:
            section1 = sp.load_packet_section1(path)
            est = (len(rubric) + len(section1) + 900) // 4   # ~4 chars/token, + instruction
        rows.append({"packet_id": pid, "ok": not reasons, "reasons": reasons,
                     "est_input_tokens_per_call": est})
    return rows, anchors


def run_live(client, rows: list[dict], anchors: dict, *, out: Path = OUT,
             draws: int = DRAWS) -> list[Path]:
    """Score every OK packet `draws` times. Refuses to overwrite a draw file."""
    rubric = sp.build_rubric_text(anchors)
    allow = sp.permits_insufficient_evidence(anchors)
    ahash = anchors_hash(anchors)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for row in (r for r in rows if r["ok"]):
        pid = row["packet_id"]
        path = sp.packet_path_for(pid)
        targets = [out / f"{pid}_draw{n}.json" for n in range(1, draws + 1)]
        clash = [t.name for t in targets if t.exists()]
        if clash:
            raise FileExistsError(f"{pid}: draw files already exist {clash}; round-2 data is append-only")
        section1 = sp.load_packet_section1(path)
        for n, target in enumerate(targets, 1):
            result = sp.score_packet(
                client, section1, rubric, packet_id=pid, rubric_version=anchors["rubric_version"],
                packet_version=sp.packet_version_for(path), allow_insufficient_evidence=allow)
            checks = sp.verify_result(result, section1)
            target.write_text(json.dumps({
                "packet_id": pid, "draw": n,
                "run_at": datetime.now(timezone.utc).isoformat(),
                "model": result.model, "reasoning_effort": result.reasoning_effort,
                "temperature_honored": result.temperature_honored,
                "rubric_version": anchors["rubric_version"], "anchors_hash": ahash,
                "packet_sha256": packet_sha256(path), "packet_version": result.packet_version,
                "result": result.to_dict(),
                "citations": [{"dimension": c.dimension, "quote": c.quote, "matched": c.matched,
                               "matched_eid": c.matched_eid, "source_tag": c.source_tag}
                              for c in checks],
            }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            written.append(target)
            print(f"  wrote {target.name}")
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packets", nargs="+")
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args(argv)

    rows, anchors = plan(a.packets)
    ok = [r for r in rows if r["ok"]]
    for r in rows:
        status = "READY" if r["ok"] else "REFUSED: " + "; ".join(r["reasons"])
        print(f"{r['packet_id']}: {status}")
    tokens = sum(r["est_input_tokens_per_call"] for r in ok) * DRAWS
    print(f"\n{len(ok)} packet(s) ready -> {len(ok) * DRAWS} calls "
          f"(~{tokens:,} input tokens, plus output incl. reasoning), "
          f"rubric {anchors['rubric_version']}")
    if not a.live:
        print("DRY RUN -- nothing was sent. Re-run with --live and SOLVERAH_ALLOW_LIVE_CALLS=1.")
        return 0
    if os.environ.get("SOLVERAH_ALLOW_LIVE_CALLS") != "1":
        print("REFUSED: --live needs SOLVERAH_ALLOW_LIVE_CALLS=1 as well.")
        return 2
    if not ok:
        return 1
    from dotenv import load_dotenv   # the OpenAI key only; nothing here touches a database
    from openai import OpenAI
    load_dotenv(REPO / ".env", override=False)
    run_live(OpenAI(), rows, anchors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
