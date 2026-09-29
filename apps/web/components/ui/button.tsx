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
        "inline-flex min-h-8 items-center justify-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-all duration-150 disabled:pointer-events-none disabled:opacity-50",
        variant === "default" && "bg-accent text-white shadow-card hover:brightness-110",
        variant === "outline" &&
          "border border-line bg-surface text-ink-2 shadow-card hover:border-line-strong hover:text-ink",
        variant === "ghost" && "text-ink-2 hover:bg-surface-2 hover:text-ink",
        variant === "segment" && (active ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"),
        className,
      )}
      aria-pressed={variant === "segment" ? !!active : undefined}
      {...p}
    />
  );
}
