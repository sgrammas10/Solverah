/*import React from 'react';*/
import { useEffect, useState } from 'react';
import { useAuth } from '../contexts/useAuth';
import { Link, useNavigate } from 'react-router-dom';
import {
  User,
  FileText,
  Brain,
  Briefcase,
  TrendingUp,
} from 'lucide-react';

const iconMap: Record<string, any> = { User, FileText, Brain, Briefcase, TrendingUp };

function JobSeekerDashboard() {
  const navigate = useNavigate();
  const goToProfileTab = (href?: string) => {
    if (!href) {
      navigate('/job-seeker/profile');
      return;
    }
    const hash = href.includes('#') ? href.split('#')[1] : undefined;
    navigate(hash
      ? { pathname: '/job-seeker/profile', search: `?tab=${encodeURIComponent(hash)}` }
      : '/job-seeker/profile'
    );
  };

  const [dashboardData, setDashboardData] = useState<any>(null);
  const { user, fetchWithAuth } = useAuth();

  useEffect(() => {
    const loadData = async () => {
      try {
        const data = await fetchWithAuth('/dashboard-data');
        console.log('Dashboard data:', data);
        setDashboardData(data);
      } catch (err) {
        console.error('Error loading dashboard data:', err);
      }
    };
    loadData();
  }, [fetchWithAuth]);

  const handleTakeAssessment = () => {
    navigate('/job-seeker/profile#assessments');
  };

  const handleBrowseJobs = () => {
    navigate('/job-seeker/feed');
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-slate-100">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-semibold text-white">
          Welcome back, {user?.name}!
        </h1>
        <p className="text-slate-200/80 mt-2">
          Here's your job search overview and recommendations.
        </p>
      </div>

      {/* Profile Completion Alert */}
      {!user?.profileComplete && (
        <div className="mb-8 rounded-lg border border-amber-400/30 bg-amber-500/10 p-4">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <User className="h-5 w-5 text-amber-200" />
            </div>
            <div className="ml-3 flex-1">
              <p className="text-sm text-amber-100">
                Complete your profile to get better job matches and increase visibility.
              </p>
            </div>
            <div className="ml-3">
              <Link
                to="/job-seeker/profile"
                className="text-sm font-semibold text-amber-200 hover:text-amber-100"
              >
                Complete Profile →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {dashboardData && (
          <>
            <div className="rounded-lg border border-white/10 bg-slate-900/70 p-6 shadow-lg shadow-black/30">
              <div className="flex items-center">
                <div className="p-2 rounded-lg bg-emerald-400/10 text-emerald-200">
                  <User className="h-5 w-5" />
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-slate-200/80">Profile Completion</p>
                  <p className="text-2xl font-semibold text-white">{dashboardData.profileCompletion}</p>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-white/10 bg-slate-900/70 p-6 shadow-lg shadow-black/30">
              <div className="flex items-center">
                <div className="p-2 rounded-lg bg-blue-400/10 text-blue-200">
                  <Briefcase className="h-5 w-5" />
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-slate-200/80">Job Matches</p>
                  <p className="text-2xl font-semibold text-white">{dashboardData.jobMatches}</p>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-white/10 bg-slate-900/70 p-6 shadow-lg shadow-black/30">
              <div className="flex items-center">
                <div className="p-2 rounded-lg bg-indigo-400/10 text-indigo-200">
                  <FileText className="h-5 w-5" />
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-slate-200/80">Applications</p>
                  <p className="text-2xl font-semibold text-white">{dashboardData.applications}</p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="grid lg:grid-cols-3 gap-8">
        {/* Recent Activity */}
        <div className="lg:col-span-2">
          <div className="rounded-lg border border-white/10 bg-slate-900/70 shadow-lg shadow-black/30">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-lg font-semibold text-white">Recent Activity</h2>
            </div>
            <div className="p-6">
              <div className="space-y-4">
                {dashboardData?.recentActivity?.map((activity: any, index: number) => {
                  const Icon = iconMap[activity.icon] || User;
                  return (
                    <div key={index} className="flex items-start space-x-3">
                      <div className="flex-shrink-0">
                        <div className="p-2 bg-white/5 rounded-lg">
                          <Icon className="h-4 w-4 text-slate-300" />
                        </div>
                      </div>
                      <div className="flex-1">
                        <p className="text-sm text-slate-100">{activity.text}</p>
                        <p className="text-xs text-slate-400 mt-1">{activity.time}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Recommendations */}
        <div>
          <div className="rounded-lg border border-white/10 bg-slate-900/70 shadow-lg shadow-black/30">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-lg font-semibold text-white">Recommendations</h2>
            </div>
            <div className="space-y-4 p-6">
              {dashboardData?.recommendations?.map((rec: any, index: number) => (
                <button
                  key={index}
                  onClick={() => goToProfileTab(rec.href)}
                  className="flex justify-between items-center w-full text-left p-4 rounded-lg bg-white/5 border border-white/10 hover:border-emerald-300/50 transition shadow-sm"
                >
                  <div>
                    <h3 className="font-semibold text-white text-sm">{rec.title}</h3>
                    {rec.description && (
                      <p className="text-xs text-slate-200/80 mt-1">{rec.description}</p>
                    )}
                    <p className="text-xs text-emerald-200 hover:text-emerald-100 font-medium mt-2">
                      {rec.action || 'Open'} →
                    </p>
                  </div>
                  <span
                    className={`px-2 py-1 text-xs rounded-full font-medium ${
                      rec.priority === 'urgent'
                        ? 'bg-red-500/20 text-red-100'
                        : 'bg-emerald-500/20 text-emerald-100'
                    }`}
                  >
                    {rec.priority === 'urgent' ? 'Action Needed' : 'Optional'}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="mt-8">
        <h2 className="text-lg font-semibold text-white mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            to="/job-seeker/profile"
            className="flex items-center p-4 rounded-lg border border-white/10 bg-slate-900/60 hover:border-emerald-300/60 transition"
          >
            <User className="h-8 w-8 text-emerald-200 mr-3" />
            <div>
              <h3 className="font-medium text-white">Edit Profile</h3>
              <p className="text-sm text-slate-200/80">Update your information</p>
            </div>
          </Link>

          <button
            onClick={handleTakeAssessment}
            className="flex items-center p-4 rounded-lg border border-white/10 bg-slate-900/60 hover:border-emerald-300/60 transition"
          >
            <Brain className="h-8 w-8 text-indigo-200 mr-3" />
            <div>
              <h3 className="font-medium text-white">Take Assessment</h3>
              <p className="text-sm text-slate-200/80">Complete psychometric test</p>
            </div>
          </button>

          <button
            onClick={handleBrowseJobs}
            className="flex items-center p-4 rounded-lg border border-white/10 bg-slate-900/60 hover:border-emerald-300/60 transition"
          >
            <Briefcase className="h-8 w-8 text-blue-200 mr-3" />
            <div>
              <h3 className="font-medium text-white">Browse Jobs</h3>
              <p className="text-sm text-slate-200/80">Find matching opportunities</p>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}

export default JobSeekerDashboard;
