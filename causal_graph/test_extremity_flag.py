"""Validation of extremity_flag.py against REAL citation data from the
2026-09-01 run_all_dims_evidence.py run. Hand-labelled band membership, grounded in
the frozen anchors' own 0.1 band descriptions. No API calls.

Each case records what the human raters said, so a flag that contradicts human
judgment is visible as such rather than silently counted as a success.
"""
import sys
sys.path.insert(0, "/home/claude")

from extremity_flag import ManualBandProbe, flag_dimension

# (dimension, quote) -> does the quote match that dimension's 0.1 band description?
# Grounded in anchors.json band text, e.g. autonomy 0.1 reads:
#   "Work is assigned and specified top-down. Most decisions need sign-off. Postings
#    stress 'follow established processes', reviews cite micromanagement or rigid procedure."
LABELS = {
    # --- P-06 autonomy: the cleanest true floor case (human C = 0.1, LLM = 0.3)
    ("autonomy", "Typically works under close supervision."): True,
    ("autonomy", "Follow a range of mandatory procedures"): True,
    ("autonomy", "they believe in top down micromanagement."): True,

    # --- P-01 autonomy: 2 harsh + 1 countervailing (human C = 0.1, LLM = 0.3)
    ("autonomy", "Heavy micromanagement."): True,
    ("autonomy", "Very micromanage."): True,
    ("autonomy", "You have significant autonomy to do your job with appropriate support when needed."): False,

    # --- P-03 autonomy: THE COUNTEREXAMPLE. All three match the 0.9 band, none match
    #     0.1, LLM scored 0.7, human median was also 0.7 -- model was right.
    ("autonomy", "Own your impact on day one"): False,
    ("autonomy", "This role is best suited for candidates who thrive in autonomous, high-expectation environments."): False,
    ("autonomy", "Demonstrated ability to work independently and take full ownership of responsibilities without the need for repeated instruction or hand-holding"): False,

    # --- P-06 innovation: weaker true floor case (human C = 0.1, LLM = 0.3)
    ("innovation", "As an established but ever-evolving company"): None,  # genuinely ambiguous
    ("innovation", "Outdated tech and systems"): True,
    ("innovation", "taking a conservative approach"): True,

    # --- P-02 decision: genuinely mixed, must not flag (LLM 0.5, humans 0.7/0.5)
    ("decision", "communicating insights and recommendations from the data to drive positive results."): False,
    ("decision", "no document, including this Code, is a substitute for your good judgment."): True,
}

CASES = [
    dict(
        name="P-06/autonomy  [TRUE FLOOR CASE]",
        packet_id="P-06", dimension="autonomy", score=0.3,
        quotes=["Typically works under close supervision.",
                "Follow a range of mandatory procedures",
                "they believe in top down micromanagement."],
        human="B=0.5, C=0.1",
        expect_flag="FLOOR_SUSPECT",
        why="All 3 verified citations match the 0.1 band verbatim in substance.",
    ),
    dict(
        name="P-01/autonomy  [countervailing evidence present]",
        packet_id="P-01", dimension="autonomy", score=0.3,
        quotes=["Heavy micromanagement.",
                "Very micromanage.",
                "You have significant autonomy to do your job with appropriate support when needed."],
        human="B=0.9, C=0.1",
        expect_flag=None,
        why="One citation contradicts the floor read; 0.3 is defensible. Conservative no-fire.",
    ),
    dict(
        name="P-03/autonomy  [COUNTEREXAMPLE that killed the symmetric design]",
        packet_id="P-03", dimension="autonomy", score=0.7,
        quotes=["Own your impact on day one",
                "This role is best suited for candidates who thrive in autonomous, high-expectation environments.",
                "Demonstrated ability to work independently and take full ownership of responsibilities without the need for repeated instruction or hand-holding"],
        human="B=0.5, C=0.9 (median 0.7 == the LLM's score)",
        expect_flag=None,
        why=("A SYMMETRIC ceiling check would fire here -- identical citation shape, all "
             "three matching the 0.9 band while the score sits inside the pole. It would "
             "be wrong: the model matched the human median exactly. This is why the flag "
             "is one-sided."),
    ),
    # NOTE 2026-09-01 (corrected): the live sweep did not fire on this cell
    # (2 of 3 quotes matched). An earlier note here claimed the probe had rejected
    # "As an established but ever-evolving company" -- that was an UNSUPPORTED
    # INFERENCE; the sweep only prints per-quote detail for cells that fired.
    # probe_boundary_test.py subsequently matched "As an established..." True and
    # "Outdated tech and systems" False, which is consistent with the sweep and
    # indicates the rejected quote was "Outdated tech and systems".
    # Independently, that boundary test showed this fixture's hand label for
    # "Outdated tech and systems" (True) is likely WRONG: innovation's 0.1 band
    # describes a deliberate execute/optimize posture, not a negative state, so
    # legacy-tech complaints are not automatically floor evidence. Left unedited on
    # purpose -- this suite validates FLAG LOGIC against hand labels and does not
    # validate the labels themselves. A green suite is not evidence of probe accuracy.
    dict(
        name="P-06/innovation  [weaker case -- see corrected note above]",
        packet_id="P-06", dimension="innovation", score=0.3,
        quotes=["As an established but ever-evolving company",
                "Outdated tech and systems",
                "taking a conservative approach"],
        human="B=0.3, C=0.1",
        expect_flag="FLOOR_SUSPECT",
        why="2 match the floor band, 1 undecidable, 0 contradict.",
    ),
    dict(
        name="P-02/decision  [genuinely mixed]",
        packet_id="P-02", dimension="decision", score=0.5,
        quotes=["communicating insights and recommendations from the data to drive positive results.",
                "no document, including this Code, is a substitute for your good judgment."],
        human="B=0.7, C=0.5",
        expect_flag=None,
        why="Evidence points both ways; the middle band is the correct answer.",
    ),
]

probe = ManualBandProbe(LABELS)
passed = failed = 0

for case in CASES:
    verified_map = {q: True for q in case["quotes"]}
    f = flag_dimension(
        packet_id=case["packet_id"], dimension=case["dimension"], score=case["score"],
        quotes=case["quotes"], verified_map=verified_map, probe=probe,
    )
    ok = f.flag == case["expect_flag"]
    passed += ok
    failed += (not ok)
    print(f"{'PASS' if ok else 'FAIL'}  {case['name']}")
    print(f"        score={f.score}  humans: {case['human']}")
    print(f"        matching_floor={f.n_matching_floor}  not_matching={f.n_not_matching}")
    print(f"        flag={f.flag} ({f.severity})  expected={case['expect_flag']}")
    print(f"        rationale: {f.rationale}")
    print(f"        note: {case['why']}")
    print()

print("=" * 78)
print(f"{passed} passed, {failed} failed")
