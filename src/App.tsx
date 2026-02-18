import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
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
import RecruiterDashboard from "./pages/RecruiterDashboard";
import JobSeekerProfile from "./pages/JobSeekerProfile";
import RecruiterProfile from "./pages/RecruiterProfile";
import Feed from "./pages/Feed";
import SearchResults from "./pages/SearchResults"; // from your quiz-aware version
import QuizInsights from "./pages/QuizInsights";
import GuestQuizPreview from "./pages/GuestQuizPreview";
import GuestQuizInsights from "./pages/GuestQuizInsights";

// Role-based route protection
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

function App() {
  return (
    <AuthProvider>
      <Router>
        <div className="min-h-screen bg-slate-950 text-slate-100">
          <Header />
          <main>
            <Routes>
              {/* Public routes */}
              <Route path="/" element={<PrelaunchLandingPage />} />
              <Route path="/landing" element={<LandingPage />} />
              <Route path="/quiz-preview" element={<GuestQuizPreview />} />
              <Route path="/quiz-preview/insights" element={<GuestQuizInsights />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/confirm-email" element={<ConfirmEmail />} />
              <Route path="/check-email" element={<CheckEmail />} />

              {/* Shared feed + search routes */}
              <Route
                path="/feed"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker", "recruiter"]}>
                    <Feed />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/search"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker", "recruiter"]}>
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

              {/* Recruiter routes */}
              <Route
                path="/recruiter/dashboard"
                element={
                  <ProtectedRoute allowedRoles={["recruiter"]}>
                    <RecruiterDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/recruiter/profile"
                element={
                  <ProtectedRoute allowedRoles={["recruiter"]}>
                    <RecruiterProfile />
                  </ProtectedRoute>
                }
              />

              {/* Quiz routes */}
              <Route
                path="/career-quizzes"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker", "recruiter"]}>
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
                  <ProtectedRoute allowedRoles={["job-seeker", "recruiter"]}>
                    <CareerQuizzes quizKey="earlyCareer" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/career-quizzes/career-transition"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker", "recruiter"]}>
                    <CareerQuizzes quizKey="careerTransition" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/career-quizzes/mid-career"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker", "recruiter"]}>
                    <CareerQuizzes quizKey="midCareer" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/career-quizzes/teen-focused"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker", "recruiter"]}>
                    <CareerQuizzes quizKey="teenFocused" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/career-job-search"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker", "recruiter"]}>
                    <NextChapterYourWayQuiz />
                  </ProtectedRoute>
                }
              />
              <Route path="/quiz-preview/career-job-search" element={<NextChapterYourWayQuiz guest />} />
              <Route
                path="/future-your-way"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker", "recruiter"]}>
                    <SolverahYourFutureYourWayQuiz />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/quiz-insights"
                element={
                  <ProtectedRoute allowedRoles={["job-seeker", "recruiter"]}>
                    <QuizInsights />
                  </ProtectedRoute>
                }
              />

              {/* Catch-all fallback */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </Router>
    </AuthProvider>
  );
}

export default App;
