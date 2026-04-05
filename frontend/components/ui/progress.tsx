import * as Progress from "@radix-ui/react-progress";

import { cn } from "@/lib/utils";

type ProgressBarProps = {
  value: number;
  className?: string;
};

export function ProgressBar({ value, className }: ProgressBarProps) {
  return (
    <Progress.Root
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-surface", className)}
      value={value}
    >
      <Progress.Indicator
        className="h-full bg-primary transition-transform duration-300"
        style={{ transform: `translateX(-${100 - Math.max(0, Math.min(value, 100))}%)` }}
      />
    </Progress.Root>
  );
}
