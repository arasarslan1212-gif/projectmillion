"use client";

import { useEffect, useState } from "react";

export interface ThemeColors {
  dark: boolean;
  surface: string;
  ink: string;
  ink2: string;
  muted: string;
  grid: string;
  axis: string;
  accent: string;
  good: string;
  critical: string;
  warning: string;
  serious: string;
  series: string[];
  synthetic: string;
}

function read(): ThemeColors {
  const cs = getComputedStyle(document.documentElement);
  const v = (n: string) => cs.getPropertyValue(n).trim();
  return {
    dark: document.documentElement.dataset.theme === "dark",
    surface: v("--surface"),
    ink: v("--ink"),
    ink2: v("--ink-2"),
    muted: v("--muted"),
    grid: v("--grid"),
    axis: v("--axis"),
    accent: v("--accent"),
    good: v("--good"),
    critical: v("--critical"),
    warning: v("--warning"),
    serious: v("--serious"),
    series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v(`--s${i}`)),
    synthetic: v("--synthetic"),
  };
}

/** Current theme tokens as concrete colors (canvas charts can't use CSS variables). */
export function useThemeColors(): ThemeColors | null {
  const [c, setC] = useState<ThemeColors | null>(null);
  useEffect(() => {
    const update = () => setC(read());
    update();
    window.addEventListener("themechange", update);
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", update);
    return () => {
      window.removeEventListener("themechange", update);
      mq.removeEventListener("change", update);
    };
  }, []);
  return c;
}

export function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  if (h.length !== 6) return hex;
  const n = parseInt(h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
