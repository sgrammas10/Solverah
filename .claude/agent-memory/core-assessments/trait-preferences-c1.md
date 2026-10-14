---
name: trait-preferences-c1
description: Per-trait tolerance + must-have step (six-trait model, chunk C1, built 2026-10-13, uncommitted) -- where it lives, the 400/422 split, the D-15 position question left open
metadata:
  type: project
---

Built 2026-10-13 as lane C1 of the CompanyLens six-trait build (orchestrated; not committed at time of writing). Person-side table is behind the D-01 doorway: `assessment_store.get_trait_preferences(db, user_id)` / `save_trait_preferences(db, user_id, prefs) -> sitting hex`; rules + `flat_zones` / `must_have_keys` in `solverah/domain/trait_preferences.py`. Its class and table names were ADDED to the D-01 guard's PERSON_SIDE_NAMES, so tests must never spell them (the store test reads through the doorway only). Routes GET/PUT `/me/trait-preferences` live in the assessments blueprint. Frontend: `TraitPreferencesStep` shown on /work-pulse right after a sitting, retake page `/trait-preferences`.

Decisions taken here: rule violations are a 400 Problem (`invalid_trait_preferences`, per-entry codes) via a `ValidationError` subclass with status 400; a body that does not match the schema is still the enforcement hook's 422. Unanswered = no rows = `flat_zones` None, never a default step. Retake entry on the completion card is a BUTTON, because a WorkPulsePage test pins "no links on the completion card" (D-15).

**Why:** Sebastian's 2026-10-13 ruling (PRODUCT_DECISIONS §2 six-trait entry; unanswered = today's behaviour).

**How to apply:** open question sent to Sebastian -- the brief asked to show each trait's "current position in plain words", which is a person-side score on the wire (D-15); NOT built, traits are described instead. export/delete coverage for the table is auth-accounts' hand-off (`export_person_side` already returns a `trait_preferences` key). See [[core-retakes-live]].
