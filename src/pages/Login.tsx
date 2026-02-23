import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/useAuth';
import { getPendingQuizSave, clearPendingQuizSave } from "../utils/guestQuiz";
import { Mail, Lock, Briefcase } from 'lucide-react';

function ResendConfirmation({ email }: { email: string }) {
  const [status, setStatus] = useState<'idle'|'sending'|'sent'|'error'>('idle');
  const [msg, setMsg] = useState('');

  const rawApiUrl = (import.meta.env.VITE_API_URL as string) || 'http://localhost:5000/api';
  const normalizedApiUrl = rawApiUrl.replace(/\/+$/, '');
  const API_URL = normalizedApiUrl.endsWith('/api') ? normalizedApiUrl : `${normalizedApiUrl}/api`;

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
    <div className="mt-2">
      <button
        onClick={handleResend}
        className="text-sm underline text-emerald-200"
        disabled={status === 'sending' || status === 'sent'}
      >
        {status === 'sending' ? 'Sending...' : status === 'sent' ? 'Sent' : 'Resend confirmation email'}
      </button>
      {msg && <div className={`text-sm ${status === 'error' ? 'text-red-300' : 'text-emerald-300'}`}>{msg}</div>}
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
      if (pending && loggedInUser.role === "job-seeker" && fetchWithAuth) {
        try {
          await fetchWithAuth("/profile", {
            method: "POST",
            body: JSON.stringify({
              profileData: {
                quizResults: pending.quizResults,
              },
            }),
          });

          await fetchWithAuth("/quiz-insights", {
            method: "POST",
            body: JSON.stringify(pending.quizPayload),
          });

          redirectPath = `/quiz-insights?group=${encodeURIComponent(pending.quizGroup)}`;
          clearPendingQuizSave();
        } catch (saveErr) {
          console.error("Failed to save pending quiz:", saveErr);
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

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 py-12 px-4 sm:px-6 lg:px-8 text-slate-100">
      <div className="max-w-md w-full space-y-8 rounded-2xl border border-white/10 bg-slate-900/70 p-8 shadow-2xl shadow-black/40">
        <div>
          <div className="mx-auto h-12 w-12 flex items-center justify-center rounded-full bg-emerald-400/10">
            <Briefcase className="h-6 w-6 text-emerald-200" />
          </div>
          <h2 className="mt-6 text-center text-3xl font-semibold text-white">
            Sign in to your account
          </h2>
          <p className="mt-2 text-center text-sm text-slate-200/80">
            Or{' '}
            <Link
              to="/register"
              className="font-semibold text-emerald-200 hover:text-emerald-100"
            >
              create a new account
            </Link>
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="rounded-md bg-red-500/10 p-4 text-sm text-red-100 ring-1 ring-red-500/30">
              {error}
              {/* Resend confirmation when email not confirmed */}
            </div>
          )}

          {/* Resend confirmation UI when appropriate */}
          {error && error.toLowerCase().includes('not confirmed') && (
            <div className="mt-3 text-center">
              <ResendConfirmation email={email} />
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label htmlFor="email" className="sr-only">
                Email address
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Mail className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="appearance-none relative block w-full px-3 py-2 pl-10 rounded-md border border-white/10 bg-white/5 text-sm text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-300/50 focus:border-emerald-300/70"
                  placeholder="Email address"
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="sr-only">
                Password
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="appearance-none relative block w-full px-3 py-2 pl-10 rounded-md border border-white/10 bg-white/5 text-sm text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-300/50 focus:border-emerald-300/70"
                  placeholder="Password"
                />
              </div>
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={loading}
              className="group relative w-full flex justify-center py-2 px-4 rounded-full text-sm font-semibold text-slate-950 bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 shadow-lg shadow-emerald-500/25 transition hover:shadow-emerald-400/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default Login;
