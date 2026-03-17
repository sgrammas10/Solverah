import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/useAuth';
import { Users, Briefcase } from 'lucide-react';
import HeroNetworkAnimation from '../components/HeroNetworkAnimation';

function Register() {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'job-seeker' as 'job-seeker' | 'recruiter',
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
    if (!/[A-Z]/.test(formData.password)) {
      setError('Password must contain an uppercase letter');
      return;
    }
    if (!/[a-z]/.test(formData.password)) {
      setError('Password must contain a lowercase letter');
      return;
    }
    if (!/[0-9]/.test(formData.password)) {
      setError('Password must contain a number');
      return;
    }
    if (!/[^A-Za-z0-9]/.test(formData.password)) {
      setError('Password must contain a symbol');
      return;
    }

    setLoading(true);
    try {
      await register(formData.email, formData.password, formData.name, formData.role);
      navigate('/verify-email', { state: { email: formData.email } });
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
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const inputCls =
    'w-full rounded border border-cream-muted bg-cream-base px-4 py-3 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors';

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
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">Get started</p>
            <h1 className="font-display text-3xl font-bold text-ink-primary">Create your account</h1>
            <p className="mt-2 text-sm text-ink-secondary">
              Already have an account?{' '}
              <Link to="/login" className="font-semibold text-forest-mid hover:text-forest-dark transition-colors">
                Sign in here
              </Link>
            </p>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit}>
            {error && (
              <div className="rounded bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            {/* Role selection */}
            <div className="space-y-1.5">
              <p className="text-sm font-medium text-ink-primary">I am a:</p>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, role: 'job-seeker' })}
                  className={`flex flex-col items-center gap-1.5 p-4 rounded border transition-colors ${
                    formData.role === 'job-seeker'
                      ? 'border-forest-light bg-forest-pale text-forest-dark'
                      : 'border-cream-muted bg-cream-base text-ink-secondary hover:border-forest-pale'
                  }`}
                >
                  <Users className="h-5 w-5" />
                  <span className="text-sm font-medium">Job Seeker</span>
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, role: 'recruiter' })}
                  className={`flex flex-col items-center gap-1.5 p-4 rounded border transition-colors ${
                    formData.role === 'recruiter'
                      ? 'border-forest-light bg-forest-pale text-forest-dark'
                      : 'border-cream-muted bg-cream-base text-ink-secondary hover:border-forest-pale'
                  }`}
                >
                  <Briefcase className="h-5 w-5" />
                  <span className="text-sm font-medium">Recruiter</span>
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="name" className="text-sm font-medium text-ink-primary">Full name</label>
              <input
                id="name"
                name="name"
                type="text"
                required
                value={formData.name}
                onChange={handleInputChange}
                className={inputCls}
                placeholder="Your full name"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="email" className="text-sm font-medium text-ink-primary">Email address</label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={formData.email}
                onChange={handleInputChange}
                className={inputCls}
                placeholder="you@example.com"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="password" className="text-sm font-medium text-ink-primary">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                required
                value={formData.password}
                onChange={handleInputChange}
                className={inputCls}
                placeholder="Min. 12 characters"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="confirmPassword" className="text-sm font-medium text-ink-primary">Confirm password</label>
              <input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                required
                value={formData.confirmPassword}
                onChange={handleInputChange}
                className={inputCls}
                placeholder="Repeat your password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
            >
              {loading ? 'Creating account…' : 'Create account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default Register;
