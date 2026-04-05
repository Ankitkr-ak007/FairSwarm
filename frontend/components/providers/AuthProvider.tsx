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

import { getSupabaseClient } from "@/lib/supabase";
import type { UserProfile } from "@/types";

type AuthContextValue = {
  supabaseUser: User | null;
  profile: UserProfile | null;
  accessToken: string | null;
  csrfToken: string | null;
  isLoading: boolean;
  setApiAuth: (payload: {
    accessToken: string;
    csrfToken?: string;
    user?: UserProfile | null;
  }) => void;
  clearApiAuth: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const ACCESS_TOKEN_KEY = "fairswarm_access_token";
const CSRF_TOKEN_KEY = "fairswarm_csrf_token";
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

    const storedToken = localStorage.getItem(ACCESS_TOKEN_KEY);
    const storedCsrf = localStorage.getItem(CSRF_TOKEN_KEY);
    const storedUser = localStorage.getItem(USER_KEY);

    setAccessToken(storedToken);
    setCsrfToken(storedCsrf);

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
      setIsLoading(false);
    }

    return () => {
      subscription?.unsubscribe();
    };
  }, []);

  const setApiAuth = (payload: {
    accessToken: string;
    csrfToken?: string;
    user?: UserProfile | null;
  }) => {
    setAccessToken(payload.accessToken);
    localStorage.setItem(ACCESS_TOKEN_KEY, payload.accessToken);

    if (payload.csrfToken) {
      setCsrfToken(payload.csrfToken);
      localStorage.setItem(CSRF_TOKEN_KEY, payload.csrfToken);
    }

    if (payload.user) {
      setProfile(payload.user);
      localStorage.setItem(USER_KEY, JSON.stringify(payload.user));
    }
  };

  const clearApiAuth = () => {
    setAccessToken(null);
    setCsrfToken(null);
    setProfile(null);
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(CSRF_TOKEN_KEY);
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
