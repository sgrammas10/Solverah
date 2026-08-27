export interface UploadedResume {
  name: string;
  size: number;
  type: string;
}

/**
 * A resume that has been uploaded to storage but not yet parsed into the profile.
 *
 * `resumeId` replaced `objectKey` in the Phase 1b redesign, and the change is a
 * security improvement rather than a rename. The old finalize endpoint took a
 * caller-supplied storage key and defended itself with a
 * `profile/{your-user-id}/` prefix check -- get that wrong and a caller could
 * name any key in the bucket and have its contents parsed into their own
 * profile, another user's resume included. The server now rebuilds the key from
 * the JWT identity and this id, so there is no key for a client to hold.
 */
export interface PendingResumeUpload {
  resumeId: string;
  mime: string;
  size: number;
  name: string;
}

export interface PsychometricScore {
  score: number | null;
  percentile: number | null;
  completed: boolean;
}

export type SkillLevel = 'beginner' | 'intermediate' | 'advanced';

export interface Certification {
  id: number;
  name: string;
  issuer: string;
  issueDate: string;
  expiryDate: string;
}

export interface ProfileFormData {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  location: string;
  primaryLocation: string;
  secondaryLocations: string[];
  linkedinUrl: string;
  summary: string;
  experience: any[];
  education: any[];
  certifications: Certification[];
  skills: string[];
  skill_levels?: Record<string, SkillLevel>;
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
  career_status?: string;
}
