// App.tsx
// Main entry point for all routing, authentication context wrapping, and role-based route protection.

import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';

// Authentication context: provides user state and login/logout helpers
import { AuthProvider, useAuth } from './contexts/AuthContext';

// Shared UI
import Header from './components/Header';

// Quiz pages
import CareerQuizzes from './components/CareerQuizzes';
import NextChapterYourWayQuiz from './components/NextChapterYourWayQuiz';
import SolverahYourFutureYourWayQuiz from './components/SolverahYourFutureYourWayQuiz';

// Public pages
import LandingPage from './pages/LandingPage';
import Login from './pages/Login';
import Register from './pages/Register';

// Job-Seeker protected pages
import JobSeekerDashboard from './pages/JobSeekerDashboard';
import JobSeekerProfile from './pages/JobSeekerProfile';

// Recruiter protected pages
import RecruiterDashboard from './pages/RecruiterDashboard';
import RecruiterProfile from './pages/RecruiterProfile';

// Pages accessible to both roles
import Feed from './pages/Feed';


/**
 * 🔐 ProtectedRoute Component
 * ---------------------------
 * Wraps around any component that should only be accessible:
 *    1) When a user is authenticated
 *    2) When that user has one of the allowed roles
 *
 * Props:
 *  - children: The page/component being protected
 *  - allowedRoles: Array of roles that are allowed to view this route
 */
function ProtectedRoute({ children, allowedRoles }: { children: React.ReactNode; allowedRoles: string[] }) {
  const { user } = useAuth();

  // Not logged in → redirect to login page
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Logged in but role not allowed → send home
  if (!allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  // User is authenticated & authorized
  return <>{children}</>;
}


/**
 * 🌐 App Component
 * ----------------
 * Wraps all pages in:
 *  - AuthProvider → gives access to user login state globally
 *  - Router → handles all navigation between pages
 */
function App() {
  return (
    <AuthProvider>
      <Router>
        <div className="min-h-screen bg-gray-50">
          {/* Navigation bar that appears on all pages */}
          <Header />
          
          <main>
            <Routes>

              {/* ============================== */}
              {/* PUBLIC ROUTES (NO LOGIN NEEDED) */}
              {/* ============================== */}

              <Route path="/" element={<LandingPage />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />


              {/* =============================== */}
              {/* SHARED ACCESS (JOB + RECRUITER) */}
              {/* =============================== */}

              <Route 
                path="/feed" 
                element={
                  <ProtectedRoute allowedRoles={['job-seeker', 'recruiter']}>
                    <Feed />
                  </ProtectedRoute>
                }
              />

              <Route 
                path="/career-job-search" 
                element={
                  <ProtectedRoute allowedRoles={['job-seeker', 'recruiter']}>
                    <NextChapterYourWayQuiz />
                  </ProtectedRoute>
                }
              />

              <Route 
                path="/future-your-way" 
                element={
                  <ProtectedRoute allowedRoles={['job-seeker', 'recruiter']}>
                    <SolverahYourFutureYourWayQuiz />
                  </ProtectedRoute>
                }
              />

              <Route 
                path="/career-quizzes" 
                element={
                  <ProtectedRoute allowedRoles={['job-seeker', 'recruiter']}>
                    <CareerQuizzes />
                  </ProtectedRoute>
                }
              />


              {/* ===================== */}
              {/* JOB SEEKER ROUTES     */}
              {/* ===================== */}

              <Route 
                path="/job-seeker/dashboard" 
                element={
                  <ProtectedRoute allowedRoles={['job-seeker']}>
                    <JobSeekerDashboard />
                  </ProtectedRoute>
                }
              />

              <Route 
                path="/job-seeker/profile" 
                element={
                  <ProtectedRoute allowedRoles={['job-seeker']}>
                    <JobSeekerProfile />
                  </ProtectedRoute>
                }
              />


              {/* ===================== */}
              {/* RECRUITER ROUTES      */}
              {/* ===================== */}

              <Route 
                path="/recruiter/dashboard" 
                element={
                  <ProtectedRoute allowedRoles={['recruiter']}>
                    <RecruiterDashboard />
                  </ProtectedRoute>
                }
              />

              <Route 
                path="/recruiter/profile" 
                element={
                  <ProtectedRoute allowedRoles={['recruiter']}>
                    <RecruiterProfile />
                  </ProtectedRoute>
                }
              />

            </Routes>
          </main>
        </div>
      </Router>
    </AuthProvider>
  );
}

export default App;
