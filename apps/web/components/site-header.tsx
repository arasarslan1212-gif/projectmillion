"use client";

import { Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUnreadAlerts } from "@/lib/alerts";
import { cn } from "@/lib/cn";
import { useTheme } from "@/lib/store";
import { APP_NAME } from "@/lib/legal";
import { StatusBar } from "@/components/engine-banner";

const NAV = [
  { href: "/", label: "Search" },
  { href: "/compare", label: "Compare" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/alerts", label: "Alerts" },
  { href: "/track-record", label: "Track record" },
  { href: "/methodology", label: "Methodology" },
  { href: "/glossary", label: "Glossary" },
];

function ThemeToggle() {
  const theme = useTheme();
  const flip = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* storage unavailable */
    }
    window.dispatchEvent(new Event("themechange"));
  };
  return (
    <button
      type="button"
      onClick={flip}
      className="inline-flex size-9 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-ink"
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
    >
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}

/** The app's mark: an ascending line in a rounded square (also app/icon.svg). */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <defs>
        <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#logo-g)" />
      <path
        d="M8 21.5l5.5-5.5 4 4L24 13.5"
        fill="none"
        stroke="#fff"
        strokeWidth="2.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function SiteHeader() {
  const path = usePathname();
  const unread = useUnreadAlerts();
  return (
    <>
      <StatusBar />
      <header className="no-print sticky top-0 z-40 border-b border-line bg-page/75 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-5 px-4">
          <Link
            href="/"
            className="flex shrink-0 items-center gap-2 rounded-lg"
            aria-label={`${APP_NAME} home`}
          >
            <LogoMark className="size-7" />
            <span className="text-[15px] font-semibold tracking-tight text-ink">{APP_NAME}</span>
          </Link>
          <nav
            aria-label="Main"
            className="-mx-1 flex flex-1 items-center gap-0.5 overflow-x-auto [mask-image:linear-gradient(to_right,black_85%,transparent)] md:[mask-image:none]"
          >
            {NAV.map((n) => {
              const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "inline-flex items-center whitespace-nowrap rounded-full px-3 py-1.5 text-[13px] font-medium text-muted transition-colors hover:text-ink",
                    active && "bg-surface text-ink shadow-card ring-1 ring-line",
                  )}
                >
                  {n.label}
                  {n.href === "/alerts" && unread > 0 && (
                    <span className="ml-1.5 rounded-full bg-accent-ink px-1.5 py-px text-[10px] font-semibold text-surface">
                      {unread}
                      <span className="sr-only"> unread</span>
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
          <ThemeToggle />
        </div>
      </header>
    </>
  );
}
