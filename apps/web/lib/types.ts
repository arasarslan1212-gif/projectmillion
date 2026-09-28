// Shapes returned by the engine. The web never computes numbers; it formats Metric values.

export type Unit =
  | "usd"
  | "usd_per_share"
  | "pct"
  | "pct_points"
  | "ratio"
  | "x"
  | "count"
  | "score"
  | "days"
  | "years"
  | "text"
  | "date"
  | "shares"
  | "prob";

export interface Metric {
  id: string;
  label: string;
  value: number | string | null;
  unit: Unit;
  status: "ok" | "insufficient_data";
  reason: string | null;
  source: string | null;
  as_of: string | null;
  def: string;
  note?: string;
  [key: string]: unknown;
}

export interface SourceMeta {
  name: string;
  source: string;
  fetched_at: string | null;
  status: "ok" | "stale" | "missing";
  reason: string | null;
}

export interface SectionBase {
  section: string;
  status: "ok" | "missing" | "error" | "partial";
  reason: string | null;
  sources: SourceMeta[];
  ticker?: string;
  generated_at?: string;
  engine_version?: string;
  config_hash?: string;
  timing_ms?: number;
}

export interface Health {
  status: string;
  engine_version: string;
  config_hash: string;
  data_mode: string;
  fixture_set: string | null;
  synthetic: boolean;
  data_tier: string;
  llm_enabled: boolean;
  today: string;
  providers: Record<string, string>;
}

export interface SearchResult {
  ticker: string;
  name: string;
  exchange: string | null;
}

export interface Definition {
  label?: string;
  definition: string;
  formula?: string;
  interpretation?: string;
  plain?: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type AnySection = SectionBase & Record<string, any>;
