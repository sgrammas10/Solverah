import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

// Stronger typing for profile data stored in the DB/localStorage
export type ProfileData = Record<string, unknown> & {
  quizResults?: Record<string, unknown>;
  _quizSummary?: Record<string, unknown>;
};

interface User {
  id: string;
  email: string;
  name: string;
  role: 'job-seeker' | 'recruiter';
  profileComplete: boolean;
  profileData?: ProfileData;
}

interface AuthContextType {
  user: User | null;
  login: (email: string, password: string, role: 'job-seeker' | 'recruiter') => Promise<void>;
  register: (email: string, password: string, name: string, role: 'job-seeker' | 'recruiter') => Promise<void>;
  logout: () => void;
  updateProfile: (updates: Partial<User>) => void;
  updateProfileData: (profileData: ProfileData) => void;
  fetchWithAuth: <T = Record<string, unknown>>(endpoint: string, options?: RequestInit) => Promise<T>;
  getProfile: () => Promise<void>; // 🔹 new function
  fetchProfileData?: () => Promise<{ profileData?: ProfileData } | null>;
  saveProfileData?: (profileData: ProfileData) => Promise<{ profileData?: ProfileData } | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_URL = "http://127.0.0.1:5000/api"; // Flask backend base URL, will adapt when we get a fully running one

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Restore user + token from localStorage if available
    const savedUser = localStorage.getItem('user');
    const token = localStorage.getItem('token');
    if (savedUser && token) {
      setUser(JSON.parse(savedUser));
    }
    setLoading(false);
  }, []);

  // Centralized fetch helper that attaches JWT if present
  const fetchWithAuth = async <T = Record<string, unknown>>(endpoint: string, options: RequestInit = {}): Promise<T> => {
    const token = localStorage.getItem("token");
    const headers = {
      ...(options.headers || {}),
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    };

    const res = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers,
    });

    if (!res.ok) {
      throw new Error(`API error: ${res.status}`);
    }

    const json = await res.json();
    return json as T;
  };

  const login = async (email: string, password: string, _role: 'job-seeker' | 'recruiter') => {
    const data = await fetchWithAuth<{ user: User; token?: string }>("/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    // mark _role as intentionally unused for linters
    void _role;

    const typed = data as { user: User; token?: string };
    setUser(typed.user);
    localStorage.setItem("user", JSON.stringify(typed.user));
    if (typed.token) localStorage.setItem("token", typed.token);
  };

  const register = async (email: string, password: string, name: string, role: 'job-seeker' | 'recruiter') => {
    const data = await fetchWithAuth<{ user: User }>("/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name, role }),
    });

    const typed = data as { user: User };
    setUser(typed.user);
    localStorage.setItem("user", JSON.stringify(typed.user));
    // Note: register doesn’t return token — user logs in after registration
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem("user");
    localStorage.removeItem("token");
  };

  const updateProfile = (updates: Partial<User>) => {
    if (user) {
      const updatedUser = { ...user, ...updates };
      setUser(updatedUser);
      localStorage.setItem('user', JSON.stringify(updatedUser));
    }
  };

  const updateProfileData = (profileData: ProfileData) => {
    if (user) {
      const updatedUser = { ...user, profileData, profileComplete: true };
      setUser(updatedUser);
      localStorage.setItem('user', JSON.stringify(updatedUser));
    }
  };

  //refresh logged-in user’s profile from backend
  const getProfile = async () => {
    const data = await fetchWithAuth<{ id?: number; email?: string; name?: string; role?: string; profileData?: ProfileData }>("/profile", { method: "GET" });
    // backend returns full user-like object; cast to User where appropriate
    setUser(data as unknown as User);
    localStorage.setItem("user", JSON.stringify(data));
  };


// Fetch full profile (including profileData)
const fetchProfileData = async (): Promise<{ profileData?: ProfileData } | null> => {
  const data = await fetchWithAuth<{ id?: number; email?: string; name?: string; role?: string; profileData?: ProfileData }>("/profile", { method: "GET" });
  if (data?.profileData) {
    setUser((prevUser) => (prevUser ? { ...prevUser, profileData: data.profileData } : null));
    localStorage.setItem("user", JSON.stringify({ ...user, profileData: data.profileData }));
  }
  return data;
};

// Save profileData to backend
const saveProfileData = async (profileData: ProfileData): Promise<{ profileData?: ProfileData } | null> => {
  const res = await fetchWithAuth<{ profileData?: ProfileData }>("/profile", {
    method: "POST",
    body: JSON.stringify({ profileData }),
  });

  if (res?.profileData) {
    setUser((prevUser) => (prevUser ? { ...prevUser, profileData: res.profileData } : null));
    localStorage.setItem("user", JSON.stringify({ ...user, profileData: res.profileData }));
  }

  return res ?? null;
};



  const value = {
    user,
    login,
    register,
    logout,
    updateProfile,
    updateProfileData,
    fetchWithAuth,
    getProfile,
    fetchProfileData,
    saveProfileData  
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
