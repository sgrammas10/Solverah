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
    logout(); // clears authentication
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

  const isDashboard = location.pathname.includes('dashboard');
  const isProfile = location.pathname.includes('profile');
  const isFeed = location.pathname === '/feed';

  return (
    <header className="border-b border-white/10 bg-slate-950/80 backdrop-blur supports-[backdrop-filter]:bg-slate-950/60">
      {/* Centered container */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header content wrapper */}
        <div className="flex justify-between items-center h-16">
          {/* Logo + Home link */}
          <Link to="/" className="flex items-center space-x-2">
            <Briefcase className="h-8 w-8 text-emerald-300" />
            <span className="text-2xl font-bold text-white">Solverah</span>
          </Link>

          {/* Navigation links */}
          <nav className="flex items-center space-x-6">
            {user ? (
              // If user IS logged in, show dashboard, feed, profile, logout, etc.
              <>
                {/* Feed Link (highlight if on /feed) */}
                <Link
                  to="/feed"
                  className={`px-3 py-2 rounded-full text-sm font-medium transition-colors ${
                    isFeed
                      ? 'text-emerald-200 bg-white/10'
                      : 'text-slate-200 hover:text-emerald-200 hover:bg-white/5'
                  }`}
                >
                  Feed
                </Link>

                {/* Dashboard Link (highlight if pathname includes "dashboard") */}
                <Link
                  to={getDashboardPath()}
                  className={`px-3 py-2 rounded-full text-sm font-medium transition-colors ${
                    isDashboard
                      ? 'text-emerald-200 bg-white/10'
                      : 'text-slate-200 hover:text-emerald-200 hover:bg-white/5'
                  }`}
                >
                  Dashboard
                </Link>

                {/* Profile Link (highlight if pathname includes "profile") */}
                <Link
                  to={getProfilePath()}
                  className={`px-3 py-2 rounded-full text-sm font-medium transition-colors ${
                    isProfile
                      ? 'text-emerald-200 bg-white/10'
                      : 'text-slate-200 hover:text-emerald-200 hover:bg-white/5'
                  }`}
                >
                  <User className="h-4 w-4 inline mr-1" />
                  Profile
                </Link>

                {/* User info + logout button */}
                <div className="flex items-center space-x-3">
                  <span className="text-sm text-slate-200/80">
                    {user.name} ({user.role === 'job-seeker' ? 'Job Seeker' : 'Recruiter'})
                  </span>

                  {/* Logout icon button */}
                  <button
                    onClick={handleLogout}
                    className="p-2 text-slate-300 hover:text-red-300 transition-colors"
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
                  className="text-slate-200 hover:text-white px-3 py-2 rounded-full text-sm font-medium transition-colors"
                >
                  Sign In
                </Link>

                <Link
                  to="/register"
                  className="bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 text-slate-950 hover:from-emerald-300 hover:via-blue-400 hover:to-indigo-400 px-4 py-2 rounded-full text-sm font-semibold transition-colors"
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
