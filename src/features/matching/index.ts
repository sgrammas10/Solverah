/**
 * Public surface of the matching slice — the only legal import path for
 * other feature slices (ARCHITECTURE.md 6.4).
 *
 * The companies slice (CompanyDetailPage, the per-company six-trait read) shares
 * CompanyLens's query keys, words, styles, polling and research form, so they
 * cross here. Feed, SearchResults and CompanyLensPage are still reached only
 * through src/app's route-level lazy() imports, which deep-import by design;
 * none of them is exported, so this barrel never pulls a page into another
 * page's chunk.
 */
export {
  companyLensKeys,
  useResearchCompany,
  type CoverageCounts,
  type Direction,
  type FlagCounts,
  type NextStep,
  type TraitFlag,
  type TraitKey,
} from "./useCompanyLens";
export { DEFAULT_POLL_TIMING, pollDelay, usePoll, type PollTiming } from "./usePoll";
export * from "./companyLensCopy";
export * from "./lensStyles";
export { FlagBadge, MustHaveBadge, NextStepChip } from "./components/LensBits";
export { default as ResearchCompanyForm } from "./components/ResearchCompanyForm";
