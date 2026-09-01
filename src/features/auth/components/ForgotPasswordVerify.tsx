import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { API_BASE } from '../../../shared/api/api';
import { useAuth } from '../useAuth';
import { User } from '../authContext';
import HeroNetworkAnimation from '../../../shared/ui/HeroNetworkAnimation';

export default function ForgotPasswordVerify() {
  const location = useLocation();
  const navigate = useNavigate();
  const { loginWithData } = useAuth();

  const email = (location.state as any)?.email || '';

  const [code, setCode] = useState('');
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [resendStatus, setResendStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [resendMsg, setResendMsg] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = code.trim();
    if (trimmed.length !== 6 || !/^\d{6}$/.test(trimmed)) {
      setStatus('error');
      setMessage('Please enter the 6-digit code from your email.');
      return;
    }
    setStatus('submitting');
    setMessage('');
    try {
      const res = await fetch(`${API_BASE}/auth/password/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, code: trimmed }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setStatus('error');
        setMessage('Invalid or expired code. Please try again.');
        return;
      }
      // Set auth state in context so protected routes work without a page reload
      loginWithData(data.user as User, data.csrfToken);
      setStatus('success');
      navigate('/job-seeker/dashboard', { replace: true });
    } catch {
      setStatus('error');
      setMessage('Network error. Please try again.');
    }
  };

  const handleResend = async () => {
    if (!email) {
      setResendStatus('error');
      setResendMsg('No email available. Please go back and enter your email.');
      return;
    }
    setResendStatus('sending');
    setResendMsg('');
    try {
      await fetch(`${API_BASE}/auth/password/forgot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      setResendStatus('sent');
      setResendMsg('New code sent! Check your inbox.');
    } catch {
      setResendStatus('error');
      setResendMsg('Network error. Please try again.');
    }
  };

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
            <p className="mt-2 text-sm text-ink-secondary">
              We sent a 6-digit code to{' '}
              <strong className="text-forest-mid">{email || 'your email'}</strong>.{' '}
              Enter it below to sign in.
            </p>
          </div>

          {status !== 'success' && (
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

              {status === 'error' && (
                <div className="rounded bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                  {message}
                </div>
              )}

              <button
                type="submit"
                disabled={status === 'submitting' || code.length !== 6}
                className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
              >
                {status === 'submitting' ? 'Verifying…' : 'Sign in'}
              </button>
            </form>
          )}

          {status !== 'success' && (
            <div className="space-y-2 pt-4">
              <p className="text-xs text-ink-tertiary">Didn't receive a code?</p>
              <button
                onClick={handleResend}
                disabled={resendStatus === 'sending' || resendStatus === 'sent'}
                className="text-sm font-medium text-forest-mid underline underline-offset-4 hover:text-forest-dark transition-colors disabled:opacity-50"
              >
                {resendStatus === 'sending' ? 'Sending…' : resendStatus === 'sent' ? 'Sent!' : 'Resend code'}
              </button>
              {resendMsg && (
                <p className={`text-xs ${resendStatus === 'error' ? 'text-red-600' : 'text-forest-mid'}`}>
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
