//Seb ur code was really anoying to fix - Sebas.
// JobSeekerProfile.tsx
import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  User,
  Mail,
  Phone as PhoneIcon,
  MapPin,
  Briefcase,
  GraduationCap,
  Upload,
  Plus,
  X,
  Star,
  Brain,
} from 'lucide-react';

// ============================  Types  ============================
type UploadedResumeMeta = {
  name: string;
  size: number;
  type: string;
} | null;

interface Experience {
  id: number;
  company: string;
  position: string;
  startDate: string;
  endDate: string;
  description: string;
}

interface Education {
  id: number;
  institution: string;
  degree: string;
  startDate: string;
  endDate: string;
  gpa: string;
}

interface Assessment {
  score: number | null;
  percentile: number | null;
  completed: boolean;
}

interface PsychometricResults {
  leadership: Assessment;
  problemSolving: Assessment;
  communication: Assessment;
  creativity: Assessment;
  teamwork: Assessment;
}

interface FormData {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  location: string;
  summary: string;
  uploadedResume: UploadedResumeMeta;
  experience: Experience[];
  education: Education[];
  skills: string[];
  performanceReviews: unknown[]; // refine if you have a specific shape
  psychometricResults: PsychometricResults;
}

// ============================  Component  ============================
const JobSeekerProfile: React.FC = () => {
  const { user } = useAuth() as any; // keep loose if your context isn't typed yet

  const getInitialFormData = (): FormData => ({
    firstName: user?.name?.split(' ')[0] || '',
    lastName: user?.name?.split(' ').slice(1).join(' ') || '',
    email: user?.email || '',
    phone: '',
    location: '',
    summary: '',
    uploadedResume: null,
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
  });

  const [formData, setFormData] = useState<FormData>(getInitialFormData());
  const [uploadedResume, setUploadedResume] = useState<File | null>(null);
  const [resumeUploaded, setResumeUploaded] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'personal' | 'experience' | 'education' | 'performance' | 'assessments'>('personal');
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [skillInput, setSkillInput] = useState<string>('');

  // Load profile data if it exists
  useEffect(() => {
    if (user?.profileData) {
      // Merge to preserve defaults when fields are missing
      const incoming = user.profileData as Partial<FormData>;
      setFormData((prev) => ({
        ...prev,
        ...incoming,
        experience: incoming.experience ?? [],
        education: incoming.education ?? [],
        skills: incoming.skills ?? [],
        uploadedResume: incoming.uploadedResume ?? null,
        psychometricResults:
          incoming.psychometricResults ?? prev.psychometricResults,
      }));

      if (incoming.uploadedResume) {
        setResumeUploaded(true);
      }
    }
  }, [user?.profileData]);

  // ============================  Resume Upload  ============================ 
  const handleResumeUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setUploadedResume(file);
    setResumeUploaded(!!file);
    // store a light-weight meta in form state (not the File itself)
    setFormData((prev) => ({
      ...prev,
      uploadedResume: file
        ? { name: file.name, size: file.size, type: file.type }
        : null,
    }));
  };

  // ============================  Experience  ============================ 
  const addExperience = () => {
    const newExp: Experience = {
      id: Date.now(),
      company: '',
      position: '',
      startDate: '',
      endDate: '',
      description: '',
    };
    setFormData((prev) => ({
      ...prev,
      experience: [...prev.experience, newExp],
    }));
  };

  const removeExperience = (id: number) => {
    setFormData((prev) => ({
      ...prev,
      experience: prev.experience.filter((exp) => exp.id !== id),
    }));
  };

  const updateExperience = (
    id: number,
    field: keyof Experience,
    value: string
  ) => {
    setFormData((prev) => ({
      ...prev,
      experience: prev.experience.map((exp) =>
        exp.id === id ? { ...exp, [field]: value } : exp
      ),
    }));
  };

  // ============================  Education  ============================ 
  const addEducation = () => {
    const newEdu: Education = {
      id: Date.now(),
      institution: '',
      degree: '',
      startDate: '',
      endDate: '',
      gpa: '',
    };
    setFormData((prev) => ({
      ...prev,
      education: [...prev.education, newEdu],
    }));
  };

  const removeEducation = (id: number) => {
    setFormData((prev) => ({
      ...prev,
      education: prev.education.filter((edu) => edu.id !== id),
    }));
  };

  const updateEducation = (
    id: number,
    field: keyof Education,
    value: string
  ) => {
    setFormData((prev) => ({
      ...prev,
      education: prev.education.map((edu) =>
        edu.id === id ? { ...edu, [field]: value } : edu
      ),
    }));
  };

  // ============================  Skills  ============================ 
  const addSkill = () => {
    const skill = skillInput.trim();
    if (skill && !formData.skills.includes(skill)) {
      setFormData((prev) => ({ ...prev, skills: [...prev.skills, skill] }));
      setSkillInput('');
    }
  };

  const removeSkill = (skill: string) => {
    setFormData((prev) => ({
      ...prev,
      skills: prev.skills.filter((s) => s !== skill),
    }));
  };

  // ============================  Submit  ============================ 
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      // If you have an API or context method, call it here.
      // e.g., await updateProfile(formData);
      console.log('Saving profile data:', formData);
    } finally {
      setIsSaving(false);
    }
  };

  // ============================  UI  ============================
  const tabs = [
    { id: 'personal', label: 'Personal Info', icon: User },
    { id: 'experience', label: 'Experience', icon: Briefcase },
    { id: 'education', label: 'Education', icon: GraduationCap },
    { id: 'performance', label: 'Performance', icon: Star },
    { id: 'assessments', label: 'Assessments', icon: Brain },
  ] as const;

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-2xl font-semibold mb-6">Job Seeker Profile</h1>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {tabs.map((t) => {
          const Icon = t.icon;
          const selected = activeTab === (t.id as typeof activeTab);
          return (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id as typeof activeTab)}
              className={`inline-flex items-center gap-2 px-3 py-2 rounded-md border text-sm ${
                selected
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 border-gray-300'
              }`}
              type="button"
            >
              <Icon size={16} />
              {t.label}
            </button>
          );
        })}
      </div>

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Personal */}
        {activeTab === 'personal' && (
          <section className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <label className="flex flex-col">
                <span className="text-sm text-gray-700 mb-1 flex items-center gap-2">
                  <User size={16} /> First name
                </span>
                <input
                  className="border rounded-md px-3 py-2"
                  value={formData.firstName}
                  onChange={(e) =>
                    setFormData((p) => ({ ...p, firstName: e.target.value }))
                  }
                />
              </label>
              <label className="flex flex-col">
                <span className="text-sm text-gray-700 mb-1">Last name</span>
                <input
                  className="border rounded-md px-3 py-2"
                  value={formData.lastName}
                  onChange={(e) =>
                    setFormData((p) => ({ ...p, lastName: e.target.value }))
                  }
                />
              </label>
              <label className="flex flex-col">
                <span className="text-sm text-gray-700 mb-1 flex items-center gap-2">
                  <Mail size={16} /> Email
                </span>
                <input
                  type="email"
                  className="border rounded-md px-3 py-2"
                  value={formData.email}
                  onChange={(e) =>
                    setFormData((p) => ({ ...p, email: e.target.value }))
                  }
                />
              </label>
              <label className="flex flex-col">
                <span className="text-sm text-gray-700 mb-1 flex items-center gap-2">
                  <PhoneIcon size={16} /> Phone
                </span>
                <input
                  className="border rounded-md px-3 py-2"
                  value={formData.phone}
                  onChange={(e) =>
                    setFormData((p) => ({ ...p, phone: e.target.value }))
                  }
                />
              </label>
              <label className="flex flex-col sm:col-span-2">
                <span className="text-sm text-gray-700 mb-1 flex items-center gap-2">
                  <MapPin size={16} /> Location
                </span>
                <input
                  className="border rounded-md px-3 py-2"
                  value={formData.location}
                  onChange={(e) =>
                    setFormData((p) => ({ ...p, location: e.target.value }))
                  }
                />
              </label>
              <label className="flex flex-col sm:col-span-2">
                <span className="text-sm text-gray-700 mb-1">Professional summary</span>
                <textarea
                  className="border rounded-md px-3 py-2 min-h-[120px]"
                  value={formData.summary}
                  onChange={(e) =>
                    setFormData((p) => ({ ...p, summary: e.target.value }))
                  }
                  placeholder="Brief summary of your professional background and career goals..."
                />
              </label>
            </div>

            {/* Resume Upload */}
            <div className="border rounded-md p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-medium mb-1">Resume</p>
                  <p className="text-sm text-gray-600">
                    Upload a PDF or DOCX. We’ll store basic file info only.
                  </p>
                  {(uploadedResume || resumeUploaded || formData.uploadedResume) && (
                    <div className="mt-3 text-sm text-gray-700">
                      <div className="font-medium">
                        {uploadedResume?.name || formData.uploadedResume?.name || 'Resume uploaded'}
                      </div>
                      <div>
                        {uploadedResume
                          ? `${(uploadedResume.size / 1024 / 1024).toFixed(2)} MB`
                          : formData.uploadedResume
                          ? `${(formData.uploadedResume.size / 1024 / 1024).toFixed(2)} MB`
                          : 'File processed'}
                      </div>
                    </div>
                  )}
                </div>

                <label
                  htmlFor="resume-upload"
                  className="cursor-pointer inline-flex items-center gap-2 px-3 py-2 border rounded-md bg-white font-medium text-blue-600 hover:text-blue-500"
                >
                  <Upload size={16} />
                  <span>{(uploadedResume || resumeUploaded) ? 'Replace resume' : 'Upload resume'}</span>
                  <input
                    id="resume-upload"
                    name="resume-upload"
                    type="file"
                    accept=".pdf,.doc,.docx"
                    className="sr-only"
                    onChange={handleResumeUpload}
                  />
                </label>
              </div>
            </div>
          </section>
        )}

        {/* Experience */}
        {activeTab === 'experience' && (
          <section className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="font-semibold">Experience</h2>
              <button type="button" onClick={addExperience} className="inline-flex items-center gap-2 px-3 py-2 border rounded-md">
                <Plus size={16} /> Add experience
              </button>
            </div>

            {formData.experience.length === 0 && (
              <p className="text-sm text-gray-600">No experience added yet.</p>
            )}

            <div className="space-y-4">
              {formData.experience.map((exp) => (
                <div key={exp.id} className="border rounded-md p-4 space-y-3">
                  <div className="flex justify-between">
                    <p className="font-medium">{exp.position || 'New role'}</p>
                    <button
                      type="button"
                      onClick={() => removeExperience(exp.id)}
                      className="text-red-600 hover:text-red-700 inline-flex items-center gap-1"
                      title="Remove"
                    >
                      <X size={16} /> Remove
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <input
                      className="border rounded-md px-3 py-2"
                      placeholder="Company"
                      value={exp.company}
                      onChange={(e) => updateExperience(exp.id, 'company', e.target.value)}
                    />
                    <input
                      className="border rounded-md px-3 py-2"
                      placeholder="Position"
                      value={exp.position}
                      onChange={(e) => updateExperience(exp.id, 'position', e.target.value)}
                    />
                    <input
                      className="border rounded-md px-3 py-2"
                      placeholder="Start date (e.g., 2024-06)"
                      value={exp.startDate}
                      onChange={(e) => updateExperience(exp.id, 'startDate', e.target.value)}
                    />
                    <input
                      className="border rounded-md px-3 py-2"
                      placeholder="End date (or Present)"
                      value={exp.endDate}
                      onChange={(e) => updateExperience(exp.id, 'endDate', e.target.value)}
                    />
                    <textarea
                      className="border rounded-md px-3 py-2 sm:col-span-2"
                      placeholder="Describe your role, responsibilities, and achievements..."
                      value={exp.description}
                      onChange={(e) => updateExperience(exp.id, 'description', e.target.value)}
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Education */}
        {activeTab === 'education' && (
          <section className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="font-semibold">Education</h2>
              <button type="button" onClick={addEducation} className="inline-flex items-center gap-2 px-3 py-2 border rounded-md">
                <Plus size={16} /> Add education
              </button>
            </div>

            {formData.education.length === 0 && (
              <p className="text-sm text-gray-600">No education added yet.</p>
            )}

            <div className="space-y-4">
              {formData.education.map((edu) => (
                <div key={edu.id} className="border rounded-md p-4 space-y-3">
                  <div className="flex justify-between">
                    <p className="font-medium">{edu.institution || 'New institution'}</p>
                    <button
                      type="button"
                      onClick={() => removeEducation(edu.id)}
                      className="text-red-600 hover:text-red-700 inline-flex items-center gap-1"
                      title="Remove"
                    >
                      <X size={16} /> Remove
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <input
                      className="border rounded-md px-3 py-2"
                      placeholder="Institution"
                      value={edu.institution}
                      onChange={(e) => updateEducation(edu.id, 'institution', e.target.value)}
                    />
                    <input
                      className="border rounded-md px-3 py-2"
                      placeholder="Degree"
                      value={edu.degree}
                      onChange={(e) => updateEducation(edu.id, 'degree', e.target.value)}
                    />
                    <input
                      className="border rounded-md px-3 py-2"
                      placeholder="Start date (e.g., 2023-09)"
                      value={edu.startDate}
                      onChange={(e) => updateEducation(edu.id, 'startDate', e.target.value)}
                    />
                    <input
                      className="border rounded-md px-3 py-2"
                      placeholder="End date (or Expected)"
                      value={edu.endDate}
                      onChange={(e) => updateEducation(edu.id, 'endDate', e.target.value)}
                    />
                    <input
                      className="border rounded-md px-3 py-2 sm:col-span-2"
                      placeholder="GPA"
                      value={edu.gpa}
                      onChange={(e) => updateEducation(edu.id, 'gpa', e.target.value)}
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Performance (skills) */}
        {activeTab === 'performance' && (
          <section className="space-y-4">
            <h2 className="font-semibold">Skills</h2>
            <div className="flex gap-2">
              <input
                className="border rounded-md px-3 py-2 flex-1"
                placeholder="Add a skill and press +"
                value={skillInput}
                onChange={(e) => setSkillInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    addSkill();
                  }
                }}
              />
              <button type="button" onClick={addSkill} className="inline-flex items-center gap-2 px-3 py-2 border rounded-md">
                <Plus size={16} /> Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {formData.skills.map((skill) => (
                <span key={skill} className="inline-flex items-center gap-1 px-2 py-1 border rounded-full text-sm">
                  {skill}
                  <button
                    type="button"
                    className="text-red-600 hover:text-red-700"
                    onClick={() => removeSkill(skill)}
                    title="Remove skill"
                  >
                    <X size={14} />
                  </button>
                </span>
              ))}
              {formData.skills.length === 0 && (
                <span className="text-sm text-gray-600">No skills added yet.</span>
              )}
            </div>
          </section>
        )}

        {/* Assessments (placeholder UI) */}
        {activeTab === 'assessments' && (
          <section className="space-y-2">
            <h2 className="font-semibold">Assessments</h2>
            <p className="text-sm text-gray-600">
              Track leadership, problem solving, communication, creativity, and teamwork scores here.
            </p>
          </section>
        )}

        {/* Footer actions */}
        <div className="flex justify-end">
          <button
            type="submit"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-blue-600 text-white disabled:opacity-60"
            disabled={isSaving}
          >
            {isSaving ? 'Saving…' : 'Save Profile'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default JobSeekerProfile;
