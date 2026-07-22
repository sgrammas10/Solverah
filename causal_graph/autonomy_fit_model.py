"""
Solverah - Causal Bayesian Network starter (first vertical slice)
==================================================================

Scope: ONE interaction dimension end-to-end (autonomy fit), not the full
platform. The goal of this slice is to prove the pipeline shape:

    Person signal + Environment signal --> Fit (causal node) --> Engagement --> Guidance

before expanding to the other dimensions (pace, feedback style, etc.) shown
in the full causal graph (see causal_graph.png).

Structure of every node's CPD below is HAND-SPECIFIED (expert-elicited),
not learned from data, because there is no user data yet. This is
intentional and matches the "no premature scoring" principle: these
probabilities are a starting belief, not a claim of certainty. Once real
signals come in from Reflection / Work Pulse / CompanyLens / ManagerMatch,
replace the hand-specified CPDs with pgmpy's parameter estimation
(MLE / BayesianEstimator) fit on logged outcomes.

Requirements:
    pip install pgmpy
"""

import itertools

from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination


def compounding_engagement_values(
    n_fit_dims: int, ceiling_high: float = 0.80, poor_divisor: float = 4.0
) -> list[list[float]]:
    """
    Generate the Engagement CPD's [Low_row, High_row] so that Poor fits
    compound multiplicatively in odds-space instead of being hand-typed
    per cell.

    ceiling_high: P(Engagement=High) when every Fit_* dimension is Good.
    poor_divisor: factor the odds of High engagement are divided by for
        EACH Fit_* dimension that reads Poor -- two Poor dimensions divide
        the odds by poor_divisor**2 (not poor_divisor*2), which is what
        makes the harm compound rather than just add up. Raise this to
        make engagement collapse faster as Poor fits stack up; lower it
        (toward 1.0) to flatten back toward a purely additive curve.

    Column order matches what pgmpy expects for evidence=[Fit_dim_1, ...,
    Fit_dim_n]: itertools.product(["Poor", "Good"], repeat=n_fit_dims).
    """
    base_odds = ceiling_high / (1 - ceiling_high)
    low_row: list[float] = []
    high_row: list[float] = []
    for combo in itertools.product(["Poor", "Good"], repeat=n_fit_dims):
        n_poor = combo.count("Poor")
        odds = base_odds / (poor_divisor**n_poor)
        p_high = odds / (1 + odds)
        high_row.append(round(p_high, 4))
        low_row.append(round(1 - p_high, 4))
    return [low_row, high_row]

# ---------------------------------------------------------------------------
# 1. Graph structure: which nodes causally influence which.
#    This structure itself is the hypothesis your partner should stress-test
#    tonight -- edges are causal claims, not just "these are correlated".
# ---------------------------------------------------------------------------
model = DiscreteBayesianNetwork([
    ("P_Autonomy", "Fit_Autonomy"),       # person trait -> fit
    ("E_ManagerStyle", "Fit_Autonomy"),   # environment trait -> fit

    ("P_Pace", "Fit_Pace"),               # person trait -> fit
    ("E_Pace", "Fit_Pace"),               # environment trait -> fit

    ("P_Feedback", "Fit_Feedback"),       # person trait -> fit
    ("E_Feedback", "Fit_Feedback"),       # environment trait -> fit

    ("Fit_Autonomy", "Engagement"),       # fit -> observed outcome
    ("Fit_Pace", "Engagement"),           # fit -> observed outcome
    ("Fit_Feedback", "Engagement"),       # fit -> observed outcome

    ("Engagement", "Guidance"),           # outcome -> what Solverah recommends
])

# ---------------------------------------------------------------------------
# 2. Priors for the two root (uncaused, within this slice) signals.
#    In production these come from Reflection (P_Autonomy) and CompanyLens /
#    ManagerMatch (E_ManagerStyle) -- here they start uninformative (50/50)
#    until a real user's Reflection answers or a real CompanyLens profile
#    updates them.
# ---------------------------------------------------------------------------
# Define the CPDs for the root nodes

#autonomy trait
cpd_p_autonomy = TabularCPD(
    variable="P_Autonomy", variable_card=2,
    # [P(Low), P(High)] -- uninformative 50/50 prior, no belief yet about
    # this person. Once Reflection answers exist, replace with the real
    # split (e.g. [[0.3],[0.7]] if reflection says they lean High-autonomy).
    # Moving this off 50/50 shifts the marginal odds of every downstream
    # node (Fit_Autonomy, Engagement, Guidance) toward whichever state you
    # weight higher, even before any evidence is supplied at query time.
    
    values=[[0.5], [0.5]],  # these values will initially be input by the reflection survey or some other form of input from the user profile
    state_names={"P_Autonomy": ["Low", "High"]},
)

cpd_e_manager = TabularCPD(
    variable="E_ManagerStyle", variable_card=2,
    # [P(Controlling), P(Empowering)] -- same uninformative-prior logic as
    # above, but for the environment/manager signal (CompanyLens/ManagerMatch
    # would supply the real split). Skews here bias Fit_Autonomy's marginal
    # toward whichever manager style is weighted higher.
    values=[[0.5], [0.5]],
    state_names={"E_ManagerStyle": ["Controlling", "Empowering"]},
)
#pace trait
cpd_p_pace = TabularCPD(
    variable="P_Pace", variable_card=2,
    # Same pattern as P_Autonomy but for pace preference. Uninformative
    # until real Reflection data backs it.
    values=[[0.5], [0.5]],
    state_names={"P_Pace": ["Low", "High"]},
)

cpd_e_pace = TabularCPD(
    variable="E_Pace", variable_card=2,
    # Environment's actual operating pace. Uninformative until CompanyLens
    # supplies a measured value.
    values=[[0.5], [0.5]],
    state_names={"E_Pace": ["Low", "High"]},
)

#feedback trait
cpd_p_feedback = TabularCPD(
    variable="P_Feedback", variable_card=2,
    # Person's desired feedback frequency. Uninformative until Reflection
    # data backs it.
    values=[[0.5], [0.5]],
    state_names={"P_Feedback": ["Low", "High"]},
)

cpd_e_feedback = TabularCPD(
    variable="E_Feedback", variable_card=2,
    # Environment's actual feedback cadence. Uninformative until
    # CompanyLens/ManagerMatch supplies a measured value.
    values=[[0.5], [0.5]],
    state_names={"E_Feedback": ["Low", "High"]},
)

# ---------------------------------------------------------------------------
# 3. Fit_Autonomy: THIS is the causal interaction node -- the actual IP.
#    It is not a similarity score between P_Autonomy and E_ManagerStyle; it
#    is a hand-elicited hypothesis about how the combination produces a fit
#    outcome. Read column-by-column against the state_names combinations
#    below (pgmpy orders evidence combinations by itertools.product).
# ---------------------------------------------------------------------------
cpd_fit_autonomy = TabularCPD(
    variable="Fit_Autonomy", variable_card=2,
    values=[
        # Column order for evidence=[P_Autonomy, E_ManagerStyle] is:
        #   (Low,Controlling) (Low,Empowering) (High,Controlling) (High,Empowering)
        # Each pair of columns (Poor row, Good row) must sum to 1.0 -- these
        # are the four "cells" of the interaction hypothesis:
        #   col1 0.20/0.80 (Low,Controlling)  -> mostly Good. A low-autonomy
        #     person under a controlling manager is expected to fit fine;
        #     raising 0.20 says "actually this combo causes more friction
        #     than expected" and pulls Fit toward Poor for that cell only.
        #   col2 0.30/0.70 (Low,Empowering)   -> still mostly Good, slightly
        #     worse than col1 because a low-autonomy person can feel
        #     under-supported without structure. Raising 0.30 claims
        #     empowering managers hurt low-autonomy people more than
        #     controlling ones do.
        #   col3 0.85/0.15 (High,Controlling) -> the core "mismatch" cell:
        #     a high-autonomy person under a controlling manager is
        #     predicted mostly Poor. Lowering 0.85 says this mismatch is
        #     less damaging than currently modeled; raising it says it's
        #     worse.
        #   col4 0.10/0.90 (High,Empowering)  -> the core "match" cell:
        #     high-autonomy + empowering manager is predicted mostly Good.
        #     Raising 0.10 waters down how strongly this ideal pairing
        #     guarantees a good fit.
        # Because this feeds Engagement/Guidance, any change to a single
        # cell only moves the query result for evidence that lands in that
        # cell -- it does not affect the other three combinations.
        [0.20, 0.30, 0.85, 0.10],   # Fit = Poor
        [0.80, 0.70, 0.15, 0.90],   # Fit = Good
    ],
    evidence=["P_Autonomy", "E_ManagerStyle"],
    evidence_card=[2, 2],
    state_names={
        "Fit_Autonomy": ["Poor", "Good"],
        "P_Autonomy": ["Low", "High"],
        "E_ManagerStyle": ["Controlling", "Empowering"],
    },
)

cpd_fit_pace = TabularCPD(
    variable="Fit_Pace", variable_card=2,
    # Same 4-column structure/logic as cpd_fit_autonomy above, just with
    # P_Pace/E_Pace states instead of P_Autonomy/E_ManagerStyle:
    #   col1 (Low,Low)   0.20/0.80 -> mostly Good (matched, both low pace)
    #   col2 (Low,High)  0.30/0.70 -> mostly Good, slightly riskier mismatch
    #   col3 (High,Low)  0.85/0.15 -> mismatch cell, mostly Poor
    #   col4 (High,High) 0.10/0.90 -> matched, mostly Good
    # Currently reuses the exact same numbers as autonomy as a placeholder;
    # tune independently once pace-specific evidence suggests the fit
    # penalty for a pace mismatch differs from an autonomy mismatch.
    values=[
        [0.20, 0.30, 0.85, 0.10],   # Fit = Poor
        [0.80, 0.70, 0.15, 0.90],   # Fit = Good
    ],
    evidence=["P_Pace", "E_Pace"],
    evidence_card=[2, 2],
    state_names={
        "Fit_Pace": ["Poor", "Good"],
        "P_Pace": ["Low", "High"],
        "E_Pace": ["Low", "High"],
    },
)

cpd_fit_feedback = TabularCPD(
    variable="Fit_Feedback", variable_card=2,
    # Same 4-column structure/logic as cpd_fit_autonomy above, just with
    # P_Feedback/E_Feedback states:
    #   col1 (Low,Low)   0.20/0.80 -> matched, mostly Good
    #   col2 (Low,High)  0.30/0.70 -> mismatch risk, but softer than col3
    #   col3 (High,Low)  0.85/0.15 -> mismatch cell (wants feedback, gets
    #     little), mostly Poor
    #   col4 (High,High) 0.10/0.90 -> matched, mostly Good
    # Also a placeholder copy of the autonomy numbers; replace once there's
    # a reason to believe feedback mismatches hurt fit more/less than
    # autonomy or pace mismatches do.
    values=[
        [0.20, 0.30, 0.85, 0.10],   # Fit = Poor
        [0.80, 0.70, 0.15, 0.90],   # Fit = Good
    ],
    evidence=["P_Feedback", "E_Feedback"],
    evidence_card=[2, 2],
    state_names={
        "Fit_Feedback": ["Poor", "Good"],
        "P_Feedback": ["Low", "High"],
        "E_Feedback": ["Low", "High"],
    },
)

# ---------------------------------------------------------------------------
# 4. Engagement: observed over time via Work Pulse. Driven by Fit here;
#    in the full model it is also driven by Fit_Pace and Fit_Feedback.
# ---------------------------------------------------------------------------
cpd_engagement = TabularCPD(
    variable="Engagement", variable_card=2,
    # Column order for evidence=[Fit_Autonomy, Fit_Pace, Fit_Feedback] is:
    #   (Poor,Poor,Poor) (Poor,Poor,Good) (Poor,Good,Poor) (Poor,Good,Good)
    #   (Good,Poor,Poor) (Good,Poor,Good) (Good,Good,Poor) (Good,Good,Good)
    #
    # Values are generated (not hand-typed) by compounding_engagement_values,
    # so that Poor fits COMPOUND multiplicatively in odds-space rather than
    # just adding up. With ceiling_high=0.80 and poor_divisor=4.0:
    #   0 Poor: odds 4.00 / 1  -> 0.8000 High  (ceiling)
    #   1 Poor: odds 4.00 / 4  -> 0.5000 High
    #   2 Poor: odds 4.00 / 16 -> 0.2000 High
    #   3 Poor: odds 4.00 / 64 -> 0.0588 High  (floor)
    # This is deliberately super-additive: a pure additive model would
    # predict harm growing in fixed steps (~0.247 per Poor fit -> 0.247,
    # 0.494, 0.741). The actual drop from the ceiling is 0.30, 0.60, 0.7412
    # -- each extra Poor fit costs MORE than the one before it, so e.g. two
    # Poor fits together are worse than twice the damage of one Poor fit
    # alone. Cells with the same Poor-count are identical regardless of
    # *which* dimension is Poor (Autonomy/Pace/Feedback are treated as
    # interchangeable risk factors here). Tune the compounding via
    # compounding_engagement_values's poor_divisor/ceiling_high args rather
    # than editing cells by hand.
    values=compounding_engagement_values(3),
    evidence=["Fit_Autonomy", "Fit_Pace", "Fit_Feedback"],
    evidence_card=[2, 2, 2],
    state_names={
        "Engagement": ["Low", "High"],
        "Fit_Autonomy": ["Poor", "Good"],
        "Fit_Pace": ["Poor", "Good"],
        "Fit_Feedback": ["Poor", "Good"],
    },
)

# ---------------------------------------------------------------------------
# 5. Guidance: the decision-layer output. Simple two-state stand-in for
#    "Decision Intelligence" -- expand this to multi-class guidance text
#    once Narrative Intelligence sits on top of it.
# ---------------------------------------------------------------------------
cpd_guidance = TabularCPD(
    variable="Guidance", variable_card=2,
    values=[
        # Columns are evidence=[Engagement=Low, Engagement=High].
        # col1 (Engagement Low):  0.80 Reconsider / 0.20 Proceed -- strong
        #   but not absolute lean toward flagging the match for review.
        #   Raising 0.80 makes Guidance react more sharply to any sign of
        #   low engagement (more false-positive "reconsider" flags on noisy
        #   data); lowering it makes Guidance more forgiving of a bad
        #   engagement read.
        # col2 (Engagement High): 0.15 Reconsider / 0.85 Proceed -- mirrors
        #   col1. Lowering 0.15 makes "Proceed" more confident when
        #   engagement looks good; raising it injects more caution even
        #   when signals are positive (useful if false "High" engagement
        #   reads are a known risk).
        # This is the only node with no hedging built in via other
        # evidence, so it's the most direct lever for how cautious vs.
        # decisive Solverah's final recommendation is.
        [0.80, 0.15],   # Guidance = "Reconsider / probe further" | Engagement Low, High
        [0.20, 0.85],   # Guidance = "Proceed"                    | Engagement Low, High
    ],
    evidence=["Engagement"],
    evidence_card=[2],
    state_names={
        "Guidance": ["Reconsider", "Proceed"],
        "Engagement": ["Low", "High"],
    },
)

model.add_cpds(cpd_p_autonomy, cpd_e_manager, cpd_p_pace, cpd_e_pace, cpd_p_feedback, cpd_e_feedback, cpd_fit_autonomy, cpd_fit_pace, cpd_fit_feedback, cpd_engagement, cpd_guidance)
assert model.check_model(), "CPDs do not match graph structure"

infer = VariableElimination(model)

if __name__ == "__main__":
    print("Model valid. Running example queries...\n")

    # Example: a person who wants a lot of autonomy, a fast pace, and frequent
    # feedback -- placed with a controlling, slow-paced, low-feedback manager.
    evidence = {
        "P_Autonomy": "High", "E_ManagerStyle": "Controlling",
        "P_Pace": "High", "E_Pace": "Low",
        "P_Feedback": "High", "E_Feedback": "Low",
    }

    for fit_var in ("Fit_Autonomy", "Fit_Pace", "Fit_Feedback"):
        fit_result = infer.query(variables=[fit_var], evidence=evidence, show_progress=False)
        print(f"P({fit_var} | mismatched evidence):")
        print(fit_result, "\n")

    engagement_result = infer.query(variables=["Engagement"], evidence=evidence, show_progress=False)
    print("P(Engagement | same evidence):")
    print(engagement_result, "\n")

    guidance_result = infer.query(variables=["Guidance"], evidence=evidence, show_progress=False)
    print("P(Guidance | same evidence):")
    print(guidance_result, "\n")

    print("-" * 60)
    print("Compare against a fully matching environment:")
    evidence2 = {
        "P_Autonomy": "High", "E_ManagerStyle": "Empowering",
        "P_Pace": "High", "E_Pace": "High",
        "P_Feedback": "High", "E_Feedback": "High",
    }
    guidance_result2 = infer.query(variables=["Guidance"], evidence=evidence2, show_progress=False)
    print("P(Guidance | High autonomy/pace/feedback need, all matched):")
    print(guidance_result2)
