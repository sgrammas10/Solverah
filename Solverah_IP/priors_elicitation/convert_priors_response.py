#!/usr/bin/env python3
"""Convert Julie's returned elicitation JSON into a priors.yaml the model can load.

    python convert_priors_response.py solverah_priors_julie.json
    python convert_priors_response.py solverah_priors_julie.json --out priors_elicited.yaml

Writes `priors_elicited.yaml` next to the input and prints a report. It NEVER
overwrites `causal_graph/v1_model/priors.yaml` -- adopting the elicited values is a
deliberate copy, not a side effect of running this. `solverah_model_config.yaml` says
"swap that file when the expert delivers real values"; swapping is the operator's move.

Standard library only, on purpose: this has to run in whatever interpreter is to hand.

------------------------------------------------------------------------------
THE ARITHMETIC, stated so it can be checked rather than trusted
------------------------------------------------------------------------------
The model's linear predictor (match_core.outcome_logit) is

    z = intercept + sum_d [ mag_d * |g_d| + dir_d * g_d ] + sum_c w_c * conf_c
    P(fit) = sigmoid(z),   g_d = person_d - env_d

The instrument asks two questions per dimension, both at a pole-vs-pole mismatch:

    "above"  person at the high pole, role at the low pole   -> g = +0.8
    "below"  person at the low pole,  role at the high pole  -> g = -0.8

|g| = 0.8 in both cases because a person's ladder value snaps to COMPANY_LATTICE
before the gap is taken (match_core.closest_achievable), and that lattice tops out at
0.9 and bottoms at 0.1 -- so pole against opposite pole is always 0.8 apart, never 1.0.
That snap is the pole-penalty fix; without it these two questions would not share a
common |g| and this conversion would be wrong.

    z_above = intercept + 0.8*mag + 0.8*dir
    z_below = intercept + 0.8*mag - 0.8*dir

Two equations, two unknowns, exactly determined:

    mag = (z_above + z_below - 2*intercept) / 1.6
    dir = (z_above - z_below) / 1.6

`mag` should come out NEGATIVE (mismatch lowers the odds). A positive `mag` means the
answers say a mismatch *helps*, which is almost always a misread question rather than a
finding -- it is flagged, not silently written.

`dir` is the asymmetry. Positive `dir` means wanting MORE than the role offers is the
survivable direction; negative means wanting LESS is. Zero means the two directions cost
the same, which is what the placeholder file currently assumes for all six.

Every conversion is round-tripped back to probabilities before anything is written. If
the recovered parameters do not reproduce her answers, this exits non-zero rather than
emitting a file.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

# Pole-vs-pole gap. Derived from match_core: PERSON_LATTICE snapped onto COMPANY_LATTICE,
# whose extremes are 0.1 and 0.9. Not a tunable -- if the lattices change, this changes.
GAP = 0.8

# Confounder standardisation, from solverah_model_config.yaml's `scale` blocks. The
# instrument asks about the extremes of each raw scale (stage index 1..5, comp band 1..5).
CONFOUNDER_SCALES = {
    "stage_size": {"mean": 3.0, "sd": 1.5, "high_raw": 5.0, "low_raw": 1.0,
                   "high_key": "large", "low_key": "small"},
    "comp": {"mean": 3.0, "sd": 1.0, "high_raw": 5.0, "low_raw": 1.0,
             "high_key": "above_market", "low_key": "below_market"},
}

# How a stated confidence becomes a prior sd on the LOGIT of one answer. These are
# judgement calls and they are meant to be argued with -- they are the one place in this
# script where a number is not derived from something she said.
#
#   confident -> she would stand behind it; still not a measurement
#   fairly    -> the default posture
#   unsure    -> wide enough that a modest amount of outcome data dominates it
#   abstain   -> her means are NOT used at all; the neutral placeholder is kept
CONFIDENCE_SD_Z = {
    "confident": 0.35,
    "fairly": 0.70,
    "unsure": 1.20,
    None: 0.70,
}
ABSTAIN_SD = 1.50          # on the parameter, not the logit -- deliberately wide
CONFOUNDER_SD_DEFAULT = 0.50   # no per-confounder confidence question is asked
SD_FLOOR, SD_CEIL = 0.15, 2.00

PLACEHOLDER_MAG = -1.0     # what priors.yaml currently carries, kept for abstentions
PLACEHOLDER_DIR = 0.0

DIMENSION_ORDER = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]


class ConversionError(RuntimeError):
    pass


def logit(p: float) -> float:
    p = min(max(p, 0.02), 0.98)   # 0/10 and 10/10 are real answers; infinities are not
    return math.log(p / (1.0 - p))


def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def out_of_10(entry, label: str):
    """Pull the 0-10 count from one answer object. Returns None if unanswered."""
    if not isinstance(entry, dict):
        raise ConversionError("%s: expected an answer object, got %r" % (label, entry))
    v = entry.get("out_of_10")
    if v is None:
        return None
    if not isinstance(v, (int, float)) or not (0 <= v <= 10):
        raise ConversionError("%s: %r is not a count out of 10" % (label, v))
    return float(v) / 10.0


def sd_from_range(entry) -> float | None:
    """A stated plausible range, read as a ~95% interval, becomes an sd on the logit."""
    if not isinstance(entry, dict):
        return None
    r = entry.get("range")
    if not r or len(r) != 2 or r[0] is None or r[1] is None:
        return None
    lo, hi = sorted((float(r[0]) / 10.0, float(r[1]) / 10.0))
    if hi <= lo:
        return None
    return (logit(hi) - logit(lo)) / 4.0


def convert(doc: dict) -> dict:
    base_p = out_of_10(doc.get("baseline", {}), "baseline")
    if base_p is None:
        raise ConversionError(
            "The baseline question is unanswered. Every other number is measured against "
            "it, so nothing can be converted without it."
        )
    intercept = logit(base_p)

    result = {
        "intercept": {"mean": round(intercept, 6), "sd": 1.0},
        "dimensions": {},
        "confounders": {},
        "report": [],
        "warnings": [],
        "baseline_p": base_p,
    }

    dims = doc.get("dimensions", {}) or {}
    for key in DIMENSION_ORDER:
        block = dims.get(key)
        if not block:
            result["dimensions"][key] = placeholder(key, "no answers returned")
            result["warnings"].append("%s: no answers returned -- placeholder kept" % key)
            continue

        confidence = block.get("confidence")
        if confidence == "abstain":
            result["dimensions"][key] = placeholder(key, "declined to estimate")
            result["report"].append({
                "key": key, "status": "abstained",
                "note": block.get("note", ""),
            })
            continue

        p_above = out_of_10(block.get("above", {}), key + ".above")
        p_below = out_of_10(block.get("below", {}), key + ".below")
        if p_above is None or p_below is None:
            result["dimensions"][key] = placeholder(key, "incomplete")
            result["warnings"].append(
                "%s: only %s of 2 scenarios answered -- placeholder kept"
                % (key, sum(x is not None for x in (p_above, p_below)))
            )
            continue

        z_above, z_below = logit(p_above), logit(p_below)
        mag = (z_above + z_below - 2 * intercept) / (2 * GAP)
        direction = (z_above - z_below) / (2 * GAP)

        # Round-trip: the recovered parameters must reproduce her two answers exactly.
        check_above = sigmoid(intercept + mag * GAP + direction * GAP)
        check_below = sigmoid(intercept + mag * GAP - direction * GAP)
        for got, want, which in ((check_above, p_above, "above"), (check_below, p_below, "below")):
            if abs(got - clamp01(want)) > 1e-9:
                raise ConversionError(
                    "%s.%s failed round-trip: recovered %.12f from an answer of %.12f. "
                    "The algebra in this file does not match match_core.outcome_logit."
                    % (key, which, got, clamp01(want))
                )

        sd_a = sd_from_range(block.get("above")) or CONFIDENCE_SD_Z.get(confidence, 0.70)
        sd_b = sd_from_range(block.get("below")) or CONFIDENCE_SD_Z.get(confidence, 0.70)
        sd_param = clamp_sd(math.sqrt(sd_a ** 2 + sd_b ** 2) / (2 * GAP))

        result["dimensions"][key] = {
            "mag": {"mean": round(mag, 6), "sd": round(sd_param, 6)},
            "dir": {"mean": round(direction, 6), "sd": round(sd_param, 6)},
        }
        result["report"].append({
            "key": key, "status": "elicited",
            "p_above": p_above, "p_below": p_below,
            "mag": mag, "dir": direction, "sd": sd_param,
            "confidence": confidence, "note": block.get("note", ""),
        })

        if mag > 0:
            result["warnings"].append(
                "%s: mag is POSITIVE (%.3f) -- these answers say a mismatch on this "
                "dimension IMPROVES the odds. Check the question was read as intended "
                "before adopting this." % (key, mag)
            )

    conf_in = doc.get("confounders", {}) or {}
    for ckey, scale in CONFOUNDER_SCALES.items():
        block = conf_in.get(ckey) or {}
        p_hi = out_of_10(block.get(scale["high_key"], {}), ckey + "." + scale["high_key"]) \
            if block.get(scale["high_key"]) else None
        p_lo = out_of_10(block.get(scale["low_key"], {}), ckey + "." + scale["low_key"]) \
            if block.get(scale["low_key"]) else None
        if p_hi is None or p_lo is None:
            result["confounders"][ckey] = {"mean": 0.0, "sd": 1.0}
            result["warnings"].append("%s: unanswered -- neutral placeholder kept" % ckey)
            continue
        span = (scale["high_raw"] - scale["mean"]) / scale["sd"] \
             - (scale["low_raw"] - scale["mean"]) / scale["sd"]
        w = (logit(p_hi) - logit(p_lo)) / span
        result["confounders"][ckey] = {"mean": round(w, 6), "sd": CONFOUNDER_SD_DEFAULT}
        result["report"].append({
            "key": ckey, "status": "confounder",
            "p_high": p_hi, "p_low": p_lo, "weight": w,
        })

    # industry stays neutral in the mean either way; what her answer moves is how much
    # room the prior leaves for data to speak.
    industry_sd = {"yes": 1.0, "a_little": 0.7, "no": 0.3, "unsure": 1.0}.get(
        conf_in.get("industry_matters"), 1.0)
    result["confounders"]["industry"] = {"mean": 0.0, "sd": industry_sd}
    result["industry_answer"] = conf_in.get("industry_matters")

    # consistency re-ask
    rc = doc.get("recheck") or {}
    rc_p = out_of_10(rc.get("answer", {}), "recheck") if rc.get("answer") else None
    if rc_p is not None and rc.get("dimension"):
        orig_block = dims.get(rc["dimension"], {}) or {}
        orig = out_of_10(orig_block.get(rc.get("scenario", "above"), {}), "recheck.original") \
            if orig_block.get(rc.get("scenario", "above")) else None
        if orig is not None:
            result["recheck"] = {
                "dimension": rc["dimension"], "scenario": rc.get("scenario"),
                "first": orig, "second": rc_p, "delta_out_of_10": abs(orig - rc_p) * 10,
            }
    return result


def clamp01(p):
    return min(max(p, 0.02), 0.98)


def clamp_sd(sd):
    return min(max(sd, SD_FLOOR), SD_CEIL)


def placeholder(key, why):
    return {
        "mag": {"mean": PLACEHOLDER_MAG, "sd": ABSTAIN_SD},
        "dir": {"mean": PLACEHOLDER_DIR, "sd": ABSTAIN_SD},
        "_placeholder_reason": why,
    }


def emit_yaml(res: dict, source: Path) -> str:
    """Hand-formatted so the provenance comments survive. priors.yaml is a document as
    much as a config; a dumper would flatten the reasoning out of it."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    L = []
    L.append("# priors.yaml -- ELICITED VALUES.")
    L.append("# Generated by priors_elicitation/convert_priors_response.py on %s" % stamp)
    L.append("# Source: %s" % source.name)
    L.append("#")
    L.append("# These are one domain expert's judgement converted to logit-scale weights,")
    L.append("# NOT a measurement. Every `mean` traces to an answer of the form 'out of ten")
    L.append("# people like this, how many are still doing well a year later'; every `sd`")
    L.append("# traces to a stated confidence or plausible range. The conversion is")
    L.append("# documented and round-trip-checked in convert_priors_response.py.")
    L.append("#")
    L.append("# Baseline: a well-matched person was put at %.0f in 10 -> intercept %.6f"
             % (res["baseline_p"] * 10, res["intercept"]["mean"]))
    L.append("#")
    L.append("# mag < 0 : a mismatch on this dimension lowers the odds")
    L.append("# dir > 0 : wanting MORE than the role offers is the cheaper direction to be wrong in")
    L.append("# dir < 0 : wanting LESS than the role offers is the cheaper direction")
    if res["warnings"]:
        L.append("#")
        L.append("# WARNINGS AT GENERATION TIME:")
        for w in res["warnings"]:
            L.append("#   - %s" % w)
    L.append("")
    ic = res["intercept"]
    L.append("intercept: { mean: %.6f, sd: %.6f }" % (ic["mean"], ic["sd"]))
    L.append("")
    L.append("dimensions:")
    width = max(len(k) for k in DIMENSION_ORDER) + 1
    for key in DIMENSION_ORDER:
        d = res["dimensions"][key]
        line = "  %-*s { mag: {mean: %.6f, sd: %.6f}, dir: {mean: %.6f, sd: %.6f} }" % (
            width, key + ":",
            d["mag"]["mean"], d["mag"]["sd"], d["dir"]["mean"], d["dir"]["sd"])
        if "_placeholder_reason" in d:
            line += "   # PLACEHOLDER -- %s" % d["_placeholder_reason"]
        L.append(line)
    L.append("  # structure / orientation added here when toggled active")
    L.append("")
    L.append("confounders:")
    for ckey in ("stage_size", "comp", "industry"):
        c = res["confounders"][ckey]
        L.append("  %-12s { mean: %.6f, sd: %.6f }" % (ckey + ":", c["mean"], c["sd"]))
    L.append("  # prestige added here when toggled active")
    L.append("")
    return "\n".join(L)


def print_report(res: dict) -> None:
    p = print
    p("")
    p("BASELINE")
    p("  A well-matched person: %.0f in 10 still doing well at a year (intercept %.3f)"
      % (res["baseline_p"] * 10, res["intercept"]["mean"]))
    p("")
    p("DIMENSIONS -- what she said, and what it becomes")
    p("  %-14s %7s %7s %9s %9s  %s" % ("dimension", "above", "below", "mag", "dir", "confidence"))
    for row in res["report"]:
        if row["status"] == "elicited":
            p("  %-14s %6.0f/10 %6.0f/10 %9.3f %9.3f  %s"
              % (row["key"], row["p_above"] * 10, row["p_below"] * 10,
                 row["mag"], row["dir"], row.get("confidence") or "-"))
        elif row["status"] == "abstained":
            p("  %-14s %7s %7s %9s %9s  declined -- placeholder kept"
              % (row["key"], "-", "-", "-", "-"))
    p("")
    p("READ IN PLAIN LANGUAGE")
    elicited = [r for r in res["report"] if r["status"] == "elicited"]
    if elicited:
        worst = min(elicited, key=lambda r: r["mag"])
        mildest = max(elicited, key=lambda r: r["mag"])
        p("  Most costly mismatch:  %s" % worst["key"])
        p("  Least costly mismatch: %s" % mildest["key"])
        ratio = worst["mag"] / mildest["mag"] if mildest["mag"] else float("nan")
        p("  Spread: a mismatch on %s costs about %.1fx a mismatch on %s."
          % (worst["key"], ratio, mildest["key"]))
        p("  (The current placeholder file says that ratio is exactly 1.0 for all six.)")
        p("")
        for r in sorted(elicited, key=lambda r: r["dir"]):
            if abs(r["dir"]) < 0.05:
                verdict = "no real difference between the two directions"
            elif r["dir"] > 0:
                verdict = "wanting MORE than the role offers is the survivable direction"
            else:
                verdict = "wanting LESS than the role offers is the survivable direction"
            p("  %-14s %s" % (r["key"], verdict))
    for row in res["report"]:
        if row["status"] == "confounder":
            p("")
            p("  %-12s %.0f/10 at the high end vs %.0f/10 at the low end -> weight %.3f"
              % (row["key"], row["p_high"] * 10, row["p_low"] * 10, row["weight"]))
    if res.get("industry_answer"):
        p("  %-12s answered '%s'" % ("industry", res["industry_answer"]))

    if "recheck" in res:
        rc = res["recheck"]
        p("")
        p("CONSISTENCY CHECK (the repeated question, unflagged to her)")
        p("  %s/%s asked twice: %.0f/10 then %.0f/10 -- %.0f apart."
          % (rc["dimension"], rc["scenario"], rc["first"] * 10, rc["second"] * 10,
             rc["delta_out_of_10"]))
        # priors_elicitation_v1's re-ask is NOT an equivalent rewording: the original
        # person is "at their best when priorities move quickly" (a need), the re-ask
        # person "doesn't mind the target moving" (a tolerance). A gap between the two
        # is an answer to a different question, so it is reported and never read as
        # noise. See README, "Known defect: the re-ask".
        if rc["delta_out_of_10"] >= 2:
            p("  NOT a noise read on this form version: the re-ask vignette softens the")
            p("  person's preference from a need to a tolerance, so the two answers")
            p("  describe different people. No noise floor is available from v1.")
        else:
            p("  Close, though v1's re-ask is not an exact repeat (see README).")

    if res["warnings"]:
        p("")
        p("WARNINGS")
        for w in res["warnings"]:
            p("  ! %s" % w)

    notes = [(r["key"], r["note"]) for r in res["report"] if r.get("note")]
    if notes:
        p("")
        p("HER NOTES")
        for k, n in notes:
            p("  %s: %s" % (k, n.strip()))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("response", type=Path, help="the JSON she sent back")
    ap.add_argument("--out", type=Path, default=None,
                    help="output path (default: priors_elicited.yaml beside the input)")
    args = ap.parse_args(argv)

    if not args.response.exists():
        print("No such file: %s" % args.response, file=sys.stderr)
        return 2
    try:
        doc = json.loads(args.response.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print("That file isn't valid JSON (%s).\nIf she pasted it into an email, check "
              "nothing was truncated." % exc, file=sys.stderr)
        return 2

    try:
        res = convert(doc)
    except ConversionError as exc:
        print("Could not convert: %s" % exc, file=sys.stderr)
        return 1

    out_path = args.out or args.response.parent / "priors_elicited.yaml"
    out_path.write_text(emit_yaml(res, args.response), encoding="utf-8")

    print_report(res)
    print("")
    print("WROTE %s" % out_path)
    print("")
    print("Nothing is adopted yet. To put these in front of the model, copy that file over")
    print("causal_graph/v1_model/priors.yaml -- and keep the placeholder version somewhere,")
    print("because the difference between the two IS the expert's contribution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
