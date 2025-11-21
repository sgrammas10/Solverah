import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { User, LogOut, Briefcase } from 'lucide-react';

function Header() {
  // Retrieve the currently logged-in user and the logout method from AuthContext
  const { user, logout } = useAuth();

  // Hooks for navigation and getting the current URL path
  const navigate = useNavigate();
  const location = useLocation();

  /**
   * Log out the user and redirect to the home page.
   */
  const handleLogout = () => {
    logout();      // clears authentication
    navigate('/'); // redirect to landing page
  };

  /**
   * Compute dashboard link based on user role.
   * - job-seeker → /job-seeker/dashboard
   * - recruiter → /recruiter/dashboard
   * - no user → /
   */
  const getDashboardPath = () => {
    if (user?.role === 'job-seeker') return '/job-seeker/dashboard';
    if (user?.role === 'recruiter') return '/recruiter/dashboard';
    return '/';
  };

  /**
   * Compute profile link based on user role.
   * - job-seeker → /job-seeker/profile
   * - recruiter → /recruiter/profile
   * - no user → /
   */
  const getProfilePath = () => {
    if (user?.role === 'job-seeker') return '/job-seeker/profile';
    if (user?.role === 'recruiter') return '/recruiter/profile';
    return '/';
  };

  return (
    <header className="bg-white shadow-sm border-b border-gray-200">
      {/* Centered container */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Header content wrapper */}
        <div className="flex justify-between items-center h-16">

          {/* Logo + Home link */}
          <Link to="/" className="flex items-center space-x-2">
            <Briefcase className="h-8 w-8 text-blue-600" />
            <span className="text-2xl font-bold text-gray-900">Solverah</span>
          </Link>

          {/* Navigation links */}
          <nav className="flex items-center space-x-6">
            {user ? (
              // If user IS logged in, show dashboard, feed, profile, logout, etc.
              <>
                {/* Feed Link (highlight if on /feed) */}
                <Link
                  to="/feed"
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    location.pathname === '/feed'
                      ? 'text-blue-600 bg-blue-50'
                      : 'text-gray-600 hover:text-blue-600 hover:bg-blue-50'
                  }`}
                >
                  Feed
                </Link>

                {/* Dashboard Link (highlight if pathname includes "dashboard") */}
                <Link
                  to={getDashboardPath()}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    location.pathname.includes('dashboard')
                      ? 'text-blue-600 bg-blue-50'
                      : 'text-gray-600 hover:text-blue-600 hover:bg-blue-50'
                  }`}
                >
                  Dashboard
                </Link>

                {/* Profile Link (highlight if pathname includes "profile") */}
                <Link
                  to={getProfilePath()}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    location.pathname.includes('profile')
                      ? 'text-blue-600 bg-blue-50'
                      : 'text-gray-600 hover:text-blue-600 hover:bg-blue-50'
                  }`}
                >
                  <User className="h-4 w-4 inline mr-1" />
                  Profile
                </Link>

                {/* User info + logout button */}
                <div className="flex items-center space-x-3">
                  <span className="text-sm text-gray-600">
                    {user.name} ({user.role === 'job-seeker' ? 'Job Seeker' : 'Recruiter'})
                  </span>

                  {/* Logout icon button */}
                  <button
                    onClick={handleLogout}
                    className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                    title="Logout"
                  >
                    <LogOut className="h-4 w-4" />
                  </button>
                </div>
              </>
            ) : (
              // If NO user logged in → show Sign In / Register buttons
              <>
                <Link
                  to="/login"
                  className="text-gray-600 hover:text-blue-600 px-3 py-2 rounded-md text-sm font-medium transition-colors"
                >
                  Sign In
                </Link>

                <Link
                  to="/register"
                  className="bg-blue-600 text-white hover:bg-blue-700 px-4 py-2 rounded-md text-sm font-medium transition-colors"
                >
                  Get Started
                </Link>
              </>
            )}
          </nav>
        </div>
      </div>
    </header>
  );
}

export default Header;
