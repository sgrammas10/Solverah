import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  User, 
  FileText, 
  BarChart3, 
  Brain, 
  Briefcase, 
  TrendingUp,
  Calendar,
  MessageCircle,
  Star
} from 'lucide-react';

function JobSeekerDashboard() {
  const { user } = useAuth();

  const stats = [
    { label: 'Profile Completion', value: '75%', icon: User, color: 'blue' },
    { label: 'Job Matches', value: '12', icon: Briefcase, color: 'green' },
    { label: 'Profile Views', value: '48', icon: TrendingUp, color: 'purple' },
    { label: 'Applications', value: '8', icon: FileText, color: 'orange' }
  ];

  const recentActivity = [
    { type: 'match', text: 'New job match: Senior Developer at TechCorp', time: '2 hours ago', icon: Briefcase },
    { type: 'view', text: 'Your profile was viewed by RecruiterPro', time: '4 hours ago', icon: User },
    { type: 'assessment', text: 'Complete your Leadership Assessment', time: '1 day ago', icon: Brain },
    { type: 'application', text: 'Application status updated for Marketing Manager', time: '2 days ago', icon: FileText }
  ];

  const recommendations = [
    {
      title: 'Complete Psychometric Assessment',
      description: 'Boost your profile visibility by completing our leadership assessment',
      action: 'Take Assessment',
      priority: 'high'
    },
    {
      title: 'Update Performance Reviews',
      description: 'Add your latest performance review to increase match accuracy',
      action: 'Add Review',
      priority: 'medium'
    },
    {
      title: 'Optimize Your Skills',
      description: 'Add 3 more skills to improve your job matching score',
      action: 'Update Skills',
      priority: 'low'
    }
  ];

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
        {stats.map((stat, index) => {
          const Icon = stat.icon;
          const colorClasses = {
            blue: 'bg-blue-100 text-blue-600',
            green: 'bg-green-100 text-green-600',
            purple: 'bg-purple-100 text-purple-600',
            orange: 'bg-orange-100 text-orange-600'
          };

          return (
            <div key={index} className="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
              <div className="flex items-center">
                <div className={`p-2 rounded-lg ${colorClasses[stat.color as keyof typeof colorClasses]}`}>
                  <Icon className="h-5 w-5" />
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">{stat.label}</p>
                  <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
                </div>
              </div>
            </div>
          );
        })}
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
                {recentActivity.map((activity, index) => {
                  const Icon = activity.icon;
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
            <div className="p-6">
              <div className="space-y-4">
                {recommendations.map((rec, index) => (
                  <div key={index} className="p-4 bg-gray-50 rounded-lg">
                    <div className="flex items-start justify-between mb-2">
                      <h3 className="font-medium text-gray-900 text-sm">{rec.title}</h3>
                      <span className={`px-2 py-1 text-xs rounded-full ${
                        rec.priority === 'high' 
                          ? 'bg-red-100 text-red-600' 
                          : rec.priority === 'medium'
                          ? 'bg-yellow-100 text-yellow-600'
                          : 'bg-gray-100 text-gray-600'
                      }`}>
                        {rec.priority}
                      </span>
                    </div>
                    <p className="text-xs text-gray-600 mb-3">{rec.description}</p>
                    <button className="text-xs text-blue-600 hover:text-blue-500 font-medium">
                      {rec.action} →
                    </button>
                  </div>
                ))}
              </div>
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

          <button className="flex items-center p-4 bg-white rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
            <Brain className="h-8 w-8 text-purple-600 mr-3" />
            <div>
              <h3 className="font-medium text-gray-900">Take Assessment</h3>
              <p className="text-sm text-gray-600">Complete psychometric test</p>
            </div>
          </button>

          <button className="flex items-center p-4 bg-white rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
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