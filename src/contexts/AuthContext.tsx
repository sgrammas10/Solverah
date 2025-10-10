import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface User {
  id: string;
  email: string;
  name: string;
  role: 'job-seeker' | 'recruiter';
  profileComplete: boolean;
  profileData?: any;
}

interface AuthContextType {
  user: User | null;
  login: (email: string, password: string, role: 'job-seeker' | 'recruiter') => Promise<void>;
  register: (email: string, password: string, name: string, role: 'job-seeker' | 'recruiter') => Promise<void>;
  logout: () => void;
  updateProfile: (updates: Partial<User>) => void;
  updateProfileData: (profileData: any) => void;
  fetchWithAuth: (endpoint: string, options?: RequestInit) => Promise<any>;
  getProfile: () => Promise<void>; // 🔹 new function
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
  const fetchWithAuth = async (endpoint: string, options: RequestInit = {}) => {
    const token = localStorage.getItem("token");
    const headers = {
      ...(options.headers || {}),
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    };

    const res = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers
    });

    if (!res.ok) {
      throw new Error(`API error: ${res.status}`);
    }

    return res.json();
  };

  const login = async (email: string, password: string, role: 'job-seeker' | 'recruiter') => {
    const data = await fetchWithAuth("/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });

    setUser(data.user);
    localStorage.setItem("user", JSON.stringify(data.user));
    localStorage.setItem("token", data.token);
  };

  const register = async (email: string, password: string, name: string, role: 'job-seeker' | 'recruiter') => {
    const data = await fetchWithAuth("/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name, role })
    });

    setUser(data.user);
    localStorage.setItem("user", JSON.stringify(data.user));
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

  const updateProfileData = (profileData: any) => {
    if (user) {
      const updatedUser = { ...user, profileData, profileComplete: true };
      setUser(updatedUser);
      localStorage.setItem('user', JSON.stringify(updatedUser));
    }
  };

  //refresh logged-in user’s profile from backend
  const getProfile = async () => {
    const data = await fetchWithAuth("/profile", { method: "GET" });
    setUser(data);
    localStorage.setItem("user", JSON.stringify(data));
  };


// Fetch full profile (including profileData)
const fetchProfileData = async () => {
  const data = await fetchWithAuth("/profile", { method: "GET" });
  if (data?.profileData) {
    setUser((prevUser) => (prevUser ? { ...prevUser, profileData: data.profileData } : null));
    localStorage.setItem("user", JSON.stringify({ ...user, profileData: data.profileData }));
  }
  return data;
};

// Save profileData to backend
const saveProfileData = async (profileData: any) => {
  const res = await fetchWithAuth("/profile", {
    method: "POST",
    body: JSON.stringify({ profileData }),
  });

  if (res?.profileData) {
    setUser((prevUser) => (prevUser ? { ...prevUser, profileData: res.profileData } : null));
    localStorage.setItem("user", JSON.stringify({ ...user, profileData: res.profileData }));
  }
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
