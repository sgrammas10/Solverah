import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/useAuth';
import {
  Users,
  Briefcase,
  UserPlus,
  Search,
  TrendingUp,
  Calendar,
  MessageCircle,
  Star,
  Filter,
  Eye
} from 'lucide-react';

function RecruiterDashboard() {
  const { user } = useAuth();

  const stats = [
    { label: 'Active Jobs', value: '24', icon: Briefcase, color: 'blue' },
    { label: 'Total Candidates', value: '156', icon: Users, color: 'green' },
    { label: 'Interviews Scheduled', value: '8', icon: Calendar, color: 'purple' },
    { label: 'Hires This Month', value: '5', icon: UserPlus, color: 'orange' }
  ];

  const recentCandidates = [
    {
      name: 'Sarah Johnson',
      role: 'Senior Developer',
      matchScore: 95,
      skills: ['React', 'Node.js', 'TypeScript'],
      status: 'Interview Scheduled',
      avatar: 'https://images.pexels.com/photos/774909/pexels-photo-774909.jpeg?auto=compress&cs=tinysrgb&w=400'
    },
    {
      name: 'Michael Chen',
      role: 'UX Designer',
      matchScore: 88,
      skills: ['Figma', 'User Research', 'Prototyping'],
      status: 'Under Review',
      avatar: 'https://images.pexels.com/photos/1040880/pexels-photo-1040880.jpeg?auto=compress&cs=tinysrgb&w=400'
    },
    {
      name: 'Emily Rodriguez',
      role: 'Product Manager',
      matchScore: 92,
      skills: ['Agile', 'Strategy', 'Analytics'],
      status: 'New Application',
      avatar: 'https://images.pexels.com/photos/1181686/pexels-photo-1181686.jpeg?auto=compress&cs=tinysrgb&w=400'
    }
  ];

  const activeJobs = [
    { title: 'Senior Full Stack Developer', applications: 23, status: 'Active', posted: '3 days ago' },
    { title: 'UX/UI Designer', applications: 15, status: 'Active', posted: '1 week ago' },
    { title: 'Product Manager', applications: 31, status: 'Active', posted: '2 weeks ago' },
    { title: 'Data Scientist', applications: 8, status: 'Draft', posted: '5 days ago' }
  ];

  const getMatchScoreColor = (score: number) => {
    if (score >= 90) return 'text-emerald-200 bg-emerald-400/10';
    if (score >= 80) return 'text-blue-200 bg-blue-400/10';
    if (score >= 70) return 'text-amber-200 bg-amber-400/10';
    return 'text-red-200 bg-red-400/10';
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'Interview Scheduled':
        return 'bg-blue-400/10 text-blue-200';
      case 'Under Review':
        return 'bg-amber-400/10 text-amber-200';
      case 'New Application':
        return 'bg-emerald-400/10 text-emerald-200';
      default:
        return 'bg-white/5 text-slate-200';
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-slate-100">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-semibold text-white">
          Welcome back, {user?.name}!
        </h1>
        <p className="text-slate-200/80 mt-2">
          Manage your recruitment pipeline and discover top talent.
        </p>
      </div>

      {/* Profile Completion Alert */}
      {!user?.profileComplete && (
        <div className="mb-8 rounded-lg border border-blue-400/30 bg-blue-500/10 p-4">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <Briefcase className="h-5 w-5 text-blue-200" />
            </div>
            <div className="ml-3 flex-1">
              <p className="text-sm text-blue-100">
                Complete your company profile to start posting jobs and accessing candidates.
              </p>
            </div>
            <div className="ml-3">
              <Link
                to="/recruiter/profile"
                className="text-sm font-semibold text-blue-200 hover:text-blue-100"
              >
                Complete Profile →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map((stat, index) => {
          const Icon = stat.icon;
          const colorClasses = {
            blue: 'bg-blue-400/10 text-blue-200',
            green: 'bg-emerald-400/10 text-emerald-200',
            purple: 'bg-indigo-400/10 text-indigo-200',
            orange: 'bg-amber-400/10 text-amber-200'
          };

          return (
            <div key={index} className="rounded-lg border border-white/10 bg-slate-900/70 p-6 shadow-lg shadow-black/30">
              <div className="flex items-center">
                <div className={`p-2 rounded-lg ${colorClasses[stat.color as keyof typeof colorClasses]}`}>
                  <Icon className="h-5 w-5" />
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-slate-200/80">{stat.label}</p>
                  <p className="text-2xl font-semibold text-white">{stat.value}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid lg:grid-cols-2 gap-8">
        {/* Recent Candidates */}
        <div>
          <div className="rounded-lg border border-white/10 bg-slate-900/70 shadow-lg shadow-black/30">
            <div className="p-6 border-b border-white/10 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Top Candidates</h2>
              <button className="text-sm text-emerald-200 hover:text-emerald-100">View All</button>
            </div>
            <div className="p-6">
              <div className="space-y-4">
                {recentCandidates.map((candidate, index) => (
                  <div key={index} className="flex items-center space-x-4 p-4 bg-white/5 rounded-lg hover:bg-white/10 transition-colors">
                    <img
                      src={candidate.avatar}
                      alt={candidate.name}
                      className="h-12 w-12 rounded-full object-cover"
                    />
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <h3 className="font-medium text-white">{candidate.name}</h3>
                        <span className={`px-2 py-1 text-xs rounded-full font-medium ${getMatchScoreColor(candidate.matchScore)}`}>
                          {candidate.matchScore}% match
                        </span>
                      </div>
                      <p className="text-sm text-slate-200/80 mb-2">{candidate.role}</p>
                      <div className="flex items-center justify-between">
                        <div className="flex flex-wrap gap-1">
                          {candidate.skills.slice(0, 3).map((skill, skillIndex) => (
                            <span key={skillIndex} className="px-2 py-1 text-xs bg-white/5 rounded text-slate-200/80">
                              {skill}
                            </span>
                          ))}
                        </div>
                        <span className={`px-2 py-1 text-xs rounded-full ${getStatusColor(candidate.status)}`}>
                          {candidate.status}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Active Jobs */}
        <div>
          <div className="rounded-lg border border-white/10 bg-slate-900/70 shadow-lg shadow-black/30">
            <div className="p-6 border-b border-white/10 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Active Job Postings</h2>
              <button className="text-sm text-emerald-200 hover:text-emerald-100">+ New Job</button>
            </div>
            <div className="p-6">
              <div className="space-y-4">
                {activeJobs.map((job, index) => (
                  <div key={index} className="p-4 bg-white/5 rounded-lg">
                    <div className="flex items-start justify-between mb-2">
                      <h3 className="font-medium text-white">{job.title}</h3>
                      <span className={`px-2 py-1 text-xs rounded-full ${
                        job.status === 'Active'
                          ? 'bg-emerald-400/10 text-emerald-200'
                          : 'bg-white/5 text-slate-200'
                      }`}>
                        {job.status}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm text-slate-200/80">
                      <span>{job.applications} applications</span>
                      <span>Posted {job.posted}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="mt-8">
        <h2 className="text-lg font-semibold text-white mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Link
            to="/recruiter/profile"
            className="flex items-center p-4 rounded-lg border border-white/10 bg-slate-900/60 hover:border-emerald-300/60 transition"
          >
            <Briefcase className="h-8 w-8 text-emerald-200 mr-3" />
            <div>
              <h3 className="font-medium text-white">Company Profile</h3>
              <p className="text-sm text-slate-200/80">Update company info</p>
            </div>
          </Link>

          <button className="flex items-center p-4 rounded-lg border border-white/10 bg-slate-900/60 hover:border-emerald-300/60 transition">
            <Search className="h-8 w-8 text-blue-200 mr-3" />
            <div>
              <h3 className="font-medium text-white">Find Candidates</h3>
              <p className="text-sm text-slate-200/80">Search talent pool</p>
            </div>
          </button>

          <button className="flex items-center p-4 rounded-lg border border-white/10 bg-slate-900/60 hover:border-emerald-300/60 transition">
            <UserPlus className="h-8 w-8 text-indigo-200 mr-3" />
            <div>
              <h3 className="font-medium text-white">Post New Job</h3>
              <p className="text-sm text-slate-200/80">Create job posting</p>
            </div>
          </button>

          <button className="flex items-center p-4 rounded-lg border border-white/10 bg-slate-900/60 hover:border-emerald-300/60 transition">
            <TrendingUp className="h-8 w-8 text-amber-200 mr-3" />
            <div>
              <h3 className="font-medium text-white">Analytics</h3>
              <p className="text-sm text-slate-200/80">View hiring insights</p>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}

export default RecruiterDashboard;
