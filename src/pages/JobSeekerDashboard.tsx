import { useEffect, useState } from 'react';
import { useAuth } from '../contexts/useAuth';
import { Link, useNavigate } from 'react-router-dom';
import { User, FileText, Brain, Briefcase, TrendingUp } from 'lucide-react';

const iconMap: Record<string, any> = { User, FileText, Brain, Briefcase, TrendingUp };

function JobSeekerDashboard() {
  const navigate = useNavigate();

  const goToProfileTab = (href?: string) => {
    if (!href) { navigate('/job-seeker/profile'); return; }
    const hash = href.includes('#') ? href.split('#')[1] : undefined;
    navigate(
      hash
        ? { pathname: '/job-seeker/profile', search: `?tab=${encodeURIComponent(hash)}` }
        : '/job-seeker/profile',
    );
  };

  const [dashboardData, setDashboardData] = useState<any>(null);
  const [jobsPopupOpen, setJobsPopupOpen] = useState(false);
  const { user, fetchWithAuth } = useAuth();

  useEffect(() => {
    const loadData = async () => {
      try {
        const data = await fetchWithAuth('/dashboard-data');
        setDashboardData(data);
      } catch (err) {
        console.error('Error loading dashboard data:', err);
      }
    };
    loadData();
  }, [fetchWithAuth]);

  const cardCls =
    'border border-cream-muted rounded-xl bg-white p-6';

  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">

        {/* Page header */}
        <div className="mb-8">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
            Dashboard
          </p>
          <h1 className="font-display text-3xl font-bold text-ink-primary">
            Welcome back, {user?.name}
          </h1>
          <p className="text-ink-secondary mt-2 text-base">
            Here's your job search overview and recommendations.
          </p>
        </div>

        {/* Profile completion alert */}
        {!user?.profileComplete && (
          <div className="mb-8 rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-center gap-4">
            <User className="h-5 w-5 text-amber-600 shrink-0" />
            <p className="text-sm text-amber-800 flex-1">
              Complete your profile to get better job matches and increase visibility.
            </p>
            <Link
              to="/job-seeker/profile"
              className="text-sm font-semibold text-amber-700 hover:text-amber-900 transition-colors shrink-0"
            >
              Complete Profile →
            </Link>
          </div>
        )}

        {/* Stats */}
        {dashboardData && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            {[
              { label: 'Profile Completion', value: dashboardData.profileCompletion, icon: User, color: 'text-forest-mid bg-forest-pale' },
              { label: 'Job Matches', value: dashboardData.jobMatches, icon: Briefcase, color: 'text-forest-mid bg-forest-pale' },
              { label: 'Applications', value: dashboardData.applications, icon: FileText, color: 'text-ink-secondary bg-cream-subtle' },
            ].map(({ label, value, icon: Icon, color }) => (
              <div key={label} className={cardCls}>
                <div className="flex items-center gap-4">
                  <div className={`p-2.5 rounded-lg ${color}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-sm text-ink-secondary">{label}</p>
                    <p className="text-2xl font-semibold text-ink-primary">{value}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Recent Activity */}
          <div className="lg:col-span-2">
            <div className={cardCls}>
              <h2 className="font-display text-lg font-semibold text-ink-primary mb-5">Recent Activity</h2>
              <div className="space-y-4">
                {dashboardData?.recentActivity?.map((activity: any, index: number) => {
                  const Icon = iconMap[activity.icon] || User;
                  return (
                    <div key={index} className="flex items-start gap-3">
                      <div className="p-2 bg-cream-subtle rounded-lg shrink-0">
                        <Icon className="h-4 w-4 text-ink-secondary" />
                      </div>
                      <div>
                        <p className="text-sm text-ink-primary">{activity.text}</p>
                        <p className="text-xs text-ink-tertiary mt-0.5">{activity.time}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Recommendations */}
          <div className={cardCls}>
            <h2 className="font-display text-lg font-semibold text-ink-primary mb-5">Recommendations</h2>
            <div className="space-y-3">
              {dashboardData?.recommendations?.map((rec: any, index: number) => (
                <button
                  key={index}
                  onClick={() => goToProfileTab(rec.href)}
                  className="w-full text-left p-4 rounded-lg border border-cream-muted bg-cream-base hover:border-forest-pale transition-colors"
                >
                  <h3 className="text-sm font-semibold text-ink-primary">{rec.title}</h3>
                  {rec.description && (
                    <p className="text-xs text-ink-secondary mt-1">{rec.description}</p>
                  )}
                  <p className="text-xs font-semibold text-forest-mid mt-2">
                    {rec.action || 'Open'} →
                  </p>
                  <span
                    className={`mt-2 inline-block px-2 py-0.5 text-xs rounded font-medium ${
                      rec.priority === 'urgent'
                        ? 'bg-red-50 text-red-700 border border-red-200'
                        : 'bg-forest-pale text-forest-dark'
                    }`}
                  >
                    {rec.priority === 'urgent' ? 'Action Needed' : 'Optional'}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="mt-8">
          <h2 className="font-display text-lg font-semibold text-ink-primary mb-4">Quick Actions</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Link
              to="/job-seeker/profile"
              className="flex items-center gap-4 p-5 rounded-xl border border-cream-muted bg-white hover:border-forest-pale transition-colors"
            >
              <div className="p-2 bg-forest-pale rounded-lg shrink-0">
                <User className="h-4 w-4 text-forest-mid" />
              </div>
              <div>
                <h3 className="font-semibold text-ink-primary">Edit Profile</h3>
                <p className="text-sm text-ink-secondary">Update your information</p>
              </div>
            </Link>

            <button
              onClick={() => navigate('/job-seeker/profile#assessments')}
              className="flex items-center gap-4 p-5 rounded-xl border border-cream-muted bg-white hover:border-forest-pale transition-colors text-left"
            >
              <div className="p-2 bg-forest-pale rounded-lg shrink-0">
                <Brain className="h-4 w-4 text-forest-mid" />
              </div>
              <div>
                <h3 className="font-semibold text-ink-primary">Take Assessment</h3>
                <p className="text-sm text-ink-secondary">Complete psychometric test</p>
              </div>
            </button>

            <button
              onClick={() => setJobsPopupOpen(true)}
              className="flex items-center gap-4 p-5 rounded-xl border border-cream-muted bg-white hover:border-forest-pale transition-colors text-left"
            >
              <div className="p-2 bg-forest-pale rounded-lg shrink-0">
                <Briefcase className="h-4 w-4 text-forest-mid" />
              </div>
              <div>
                <h3 className="font-semibold text-ink-primary">Browse Jobs</h3>
                <p className="text-sm text-ink-secondary">Find matching opportunities</p>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Jobs coming-soon modal */}
      {jobsPopupOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-ink-primary/50 backdrop-blur-sm px-4 pt-24"
          role="dialog"
          aria-modal="true"
          aria-labelledby="jobs-popup-title"
        >
          <div className="w-full max-w-xl rounded-xl border border-cream-muted bg-cream-base p-8 shadow-2xl">
            <p id="jobs-popup-title" className="font-display text-xl font-semibold text-ink-primary">
              Feature coming soon
            </p>
            <p className="mt-2 text-sm text-ink-secondary leading-relaxed">
              Job browsing will be available after launch.
            </p>
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setJobsPopupOpen(false)}
                className="bg-forest-dark text-white text-sm font-semibold px-6 py-2.5 rounded hover:bg-forest-mid transition-colors"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default JobSeekerDashboard;
