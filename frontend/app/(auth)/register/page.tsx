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

const registerSchema = z
  .object({
    full_name: z.string().min(2, "Name must be at least 2 characters"),
    organization: z.string().optional(),
    email: z.string().email("Enter a valid email address"),
    password: z
      .string()
      .min(8, "Minimum 8 characters")
      .regex(/[A-Z]/, "Must include one uppercase letter")
      .regex(/\d/, "Must include one number")
      .regex(/[^\w\s]/, "Must include one special character"),
    confirmPassword: z.string(),
  })
  .refine((value) => value.password === value.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords do not match",
  });

type RegisterFormValues = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const router = useRouter();
  const { setApiAuth } = useAuth();
  const { notify } = useToast();

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);

  const form = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      full_name: "",
      organization: "",
      email: "",
      password: "",
      confirmPassword: "",
    },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const response = await authApi.register({
        email: values.email,
        password: values.password,
        full_name: values.full_name,
        organization: values.organization,
      });
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
      notify({ title: "Account created", description: "Welcome to FairSwarm.", variant: "success" });
      router.push("/dashboard");
    } catch (error) {
      const message = normalizeApiError(error);
      setGeneralError(message);
      notify({ title: "Registration failed", description: message, variant: "error" });
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
            <h1 className="text-3xl font-semibold text-white">Create Account</h1>
            <p className="mt-1 text-sm text-slate-400">Start bias analysis with the FairSwarm AI swarm.</p>
          </div>

          <form className="space-y-4" onSubmit={onSubmit}>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-[0.14em] text-slate-400">Full Name</label>
              <input
                {...form.register("full_name")}
                className="h-11 w-full rounded-md border border-border bg-surface px-3 text-white outline-none focus:border-primary"
                placeholder="Jane Doe"
              />
              {form.formState.errors.full_name ? (
                <p className="mt-1 text-xs text-danger">{form.formState.errors.full_name.message}</p>
              ) : null}
            </div>

            <div>
              <label className="mb-1 block text-xs uppercase tracking-[0.14em] text-slate-400">Organization</label>
              <input
                {...form.register("organization")}
                className="h-11 w-full rounded-md border border-border bg-surface px-3 text-white outline-none focus:border-primary"
                placeholder="Fairness Lab"
              />
            </div>

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

            <div>
              <label className="mb-1 block text-xs uppercase tracking-[0.14em] text-slate-400">Confirm Password</label>
              <div className="relative">
                <input
                  {...form.register("confirmPassword")}
                  type={showConfirmPassword ? "text" : "password"}
                  className="h-11 w-full rounded-md border border-border bg-surface px-3 pr-11 text-white outline-none focus:border-primary"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword((current) => !current)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
                >
                  {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {form.formState.errors.confirmPassword ? (
                <p className="mt-1 text-xs text-danger">{form.formState.errors.confirmPassword.message}</p>
              ) : null}
            </div>

            {generalError ? <p className="text-sm text-danger">{generalError}</p> : null}

            <Button className="w-full" type="submit" disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create Account"}
            </Button>

            <p className="text-center text-sm text-slate-400">
              Already have an account?{" "}
              <Link href="/login" className="text-secondary hover:text-primary">
                Sign in
              </Link>
            </p>
          </form>
        </Card>
      </motion.div>
    </div>
  );
}
