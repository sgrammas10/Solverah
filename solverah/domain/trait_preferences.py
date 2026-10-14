"""Per-trait tolerance and must-have: the value object, its rules, and the flat zone.

Pure: no Flask, no SQLAlchemy. Storage is `assessment_store` (the D-01 doorway); the
HTTP surface is `GET/PUT /me/trait-preferences`. Decided by Sebastian 2026-10-13
(docs/PRODUCT_DECISIONS.md §2, "The six-trait match model").

WHAT THE USER STATES
--------------------
The 24 core items are the user's *current stated preference* on each of the six
traits. This step adds, per trait, how far a job may sit from that preference before
it starts to cost them, separately in each direction, in steps of the person lattice
(0.25):

* ``under_steps`` (0, 1 or 2): how much LESS of the trait than the user prefers the
  environment may provide without cost. "Under" means the environment under-supplies:
  ``env < person``.
* ``over_steps`` (0, 1 or 2): how much MORE of the trait than the user prefers the
  environment may provide without cost. "Over" means ``env > person``.
* ``must_have``: this trait is non-negotiable. At most two per user.

TWO GAP SIGN CONVENTIONS EXIST -- how "under" and "over" map onto each
-----------------------------------------------------------------------
* ``work_pulse/situation.py`` (Situation Report): ``gap = env - person``.
  under  <=>  gap < 0  -> compare ``|gap|`` with the under zone;
  over   <=>  gap > 0  -> compare ``|gap|`` with the over zone.
  (Its own ``UNDER`` / ``OVER`` direction labels already mean exactly this.)
* ``causal_graph/v1_model/match_core.fit_gap`` (the match model):
  ``gap = person - env``.
  under  <=>  gap > 0;   over  <=>  gap < 0.

``flat_zones`` returns ``(under_zone, over_zone)`` per trait and never a signed
value, so each consumer applies its own sign rule above.

UNANSWERED IS NOT "ONE STEP"
----------------------------
A user who never answered, or skipped, is UNANSWERED: ``flat_zones`` returns None and
every caller takes today's code path unchanged (the 0.15 aligned band in the Situation
Report, ``flat_zones=None`` in the model). Ruling 2026-10-13 ("Pipeline calls", Q3)
replaced the earlier "1-step default". Never substitute a default tolerance here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "ALIGNED_FLOOR",
    "FORM_VERSION",
    "MAX_MUST_HAVES",
    "MAX_STEPS",
    "STEP_SIZE",
    "TRAIT_KEYS",
    "TraitPreference",
    "TraitPreferenceError",
    "flat_zones",
    "must_have_keys",
    "parse_trait_preferences",
    "unanswered_preferences",
    "validate_trait_preferences",
]

#: The six traits, in the product's fixed order. Must equal
#: `work_pulse.situation.DIMENSIONS` and the core item bank's dimensions
#: (tests/test_trait_preferences.py pins both).
TRAIT_KEYS: tuple[str, ...] = (
    "autonomy",
    "pace",
    "collaboration",
    "feedback",
    "innovation",
    "decision",
)

#: One step of the person lattice (0, 0.25, 0.5, 0.75, 1.0): the smallest change in a
#: core dimension score four items can produce.
STEP_SIZE = 0.25

#: Largest tolerance a user can state, per direction.
MAX_STEPS = 2

#: The Situation Report's `aligned` band (`work_pulse.situation.ALIGNED_THRESHOLDS`),
#: the measurement-noise floor. A stated tolerance never narrows the flat zone below it.
ALIGNED_FLOOR = 0.15

#: At most this many must-have traits per user (enforced server-side).
MAX_MUST_HAVES = 2

#: Which wording of the questions produced a sitting. Bump when the meaning of the
#: questions changes, not for copy polish.
FORM_VERSION = "tp-v1-2026-10-13"


@dataclass(frozen=True)
class TraitPreference:
    """One trait's tolerance and must-have flag, as of the user's latest sitting.

    Unanswered: ``under_steps`` and ``over_steps`` are None, ``must_have`` is False,
    ``answered`` is False. Never a partially answered value: a sitting answers all six.
    """

    dimension_key: str
    under_steps: int | None
    over_steps: int | None
    must_have: bool
    answered: bool


class TraitPreferenceError(ValueError):
    """A submitted set of trait preferences breaks a rule. Carries field-level errors in
    the Problem Details ``errors`` shape (``field``, ``code``, ``detail``)."""

    def __init__(self, errors: list[dict[str, str]]):
        self.errors = errors
        super().__init__(errors[0]["detail"] if errors else "invalid trait preferences")


def unanswered_preferences() -> dict[str, TraitPreference]:
    """All six traits, unanswered."""
    return {
        key: TraitPreference(
            dimension_key=key,
            under_steps=None,
            over_steps=None,
            must_have=False,
            answered=False,
        )
        for key in TRAIT_KEYS
    }


def _is_step(value: Any) -> bool:
    # bool is an int subclass; True is not a step count.
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_STEPS


def validate_trait_preferences(prefs: Mapping[str, TraitPreference]) -> None:
    """Raise TraitPreferenceError unless ``prefs`` is one complete, answered sitting:
    all six traits, each answered with steps in 0..MAX_STEPS, at most MAX_MUST_HAVES
    must-haves."""
    errors: list[dict[str, str]] = []
    missing = [k for k in TRAIT_KEYS if k not in prefs]
    if missing:
        errors.append({
            "field": "traits",
            "code": "missing_trait",
            "detail": "every trait must be answered; missing: %s" % ", ".join(missing),
        })
    unknown = sorted(k for k in prefs if k not in TRAIT_KEYS)
    for key in unknown:
        errors.append({
            "field": "traits",
            "code": "unknown_trait",
            "detail": "unknown trait %r" % key,
        })
    for key in TRAIT_KEYS:
        pref = prefs.get(key)
        if pref is None:
            continue
        if pref.dimension_key != key:
            errors.append({
                "field": "traits.%s" % key,
                "code": "unknown_trait",
                "detail": "entry for %r names %r" % (key, pref.dimension_key),
            })
        if not pref.answered:
            errors.append({
                "field": "traits.%s" % key,
                "code": "missing_trait",
                "detail": "%s is not answered" % key,
            })
        for name in ("under_steps", "over_steps"):
            if not _is_step(getattr(pref, name)):
                errors.append({
                    "field": "traits.%s.%s" % (key, name),
                    "code": "steps_out_of_range",
                    "detail": "%s.%s must be a whole number from 0 to %d"
                    % (key, name, MAX_STEPS),
                })
        if not isinstance(pref.must_have, bool):
            errors.append({
                "field": "traits.%s.must_have" % key,
                "code": "invalid_type",
                "detail": "%s.must_have must be true or false" % key,
            })
    flagged = [k for k in TRAIT_KEYS if k in prefs and prefs[k].must_have is True]
    if len(flagged) > MAX_MUST_HAVES:
        errors.append({
            "field": "traits",
            "code": "too_many_must_haves",
            "detail": "at most %d traits can be must-haves; got %d (%s)"
            % (MAX_MUST_HAVES, len(flagged), ", ".join(flagged)),
        })
    if errors:
        raise TraitPreferenceError(errors)


def parse_trait_preferences(raw: Any) -> dict[str, TraitPreference]:
    """Turn a request's ``traits`` list into a validated sitting, or raise
    TraitPreferenceError.

    Strict on types on purpose: the request schema's lax coercion is documentation,
    and this is what decides. ``"1"`` is not a step count and ``1`` is not a boolean.
    """
    if not isinstance(raw, list):
        raise TraitPreferenceError([{
            "field": "traits",
            "code": "invalid_type",
            "detail": "traits must be a list of the six traits",
        }])
    errors: list[dict[str, str]] = []
    prefs: dict[str, TraitPreference] = {}
    for index, entry in enumerate(raw):
        where = "traits.%d" % index
        if not isinstance(entry, dict):
            errors.append({
                "field": where, "code": "invalid_type", "detail": "%s must be an object" % where,
            })
            continue
        key = entry.get("dimension_key")
        if not isinstance(key, str) or key not in TRAIT_KEYS:
            errors.append({
                "field": "%s.dimension_key" % where,
                "code": "unknown_trait",
                "detail": "unknown trait %r; expected one of %s" % (key, ", ".join(TRAIT_KEYS)),
            })
            continue
        if key in prefs:
            errors.append({
                "field": "%s.dimension_key" % where,
                "code": "duplicate_trait",
                "detail": "%s appears more than once" % key,
            })
            continue
        prefs[key] = TraitPreference(
            dimension_key=key,
            under_steps=entry.get("under_steps"),
            over_steps=entry.get("over_steps"),
            must_have=entry.get("must_have"),
            answered=True,
        )
    if errors:
        raise TraitPreferenceError(errors)
    validate_trait_preferences(prefs)
    return prefs


def _is_answered_set(prefs: Mapping[str, TraitPreference]) -> bool:
    """True if the set is one answered sitting, False if wholly unanswered. A set that
    is neither (missing traits, or answered and unanswered mixed) is a caller bug:
    raised, never quietly read as "unanswered" (D-07)."""
    missing = [k for k in TRAIT_KEYS if k not in prefs]
    if missing:
        raise ValueError("trait preferences missing %s" % ", ".join(missing))
    answered = {prefs[k].answered for k in TRAIT_KEYS}
    if answered == {True, False}:
        raise ValueError("trait preferences mix answered and unanswered traits")
    return answered == {True}


def flat_zones(
    prefs: Mapping[str, TraitPreference],
) -> dict[str, tuple[float, float]] | None:
    """``{trait: (under_zone, over_zone)}``, or None for a user who has not answered.

    zone = ``max(ALIGNED_FLOOR, steps * STEP_SIZE)``: 0 steps -> 0.15, 1 -> 0.25,
    2 -> 0.5. A gap whose magnitude is inside the zone for its direction costs nothing.
    See the module docstring for which sign of each convention's gap is "under".

    None means "take today's path" -- callers must not build zones of their own for it.
    """
    if not _is_answered_set(prefs):
        return None
    return {
        key: (
            max(ALIGNED_FLOOR, prefs[key].under_steps * STEP_SIZE),
            max(ALIGNED_FLOOR, prefs[key].over_steps * STEP_SIZE),
        )
        for key in TRAIT_KEYS
    }


def must_have_keys(prefs: Mapping[str, TraitPreference]) -> frozenset[str]:
    """The traits flagged must-have. Empty for an unanswered user."""
    return frozenset(
        key for key, pref in prefs.items() if pref.answered and pref.must_have
    )
