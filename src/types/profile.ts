export interface UploadedResume {
  name: string;
  size: number;
  type: string;
}

export interface PendingResumeUpload {
  objectKey: string;
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
