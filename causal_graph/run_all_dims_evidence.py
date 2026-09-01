"""Extended version of run_decision_evidence.py: call score_packet() once per packet
(6 calls total, same as before) but print+save EVERY dimension's score, confidence,
and evidence_quotes with citation verification -- not just decision. Also writes a
JSON file so follow-up questions about any dimension don't require new API calls.

Run from decision_test/causal_graph/ with SOLVERAH_IP_DIR=../ip_test already set,
same as run_decision_evidence.py / run_decision_test.ps1.
"""
import json
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

all_results = {}

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

    print("=" * 80)
    print(f"{pk}")
    pk_out = []
    for dim in result.dimensions:
        dim_checks = [c for c in checks if c.dimension == dim.dimension]
        print(f"\n  [{dim.dimension}]  score={dim.score}  confidence={dim.confidence}")
        quotes_out = []
        for i, q in enumerate(dim.evidence_quotes, 1):
            match = next((c for c in dim_checks if c.quote == q), None)
            status = f"VERIFIED (eid={match.matched_eid}, source={match.source_tag})" if match and match.matched else "**NOT VERIFIED**"
            print(f"    quote {i}: {status}")
            print(f"      \"{q}\"")
            quotes_out.append({
                "quote": q,
                "verified": bool(match and match.matched),
                "eid": match.matched_eid if match else None,
                "source_tag": match.source_tag if match else None,
            })
        pk_out.append({
            "dimension": dim.dimension, "score": dim.score, "confidence": dim.confidence,
            "quotes": quotes_out,
        })
    all_results[pk] = pk_out
    print()

out_path = Path(__file__).resolve().parent / "results" / "all_dims_evidence_2026-09-01.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
print(f"\nWrote {out_path}")
