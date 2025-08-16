import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface User {
  id: string;
  email: string;
  name: string;
  role: 'job-seeker' | 'recruiter';
  profileComplete: boolean;
}

interface AuthContextType {
  user: User | null;
  login: (email: string, password: string, role: 'job-seeker' | 'recruiter') => Promise<void>;
  register: (email: string, password: string, name: string, role: 'job-seeker' | 'recruiter') => Promise<void>;
  logout: () => void;
  updateProfile: (updates: Partial<User>) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check for saved user in localStorage
    const savedUser = localStorage.getItem('user');
    if (savedUser) {
      setUser(JSON.parse(savedUser));
    }
    setLoading(false);
  }, []);

  const login = async (email: string, password: string, role: 'job-seeker' | 'recruiter') => {
    // Mock authentication - in real app, this would call an API
    const mockUser: User = {
      id: Math.random().toString(36).substr(2, 9),
      email,
      name: email.split('@')[0],
      role,
      profileComplete: false
    };
    
    setUser(mockUser);
    localStorage.setItem('user', JSON.stringify(mockUser));
  };

  const register = async (email: string, password: string, name: string, role: 'job-seeker' | 'recruiter') => {
    // Mock registration - in real app, this would call an API
    const mockUser: User = {
      id: Math.random().toString(36).substr(2, 9),
      email,
      name,
      role,
      profileComplete: false
    };
    
    setUser(mockUser);
    localStorage.setItem('user', JSON.stringify(mockUser));
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('user');
  };

  const updateProfile = (updates: Partial<User>) => {
    if (user) {
      const updatedUser = { ...user, ...updates };
      setUser(updatedUser);
      localStorage.setItem('user', JSON.stringify(updatedUser));
    }
  };

  const value = {
    user,
    login,
    register,
    logout,
    updateProfile
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