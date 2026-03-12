import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/useAuth';
import { getPendingQuizSave, clearPendingQuizSave } from "../utils/guestQuiz";
import { API_BASE as API_URL } from "../utils/api";

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
      const res = await fetch(`${API_URL}/resend-confirmation`, {
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

  return (
    <div className="min-h-screen bg-cream-base font-sans flex items-center justify-center py-16 px-4">
      <div className="w-full max-w-md">
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
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputCls}
                placeholder="Your password"
              />
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
