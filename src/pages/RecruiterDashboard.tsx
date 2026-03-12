import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/useAuth';
import { Users, Briefcase, UserPlus, Search, TrendingUp, Calendar } from 'lucide-react';

function RecruiterDashboard() {
  const { user } = useAuth();

  const stats = [
    { label: 'Active Jobs', value: '24', icon: Briefcase, color: 'text-forest-mid bg-forest-pale' },
    { label: 'Total Candidates', value: '156', icon: Users, color: 'text-forest-mid bg-forest-pale' },
    { label: 'Interviews Scheduled', value: '8', icon: Calendar, color: 'text-ink-secondary bg-cream-subtle' },
    { label: 'Hires This Month', value: '5', icon: UserPlus, color: 'text-amber-700 bg-amber-50' },
  ];

  const recentCandidates = [
    {
      name: 'Sarah Johnson',
      role: 'Senior Developer',
      matchScore: 95,
      skills: ['React', 'Node.js', 'TypeScript'],
      status: 'Interview Scheduled',
      avatar: 'https://images.pexels.com/photos/774909/pexels-photo-774909.jpeg?auto=compress&cs=tinysrgb&w=400',
    },
    {
      name: 'Michael Chen',
      role: 'UX Designer',
      matchScore: 88,
      skills: ['Figma', 'User Research', 'Prototyping'],
      status: 'Under Review',
      avatar: 'https://images.pexels.com/photos/1040880/pexels-photo-1040880.jpeg?auto=compress&cs=tinysrgb&w=400',
    },
    {
      name: 'Emily Rodriguez',
      role: 'Product Manager',
      matchScore: 92,
      skills: ['Agile', 'Strategy', 'Analytics'],
      status: 'New Application',
      avatar: 'https://images.pexels.com/photos/1181686/pexels-photo-1181686.jpeg?auto=compress&cs=tinysrgb&w=400',
    },
  ];

  const activeJobs = [
    { title: 'Senior Full Stack Developer', applications: 23, status: 'Active', posted: '3 days ago' },
    { title: 'UX/UI Designer', applications: 15, status: 'Active', posted: '1 week ago' },
    { title: 'Product Manager', applications: 31, status: 'Active', posted: '2 weeks ago' },
    { title: 'Data Scientist', applications: 8, status: 'Draft', posted: '5 days ago' },
  ];

  const matchScoreCls = (score: number) => {
    if (score >= 90) return 'text-forest-mid bg-forest-pale';
    if (score >= 80) return 'text-blue-600 bg-blue-50';
    if (score >= 70) return 'text-amber-600 bg-amber-50';
    return 'text-red-600 bg-red-50';
  };

  const statusCls = (status: string) => {
    switch (status) {
      case 'Interview Scheduled': return 'bg-blue-50 text-blue-700';
      case 'Under Review': return 'bg-amber-50 text-amber-700';
      case 'New Application': return 'bg-forest-pale text-forest-dark';
      default: return 'bg-cream-subtle text-ink-secondary';
    }
  };

  const cardCls = 'border border-cream-muted rounded-xl bg-white';

  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">

        {/* Page header */}
        <div className="mb-8">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">Dashboard</p>
          <h1 className="font-display text-3xl font-bold text-ink-primary">
            Welcome back, {user?.name}
          </h1>
          <p className="text-ink-secondary mt-2">
            Manage your recruitment pipeline and discover top talent.
          </p>
        </div>

        {/* Profile completion alert */}
        {!user?.profileComplete && (
          <div className="mb-8 rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-center gap-4">
            <Briefcase className="h-5 w-5 text-amber-600 shrink-0" />
            <p className="text-sm text-amber-800 flex-1">
              Complete your company profile to start posting jobs and accessing candidates.
            </p>
            <Link
              to="/recruiter/profile"
              className="text-sm font-semibold text-amber-700 hover:text-amber-900 transition-colors shrink-0"
            >
              Complete Profile →
            </Link>
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {stats.map((stat) => {
            const Icon = stat.icon;
            return (
              <div key={stat.label} className={`${cardCls} p-6`}>
                <div className="flex items-center gap-4">
                  <div className={`p-2.5 rounded-lg ${stat.color}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-sm text-ink-secondary">{stat.label}</p>
                    <p className="text-2xl font-semibold text-ink-primary">{stat.value}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="grid lg:grid-cols-2 gap-8">
          {/* Top Candidates */}
          <div className={cardCls}>
            <div className="p-6 border-b border-cream-muted flex items-center justify-between">
              <h2 className="font-display text-lg font-semibold text-ink-primary">Top Candidates</h2>
              <button className="text-sm font-medium text-forest-mid hover:text-forest-dark transition-colors">
                View All
              </button>
            </div>
            <div className="p-6 space-y-4">
              {recentCandidates.map((candidate, index) => (
                <div
                  key={index}
                  className="flex items-center gap-4 p-4 rounded-lg border border-cream-muted hover:border-forest-pale transition-colors"
                >
                  <img
                    src={candidate.avatar}
                    alt={candidate.name}
                    className="h-10 w-10 rounded-full object-cover shrink-0"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <h3 className="text-sm font-semibold text-ink-primary truncate">{candidate.name}</h3>
                      <span className={`ml-2 px-2 py-0.5 text-xs rounded font-medium shrink-0 ${matchScoreCls(candidate.matchScore)}`}>
                        {candidate.matchScore}% match
                      </span>
                    </div>
                    <p className="text-sm text-ink-secondary mb-2">{candidate.role}</p>
                    <div className="flex flex-wrap gap-1">
                      {candidate.skills.slice(0, 3).map((skill, i) => (
                        <span key={i} className="px-2 py-0.5 text-xs bg-cream-subtle rounded text-ink-secondary">
                          {skill}
                        </span>
                      ))}
                      <span className={`px-2 py-0.5 text-xs rounded font-medium ${statusCls(candidate.status)}`}>
                        {candidate.status}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Active Jobs */}
          <div className={cardCls}>
            <div className="p-6 border-b border-cream-muted flex items-center justify-between">
              <h2 className="font-display text-lg font-semibold text-ink-primary">Active Job Postings</h2>
              <button className="text-sm font-medium text-forest-mid hover:text-forest-dark transition-colors">
                + New Job
              </button>
            </div>
            <div className="p-6 space-y-3">
              {activeJobs.map((job, index) => (
                <div key={index} className="p-4 rounded-lg border border-cream-muted">
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="text-sm font-semibold text-ink-primary">{job.title}</h3>
                    <span
                      className={`ml-2 px-2 py-0.5 text-xs rounded font-medium shrink-0 ${
                        job.status === 'Active' ? 'bg-forest-pale text-forest-dark' : 'bg-cream-subtle text-ink-secondary'
                      }`}
                    >
                      {job.status}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-ink-tertiary">
                    <span>{job.applications} applications</span>
                    <span>Posted {job.posted}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="mt-8">
          <h2 className="font-display text-lg font-semibold text-ink-primary mb-4">Quick Actions</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {[
              { to: '/recruiter/profile', icon: Briefcase, label: 'Company Profile', sub: 'Update company info' },
              { icon: Search, label: 'Find Candidates', sub: 'Search talent pool' },
              { icon: UserPlus, label: 'Post New Job', sub: 'Create job posting' },
              { icon: TrendingUp, label: 'Analytics', sub: 'View hiring insights' },
            ].map(({ to, icon: Icon, label, sub }, i) => {
              const cls = 'flex items-center gap-4 p-5 rounded-xl border border-cream-muted bg-white hover:border-forest-pale transition-colors text-left';
              const inner = (
                <>
                  <div className="p-2 bg-forest-pale rounded-lg shrink-0">
                    <Icon className="h-4 w-4 text-forest-mid" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-ink-primary">{label}</h3>
                    <p className="text-sm text-ink-secondary">{sub}</p>
                  </div>
                </>
              );
              return to ? (
                <Link key={i} to={to} className={cls}>{inner}</Link>
              ) : (
                <button key={i} className={cls}>{inner}</button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default RecruiterDashboard;
