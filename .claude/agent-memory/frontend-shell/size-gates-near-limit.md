---
name: size-gates-near-limit
description: Entry JS and initial CSS headroom against the 101 kB / 11 kB size-limit gates, last measured 2026-10-14
metadata:
  type: project
---

Measured 2026-10-14 with the six-trait CompanyLens build in the tree: entry JS 99.87 kB gzip
(limit 101, ~1.1 kB headroom), initial CSS 10.51 kB gzip (limit 11, ~0.5 kB headroom).

**Why:** both gates are close; one new globally-imported component or a burst of new
Tailwind classes used on the entry path can tip them.
**How to apply:** when reviewing a route line or shared-code change, run `npm run build &&
npm run size` and update these numbers. New feature code must stay behind `lazy()`.
