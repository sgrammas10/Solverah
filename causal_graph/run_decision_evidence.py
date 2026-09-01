"""One-off driver: call score_packet() from scorer_pipeline.py once per packet, using
the patched (v3 decision-anchor) rubric, and print the Decision dimension's score,
confidence, evidence_quotes, and citation-verification result for each. Single call
per packet (6 calls total) -- 5/6 packets were fully deterministic in the prior
variance-test run, so one call per packet is representative; goal here is inspecting
what the model cites, not re-measuring variance.

Run from decision_test/causal_graph/ with SOLVERAH_IP_DIR=../ip_test already set,
same as run_decision_test.ps1.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from openai import OpenAI
import scorer_pipeline as sp

VALID_PACKETS = ["P-01", "P-02", "P-03", "P-04", "P-05", "P-06"]

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("OPENAI_API_KEY not set")

client = OpenAI(api_key=api_key)

anchors = sp.load_anchors()
rubric = sp.build_rubric_text(anchors)
print(f"Loaded rubric {anchors.get('rubric_version')} ({len(rubric)} chars)\n")

for pk in VALID_PACKETS:
    packet_path = sp.packet_path_for(pk)
    packet_text = sp.load_packet_section1(packet_path)
    packet_version = sp.packet_version_for(packet_path)

    result = sp.score_packet(
        client, packet_text, rubric,
        packet_id=pk, rubric_version=anchors.get("rubric_version", "?"),
        packet_version=packet_version,
    )
    checks = sp.verify_result(result, packet_text)

    dec = next(d for d in result.dimensions if d.dimension == "decision")
    dec_checks = [c for c in checks if c.dimension == "decision"]

    print("=" * 80)
    print(f"{pk}  decision score={dec.score}  confidence={dec.confidence}")
    for i, q in enumerate(dec.evidence_quotes, 1):
        match = next((c for c in dec_checks if c.quote == q), None)
        status = f"VERIFIED (eid={match.matched_eid}, source={match.source_tag})" if match and match.matched else "**NOT VERIFIED / NOT FOUND IN PACKET**"
        print(f"  quote {i}: {status}")
        print(f"    \"{q}\"")
    print()
