"use client";

import * as T from "@radix-ui/react-tabs";
import { cn } from "@/lib/cn";
import type { ComponentProps } from "react";

export const Tabs = T.Root;

export function TabsList({ className, ...p }: ComponentProps<typeof T.List>) {
  return <T.List className={cn("flex flex-wrap gap-1 border-b border-line", className)} {...p} />;
}

export function TabsTrigger({ className, ...p }: ComponentProps<typeof T.Trigger>) {
  return (
    <T.Trigger
      className={cn(
        "-mb-px border-b-2 border-transparent px-2.5 py-1.5 text-xs font-medium text-ink-2 hover:text-ink data-[state=active]:border-accent data-[state=active]:text-ink",
        className,
      )}
      {...p}
    />
  );
}

export function TabsContent({ className, ...p }: ComponentProps<typeof T.Content>) {
  return <T.Content className={cn("pt-3 outline-none", className)} {...p} />;
}
