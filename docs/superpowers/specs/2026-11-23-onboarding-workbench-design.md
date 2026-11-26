# Onboarding Workbench — design (approved 2026-11-23)

## Intent
A new account lands on 5–7 competing prompts with no order (intake modal, Work Pulse
banner, permanent amber profile alert, Situation card, Pulse invite, career-status rec).
Sebastian and Julie need one place to agree the first-run flow live on a Teams call; the
agreed flow becomes the build spec for the site.

## Goals / non-goals / anti-goals
- Goals: edit a proposed flow live; see each step's cost (minutes), data collected and what
  it unlocks; get flagged when an edit breaks a site dependency; leave with decisions
  Claude can read back and build from.
- Non-goals: no site code; no final copy (Julie revises on the built product); not the full
  conversational Reflection Engine (V1 shows where it plugs in).
- Anti-goal: a pretty static map nobody can change mid-call.

## Approaches
- **A. claude.ai artifact page with a shared `db` store (CHOSEN).** Live edits saved; Claude
  reads decisions back with ArtifactData; Julie can open it between calls (async-only).
  Lives outside the repo, so the exported/read-back spec is what gets committed.
- B. Single HTML file in the repo with localStorage. Versioned, but only on one machine.
- C. Hidden `/dev/onboarding-lab` route in Solverah. Most realistic, but touches App.tsx,
  guards and size gates for a planning tool.

## The page
1. Flow board — columns Arrive / Understand / Clarify / Guide / Continue (Julie's loop) plus
   an "Off the first run" lane. Cards drag (plus move buttons for keyboard/touch). Each card:
   what the user sees, data collected, unlocks, minutes, Julie principle, status pill
   (keep / change / cut / undecided), career moments it applies to, notes, decision.
2. Walk as a user — pick a career moment or one of Julie's worked-example personas; shows
   the exact path and total minutes.
3. Site needs check — live dependency rules (career status before Environment Report,
   Work Pulse before Situation Report / CompanyLens / tolerance, Env Report before Situation
   Report and never for first_job, Manager Match before Manager Profile, Paths need status +
   skills, confirm step needs a report, first-run length warning).
4. Today panel — the current new-user experience, read-only.
5. Questions for Julie — editable list with answer fields.
6. Export — markdown spec via copy button / download.

## Calls made by Claude
Shared db store (Claude reads decisions back); Solverah cream/forest tokens, Archivo +
Public Sans; private until Sebastian shares (sharing can't be changed from Claude's tools).
The seeded draft flow is a proposal to be edited on the call, not a decision.
