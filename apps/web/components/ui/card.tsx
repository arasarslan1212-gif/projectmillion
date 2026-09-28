import { cn } from "@/lib/cn";
import type { HTMLAttributes } from "react";

export function Card({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-line bg-surface", className)} {...p} />;
}

export function CardHeader({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex flex-wrap items-start justify-between gap-2 px-4 pt-4 sm:px-5", className)}
      {...p}
    />
  );
}

export function CardTitle({ className, ...p }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-sm font-semibold text-ink", className)} {...p} />;
}

export function CardBody({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-4 pt-3 pb-4 sm:px-5", className)} {...p} />;
}
