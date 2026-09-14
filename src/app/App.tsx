/**
 * App.tsx — Root React component and client-side routing configuration.
 *
 * Route structure:
 *   /                         PrelaunchLandingPage (public, has its own nav)
 *   /landing                  LandingPage (public)
 *   /login, /register         Auth pages (public)
 *   /verify-email             OTP confirmation page (public)
 *   /quiz-preview/*           Guest quiz previews (public, rate-limited on backend)
 *   /agent                    AI agent chat (job-seeker)
 *   /feed, /search            Shared authenticated routes (job-seeker)
 *   /job-seeker/*             Job-seeker-only routes
 *   /settings                 Account settings — data export + account deletion
 *                             (job-seeker; the screen the legal pages promise)
 *   /career-quizzes/*         Authenticated quiz routes
 *   /quiz-insights            Authenticated quiz insights
 *   /environment-report       Environment-side instrument (job-seeker)
 *   /situation-report         Situation Report (job-seeker)
 *   /pulse, /pulse/trend      Pulse check-in + trend (job-seeker; /pulse is
 *                             the Pulse prompt email's deep-link target)
 *   /trust                    Transparency page (job-seeker)
 *   *                         Catch-all → redirect to /
 *
 * Access control:
 *   The authenticated routes are children of one pathless `RequireAuth` layout
 *   route (ARCHITECTURE.md 6.3). It holds its subtree back while the session
 *   probe is in flight, redirects to /login when nobody is signed in, and to /
 *   when the signed-in role is not allowed. Public routes are its siblings and
 *   render with zero wait on `GET /auth/session` — AuthProvider no longer
 *   gates the tree; see RequireAuth.tsx.
 *
 * Header visibility:
 *   The global Header is hidden on the "/" route because PrelaunchLandingPage
 *   renders its own navigation (LandingNav).  All other routes show the Header.
 */
import React, { lazy } from "react";
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "../features/auth/AuthContext.tsx";
import { ProfileCacheSync } from "../features/profile";
import Header from "./Header";
import { RequireAuth } from "./RequireAuth";
import { RouteErrorBoundary } from "./RouteErrorBoundary";
import { createQueryClient } from "../shared/api/queryClient";

/*
 * Route modules: eager for the entry surface, lazy for everything else.
 *
 * Phase 4b. Before this every one of the 30 page modules below was a static
 * import, so the single bundle the landing page downloaded contained the whole
 * authenticated application -- every quiz, every results screen, react-markdown
 * and dnd-kit included -- for a visitor who had not signed in and might never.
 *
 * The split line is "can this be someone's first paint?", not "is it public".
 *   - "/" is the entry point.
 *   - /login and /register are linked straight off it, and are where a returning
 *     visitor goes first.
 *   - /verify-email, /forgot-password and /forgot-password/verify are reached by
 *     clicking a link in an email, which is a cold load with no chunk cached.
 * Splitting any of those would add a round trip in front of first paint, which
 * is the cost this change exists to remove, not to relocate.
 *
 * Everything else is reached by an in-app navigation, where the shell is already
 * on screen and RouteFallback can render inside it. That includes the public
 * marketing and legal pages: they are real destinations, but nobody's session
 * starts there often enough to pay for them on every landing-page load.
 */

// ── Eager: the entry surface ────────────────────────────────────────────────
import PrelaunchLandingPage from "../features/landing/components/prelaunchlandingpage";
import Login from "../features/auth/components/Login";
import Register from "../features/auth/components/Register";
import ConfirmEmail from "../features/auth/components/ConfirmEmail";
import CheckEmail from "../features/auth/components/CheckEmail";
import ForgotPassword from "../features/auth/components/ForgotPassword";
import ForgotPasswordVerify from "../features/auth/components/ForgotPasswordVerify";

// ── Lazy: quiz components ───────────────────────────────────────────────────
const CareerQuizzes = lazy(() => import("../features/intelligence/components/CareerQuizzes"));
const NextChapterYourWayQuiz = lazy(() => import("../features/intelligence/components/NextChapterYourWayQuiz"));
const SolverahYourFutureYourWayQuiz = lazy(
  () => import("../features/intelligence/components/SolverahYourFutureYourWayQuiz"),
);

// ── Lazy: public pages behind an in-app navigation ──────────────────────────
const LandingPage = lazy(() => import("../features/landing/components/LandingPage"));
const GuestQuizPreview = lazy(() => import("../features/intelligence/components/GuestQuizPreview"));
const GuestQuizInsights = lazy(() => import("../features/intelligence/components/GuestQuizInsights"));
const CareerIntakePage = lazy(() => import("../features/intake/components/CareerIntakePage"));
const LegalPage = lazy(() => import("../features/landing/components/LegalPage"));
const HowMatchingWorksPage = lazy(() => import("../features/landing/components/HowMatchingWorksPage"));

// ── Lazy: the authenticated application ─────────────────────────────────────
const JobSeekerDashboard = lazy(() => import("../features/profile/components/JobSeekerDashboard"));
const JobSeekerProfile = lazy(() => import("../features/profile/components/JobSeekerProfile"));
const AccountSettingsPage = lazy(() => import("../features/profile/components/AccountSettingsPage"));
const Feed = lazy(() => import("../features/matching/components/Feed"));
const SearchResults = lazy(() => import("../features/matching/components/SearchResults"));
const QuizInsights = lazy(() => import("../features/intelligence/components/QuizInsights"));
const AgentChat = lazy(() => import("../features/agent/components/AgentChat"));
const WorkPulsePage = lazy(() => import("../features/assessments/components/WorkPulsePage"));
const AssessmentPage = lazy(() => import("../features/assessments/components/AssessmentPage"));
const WorkPulseResultsPage = lazy(() => import("../features/assessments/components/WorkPulseResultsPage"));
const FocusTypePage = lazy(() => import("../features/assessments/components/FocusTypePage"));
const FocusTypeResultsPage = lazy(() => import("../features/assessments/components/FocusTypeResultsPage"));
const IntelligencePage = lazy(() => import("../features/intelligence/components/IntelligencePage"));
const CompanyDetailPage = lazy(() => import("../features/companies/components/CompanyDetailPage"));
const CompanyLensPage = lazy(() => import("../features/matching/components/CompanyLensPage"));
const ManagerMatchPage = lazy(() => import("../features/assessments/components/ManagerMatchPage"));
const ManagerMatchResultsPage = lazy(() => import("../features/assessments/components/ManagerMatchResultsPage"));
const ManagerProfilePage = lazy(() => import("../features/assessments/components/ManagerProfilePage"));
const ManagerPlaybookPage = lazy(() => import("../features/assessments/components/ManagerPlaybookPage"));
const EnvironmentReportPage = lazy(() => import("../features/assessments/components/EnvironmentReportPage"));
const SituationReportPage = lazy(() => import("../features/assessments/components/SituationReportPage"));
const PulseCheckinPage = lazy(() => import("../features/assessments/components/PulseCheckinPage"));
const PulseTrendPage = lazy(() => import("../features/assessments/components/PulseTrendPage"));
const PathIntelligencePage = lazy(() => import("../features/intelligence/components/PathIntelligencePage"));
const TrustPage = lazy(() => import("../features/intelligence/components/TrustPage"));

// Routes that render their own full navigation bar (hide the global Header).
const ROUTES_WITHOUT_HEADER = new Set(["/", "/start"]);

// Routes that include their own footer (suppress the global footer to avoid duplication).
const ROUTES_WITHOUT_FOOTER = new Set(["/"]);

function OnetAttribution() {
  return (
    <footer className="border-t border-cream-muted bg-cream-base px-6 py-5">
      <p className="mx-auto max-w-3xl text-xs text-ink-tertiary leading-relaxed text-center">
        This page includes information from the{" "}
        <a
          href="https://www.onetcenter.org/database.html"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-ink-secondary transition-colors"
        >
          O*NET 30.3 Database
        </a>{" "}
        by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA). Used under the{" "}
        <a
          href="https://creativecommons.org/licenses/by/4.0/"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-ink-secondary transition-colors"
        >
          CC BY 4.0
        </a>{" "}
        license. O*NET® is a trademark of USDOL/ETA. Solverah has modified all or some of this information. USDOL/ETA has not approved, endorsed, or tested these modifications.
      </p>
    </footer>
  );
}

/**
 * AppShell — Layout wrapper that conditionally renders the global Header and Footer.
 *
 * The Header is suppressed on the pre-launch landing page ("/") because
 * that page has its own LandingNav component. The global footer is suppressed
 * on "/" for the same reason — PrelaunchLandingPage renders its own footer
 * which includes the O*NET attribution inline.
 *
 * Phase 4b put `RouteErrorBoundary` *between* the chrome and the routes rather
 * than around the shell. That is the placement that makes the guarantee worth
 * having: a screen that throws is replaced by a fallback in the content area
 * while the Header above it keeps working, so the user navigates out of the
 * broken page instead of reaching for the back button. Wrapping the shell
 * instead would take the Header down with the route and leave them stranded.
 *
 * The route-level `Suspense` lives inside that boundary too — see
 * components/RouteErrorBoundary.tsx for why the two belong together.
 */
function AppShell({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const hideHeader = ROUTES_WITHOUT_HEADER.has(location.pathname);
  const hideFooter = ROUTES_WITHOUT_FOOTER.has(location.pathname);
  return (
    <div className="min-h-screen flex flex-col">
      {!hideHeader && <Header />}
      <div className="flex-1">
        <RouteErrorBoundary>{children}</RouteErrorBoundary>
      </div>
      {!hideFooter && <OnetAttribution />}
    </div>
  );
}

/**
 * The app's query client.
 *
 * Created once at module scope rather than inside App: a client rebuilt on
 * render would throw the cache away on every re-render, which defeats the
 * point. It sits outside AuthProvider because AuthProvider itself reaches for
 * it -- logout clears the whole cache so nothing outlives the session.
 */
const queryClient = createQueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
      {/* The profile slice's subscriber to auth's signed-in announcement: it
          seeds the profile cache from the login envelope. This mount is the
          wiring — auth cannot import the profile slice (that import WAS the
          barrel cycle), so the composition root connects the two. Removing it
          does not break sign-in; it silently moves the document fetch onto the
          first screen that renders it, which the tests in
          ProfileCacheSync.test.tsx exist to catch. */}
      <ProfileCacheSync />
      <Router>
        <AppShell>
          <Routes>
              {/* Public routes */}
              <Route path="/" element={<PrelaunchLandingPage />} />
              <Route path="/landing" element={<LandingPage />} />
              <Route path="/quiz-preview" element={<GuestQuizPreview />} />
              <Route path="/quiz-preview/insights" element={<GuestQuizInsights />} />
              <Route path="/start" element={<CareerIntakePage />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              {/* Legal + transparency (public) */}
              <Route path="/privacy" element={<LegalPage doc="privacy" />} />
              <Route path="/terms" element={<LegalPage doc="terms" />} />
              <Route path="/how-matching-works" element={<HowMatchingWorksPage />} />
              <Route path="/verify-email" element={<ConfirmEmail />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/forgot-password/verify" element={<ForgotPasswordVerify />} />
              {/* Legacy routes redirect to new code-entry page */}
              <Route path="/confirm-email" element={<CheckEmail />} />
              <Route path="/check-email" element={<CheckEmail />} />

              {/* Guest quiz previews (public twins of the guarded quiz routes) */}
              <Route path="/quiz-preview/early-career" element={<CareerQuizzes quizKey="earlyCareer" guest />} />
              <Route path="/quiz-preview/career-transition" element={<CareerQuizzes quizKey="careerTransition" guest />} />
              <Route path="/quiz-preview/mid-career" element={<CareerQuizzes quizKey="midCareer" guest />} />
              <Route path="/quiz-preview/teen-focused" element={<CareerQuizzes quizKey="teenFocused" guest />} />
              <Route path="/quiz-preview/career-job-search" element={<NextChapterYourWayQuiz guest />} />

              {/* The authenticated application. One pathless layout route
                  (ARCHITECTURE.md 6.3): RequireAuth holds this subtree back
                  while the session probe is in flight, then either renders the
                  matched child or redirects — /login when signed out, / when
                  the role is not allowed. The children keep absolute paths;
                  a pathless parent imposes no prefix. */}
              <Route element={<RequireAuth allowedRoles={["job-seeker"]} />}>
                {/* Agent chat route */}
                <Route path="/agent" element={<AgentChat />} />

                {/* Shared feed + search routes */}
                <Route path="/feed" element={<Feed />} />
                <Route path="/search" element={<SearchResults />} />

                {/* Job Seeker routes */}
                <Route path="/job-seeker/dashboard" element={<JobSeekerDashboard />} />
                <Route path="/job-seeker/profile" element={<JobSeekerProfile />} />
                <Route path="/settings" element={<AccountSettingsPage />} />

                {/* Quiz routes */}
                <Route path="/career-quizzes" element={<CareerQuizzes />} />
                <Route path="/career-quizzes/early-career" element={<CareerQuizzes quizKey="earlyCareer" />} />
                <Route path="/career-quizzes/career-transition" element={<CareerQuizzes quizKey="careerTransition" />} />
                <Route path="/career-quizzes/mid-career" element={<CareerQuizzes quizKey="midCareer" />} />
                <Route path="/career-quizzes/teen-focused" element={<CareerQuizzes quizKey="teenFocused" />} />
                <Route path="/career-job-search" element={<NextChapterYourWayQuiz />} />
                <Route path="/future-your-way" element={<SolverahYourFutureYourWayQuiz />} />
                <Route path="/quiz-insights" element={<QuizInsights />} />

                {/* Legacy alias. The person-side assessment ships as Work Pulse at /work-pulse;
                    AssessmentPage is now a redirect kept so pre-rename links don't break. */}
                <Route path="/assessment" element={<AssessmentPage />} />

                {/* Work Pulse routes */}
                <Route path="/work-pulse" element={<WorkPulsePage />} />
                <Route path="/work-pulse/results" element={<WorkPulseResultsPage />} />
                <Route path="/solverah-profile" element={<IntelligencePage />} />
                <Route path="/intelligence" element={<IntelligencePage />} />

                {/* FocusType routes */}
                <Route path="/focus-type" element={<FocusTypePage />} />
                <Route path="/focus-type/results" element={<FocusTypeResultsPage />} />

                {/* ManagerMatch routes */}
                <Route path="/manager-match" element={<ManagerMatchPage />} />
                <Route path="/manager-match/results" element={<ManagerMatchResultsPage />} />

                {/* Manager Decoder routes (BUILD_PLAN C-4) */}
                <Route path="/manager-profile" element={<ManagerProfilePage />} />
                <Route path="/manager-profile/playbook" element={<ManagerPlaybookPage />} />

                {/* Situation Report routes (BUILD_PLAN A-7). The environment
                    instrument and its payoff surface, the same
                    instrument/report pairing the Manager Decoder above has. */}
                <Route path="/environment-report" element={<EnvironmentReportPage />} />
                <Route path="/situation-report" element={<SituationReportPage />} />

                {/* Pulse routes (BUILD_PLAN B-3). /pulse is B-2's email
                    deep-link target (send_pulse_prompt_email) -- this exact
                    path must not move. */}
                <Route path="/pulse" element={<PulseCheckinPage />} />
                <Route path="/pulse/trend" element={<PulseTrendPage />} />

                {/* CompanyLens */}
                <Route path="/company-lens" element={<CompanyLensPage />} />

                {/* Path Intelligence */}
                <Route path="/intelligence/paths" element={<PathIntelligencePage />} />

                {/* Transparency (authenticated). The public twin waits on the
                    publicity gate — /how-matching-works is the public page. */}
                <Route path="/trust" element={<TrustPage />} />

                {/* Company detail */}
                <Route path="/companies/:id" element={<CompanyDetailPage />} />
              </Route>

              {/* Catch-all fallback */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </AppShell>
      </Router>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
