/*import React from 'react';*/
import { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
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
    if (!href) { navigate('/job-seeker/profile'); return; }
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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">
          Welcome back, {user?.name}!
        </h1>
        <p className="text-gray-600 mt-2">
          Here's your job search overview and recommendations.
        </p>
      </div>

      {/* Profile Completion Alert */}
      {!user?.profileComplete && (
        <div className="mb-8 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <User className="h-5 w-5 text-yellow-600" />
            </div>
            <div className="ml-3 flex-1">
              <p className="text-sm text-yellow-700">
                Complete your profile to get better job matches and increase visibility.
              </p>
            </div>
            <div className="ml-3">
              <Link
                to="/job-seeker/profile"  
                className="text-sm font-medium text-yellow-600 hover:text-yellow-500"
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
          <div className="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
            <div className="flex items-center">
              <div className="p-2 rounded-lg bg-blue-100 text-blue-600">
                <User className="h-5 w-5" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Profile Completion</p>
                <p className="text-2xl font-bold text-gray-900">{dashboardData.profileCompletion}</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
            <div className="flex items-center">
              <div className="p-2 rounded-lg bg-green-100 text-green-600">
                <Briefcase className="h-5 w-5" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Job Matches</p>
                <p className="text-2xl font-bold text-gray-900">{dashboardData.jobMatches}</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
            <div className="flex items-center">
              <div className="p-2 rounded-lg bg-orange-100 text-orange-600">
                <FileText className="h-5 w-5" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Applications</p>
                <p className="text-2xl font-bold text-gray-900">{dashboardData.applications}</p>
              </div>
            </div>
          </div>
        </>
        )}
      </div>

      <div className="grid lg:grid-cols-3 gap-8">
        {/* Recent Activity */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200">
            <div className="p-6 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Recent Activity</h2>
            </div>
            <div className="p-6">
              <div className="space-y-4">
                {dashboardData?.recentActivity?.map((activity: any, index: number) => {
                  const Icon = iconMap[activity.icon] || User;
                  return (
                    <div key={index} className="flex items-start space-x-3">
                      <div className="flex-shrink-0">
                        <div className="p-2 bg-gray-100 rounded-lg">
                          <Icon className="h-4 w-4 text-gray-600" />
                        </div>
                      </div>
                      <div className="flex-1">
                        <p className="text-sm text-gray-900">{activity.text}</p>
                        <p className="text-xs text-gray-500 mt-1">{activity.time}</p>
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
          <div className="bg-white rounded-lg shadow-sm border border-gray-200">
            <div className="p-6 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Recommendations</h2>
            </div>
            <div className="space-y-4">
                {dashboardData?.recommendations?.map((rec: any, index: number) => (
                  <button
                    key={index}
                    onClick={() => goToProfileTab(rec.href)}
                    className="flex justify-between items-center w-full text-left p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition border border-gray-200 shadow-sm"
                  >
                    <div>
                      <h3 className="font-semibold text-gray-900 text-sm">{rec.title}</h3>
                      {rec.description && (
                        <p className="text-xs text-gray-600 mt-1">{rec.description}</p>
                      )}
                      <p className="text-xs text-blue-600 hover:text-blue-500 font-medium mt-2">
                        {rec.action || 'Open'} →
                      </p>
                    </div>
                    <span
                      className={`px-2 py-1 text-xs rounded-full font-medium ${
                        rec.priority === 'urgent'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-green-100 text-green-700'
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
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            to="/job-seeker/profile"
            className="flex items-center p-4 bg-white rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow"
          >
            <User className="h-8 w-8 text-blue-600 mr-3" />
            <div>
              <h3 className="font-medium text-gray-900">Edit Profile</h3>
              <p className="text-sm text-gray-600">Update your information</p>
            </div>
          </Link>

          <button
            onClick={handleTakeAssessment}
            className="flex items-center p-4 bg-white rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow"
          >
            <Brain className="h-8 w-8 text-purple-600 mr-3" />
            <div>
              <h3 className="font-medium text-gray-900">Take Assessment</h3>
              <p className="text-sm text-gray-600">Complete psychometric test</p>
            </div>
          </button>

          <button
            onClick={handleBrowseJobs}
            className="flex items-center p-4 bg-white rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow"
          >
            <Briefcase className="h-8 w-8 text-green-600 mr-3" />
            <div>
              <h3 className="font-medium text-gray-900">Browse Jobs</h3>
              <p className="text-sm text-gray-600">Find matching opportunities</p>
            </div>
          </button>

        </div>
      </div>
    </div>
  );
}

export default JobSeekerDashboard;