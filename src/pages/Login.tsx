import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/useAuth';
import { getPendingQuizSave, clearPendingQuizSave } from "../utils/guestQuiz";
import { API_BASE } from "../utils/api";
import HeroNetworkAnimation from '../components/HeroNetworkAnimation';
import { Eye, EyeOff } from 'lucide-react';

function ResendConfirmation({ email }: { email: string }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState<'idle' | 'sending' | 'error'>('idle');
  const [msg, setMsg] = useState('');

  const handleResend = async () => {
    if (!email) {
      setMsg('Please enter your email above before resending.');
      setStatus('error');
      return;
    }
    setStatus('sending');
    setMsg('');
    try {
      const res = await fetch(`${API_BASE}/resend-confirmation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setStatus('error');
        setMsg(data?.error || 'Failed to resend code');
        return;
      }
      navigate('/verify-email', { state: { email } });
    } catch (err: any) {
      setStatus('error');
      setMsg(err?.message || 'Network error');
    }
  };

  return (
    <div className="mt-2">
      <button
        onClick={handleResend}
        className="text-sm font-medium text-forest-mid underline underline-offset-4 hover:text-forest-dark transition-colors"
        disabled={status === 'sending'}
      >
        {status === 'sending' ? 'Sending…' : 'Resend verification code'}
      </button>
      {msg && <p className="mt-1 text-sm text-red-600">{msg}</p>}
    </div>
  );
}

function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const { login, fetchWithAuth } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const loggedInUser = await login(email, password);
      let redirectPath =
        loggedInUser.role === 'job-seeker' ? '/job-seeker/dashboard' : '/recruiter/dashboard';

      const pending = getPendingQuizSave();
      if (pending && loggedInUser.role === 'job-seeker' && fetchWithAuth) {
        try {
          await fetchWithAuth('/profile', {
            method: 'POST',
            body: JSON.stringify({ profileData: { quizResults: pending.quizResults } }),
          });
          await fetchWithAuth('/quiz-insights', {
            method: 'POST',
            body: JSON.stringify(pending.quizPayload),
          });
          redirectPath = `/quiz-insights?group=${encodeURIComponent(pending.quizGroup)}`;
          clearPendingQuizSave();
        } catch (saveErr) {
          console.error('Failed to save pending quiz:', saveErr);
        }
      }

      navigate(redirectPath);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (message && message.toLowerCase().includes('email not confirmed')) {
        setError('Your email is not confirmed. Please check your inbox.');
      } else {
        setError('Failed to sign in. Please check your credentials.');
      }
    } finally {
      setLoading(false);
    }
  };

  const inputCls =
    'w-full rounded border border-cream-muted bg-cream-base px-4 py-3 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors';
  const inputWithToggleCls =
    'w-full rounded border border-cream-muted bg-cream-base pl-4 pr-11 py-3 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors';

  return (
    <div className="relative overflow-hidden min-h-screen bg-cream-base font-sans flex items-center justify-center py-16 px-4">
      <HeroNetworkAnimation theme="light" />
      <div className="relative z-10 w-full max-w-md">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-ink-tertiary hover:text-forest-mid transition-colors mb-8"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Back to Solverah
        </Link>

        <div className="border border-cream-muted rounded-xl bg-white p-8">
          <div className="mb-8">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">Welcome back</p>
            <h1 className="font-display text-3xl font-bold text-ink-primary">Sign in to your account</h1>
            <p className="mt-2 text-sm text-ink-secondary">
              Don't have an account?{' '}
              <Link to="/register" className="font-semibold text-forest-mid hover:text-forest-dark transition-colors">
                Create one here
              </Link>
            </p>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit}>
            {error && (
              <div className="rounded bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            {error && error.toLowerCase().includes('not confirmed') && (
              <ResendConfirmation email={email} />
            )}

            <div className="space-y-1.5">
              <label htmlFor="email" className="text-sm font-medium text-ink-primary">
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={inputCls}
                placeholder="you@example.com"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="password" className="text-sm font-medium text-ink-primary">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={inputWithToggleCls}
                  placeholder="Your password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute inset-y-0 right-3 flex items-center text-ink-tertiary hover:text-ink-secondary transition-colors"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default Login;
