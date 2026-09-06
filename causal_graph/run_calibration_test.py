"""Floor-bias prompt test: same rubric/packet as run_all_dims_evidence.py, but with
one added calibration instruction, to check whether an explicit nudge moves the three
genuine floor-avoidance cases (P-01/autonomy, P-06/autonomy, P-06/innovation) toward
the bottom band. Only P-01 and P-06 needed (2 calls) -- P-06 covers two of the three
cases in one call since score_packet scores all 6 dimensions per call.

Baseline scores to compare against (from run_all_dims_evidence.py, same anchors):
  P-01 autonomy = 0.3  (human C = 0.1)
  P-06 autonomy = 0.3  (human C = 0.1)
  P-06 innovation = 0.3  (human C = 0.1)
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

CALIBRATION_ADDENDUM = (
    " Calibration note: if the cited evidence is unanimous and clearly one-sided, with no "
    "meaningful countervailing signal, use the most extreme band (0.1 or 0.9) that the evidence "
    "supports -- do not default to a more moderate band as a hedge against unanimous evidence. "
    "Reserve the middle bands (0.3, 0.5, 0.7) for evidence that is genuinely mixed or ambiguous, "
    "not as a general caution."
)

BASELINE = {
    ("P-01", "autonomy"): 0.3,
    ("P-06", "autonomy"): 0.3,
    ("P-06", "innovation"): 0.3,
}


def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)

    anchors = sp.load_anchors()
    rubric = sp.build_rubric_text(anchors)
    print(f"Loaded rubric {anchors.get('rubric_version')} ({len(rubric)} chars)")
    print(f"Calibration addendum length: {len(CALIBRATION_ADDENDUM)} chars\n")

    instruction = (
        "Score the evidence packet against the rubric on these six dimensions: "
        + ", ".join(sp.DIMENSIONS) + ". For each dimension, choose a score from exactly "
        f"these band values: {sp.SCORE_BAND_VALUES}, a confidence from exactly these band "
        f"values: {sp.CONFIDENCE_BAND_VALUES}, and 1-3 short verbatim quotes from the "
        "packet supporting the score. Base your scoring only on the rubric and packet "
        "text provided. Do not use any outside knowledge, web search, or tools, even "
        "if you recognise the company from the evidence." + CALIBRATION_ADDENDUM
    )

    for pk in ["P-01", "P-06"]:
        packet_path = sp.packet_path_for(pk)
        packet_text = sp.load_packet_section1(packet_path)
        messages = [{"role": "user", "content": f"RUBRIC:\n{rubric}\n\nEVIDENCE PACKET:\n{packet_text}\n\n{instruction}"}]
        response, temp_honored = sp.call_with_retry(client, messages, sp.MODEL, sp.TEMPERATURE, sp.REASONING_EFFORT)
        parsed = json.loads(response.choices[0].message.content)

        print("=" * 80)
        print(pk)
        for dim in sp.DIMENSIONS:
            d = parsed[dim]
            flag = ""
            if (pk, dim) in BASELINE:
                base = BASELINE[(pk, dim)]
                flag = f"   <-- baseline was {base}, {'MOVED to ' + str(d['score']) if d['score'] != base else 'UNCHANGED'}"
            print(f"  [{dim}] score={d['score']} confidence={d['confidence']}{flag}")
            for q in d.get("evidence_quotes", []):
                print(f"      \"{q}\"")


if __name__ == "__main__":
    main()
