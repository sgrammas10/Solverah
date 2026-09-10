/**
 * Public surface of the assessments slice — the only legal import path for
 * other feature slices (ARCHITECTURE.md 6.4).
 *
 * The instrument pages (WorkPulsePage, FocusTypePage, ManagerMatch*, …) are
 * consumed only by src/app's route-level lazy() imports, which deep-import by
 * design, so they are not exported here. FocusTypeResult is re-exported
 * type-only, so the barrel adds no runtime import of the page module.
 */
export { useWP } from "./useWP";
export type { WpApiResponse } from "./useWP";
export { useWorkPulseResult, workPulseResultKeys } from "./useWorkPulseResult";
export { useMM } from "./useMM";
export type { MMResult } from "./useMM";
export { useManagerMatchResult, managerMatchResultKeys } from "./useManagerMatchResult";
export { useManagerPlaybook, managerPlaybookKeys } from "./useManagerPlaybook";
export type { ManagerPlaybook, ManagerPlaybookData, ManagerPlaybookDimensionEntry } from "./useManagerPlaybook";
export {
  isKnownScoringPhase,
  useScoringJobStatus,
  useStartScoringJob,
} from "./useScoringJob";
export type { ScoringJobPhase } from "./useScoringJob";
export type { FocusTypeResult } from "./components/FocusTypePage";
export { default as WorkPulseBanner } from "./components/WorkPulseBanner";
export { default as WorkPulseUnlock } from "./components/WorkPulseUnlock";
