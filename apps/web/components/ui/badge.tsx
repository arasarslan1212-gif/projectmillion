import { cn } from "@/lib/cn";
import type { HTMLAttributes } from "react";

type Tone = "neutral" | "accent" | "good" | "warning" | "critical" | "synthetic";

const tones: Record<Tone, string> = {
  neutral: "border-line bg-surface-2 text-ink-2",
  accent: "border-transparent bg-accent-wash text-accent-ink",
  good: "border-transparent bg-good/12 text-good-ink",
  warning: "border-transparent bg-warning/18 text-warning-ink",
  critical: "border-transparent bg-critical/12 text-critical-ink",
  synthetic: "border-transparent bg-synthetic/15 text-synthetic-ink",
};

export function Badge({
  tone = "neutral",
  className,
  ...p
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
      {...p}
    />
  );
}
