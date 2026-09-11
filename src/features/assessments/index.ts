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
export {
  isAlignedEntry,
  isFirstJobRefusal,
  isNoCoreSittingRefusal,
  situationReportKeys,
  useRecalibrateSituationReport,
  useSituationReport,
  useSubmitEnvironmentReport,
} from "./useSituationReport";
export type {
  AlignedDimensionEntry,
  EnvironmentReportSubmission,
  SituationBucket,
  SituationComplete,
  SituationDimension,
  SituationDimensionEntry,
  SituationDirection,
  SituationManagerSection,
  SituationReport,
  StrainDimensionEntry,
} from "./useSituationReport";
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
export { default as PulseDashboardCard } from "./components/PulseDashboardCard";
export {
  pulseKeys,
  usePulseHistory,
  usePulseNextCheckin,
  usePulseSettings,
  useSubmitPulseCheckin,
  useSubmitPulseEvent,
  useUpdatePulseSettings,
} from "./usePulse";
export type {
  PulseCadence,
  PulseCheckinItem,
  PulseCheckinRecord,
  PulseCheckinSubmission,
  PulseDimension,
  PulseEventRecord,
  PulseEventSubmission,
  PulseEventType,
  PulseHistory,
  PulseNextCheckin,
  PulseOutcomeItem,
  PulseSettableCadence,
} from "./usePulse";
