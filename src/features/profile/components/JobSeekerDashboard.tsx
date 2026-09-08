import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth';
import { Link, useNavigate } from 'react-router-dom';
import { User, FileText, Brain, Briefcase, TrendingUp } from 'lucide-react';
import { IntakePromptModal } from '../../intake';
import { WorkPulseBanner, WorkPulseUnlock } from '../../assessments';

const iconMap: Record<string, any> = { User, FileText, Brain, Briefcase, TrendingUp };

/** Query keys for the dashboard document. `all` is the invalidation handle. */
export const dashboardKeys = {
  all: ['dashboard'] as const,
  summary: () => ['dashboard', 'summary'] as const,
};

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

  const [jobsPopupOpen, setJobsPopupOpen] = useState(false);
  const [intakeModalOpen, setIntakeModalOpen] = useState(false);
  const [wplBannerDismissed, setWplBannerDismissed] = useState(false);
  const { user, fetchWithAuth } = useAuth();

  // A failed fetch (after queryClient.ts's bounded retries) leaves `data`
  // undefined and this page renders without the stats row, exactly as the
  // hand-rolled catch-and-log did.
  const { data: dashboardData } = useQuery({
    queryKey: dashboardKeys.summary(),
    queryFn: () => fetchWithAuth<any>('/me/dashboard'),
  });

  useEffect(() => {
    if (!dashboardData) return;
    const completionPct = parseInt(dashboardData.profileCompletion ?? '0', 10);
    if (completionPct < 50) {
      setIntakeModalOpen(true);
    }
  }, [dashboardData]);

  const cardCls =
    'border border-cream-muted rounded-xl bg-white p-6';

  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <IntakePromptModal
        open={intakeModalOpen}
        hasIntakeSubmission={dashboardData?.hasIntakeSubmission ?? false}
        onClose={() => setIntakeModalOpen(false)}
        onSuccess={() => { setIntakeModalOpen(false); navigate('/job-seeker/profile'); }}
      />
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

        {/* Work Pulse — completion card or prompt banner.
            Gated on wp_v2_completed (the CURRENT 24-item instrument), not wpl_completed:
            the original 12-question quiz was replaced 2026-08-19 and its sittings don't
            feed the matching model, so previous completers are re-prompted (retake copy).
            Their old narrative stays reachable from the Work Pulse page itself. */}
        {user?.wp_v2_completed ? (
          <div className="mb-6">
            <WorkPulseUnlock />
          </div>
        ) : (
          user && !wplBannerDismissed && (
            <div className="mb-6">
              <WorkPulseBanner
                onDismiss={() => setWplBannerDismissed(true)}
                retake={Boolean(user.wpl_completed)}
              />
            </div>
          )
        )}

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
              {/* The empty branch is not decoration. This is the first screen after
                  sign-up and both arrays are empty for every new account, so without
                  it the card renders as a heading over nothing and reads as broken
                  rather than new. Found by the real-stack E2E walkthrough. */}
              {dashboardData?.recentActivity?.length ? (
                <div className="space-y-4">
                  {dashboardData.recentActivity.map((activity: any, index: number) => {
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
              ) : (
                <div className="text-center py-10">
                  <TrendingUp className="h-8 w-8 text-ink-tertiary mx-auto mb-3" />
                  <p className="text-sm text-ink-secondary">Nothing here yet.</p>
                  <p className="text-xs text-ink-tertiary mt-1">
                    Your activity shows up here as you complete Work Pulse and fill in your profile.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Recommendations */}
          <div className={cardCls}>
            <h2 className="font-display text-lg font-semibold text-ink-primary mb-5">Recommendations</h2>
            {!dashboardData?.recommendations?.length && (
              <div className="text-center py-10">
                <Brain className="h-8 w-8 text-ink-tertiary mx-auto mb-3" />
                <p className="text-sm text-ink-secondary">No recommendations yet.</p>
                <p className="text-xs text-ink-tertiary mt-1">
                  Once you finish Work Pulse we&rsquo;ll suggest what to do next.
                </p>
              </div>
            )}
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
              onClick={() => navigate('/intelligence')}
              className="flex items-center gap-4 p-5 rounded-xl border border-cream-muted bg-white hover:border-forest-pale transition-colors text-left"
            >
              <div className="p-2 bg-forest-pale rounded-lg shrink-0">
                <Brain className="h-4 w-4 text-forest-mid" />
              </div>
              <div>
                {/* One name for one instrument. This card used to read "Take
                    Assessment / Complete psychometric test" while the banner
                    directly above it called the same 24 questions "Work Pulse",
                    so the screen appeared to offer two separate things. It
                    navigates to /intelligence, which is the hub Work Pulse is
                    started from, hence "Your Solverah profile" rather than a
                    second "Start Work Pulse" button. */}
                <h3 className="font-semibold text-ink-primary">Your Solverah profile</h3>
                <p className="text-sm text-ink-secondary">Work Pulse, FocusType and ManagerMatch</p>
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
