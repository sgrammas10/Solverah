import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/useAuth';
import { User, LogOut, Briefcase } from 'lucide-react';

function Header() {
  const { user, logout } = useAuth();
  const [feedPopupOpen, setFeedPopupOpen] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const handleFeedClick = (event: React.MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    setFeedPopupOpen(true);
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

  const isDashboard = location.pathname.includes('dashboard');
  const isProfile = location.pathname.includes('profile');
  const isFeed = location.pathname === '/feed';

  const navLinkCls = (active: boolean) =>
    `px-3 py-2 text-sm font-medium transition-colors rounded ${
      active
        ? 'text-forest-mid bg-forest-pale'
        : 'text-ink-secondary hover:text-forest-mid hover:bg-cream-subtle'
    }`;

  return (
    <header className="sticky top-0 z-50 border-b border-cream-muted bg-cream-base/95 backdrop-blur font-sans">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo */}
          <Link to={user ? getDashboardPath() : "/"} className="font-display text-2xl font-bold text-forest-dark tracking-tight">
            Solverah
          </Link>

          {/* Nav */}
          <nav className="flex items-center gap-1">
            {user ? (
              <>
                <Link
                  to="/feed"
                  onClick={handleFeedClick}
                  className={navLinkCls(isFeed)}
                >
                  Feed
                </Link>
                <Link
                  to={getDashboardPath()}
                  className={navLinkCls(isDashboard)}
                >
                  Dashboard
                </Link>
                <Link
                  to={getProfilePath()}
                  className={navLinkCls(isProfile)}
                >
                  <User className="h-4 w-4 inline mr-1 -mt-0.5" />
                  Profile
                </Link>
                <div className="flex items-center gap-3 ml-4 pl-4 border-l border-cream-muted">
                  <span className="text-sm text-ink-tertiary">
                    {user.name}
                  </span>
                  <button
                    onClick={handleLogout}
                    className="p-2 text-ink-tertiary hover:text-red-600 transition-colors rounded hover:bg-red-50"
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
                  className="text-sm font-medium text-ink-secondary px-4 py-2 rounded hover:text-forest-mid transition-colors"
                >
                  Sign In
                </Link>
                <Link
                  to="/register"
                  className="bg-forest-dark text-white text-sm font-semibold px-5 py-2 rounded hover:bg-forest-mid transition-colors"
                >
                  Get Started
                </Link>
              </>
            )}
          </nav>
        </div>
      </div>

      {/* Feed coming-soon modal */}
      {feedPopupOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-ink-primary/50 backdrop-blur-sm px-4 pt-24"
          role="dialog"
          aria-modal="true"
          aria-labelledby="feed-popup-title"
        >
          <div className="w-full max-w-xl rounded-xl border border-cream-muted bg-cream-base p-8 shadow-2xl">
            <p id="feed-popup-title" className="font-display text-xl font-semibold text-ink-primary">
              Feature coming soon
            </p>
            <p className="mt-2 text-sm text-ink-secondary leading-relaxed">
              The feed will be available soon. Check back after launch.
            </p>
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setFeedPopupOpen(false)}
                className="bg-forest-dark text-white text-sm font-semibold px-6 py-2.5 rounded hover:bg-forest-mid transition-colors"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

export default Header;
