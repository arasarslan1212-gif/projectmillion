import { cn } from "@/lib/cn";
import type { ButtonHTMLAttributes } from "react";

type Variant = "default" | "ghost" | "outline" | "segment";

export function Button({
  variant = "outline",
  active,
  className,
  ...p
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; active?: boolean }) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex min-h-8 items-center justify-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors disabled:opacity-50",
        variant === "default" && "bg-accent text-white hover:bg-accent/90",
        variant === "outline" && "border border-line bg-surface text-ink-2 hover:bg-surface-2",
        variant === "ghost" && "text-ink-2 hover:bg-surface-2",
        variant === "segment" &&
          (active ? "bg-accent-wash text-accent-ink" : "text-ink-2 hover:bg-surface-2"),
        className,
      )}
      aria-pressed={variant === "segment" ? !!active : undefined}
      {...p}
    />
  );
}
