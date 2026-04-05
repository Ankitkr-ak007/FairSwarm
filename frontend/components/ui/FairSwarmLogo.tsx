import { cn } from "@/lib/utils";

type FairSwarmLogoProps = {
  className?: string;
  size?: "sm" | "md" | "lg";
};

const sizes = {
  sm: "h-9 w-9 text-sm",
  md: "h-11 w-11 text-base",
  lg: "h-14 w-14 text-lg",
};

export function FairSwarmLogo({ className, size = "md" }: FairSwarmLogoProps) {
  return (
    <div className={cn("inline-flex items-center gap-3", className)}>
      <div
        className={cn(
          "grid place-items-center rounded-md border border-primary bg-surface font-bold tracking-tight text-primary",
          sizes[size]
        )}
      >
        FS
      </div>
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-secondary">FairSwarm</p>
        <p className="text-xs text-slate-400">Bias Intelligence Platform</p>
      </div>
    </div>
  );
}
