/**
 * Public surface of the intake slice — the only legal import path for other
 * feature slices (ARCHITECTURE.md 6.4).
 *
 * CareerIntakePage is consumed only by src/app's route-level lazy() import,
 * which deep-imports by design, so it is not exported here. The default
 * exports are re-exported as named so cross-slice consumers import
 * `{ IntakeForm }` etc. from this barrel.
 */
import { lazy } from "react";

export { useIntakeForm } from "./useIntakeForm";
export { default as IntakeForm } from "./components/IntakeForm";
// Lazy, and only lazy: a static re-export here would keep the module in the
// landing page's entry chunk however the page imported it. It opens only
// after a successful submit, so the page renders it inside <Suspense>.
export const AccountModal = lazy(() => import("./components/AccountModal"));
export { default as IntakePromptModal } from "./components/IntakePromptModal";
export { default as TierBar } from "./components/TierBar";
