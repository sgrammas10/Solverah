# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Individuals navigating career decisions — job seekers and early/mid-career professionals — not employers or recruiters. Solverah is explicitly not a dual-sided hiring marketplace: it does not make hiring, promotion, or compensation decisions, and user data is never shown to employers (enforced in code, not just a policy statement).

## Product Purpose

Solverah is a career development platform, not a job board. It combines:
- Assessments (Work Pulse, Work Pulse Lite, Focus Type, Manager Match, a core assessment) that surface a person's work-style and culture-fit dimensions.
- A causal Bayesian model that matches those dimensions against company culture profiles.
- Deterministic resume parsing.
- O*NET-backed career-path intelligence (task/condition-level "more or less of this" comparisons against the user's own current role, not a percentage score).

Success means the user leaves with structured, interpretive insight into how they work and where they'd thrive — not a ranked score or a job-search shortcut.

## Positioning

Branded internally as "Authentic Intelligence": structured frameworks, rules-based logic, and automated analysis, paired with human review of every submission — explicitly positioned against black-box AI scoring and against keyword/ATS-style job matching. The differentiating claim: conditions and context over labels and scores ("we don't score you against a template").

A separate internal methodology document (the "Reflection Engine," V1/V2, dated 2026-09-18) describes a future conversational reasoning model: treat a person's statements as evidence not conclusions, distinguish labels ("Director," "stability," "having a voice") from the substance behind them, hold multiple competing interpretations, offer an interpretation back for the person to confirm/correct rather than scoring them, and know when understanding is sufficient without a full profile. **Verified 2026-09-22: this is not implemented anywhere in the codebase** — no matching routes, components, or naming exist. The live product's only free-text/LLM surfaces are static assessment forms plus a generic Q&A chatbot at `/agent`, unrelated to this reflect/confirm loop. Treat the document as future vision and a source of positioning language, never as a description of current capability — do not let landing-page or in-product copy imply a live conversational interpretation loop exists today. Its "labels are not evidence" principle already matches shipped positioning ("we read beyond job titles and buzzwords") and can sharpen existing copy without overclaiming.

## Operating Context

React/TypeScript SPA (`src/`, Vite, Tailwind, React Router, TanStack Query) talking to a Flask/Python monolith API. Users land on the marketing site, submit an intake (resume + background), create an account, and move through assessments and matching/intelligence features while signed in.

## Capabilities and Constraints

- Account creation and sign-in are already fully implemented (not just a waitlist form) — `IntakeForm` + `AccountModal` on the current homepage already create real accounts.
- Work Pulse and Work Pulse Lite are live; Work Pulse Pro (deeper pattern analysis, CompanyLens™ company matching) is roadmap, not built — do not present it as available.
- Data handling is a real, enforced constraint, not just marketing copy: user data is never sold and never shown to employers (backed by a dedicated test suite in the codebase).
- No real testimonials, customer logos, or usage-count evidence exist yet — do not fabricate them.

## Brand Commitments

Name: Solverah. "Work Pulse™" and "Authentic Intelligence" are established product/proprietary terms already in use in-product and should be preserved as terminology (not necessarily as visual treatment). No binding visual identity (colors, type, logo mark, imagery) — fully open for this redesign to replace.

## Evidence on Hand

- O*NET 30.3 Database attribution (CC BY 4.0, USDOL/ETA) is a real licensing obligation that must stay on any page using O*NET-derived content — currently in the footer of `LandingPage.tsx`.
- Existing FAQ content (what Authentic Intelligence is, how it differs from AI, what data it uses, that it doesn't make employment decisions) reflects real product policy — preserve the substance; copy wording itself may be rewritten.

## Product Principles

1. Context over keywords — read the full picture, not titles or buzzwords.
2. Human judgment stays in the loop — automation supports, never replaces, decisions.
3. Conditions and fit over scores and rankings.
4. Privacy by default — user data is never sold or shown to employers.
5. Individuals are the customer, not employers — do not reintroduce a dual-sided/recruiter framing (an old orphaned `/landing` route still has this stale framing; out of scope here, flagged separately).
