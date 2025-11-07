import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { 
  Briefcase,
  MessageCircle,
  Bell,
  Search,
  Filter,
  Building,
  TrendingUp
} from 'lucide-react';
// import the CSV as a raw string using Vite's ?raw
// @ts-ignore
import jobCsv from '../../zensearchData/job_postings.csv?raw';

// simple CSV parser that handles quoted fields and escaped quotes
function parseCSV(raw: string) {
  const rows: string[][] = [];
  let cur = '';
  let row: string[] = [];
  let inQuotes = false;
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (ch === '"') {
      if (inQuotes && raw[i + 1] === '"') {
        cur += '"';
        i++; // skip escaped quote
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === ',' && !inQuotes) {
      row.push(cur);
      cur = '';
    } else if ((ch === '\n' || ch === '\r') && !inQuotes) {
      // handle CRLF or LF
      if (ch === '\r' && raw[i + 1] === '\n') {
        // skip, let the \n handle pushing
      }
      if (cur !== '' || row.length > 0) {
        row.push(cur);
        rows.push(row);
        row = [];
        cur = '';
      }
    } else {
      cur += ch;
    }
  }
  if (cur !== '' || row.length > 0) {
    row.push(cur);
    rows.push(row);
  }
  return rows;
}

function truncate(text: string, n = 220) {
  if (!text) return '';
  return text.length > n ? text.slice(0, n) + '...' : text;
}

function formatDateUS(dateStr?: string) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return '';
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const yyyy = d.getFullYear();
  return `${mm}/${dd}/${yyyy}`;
}

function JobRecommendations() {
  const [jobs, setJobs] = React.useState<any[]>([]);

  useEffect(() => {
    try {
      const rows = parseCSV(String(jobCsv || ''));
      if (!rows || rows.length < 2) return;
      const headers = rows[0].map((h) => h.replace(/^"|"$/g, '').trim());
      const data = rows.slice(1).map((r) => {
        const obj: any = {};
        headers.forEach((h, i) => (obj[h] = (r[i] ?? '').replace(/^"|"$/g, '').trim()));
        return obj;
      });
      setJobs(data.slice(0, 25));
    } catch (err) {
      // fallback: empty
      setJobs([]);
    }
  }, []);

  if (!jobs.length) {
    return (
      <div className="text-center py-12">
        <Briefcase className="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">Job recommendations coming soon</h3>
        <p className="text-gray-600">Complete your profile to start receiving personalized job recommendations.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 max-h-[60vh] overflow-y-auto">
      {jobs.map((job, idx) => (
        <div key={job.ID || idx} className="border border-gray-200 rounded-lg p-4 hover:shadow-sm">
          <div className="flex items-start justify-between">
            <div>
              <a
                className="text-md font-semibold text-blue-600 hover:underline"
                href={job.Link || '#'}
                target="_blank"
                rel="noreferrer"
              >
                {job.Title || 'Untitled Role'}
              </a>
              <div className="text-sm text-gray-600 mt-1">
                {job.Company ? <span>{job.Company}</span> : null}
                {job.Location ? <span className="mx-2">•</span> : null}
                {job.Location ? <span>{job.Location}</span> : null}
                {job.EmploymentType ? <span className="mx-2">•</span> : null}
                {job.EmploymentType ? <span>{job.EmploymentType}</span> : null}
              </div>
            </div>
            <div className="text-right text-sm text-gray-500">
              {job.DatePosted ? <div>Posted {formatDateUS(job.DatePosted)}</div> : null}
              {job.Remote ? <div className="mt-1">{job.Remote === 'Yes' ? 'Remote' : 'Onsite'}</div> : null}
            </div>
          </div>

          {job.RoleDescription ? (
            <p className="text-sm text-gray-700 mt-3 whitespace-pre-line">{truncate(job.RoleDescription, 300)}</p>
          ) : null}

          <div className="mt-3 flex items-center justify-between">
            <div className="text-sm text-gray-500">Experience: {job.Experience || 'N/A'} Years</div>
            <div className="flex items-center gap-2">
              <a
                href={job.Link || '#'}
                target="_blank"
                rel="noreferrer"
                className="px-3 py-1 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                View
              </a>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function Feed() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('jobs');

  const tabs = [
    { id: 'jobs', label: 'Job Feed', icon: Briefcase },
    { id: 'messages', label: 'Messages', icon: MessageCircle },
    { id: 'notifications', label: 'Notifications', icon: Bell }
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">
          Welcome to your feed, {user?.name?.split(' ')[0] || user?.name}!
        </h1>
        <p className="text-gray-600 mt-2">
          Stay updated with the latest opportunities and connections.
        </p>
      </div>

      {/* Search and Filter Bar */}
      <div className="mb-6 flex flex-col sm:flex-row gap-4">
        <div className="flex-1 relative">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-5 w-5 text-gray-400" />
          </div>
          <input
            type="text"
            placeholder="Search jobs, companies, or people..."
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <button className="flex items-center px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50">
          <Filter className="h-4 w-4 mr-2" />
          Filters
        </button>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-gray-200 mb-8">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon className="h-5 w-5 mr-2" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Content based on active tab */}
      {activeTab === 'jobs' && (
        <div className="grid lg:grid-cols-3 gap-8">
          {/* Main Feed */}
          <div className="lg:col-span-2 space-y-6">
            {/* Job Recommendations */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Recommended for You</h2>
              <JobRecommendations />
            </div>

            {/* Recent Activity */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Activity</h2>
              <div className="text-center py-8">
                <TrendingUp className="h-8 w-8 text-gray-400 mx-auto mb-3" />
                <p className="text-gray-600">No recent activity to show</p>
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Quick Stats */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Your Stats</h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-600">Profile Views</span>
                  <span className="font-medium">--</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Job Matches</span>
                  <span className="font-medium">--</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Applications</span>
                  <span className="font-medium">--</span>
                </div>
              </div>
            </div>

            {/* Trending Companies */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Trending Companies</h3>
              <div className="text-center py-6">
                <Building className="h-8 w-8 text-gray-400 mx-auto mb-3" />
                <p className="text-gray-600 text-sm">Company trends coming soon</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'messages' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
          <div className="text-center">
            <MessageCircle className="h-16 w-16 text-gray-400 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Messages</h2>
            <p className="text-gray-600 mb-6">
              Connect with recruiters and other professionals. Your conversations will appear here.
            </p>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              Start a Conversation
            </button>
          </div>
        </div>
      )}

      {activeTab === 'notifications' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
          <div className="text-center">
            <Bell className="h-16 w-16 text-gray-400 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Notifications</h2>
            <p className="text-gray-600 mb-6">
              Stay updated with job matches, profile views, and important updates.
            </p>
            <div className="text-sm text-gray-500">
              No notifications yet
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Feed;