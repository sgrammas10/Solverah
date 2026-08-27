"""Tests for check_state.py (S-28).

THE DESIGN: the fixtures ARE the incident history.

Each historical failure that motivated this checker is reconstructed here as a perturbation of
a known-good STATE + repo, and the test asserts the checker fires. That is what converts
"this would have caught six of seven" from a claim into a measurement. A checker tested only
against a healthy document proves nothing -- the six incidents all happened to people looking
at documents that appeared healthy.

Every perturbation test is paired with the clean baseline (test_healthy_state_passes), so a
failure cannot pass merely because the fixture is broken for all inputs -- the S-40 discipline
applied to this file itself.

Reconstructed incidents:
  * S-35        D-12's rule text rewritten away from the artifact  -> CHECK-STALE
  * "6 files"   6 rater HTML files on disk where STATE claims 18   -> count FAIL
  * S-34        STATE calls a file uncommitted that git has clean  -> git FAIL
  * generic     an artifact named in STATE that is not on disk     -> existence FAIL
  * structural  an id both open and closed / dangling / no carried -> structure FAIL
"""

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "causal_graph" / "v1_model"))

import check_state as cs  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: a minimal healthy STATE and a matching minimal repo
# ---------------------------------------------------------------------------

HEALTHY_STATE = """# Solverah — STATE

## 1. What Solverah currently is

`mean_pole` over four items. See S-01 and D-02.

## 2. Artifact inventory

| artifact | what it is | since |
|---|---|---|
| `assessment_items_v2.yaml` | `status: active`, `form_version: v2-2026-08-18` | 08-18 |
| `assessment_items.yaml` | retired; `status: superseded` | 08-18 |
| `seed_discipline.py` | D-21 enforced. In the working tree, uncommitted. | 08-19b |
| `match_core.py` | carries `PERSON_LATTICE` | 08-19b |
| `assessment_form.py` | CONFIDENCE_PENDING_DIMENSIONS lives here | 08-19b |
| `anchors.json` | FROZEN `v1-frozen-2026-08-15`, `band_values` `[0.1,0.3,0.5,0.7,0.9]` | 08-15 |
| **18 rater HTML files** | `P-01`–`P-06` × A, B, C = 18, *not* 6 | 08-19 |

## 3. Open items

**S-01 — An open item.** `carried: 2`
Body text referencing D-12.

**S-02 — Another open item.** `carried: 0`
More body text.

## 4. Locked decisions

- **D-02. Exactly four items per dimension.** Enforced by the scorer.
- **D-12. The agreement rule is the one in `anchors.json`.**

  **(a) Band distance, compared as integers — not a numeric threshold.** Same band = agreement.
- **D-21. The seeds rule.** A comparison needs ≥3 independent draws.

## 5. Measured results

Nothing to re-derive here.

## 6. Closed

- **S-03 — A closed item.** CLOSED.

## 7. Won't do

- **S-04 — A won't-do item.** Moved here.
"""

ITEMS_V2 = """form_version: v2-2026-08-18
status: active
scoring:
  method: mean_pole
  pole_values: {low: 0.0, high: 1.0}
items:
""" + "".join(
    f"""  - id: {d[:2]}{r}v2
    dimension: {d}
    difficulty_target: {0.1 + 0.2 * r}
    options:
      - {{ key: A, text: "a", pole: high }}
      - {{ key: B, text: "b", pole: low }}
"""
    for d in ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
    for r in range(1, 5)
)

ANCHORS = """{
  "rubric_version": "v1-frozen-2026-08-15",
  "band_values": [0.1, 0.3, 0.5, 0.7, 0.9],
  "agreement_rule": {
    "same_band": "agreement",
    "one_band_apart": "expected instrument resolution, not ambiguity",
    "two_or_more_bands_apart": "anchor ambiguity - reword, do not average"
  }
}"""


def build_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A minimal repo + IP tree that satisfies every registered claim."""
    repo = tmp_path / "Solverah"
    ip = tmp_path / "Solverah_IP"
    vm = repo / "causal_graph" / "v1_model"
    vm.mkdir(parents=True)
    (vm / "assessment_items_v2.yaml").write_text(ITEMS_V2, encoding="utf-8")
    (vm / "assessment_items.yaml").write_text("status: superseded\nitems: []\n", encoding="utf-8")
    (vm / "seed_discipline.py").write_text("MIN_DRAWS = 3\n", encoding="utf-8")
    (vm / "match_core.py").write_text(
        "PERSON_LATTICE = np.array([0.0, 0.25, 0.5, 0.75, 1.0])\n", encoding="utf-8"
    )
    (repo / "assessment_form.py").write_text(
        'CONFIDENCE_PENDING_DIMENSIONS = frozenset({"feedback"})\n', encoding="utf-8"
    )

    out = ip / "ground_truth" / "rater_app" / "out"
    out.mkdir(parents=True)
    (ip / "ground_truth" / "rater_app" / "anchors.json").write_text(ANCHORS, encoding="utf-8")
    for packet in range(1, 7):
        for rater in "ABC":
            (out / f"P-0{packet}_rater{rater}.html").write_text("<html></html>", encoding="utf-8")
    return repo, ip


def failures(state, repo, ip):
    return cs.run_checks(state, repo, ip).fails


# ---------------------------------------------------------------------------
# The baseline. Every test below is a perturbation of THIS.
# ---------------------------------------------------------------------------

def test_healthy_state_passes(tmp_path):
    repo, ip = build_repo(tmp_path)
    rep = cs.run_checks(HEALTHY_STATE, repo, ip)
    assert rep.fails == [], rep.fails
    assert rep.passes > 10


# ---------------------------------------------------------------------------
# Incident: S-35 -- a rule quoted from the wrong source
# ---------------------------------------------------------------------------

def test_s35_state_rewritten_away_from_the_artifact_is_caught(tmp_path):
    """The historical shape: STATE carried `ABS(A-B) > 0.15` while the live anchors.json said
    band distance. The registry catches it from the STATE side -- rewriting D-12 past the
    registered text is CHECK-STALE, which forces someone to look at the artifact again."""
    repo, ip = build_repo(tmp_path)
    broken = HEALTHY_STATE.replace(
        "**(a) Band distance, compared as integers — not a numeric threshold.**",
        "**(a) Flag when `ABS(A−B) > 0.15`.**",
    )
    fails = failures(broken, repo, ip)
    assert any("CHECK-STALE" in f and "agreement_rule_is_band_distance" in f for f in fails), fails


def test_s35_artifact_side_numeric_threshold_is_caught(tmp_path):
    """The mirror: if the ARTIFACT ever grows a numeric threshold, the band-distance claim in
    STATE stops being true and must fail."""
    repo, ip = build_repo(tmp_path)
    (ip / "ground_truth" / "rater_app" / "anchors.json").write_text(
        '{"rubric_version": "v1-frozen-2026-08-15", "band_values": [0.1,0.3,0.5,0.7,0.9],'
        ' "agreement_rule": {"flag_if_gap_exceeds": "0.15"}}', encoding="utf-8"
    )
    fails = failures(HEALTHY_STATE, repo, ip)
    assert any("agreement_rule_is_band_distance" in f for f in fails), fails


# ---------------------------------------------------------------------------
# Incident: "6 rater HTML files" where 18 exist
# ---------------------------------------------------------------------------

def test_rater_file_count_mismatch_is_caught(tmp_path):
    repo, ip = build_repo(tmp_path)
    out = ip / "ground_truth" / "rater_app" / "out"
    for p in sorted(out.glob("*.html"))[6:]:
        p.unlink()                      # leave 6, exactly the historical miscount
    fails = failures(HEALTHY_STATE, repo, ip)
    assert any("rater_html_count_18" in f and "6 .html" in f for f in fails), fails


# ---------------------------------------------------------------------------
# Incident: S-34 -- "uncommitted" outliving the commit that falsified it
# ---------------------------------------------------------------------------

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, timeout=60)


def test_s34_stale_uncommitted_claim_is_caught(tmp_path):
    repo, ip = build_repo(tmp_path)
    try:
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "t")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "everything committed")
    except Exception:
        pytest.skip("git unavailable")

    # STATE still says seed_discipline.py is uncommitted; git says the tree is clean.
    fails = failures(HEALTHY_STATE, repo, ip)
    assert any("uncommitted" in f and "seed_discipline.py" in f for f in fails), fails


def test_uncommitted_claims_are_actually_extracted(tmp_path):
    """Regression on the checker's own first bug: a proximity regex matched NOTHING against
    real STATE and reported a cheerful 'no claims to verify'. Absence of claims and absence
    of extraction must never look alike."""
    assert cs._uncommitted_claims(HEALTHY_STATE) == ["seed_discipline.py"]
    multi = ("**S-34 — Commit the work.** `carried: 0`\n"
             "Uncommitted now: `model.py`, `match_core.py`,\n"
             "`assessment_form.py`. Check `git status` first.\n")
    assert cs._uncommitted_claims(multi) == [
        "assessment_form.py", "match_core.py", "model.py",
    ]


# ---------------------------------------------------------------------------
# Artifact existence
# ---------------------------------------------------------------------------

def test_artifact_named_in_state_but_absent_is_caught(tmp_path):
    repo, ip = build_repo(tmp_path)
    (repo / "causal_graph" / "v1_model" / "match_core.py").unlink()
    fails = failures(HEALTHY_STATE, repo, ip)
    assert any("match_core.py" in f for f in fails), fails


# ---------------------------------------------------------------------------
# Structural drift in STATE itself
# ---------------------------------------------------------------------------

def test_item_both_open_and_closed_is_caught(tmp_path):
    repo, ip = build_repo(tmp_path)
    broken = HEALTHY_STATE.replace("**S-03 — A closed item.**", "**S-01 — A closed item.**")
    fails = failures(broken, repo, ip)
    assert any("both open and closed" in f for f in fails), fails


def test_dangling_reference_is_caught(tmp_path):
    repo, ip = build_repo(tmp_path)
    broken = HEALTHY_STATE.replace("See S-01 and D-02.", "See S-99 and D-02.")
    fails = failures(broken, repo, ip)
    assert any("referenced S-id is defined" in f and "S-99" in f for f in fails), fails


def test_dangling_decision_reference_is_caught(tmp_path):
    repo, ip = build_repo(tmp_path)
    broken = HEALTHY_STATE.replace("Body text referencing D-12.", "Body text referencing D-77.")
    fails = failures(broken, repo, ip)
    assert any("referenced D-id is defined" in f and "D-77" in f for f in fails), fails


def test_open_item_without_carried_is_caught(tmp_path):
    repo, ip = build_repo(tmp_path)
    broken = HEALTHY_STATE.replace("**S-02 — Another open item.** `carried: 0`",
                                   "**S-02 — Another open item.**")
    fails = failures(broken, repo, ip)
    assert any("declares `carried:`" in f and "S-02" in f for f in fails), fails


def test_carried_over_limit_is_caught(tmp_path):
    repo, ip = build_repo(tmp_path)
    broken = HEALTHY_STATE.replace("`carried: 2`", "`carried: 7`")
    fails = failures(broken, repo, ip)
    assert any("carried:5 limit" in f for f in fails), fails


def test_missing_section_is_caught(tmp_path):
    repo, ip = build_repo(tmp_path)
    broken = HEALTHY_STATE.replace("## 5. Measured results", "### 5. Measured results")
    fails = failures(broken, repo, ip)
    assert any("section 5 is present" in f for f in fails), fails


# ---------------------------------------------------------------------------
# The checker's own honesty
# ---------------------------------------------------------------------------

def test_a_crashing_verifier_fails_rather_than_passing(tmp_path, monkeypatch):
    """D-07 applied to the checker: a verifier that raises must not be read as a pass."""
    repo, ip = build_repo(tmp_path)

    def boom(_roots):
        raise RuntimeError("artifact unreadable")

    monkeypatch.setattr(cs, "CLAIMS", [("exploding", "`mean_pole`", boom)])
    fails = failures(HEALTHY_STATE, repo, ip)
    assert any("exploding" in f and "RuntimeError" in f for f in fails), fails


def test_coverage_names_what_it_cannot_check():
    """The anti-theater clause. If these disappear, a green run starts implying more than it
    earned -- which is how six incidents happened to people who thought they had checked."""
    blob = " ".join(cs.UNCHECKABLE).lower()
    assert "completeness" in blob
    assert "priority" in blob
    assert "statistical validity" in blob
    assert "test quality" in blob


def test_unavailable_artifact_skips_rather_than_passing(tmp_path):
    """A claim whose artifact cannot be found is UNVERIFIED, not verified. It must not
    increment the pass count."""
    repo, ip = build_repo(tmp_path)
    (ip / "ground_truth" / "rater_app" / "anchors.json").unlink()
    rep = cs.run_checks(HEALTHY_STATE, repo, ip)
    assert any("anchors.rubric_version" in s for s in rep.skips), rep.skips
