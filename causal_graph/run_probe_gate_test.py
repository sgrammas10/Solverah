"""GATING TEST for extremity_flag.py -- run this before trusting the flag.

The floor-bias workaround rests on one untested hypothesis: that the model's
refusal to assign the 0.1 band attaches to RATING AN EMPLOYER, not to classifying
an isolated text fragment against a description. If that's right, a binary
company-agnostic membership probe escapes the reluctance and can supply the
bottom-end signal the score field can't. If it's wrong, this approach is dead too.

This costs ONE API call. It feeds the probe three quotes that match the autonomy
0.1 band almost verbatim (that band's own text says "reviews cite micromanagement
or rigid procedure") plus two clear non-matches as controls.

A FAIL is a real finding about the model. Record it; do not loosen the test.

Run from decision_test/causal_graph/ with SOLVERAH_IP_DIR=../ip_test set.
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
from extremity_flag import LLMBandProbe, validate_probe_escapes_reluctance

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("OPENAI_API_KEY not set")

client = OpenAI(api_key=api_key)
anchors = sp.load_anchors()
print(f"Loaded anchors {anchors.get('rubric_version')}\n")

probe = LLMBandProbe(client, anchors, model=sp.MODEL, reasoning_effort=sp.REASONING_EFFORT)
report = validate_probe_escapes_reluctance(probe)

print("=" * 78)
print("SHOULD be classified as matching the 0.1 'Directed' band:")
for q, got in report["expected_true"].items():
    mark = "ok " if got is True else "MISS"
    print(f"  [{mark}] got={got}   \"{q}\"")

print("\nSHOULD be classified as NOT matching (controls):")
for q, got in report["expected_false"].items():
    mark = "ok " if got is False else "MISS"
    print(f"  [{mark}] got={got}   \"{q}\"")

print("\n" + "=" * 78)
print(f"RESULT: {'PASS' if report['passed'] else 'FAIL'}")
print(report["interpretation"])
print("=" * 78)

out = Path(__file__).resolve().parent / "results" / "probe_gate_test.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nWrote {out}")
