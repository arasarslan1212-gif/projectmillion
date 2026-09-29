"use client";

import * as T from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <T.Provider delayDuration={150} skipDelayDuration={300}>
      {children}
    </T.Provider>
  );
}

/** Accessible tooltip: opens on hover and on keyboard focus of the trigger. */
export function Tip({
  content,
  children,
  side = "top",
}: {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content
          side={side}
          sideOffset={6}
          collisionPadding={12}
          className="z-50 max-w-xs rounded-xl border border-line bg-surface px-3 py-2 text-xs leading-relaxed text-ink shadow-pop"
        >
          {content}
          <T.Arrow className="fill-surface" />
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
