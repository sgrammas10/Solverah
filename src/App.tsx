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
import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext.tsx";
import { useAuth } from "./contexts/useAuth";
import Header from "./components/Header";

// Quiz Components
import CareerQuizzes from "./components/CareerQuizzes";
import NextChapterYourWayQuiz from "./components/NextChapterYourWayQuiz";
import SolverahYourFutureYourWayQuiz from "./components/SolverahYourFutureYourWayQuiz";

// Core Pages
import PrelaunchLandingPage from "./pages/prelaunchlandingpage";
import LandingPage from "./pages/LandingPage";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ConfirmEmail from "./pages/ConfirmEmail";
import CheckEmail from "./pages/CheckEmail";
import JobSeekerDashboard from "./pages/JobSeekerDashboard";
import JobSeekerProfile from "./pages/JobSeekerProfile";
import Feed from "./pages/Feed";
import SearchResults from "./pages/SearchResults"; // from your quiz-aware version
import QuizInsights from "./pages/QuizInsights";
import GuestQuizPreview from "./pages/GuestQuizPreview";
import GuestQuizInsights from "./pages/GuestQuizInsights";
import AgentChat from "./pages/AgentChat";

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
const ROUTES_WITHOUT_HEADER = new Set(["/"]);

/**
 * AppShell — Layout wrapper that conditionally renders the global Header.
 *
 * The Header is suppressed on the pre-launch landing page ("/") because
 * that page has its own LandingNav component.
 */
function AppShell({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const hideHeader = ROUTES_WITHOUT_HEADER.has(location.pathname);
  return (
    <div className="min-h-screen">
      {!hideHeader && <Header />}
      {children}
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <AppShell>
          <Routes>
              {/* Public routes */}
              <Route path="/" element={<PrelaunchLandingPage />} />
              <Route path="/landing" element={<LandingPage />} />
              <Route path="/quiz-preview" element={<GuestQuizPreview />} />
              <Route path="/quiz-preview/insights" element={<GuestQuizInsights />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/verify-email" element={<ConfirmEmail />} />
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

              {/* Catch-all fallback */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </AppShell>
      </Router>
    </AuthProvider>
  );
}

export default App;
