import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { useAuth } from '../useAuth';
import { getPendingQuizSave, clearPendingQuizSave } from "../../../shared/lib/guestQuiz";
import { API_BASE } from "../../../shared/api/api";
import { parseApiError } from "../../../shared/api/apiError";

const INTAKE_STORAGE_KEY = 'solverah_intake';

function getPendingIntakeSave() {
  try {
    const raw = sessionStorage.getItem(INTAKE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.wpllAnswers?.length) return null;
    return parsed;
  } catch {
    return null;
  }
}
import HeroNetworkAnimation from '../../../shared/ui/HeroNetworkAnimation';
import { Eye, EyeOff } from 'lucide-react';

function ResendConfirmation({ email }: { email: string }) {
  const navigate = useNavigate();
  // Client-side validation only; the request's own failure lives on the mutation.
  const [validationMsg, setValidationMsg] = useState('');

  const resendMutation = useMutation({
    mutationFn: async (targetEmail: string) => {
      const res = await fetch(`${API_BASE}/auth/email/verify/resend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: targetEmail }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw parseApiError(res, data, 'Failed to resend code');
    },
    onSuccess: () => navigate('/verify-email', { state: { email } }),
  });

  const handleResend = () => {
    if (!email) {
      setValidationMsg('Please enter your email above before resending.');
      return;
    }
    setValidationMsg('');
    resendMutation.mutate(email);
  };

  const msg =
    validationMsg ||
    (resendMutation.isError
      ? resendMutation.error instanceof Error
        ? resendMutation.error.message || 'Network error'
        : 'Network error'
      : '');

  return (
    <div className="mt-2">
      <button
        onClick={handleResend}
        className="text-sm font-medium text-forest-mid underline underline-offset-4 hover:text-forest-dark transition-colors"
        disabled={resendMutation.isPending}
      >
        {resendMutation.isPending ? 'Sending…' : 'Resend verification code'}
      </button>
      {msg && <p className="mt-1 text-sm text-red-600">{msg}</p>}
    </div>
  );
}

function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const { login, fetchWithAuth } = useAuth();
  const navigate = useNavigate();

  const loginMutation = useMutation({
    mutationFn: (credentials: { email: string; password: string }) =>
      login(credentials.email, credentials.password),
    // The chained follow-ups and the redirect live here: the mutation stays
    // pending until this resolves, so the button reads "Signing in…" through
    // the whole sequence, exactly as the hand-rolled flag did.
    onSuccess: async (loggedInUser) => {
      let redirectPath = '/job-seeker/dashboard';

      const pendingIntake = getPendingIntakeSave();
      if (pendingIntake && loggedInUser.role === 'job-seeker' && fetchWithAuth) {
        try {
          // One `claim` replaces the four account-attachment endpoints; `mode`
          // selects which. This is the anonymous quiz session held in
          // sessionStorage being adopted onto the account just signed in to.
          await fetchWithAuth('/intake/claims', {
            method: 'POST',
            body: JSON.stringify({
              mode: 'session',
              selected_statement_ids: pendingIntake.selectedStatementIds,
              wpll_answers: pendingIntake.wpllAnswers.map(
                (a: { questionId: string; optionId: string }) => ({
                  question_id: a.questionId,
                  option_id: a.optionId,
                })
              ),
              wpll_insight_text: pendingIntake.wpllInsightText ?? '',
            }),
          });
          sessionStorage.removeItem(INTAKE_STORAGE_KEY);
        } catch (intakeErr) {
          console.error('Failed to save intake data:', intakeErr);
        }
      }

      const pending = getPendingQuizSave();
      if (pending && loggedInUser.role === 'job-seeker' && fetchWithAuth) {
        try {
          await fetchWithAuth('/me/profile', {
            method: 'PATCH',
            body: JSON.stringify({ profile: { quizResults: pending.quizResults } }),
          });
          await fetchWithAuth('/me/quiz-insights', {
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
    },
  });

  const loading = loginMutation.isPending;
  const error = loginMutation.isError
    ? (() => {
        const err = loginMutation.error;
        const message = err instanceof Error ? err.message : String(err);
        return message && message.toLowerCase().includes('email not confirmed')
          ? 'Your email is not confirmed. Please check your inbox.'
          : 'Failed to sign in. Please check your credentials.';
      })()
    : '';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loginMutation.mutate({ email, password });
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

            <div className="text-center">
              <Link
                to="/forgot-password"
                className="text-sm text-ink-tertiary hover:text-forest-mid transition-colors"
              >
                Forgot your password?
              </Link>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default Login;
