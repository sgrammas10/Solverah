import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { 
  Building, 
  Mail, 
  Phone, 
  MapPin, 
  Users, 
  Globe,
  Upload,
  Plus,
  X,
  Briefcase,
  Target
} from 'lucide-react';

function RecruiterProfile() {
  const { user, updateProfile } = useAuth();
  const [activeTab, setActiveTab] = useState('company');
  const [isSaving, setIsSaving] = useState(false);

  const [formData, setFormData] = useState({
    // Company Info
    companyName: 'TechCorp Solutions',
    industry: 'Technology',
    companySize: '201-500',
    website: 'https://techcorp.com',
    location: 'San Francisco, CA',
    description: 'Leading technology company specializing in innovative software solutions for enterprise clients. We foster a culture of creativity, collaboration, and continuous learning.',
    
    // Contact Info
    firstName: 'Jane',
    lastName: 'Smith',
    title: 'Senior Talent Acquisition Manager',
    email: user?.email || '',
    phone: '+1 (555) 987-6543',
    
    // Hiring Preferences
    typicalRoles: ['Software Engineer', 'Product Manager', 'UX Designer', 'Data Scientist'],
    experienceLevels: ['Mid-level', 'Senior'],
    preferredSkills: ['React', 'Python', 'AWS', 'Agile', 'Machine Learning'],
    remotePolicy: 'Hybrid',
    
    // Active Job Postings
    activeJobs: [
      {
        id: 1,
        title: 'Senior Full Stack Developer',
        department: 'Engineering',
        type: 'Full-time',
        location: 'San Francisco, CA',
        remote: true,
        salary: '$120,000 - $150,000',
        status: 'Active',
        posted: '2024-01-15'
      },
      {
        id: 2,
        title: 'Product Manager',
        department: 'Product',
        type: 'Full-time',
        location: 'San Francisco, CA',
        remote: true,
        salary: '$130,000 - $160,000',
        status: 'Active',
        posted: '2024-01-10'
      }
    ]
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Update the user's name and profile completion status
    const fullName = `${formData.firstName} ${formData.lastName}`.trim();
    updateProfile({ 
      name: fullName,
      profileComplete: true 
    });
    
    setIsSaving(false);
  };

  const addRole = (role: string) => {
    if (role && !formData.typicalRoles.includes(role)) {
      setFormData({
        ...formData,
        typicalRoles: [...formData.typicalRoles, role]
      });
    }
  };

  const removeRole = (role: string) => {
    setFormData({
      ...formData,
      typicalRoles: formData.typicalRoles.filter(r => r !== role)
    });
  };

  const addSkill = (skill: string) => {
    if (skill && !formData.preferredSkills.includes(skill)) {
      setFormData({
        ...formData,
        preferredSkills: [...formData.preferredSkills, skill]
      });
    }
  };

  const removeSkill = (skill: string) => {
    setFormData({
      ...formData,
      preferredSkills: formData.preferredSkills.filter(s => s !== skill)
    });
  };

  const tabs = [
    { id: 'company', label: 'Company Info', icon: Building },
    { id: 'contact', label: 'Contact Info', icon: Mail },
    { id: 'preferences', label: 'Hiring Preferences', icon: Target },
    { id: 'jobs', label: 'Job Postings', icon: Briefcase }
  ];

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Recruiter Profile</h1>
        <p className="text-gray-600 mt-2">
          Complete your company profile to attract the best candidates and showcase your organization.
        </p>
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

      <form onSubmit={handleSubmit}>
        {/* Company Info Tab */}
        {activeTab === 'company' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Company Information</h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Company Name
                  </label>
                  <input
                    type="text"
                    value={formData.companyName}
                    onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Industry
                  </label>
                  <select
                    value={formData.industry}
                    onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="Technology">Technology</option>
                    <option value="Healthcare">Healthcare</option>
                    <option value="Finance">Finance</option>
                    <option value="Education">Education</option>
                    <option value="Manufacturing">Manufacturing</option>
                    <option value="Retail">Retail</option>
                    <option value="Other">Other</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Company Size
                  </label>
                  <select
                    value={formData.companySize}
                    onChange={(e) => setFormData({ ...formData, companySize: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="1-10">1-10 employees</option>
                    <option value="11-50">11-50 employees</option>
                    <option value="51-200">51-200 employees</option>
                    <option value="201-500">201-500 employees</option>
                    <option value="501-1000">501-1000 employees</option>
                    <option value="1000+">1000+ employees</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Website
                  </label>
                  <input
                    type="url"
                    value={formData.website}
                    onChange={(e) => setFormData({ ...formData, website: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Location
                  </label>
                  <input
                    type="text"
                    value={formData.location}
                    onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Company Description
                  </label>
                  <textarea
                    rows={4}
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Describe your company culture, values, and what makes you unique..."
                  />
                </div>
              </div>

              {/* Company Logo Upload */}
              <div className="mt-6 pt-6 border-t border-gray-200">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Company Logo
                </label>
                <div className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-gray-300 border-dashed rounded-md">
                  <div className="space-y-1 text-center">
                    <Upload className="mx-auto h-12 w-12 text-gray-400" />
                    <div className="flex text-sm text-gray-600">
                      <label htmlFor="logo-upload" className="relative cursor-pointer bg-white rounded-md font-medium text-blue-600 hover:text-blue-500">
                        <span>Upload company logo</span>
                        <input id="logo-upload" name="logo-upload" type="file" className="sr-only" accept="image/*" />
                      </label>
                      <p className="pl-1">or drag and drop</p>
                    </div>
                    <p className="text-xs text-gray-500">PNG, JPG, GIF up to 10MB</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Contact Info Tab */}
        {activeTab === 'contact' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Contact Information</h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    First Name
                  </label>
                  <input
                    type="text"
                    value={formData.firstName}
                    onChange={(e) => setFormData({ ...formData, firstName: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Last Name
                  </label>
                  <input
                    type="text"
                    value={formData.lastName}
                    onChange={(e) => setFormData({ ...formData, lastName: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Job Title
                  </label>
                  <input
                    type="text"
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Email
                  </label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Phone
                  </label>
                  <input
                    type="tel"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Hiring Preferences Tab */}
        {activeTab === 'preferences' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Hiring Preferences</h2>

              {/* Typical Roles */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Typical Roles You Hire For
                </label>
                <div className="flex flex-wrap gap-2 mb-3">
                  {formData.typicalRoles.map((role) => (
                    <span
                      key={role}
                      className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800"
                    >
                      {role}
                      <button
                        type="button"
                        onClick={() => removeRole(role)}
                        className="ml-2 text-blue-600 hover:text-blue-500"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex">
                  <input
                    type="text"
                    placeholder="Add a role (press Enter)"
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-l-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        const target = e.target as HTMLInputElement;
                        addRole(target.value);
                        target.value = '';
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="px-4 py-2 bg-blue-600 text-white rounded-r-md hover:bg-blue-700"
                    onClick={(e) => {
                      const input = (e.target as HTMLButtonElement).previousElementSibling as HTMLInputElement;
                      addRole(input.value);
                      input.value = '';
                    }}
                  >
                    Add
                  </button>
                </div>
              </div>

              {/* Experience Levels */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Preferred Experience Levels
                </label>
                <div className="space-y-2">
                  {['Entry-level', 'Mid-level', 'Senior', 'Executive'].map((level) => (
                    <label key={level} className="flex items-center">
                      <input
                        type="checkbox"
                        checked={formData.experienceLevels.includes(level)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setFormData({
                              ...formData,
                              experienceLevels: [...formData.experienceLevels, level]
                            });
                          } else {
                            setFormData({
                              ...formData,
                              experienceLevels: formData.experienceLevels.filter(l => l !== level)
                            });
                          }
                        }}
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      <span className="ml-2 text-sm text-gray-700">{level}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Remote Policy */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Remote Work Policy
                </label>
                <select
                  value={formData.remotePolicy}
                  onChange={(e) => setFormData({ ...formData, remotePolicy: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="On-site">On-site only</option>
                  <option value="Hybrid">Hybrid</option>
                  <option value="Remote">Fully remote</option>
                </select>
              </div>

              {/* Preferred Skills */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Preferred Skills & Technologies
                </label>
                <div className="flex flex-wrap gap-2 mb-3">
                  {formData.preferredSkills.map((skill) => (
                    <span
                      key={skill}
                      className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800"
                    >
                      {skill}
                      <button
                        type="button"
                        onClick={() => removeSkill(skill)}
                        className="ml-2 text-green-600 hover:text-green-500"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex">
                  <input
                    type="text"
                    placeholder="Add a skill (press Enter)"
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-l-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        const target = e.target as HTMLInputElement;
                        addSkill(target.value);
                        target.value = '';
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="px-4 py-2 bg-blue-600 text-white rounded-r-md hover:bg-blue-700"
                    onClick={(e) => {
                      const input = (e.target as HTMLButtonElement).previousElementSibling as HTMLInputElement;
                      addSkill(input.value);
                      input.value = '';
                    }}
                  >
                    Add
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Job Postings Tab */}
        {activeTab === 'jobs' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">Active Job Postings</h2>
                <button
                  type="button"
                  className="flex items-center px-3 py-2 text-sm font-medium text-blue-600 hover:text-blue-500"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Create New Job
                </button>
              </div>

              <div className="space-y-4">
                {formData.activeJobs.map((job) => (
                  <div key={job.id} className="p-4 border border-gray-200 rounded-lg">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="font-medium text-gray-900 mb-1">{job.title}</h3>
                        <div className="text-sm text-gray-600 space-y-1">
                          <div className="flex items-center">
                            <Building className="h-4 w-4 mr-2" />
                            {job.department}
                          </div>
                          <div className="flex items-center">
                            <MapPin className="h-4 w-4 mr-2" />
                            {job.location} {job.remote && '(Remote available)'}
                          </div>
                          <div className="flex items-center">
                            <Users className="h-4 w-4 mr-2" />
                            {job.type}
                          </div>
                          <div>
                            <strong>Salary:</strong> {job.salary}
                          </div>
                          <div>
                            <strong>Posted:</strong> {job.posted}
                          </div>
                        </div>
                      </div>
                      <div className="ml-4">
                        <span className={`px-2 py-1 text-xs rounded-full ${
                          job.status === 'Active' 
                            ? 'bg-green-100 text-green-800' 
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                          {job.status}
                        </span>
                      </div>
                    </div>
                    
                    <div className="mt-3 flex space-x-2">
                      <button className="text-sm text-blue-600 hover:text-blue-500">Edit</button>
                      <button className="text-sm text-gray-500 hover:text-gray-700">View Applications</button>
                      <button className="text-sm text-red-600 hover:text-red-500">Archive</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Save Button */}
        <div className="flex justify-end pt-6">
          <button
            type="submit"
            disabled={isSaving}
            className="px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {isSaving ? 'Saving...' : 'Save Profile'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default RecruiterProfile;