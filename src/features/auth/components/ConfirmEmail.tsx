import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { API_BASE } from '../../../shared/api/api';
import { parseApiError } from '../../../shared/api/apiError';
import { otpErrorMessage } from '../otpErrorCopy';

const REDIRECT_DELAY_MS = 2000;
import HeroNetworkAnimation from '../../../shared/ui/HeroNetworkAnimation';

export default function ConfirmEmail() {
  const location = useLocation();
  const navigate = useNavigate();
  const email =
    (location.state as any)?.email ||
    new URLSearchParams(location.search).get('email') ||
    '';
  const fromParam: string | undefined = (location.state as any)?.from;

  const [code, setCode] = useState('');
  // Client-side validation only; each request's own failure lives on its mutation.
  const [codeValidationMsg, setCodeValidationMsg] = useState('');
  const [resendValidationMsg, setResendValidationMsg] = useState('');

  const verifyMutation = useMutation({
    mutationFn: async (trimmedCode: string) => {
      const res = await fetch(`${API_BASE}/auth/email/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code: trimmedCode }),
        credentials: 'include',
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw parseApiError(res, data, 'Verification failed. Please try again.');
    },
    onSuccess: () => {
      setTimeout(
        () => navigate(fromParam === 'wpll' ? '/login?from=wpll' : '/login'),
        REDIRECT_DELAY_MS
      );
    },
  });

  const resendMutation = useMutation({
    mutationFn: async (targetEmail: string) => {
      const res = await fetch(`${API_BASE}/auth/email/verify/resend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: targetEmail }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw parseApiError(res, data, 'Failed to resend code.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = code.trim();
    if (trimmed.length !== 6 || !/^\d{6}$/.test(trimmed)) {
      setCodeValidationMsg('Please enter the 6-digit code from your email.');
      return;
    }
    setCodeValidationMsg('');
    verifyMutation.mutate(trimmed);
  };

  const handleResend = () => {
    if (!email) {
      setResendValidationMsg('No email available.');
      return;
    }
    setResendValidationMsg('');
    resendMutation.mutate(email);
  };

  const verified = verifyMutation.isSuccess;
  // G8: the server answers a bad code with `invalid code` / `code expired`;
  // otpErrorCopy turns those into sentences and leaves any other message alone.
  const verifyErrorMsg =
    codeValidationMsg ||
    (verifyMutation.isError
      ? otpErrorMessage(verifyMutation.error, 'Network error. Please try again.')
      : '');
  const resendFailed = Boolean(resendValidationMsg) || resendMutation.isError;
  const resendMsg =
    resendValidationMsg ||
    (resendMutation.isError
      ? resendMutation.error instanceof Error
        ? resendMutation.error.message || 'Network error.'
        : 'Network error.'
      : resendMutation.isSuccess
      ? 'New code sent! Check your inbox.'
      : '');

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

        <div className="border border-cream-muted rounded-xl bg-white p-8 text-center">
          <div className="mb-6">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">Verify your email</p>
            <h1 className="font-display text-3xl font-bold text-ink-primary">Check your inbox</h1>
            <p className="mt-2 text-sm text-ink-secondary">
              We sent a 6-digit code to{' '}
              <strong className="text-forest-mid">{email || 'your email'}</strong>.{' '}
              Enter it below to activate your account.
            </p>
          </div>

          {!verified && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                className="w-full text-center text-3xl tracking-[0.5em] rounded border border-cream-muted bg-cream-base px-4 py-3 text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors"
                autoFocus
              />

              {verifyErrorMsg && (
                <div className="rounded bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                  {verifyErrorMsg}
                </div>
              )}

              <button
                type="submit"
                disabled={verifyMutation.isPending || code.length !== 6}
                className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
              >
                {verifyMutation.isPending ? 'Verifying…' : 'Verify email'}
              </button>
            </form>
          )}

          {verified && (
            <p className="text-sm text-forest-mid font-medium">
              {fromParam === 'wpll'
                ? 'Email verified! Signing you in to unlock your results…'
                : 'Email verified! Redirecting to sign in…'}
            </p>
          )}

          {!verified && (
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
