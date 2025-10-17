import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Header from './components/Header';
import CareerAndJobSearchTab from './components/CareerAndJobSearchTab';
import LandingPage from './pages/LandingPage';
import Login from './pages/Login';
import Register from './pages/Register';
import JobSeekerDashboard from './pages/JobSeekerDashboard';
import RecruiterDashboard from './pages/RecruiterDashboard';
import JobSeekerProfile from './pages/JobSeekerProfile';
import RecruiterProfile from './pages/RecruiterProfile';
import Feed from './pages/Feed';


function ProtectedRoute({ children, allowedRoles }: { children: React.ReactNode; allowedRoles: string[] }) {
  const { user } = useAuth();
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  
  if (!allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  
  return <>{children}</>;
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <div className="min-h-screen bg-gray-50">
          <Header />
          <main>
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route 
                path="/feed" 
                element={
                  <ProtectedRoute allowedRoles={['job-seeker', 'recruiter']}>
                    <Feed />
                  </ProtectedRoute>
                } 
              />
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
              <Route 
                path="/career-job-search" 
                element={
                  <ProtectedRoute allowedRoles={['job-seeker', 'recruiter']}>
                    <CareerAndJobSearchTab />
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