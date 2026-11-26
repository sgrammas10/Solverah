# Onboarding Workbench Implementation Plan

> **For agentic workers:** executed natively by the orchestrator (user said "go for it").

**Goal:** a private claude.ai artifact page where Sebastian and Julie edit the post-signup flow live.

**Architecture:** one self-contained HTML page (vanilla JS, no libraries) declaring
`capabilities: {db:{}, user:{}, downloads:true}`. State lives in two db collections; the page
subscribes once to each and renders from snapshots. Seed data is written with ArtifactData
after the first publish, never hardcoded into the page.

**Tech Stack:** HTML/CSS/JS, Artifact runtime contract 0.2.98, Google Fonts (Archivo, Public Sans).

**Spec:** docs/superpowers/specs/2026-11-23-onboarding-workbench-design.md

## Global Constraints
- Colors from DESIGN.md: cream #FAF7F2, forest #1B4332/#2D6A4F/#40916C/#D8F3DC, ink #1A1A1A; dark theme mirrored via tokens.
- All db values rendered with textContent (other viewers' text is untrusted).
- One write per doc at a time; text fields debounce-save on pause/blur.
- Works at 400px; no horizontal body scroll except the board's own scroller.

## Data model
- `steps/{id}`: key, title, phase (arrive|understand|clarify|guide|continue|off), order (number),
  sees, collects, unlocks, minutes (number), principle, status (keep|change|cut|undecided),
  moments (string[] of moment ids), notes, decision, updatedBy, updatedAt.
- `questions/{id}`: text, context, answer, open (bool), order, updatedBy, updatedAt.
- Moments (static in page): off_at_work, stay_or_go, job_hunting, between_jobs, first_job, curious.

## Review Focus
1. Empty db (before seed / new viewer offline): designed empty state, 10 s timeout note.
2. Two people editing the same card: last-writer-wins, field-level `update` only for the field changed.
3. Read-only viewer (Viewer/Commenter): inputs disabled after `can("data.write")` false or a rejected write.
4. Custom step added on the call (key `custom`): excluded from rules, included in paths/minutes.
5. Drag to the same position / to an empty column: order computed as midpoint or +1, single write.

### Task 1: Page + publish
- [ ] Write page to scratchpad `onboarding-workbench/index.html`; one preview look; publish with capabilities.
### Task 2: Seed
- [ ] ArtifactData batch set: ~22 steps, ~7 questions.
### Task 3: Functional pass
- [ ] ArtifactData list `steps` and `questions`; report to Sebastian in one line.
