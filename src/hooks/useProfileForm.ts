/**
 * useProfileForm — Stateful form hook for the job-seeker profile editor.
 *
 * Responsibilities:
 *   - Fetches the user's current profile from the server on mount and populates
 *     form state.
 *   - Exposes helpers for adding, updating, and removing experience / education /
 *     skill / location entries with per-collection caps.
 *   - Manages resume upload state (pending file, upload progress, parsed data
 *     returned by the backend after finalization).
 *   - Saves the entire form to POST /api/profile on submit.
 *
 * Exported helpers:
 *   buildDefaultProfile(user?)     — Build a blank ProfileFormData from a User.
 *   normalizeProfileData(incoming) — Coerce a raw server payload to ProfileFormData shape.
 *   useProfileForm()               — The hook itself; returns form state + mutators.
 */
import React, { useState, useEffect } from "react";
import { useAuth } from "../contexts/useAuth";
import { ProfileFormData, PendingResumeUpload } from "../types/profile";

// Per-collection limits enforced in the UI to prevent unreasonably large profiles.
const MAX_EXPERIENCES = 20;
const MAX_EDUCATIONS = 10;
const MAX_SKILLS = 50;
const MAX_SECONDARY_LOCATIONS = 20;

// Upload progress simulation timing constants.
const PROGRESS_TICK_MS = 450;        // interval between each progress step
const PROGRESS_RESET_DELAY_MS = 600; // delay before resetting progress bar to 0 after completion

/**
 * Build a blank ProfileFormData, optionally pre-seeded with the user's name and email.
 * Used when profile_data is null/empty on the server (new accounts) or as a
 * safe fallback if the API returns unexpected data.
 */
export function buildDefaultProfile(
  user?: { name?: string; email?: string } | null
): ProfileFormData {
  return {
    firstName: user?.name?.split(" ")?.[0] ?? "",
    lastName: user?.name?.split(" ")?.slice(1).join(" ") ?? "",
    email: user?.email ?? "",
    phone: "",
    location: "",
    primaryLocation: "",
    secondaryLocations: [],
    linkedinUrl: "",
    summary: "",
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
  };
}

/**
 * Coerce a raw server profile payload to the ProfileFormData shape.
 *
 * Handles the legacy ``location`` → ``primaryLocation`` rename and ensures all
 * optional arrays default to empty arrays rather than undefined so the UI
 * doesn't have to null-check every array field.
 */
export function normalizeProfileData(
  incoming?: Partial<ProfileFormData> | null
): Partial<ProfileFormData> {
  if (!incoming || typeof incoming !== "object") return {};
  const legacyLocation = incoming.location;
  return {
    firstName: incoming.firstName ?? undefined,
    lastName: incoming.lastName ?? undefined,
    email: incoming.email ?? undefined,
    phone: incoming.phone ?? undefined,
    location: legacyLocation ?? undefined,
    primaryLocation: incoming.primaryLocation ?? legacyLocation ?? undefined,
    secondaryLocations: incoming.secondaryLocations ?? [],
    linkedinUrl: incoming.linkedinUrl ?? undefined,
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
}

export function useProfileForm() {
  const {
    user,
    updateProfile,
    updateProfileData,
    fetchProfileData,
    saveProfileData,
    fetchWithAuth,
  } = useAuth();

  const [formData, setFormData] = useState<ProfileFormData>(() =>
    buildDefaultProfile(user ?? undefined)
  );
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(true);
  const [saveProgress, setSaveProgress] = useState(0);
  const [isUploadingResume, setIsUploadingResume] = useState(false);
  const [uploadedResume, setUploadedResume] = useState<File | null>(null);
  const [resumeUploaded, setResumeUploaded] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [pendingResume, setPendingResume] = useState<PendingResumeUpload | null>(null);
  const [experienceLimitMsg, setExperienceLimitMsg] = useState("");
  const [skillLimitMsg, setSkillLimitMsg] = useState("");
  const [educationLimitMsg, setEducationLimitMsg] = useState("");
  const [locationLimitMsg, setLocationLimitMsg] = useState("");

  // Progress bar simulation for saving
  useEffect(() => {
    if (!isSaving) return;
    setSaveProgress(8);
    const timer = setInterval(() => {
      setSaveProgress((prev) => (prev < 90 ? Math.min(90, prev + 6 + Math.random() * 6) : prev));
    }, PROGRESS_TICK_MS);
    return () => clearInterval(timer);
  }, [isSaving]);

  // Progress bar simulation for resume upload
  useEffect(() => {
    if (!isUploadingResume) return;
    setUploadProgress(8);
    const timer = setInterval(() => {
      setUploadProgress((prev) => (prev < 90 ? Math.min(90, prev + 6 + Math.random() * 6) : prev));
    }, PROGRESS_TICK_MS);
    return () => clearInterval(timer);
  }, [isUploadingResume]);

  // Sync form when user context updates
  useEffect(() => {
    if (user?.profileData) {
      setFormData((curr) => ({
        ...curr,
        ...(user.profileData as Partial<ProfileFormData>),
      }));
    } else {
      setFormData(buildDefaultProfile(user ?? undefined));
    }
  }, [user]);

  // Load profile from backend on mount
  useEffect(() => {
    const loadProfile = async () => {
      try {
        if (fetchProfileData) {
          const data = await fetchProfileData();
          if (data?.profileData) {
            setFormData((curr) => ({
              ...curr,
              ...normalizeProfileData(data.profileData as Partial<ProfileFormData>),
            }));
          } else {
            setFormData(buildDefaultProfile(user ?? undefined));
          }
        }
      } catch (err) {
        console.error("Error loading profile:", err);
      }
    };
    loadProfile();
  }, [fetchProfileData, user]);

  // Mark resume as uploaded if profile has one
  useEffect(() => {
    if ((user?.profileData as any)?.uploadedResume) {
      setResumeUploaded(true);
    }
  }, [user?.profileData]);

  // Warn before leaving with unsaved changes
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
    if (formData.summary?.trim()) {
      sections.push({ section: "Summary", content: formData.summary.trim() });
    }
    const experienceEntries =
      formData.experience?.map((exp: any) => {
        const parts: string[] = [];
        if (exp.position) parts.push(`Role: ${exp.position}`);
        if (exp.company) parts.push(`Company: ${exp.company}`);
        if (exp.description) parts.push(`Description: ${exp.description}`);
        return parts.join("\n");
      }) ?? [];
    if (experienceEntries.length > 0) {
      sections.push({ section: "Experience", content: experienceEntries.join("\n\n") });
    }
    if (formData.skills?.length > 0) {
      sections.push({ section: "Skills", content: formData.skills.join(", ") });
    }
    const educationEntries =
      formData.education?.map((edu: any) => {
        const parts: string[] = [];
        if (edu.degree) parts.push(`Degree: ${edu.degree}`);
        if (edu.institution) parts.push(`Institution: ${edu.institution}`);
        if (edu.gpa) parts.push(`GPA: ${edu.gpa}`);
        return parts.join("\n");
      }) ?? [];
    if (educationEntries.length > 0) {
      sections.push({ section: "Education", content: educationEntries.join("\n\n") });
    }
    const locationLines: string[] = [];
    const primary = (formData.primaryLocation || formData.location || "").trim();
    if (primary) locationLines.push(`Primary: ${primary}`);
    if (formData.secondaryLocations?.length > 0) {
      locationLines.push(`Open to: ${formData.secondaryLocations.join(", ")}`);
    }
    if (locationLines.length > 0) {
      sections.push({ section: "Locations", content: locationLines.join("\n") });
    }
    return sections;
  };

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

    const fullName = `${profileDataToSave.firstName} ${profileDataToSave.lastName}`.trim();
    updateProfile?.({ name: fullName, profileComplete: true });
    updateProfileData?.(profileDataToSave);

    if (saveProfileData) {
      await saveProfileData(profileDataToSave);
      console.log("Profile saved to backend!");
    } else {
      console.warn("saveProfileData is not available; profile saved locally only.");
    }

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

    setFormData(profileDataToSave);
    setSaveProgress(100);
    setIsSaving(false);
    setIsSaved(true);
    setTimeout(() => setSaveProgress(0), PROGRESS_RESET_DELAY_MS);
  };

  const handleChange = (field: string, value: any) => {
    setFormData((prev) => {
      const updated: ProfileFormData = { ...prev, [field]: value };
      if (field === "primaryLocation") updated.location = value;
      return updated;
    });
    setIsSaved(false);
  };

  // ── Experience ──────────────────────────────────────────────────────────────
  const addExperience = () => {
    if (formData.experience.length >= MAX_EXPERIENCES) {
      setExperienceLimitMsg(`You have reached the maximum of ${MAX_EXPERIENCES} experiences.`);
      return;
    }
    if (experienceLimitMsg) setExperienceLimitMsg("");
    setFormData((prev) => ({
      ...prev,
      experience: [
        ...prev.experience,
        { id: Date.now(), company: "", position: "", startDate: "", endDate: "", description: "" },
      ],
    }));
  };

  const removeExperience = (id: number) => {
    setFormData((prev) => ({ ...prev, experience: prev.experience.filter((e) => e.id !== id) }));
  };

  const updateExperience = (id: number, field: string, value: string) => {
    setFormData((prev) => ({
      ...prev,
      experience: prev.experience.map((e) => (e.id === id ? { ...e, [field]: value } : e)),
    }));
  };

  // ── Skills ──────────────────────────────────────────────────────────────────
  const addSkill = (skill: string) => {
    if (!skill) return;
    if (formData.skills.length >= MAX_SKILLS) {
      setSkillLimitMsg(`You have reached the maximum of ${MAX_SKILLS} skills.`);
      return;
    }
    if (!formData.skills.includes(skill)) {
      if (skillLimitMsg) setSkillLimitMsg("");
      setFormData((prev) => ({ ...prev, skills: [...prev.skills, skill] }));
    }
  };

  const removeSkill = (skill: string) => {
    setFormData((prev) => ({ ...prev, skills: prev.skills.filter((s) => s !== skill) }));
  };

  // ── Education ───────────────────────────────────────────────────────────────
  const addEducation = () => {
    if (formData.education.length >= MAX_EDUCATIONS) {
      setEducationLimitMsg(`You have reached the maximum of ${MAX_EDUCATIONS} education entries.`);
      return;
    }
    if (educationLimitMsg) setEducationLimitMsg("");
    setFormData((prev) => ({
      ...prev,
      education: [
        ...prev.education,
        { id: Date.now(), institution: "", degree: "", startDate: "", endDate: "", gpa: "" },
      ],
    }));
  };

  const removeEducation = (id: number) => {
    setFormData((prev) => ({ ...prev, education: prev.education.filter((e) => e.id !== id) }));
  };

  const updateEducation = (id: number, field: string, value: string) => {
    setFormData((prev) => ({
      ...prev,
      education: prev.education.map((e) => (e.id === id ? { ...e, [field]: value } : e)),
    }));
  };

  // ── Secondary Locations ─────────────────────────────────────────────────────
  const addSecondaryLocation = (loc: string) => {
    const trimmed = loc.trim();
    if (!trimmed) return;
    if (formData.secondaryLocations.length >= MAX_SECONDARY_LOCATIONS) {
      setLocationLimitMsg(`You have reached the maximum of ${MAX_SECONDARY_LOCATIONS} locations.`);
      return;
    }
    if (!formData.secondaryLocations.includes(trimmed)) {
      if (locationLimitMsg) setLocationLimitMsg("");
      setFormData((prev) => ({ ...prev, secondaryLocations: [...prev.secondaryLocations, trimmed] }));
      setIsSaved(false);
    }
  };

  const removeSecondaryLocation = (loc: string) => {
    setFormData((prev) => ({
      ...prev,
      secondaryLocations: prev.secondaryLocations.filter((l) => l !== loc),
    }));
    setIsSaved(false);
  };

  // ── Resume ──────────────────────────────────────────────────────────────────
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
      setPendingResume({ objectKey: presign.object_key, mime: file.type, size: file.size, name: file.name });
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
      setTimeout(() => setUploadProgress(0), PROGRESS_RESET_DELAY_MS);
    }
  };

  const handleViewResume = async () => {
    try {
      const data = await fetchWithAuth<{ url: string }>("/profile/resume-url", { method: "GET" });
      if (data?.url) window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (err) {
      console.error(err);
      alert("Unable to open resume right now.");
    }
  };

  const removeUploadedResume = () => {
    setUploadedResume(null);
    setFormData((curr) => ({ ...curr, uploadedResume: null, resumeKey: null }));
    setResumeUploaded(false);
    setPendingResume(null);
    setIsSaved(false);
  };

  return {
    formData,
    setFormData,
    isSaving,
    isSaved,
    setIsSaved,
    saveProgress,
    isUploadingResume,
    uploadProgress,
    uploadedResume,
    resumeUploaded,
    pendingResume,
    experienceLimitMsg,
    skillLimitMsg,
    educationLimitMsg,
    locationLimitMsg,
    handleSubmit,
    handleChange,
    addExperience,
    removeExperience,
    updateExperience,
    addSkill,
    removeSkill,
    addEducation,
    removeEducation,
    updateEducation,
    addSecondaryLocation,
    removeSecondaryLocation,
    handleResumeUpload,
    handleViewResume,
    removeUploadedResume,
  };
}
