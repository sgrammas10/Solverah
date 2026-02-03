import React, { useState } from 'react';
import { useLocation, Link } from 'react-router-dom';

const rawApiUrl = (import.meta.env.VITE_API_URL as string) || 'http://localhost:5000/api';
const normalizedApiUrl = rawApiUrl.replace(/\/+$/, '');
const API_URL = normalizedApiUrl.endsWith('/api') ? normalizedApiUrl : `${normalizedApiUrl}/api`;

export default function CheckEmail() {
  const location = useLocation();
  const email = (location.state as any)?.email || new URLSearchParams(location.search).get('email') || '';
  const [status, setStatus] = useState<'idle'|'sending'|'sent'|'error'>('idle');
  const [msg, setMsg] = useState('');

  const handleResend = async () => {
    if (!email) {
      setMsg('No email available to resend confirmation to.');
      setStatus('error');
      return;
    }
    setStatus('sending');
    try {
      const res = await fetch(`${API_URL}/resend-confirmation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setStatus('error');
        setMsg(data?.error || 'Failed to resend confirmation');
        return;
      }
      setStatus('sent');
      setMsg('Confirmation email resent. Check your inbox.');
    } catch (err: any) {
      setStatus('error');
      setMsg(err?.message || 'Network error');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 py-12 px-4 sm:px-6 lg:px-8 text-slate-100">
      <div className="max-w-md w-full space-y-8 rounded-2xl border border-white/10 bg-slate-900/70 p-8 shadow-2xl shadow-black/40 text-center">
        <h2 className="text-2xl font-semibold">Check your email</h2>
        <p className="text-sm text-slate-300">We sent a confirmation link to <strong className="text-emerald-200">{email || 'your email'}</strong>. It expires in 48 hours.</p>
        <div className="space-y-2">
          <button
            onClick={handleResend}
            className="px-4 py-2 rounded-full bg-emerald-400/10 text-emerald-200 border border-white/10"
            disabled={status === 'sending' || status === 'sent'}
          >
            {status === 'sending' ? 'Sending...' : status === 'sent' ? 'Sent' : 'Resend confirmation'}
          </button>
          {msg && <div className={`text-sm ${status === 'error' ? 'text-red-300' : 'text-emerald-300'}`}>{msg}</div>}
        </div>
        <div>
          <Link to="/login" className="underline text-emerald-200">Back to sign in</Link>
        </div>
      </div>
    </div>
  );
}
