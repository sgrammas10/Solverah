"""
Solverah - Autonomy-only Bayesian Network slice
================================================

Trimmed-down version of autonomy_fit_model.py: only the autonomy chain.

    P_Autonomy + E_ManagerStyle --> Fit_Autonomy --> Engagement --> Guidance

Pace and Feedback are left out entirely (not just zeroed out) so this file
can be reasoned about and tuned in isolation before wiring the other two
dimensions back in.

No behavioral-evidence / belief-updating layer yet -- P_Autonomy is still
the flat 50/50 "no belief yet" prior. Per-user belief (quiz score, then
Bayesian updates from observed behavior) is a separate follow-up; this file
is just the causal chain and its hand-elicited CPDs.

Requirements:
    pip install pgmpy
"""

from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination

# ---------------------------------------------------------------------------
# 1. Graph structure: which nodes causally influence which.
#    This structure itself is the hypothesis to stress-test -- edges are
#    causal claims, not just "these are correlated".
# ---------------------------------------------------------------------------
model = DiscreteBayesianNetwork([
    ("P_Autonomy", "Fit_Autonomy"),       # person trait -> fit
    ("E_ManagerStyle", "Fit_Autonomy"),   # environment trait -> fit
    ("Fit_Autonomy", "Engagement"),       # fit -> observed outcome
    ("Engagement", "Guidance"),           # outcome -> what Solverah recommends
])

# ---------------------------------------------------------------------------
# 2. Priors for the two root (uncaused, within this slice) signals.
#    In production these come from Reflection (P_Autonomy) and CompanyLens /
#    ManagerMatch (E_ManagerStyle) -- here they start uninformative (50/50)
#    until a real user's Reflection answers or a real CompanyLens profile
#    updates them.
# ---------------------------------------------------------------------------
cpd_p_autonomy = TabularCPD(
    variable="P_Autonomy", variable_card=3,
    # [P(Low), P(Moderate), P(High)] -- uninformative ~1/3-1/3-1/3 prior, no
    # belief yet about this person. Once Reflection answers exist, replace
    # with the real split. Moving this off uniform shifts the marginal odds
    # of every downstream node (Fit_Autonomy, Engagement, Guidance) toward
    # whichever state you weight higher, even before any evidence is
    # supplied at query time.
    values=[[0.34], [0.33], [0.33]],
    state_names={"P_Autonomy": ["Low", "Moderate", "High"]},
)

cpd_e_manager = TabularCPD(
    variable="E_ManagerStyle", variable_card=3,
    # [P(Controlling), P(Balanced), P(Empowering)] -- same uninformative-
    # prior logic as above, but for the environment/manager signal
    # (CompanyLens/ManagerMatch would supply the real split). Skews here
    # bias Fit_Autonomy's marginal toward whichever manager style is
    # weighted higher.
    values=[[0.34], [0.33], [0.33]],
    state_names={"E_ManagerStyle": ["Controlling", "Balanced", "Empowering"]},
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
        #   (Low,Ctrl) (Low,Bal) (Low,Emp) (Mod,Ctrl) (Mod,Bal) (Mod,Emp) (High,Ctrl) (High,Bal) (High,Emp)
        # Each pair of columns (Poor row, Good row) must sum to 1.0. This is
        # a soft "matching" hypothesis: Low<->Controlling, Moderate<->Balanced,
        # High<->Empowering are each other's best-fit pairing, and Good-rate
        # falls off as person/manager style diverge along that diagonal.
        #   (Low,Ctrl)   0.20/0.80 -> best-fit corner for a low-autonomy
        #     person; raising 0.20 says this pairing causes more friction
        #     than expected.
        #   (Low,Bal)    0.25/0.75 -> one step off the low-autonomy person's
        #     ideal (structure), slightly worse than (Low,Ctrl).
        #   (Low,Emp)    0.30/0.70 -> furthest from a low-autonomy person's
        #     ideal; under-supported without structure.
        #   (Mod,Ctrl)   0.55/0.45 -> moderate person tolerates structure but
        #     it's not their best fit.
        #   (Mod,Bal)    0.20/0.80 -> the matched-pair cell for a moderate
        #     person; deliberately the strongest Good-rate in the table.
        #   (Mod,Emp)    0.35/0.65 -> moderate person under-structured
        #     relative to their ideal, but still workable.
        #   (High,Ctrl)  0.85/0.15 -> the core "mismatch" cell: a
        #     high-autonomy person under a controlling manager is predicted
        #     mostly Poor.
        #   (High,Bal)   0.45/0.55 -> one step off the high-autonomy
        #     person's ideal (full empowerment), better than (High,Ctrl)
        #     but not as good as (High,Emp).
        #   (High,Emp)   0.10/0.90 -> the core "match" cell: high-autonomy +
        #     empowering manager is predicted mostly Good.
        # Because this feeds Engagement/Guidance, any change to a single
        # cell only moves the query result for evidence that lands in that
        # cell -- it does not affect the other eight combinations.
        [0.20, 0.25, 0.30, 0.55, 0.20, 0.35, 0.85, 0.45, 0.10],   # Fit = Poor
        [0.80, 0.75, 0.70, 0.45, 0.80, 0.65, 0.15, 0.55, 0.90],   # Fit = Good
    ],
    evidence=["P_Autonomy", "E_ManagerStyle"],
    evidence_card=[3, 3],
    state_names={
        "Fit_Autonomy": ["Poor", "Good"],
        "P_Autonomy": ["Low", "Moderate", "High"],
        "E_ManagerStyle": ["Controlling", "Balanced", "Empowering"],
    },
)

# ---------------------------------------------------------------------------
# 4. Engagement: observed over time via Work Pulse. Driven only by
#    Fit_Autonomy in this slice -- the full model also blends in Fit_Pace
#    and Fit_Feedback, which is why that version needs 8 columns
#    (Poor/Good ^3) instead of these 2.
# ---------------------------------------------------------------------------
cpd_engagement = TabularCPD(
    variable="Engagement", variable_card=2,
    values=[
        # Columns are evidence=[Fit_Autonomy]: Poor, Good.
        # col1 (Fit=Poor): 0.85 Low / 0.15 High -- a bad autonomy fit mostly
        #   tanks engagement. Since this slice has no Fit_Pace/Fit_Feedback
        #   to partially offset a bad autonomy read, this floor is set
        #   lower (more decisive) than the full model's all-Poor floor
        #   (0.10 High there vs 0.15 here) -- there's nothing else in this
        #   graph that could still be going right.
        # col2 (Fit=Good): 0.15 Low / 0.85 High -- mirrors col1. Fit alone
        #   drives engagement almost fully in this trimmed graph, so the
        #   ceiling is intentionally not 1.0 -- engagement isn't literally
        #   guaranteed by fit alone even in the single-dimension case.
        # Raising col1's 0.85 makes the model more forgiving of a bad
        # autonomy fit; lowering col2's 0.85 makes it more skeptical that
        # a good fit alone produces real engagement.
        [0.85, 0.15],   # Engagement = Low
        [0.15, 0.85],   # Engagement = High
    ],
    evidence=["Fit_Autonomy"],
    evidence_card=[2],
    state_names={
        "Engagement": ["Low", "High"],
        "Fit_Autonomy": ["Poor", "Good"],
    },
)

# ---------------------------------------------------------------------------
# 5. Guidance: the decision-layer output. Simple two-state stand-in for
#    "Decision Intelligence" -- expand this to multi-class guidance text
#    once Narrative Intelligence sits on top of it. Unchanged from the full
#    model since it only ever depends on Engagement, never on Fit directly.
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

model.add_cpds(cpd_p_autonomy, cpd_e_manager, cpd_fit_autonomy, cpd_engagement, cpd_guidance)
assert model.check_model(), "CPDs do not match graph structure"

infer = VariableElimination(model)

if __name__ == "__main__":
    print("Model valid. Running example queries...\n")

    # Mismatch: high-autonomy person, controlling manager.
    evidence = {"P_Autonomy": "High", "E_ManagerStyle": "Controlling"}
    for var in ("Fit_Autonomy", "Engagement", "Guidance"):
        result = infer.query(variables=[var], evidence=evidence, show_progress=False)
        print(f"P({var} | High autonomy, Controlling manager):")
        print(result, "\n")

    print("-" * 60)
    # Match: high-autonomy person, empowering manager.
    evidence2 = {"P_Autonomy": "High", "E_ManagerStyle": "Empowering"}
    guidance2 = infer.query(variables=["Guidance"], evidence=evidence2, show_progress=False)
    print("P(Guidance | High autonomy, Empowering manager):")
    print(guidance2, "\n")

    print("-" * 60)
    # Matched-pair case introduced by the Moderate/Balanced states.
    evidence3 = {"P_Autonomy": "Moderate", "E_ManagerStyle": "Balanced"}
    guidance3 = infer.query(variables=["Guidance"], evidence=evidence3, show_progress=False)
    print("P(Guidance | Moderate autonomy, Balanced manager):")
    print(guidance3)
