import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { API_BASE } from '../../../shared/api/api';
import { ApiError, parseApiError } from '../../../shared/api/apiError';
import HeroNetworkAnimation from '../../../shared/ui/HeroNetworkAnimation';

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');

  const forgotMutation = useMutation({
    mutationFn: async (normalizedEmail: string) => {
      const res = await fetch(`${API_BASE}/auth/password/forgot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: normalizedEmail }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw parseApiError(res, data, 'Something went wrong. Please try again.');
      return normalizedEmail;
    },
    onSuccess: (normalizedEmail) =>
      navigate('/forgot-password/verify', { state: { email: normalizedEmail } }),
  });

  const loading = forgotMutation.isPending;
  // An ApiError carries the server's own wording; anything else never reached it.
  const error = forgotMutation.isError
    ? forgotMutation.error instanceof ApiError
      ? forgotMutation.error.message
      : 'Network error. Please try again.'
    : '';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    forgotMutation.mutate(email.trim().toLowerCase());
  };

  const inputCls =
    'w-full rounded border border-cream-muted bg-cream-base px-4 py-3 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors';

  return (
    <div className="relative overflow-hidden min-h-screen bg-cream-base font-sans flex items-center justify-center py-16 px-4">
      <HeroNetworkAnimation theme="light" />
      <div className="relative z-10 w-full max-w-md">
        <Link
          to="/login"
          className="inline-flex items-center gap-1.5 text-sm text-ink-tertiary hover:text-forest-mid transition-colors mb-8"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Back to sign in
        </Link>

        <div className="border border-cream-muted rounded-xl bg-white p-8">
          <div className="mb-8">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">Forgot password</p>
            <h1 className="font-display text-3xl font-bold text-ink-primary">Sign in with a code</h1>
            <p className="mt-2 text-sm text-ink-secondary">
              Enter your email and we'll send a one-time code you can use to sign in.
            </p>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit}>
            {error && (
              <div className="rounded bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
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
                autoFocus
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
            >
              {loading ? 'Sending…' : 'Send code'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
