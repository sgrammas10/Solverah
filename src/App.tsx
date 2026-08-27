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
 *   /career-quizzes/*         Authenticated quiz routes
 *   /quiz-insights            Authenticated quiz insights
 *   *                         Catch-all → redirect to /
 *
 * Access control:
 *   ProtectedRoute checks user presence (redirect to /login if null) and role
 *   membership (redirect to / if the user's role is not in allowedRoles).
 *
 * Header visibility:
 *   The global Header is hidden on the "/" route because PrelaunchLandingPage
 *   renders its own navigation (LandingNav).  All other routes show the Header.
 */
import React, { lazy } from "react";
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./contexts/AuthContext.tsx";
import { useAuth } from "./contexts/useAuth";
import Header from "./components/Header";
import { RouteErrorBoundary } from "./components/RouteErrorBoundary";
import { createQueryClient } from "./utils/queryClient";

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
import PrelaunchLandingPage from "./pages/prelaunchlandingpage";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ConfirmEmail from "./pages/ConfirmEmail";
import CheckEmail from "./pages/CheckEmail";
import ForgotPassword from "./pages/ForgotPassword";
import ForgotPasswordVerify from "./pages/ForgotPasswordVerify";

// ── Lazy: quiz components ───────────────────────────────────────────────────
const CareerQuizzes = lazy(() => import("./components/CareerQuizzes"));
const NextChapterYourWayQuiz = lazy(() => import("./components/NextChapterYourWayQuiz"));
const SolverahYourFutureYourWayQuiz = lazy(
  () => import("./components/SolverahYourFutureYourWayQuiz"),
);

// ── Lazy: public pages behind an in-app navigation ──────────────────────────
const LandingPage = lazy(() => import("./pages/LandingPage"));
const GuestQuizPreview = lazy(() => import("./pages/GuestQuizPreview"));
const GuestQuizInsights = lazy(() => import("./pages/GuestQuizInsights"));
const CareerIntakePage = lazy(() => import("./pages/CareerIntakePage"));
const LegalPage = lazy(() => import("./pages/LegalPage"));
const HowMatchingWorksPage = lazy(() => import("./pages/HowMatchingWorksPage"));

// ── Lazy: the authenticated application ─────────────────────────────────────
const JobSeekerDashboard = lazy(() => import("./pages/JobSeekerDashboard"));
const JobSeekerProfile = lazy(() => import("./pages/JobSeekerProfile"));
const Feed = lazy(() => import("./pages/Feed"));
const SearchResults = lazy(() => import("./pages/SearchResults"));
const QuizInsights = lazy(() => import("./pages/QuizInsights"));
const AgentChat = lazy(() => import("./pages/AgentChat"));
const WorkPulsePage = lazy(() => import("./pages/WorkPulsePage"));
const AssessmentPage = lazy(() => import("./pages/AssessmentPage"));
const WorkPulseResultsPage = lazy(() => import("./pages/WorkPulseResultsPage"));
const FocusTypePage = lazy(() => import("./pages/FocusTypePage"));
const FocusTypeResultsPage = lazy(() => import("./pages/FocusTypeResultsPage"));
const IntelligencePage = lazy(() => import("./pages/IntelligencePage"));
const CompanyDetailPage = lazy(() => import("./pages/CompanyDetailPage"));
const CompanyLensPage = lazy(() => import("./pages/CompanyLensPage"));
const ManagerMatchPage = lazy(() => import("./pages/ManagerMatchPage"));
const ManagerMatchResultsPage = lazy(() => import("./pages/ManagerMatchResultsPage"));
const PathIntelligencePage = lazy(() => import("./pages/PathIntelligencePage"));

/**
 * ProtectedRoute — Wraps a route element with authentication and role checks.
 *
 * Unauthenticated users are redirected to /login.
 * Authenticated users whose role is not in allowedRoles are redirected to /.
 * This relies on AuthProvider completing the session-restore fetch before
 * rendering (AuthProvider shows a spinner while loading=true).
 */
function ProtectedRoute({
  children,
  allowedRoles,
}: {
  children: React.ReactNode;
  allowedRoles: string[];
}) {
  const { user } = useAuth();

  if (!user) return <Navigate to="/login" replace />;
  if (!allowedRoles.includes(user.role)) return <Navigate to="/" replace />;

  return <>{children}</>;
}

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
 * it -- login seeds the profile document into the cache and logout clears it.
 */
const queryClient = createQueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
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

              {/* Agent chat route */}
              <Route
                path="/agent"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <AgentChat />
                  </ProtectedRoute>
                }
              />

              {/* Shared feed + search routes */}
              <Route
                path="/feed"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <Feed />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/search"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <SearchResults />
                  </ProtectedRoute>
                }
              />

              {/* Job Seeker routes */}
              <Route
                path="/job-seeker/dashboard"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <JobSeekerDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/job-seeker/profile"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <JobSeekerProfile />
                  </ProtectedRoute>
                }
              />

              {/* Quiz routes */}
              <Route
                path="/career-quizzes"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <CareerQuizzes />
                  </ProtectedRoute>
                }
              />
              <Route path="/quiz-preview/early-career" element={<CareerQuizzes quizKey="earlyCareer" guest />} />
              <Route path="/quiz-preview/career-transition" element={<CareerQuizzes quizKey="careerTransition" guest />} />
              <Route path="/quiz-preview/mid-career" element={<CareerQuizzes quizKey="midCareer" guest />} />
              <Route path="/quiz-preview/teen-focused" element={<CareerQuizzes quizKey="teenFocused" guest />} />
              <Route
                path="/career-quizzes/early-career"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <CareerQuizzes quizKey="earlyCareer" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/career-quizzes/career-transition"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <CareerQuizzes quizKey="careerTransition" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/career-quizzes/mid-career"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <CareerQuizzes quizKey="midCareer" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/career-quizzes/teen-focused"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <CareerQuizzes quizKey="teenFocused" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/career-job-search"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <NextChapterYourWayQuiz />
                  </ProtectedRoute>
                }
              />
              <Route path="/quiz-preview/career-job-search" element={<NextChapterYourWayQuiz guest />} />
              <Route
                path="/future-your-way"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <SolverahYourFutureYourWayQuiz />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/quiz-insights"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <QuizInsights />
                  </ProtectedRoute>
                }
              />

              {/* Legacy alias. The person-side assessment ships as Work Pulse at /work-pulse;
                  AssessmentPage is now a redirect kept so pre-rename links don't break. */}
              <Route
                path="/assessment"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <AssessmentPage />
                  </ProtectedRoute>
                }
              />

              {/* Work Pulse routes */}
              <Route
                path="/work-pulse"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <WorkPulsePage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/work-pulse/results"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <WorkPulseResultsPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/solverah-profile"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <IntelligencePage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/intelligence"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <IntelligencePage />
                  </ProtectedRoute>
                }
              />

              {/* FocusType routes */}
              <Route
                path="/focus-type"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <FocusTypePage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/focus-type/results"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <FocusTypeResultsPage />
                  </ProtectedRoute>
                }
              />

              {/* ManagerMatch routes */}
              <Route
                path="/manager-match"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <ManagerMatchPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/manager-match/results"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <ManagerMatchResultsPage />
                  </ProtectedRoute>
                }
              />

              {/* CompanyLens */}
              <Route
                path="/company-lens"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <CompanyLensPage />
                  </ProtectedRoute>
                }
              />

              {/* Path Intelligence */}
              <Route
                path="/intelligence/paths"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <PathIntelligencePage />
                  </ProtectedRoute>
                }
              />

              {/* Company detail */}
              <Route
                path="/companies/:id"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker"]}>
                    <CompanyDetailPage />
                  </ProtectedRoute>
                }
              />

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
