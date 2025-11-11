import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useLocation, useSearchParams } from 'react-router-dom';
import { 
  User, 
  Briefcase, 
  GraduationCap,
  Upload,
  Plus,
  X,
  Star,
  Brain
} from 'lucide-react';

function JobSeekerProfile() {
  const { user, updateProfile, updateProfileData, fetchProfileData, saveProfileData } = useAuth();

  const location = useLocation();
  

  const getTabFromURL = () => {
    // Parse directly from the current location each time
    const qs = new URLSearchParams(location.search);
    const fromSearch = qs.get('tab');
    if (fromSearch) return fromSearch;
    if (location.hash && location.hash.length > 1) return location.hash.slice(1);
    const st = (location.state as any) || {};
    if (st.initialTab) return st.initialTab;
    return null;
  };

  const [activeTab, setActiveTab] = useState<string>(() => getTabFromURL() || 'personal');
 
  useEffect(() => {
    const incoming = getTabFromURL();
    if (incoming && incoming !== activeTab) {
      setActiveTab(incoming);
    }
    // no searchParams here
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search, location.hash, location.state]);

  const [searchParams, setSearchParams] = useSearchParams();


  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(true);
  const [uploadedResume, setUploadedResume] = useState<File | null>(null);
  const [resumeUploaded, setResumeUploaded] = useState(false);

  interface UploadedResume {
    name: string;
    size: number;
    type: string;
  }

  interface PsychometricScore {
    score: number | null;
    percentile: number | null;
    completed: boolean;
  }

  interface ProfileData {
    // Personal Info
    firstName: string;
    lastName: string;
    email: string;
    phone: string;
    location: string;
    summary: string;

    // Experience / Education / Skills
    experience: any[];   // (tighten later if you have a shape)
    education: any[];    // (tighten later if you have a shape)
    skills: string[];

    // Reviews / Psychometrics
    performanceReviews: any[]; // (tighten later)
    psychometricResults: {
      leadership: PsychometricScore;
      problemSolving: PsychometricScore;
      communication: PsychometricScore;
      creativity: PsychometricScore;
      teamwork: PsychometricScore;
    };

    // Files & optional fields you mentioned elsewhere
    uploadedResume: UploadedResume | null;
    quizResults?: Record<string, unknown>;
    _quizSummary?: Record<string, unknown>;
  }

  interface ProfileFormData {
    firstName: string;
    lastName: string;
    email: string;
    phone: string;
    location: string;
    summary: string;
    experience: any[];
    education: any[];
    skills: string[];
    performanceReviews: any[];
    psychometricResults: {
      leadership: { score: number | null; percentile: number | null; completed: boolean };
      problemSolving: { score: number | null; percentile: number | null; completed: boolean };
      communication: { score: number | null; percentile: number | null; completed: boolean };
      creativity: { score: number | null; percentile: number | null; completed: boolean };
      teamwork: { score: number | null; percentile: number | null; completed: boolean };
    };
    uploadedResume: { name: string; size: number; type: string } | null;
    quizResults?: Record<string, unknown>;
    _quizSummary?: Record<string, unknown>;
  }
  type FetchProfileData = () => Promise<{ profileData?: Partial<ProfileFormData> } | null>;

  // Build defaults for the **form**
  const buildDefaultProfile = (user?: { name?: string; email?: string } | null): ProfileFormData => ({
    firstName: user?.name?.split(' ')?.[0] ?? '',
    lastName: user?.name?.split(' ')?.slice(1).join(' ') ?? '',
    email: user?.email ?? '',
    phone: '',
    location: '',
    summary: '',
    experience: [],
    education: [],
    skills: [],
    performanceReviews: [],
    psychometricResults: {
      leadership: { score: null, percentile: null, completed: false },
      problemSolving: { score: null, percentile: null, completed: false },
      communication: { score: null, percentile: null, completed: false },
      creativity: { score: null, percentile: null, completed: false },
      teamwork: { score: null, percentile: null, completed: false },
    },
    uploadedResume: null,
  });

  const getInitialFormData = (): ProfileData => {
    // If you persist profileData in auth, merge it over defaults
    // so we keep a complete, typed object.
    // (If user.profileData is unknown, cast it to Partial<ProfileData>.)
    if (user?.profileData) {
      return {
        ...buildDefaultProfile(user),
        ...(user.profileData as Partial<ProfileData>),
      };
    }
    return buildDefaultProfile(user ?? undefined);
  };


  const [formData, setFormData] = useState<ProfileFormData>(() =>
    buildDefaultProfile(user ?? undefined)
  );
  

  // Update form data when user profile data changes
  useEffect(() => {
    if (user?.profileData) {
      // Treat it as a partial and merge — guarantees we still have every required field
      setFormData((curr) => ({
        ...curr,
        ...(user.profileData as Partial<ProfileData>),
      }));
    } else {
      // optional: when user changes or clears, rebuild from defaults
      setFormData(buildDefaultProfile(user ?? undefined));
    }
  }, [user]); // depend on user; using user?.profileData is fine too

  //Fetch saved profile data from the backend when page loads
  useEffect(() => {
    const loadProfile = async () => {
      try {
        if (fetchProfileData) {
          const data = await fetchProfileData();
          if (data?.profileData) {
            setFormData((curr) => ({
              ...curr,
              ...normalizeProfileData(data.profileData), // merge partial over full
            }));
          } else {
            // optional: reset to defaults if nothing came back
            setFormData(buildDefaultProfile(user ?? undefined));
          }
        }
      } catch (err) {
        console.error("Error loading profile:", err);
      }
    };
    loadProfile();
  }, [fetchProfileData, user]); // include user so defaults realign if user changes


  const normalizeProfileData = (
    incoming?: Partial<ProfileFormData> | null
  ): Partial<ProfileFormData> => {
    if (!incoming || typeof incoming !== 'object') return {};
    return {
      // Only copy safe/known keys
      firstName: incoming.firstName ?? undefined,
      lastName: incoming.lastName ?? undefined,
      email: incoming.email ?? undefined,
      phone: incoming.phone ?? undefined,
      location: incoming.location ?? undefined,
      summary: incoming.summary ?? undefined,
      experience: incoming.experience ?? undefined,
      education: incoming.education ?? undefined,
      skills: incoming.skills ?? undefined,
      performanceReviews: incoming.performanceReviews ?? undefined,
      psychometricResults: incoming.psychometricResults ?? undefined,
      uploadedResume: incoming.uploadedResume ?? undefined,
      quizResults: incoming.quizResults ?? undefined,
      _quizSummary: incoming._quizSummary ?? undefined,
    };
  };

  // Check for uploaded resume in profile data
  useEffect(() => {
    if (user?.profileData?.uploadedResume) {
      setResumeUploaded(true);
    }
  }, [user?.profileData]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    
    const profileDataToSave = {
      ...formData,
      uploadedResume: uploadedResume ? {
        name: uploadedResume.name,
        size: uploadedResume.size,
        type: uploadedResume.type
      } : (resumeUploaded ? formData.uploadedResume : null)
    };
  



    // Update the user's name in the auth context
    const fullName = `${profileDataToSave.firstName} ${profileDataToSave.lastName}`.trim();
    updateProfile({ name: fullName, profileComplete: true });
    
    // Save locally and to backend
    updateProfileData(profileDataToSave);
    await saveProfileData(profileDataToSave);
    console.log('Profile saved to backend!');

    // Build AI pipeline automatically
    const pipeline = buildProfilePipeline();
    const stringified = JSON.stringify(pipeline, null, 2);

    console.log("AI Profile Pipeline:", stringified);

    // Update local form data
    setFormData(profileDataToSave);
    setIsSaving(false);
    setIsSaved(true);

  };

   //Warns about leaving without saving
   useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!isSaved) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
  
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isSaved]);
       
  const buildProfilePipeline = () => {
    const sections: { section: string; content: string }[] = [];

   //Personal info
    const personalInfo = `
    Name: ${formData.firstName} ${formData.lastName}
    Email: ${formData.email}
    Phone: ${formData.phone || "N/A"}
    Location: ${formData.location || "N/A"}
    Summary: ${formData.summary || "N/A"}
    `;
    sections.push({ section: "Personal Info", content: personalInfo.trim() });

    //Exp
    const experienceEntries = formData.experience?.map((exp: any) => {
      return `
      Company: ${exp.company}
      Position: ${exp.position}
      Dates: ${exp.startDate || "?"} → ${exp.endDate || "Present"}
      Description: ${exp.description || ""}
      `;
    }) || [];
    sections.push({ section: "Experience", content: experienceEntries.join("\n\n") });

    //Skills
    const skills = formData.skills?.join(", ") || "None listed";
    sections.push({ section: "Skills", content: `Skills: ${skills}` });

    //Education
    const educationEntries = formData.education?.map((edu: any) => {
      return `
      Institution: ${edu.institution}
      Degree: ${edu.degree}
      Dates: ${edu.startDate || "?"} → ${edu.endDate || "?"}
      GPA: ${edu.gpa || "N/A"}
      `;
    }) || [];
    sections.push({ section: "Education", content: educationEntries.join("\n\n") });

    return sections;
  };


  const addExperience = () => {
    const newExp = {
      id: Date.now(),
      company: '',
      position: '',
      startDate: '',
      endDate: '',
      description: ''
    };
    setFormData({
      ...formData,
      experience: [...formData.experience, newExp]
    });
  };

  const removeExperience = (id: number) => {
    setFormData({
      ...formData,
      experience: formData.experience.filter(exp => exp.id !== id)
    });
  };

  const updateExperience = (id: number, field: string, value: string) => {
    setFormData({
      ...formData,
      experience: formData.experience.map(exp => 
        exp.id === id ? { ...exp, [field]: value } : exp
      )
    });
  };

  const addSkill = (skill: string) => {
    if (skill && !formData.skills.includes(skill)) {
      setFormData({
        ...formData,
        skills: [...formData.skills, skill]
      });
    }
  };

  const removeSkill = (skill: string) => {
    setFormData({
      ...formData,
      skills: formData.skills.filter(s => s !== skill)
    });
  };

  const handleResumeUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadedResume(file);
      setResumeUploaded(true);
    }
  };

  const addEducation = () => {
    const newEdu = {
      id: Date.now(),
      institution: '',
      degree: '',
      startDate: '',
      endDate: '',
      gpa: ''
    };
    setFormData({
      ...formData,
      education: [...formData.education, newEdu]
    });
  };

  const removeEducation = (id: number) => {
    setFormData({
      ...formData,
      education: formData.education.filter(edu => edu.id !== id)
    });
  };

  const updateEducation = (id: number, field: string, value: string) => {
    setFormData({
      ...formData,
      education: formData.education.map(edu => 
        edu.id === id ? { ...edu, [field]: value } : edu
      )
    });
  };


  const handleChange = (field: string, value: any) => {
    setFormData({ ...formData, [field]: value });
    setIsSaved(false);
  };
  

  const tabs = [
    { id: 'personal', label: 'Personal Info', icon: User },
    { id: 'experience', label: 'Experience', icon: Briefcase },
    { id: 'education', label: 'Education', icon: GraduationCap },
    { id: 'performance', label: 'Performance', icon: Star },
    { id: 'assessments', label: 'Assessments', icon: Brain }
  ];

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Job Seeker Profile</h1>
        <p className="text-gray-600 mt-2">
          Complete your profile to get better job matches and increase visibility to recruiters.
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-gray-200 mb-8">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                type="button"
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  const next = new URLSearchParams(searchParams);
                  next.set('tab', tab.id);
                  setSearchParams(next, { replace: true });
                }}

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

      
      {!isSaved && (
      <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 text-yellow-800 rounded-md">
           You have unsaved changes — don't forget to click <b>Save Profile</b>.
      </div>
      )}
      <form onSubmit={handleSubmit}>
        {/* Personal Info Tab */}
        {activeTab === 'personal' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Personal Information</h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    First Name
                  </label>
                  <input
                    type="text"
                    value={formData.firstName}
                    onChange={(e) => handleChange("firstName", e.target.value)}
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
                    onChange={(e) => handleChange("lastName", e.target.value)}
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
                    onChange={(e) => handleChange("email", e.target.value)}
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
                    onChange={(e) => handleChange("phone", e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Location
                  </label>
                  <input
                    type="text"
                    value={formData.location}
                    onChange={(e) => handleChange("location", e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Professional Summary
                  </label>
                  <textarea
                    rows={4}
                    value={formData.summary}
                    onChange={(e) => handleChange("summary", e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Brief summary of your professional background and career goals..."
                  />
                </div>
              </div>

              {/* Resume Upload */}
              <div className="mt-6 pt-6 border-t border-gray-200">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Resume
                </label>
                {(uploadedResume || resumeUploaded) && (
                  <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-md">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <div className="flex-shrink-0">
                          <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
                            <svg className="w-4 h-4 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          </div>
                        </div>
                        <div className="ml-3">
                          <p className="text-sm font-medium text-green-800">
                            {uploadedResume?.name || formData.uploadedResume?.name || 'Resume uploaded successfully'}
                          </p>
                          <p className="text-xs text-green-600">
                            {uploadedResume ? `${(uploadedResume.size / 1024 / 1024).toFixed(2)} MB` : 
                             formData.uploadedResume ? `${(formData.uploadedResume.size / 1024 / 1024).toFixed(2)} MB` : 'File processed'}
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setUploadedResume(null);
                          setResumeUploaded(false);
                        }}
                        className="text-green-600 hover:text-green-500"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                )}
                <div className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-gray-300 border-dashed rounded-md">
                  <div className="space-y-1 text-center">
                    <Upload className="mx-auto h-12 w-12 text-gray-400" />
                    <div className="flex text-sm text-gray-600">
                      <label htmlFor="resume-upload" className="relative cursor-pointer bg-white rounded-md font-medium text-blue-600 hover:text-blue-500">
                        <span>{(uploadedResume || resumeUploaded) ? 'Replace resume' : 'Upload your resume'}</span>
                        <input 
                          id="resume-upload" 
                          name="resume-upload" 
                          type="file" 
                          className="sr-only" 
                          accept=".pdf,.doc,.docx"
                          onChange={handleResumeUpload}
                        />
                      </label>
                      <p className="pl-1">or drag and drop</p>
                    </div>
                    <p className="text-xs text-gray-500">PDF, DOC, DOCX up to 10MB</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Experience Tab */}
        {activeTab === 'experience' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">Work Experience</h2>
                <button
                  type="button"
                  onClick={addExperience}
                  className="flex items-center px-3 py-2 text-sm font-medium text-blue-600 hover:text-blue-500"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Experience
                </button>
              </div>

              <div className="space-y-6">
                {formData.experience.map((exp, index) => (
                  <div key={exp.id} className="p-4 border border-gray-200 rounded-lg">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-medium text-gray-900">Experience #{index + 1}</h3>
                      <button
                        type="button"
                        onClick={() => removeExperience(exp.id)}
                        className="text-red-600 hover:text-red-500"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Company
                        </label>
                        <input
                          type="text"
                          value={exp.company}
                          onChange={(e) => updateExperience(exp.id, 'company', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Position
                        </label>
                        <input
                          type="text"
                          value={exp.position}
                          onChange={(e) => updateExperience(exp.id, 'position', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Start Date
                        </label>
                        <input
                          type="month"
                          value={exp.startDate}
                          onChange={(e) => updateExperience(exp.id, 'startDate', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          End Date
                        </label>
                        <input
                          type="month"
                          value={exp.endDate}
                          onChange={(e) => updateExperience(exp.id, 'endDate', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                          placeholder="Present"
                        />
                      </div>

                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Description
                        </label>
                        <textarea
                          rows={3}
                          value={exp.description}
                          onChange={(e) => updateExperience(exp.id, 'description', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                          placeholder="Describe your role, responsibilities, and achievements..."
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Skills Section */}
              <div className="mt-8 pt-6 border-t border-gray-200">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Skills</h3>
                <div className="flex flex-wrap gap-2 mb-4">
                  {formData.skills.map((skill) => (
                    <span
                      key={skill}
                      className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800"
                    >
                      {skill}
                      <button
                        type="button"
                        onClick={() => removeSkill(skill)}
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

        {/* Education Tab */}
        {activeTab === 'education' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">Education</h2>
                <button
                  type="button"
                  onClick={addEducation}
                  className="flex items-center px-3 py-2 text-sm font-medium text-blue-600 hover:text-blue-500"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Education
                </button>
              </div>
              
              <div className="space-y-6">
                {formData.education.map((edu, index) => (
                  <div key={edu.id} className="p-4 border border-gray-200 rounded-lg">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-medium text-gray-900">Education #{index + 1}</h3>
                      <button
                        type="button"
                        onClick={() => removeEducation(edu.id)}
                        className="text-red-600 hover:text-red-500"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Institution
                        </label>
                        <input
                          type="text"
                          value={edu.institution}
                          onChange={(e) => updateEducation(edu.id, 'institution', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </div>

                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Degree
                        </label>
                        <input
                          type="text"
                          value={edu.degree}
                          onChange={(e) => updateEducation(edu.id, 'degree', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Start Date
                        </label>
                        <input
                          type="month"
                          value={edu.startDate}
                          onChange={(e) => updateEducation(edu.id, 'startDate', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          End Date
                        </label>
                        <input
                          type="month"
                          value={edu.endDate}
                          onChange={(e) => updateEducation(edu.id, 'endDate', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          GPA (Optional)
                        </label>
                        <input
                          type="text"
                          value={edu.gpa}
                          onChange={(e) => updateEducation(edu.id, 'gpa', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                          placeholder="3.8"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Performance Reviews Tab */}
        {activeTab === 'performance' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">Performance Reviews</h2>
                <button
                  type="button"
                  className="flex items-center px-3 py-2 text-sm font-medium text-blue-600 hover:text-blue-500"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Review
                </button>
              </div>

              <div className="space-y-6">
                {formData.performanceReviews.map((review) => (
                  <div key={review.id} className="p-4 bg-gray-50 rounded-lg">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <h3 className="font-medium text-gray-900">{review.company}</h3>
                        <p className="text-sm text-gray-600">{review.period}</p>
                      </div>
                      <div className="flex items-center">
                        <Star className="h-5 w-5 text-yellow-400 mr-1" />
                        <span className="text-lg font-semibold text-gray-900">{review.rating}</span>
                        <span className="text-gray-600">/5</span>
                      </div>
                    </div>
                    
                    <p className="text-gray-700 mb-3">{review.summary}</p>
                    
                    <div>
                      <h4 className="font-medium text-gray-900 mb-2">Key Achievements:</h4>
                      <ul className="list-disc list-inside space-y-1">
                        {(review.keyAchievements as any[])?.map((achievement: any, index: number) => (
                          <li key={index}>{achievement}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Assessments Tab */}
        {activeTab === 'assessments' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Solverah Psychometric Assessments</h2>
              <p className="text-gray-600 mb-6">
                Our proprietary assessments help match you with roles that align with your personality and work style.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {Object.entries(formData.psychometricResults).map(([trait, result]) => (
                  <div key={trait} className="p-4 bg-gray-50 rounded-lg">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-medium text-gray-900 capitalize">
                        {trait.replace(/([A-Z])/g, ' $1').trim()}
                      </h3>
                      <span className="text-sm text-gray-500">Not completed</span>
                    </div>
                    
                    <div className="text-center py-4">
                      <p className="text-sm text-gray-500 mb-3">
                        Complete this assessment to see your score
                      </p>
                      <button
                        type="button"
                        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm"
                      >
                        Take Assessment
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <div className="flex items-center">
                  <Brain className="h-5 w-5 text-yellow-600 mr-2" />
                  <div>
                    <h3 className="font-medium text-yellow-900">Complete Your Assessments</h3>
                    <p className="text-sm text-yellow-700">
                      Take our psychometric assessments to improve your job matching accuracy and showcase your potential to employers.
                    </p>
                  </div>
                  <button className="ml-auto px-4 py-2 bg-yellow-600 text-white rounded-md hover:bg-yellow-700 text-sm">
                    Start Assessments
                  </button>
                </div>
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

export default JobSeekerProfile;