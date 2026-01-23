import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Mail, Lock, User, Users, Briefcase } from 'lucide-react';

function Register() {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'job-seeker' as 'job-seeker' | 'recruiter'
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (formData.password.length < 12) {
      setError('Password must be at least 12 characters');
      return;
    }

    setLoading(true);

    try {
      await register(formData.email, formData.password, formData.name, formData.role);
      const redirectPath = formData.role === 'job-seeker' ? '/job-seeker/profile' : '/recruiter/profile';
      navigate(redirectPath);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes('User already exists') || message.toLowerCase().includes('already exists')) {
        setError('An account with that email already exists');
      } else if (message.includes('409') || message.includes('400')) {
        setError('Failed to create account. Please check your input and try again.');
      } else {
        setError(message || 'Failed to create account. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 py-12 px-4 sm:px-6 lg:px-8 text-slate-100">
      <div className="max-w-md w-full space-y-8 rounded-2xl border border-white/10 bg-slate-900/70 p-8 shadow-2xl shadow-black/40">
        <div>
          <div className="mx-auto h-12 w-12 flex items-center justify-center rounded-full bg-emerald-400/10">
            <Briefcase className="h-6 w-6 text-emerald-200" />
          </div>
          <h2 className="mt-6 text-center text-3xl font-semibold text-white">
            Create your account
          </h2>
          <p className="mt-2 text-center text-sm text-slate-200/80">
            Or{' '}
            <Link
              to="/login"
              className="font-semibold text-emerald-200 hover:text-emerald-100"
            >
              sign in to your existing account
            </Link>
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="rounded-md bg-red-500/10 p-4 text-sm text-red-100 ring-1 ring-red-500/30">
              {error}
            </div>
          )}

          {/* Role Selection */}
          <div>
            <label className="block text-sm font-medium text-slate-200 mb-2">
              I am a:
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setFormData({ ...formData, role: 'job-seeker' })}
                className={`p-3 rounded-lg border transition-all ${
                  formData.role === 'job-seeker'
                    ? 'border-emerald-300/60 bg-emerald-400/10 text-emerald-100'
                    : 'border-white/10 bg-white/5 text-slate-200 hover:border-emerald-300/50'
                }`}
              >
                <Users className="h-5 w-5 mx-auto mb-1" />
                <div className="text-sm font-medium">Job Seeker</div>
              </button>
              <button
                type="button"
                onClick={() => setFormData({ ...formData, role: 'recruiter' })}
                className={`p-3 rounded-lg border transition-all ${
                  formData.role === 'recruiter'
                    ? 'border-emerald-300/60 bg-emerald-400/10 text-emerald-100'
                    : 'border-white/10 bg-white/5 text-slate-200 hover:border-emerald-300/50'
                }`}
              >
                <Briefcase className="h-5 w-5 mx-auto mb-1" />
                <div className="text-sm font-medium">Recruiter</div>
              </button>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label htmlFor="name" className="sr-only">
                Full name
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <User className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  id="name"
                  name="name"
                  type="text"
                  required
                  value={formData.name}
                  onChange={handleInputChange}
                  className="appearance-none relative block w-full px-3 py-2 pl-10 rounded-md border border-white/10 bg-white/5 text-sm text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-300/50 focus:border-emerald-300/70"
                  placeholder="Full name"
                />
              </div>
            </div>

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
                  value={formData.email}
                  onChange={handleInputChange}
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
                  required
                  value={formData.password}
                  onChange={handleInputChange}
                  className="appearance-none relative block w-full px-3 py-2 pl-10 rounded-md border border-white/10 bg-white/5 text-sm text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-300/50 focus:border-emerald-300/70"
                  placeholder="Password (min. 6 characters)"
                />
              </div>
            </div>

            <div>
              <label htmlFor="confirmPassword" className="sr-only">
                Confirm Password
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  required
                  value={formData.confirmPassword}
                  onChange={handleInputChange}
                  className="appearance-none relative block w-full px-3 py-2 pl-10 rounded-md border border-white/10 bg-white/5 text-sm text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-300/50 focus:border-emerald-300/70"
                  placeholder="Confirm password"
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
              {loading ? 'Creating account...' : 'Create account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default Register;
