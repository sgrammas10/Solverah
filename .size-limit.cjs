/**
 * Bundle budget (ARCHITECTURE.md 6.5 -- "Budget | size-limit | Fails CI on bundle regression").
 *
 * WHAT IS MEASURED
 *
 * Only what the browser must download before anything renders: the entry chunk
 * referenced by `<script type="module">` in dist/index.html, and the one stylesheet
 * linked beside it. Every other chunk in dist/assets is reached through a
 * `lazy(() => import(...))` in App.tsx and is not part of the first paint, so
 * putting it in the budget would fail the gate for code the user never waited on.
 *
 * The entry is matched as `entry-*.js`, not `index-*.js`, and that is load-bearing.
 * Rollup names a lazy chunk after its source module, and a module named `index.ts`
 * produces `assets/index-<hash>.js` sitting next to the entry's own
 * `assets/index-<hash>.js`. At the time of writing that second file is the 117 kB
 * react-markdown chunk. A glob of `index-*.js` therefore matches two files and
 * quietly measures a number that is neither the entry nor the initial payload.
 * vite.config.ts pins the entry to `assets/entry-[hash].js` so this glob is exact.
 *
 * WHERE THE NUMBERS COME FROM
 *
 * Measured, not aspired to. A budget the build already exceeds is a broken gate on
 * day one -- it reports red before anyone has regressed anything, and the first
 * response to a gate that is red by construction is to raise it or delete it.
 *
 * Measured 2026-08-27 at 79969d3 by this same config (`npm run size`):
 *
 *     entry JS   94.44 kB gzipped
 *     CSS         8.94 kB gzipped
 *
 * The limits below sit ~5 % above those, which is deliberate on two counts. It is
 * tight enough that a new dependency on the eager path trips it -- adding a chunk
 * the size of the react-markdown one would blow through it many times over -- and
 * loose enough to absorb the few hundred bytes that gzip output can shift by
 * between zlib versions, since this is measured on Node 22 locally and Node 24 on
 * the runner.
 *
 * Phase 4b took the entry from 774 kB -> 326 kB raw and 215 kB -> 95 kB gzipped by
 * moving the route modules behind React.lazy. This budget exists to keep that.
 *
 * gzip rather than brotli -- size-limit v12 defaults to brotli -- because every
 * bundle figure recorded for this project is a gzip figure, and a budget that
 * cannot be compared against the numbers in the phase notes invites the wrong
 * conclusion when it moves.
 *
 * WHEN THIS FAILS
 *
 * Find what landed on the eager path before raising the number. `npx vite build`
 * prints per-chunk sizes, and something newly imported at module scope by App.tsx
 * or one of its static imports is the usual cause. Raising the limit is
 * occasionally right, but it is the second thing to try, not the first.
 */
module.exports = [
  {
    name: "Initial JS (entry chunk)",
    path: "dist/assets/entry-*.js",
    gzip: true,
    limit: "99 kB",
  },
  {
    name: "Initial CSS",
    path: "dist/assets/*.css",
    gzip: true,
    limit: "9.5 kB",
  },
];
