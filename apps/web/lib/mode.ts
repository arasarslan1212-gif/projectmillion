"use client";

import { useStored } from "./store";

/** The global reading mode: "plain" for newcomers, "analyst" for full detail. Shared by every component and tab. */
export type ReadingMode = "plain" | "analyst";

export const MODE_OPTIONS: { value: ReadingMode; label: string }[] = [
  { value: "plain", label: "Plain" },
  { value: "analyst", label: "Analyst" },
];

export function useReadingMode(): [ReadingMode, (m: ReadingMode) => void] {
  const [mode, setMode] = useStored<ReadingMode>("reading-mode", "plain");
  return [mode === "analyst" ? "analyst" : "plain", setMode];
}
