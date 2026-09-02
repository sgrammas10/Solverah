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
import React, { useState, useEffect, useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../auth";
import { useProfile, profileKeys } from "./useProfile";
import { useProfileActions } from "./useProfileActions";
import { useStartResumeParseJob, useResumeParseJobStatus } from "./useResumeParseJob";
import { errorMessage } from "../../shared/api/apiError";
import { ProfileFormData, PendingResumeUpload, ResumeParseUiState, SkillLevel, Certification } from "./types";

// Per-collection limits enforced in the UI to prevent unreasonably large profiles.
const MAX_EXPERIENCES = 20;
const MAX_EDUCATIONS = 10;
const MAX_CERTIFICATIONS = 20;
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
    certifications: [],
    skills: [],
    skill_levels: {},
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
    certifications: incoming.certifications ?? [],
    skills: incoming.skills ?? undefined,
    skill_levels: incoming.skill_levels ?? undefined,
    performanceReviews: incoming.performanceReviews ?? undefined,
    psychometricResults: incoming.psychometricResults ?? undefined,
    uploadedResume: incoming.uploadedResume ?? undefined,
    resumeKey: incoming.resumeKey ?? undefined,
    quizResults: incoming.quizResults ?? undefined,
    _quizSummary: incoming._quizSummary ?? undefined,
  };
}

export function useProfileForm() {
  const { user, updateProfile, fetchWithAuth } = useAuth();
  // The document writes come from the profile slice's own hook now; only
  // identity (`user`, `updateProfile`) and the transport stay on auth.
  const { updateProfileData, saveProfileData } = useProfileActions();

  // The profile document, from the query rather than off `user`. This hook used
  // to do both -- read `user.profileData` in one effect and call
  // fetchProfileData() in another, racing to populate the same form state from
  // two copies of the same document. One source now.
  const { data: profile, isSuccess: profileLoaded } = useProfile();

  const queryClient = useQueryClient();
  const startResumeParseJob = useStartResumeParseJob();
  const [resumeParseJobId, setResumeParseJobId] = useState<string | null>(null);
  const resumeParseJobStatus = useResumeParseJobStatus(resumeParseJobId);

  const [formData, setFormData] = useState<ProfileFormData>(() =>
    buildDefaultProfile(user ?? undefined)
  );
  const [isSaved, setIsSaved] = useState(true);
  const [saveProgress, setSaveProgress] = useState(0);
  const [uploadedResume, setUploadedResume] = useState<File | null>(null);
  const [resumeUploaded, setResumeUploaded] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [pendingResume, setPendingResume] = useState<PendingResumeUpload | null>(null);
  const [experienceLimitMsg, setExperienceLimitMsg] = useState("");
  const [skillLimitMsg, setSkillLimitMsg] = useState("");
  const [educationLimitMsg, setEducationLimitMsg] = useState("");
  const [certificationLimitMsg, setCertificationLimitMsg] = useState("");
  const [locationLimitMsg, setLocationLimitMsg] = useState("");

  // Single structured resume-parse status, derived from the start mutation and
  // the poll query -- no separate hand-rolled booleans for "parsing"/"failed".
  const resumeParseStatus: ResumeParseUiState = useMemo(() => {
    if (startResumeParseJob.isError) {
      return { phase: "failed", message: errorMessage(startResumeParseJob.error, "Unable to start resume parsing.") };
    }
    if (startResumeParseJob.isPending) return { phase: "starting" };
    if (!resumeParseJobId) return { phase: "idle" };
    if (resumeParseJobStatus.error) {
      return {
        phase: "failed",
        message: errorMessage(resumeParseJobStatus.error, "Unable to check resume parsing status."),
      };
    }
    const status = resumeParseJobStatus.data?.status;
    if (status === "succeeded") return { phase: "succeeded" };
    if (status === "failed") {
      return { phase: "failed", message: resumeParseJobStatus.data?.error || "We couldn't read that file. Try uploading again." };
    }
    if (status === "queued" || status === "running") return { phase: status };
    if (status !== undefined) return { phase: "failed", message: "Resume parsing did not complete. Try uploading again." };
    return { phase: "starting" };
  }, [
    startResumeParseJob.isError,
    startResumeParseJob.error,
    startResumeParseJob.isPending,
    resumeParseJobId,
    resumeParseJobStatus.error,
    resumeParseJobStatus.data,
  ]);

  // The two-write save -- the profile PATCH (through useProfileActions) and the
  // recommendations refresh -- as one mutation, so "saving" is the mutation's
  // pending state rather than a hand-rolled boolean. The refresh keeps its own
  // swallowed catch: a failed recommendation rebuild has never failed the save.
  const saveProfile = useMutation({
    mutationFn: async (profileDataToSave: ProfileFormData) => {
      if (saveProfileData) {
        // Spread rather than passed direct: `ProfileData` wants an index
        // signature, which the anonymous spread type has and the named
        // `ProfileFormData` interface does not.
        await saveProfileData({ ...profileDataToSave });
        console.log("Profile saved to backend!");
      } else {
        console.warn("saveProfileData is not available; profile saved locally only.");
      }

      const modelPipeline = buildProfilePipeline();
      const stringified = JSON.stringify(modelPipeline);
      try {
        await fetchWithAuth("/me/recommendations/refresh", {
          method: "POST",
          body: JSON.stringify({ profilePipeline: stringified }),
        });
        console.log("Job recommendations generated and saved!");
      } catch (err) {
        console.error("Error generating recommendations:", err);
      }
      console.log("AI Profile Pipeline:", stringified);
    },
    onSuccess: (_data, profileDataToSave) => {
      setFormData(profileDataToSave);
      setIsSaved(true);
    },
    onSettled: () => {
      setSaveProgress(100);
      setTimeout(() => setSaveProgress(0), PROGRESS_RESET_DELAY_MS);
    },
  });
  const isSaving = saveProfile.isPending;

  // The resume upload -- ticket then S3 PUT -- as one mutation: the two steps
  // succeed or fail as a unit, exactly as the hand-rolled try block treated
  // them. Mutations never retry, and the PUT in particular must not be -- the
  // presigned URL is single-use.
  const uploadResume = useMutation({
    mutationFn: async (file: File) => {
      // The ticket hands back a resume_id, not a storage key -- see
      // PendingResumeUpload in types/profile.ts for why that is the security
      // improvement rather than a rename.
      const ticket = await fetchWithAuth<{
        resume_id: string;
        upload_url: string;
        max_bytes: number;
      }>("/me/resumes", {
        method: "POST",
        body: JSON.stringify({ mime: file.type, size: file.size }),
      });
      await fetch(ticket.upload_url, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file,
      });
      return ticket;
    },
    onSuccess: (ticket, file) => {
      setPendingResume({ resumeId: ticket.resume_id, mime: file.type, size: file.size, name: file.name });
      setFormData((prev) => ({
        ...prev,
        uploadedResume: { name: file.name, size: file.size, type: file.type },
      }));
      setResumeUploaded(true);

      // Kick off the parse in the background rather than waiting for submit --
      // reset first, in case a job for a resume this one is replacing is still
      // in flight.
      setResumeParseJobId(null);
      startResumeParseJob.mutate(
        { resumeId: ticket.resume_id, mime: file.type, size: file.size, name: file.name },
        { onSuccess: (data) => setResumeParseJobId(data.job_id) }
      );
    },
    onError: (err) => {
      console.error(err);
      alert("Unable to process resume right now.");
    },
    onSettled: () => {
      setUploadedResume(null);
      setUploadProgress(100);
      setTimeout(() => setUploadProgress(0), PROGRESS_RESET_DELAY_MS);
    },
  });
  const isUploadingResume = uploadResume.isPending;

  // Progress bar simulation for saving -- UX, not server state. isPending
  // starts it; the mutation settling ends it (see onSettled above).
  useEffect(() => {
    if (!isSaving) return;
    setSaveProgress(8);
    const timer = setInterval(() => {
      setSaveProgress((prev) => (prev < 90 ? Math.min(90, prev + 6 + Math.random() * 6) : prev));
    }, PROGRESS_TICK_MS);
    return () => clearInterval(timer);
  }, [isSaving]);

  // Progress bar simulation for resume upload -- same contract as the save's.
  useEffect(() => {
    if (!isUploadingResume) return;
    setUploadProgress(8);
    const timer = setInterval(() => {
      setUploadProgress((prev) => (prev < 90 ? Math.min(90, prev + 6 + Math.random() * 6) : prev));
    }, PROGRESS_TICK_MS);
    return () => clearInterval(timer);
  }, [isUploadingResume]);

  // Populate the form from the fetched document.
  //
  // Gated on isSuccess rather than on `profile` being truthy: while the query is
  // still in flight `profile` is undefined, and treating that as "no profile"
  // is what would blank a populated form for one render on every mount.
  useEffect(() => {
    if (!profileLoaded) return;
    if (profile && Object.keys(profile).length > 0) {
      setFormData((curr) => ({
        ...curr,
        ...normalizeProfileData(profile as Partial<ProfileFormData>),
      }));
    } else {
      setFormData(buildDefaultProfile(user ?? undefined));
    }
  }, [profile, profileLoaded, user]);

  // Backfill identity from the session for a document that does not carry it.
  //
  // `normalizeProfileData` writes `undefined` for every key the document is
  // missing, so a stored profile with no firstName blanks the one the session
  // knows. `||` rather than `??`: an empty string is the same nothing as
  // undefined here, and both should fall back.
  useEffect(() => {
    if (!user) return;
    const defaults = buildDefaultProfile(user);
    setFormData((curr) => ({
      ...curr,
      firstName: curr.firstName || defaults.firstName,
      lastName: curr.lastName || defaults.lastName,
      email: curr.email || defaults.email,
    }));
  }, [user]);

  // Mark resume as uploaded if profile has one
  useEffect(() => {
    if ((profile as any)?.uploadedResume) {
      setResumeUploaded(true);
    }
  }, [profile]);

  // Reflect a succeeded parse job in the open form.
  //
  // The server already persisted this merge -- resume_jobs.py's run() writes
  // it through profile_repository.update_document before the job is marked
  // succeeded, and status_for() hands back that already-current document, not
  // a snapshot from parse time. So this effect is a UI convenience, not a
  // pending write: it does NOT call setIsSaved(false) (there is nothing to
  // save) and does NOT force setIsSaved(true) either (that could paper over a
  // genuinely unrelated edit -- e.g. an unsaved phone-number change -- that
  // happens to be in flight at the same moment). It does invalidate the
  // profile query so other useProfile() consumers pick up the server's copy
  // without a manual refresh.
  //
  // Note the trade-off this shares with the old submit-time merge: if the user
  // edited a field the parse also touches (e.g. summary) before this lands,
  // that edit is overwritten. Same behavior as before, kept deliberately.
  useEffect(() => {
    const data = resumeParseJobStatus.data;
    if (data?.status !== "succeeded" || !data.profile) return;
    const normalized = normalizeProfileData(data.profile as Partial<ProfileFormData>);
    setFormData((prev) => ({
      ...prev,
      ...normalized,
      experience: normalized.experience ?? prev.experience,
      education: normalized.education ?? prev.education,
      skills: normalized.skills ?? prev.skills,
      uploadedResume: normalized.uploadedResume ?? prev.uploadedResume,
      resumeKey: normalized.resumeKey ?? prev.resumeKey,
    }));
    queryClient.invalidateQueries({ queryKey: profileKeys.document() });
    setResumeParseJobId(null);
  }, [resumeParseJobStatus.data, queryClient]);

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
      const levels = formData.skill_levels ?? {};
      const skillsContent = formData.skills
        .map((s) => (levels[s] ? `${s} (${levels[s]})` : s))
        .join(", ");
      sections.push({ section: "Skills", content: skillsContent });
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    let profileDataToSave = {
      ...formData,
      uploadedResume: uploadedResume
        ? { name: uploadedResume.name, size: uploadedResume.size, type: uploadedResume.type }
        : formData.uploadedResume ?? null,
    };

    // If any experience entry is marked as current, the user is employed.
    // Set career_status automatically so Path Intelligence stops showing the
    // "set your career status" prompt after the profile is saved.
    const hasCurrentRole = (profileDataToSave.experience ?? []).some(
      (exp: any) =>
        ["present", "current"].includes((exp.endDate ?? "").toLowerCase())
    );
    if (hasCurrentRole) {
      profileDataToSave = { ...profileDataToSave, career_status: "employed" };
    }

    // The synchronous cache merges stay ahead of the server round trip, as
    // they always were; the awaited writes live on the mutation.
    const fullName = `${profileDataToSave.firstName} ${profileDataToSave.lastName}`.trim();
    updateProfile?.({ name: fullName, profileComplete: true });
    updateProfileData?.(profileDataToSave);

    saveProfile.mutate(profileDataToSave);
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
    setFormData((prev) => {
      if (prev.skills.includes(skill)) return prev;
      if (skillLimitMsg) setSkillLimitMsg("");
      return { ...prev, skills: [...prev.skills, skill] };
    });
  };

  const removeSkill = (skill: string) => {
    setFormData((prev) => {
      const { [skill]: _removed, ...remainingLevels } = prev.skill_levels ?? {};
      return { ...prev, skills: prev.skills.filter((s) => s !== skill), skill_levels: remainingLevels };
    });
    setIsSaved(false);
  };

  const updateSkillLevel = (name: string, level: SkillLevel | undefined) => {
    setFormData((prev) => {
      const current = prev.skill_levels ?? {};
      if (level === undefined) {
        const { [name]: _removed, ...rest } = current;
        return { ...prev, skill_levels: rest };
      }
      return { ...prev, skill_levels: { ...current, [name]: level } };
    });
    setIsSaved(false);
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

  // ── Certifications ──────────────────────────────────────────────────────────
  const addCertification = () => {
    if ((formData.certifications ?? []).length >= MAX_CERTIFICATIONS) {
      setCertificationLimitMsg(`You have reached the maximum of ${MAX_CERTIFICATIONS} certifications.`);
      return;
    }
    if (certificationLimitMsg) setCertificationLimitMsg("");
    setFormData((prev) => ({
      ...prev,
      certifications: [
        ...(prev.certifications ?? []),
        { id: Date.now(), name: "", issuer: "", issueDate: "", expiryDate: "" } as Certification,
      ],
    }));
    setIsSaved(false);
  };

  const removeCertification = (id: number) => {
    setFormData((prev) => ({
      ...prev,
      certifications: (prev.certifications ?? []).filter((c) => c.id !== id),
    }));
    setIsSaved(false);
  };

  const updateCertification = (id: number, field: keyof Omit<Certification, "id">, value: string) => {
    setFormData((prev) => ({
      ...prev,
      certifications: (prev.certifications ?? []).map((c) =>
        c.id === id ? { ...c, [field]: value } : c
      ),
    }));
    setIsSaved(false);
  };

  // ── Secondary Locations ─────────────────────────────────────────────────────
  const addSecondaryLocation = (loc: string) => {
    const trimmed = loc.trim();
    if (!trimmed) return;
    if (formData.secondaryLocations.length >= MAX_SECONDARY_LOCATIONS) {
      setLocationLimitMsg(`You have reached the maximum of ${MAX_SECONDARY_LOCATIONS} locations.`);
      return;
    }
    setFormData((prev) => {
      if (prev.secondaryLocations.includes(trimmed)) return prev;
      if (locationLimitMsg) setLocationLimitMsg("");
      return { ...prev, secondaryLocations: [...prev.secondaryLocations, trimmed] };
    });
    setIsSaved(false);
  };

  const removeSecondaryLocation = (loc: string) => {
    setFormData((prev) => ({
      ...prev,
      secondaryLocations: prev.secondaryLocations.filter((l) => l !== loc),
    }));
    setIsSaved(false);
  };

  // ── Resume ──────────────────────────────────────────────────────────────────
  const handleResumeUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadedResume(file);
    setIsSaved(false);
    uploadResume.mutate(file);
  };

  const handleViewResume = async () => {
    try {
      const data = await fetchWithAuth<{ url: string }>("/me/resumes/current/download-url", { method: "GET" });
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
    setResumeParseJobId(null);
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
    resumeParseStatus,
    experienceLimitMsg,
    skillLimitMsg,
    educationLimitMsg,
    certificationLimitMsg,
    locationLimitMsg,
    handleSubmit,
    handleChange,
    addExperience,
    removeExperience,
    updateExperience,
    addSkill,
    removeSkill,
    updateSkillLevel,
    addEducation,
    removeEducation,
    updateEducation,
    addCertification,
    removeCertification,
    updateCertification,
    addSecondaryLocation,
    removeSecondaryLocation,
    handleResumeUpload,
    handleViewResume,
    removeUploadedResume,
  };
}
