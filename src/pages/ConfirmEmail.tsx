import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';

const rawApiUrl = (import.meta.env.VITE_API_URL as string) || 'http://localhost:5000/api';
const normalizedApiUrl = rawApiUrl.replace(/\/+$/, '');
const API_URL = normalizedApiUrl.endsWith('/api') ? normalizedApiUrl : `${normalizedApiUrl}/api`;

export default function ConfirmEmail() {
  const [status, setStatus] = useState<'loading' | 'success' | 'error' | 'no-token'>('loading');
  const [message, setMessage] = useState('');
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const token = params.get('token');
    if (!token) {
      setStatus('no-token');
      setMessage('No confirmation token provided.');
      return;
    }

    (async () => {
      try {
        const res = await fetch(`${API_URL}/confirm-email`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
          credentials: 'include',
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) {
          setStatus('error');
          setMessage(data?.error || 'Failed to confirm email');
          return;
        }
        setStatus('success');
        setMessage('Email confirmed. Redirecting to sign in...');
        setTimeout(() => navigate('/login'), 2500);
      } catch (err: any) {
        setStatus('error');
        setMessage(err?.message || 'Network error');
      }
    })();
  }, [location, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 py-12 px-4 sm:px-6 lg:px-8 text-slate-100">
      <div className="max-w-md w-full space-y-8 rounded-2xl border border-white/10 bg-slate-900/70 p-8 shadow-2xl shadow-black/40 text-center">
        <h2 className="text-2xl font-semibold">Email confirmation</h2>
        {status === 'loading' && <p className="text-sm text-slate-300">Confirming your email...</p>}
        {status === 'success' && <p className="text-sm text-emerald-300">{message}</p>}
        {status === 'error' && <p className="text-sm text-red-300">{message}</p>}
        {status === 'no-token' && <p className="text-sm text-red-300">{message}</p>}
        <div>
          <Link to="/login" className="underline text-emerald-200">Go to sign in</Link>
        </div>
      </div>
    </div>
  );
}
