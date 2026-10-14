import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../features/auth/useAuth';
import { User, LogOut, MessageSquare, Brain, Settings, Menu, X } from 'lucide-react';

/**
 * The signed-in app chrome.
 *
 * Two things here are load-bearing and each has a regression test beside it:
 *
 * - The Feed modal is PORTALED to document.body. The header carries
 *   `backdrop-blur`, and an element with a backdrop-filter becomes the
 *   containing block for its `position: fixed` descendants -- so a modal
 *   rendered inside the header was clipped to the 64px bar and showed up in
 *   the top-left corner instead of over the page.
 *
 * - On narrow screens the signed-in links (five nav links, the name, the gear
 *   and logout) collapse behind a menu button. They used to sit in one
 *   unwrapped flex row and ran off the side of a phone.
 */
function Header() {
  const { user, logout } = useAuth();
  const [feedPopupOpen, setFeedPopupOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();

  // Any navigation closes the mobile menu, whichever link caused it.
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  // Escape closes whichever overlay is open.
  useEffect(() => {
    if (!menuOpen && !feedPopupOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setMenuOpen(false);
      setFeedPopupOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [menuOpen, feedPopupOpen]);

  const handleLogout = async () => {
    // The session must be gone BEFORE we arrive on "/": the landing page sends
    // a signed-in visitor to the dashboard (RedirectIfAuthenticated), and
    // logout() only clears `user` once POST /auth/logout has settled.
    // Navigating first would bounce someone who just clicked "Logout" to the
    // dashboard, and from there -- once the session cleared -- to /login.
    // logout() never throws; local state is cleared in its `finally`.
    setMenuOpen(false);
    await logout();
    navigate('/');
  };

  const handleFeedClick = (event: React.MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    setMenuOpen(false);
    setFeedPopupOpen(true);
  };

  const getDashboardPath = () => {
    if (user) return '/job-seeker/dashboard';
    return '/';
  };

  const getProfilePath = () => {
    if (user) return '/job-seeker/profile';
    return '/';
  };

  const isDashboard = location.pathname.includes('dashboard');
  const isProfile = location.pathname.startsWith('/job-seeker/profile');
  const isFeed = location.pathname === '/feed';
  const isAgent = location.pathname.startsWith('/agent');
  const isIntelligence =
    location.pathname.startsWith('/intelligence') ||
    location.pathname === '/solverah-profile';

  const navLinkCls = (active: boolean) =>
    `px-3 py-2 text-sm font-medium transition-colors rounded ${
      active
        ? 'text-forest-mid bg-forest-pale'
        : 'text-ink-secondary hover:text-forest-mid hover:bg-cream-subtle'
    }`;

  // One list, rendered twice: inline on desktop, stacked in the mobile menu.
  const navLinks = (linkCls: (active: boolean) => string, onNavigate?: () => void) => (
    <>
      <Link to="/feed" onClick={handleFeedClick} className={linkCls(isFeed)}>
        Feed
      </Link>
      <Link to={getDashboardPath()} onClick={onNavigate} className={linkCls(isDashboard)}>
        Dashboard
      </Link>
      <Link to="/intelligence" onClick={onNavigate} className={linkCls(isIntelligence)}>
        <Brain className="h-4 w-4 inline mr-1 -mt-0.5" />
        Intelligence
      </Link>
      <Link to={getProfilePath()} onClick={onNavigate} className={linkCls(isProfile)}>
        <User className="h-4 w-4 inline mr-1 -mt-0.5" />
        Profile
      </Link>
      <Link to="/agent" onClick={onNavigate} className={linkCls(isAgent)}>
        <MessageSquare className="h-4 w-4 inline mr-1 -mt-0.5" />
        Agent
      </Link>
    </>
  );

  const mobileLinkCls = (active: boolean) => `block ${navLinkCls(active)} py-3`;

  const feedModal = feedPopupOpen
    ? createPortal(
        <div
          className="fixed inset-0 z-[60] flex items-start justify-center bg-ink-primary/50 backdrop-blur-sm px-4 pt-24 print:hidden"
          role="dialog"
          aria-modal="true"
          aria-labelledby="feed-popup-title"
        >
          <div className="w-full max-w-xl rounded-xl border border-cream-muted bg-cream-base p-8 shadow-2xl">
            <p id="feed-popup-title" className="font-display text-xl font-semibold text-ink-primary">
              Feature coming soon
            </p>
            <p className="mt-2 text-sm text-ink-secondary leading-relaxed">
              We're still building the feed. It'll show up here when it's ready.
            </p>
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setFeedPopupOpen(false)}
                className="bg-forest-dark text-white text-sm font-semibold px-6 py-2.5 rounded-[4px] hover:bg-forest-mid transition-colors"
              >
                Got it
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <header className="sticky top-0 z-50 border-b border-cream-muted bg-cream-base/95 backdrop-blur font-sans print:hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo */}
          <Link
            to={user ? getDashboardPath() : "/"}
            className="font-headline text-[1.35rem] font-extrabold tracking-[-0.02em] text-ink-primary"
          >
            Solverah
          </Link>

          {user ? (
            <>
              {/* Desktop nav */}
              <nav aria-label="Main" className="hidden md:flex items-center gap-1">
                {navLinks(navLinkCls)}
                <div className="flex items-center gap-3 ml-4 pl-4 border-l border-cream-muted">
                  <span className="text-sm text-ink-tertiary">
                    {user.name}
                  </span>
                  <Link
                    to="/settings"
                    aria-label="Account settings"
                    title="Account settings"
                    className="p-2 text-ink-tertiary hover:text-forest-mid transition-colors rounded hover:bg-cream-subtle"
                  >
                    <Settings className="h-4 w-4" />
                  </Link>
                  <button
                    onClick={handleLogout}
                    className="p-2 text-ink-tertiary hover:text-red-600 transition-colors rounded hover:bg-red-50"
                    title="Logout"
                  >
                    <LogOut className="h-4 w-4" />
                  </button>
                </div>
              </nav>

              {/* Mobile menu button */}
              <button
                type="button"
                onClick={() => setMenuOpen((open) => !open)}
                aria-expanded={menuOpen}
                aria-controls="mobile-nav"
                aria-label={menuOpen ? 'Close menu' : 'Open menu'}
                className="md:hidden p-2 text-ink-secondary hover:text-forest-mid rounded-[4px] hover:bg-cream-subtle transition-colors"
              >
                {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>
            </>
          ) : (
            <nav className="flex items-center gap-3">
              <Link
                to="/login"
                className="px-3 py-2 text-[0.9rem] font-medium text-ink-secondary transition-colors hover:text-forest-mid"
              >
                Sign in
              </Link>
              <Link
                to="/register"
                className="inline-flex items-center rounded-[4px] bg-forest-dark px-5 py-2.5 font-headline text-[0.9rem] font-bold text-white transition-colors hover:bg-forest-mid"
              >
                Get started
              </Link>
            </nav>
          )}
        </div>
      </div>

      {/* Mobile menu panel -- only mounted while open. */}
      {user && menuOpen && (
        <nav
          id="mobile-nav"
          aria-label="Mobile"
          className="md:hidden border-t border-cream-muted bg-cream-base px-4 pb-4 pt-2"
        >
          {navLinks(mobileLinkCls, () => setMenuOpen(false))}
          <div className="mt-2 pt-3 border-t border-cream-muted flex items-center justify-between gap-3">
            <span className="text-sm text-ink-tertiary truncate">{user.name}</span>
            <div className="flex items-center gap-1">
              <Link
                to="/settings"
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-sm text-ink-secondary hover:text-forest-mid rounded hover:bg-cream-subtle transition-colors"
              >
                <Settings className="h-4 w-4" />
                Settings
              </Link>
              <button
                type="button"
                onClick={handleLogout}
                className="flex items-center gap-2 px-3 py-2 text-sm text-ink-secondary hover:text-red-600 rounded hover:bg-red-50 transition-colors"
              >
                <LogOut className="h-4 w-4" />
                Log out
              </button>
            </div>
          </div>
        </nav>
      )}

      {feedModal}
    </header>
  );
}

export default Header;
