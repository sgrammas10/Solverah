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

from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination

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
    values=[[0.5], [0.5]],
    state_names={"P_Autonomy": ["Low", "High"]},
)

cpd_e_manager = TabularCPD(
    variable="E_ManagerStyle", variable_card=2,
    values=[[0.5], [0.5]],
    state_names={"E_ManagerStyle": ["Controlling", "Empowering"]},
)
#pace trait
cpd_p_pace = TabularCPD(
    variable="P_Pace", variable_card=2,
    values=[[0.5], [0.5]],
    state_names={"P_Pace": ["Low", "High"]},
)

cpd_e_pace = TabularCPD(
    variable="E_Pace", variable_card=2,
    values=[[0.5], [0.5]],
    state_names={"E_Pace": ["Low", "High"]},
)

#feedback trait
cpd_p_feedback = TabularCPD(
    variable="P_Feedback", variable_card=2,
    values=[[0.5], [0.5]],
    state_names={"P_Feedback": ["Low", "High"]},
)

cpd_e_feedback = TabularCPD(
    variable="E_Feedback", variable_card=2,
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
    values=[
        # Column order for evidence=[Fit_Autonomy, Fit_Pace, Fit_Feedback] is:
        #   (Poor,Poor,Poor) (Poor,Poor,Good) (Poor,Good,Poor) (Poor,Good,Good)
        #   (Good,Poor,Poor) (Good,Poor,Good) (Good,Good,Poor) (Good,Good,Good)
        [0.90, 0.75, 0.75, 0.55, 0.75, 0.55, 0.55, 0.25],   # Engagement = Low
        [0.10, 0.25, 0.25, 0.45, 0.25, 0.45, 0.45, 0.75],   # Engagement = High
    ],
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
