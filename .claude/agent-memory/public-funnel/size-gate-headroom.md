---
name: size-gate-headroom
description: Entry-chunk size headroom on / and why AccountModal is a lazy export from the intake barrel
metadata:
  type: project
---

2026-11-23: with every lane's uncommitted work in the tree, the entry chunk measured 101.07 kB gzip (gate 101 kB) after the G26/G29/G30 fixes. Making `AccountModal` lazy brought it to 99.72 kB. After `/start` and Login's intake replay were removed the same day: 99.44 kB JS, 10.23 kB CSS (gates 101 / 11).

**Why:** the modal opens only after a successful hero-form submit, so it never needed to be in the entry chunk. It is exported from `src/features/intake/index.ts` as `lazy(() => import(...))`. A static re-export from the barrel would pull it back into the entry chunk however LandingPage imports it (Vite's default moduleSideEffects keeps statically reachable modules).

**How to apply:** before adding to `/`, run `npm run build && npm run size`. Other lanes' concurrent edits move the number, so do not read a red gate as your own delta without checking. The next things that could go lazy are other post-interaction pieces of the landing page.
