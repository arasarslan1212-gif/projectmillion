"use client";

import { Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUnreadAlerts } from "@/lib/alerts";
import { useHealth } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useTheme } from "@/lib/store";
import { APP_NAME } from "@/lib/legal";

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
      className="inline-flex size-8 items-center justify-center rounded-md text-ink-2 hover:bg-surface-2"
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
    >
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}

export function SyntheticBanner() {
  const h = useHealth();
  if (!h?.synthetic) return null;
  return (
    <div
      role="note"
      className="no-print border-b border-synthetic/30 bg-synthetic/10 px-4 py-1.5 text-center text-xs font-medium text-synthetic-ink"
    >
      SYNTHETIC TEST DATA: every company, price, analyst and headline shown here is generated for testing and
      is not real. Configure data providers to see real companies.
    </div>
  );
}

export function SiteHeader() {
  const path = usePathname();
  const unread = useUnreadAlerts();
  return (
    <header className="no-print border-b border-line bg-surface">
      <SyntheticBanner />
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2.5">
        <Link href="/" className="text-sm font-bold tracking-tight text-ink">
          {APP_NAME}
          <span className="ml-1.5 hidden font-normal text-muted sm:inline">explainable stock research</span>
        </Link>
        <nav aria-label="Main" className="-mx-1 flex flex-1 items-center gap-0.5 overflow-x-auto">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium text-ink-2 hover:bg-surface-2",
                (n.href === "/" ? path === "/" : path.startsWith(n.href)) && "bg-surface-2 text-ink",
              )}
            >
              {n.label}
              {n.href === "/alerts" && unread > 0 && (
                <span className="ml-1 rounded-full bg-accent-ink px-1.5 py-px text-[10px] font-semibold text-surface">
                  {unread}
                  <span className="sr-only"> unread</span>
                </span>
              )}
            </Link>
          ))}
        </nav>
        <ThemeToggle />
      </div>
    </header>
  );
}
