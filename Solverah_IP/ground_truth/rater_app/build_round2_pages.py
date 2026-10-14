"""
build_round2_pages.py -- every round-2 rater page, scrub gate first (PREREG_ROUND2 addendum A2).

For each packet in P-07..P-19 that is in anonymization/ AND passes Scripts/verify_scrub.py today:
  * Sebastian's page -> out/round2/P-XX_raterD.html
  * Julie's page     -> out/round2/for_julie/NN_P-XX_raterA.html, NN = its place in JULIE_ORDER,
    so her folder lists in the order she is asked to work in.
A packet that is missing, or fails the gate, gets no page and is listed as skipped. Rebuilding a
page from an unchanged packet and rubric gives identical bytes.

    python Solverah_IP/ground_truth/rater_app/build_round2_pages.py

Every print is ASCII.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ANON = HERE.parent / "anonymization"
ANCHORS_V31 = HERE / "anchors_v3_1_PROPOSED.json"
OUT = HERE / "out" / "round2"
JULIE_DIR = OUT / "for_julie"

ROUND2_PACKETS = [f"P-{n:02d}" for n in range(7, 20)]

# A2.2: Julie's A1.3 draws first, then the other eleven shuffled. Pinned as a literal so it
# cannot drift; test_build_round2_pages re-derives it from the seed.
JULIE_SEED = 20261001
JULIE_ORDER = ["P-11", "P-10", "P-19", "P-09", "P-17", "P-08", "P-13",
               "P-07", "P-16", "P-15", "P-18", "P-14", "P-12"]


def julie_page_name(pid: str) -> str:
    return f"{JULIE_ORDER.index(pid) + 1:02d}_{pid}_raterA.html"


def _verify_scrub(pid: str) -> bool:
    # Imported here, not at module top: round2_analysis imports JULIE_ORDER from this file and
    # must not pull in the scorer (and openai) to do it.
    sys.path.insert(0, str(REPO / "causal_graph"))
    from run_round2_scoring import verify_scrub
    return verify_scrub(pid)


def buildable(packets=ROUND2_PACKETS, *, anon_dir: Path = ANON, verify=_verify_scrub):
    """-> (packets to build, {packet: reason skipped})."""
    ok, skipped = [], {}
    for pid in packets:
        if not (anon_dir / f"{pid}_packet_ANON.txt").is_file():
            skipped[pid] = "not in anonymization/ yet"
        elif not verify(pid):
            skipped[pid] = "verify_scrub did not PASS"
        else:
            ok.append(pid)
    return ok, skipped


def _build(pid: str, rater: str, out_dir: Path) -> Path:
    subprocess.run([sys.executable, str(HERE / "build_rater_page.py"),
                    "--packet", str(ANON / f"{pid}_packet_ANON.txt"), "--packet-id", pid,
                    "--rater", rater, "--anchors", str(ANCHORS_V31), "--out", str(out_dir)],
                   check=True)
    return out_dir / f"{pid}_rater{rater}.html"


def main() -> int:
    ok, skipped = buildable()
    for pid in ok:
        _build(pid, "D", OUT)
        built = _build(pid, "A", JULIE_DIR)
        built.replace(JULIE_DIR / julie_page_name(pid))
    print(f"built: {', '.join(ok) or 'none'}")
    for pid, why in skipped.items():
        print(f"skipped {pid}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
