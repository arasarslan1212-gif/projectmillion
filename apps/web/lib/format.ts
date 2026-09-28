import type { Metric, Unit } from "./types";

const DASH = "—";

function compact(n: number, digits = 2): string {
  const a = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (a >= 1e12) return `${sign}${(a / 1e12).toFixed(digits)}T`;
  if (a >= 1e9) return `${sign}${(a / 1e9).toFixed(digits)}B`;
  if (a >= 1e6) return `${sign}${(a / 1e6).toFixed(digits)}M`;
  if (a >= 1e4) return `${sign}${(a / 1e3).toFixed(1)}K`;
  return `${sign}${a.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

export function formatValue(
  value: number | string | null | undefined,
  unit: Unit,
  opts: { digits?: number; signed?: boolean } = {},
): string {
  const out = formatRaw(value, unit, opts);
  // a value that rounds to zero carries no sign ("-0.0%" → "0.0%")
  return /^[+-]/.test(out) && !/[1-9]/.test(out) ? out.slice(1) : out;
}

function formatRaw(
  value: number | string | null | undefined,
  unit: Unit,
  opts: { digits?: number; signed?: boolean },
): string {
  if (value === null || value === undefined) return DASH;
  if (typeof value === "string") {
    if (unit === "date") return formatDate(value);
    return value;
  }
  if (!Number.isFinite(value)) return DASH;
  const d = opts.digits;
  const sign = opts.signed && value > 0 ? "+" : "";
  switch (unit) {
    case "usd":
      return `${sign}${value < 0 ? "-" : ""}$${compact(Math.abs(value), d ?? 2)}`;
    case "usd_per_share": {
      const digits = d ?? (Math.abs(value) >= 1000 ? 0 : 2);
      const s = Math.abs(value).toLocaleString("en-US", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
      return `${sign}${value < 0 ? "-" : ""}$${s}`;
    }
    case "pct":
      return `${sign}${(value * 100).toFixed(d ?? 1)}%`;
    case "prob": {
      // A model probability is never shown as certain: round-trips to 0% or 100% become "<" / ">".
      const digits = d ?? 1;
      const edge = 0.5 * 10 ** -(digits + 2);
      if (value >= 1 - edge) return `>${(100 - 10 ** -digits).toFixed(digits)}%`;
      if (value < edge) return `<${(10 ** -digits).toFixed(digits)}%`;
      return `${sign}${(value * 100).toFixed(digits)}%`;
    }
    case "pct_points":
      return `${sign}${value.toFixed(d ?? 1)} pp`;
    case "x":
      return `${sign}${value.toFixed(d ?? 1)}×`;
    case "ratio":
      return `${sign}${value.toFixed(d ?? 2)}`;
    case "score":
      return `${sign}${value.toFixed(d ?? 0)}`;
    case "shares":
    case "count":
      return `${sign}${compact(value, d ?? 2)}`;
    case "days":
      return `${sign}${value.toFixed(d ?? 1)} days`;
    case "years":
      return `${sign}${value.toFixed(d ?? 1)} yrs`;
    default:
      return `${sign}${value.toLocaleString("en-US", { maximumFractionDigits: d ?? 2 })}`;
  }
}

export function formatMetric(
  m: Metric | null | undefined,
  opts: { digits?: number; signed?: boolean } = {},
): string {
  if (!m) return DASH;
  return formatValue(m.value, m.unit, opts);
}

export function formatDate(s: string | null | undefined): string {
  if (!s) return DASH;
  const d = new Date(s.length === 10 ? `${s}T12:00:00Z` : s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
}

export function formatDateTime(s: string | null | undefined): string {
  if (!s) return DASH;
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Direction of a signed number for coloring: up / down / flat. */
export function direction(v: number | null | undefined): "up" | "down" | "flat" {
  if (v === null || v === undefined || !Number.isFinite(v) || v === 0) return "flat";
  return v > 0 ? "up" : "down";
}

export function gradeColor(grade: string | null | undefined): string {
  if (!grade) return "text-muted";
  if (grade.startsWith("A")) return "text-good-ink";
  if (grade.startsWith("B")) return "text-accent-ink";
  if (grade.startsWith("C")) return "text-warning-ink";
  return "text-critical-ink";
}
