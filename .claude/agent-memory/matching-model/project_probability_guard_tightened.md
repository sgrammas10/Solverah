---
name: probability-guard-tightened
description: 2026-10-14 UNCOMMITTED: assertNoProbabilityText now rejects bare decimals and ratings; frontend-shell review follow-ups (a)(b)(c) done
metadata:
  type: project
---

Guard in tests/msw/companyLensHandlers.ts adds DECIMAL and RATED regexes; self-tests in src/features/matching/noProbability.test.tsx; companies sweep asserts LEGACY_PROFILE raw values ("0.82","3.9") never render. No false positives found in the UI. researchProgresses wrong run_id returns undefined; researchRefused/DAILY_LIMIT_PROBLEM/companyProfileReply typed from schema.ts.

**TRAP:** a Python heredoc turned `\b` into literal backspace characters in a regex (Read output hides them). Check with `grep -c $'\x08'`; write regex edits via a perl file, not a heredoc.
