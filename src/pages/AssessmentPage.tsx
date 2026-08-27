/**
 * AssessmentPage -- superseded 2026-08-19.
 *
 * The person-side assessment ships under the Work Pulse name and lives at /work-pulse
 * (WorkPulsePage.tsx, which also carries this page's load-bearing copy and the reasoning
 * behind it -- read its header before editing that copy). This route survives only as a
 * redirect so that any link or bookmark minted while /assessment was the canonical path
 * keeps working. Do not mount a second copy of the form here: two entry points with
 * different framing collect answers under different self-presentation pressure, which is
 * exactly the variable S-43 existed to pin down.
 */
import { Navigate } from "react-router-dom";

export default function AssessmentPage() {
  return <Navigate to="/work-pulse" replace />;
}
