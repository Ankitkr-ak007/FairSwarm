"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";

import { AuthProvider } from "@/components/providers/AuthProvider";
import { ToastProvider } from "@/components/providers/ToastProvider";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function GlobalRouteLoading() {
  const pathname = usePathname();
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsVisible(true);
    const timer = window.setTimeout(() => setIsVisible(false), 320);
    return () => window.clearTimeout(timer);
  }, [pathname]);

  return (
    <div
      className={
        isVisible
          ? "pointer-events-none fixed left-0 top-0 z-[110] h-0.5 w-full bg-primary opacity-100 transition-opacity"
          : "pointer-events-none fixed left-0 top-0 z-[110] h-0.5 w-full bg-primary opacity-0 transition-opacity"
      }
    />
  );
}

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ToastProvider>
          <GlobalRouteLoading />
          {children}
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
