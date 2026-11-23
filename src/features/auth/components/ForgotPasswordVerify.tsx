import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { API_BASE } from '../../../shared/api/api';
import { ApiError, parseApiError } from '../../../shared/api/apiError';
import { otpErrorMessage } from '../otpErrorCopy';
import { useAuth } from '../useAuth';
import { User } from '../authContext';
import HeroNetworkAnimation from '../../../shared/ui/HeroNetworkAnimation';

export default function ForgotPasswordVerify() {
  const location = useLocation();
  const navigate = useNavigate();
  const { loginWithData } = useAuth();

  const routedEmail: string =
    (location.state as any)?.email ||
    new URLSearchParams(location.search).get('email') ||
    '';
  // Same fix as /verify-email's G35: opened in a new tab there is no router
  // state, and the page used to post an empty address and resend to nobody.
  // With no routed address it asks for one.
  const askForEmail = !routedEmail;
  const [typedEmail, setTypedEmail] = useState('');
  const email = routedEmail || typedEmail.trim().toLowerCase();

  const [code, setCode] = useState('');
  // Client-side validation only; each request's own failure lives on its mutation.
  const [codeValidationMsg, setCodeValidationMsg] = useState('');
  const [resendValidationMsg, setResendValidationMsg] = useState('');

  const resetMutation = useMutation({
    mutationFn: async (trimmedCode: string) => {
      const res = await fetch(`${API_BASE}/auth/password/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, code: trimmedCode }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw parseApiError(res, data);
      return data;
    },
    onSuccess: (data) => {
      // Set auth state in context so protected routes work without a page reload
      loginWithData(data.user as User, data.csrfToken);
      navigate('/job-seeker/dashboard', { replace: true });
    },
  });

  const resendMutation = useMutation({
    // G34: this used to ignore the response, so a 429 from the 3/minute limit
    // still read "New code sent!". The server's own wording is shown instead;
    // with no usable body, parseApiError's status fallback applies.
    mutationFn: async (targetEmail: string) => {
      const res = await fetch(`${API_BASE}/auth/password/forgot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: targetEmail }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw parseApiError(res, data);
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      setCodeValidationMsg('Please enter the email address you asked for a code with.');
      return;
    }
    const trimmed = code.trim();
    if (trimmed.length !== 6 || !/^\d{6}$/.test(trimmed)) {
      setCodeValidationMsg('Please enter the 6-digit code from your email.');
      return;
    }
    setCodeValidationMsg('');
    resetMutation.mutate(trimmed);
  };

  const handleResend = () => {
    if (!email) {
      setResendValidationMsg('Enter your email address above, then press Resend code.');
      return;
    }
    setResendValidationMsg('');
    resendMutation.mutate(email);
  };

  // Keyed on the wire string `invalid_or_expired_code` rather than on "any
  // ApiError": before G8 a 429 from the 5/minute limiter was shown as a wrong
  // code, which sent people back to retype a code that was fine.
  const message =
    codeValidationMsg ||
    (resetMutation.isError
      ? otpErrorMessage(resetMutation.error, 'Network error. Please try again.')
      : '');
  const showMessage = Boolean(codeValidationMsg) || resetMutation.isError;
  const resendFailed = Boolean(resendValidationMsg) || resendMutation.isError;
  const resendMsg =
    resendValidationMsg ||
    (resendMutation.isError
      ? resendMutation.error instanceof ApiError
        ? resendMutation.error.message
        : 'Network error. Please try again.'
      : resendMutation.isSuccess
      ? 'New code sent! Check your inbox.'
      : '');

  return (
    <div className="relative overflow-hidden min-h-screen bg-cream-base font-sans flex items-center justify-center py-16 px-4">
      <HeroNetworkAnimation theme="light" />
      <div className="relative z-10 w-full max-w-md">
        <Link
          to="/forgot-password"
          className="inline-flex items-center gap-1.5 text-sm text-ink-tertiary hover:text-forest-mid transition-colors mb-8"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Back
        </Link>

        <div className="border border-cream-muted rounded-xl bg-white p-8 text-center">
          <div className="mb-6">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">Check your inbox</p>
            <h1 className="font-display text-3xl font-bold text-ink-primary">Enter your code</h1>
            {askForEmail ? (
              <p className="mt-2 text-sm text-ink-secondary">
                Enter your email and the 6-digit code we sent to it to sign in.
              </p>
            ) : (
              <p className="mt-2 text-sm text-ink-secondary">
                We sent a 6-digit code to{' '}
                <strong className="text-forest-mid">{routedEmail}</strong>.{' '}
                Enter it below to sign in.
              </p>
            )}
          </div>

          {!resetMutation.isSuccess && (
            <form onSubmit={handleSubmit} className="space-y-4">
              {askForEmail && (
                <div className="space-y-1.5 text-left">
                  <label htmlFor="reset-code-email-address" className="text-sm font-medium text-ink-primary">
                    Email address
                  </label>
                  <input
                    id="reset-code-email-address"
                    type="email"
                    autoComplete="email"
                    value={typedEmail}
                    onChange={e => setTypedEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full rounded border border-cream-muted bg-cream-base px-4 py-3 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors"
                    autoFocus
                  />
                </div>
              )}
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                aria-label="6-digit code"
                className="w-full text-center text-3xl tracking-[0.5em] rounded border border-cream-muted bg-cream-base px-4 py-3 text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors"
                autoFocus={!askForEmail}
              />

              {showMessage && (
                <div className="rounded bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                  {message}
                </div>
              )}

              <button
                type="submit"
                disabled={resetMutation.isPending || code.length !== 6}
                className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
              >
                {resetMutation.isPending ? 'Verifying…' : 'Sign in'}
              </button>
            </form>
          )}

          {!resetMutation.isSuccess && (
            <div className="space-y-2 pt-4">
              <p className="text-xs text-ink-tertiary">Didn't receive a code?</p>
              <button
                onClick={handleResend}
                disabled={resendMutation.isPending || resendMutation.isSuccess}
                className="text-sm font-medium text-forest-mid underline underline-offset-4 hover:text-forest-dark transition-colors disabled:opacity-50"
              >
                {resendMutation.isPending ? 'Sending…' : resendMutation.isSuccess ? 'Sent!' : 'Resend code'}
              </button>
              {resendMsg && (
                <p className={`text-xs ${resendFailed ? 'text-red-600' : 'text-forest-mid'}`}>
                  {resendMsg}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
