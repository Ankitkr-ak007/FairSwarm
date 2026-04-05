"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { User } from "@supabase/supabase-js";

import { authApi } from "@/lib/api";
import { getSupabaseClient } from "@/lib/supabase";
import type { UserProfile } from "@/types";

type AuthContextValue = {
  supabaseUser: User | null;
  profile: UserProfile | null;
  accessToken: string | null;
  csrfToken: string | null;
  isLoading: boolean;
  setApiAuth: (payload: {
    accessToken?: string;
    csrfToken?: string;
    user?: UserProfile | null;
  }) => void;
  clearApiAuth: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const USER_KEY = "fairswarm_user";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [supabaseUser, setSupabaseUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    if (typeof window === "undefined") {
      setIsLoading(false);
      return;
    }

    const storedUser = localStorage.getItem(USER_KEY);

    setAccessToken(null);
    setCsrfToken(null);

    if (storedUser) {
      try {
        setProfile(JSON.parse(storedUser) as UserProfile);
      } catch {
        localStorage.removeItem(USER_KEY);
      }
    }

    let subscription: { unsubscribe: () => void } | undefined;

    try {
      const supabase = getSupabaseClient();

      supabase.auth.getUser().then(({ data }) => {
        setSupabaseUser(data.user ?? null);
        setIsLoading(false);
      });

      subscription = supabase.auth.onAuthStateChange((_event, session) => {
        setSupabaseUser(session?.user ?? null);
      }).data.subscription;
    } catch {
      // Supabase auth is optional for core app auth.
    }

    authApi
      .me()
      .then((response) => {
        const user = response.data.user as UserProfile | undefined;
        if (user) {
          setProfile(user);
          localStorage.setItem(USER_KEY, JSON.stringify(user));
        }
      })
      .finally(() => setIsLoading(false));

    return () => {
      subscription?.unsubscribe();
    };
  }, []);

  const setApiAuth = (payload: {
    accessToken?: string;
    csrfToken?: string;
    user?: UserProfile | null;
  }) => {
    setAccessToken(null);
    setCsrfToken(null);

    if (payload.user) {
      setProfile(payload.user);
      localStorage.setItem(USER_KEY, JSON.stringify(payload.user));
    }
  };

  const clearApiAuth = () => {
    setAccessToken(null);
    setCsrfToken(null);
    setProfile(null);
    localStorage.removeItem(USER_KEY);
  };

  const value = useMemo<AuthContextValue>(
    () => ({
      supabaseUser,
      profile,
      accessToken,
      csrfToken,
      isLoading,
      setApiAuth,
      clearApiAuth,
    }),
    [supabaseUser, profile, accessToken, csrfToken, isLoading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
