/**
 * The synthetic occupation corpus the Workstream F real-stack flow runs on.
 *
 * WHY SYNTHETIC, AND WHY THAT IS NOT A COMPROMISE. The real artifact is 6 MB of
 * float32 written by `flask corpus build` against live O*NET, and it lives
 * OUTSIDE the repo on purpose: the guard tests walk the whole tree, and a 6 MB
 * binary in `tests/fixtures` would fail them. It reaches a runner only through
 * S3 -- `SOLVERAH_CORPUS_S3_KEY` plus the app bucket -- and that upload is
 * Sebastian's trigger, deliberately not automated (BUILD_PLAN F-1, F-8 box 1).
 *
 * F-8 box 7 asked for the real-stack flow to run against F-3's committed 26-row
 * fixture so that no runner would need the artifact. **It cannot today, and the
 * reason is recorded here rather than only in a commit message:** the fixture's
 * vectors are EIGHT-dimensional -- deliberately, so every cosine in
 * `test_occupation_retrieval.py` is checkable by hand -- while every real
 * embedding is 1,536. `adjacent` blends the corpus anchor with the user's
 * skills document in one expression (`path_scoring._blend`), and numpy will not
 * broadcast an 8-vector against a 1,536-vector. The fixture is usable with a
 * FAKE embedder and unusable with a real one.
 *
 * Closing that means regenerating this fixture at 1,536 dimensions -- 26 x 1536
 * x 4 = 160 KB, small enough to commit -- and rewriting the hand-written vector
 * assertions in `test_occupation_retrieval.py` that depend on its readable
 * planes. That is F-3's file and its own piece of work.
 *
 * Until then `path_intelligence.spec.ts` runs against whatever corpus the API
 * serves, and the codes below are used only when `E2E_CORPUS_IS_FIXTURE=1` says
 * the fixture is in play -- as the check that PROVES it, rather than a README
 * line claiming it.
 */

/** Where the API must have `SOLVERAH_CORPUS_PATH` pointed, relative to the repo root. */
export const E2E_CORPUS_DIR = "tests/fixtures/corpus";

/** Every O*NET code in `onet_corpus_testfix.json`, in the order it stores them. */
export const E2E_CORPUS_CODES: readonly string[] = [
  "11-1021.00", // General and Operations Managers
  "11-3021.00", // Computer and Information Systems Managers
  "11-9199.00", // Managers, All Other          -- retrieval filters residuals
  "13-1199.00", // Business Operations Specialists, All Other
  "13-2011.00", // Accountants and Auditors
  "15-1243.00", // Database Architects
  "15-1299.00", // Computer Occupations, All Other
  "15-2031.00", // Operations Research Analysts
  "15-2041.00", // Statisticians
  "15-2051.00", // Data Scientists
  "15-2099.00", // Mathematical Science Occupations, All Other
  "19-3094.00", // Political Scientists
  "25-2021.00", // Elementary School Teachers, Except Special Education
  "29-1141.00", // Registered Nurses
  "29-1299.00", // Healthcare Diagnosing or Treating Practitioners, All Other
  "29-2061.00", // Licensed Practical and Licensed Vocational Nurses
  "31-1131.00", // Nursing Assistants
  "31-9099.00", // Healthcare Support Workers, All Other
  "35-3023.00", // Fast Food and Counter Workers
  "39-9011.00", // Childcare Workers
  "47-2031.00", // Carpenters
  "47-2111.00", // Electricians
  "47-4099.00", // Construction and Related Workers, All Other
  "47-5041.00", // Continuous Mining Machine Operators
  "49-3023.00", // Automotive Service Technicians and Mechanics
  "53-7062.00", // Laborers and Freight, Stock, and Material Movers, Hand
];

/**
 * The residual buckets. `occupation_retrieval` filters these from every result
 * by title suffix, so a suggestion carrying one is a retrieval regression and
 * not a ranking opinion.
 */
export const E2E_CORPUS_RESIDUALS: readonly string[] = [
  "11-9199.00",
  "13-1199.00",
  "15-1299.00",
  "15-2099.00",
  "29-1299.00",
  "31-9099.00",
  "47-4099.00",
];
