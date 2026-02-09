import { createContext } from "react";

export type ProfileData = Record<string, unknown> & {
  quizResults?: Record<string, unknown>;
  _quizSummary?: Record<string, unknown>;
  quizInsights?: Record<string, unknown>;
};

export interface User {
  id: string;
  email: string;
  name: string;
  role: "job-seeker" | "recruiter";
  profileComplete: boolean;
  profileData?: ProfileData;
}

export interface AuthContextType {
  user: User | null;
  login: (email: string, password: string) => Promise<User>;
  register: (email: string, password: string, name: string, role: "job-seeker" | "recruiter") => Promise<void>;
  logout: () => Promise<void>;
  fetchProfile: () => Promise<void>;
  fetchWithAuth: <T = any>(endpoint: string, options?: RequestInit) => Promise<T>;
  fetchProfileData?: () => Promise<{ profileData?: ProfileData } | null>;
  saveProfileData?: (profileData: ProfileData) => Promise<{ profileData?: ProfileData } | null>;
  updateProfile?: (updates: Partial<User>) => void;
  updateProfileData?: (profileData: ProfileData) => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);
