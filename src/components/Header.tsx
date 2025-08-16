import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { User, LogOut, Briefcase, Users } from 'lucide-react';

function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const getDashboardPath = () => {
    if (user?.role === 'job-seeker') return '/job-seeker/dashboard';
    if (user?.role === 'recruiter') return '/recruiter/dashboard';
    return '/';
  };

  const getProfilePath = () => {
    if (user?.role === 'job-seeker') return '/job-seeker/profile';
    if (user?.role === 'recruiter') return '/recruiter/profile';
    return '/';
  };

  return (
    <header className="bg-white shadow-sm border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <Link to="/" className="flex items-center space-x-2">
            <Briefcase className="h-8 w-8 text-blue-600" />
            <span className="text-2xl font-bold text-gray-900">Solverah</span>
          </Link>

          <nav className="flex items-center space-x-6">
            {user ? (
              <>
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
                <div className="flex items-center space-x-3">
                  <span className="text-sm text-gray-600">
                    {user.name} ({user.role === 'job-seeker' ? 'Job Seeker' : 'Recruiter'})
                  </span>
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