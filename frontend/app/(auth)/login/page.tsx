"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "framer-motion";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useAuth } from "@/components/providers/AuthProvider";
import { useToast } from "@/components/providers/ToastProvider";
import { FairSwarmLogo } from "@/components/ui/FairSwarmLogo";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { authApi, normalizeApiError } from "@/lib/api";
import { getSupabaseClient } from "@/lib/supabase";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { setApiAuth } = useAuth();
  const { notify } = useToast();

  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const handleForgotPassword = async () => {
    const email = form.getValues("email");
    if (!email) {
      notify({ title: "Email required", description: "Enter your email first.", variant: "info" });
      return;
    }

    let supabase;
    try {
      supabase = getSupabaseClient();
    } catch (error) {
      notify({ title: "Supabase not configured", description: normalizeApiError(error), variant: "error" });
      return;
    }

    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/login`,
    });

    if (error) {
      notify({ title: "Reset failed", description: error.message, variant: "error" });
      return;
    }

    notify({ title: "Reset email sent", description: "Check your inbox for reset instructions.", variant: "success" });
  };

  const onSubmit = form.handleSubmit(async (values) => {
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const response = await authApi.login(values);
      const payload = response.data as {
        access_token: string;
        csrf_token?: string;
        user?: { id: string; email: string; full_name?: string | null; organization?: string | null };
      };

      setApiAuth({
        accessToken: payload.access_token,
        csrfToken: payload.csrf_token,
        user: payload.user,
      });

      notify({ title: "Welcome back", description: "Redirecting to dashboard.", variant: "success" });
      router.push("/dashboard");
    } catch (error) {
      const message = normalizeApiError(error);
      setGeneralError(message);
      notify({ title: "Login failed", description: message, variant: "error" });
    } finally {
      setIsSubmitting(false);
    }
  });

  return (
    <div className="grid min-h-screen place-items-center px-4 py-10">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="w-full max-w-md"
      >
        <Card className="space-y-6 p-6 sm:p-8">
          <FairSwarmLogo size="lg" />

          <div>
            <h1 className="text-3xl font-semibold text-white">Sign In</h1>
            <p className="mt-1 text-sm text-slate-400">Continue to your fairness command center.</p>
          </div>

          <form className="space-y-4" onSubmit={onSubmit}>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-[0.14em] text-slate-400">Email</label>
              <input
                {...form.register("email")}
                type="email"
                className="h-11 w-full rounded-md border border-border bg-surface px-3 text-white outline-none focus:border-primary"
                placeholder="you@example.com"
              />
              {form.formState.errors.email ? (
                <p className="mt-1 text-xs text-danger">{form.formState.errors.email.message}</p>
              ) : null}
            </div>

            <div>
              <label className="mb-1 block text-xs uppercase tracking-[0.14em] text-slate-400">Password</label>
              <div className="relative">
                <input
                  {...form.register("password")}
                  type={showPassword ? "text" : "password"}
                  className="h-11 w-full rounded-md border border-border bg-surface px-3 pr-11 text-white outline-none focus:border-primary"
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {form.formState.errors.password ? (
                <p className="mt-1 text-xs text-danger">{form.formState.errors.password.message}</p>
              ) : null}
            </div>

            <div className="flex items-center justify-between text-sm">
              <button type="button" onClick={handleForgotPassword} className="text-secondary hover:text-primary">
                Forgot password?
              </button>
              <Link href="/register" className="text-slate-300 hover:text-white">
                Create account
              </Link>
            </div>

            {generalError ? <p className="text-sm text-danger">{generalError}</p> : null}

            <Button className="w-full" type="submit" disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Sign In"}
            </Button>
          </form>
        </Card>
      </motion.div>
    </div>
  );
}
