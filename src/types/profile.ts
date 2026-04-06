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
  skills: string[];
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
