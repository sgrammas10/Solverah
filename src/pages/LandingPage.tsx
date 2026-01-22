import React from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Users, Target, BarChart3, Shield, ArrowRight } from 'lucide-react';

function LandingPage() {
  const { user } = useAuth();

  // If user is logged in, redirect to feed
  if (user) {
    return <Navigate to="/feed" replace />;
  }

  return (
    <div className="bg-slate-950 text-slate-100">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-600/30 via-blue-700/20 to-indigo-800/30" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.18),_transparent_45%),radial-gradient(circle_at_bottom_right,_rgba(59,130,246,0.18),_transparent_45%)]" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16">
          <div className="text-center">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-200">Solverah</p>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-semibold text-white mb-6">
              Perfect Job Matches with
              <span className="text-emerald-200 block">Solverah Intelligence</span>
            </h1>
            <p className="text-xl text-slate-200/80 mb-8 max-w-3xl mx-auto">
              Connect job seekers and employers through comprehensive profiles powered by
              resumes, performance reviews, and our proprietary psychometric assessments.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Link
                to="/register"
                className="inline-flex items-center justify-center px-8 py-3 rounded-full text-base font-semibold text-slate-950 bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 shadow-lg shadow-emerald-500/25 transition hover:shadow-emerald-400/30"
              >
                Get Started
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
              <Link
                to="/login"
                className="inline-flex items-center justify-center px-8 py-3 rounded-full text-base font-semibold text-slate-100 border border-white/15 bg-white/5 hover:border-emerald-300/60 transition-colors"
              >
                Sign In
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Features Section */}
      <div className="py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-semibold text-white mb-4">
              Why Choose Solverah?
            </h2>
            <p className="text-lg text-slate-200/80">
              Our comprehensive approach to job matching goes beyond traditional methods
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            <div className="text-center p-6 rounded-2xl border border-white/10 bg-slate-900/70 shadow-lg shadow-black/30">
              <div className="w-12 h-12 bg-emerald-400/10 rounded-lg flex items-center justify-center mx-auto mb-4">
                <Users className="h-6 w-6 text-emerald-200" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Comprehensive Profiles
              </h3>
              <p className="text-slate-200/80">
                Combine resumes, performance reviews, and psychometric assessments for complete candidate insights
              </p>
            </div>

            <div className="text-center p-6 rounded-2xl border border-white/10 bg-slate-900/70 shadow-lg shadow-black/30">
              <div className="w-12 h-12 bg-blue-400/10 rounded-lg flex items-center justify-center mx-auto mb-4">
                <Target className="h-6 w-6 text-blue-200" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Smart Matching
              </h3>
              <p className="text-slate-200/80">
                AI-powered algorithms match candidates with roles based on skills, personality, and culture fit
              </p>
            </div>

            <div className="text-center p-6 rounded-2xl border border-white/10 bg-slate-900/70 shadow-lg shadow-black/30">
              <div className="w-12 h-12 bg-indigo-400/10 rounded-lg flex items-center justify-center mx-auto mb-4">
                <BarChart3 className="h-6 w-6 text-indigo-200" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Performance Insights
              </h3>
              <p className="text-slate-200/80">
                Track and analyze performance data to predict job success and career growth potential
              </p>
            </div>

            <div className="text-center p-6 rounded-2xl border border-white/10 bg-slate-900/70 shadow-lg shadow-black/30">
              <div className="w-12 h-12 bg-emerald-400/10 rounded-lg flex items-center justify-center mx-auto mb-4">
                <Shield className="h-6 w-6 text-emerald-200" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Proprietary Assessments
              </h3>
              <p className="text-slate-200/80">
                Our trademarked psychometric tests provide unique insights into candidate potential
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* User Types Section */}
      <div className="py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-semibold text-white mb-4">
              Built for Both Sides of Hiring
            </h2>
          </div>

          <div className="grid md:grid-cols-2 gap-12">
            <div className="text-center rounded-2xl border border-white/10 bg-slate-900/70 p-8 shadow-lg shadow-black/30">
              <div className="w-16 h-16 bg-emerald-400/10 rounded-full flex items-center justify-center mx-auto mb-6">
                <Users className="h-8 w-8 text-emerald-200" />
              </div>
              <h3 className="text-2xl font-semibold text-white mb-4">For Job Seekers</h3>
              <ul className="text-left space-y-3 text-slate-200/80">
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-emerald-300 rounded-full mr-3"></div>
                  Create comprehensive profiles with resume, performance history, and assessments
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-emerald-300 rounded-full mr-3"></div>
                  Get matched with roles that fit your skills and personality
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-emerald-300 rounded-full mr-3"></div>
                  Showcase your true potential beyond traditional resumes
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-emerald-300 rounded-full mr-3"></div>
                  Receive personalized career development insights
                </li>
              </ul>
            </div>

            <div className="text-center rounded-2xl border border-white/10 bg-slate-900/70 p-8 shadow-lg shadow-black/30">
              <div className="w-16 h-16 bg-blue-400/10 rounded-full flex items-center justify-center mx-auto mb-6">
                <Target className="h-8 w-8 text-blue-200" />
              </div>
              <h3 className="text-2xl font-semibold text-white mb-4">For Recruiters</h3>
              <ul className="text-left space-y-3 text-slate-200/80">
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-blue-300 rounded-full mr-3"></div>
                  Access detailed candidate profiles with performance data
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-blue-300 rounded-full mr-3"></div>
                  Use AI-powered matching to find ideal candidates
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-blue-300 rounded-full mr-3"></div>
                  Evaluate culture fit through psychometric assessments
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-blue-300 rounded-full mr-3"></div>
                  Reduce hiring time and improve success rates
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LandingPage;
