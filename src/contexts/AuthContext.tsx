import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

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
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string, role: 'job-seeker' | 'recruiter') => Promise<void>;
  logout: () => Promise<void>;
  fetchProfile: () => Promise<void>;
  fetchWithAuth: <T = any>(endpoint: string, options?: RequestInit) => Promise<T>;
  fetchProfileData?: () => Promise<{ profileData?: ProfileData } | null>;
  saveProfileData?: (profileData: ProfileData) => Promise<{ profileData?: ProfileData } | null>;

  updateProfile?: (updates: Partial<User>) => void;
  updateProfileData?: (profileData: ProfileData) => void;
}


const AuthContext = createContext<AuthContextType | undefined>(undefined);

// const API_URL = "http://127.0.0.1:5000/api";
const API_URL = "http://localhost:5000/api";

const getCookie = (name: string): string | null => {
  const match = document.cookie.match(
    new RegExp('(^|;\\s*)' + name + '=([^;]*)')
  );
  return match ? decodeURIComponent(match[2]) : null;
};


export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  // Restore session automatically using secure cookies
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_URL}/profile`, {
          method: "GET",
          credentials: "include",
        });

        if (res.ok) {
          const data = await res.json();
          setUser(data as User);
        } else {
          setUser(null);
        }
      } catch {
        setUser(null);
      }
      const csrf = getCookie("csrf_access_token");
      if (csrf) {
        setCsrfToken(csrf);
      }
      setLoading(false);
    })();
  }, []);

  
  const fetchWithAuth = async <T = any>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> => {
    const method = (options.method || "GET").toUpperCase();

    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };

    // attach CSRF token for state-changing requests
    if (csrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      (headers as any)["X-CSRF-TOKEN"] = csrfToken;
    }

    const res = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers,
      credentials: "include",
    });

    const data = await res.json().catch(() => null);

    if (!res.ok) {
      throw new Error(data?.error || data?.message || "Request failed");
    }

    return data as T;
  };


  // LOGIN — backend sets an HttpOnly JWT cookie
  const login = async (email: string, password: string) => {
    const res = await fetch(`${API_URL}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "Login failed");
    }

    // The backend sets a secure cookie — we only store the user object
    setUser(data.user as User);

    const csrf = getCookie("csrf_access_token");
    if (csrf) {
      setCsrfToken(csrf);
    }
  };

  // REGISTER — then user logs in normally
  const register = async (email: string, password: string, name: string, role: 'job-seeker' | 'recruiter') => {
    const res = await fetch(`${API_URL}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password, name, role }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Registration failed");
  };

  // LOGOUT — clears cookie on backend
  const logout = async () => {
    try {
      await fetchWithAuth("/logout", { method: "POST" });
    } catch (e) {
      console.error(e);
    } finally {
      setUser(null);
    }
  };


  const fetchProfile = async () => {
    const data = await fetchWithAuth<User>("/profile", { method: "GET" });
    setUser(data);
  };

  const fetchProfileData = async () => {
    const data = await fetchWithAuth<{ profileData?: ProfileData }>("/profile", { method: "GET" });
    return { profileData: data.profileData };
  };

  const saveProfileData = async (profileData: ProfileData) => {
    return await fetchWithAuth<{ profileData?: ProfileData }>("/profile", {
      method: "POST",
      body: JSON.stringify({ profileData }),
    });
  };
  const updateProfile = (updates: Partial<User>) => {
    setUser((prev) => (prev ? { ...prev, ...updates } : prev));
  };

  const updateProfileData = (profileData: ProfileData) => {
    setUser((prev) =>
      prev ? { ...prev, profileData: { ...(prev.profileData || {}), ...profileData } } : prev
    );
  };


  const value = {
    user,
    login,
    register,
    logout,
    fetchProfile,
    fetchWithAuth,
    fetchProfileData,
    saveProfileData,
    updateProfile,
    updateProfileData,
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
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
