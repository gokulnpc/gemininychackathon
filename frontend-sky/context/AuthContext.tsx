"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import {
  User,
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
} from "firebase/auth";
import { auth, googleProvider } from "@/lib/firebase";
import apiClient from "@/lib/apiClient";

export interface UserProfile {
  uid: string;
  email: string | null;
  display_name: string | null;
  photo_url: string | null;
  credits: number;
  created_at: string | null;
  last_seen_at: string | null;
}

interface AuthContextValue {
  user: User | null;
  idToken: string | null;
  userProfile: UserProfile | null;
  credits: number;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [idToken, setIdToken] = useState<string | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = useCallback(async () => {
    try {
      const res = await apiClient.get("/api/v1/users/me");
      setUserProfile(res.data);
    } catch {
      // Non-fatal — profile may not be provisioned yet
    }
  }, []);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      setUser(firebaseUser);
      if (firebaseUser) {
        const token = await firebaseUser.getIdToken();
        setIdToken(token);
        document.cookie = `firebase_token=${token}; path=/; max-age=3600; SameSite=Strict`;
        // Fetch real profile + credits after sign-in
        await fetchProfile();
      } else {
        setIdToken(null);
        setUserProfile(null);
        document.cookie = "firebase_token=; path=/; max-age=0";
      }
      setLoading(false);
    });
    return unsubscribe;
  }, [fetchProfile]);

  const signInWithGoogle = async () => {
    await signInWithPopup(auth, googleProvider);
  };

  const signOut = async () => {
    await firebaseSignOut(auth);
  };

  return (
    <AuthContext.Provider value={{
      user,
      idToken,
      userProfile,
      credits: userProfile?.credits ?? 0,
      loading,
      signInWithGoogle,
      signOut,
      refreshProfile: fetchProfile,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
