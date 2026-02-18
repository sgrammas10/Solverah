import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/useAuth';
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
import { Link } from "react-router-dom";
import CareerQuizzes from "../components/CareerQuizzes";
import NextChapterYourWayQuiz from "../components/NextChapterYourWayQuiz";
import SolverahYourFutureYourWayQuiz from "../components/SolverahYourFutureYourWayQuiz";

type QuizQuestion = { id: number; text: string; options: string[] };

// Import question banks from the quiz components
import { careerJobSearchQuestionBank } from "../data/nextChapterYourWayQuiz";
import { yourFutureYourWayQuestionBank } from "../data/solverahYourFutureYourWayQuiz";
function JobSeekerProfile() {
  const { user, updateProfile, updateProfileData, fetchProfileData, saveProfileData, fetchWithAuth} = useAuth();

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
  const [isUploadingResume, setIsUploadingResume] = useState(false);
  const [uploadedResume, setUploadedResume] = useState<File | null>(null);
  const [resumeUploaded, setResumeUploaded] = useState(false);
  const [saveProgress, setSaveProgress] = useState(0);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [pendingResume, setPendingResume] = useState<PendingResumeUpload | null>(null);

  const [showQuizResults, setShowQuizResults] = useState(false);

  useEffect(() => {
    if (!isSaving) return;
    setSaveProgress(8);
    const timer = setInterval(() => {
      setSaveProgress((prev) => (prev < 90 ? Math.min(90, prev + 6 + Math.random() * 6) : prev));
    }, 450);
    return () => clearInterval(timer);
  }, [isSaving]);

  useEffect(() => {
    if (!isUploadingResume) return;
    setUploadProgress(8);
    const timer = setInterval(() => {
      setUploadProgress((prev) => (prev < 90 ? Math.min(90, prev + 6 + Math.random() * 6) : prev));
    }, 450);
    return () => clearInterval(timer);
  }, [isUploadingResume]);


  interface UploadedResume {
    name: string;
    size: number;
    type: string;
  }

  interface PendingResumeUpload {
    objectKey: string;
    mime: string;
    size: number;
    name: string;
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
    primaryLocation?: string;
    secondaryLocations?: string[];
    summary: string;

    // Experience / Education / Skills
    experience: any[];
    education: any[];
    skills: string[];

    // Reviews / Psychometrics
    performanceReviews: any[];
    psychometricResults: {
      leadership: PsychometricScore;
      problemSolving: PsychometricScore;
      communication: PsychometricScore;
      creativity: PsychometricScore;
      teamwork: PsychometricScore;
    };

    uploadedResume: UploadedResume | null;
    resumeKey?: string | null;
    quizResults?: Record<string, unknown>;
    _quizSummary?: Record<string, unknown>;
  }

  interface ProfileFormData {
    firstName: string;
    lastName: string;
    email: string;
    phone: string;
    location: string;
    primaryLocation: string;   
    secondaryLocations: string[]; 
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
    resumeKey?: string | null;
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
    primaryLocation: '', 
    secondaryLocations: [], 
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
    resumeKey: null,
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

    const legacyLocation = incoming.location;

    return {
      firstName: incoming.firstName ?? undefined,
      lastName: incoming.lastName ?? undefined,
      email: incoming.email ?? undefined,
      phone: incoming.phone ?? undefined,
      location: legacyLocation ?? undefined,
      primaryLocation: incoming.primaryLocation ?? legacyLocation ?? undefined, 
      secondaryLocations: incoming.secondaryLocations ?? [], 
      summary: incoming.summary ?? undefined,
      experience: incoming.experience ?? undefined,
      education: incoming.education ?? undefined,
      skills: incoming.skills ?? undefined,
      performanceReviews: incoming.performanceReviews ?? undefined,
      psychometricResults: incoming.psychometricResults ?? undefined,
      uploadedResume: incoming.uploadedResume ?? undefined,
      resumeKey: incoming.resumeKey ?? undefined,
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
    
    let profileDataToSave = {
      ...formData,
      uploadedResume: uploadedResume
        ? { name: uploadedResume.name, size: uploadedResume.size, type: uploadedResume.type }
        : formData.uploadedResume ?? null,
    };

    if (pendingResume) {
      try {
        const finalized = await fetchWithAuth<{ profileData?: Partial<ProfileFormData> }>(
          "/profile/resume/finalize",
          {
            method: "POST",
            body: JSON.stringify({
              object_key: pendingResume.objectKey,
              mime: pendingResume.mime,
              size: pendingResume.size,
              name: pendingResume.name,
            }),
          }
        );

        if (finalized?.profileData) {
          const normalized = normalizeProfileData(finalized.profileData);
          profileDataToSave = {
            ...profileDataToSave,
            ...normalized,
            experience: normalized.experience ?? profileDataToSave.experience,
            education: normalized.education ?? profileDataToSave.education,
            skills: normalized.skills ?? profileDataToSave.skills,
            uploadedResume: normalized.uploadedResume ?? profileDataToSave.uploadedResume,
            resumeKey: normalized.resumeKey ?? profileDataToSave.resumeKey,
          };
          setPendingResume(null);
        }
      } catch (err) {
        console.error(err);
        alert("Unable to process resume right now.");
      }
    }

    // Update the user's name in the auth context
    const fullName = `${profileDataToSave.firstName} ${profileDataToSave.lastName}`.trim();
    updateProfile?.({ name: fullName, profileComplete: true });
    
    // Save locally and to backend
    updateProfileData?.(profileDataToSave);
    if (saveProfileData) {
      await saveProfileData(profileDataToSave);
      console.log('Profile saved to backend!');
    } else {
      console.warn('saveProfileData is not available; profile saved locally only.');
    }


    // Build AI pipeline automatically (PII-safe for the model)
    const modelPipeline = buildProfilePipeline();
    const stringified = JSON.stringify(modelPipeline);
    try {
      await fetchWithAuth("/recommendations", {
        method: "POST",
        body: JSON.stringify({ profilePipeline: stringified }),
      });
      console.log("Job recommendations generated and saved!");
    } catch (err) {
      console.error("Error generating recommendations:", err);
    }

    console.log("AI Profile Pipeline:", stringified);

    // Update local form data
    setFormData(profileDataToSave);
    setSaveProgress(100);
    setIsSaving(false);
    setIsSaved(true);
    setTimeout(() => setSaveProgress(0), 600);

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
  
  type QuizResultsSectionProps = {
    title: string;
    questions: QuizQuestion[];
    answers: Record<string, number> | Record<number, number>;
  };

  const QuizResultsSection: React.FC<QuizResultsSectionProps> = ({
    title,
    questions,
    answers,
  }) => {
    const getQuestionById = (id: number) => questions.find((q) => q.id === id);

    const entries = Object.entries(answers)
      .map(([idStr, idx]) => ({ id: Number(idStr), idx }))
      .sort((a, b) => a.id - b.id);

    return (
      <section className="bg-slate-900/70 border border-white/10 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-white mb-3">{title}</h3>
        <ol className="space-y-3 list-decimal list-inside text-sm text-white">
          {entries.map(({ id, idx }) => {
            const question = getQuestionById(id);
            if (!question) return null;

            const choiceIndex = typeof idx === "number" ? idx : Number(idx);
            const answerText =
              question.options[choiceIndex] ?? "No answer selected";

            return (
              <li key={id}>
                <div className="font-medium">{question.text}</div>
                <div className="text-slate-200/80">
                  <span className="font-semibold">Your answer: </span>
                  {answerText}
                </div>
              </li>
            );
          })}
        </ol>
      </section>
    );
  };


  const buildProfilePipeline = () => {
    const sections: { section: string; content: string }[] = [];

    if (formData.summary && formData.summary.trim()) {
      sections.push({
        section: "Summary",
        content: formData.summary.trim(),
      });
    }

    const experienceEntries =
      formData.experience?.map((exp: any) => {
        const parts: string[] = [];

        if (exp.position) {
          parts.push(`Role: ${exp.position}`);
        }
        if (exp.company) {
          parts.push(`Company: ${exp.company}`);
        }
        if (exp.description) {
          parts.push(`Description: ${exp.description}`);
        }

        return parts.join("\n");
      }) || [];

    if (experienceEntries.length > 0) {
      sections.push({
        section: "Experience",
        content: experienceEntries.join("\n\n"),
      });
    }

    if (formData.skills && formData.skills.length > 0) {
      sections.push({
        section: "Skills",
        content: formData.skills.join(", "),
      });
    }

    const educationEntries =
      formData.education?.map((edu: any) => {
        const parts: string[] = [];

        if (edu.degree) {
          parts.push(`Degree: ${edu.degree}`);
        }
        if (edu.institution) {
          parts.push(`Institution: ${edu.institution}`);
        }
        if (edu.gpa) {
          parts.push(`GPA: ${edu.gpa}`);
        }

        return parts.join("\n");
      }) || [];

    if (educationEntries.length > 0) {
      sections.push({
        section: "Education",
        content: educationEntries.join("\n\n"),
      });
    }

    // NEW: Locations section – primary + open-to-work
    const locationLines: string[] = [];

    const primary = (formData.primaryLocation || formData.location || "").trim();
    if (primary) {
      locationLines.push(`Primary: ${primary}`);
    }

    if (formData.secondaryLocations && formData.secondaryLocations.length > 0) {
      locationLines.push(
        `Open to: ${formData.secondaryLocations.join(", ")}`
      );
    }

    if (locationLines.length > 0) {
      sections.push({
        section: "Locations",
        content: locationLines.join("\n"),
      });
    }

    return sections;
  };


  const [experienceLimitMsg, setExperienceLimitMsg] = useState("");
  const MAX_EXPERIENCES = 20;
  const addExperience = () => {
    if (formData.experience.length >= MAX_EXPERIENCES) {
      setExperienceLimitMsg(`You have reached the maximum of ${MAX_EXPERIENCES} experiences.`);
      return;
    }

    // clear existing message if user goes under the limit later
    if (experienceLimitMsg) setExperienceLimitMsg("");

    const newExp = {
      id: Date.now(),
      company: "",
      position: "",
      startDate: "",
      endDate: "",
      description: "",
    };

    setFormData({
      ...formData,
      experience: [...formData.experience, newExp],
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

  const MAX_SKILLS = 50;
  const [skillLimitMsg, setSkillLimitMsg] = useState("");
  const addSkill = (skill: string) => {
    if (!skill) return;

    // Check max skill count
    if (formData.skills.length >= MAX_SKILLS) {
      setSkillLimitMsg(`You have reached the maximum of ${MAX_SKILLS} skills.`);
      return;
    }

    // Prevent duplicates
    if (!formData.skills.includes(skill)) {
      // clear any previous limit message if going back under limit
      if (skillLimitMsg) setSkillLimitMsg("");

      setFormData({
        ...formData,
        skills: [...formData.skills, skill],
      });
    }
  };


  const removeSkill = (skill: string) => {
    setFormData({
      ...formData,
      skills: formData.skills.filter(s => s !== skill)
    });
  };

  const handleResumeUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadedResume(file);
    setIsSaved(false);
    setIsUploadingResume(true);

    try {
      const presign = await fetchWithAuth<{
        object_key: string;
        upload_url: string;
        max_bytes: number;
      }>("/profile/resume/presign", {
        method: "POST",
        body: JSON.stringify({ mime: file.type, size: file.size }),
      });

      await fetch(presign.upload_url, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file,
      });

      setPendingResume({
        objectKey: presign.object_key,
        mime: file.type,
        size: file.size,
        name: file.name,
      });

      setFormData((prev) => ({
        ...prev,
        uploadedResume: { name: file.name, size: file.size, type: file.type },
      }));
      setResumeUploaded(true);
    } catch (err) {
      console.error(err);
      alert("Unable to process resume right now.");
    } finally {
      setUploadedResume(null);
      setUploadProgress(100);
      setIsUploadingResume(false);
      setTimeout(() => setUploadProgress(0), 600);
    }
  };
  const handleViewResume = async () => {
    try {
      const data = await fetchWithAuth<{ url: string }>("/profile/resume-url", { method: "GET" });
      if (data?.url) {
        window.open(data.url, "_blank", "noopener,noreferrer");
      }
    } catch (err) {
      console.error(err);
      alert("Unable to open resume right now.");
    }
  };
  const MAX_EDUCATIONS = 10;
  const [educationLimitMsg, setEducationLimitMsg] = useState("");
  const addEducation = () => {
    // Check max education count
    if (formData.education.length >= MAX_EDUCATIONS) {
      setEducationLimitMsg(`You have reached the maximum of ${MAX_EDUCATIONS} education entries.`);
      return;
    }

    // Clear warning if we're under the limit again
    if (educationLimitMsg) setEducationLimitMsg("");

    const newEdu = {
      id: Date.now(),
      institution: "",
      degree: "",
      startDate: "",
      endDate: "",
      gpa: "",
    };

    setFormData({
      ...formData,
      education: [...formData.education, newEdu],
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



  const MAX_SECONDARY_LOCATIONS = 20;
  const [locationLimitMsg, setLocationLimitMsg] = useState("");

  const addSecondaryLocation = (loc: string) => {
    const trimmed = loc.trim();
    if (!trimmed) return;

    if (formData.secondaryLocations.length >= MAX_SECONDARY_LOCATIONS) {
      setLocationLimitMsg(`You have reached the maximum of ${MAX_SECONDARY_LOCATIONS} locations.`);
      return;
    }

    if (!formData.secondaryLocations.includes(trimmed)) {
      if (locationLimitMsg) setLocationLimitMsg("");
      setFormData({
        ...formData,
        secondaryLocations: [...formData.secondaryLocations, trimmed],
      });
      setIsSaved(false);
    }
  };

  const removeSecondaryLocation = (loc: string) => {
    setFormData({
      ...formData,
      secondaryLocations: formData.secondaryLocations.filter((l) => l !== loc),
    });
    setIsSaved(false);
  };


  const handleChange = (field: string, value: any) => {
    setFormData((prev) => {
      const updated: ProfileFormData = { ...prev, [field]: value } as ProfileFormData;

      if (field === "primaryLocation") {
        updated.location = value;
      }

      return updated;
    });
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
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-slate-100">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Job Seeker Profile</h1>
        <p className="text-slate-200/80 mt-2">
          Complete your profile to get better job matches and increase visibility to recruiters.
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-white/10 mb-8">
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
                    ? 'border-emerald-300/60 text-emerald-200'
                    : 'border-transparent text-slate-300 hover:text-slate-200/80 hover:border-white/10'
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
      <div className="mb-4 p-3 bg-amber-500/10 border border-amber-400/30 text-amber-100 rounded-md">
           You have unsaved changes — don't forget to click <b>Save Profile</b>.
      </div>
      )}
      <form onSubmit={handleSubmit}>
        {/* Personal Info Tab */}
        {activeTab === 'personal' && (
          <div className="space-y-6">
            <div className="bg-slate-900/70 rounded-lg shadow-sm border border-white/10 p-6">
              <h2 className="text-lg font-semibold text-white mb-4">Personal Information</h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-slate-200/80 mb-2">
                    First Name
                  </label>
                  <input
                    type="text"
                    maxLength={25}
                    value={formData.firstName}
                    onChange={(e) => handleChange("firstName", e.target.value)}
                    className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-200/80 mb-2">
                    Last Name
                  </label>
                  <input
                    type="text"
                    maxLength={25}
                    value={formData.lastName}
                    onChange={(e) => handleChange("lastName", e.target.value)}
                    className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-200/80 mb-2">
                    Email
                  </label>
                  <input
                    type="email"
                    maxLength={50}
                    value={formData.email}
                    onChange={(e) => handleChange("email", e.target.value)}
                    className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-200/80 mb-2">
                    Phone
                  </label>
                  <input
                    type="tel"
                    maxLength={25}
                    value={formData.phone}
                    onChange={(e) => handleChange("phone", e.target.value)}
                    className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                  />
                </div>

                {/* Primary Location */}
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-slate-200/80 mb-2">
                    Primary Location (where you live)
                  </label>
                  <input
                    type="text"
                    maxLength={50}
                    value={formData.primaryLocation}
                    onChange={(e) => handleChange("primaryLocation", e.target.value)}
                    className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                    placeholder="e.g., Annapolis, MD"
                  />
                </div>

                {/* Secondary / Open-to-work Locations */}
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-slate-200/80 mb-2">
                    Open to work locations
                  </label>

                  <div className="flex flex-wrap gap-2 mb-2">
                    {formData.secondaryLocations.map((loc) => (
                      <span
                        key={loc}
                        className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-500/10 text-blue-100"
                      >
                        {loc}
                        <button
                          type="button"
                          onClick={() => removeSecondaryLocation(loc)}
                          className="ml-2 text-emerald-200 hover:text-emerald-100"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>

                  <div className="flex">
                    <input
                      type="text"
                      maxLength={50}
                      placeholder="Add a location (press Enter)"
                      className="flex-1 px-3 py-2 border border-white/10 rounded-l-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                      onKeyPress={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          const target = e.target as HTMLInputElement;
                          addSecondaryLocation(target.value);
                          target.value = "";
                        }
                      }}
                    />
                    <button
                      type="button"
                      className="px-4 py-2 bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 text-slate-950 rounded-r-md hover:from-emerald-300 hover:via-blue-400 hover:to-indigo-400"
                      onClick={(e) => {
                        const input = (e.currentTarget.previousElementSibling as HTMLInputElement);
                        addSecondaryLocation(input.value);
                        input.value = "";
                      }}
                    >
                      Add
                    </button>
                  </div>

                  {locationLimitMsg && (
                    <div className="mt-2 p-2 text-red-100 bg-red-500/10 border border-red-500/30 rounded">
                      {locationLimitMsg}
                    </div>
                  )}
                </div>


                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-slate-200/80 mb-2">
                    Professional Summary
                  </label>
                  <textarea
                    rows={4}
                    maxLength={4000}
                    value={formData.summary}
                    onChange={(e) => handleChange("summary", e.target.value)}
                    className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                    placeholder="Brief summary of your professional background and career goals..."
                  />
                </div>
              </div>

              {/* Resume Upload */}
              <div className="mt-6 pt-6 border-t border-white/10">
                <label className="block text-sm font-medium text-slate-200/80 mb-2">
                  Resume
                </label>
                {isUploadingResume && (
                  <div className="mb-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-emerald-200/80">
                      Uploading resume
                    </div>
                    <div className="mt-2 h-2 w-full rounded-full bg-white/10">
                      <div
                        className="h-2 rounded-full bg-emerald-400 transition-all duration-300"
                        style={{ width: `${Math.min(100, Math.max(4, uploadProgress))}%` }}
                      />
                    </div>
                  </div>
                )}
                {(uploadedResume || formData.uploadedResume) && (
                  <div className="mb-4 p-3 bg-emerald-500/10 border border-emerald-400/30 rounded-md">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <div className="flex-shrink-0">
                          <div className="w-8 h-8 bg-emerald-400/10 rounded-full flex items-center justify-center">
                            <svg className="w-4 h-4 text-emerald-200" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          </div>
                        </div>
                        <div className="ml-3">
                          <p className="text-sm font-medium text-emerald-100">
                            {uploadedResume?.name || formData.uploadedResume?.name || 'Resume uploaded successfully'}
                          </p>
                          <p className="text-xs text-emerald-200">
                            {uploadedResume ? `${(uploadedResume.size / 1024 / 1024).toFixed(2)} MB` : 
                             formData.uploadedResume ? `${(formData.uploadedResume.size / 1024 / 1024).toFixed(2)} MB` : 'File processed'}
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setUploadedResume(null);
                          setFormData((curr) => ({ ...curr, uploadedResume: null, resumeKey: null }));
                          setResumeUploaded(false);
                          setPendingResume(null);
                          setIsSaved(false);
                        }}
                        className="text-emerald-200 hover:text-emerald-100"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                    {formData.resumeKey && (
                      <div className="mt-3 flex justify-end">
                        <button
                          type="button"
                          onClick={handleViewResume}
                          className="rounded-full border border-emerald-300/50 px-3 py-1 text-xs font-semibold text-emerald-100 hover:border-emerald-200"
                        >
                          View Resume
                        </button>
                      </div>
                    )}
                  </div>
                )}
                <div className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-white/10 border-dashed rounded-md">
                  <div className="space-y-1 text-center">
                    <Upload className="mx-auto h-12 w-12 text-slate-400" />
                    <div className="flex text-sm text-slate-200/80">
                      <label htmlFor="resume-upload" className="relative cursor-pointer bg-slate-900/70 rounded-md font-medium text-emerald-200 hover:text-emerald-100">
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
                    <p className="text-xs text-slate-300">PDF, DOC, DOCX up to 10MB</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Experience Tab */}
        {activeTab === 'experience' && (
          <div className="space-y-6">
            <div className="bg-slate-900/70 rounded-lg shadow-sm border border-white/10 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-white">Work Experience</h2>           
                <button
                  type="button"
                  onClick={addExperience}
                  className="flex items-center px-3 py-2 text-sm font-medium text-emerald-200 hover:text-emerald-100"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Experience
                </button>
              </div>
              {experienceLimitMsg && (
                <div className="p-2 mb-3 text-red-100 bg-red-500/10 border border-red-500/30 rounded">
                  {experienceLimitMsg}
                </div>
              )}
              <div className="space-y-6">
                {formData.experience.map((exp, index) => (
                  <div key={exp.id} className="p-4 border border-white/10 rounded-lg">
                    {/*
                      If endDate is "Present"/"Current", treat as currently employed.
                      Keep the input empty/disabled to avoid invalid value for type="month".
                    */}
                    {(() => {
                      const isCurrent =
                        (exp.endDate || "").toLowerCase() === "present" ||
                        (exp.endDate || "").toLowerCase() === "current";
                      const endDateValue = isCurrent ? "" : exp.endDate;
                      return (
                        <>
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-medium text-white">Experience #{index + 1}</h3>
                      <button
                        type="button"
                        onClick={() => removeExperience(exp.id)}
                        className="text-red-200 hover:text-red-100"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-slate-200/80 mb-1">
                          Company
                        </label>
                        <input
                          type="text"
                          maxLength={50}
                          value={exp.company}
                          onChange={(e) => updateExperience(exp.id, 'company', e.target.value)}
                          className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-slate-200/80 mb-1">
                          Position
                        </label>
                        <input
                          type="text"
                          maxLength={50}
                          value={exp.position}
                          onChange={(e) => updateExperience(exp.id, 'position', e.target.value)}
                          className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-slate-200/80 mb-1">
                          Start Date
                        </label>
                        <input
                          type="month"
                          maxLength={50}
                          value={exp.startDate}
                          onChange={(e) => updateExperience(exp.id, 'startDate', e.target.value)}
                          className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-slate-200/80 mb-1">
                          End Date
                        </label>
                        <input
                          type="month"
                          maxLength={50}
                          value={endDateValue}
                          onChange={(e) => updateExperience(exp.id, 'endDate', e.target.value)}
                          disabled={isCurrent}
                          className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                          placeholder="Present"
                        />
                        <label className="mt-2 inline-flex items-center gap-2 text-sm text-slate-200/80">
                          <input
                            type="checkbox"
                            checked={isCurrent}
                            onChange={(e) =>
                              updateExperience(
                                exp.id,
                                'endDate',
                                e.target.checked ? 'Present' : ''
                              )
                            }
                            className="h-4 w-4 rounded border-white/20 bg-transparent text-emerald-300 focus:ring-emerald-300/50"
                          />
                          I currently work here
                        </label>
                      </div>

                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-slate-200/80 mb-1">
                          Description
                        </label>
                        <textarea
                          rows={3}
                          maxLength={4000}
                          value={exp.description}
                          onChange={(e) => updateExperience(exp.id, 'description', e.target.value)}
                          className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                          placeholder="Describe your role, responsibilities, and achievements..."
                        />
                      </div>
                    </div>
                        </>
                      );
                    })()}
                  </div>
                ))}
              </div>

              {/* Skills Section */}
              <div className="mt-8 pt-6 border-t border-white/10">
                <h3 className="text-lg font-medium text-white mb-4">Skills</h3>
                <div className="flex flex-wrap gap-2 mb-4">
                  {formData.skills.map((skill) => (
                    <span
                      key={skill}
                      className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-500/10 text-blue-100"
                    >
                      {skill}
                      <button
                        type="button"
                        onClick={() => removeSkill(skill)}
                        className="ml-2 text-emerald-200 hover:text-emerald-100"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex">
                  <input
                    type="text"
                    maxLength={50}
                    placeholder="Add a skill (press Enter)"
                    className="flex-1 px-3 py-2 border border-white/10 rounded-l-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
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
                    className="px-4 py-2 bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 text-slate-950 rounded-r-md hover:from-emerald-300 hover:via-blue-400 hover:to-indigo-400"
                    onClick={(e) => {
                      const input = (e.target as HTMLButtonElement).previousElementSibling as HTMLInputElement;
                      addSkill(input.value);
                      input.value = '';
                    }}
                  >
                    Add
                  </button>
                </div>
                {skillLimitMsg && (
                  <div className="p-2 mb-3 text-red-100 bg-red-500/10 border border-red-500/30 rounded">
                    {skillLimitMsg}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Education Tab */}
        {activeTab === 'education' && (
          <div className="space-y-6">
            <div className="bg-slate-900/70 rounded-lg shadow-sm border border-white/10 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-white">Education</h2>
                <button
                  type="button"
                  onClick={addEducation}
                  className="flex items-center px-3 py-2 text-sm font-medium text-emerald-200 hover:text-emerald-100"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Education
                </button>
              </div>
              {educationLimitMsg && (
                <div className="p-2 mb-3 text-red-100 bg-red-500/10 border border-red-500/30 rounded">
                  {educationLimitMsg}
                </div>
              )}
              <div className="space-y-6">
                {formData.education.map((edu, index) => (
                  <div key={edu.id} className="p-4 border border-white/10 rounded-lg">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-medium text-white">Education #{index + 1}</h3>
                      <button
                        type="button"
                        onClick={() => removeEducation(edu.id)}
                        className="text-red-200 hover:text-red-100"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-slate-200/80 mb-1">
                          Institution
                        </label>
                        <input
                          type="text"
                          maxLength={50}
                          value={edu.institution}
                          onChange={(e) => updateEducation(edu.id, 'institution', e.target.value)}
                          className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                        />
                      </div>

                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-slate-200/80 mb-1">
                          Degree
                        </label>
                        <input
                          type="text"
                          maxLength={50}
                          value={edu.degree}
                          onChange={(e) => updateEducation(edu.id, 'degree', e.target.value)}
                          className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-slate-200/80 mb-1">
                          Start Date
                        </label>
                        <input
                          type="month"
                          maxLength={50}
                          value={edu.startDate}
                          onChange={(e) => updateEducation(edu.id, 'startDate', e.target.value)}
                          className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-slate-200/80 mb-1">
                          End Date
                        </label>
                        <input
                          type="month"
                          maxLength={50}
                          value={edu.endDate}
                          onChange={(e) => updateEducation(edu.id, 'endDate', e.target.value)}
                          className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-slate-200/80 mb-1">
                          GPA (Optional)
                        </label>
                        <input
                          type="text"
                          maxLength={50}
                          value={edu.gpa}
                          onChange={(e) => updateEducation(edu.id, 'gpa', e.target.value)}
                          className="w-full px-3 py-2 border border-white/10 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
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
            <div className="bg-slate-900/70 rounded-lg shadow-sm border border-white/10 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-white">Performance Reviews</h2>
                <button
                  type="button"
                  className="flex items-center px-3 py-2 text-sm font-medium text-emerald-200 hover:text-emerald-100"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Review
                </button>
              </div>

              <div className="space-y-6">
                {formData.performanceReviews.map((review) => (
                  <div key={review.id} className="p-4 bg-slate-900/60 rounded-lg">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <h3 className="font-medium text-white">{review.company}</h3>
                        <p className="text-sm text-slate-200/80">{review.period}</p>
                      </div>
                      <div className="flex items-center">
                        <Star className="h-5 w-5 text-amber-300 mr-1" />
                        <span className="text-lg font-semibold text-white">{review.rating}</span>
                        <span className="text-slate-200/80">/5</span>
                      </div>
                    </div>
                    
                    <p className="text-slate-200/80 mb-3">{review.summary}</p>
                    
                    <div>
                      <h4 className="font-medium text-white mb-2">Key Achievements:</h4>
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
            <div className="bg-slate-900/70 rounded-lg shadow-sm border border-white/10 p-6">
              <h2 className="text-lg font-semibold text-white mb-4">
                Solverah Career & Psychometric Quizzes
              </h2>
              <p className="text-slate-200/80 mb-6">
                Explore our curated set of quizzes to uncover your strengths, personality traits, 
                and career motivations. Your responses will be automatically saved to your profile.
              </p>

              {/* Quiz Cards */}
              <div className="grid md:grid-cols-2 gap-6">
                {/* Career Quizzes & Archetypes */}
                <div className="border border-white/10 rounded-lg p-5 bg-slate-900/60 hover:shadow-md transition">
                  <h3 className="text-lg font-semibold text-emerald-200 mb-2">
                    Career Quizzes & Archetypes
                  </h3>
                  <p className="text-sm text-slate-200/80 mb-4">
                    Learn what drives your success and identify your career archetype across multiple themed quizzes.
                  </p>
                  <Link
                    to="/career-quizzes"
                    className="inline-block px-4 py-2 bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 text-slate-950 rounded-md hover:from-emerald-300 hover:via-blue-400 hover:to-indigo-400 text-sm"
                  >
                    {formData.quizResults?.careerQuizzes ? "View Answers" : "Start Quiz"}
                  </Link>
                </div>

                {/* Career & Job Search */}
                <div className="border border-white/10 rounded-lg p-5 bg-slate-900/60 hover:shadow-md transition">
                  <h3 className="text-lg font-semibold text-emerald-200 mb-2">
                    Career & Job Search
                  </h3>
                  <p className="text-sm text-slate-200/80 mb-4">
                    A reflection-based quiz for graduates and early-career professionals navigating their next chapter.
                  </p>
                  <Link
                    to="/career-job-search"
                    className="inline-block px-4 py-2 bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 text-slate-950 rounded-md hover:from-emerald-300 hover:via-blue-400 hover:to-indigo-400 text-sm"
                  >
                    {formData.quizResults?.careerJobSearch ? "View Answers" : "Start Quiz"}
                  </Link>
                </div>

                {/* Your Future, Your Way */}
                <div className="border border-white/10 rounded-lg p-5 bg-slate-900/60 hover:shadow-md transition md:col-span-2">
                  <h3 className="text-lg font-semibold text-emerald-200 mb-2">
                    Your Future, Your Way
                  </h3>
                  <p className="text-sm text-slate-200/80 mb-4">
                    A fun, teen-focused quiz that helps you explore interests, personality, and future goals in an engaging way.
                  </p>
                  <Link
                    to="/future-your-way"
                    className="inline-block px-4 py-2 bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 text-slate-950 rounded-md hover:from-emerald-300 hover:via-blue-400 hover:to-indigo-400 text-sm"
                  >
                    {formData.quizResults?.yourFutureYourWay ? "View Answers" : "Start Quiz"}
                  </Link>
                </div>
              </div>

              {/* Call to Action Banner */}
              <div className="mt-8 p-4 bg-amber-500/10 border border-amber-400/30 rounded-lg flex items-center">
                <Brain className="h-5 w-5 text-amber-200 mr-3" />
                <div>
                  <h3 className="font-medium text-amber-100">Complete Your Assessments</h3>
                  <p className="text-sm text-amber-200/80">
                    Taking these quizzes will improve your personalized job matching accuracy and help you stand out to employers.
                  </p>
                </div>
                <Link
                  to="/career-quizzes"
                  className="ml-auto px-4 py-2 bg-amber-500 text-white rounded-md hover:bg-amber-400 text-sm"
                >
                  View All Quizzes
                </Link>
              </div>
            </div>
          </div>
        )}


        {/* Save Button */}
        <div className="pt-6">
          {isSaving && (
            <div className="mb-4">
              <div className="text-xs uppercase tracking-[0.18em] text-emerald-200/80">
                Saving profile
              </div>
              <div className="mt-2 h-2 w-full rounded-full bg-white/10">
                <div
                  className="h-2 rounded-full bg-emerald-400 transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(4, saveProgress))}%` }}
                />
              </div>
            </div>
          )}
          <div className="flex justify-end">
          <button
            type="submit"
            disabled={isSaving}
            className="px-6 py-3 bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 text-slate-950 rounded-md hover:from-emerald-300 hover:via-blue-400 hover:to-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {isSaving ? 'Saving...' : 'Save Profile'}
          </button>
          </div>
        </div>
      </form>
    </div>
  );
}

export default JobSeekerProfile;
