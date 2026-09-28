"""Track-record statistics over scored snapshots. Pure functions of a DataFrame from `outcomes_frame`.

Every rate comes with its sample size and, for proportions, a 95% Wilson interval, so small samples read as
uncertain rather than as precise claims.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

Z80 = float(norm.ppf(0.9))  # half-width of the 80% band in standard deviations


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def _f(x) -> float | None:
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else float(x)


def summary(df: pd.DataFrame) -> dict:
    """Headline grades: range coverage, P50 error, direction hit rate, Brier score and its skill."""
    n = len(df)
    if n == 0:
        return {"n": 0}
    inb = int(df["in_band"].sum())
    pred_up = df["p50"] > df["price"]
    hits = int((pred_up == df["realized_up"]).sum())
    out = {
        "n": n,
        "tickers": int(df["ticker"].nunique()),
        "first": str(df["as_of"].min()),
        "last": str(df["as_of"].max()),
        "coverage": inb / n,
        "coverage_ci": wilson(inb, n),
        "coverage_target": 0.8,
        "above_p90": float((df["realized_price"] > df["p90"]).mean()),
        "below_p10": float((df["realized_price"] < df["p10"]).mean()),
        "median_abs_err": float(df["abs_pct_err"].median()),
        "mean_abs_err": float(df["abs_pct_err"].mean()),
        "direction_hit_rate": hits / n,
        "direction_hit_ci": wilson(hits, n),
        "realized_up_share": float(df["realized_up"].mean()),
        "mean_realized_return": float(df["realized_return"].mean()),
        "mean_implied_return": float((df["p50"] / df["price"] - 1).mean()),
    }
    b = df.dropna(subset=["brier", "prob_up"])
    if len(b):
        base = float(b["realized_up"].mean())
        ref = float(((base - b["realized_up"].astype(float)) ** 2).mean())
        brier = float(b["brier"].mean())
        out.update(
            {"brier": brier, "brier_reference": ref, "brier_skill": (1 - brier / ref) if ref > 0 else None}
        )
    return out


def reliability(df: pd.DataFrame, bins: int = 10) -> list[dict]:
    """Calibration curve for prob_up: mean forecast vs. observed frequency per equal-width bin."""
    d = df.dropna(subset=["prob_up"])
    if d.empty:
        return []
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(d["prob_up"], edges[1:-1]), 0, bins - 1)
    out = []
    for i in range(bins):
        g = d[idx == i]
        if len(g) == 0:
            continue
        k = int(g["realized_up"].sum())
        out.append({
            "lo": float(edges[i]), "hi": float(edges[i + 1]), "n": len(g),
            "forecast": float(g["prob_up"].mean()), "observed": k / len(g), "ci": wilson(k, len(g)),
        })  # fmt: skip
    return out


def z_scores(df: pd.DataFrame) -> np.ndarray:
    """Where each realized price fell in its forecast distribution, in standard deviations from P50."""
    sigma = np.log(df["p90"] / df["p50"]) / Z80
    return (np.log(df["realized_price"] / df["p50"]) / sigma).to_numpy(float)


def interval_coverage(df: pd.DataFrame, levels: list[float]) -> list[dict]:
    """Nominal vs. actual coverage of central intervals (the 80% row is the P10–P90 band)."""
    if df.empty:
        return []
    z = np.abs(z_scores(df))
    n = len(z)
    out = []
    for c in levels:
        k = int((z <= norm.ppf(0.5 + c / 2)).sum())
        out.append({"nominal": c, "actual": k / n, "n": n, "ci": wilson(k, n)})
    return out


def pit_histogram(df: pd.DataFrame, bins: int = 10) -> list[dict]:
    """Histogram of the probability integral transform: flat if the distribution is calibrated."""
    if df.empty:
        return []
    u = norm.cdf(z_scores(df))
    counts, edges = np.histogram(u, bins=bins, range=(0, 1))
    return [
        {"lo": float(edges[i]), "hi": float(edges[i + 1]), "share": float(counts[i] / len(u))}
        for i in range(bins)
    ]


def by_group(df: pd.DataFrame, key: str, min_n: int = 1) -> list[dict]:
    out = []
    for g, sub in df.groupby(key, dropna=True):
        if len(sub) >= min_n:
            s = summary(sub)
            out.append({"group": str(g), **{k: s.get(k) for k in (
                "n", "coverage", "coverage_ci", "median_abs_err", "direction_hit_rate", "brier", "brier_skill")}})  # fmt: skip
    return sorted(out, key=lambda r: -r["n"])


def trust_buckets(df: pd.DataFrame, n_buckets: int = 5) -> dict:
    """Forward 12-month returns by Trust Rating quantile bucket (lowest to highest)."""
    d = df.dropna(subset=["trust_rating"])
    if len(d) < n_buckets * 5:
        return {"buckets": [], "n": len(d), "note": "too few scored snapshots with a Trust Rating"}
    q = pd.qcut(d["trust_rating"].rank(method="first"), n_buckets, labels=False)
    rows = []
    for b in range(n_buckets):
        g = d[q == b]
        k = int((g["realized_return"] > 0).sum())
        rows.append({
            "bucket": b + 1, "n": len(g),
            "trust_lo": float(g["trust_rating"].min()), "trust_hi": float(g["trust_rating"].max()),
            "mean_return": float(g["realized_return"].mean()), "median_return": float(g["realized_return"].median()),
            "positive_share": k / len(g), "positive_ci": wilson(k, len(g)),
        })  # fmt: skip
    spread = rows[-1]["mean_return"] - rows[0]["mean_return"]
    rho = float(d["trust_rating"].corr(d["realized_return"], method="spearman"))
    return {"buckets": rows, "n": len(d), "top_minus_bottom": spread, "spearman": _f(rho)}


def method_errors(df: pd.DataFrame) -> list[dict]:
    """Per valuation method: median absolute log error of its 12-month figure against the realized price."""
    recs = []
    for _, r in df.iterrows():
        for mth in r["methods"] or []:
            t = mth.get("target_12m")
            if t and t > 0 and r["realized_price"] > 0:
                recs.append({"method": mth["id"], "label": mth.get("label", mth["id"]), "profile": r["profile"],
                             "err": abs(math.log(r["realized_price"] / t)),
                             "up_right": (t > r["price"]) == bool(r["realized_up"])})  # fmt: skip
    if not recs:
        return []
    e = pd.DataFrame(recs)
    out = []
    for (mid, label), g in e.groupby(["method", "label"]):
        out.append({"method": mid, "label": label, "n": len(g), "median_abs_log_err": float(g["err"].median()),
                    "direction_hit_rate": float(g["up_right"].mean())})  # fmt: skip
    return sorted(out, key=lambda r: r["median_abs_log_err"])


def full(df: pd.DataFrame, cfg: dict) -> dict:
    """Everything the track record page shows for one slice of snapshots."""
    t = cfg["track"]
    return {
        "summary": summary(df),
        "reliability": reliability(df, int(t["prob_bins"])),
        "interval_coverage": interval_coverage(df, list(t["coverage_levels"])),
        "pit": pit_histogram(df),
        "by_profile": by_group(df, "profile"),
        "by_vol": by_group(df, "vol_bucket"),
        "by_size": by_group(df, "size_bucket"),
        "by_year": by_group(df.assign(year=pd.to_datetime(df["as_of"]).dt.year), "year") if len(df) else [],
        "trust": trust_buckets(df, int(t["trust_buckets"])),
        "methods": method_errors(df),
    }
