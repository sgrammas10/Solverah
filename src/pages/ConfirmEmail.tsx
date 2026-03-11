import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { API_BASE as API_URL } from '../utils/api';

export default function ConfirmEmail() {
  const location = useLocation();
  const navigate = useNavigate();
  const email =
    (location.state as any)?.email ||
    new URLSearchParams(location.search).get('email') ||
    '';

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
      const res = await fetch(`${API_URL}/confirm-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code: trimmed }),
        credentials: 'include',
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setStatus('error');
        setMessage(data?.error || 'Verification failed. Please try again.');
        return;
      }
      setStatus('success');
      setMessage('Email verified! Redirecting to sign in...');
      setTimeout(() => navigate('/login'), 2000);
    } catch (err: any) {
      setStatus('error');
      setMessage(err?.message || 'Network error. Please try again.');
    }
  };

  const handleResend = async () => {
    if (!email) {
      setResendStatus('error');
      setResendMsg('No email available.');
      return;
    }
    setResendStatus('sending');
    setResendMsg('');
    try {
      const res = await fetch(`${API_URL}/resend-confirmation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setResendStatus('error');
        setResendMsg(data?.error || 'Failed to resend code.');
        return;
      }
      setResendStatus('sent');
      setResendMsg('New code sent! Check your inbox.');
    } catch (err: any) {
      setResendStatus('error');
      setResendMsg(err?.message || 'Network error.');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 py-12 px-4 sm:px-6 lg:px-8 text-slate-100">
      <div className="max-w-md w-full space-y-8 rounded-2xl border border-white/10 bg-slate-900/70 p-8 shadow-2xl shadow-black/40 text-center">
        <h2 className="text-2xl font-semibold">Check your email</h2>
        <p className="text-sm text-slate-300">
          We sent a 6-digit verification code to{' '}
          <strong className="text-emerald-200">{email || 'your email'}</strong>.{' '}
          Enter it below to activate your account.
        </p>

        {status !== 'success' && (
          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={code}
              onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000"
              className="w-full text-center text-3xl tracking-[0.5em] rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
              autoFocus
            />

            {status === 'error' && (
              <p className="text-sm text-red-300">{message}</p>
            )}

            <button
              type="submit"
              disabled={status === 'submitting' || code.length !== 6}
              className="w-full py-2 px-4 rounded-full text-sm font-semibold text-slate-950 bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {status === 'submitting' ? 'Verifying...' : 'Verify email'}
            </button>
          </form>
        )}

        {status === 'success' && (
          <p className="text-sm text-emerald-300">{message}</p>
        )}

        {status !== 'success' && (
          <div className="space-y-2 pt-2">
            <p className="text-xs text-slate-400">Didn't receive a code?</p>
            <button
              onClick={handleResend}
              disabled={resendStatus === 'sending' || resendStatus === 'sent'}
              className="text-sm text-emerald-200 underline disabled:opacity-50"
            >
              {resendStatus === 'sending' ? 'Sending...' : resendStatus === 'sent' ? 'Sent!' : 'Resend code'}
            </button>
            {resendMsg && (
              <p className={`text-xs ${resendStatus === 'error' ? 'text-red-300' : 'text-emerald-300'}`}>
                {resendMsg}
              </p>
            )}
          </div>
        )}

        <div className="pt-2">
          <Link to="/login" className="underline text-slate-400 text-sm">
            Back to sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
