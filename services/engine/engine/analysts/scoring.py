"""Analyst and firm Trust Scores (0–100).

Each call is scored only on horizons that have fully passed by the report date (point-in-time):

    hit          the price reached the target within 12 months (closing prices; bullish targets need a close at
                 or above the target, bearish targets a close at or below it)
    ape          |price 12 months later ÷ target − 1|                              (mean = MAPE)
    directional  direction × (stock total return − benchmark total return), at 3, 6 and 12 months, against the
                 market and the sector ETF; direction is +1 Buy / −1 Sell (Holds are not directional)
    optimism     target-implied return − realized 12-month price return            (always-bullish bias)

Per analyst, metrics are recency-weighted means (half-life in config). Sample size is handled with Bayesian
shrinkage: (n × own + k × prior) ÷ (n + k), where the prior for the analyst's all-stock record is the average
analyst, for their sector record their all-stock record, and for this stock their sector record. So a 3-for-3
record stays close to average while 60-for-90 mostly speaks for itself. The Trust Score maps the shrunk metrics
to 0–100 with the configured anchors and weights. Firms are scored the same way on all their analysts' calls.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from engine.analysts.calls import Call, direction

METRICS = ("hit_rate", "mape", "directional", "optimism_bias")


@dataclass
class PriceBook:
    dates: np.ndarray  # datetime64[D], ascending
    close: np.ndarray  # split-adjusted close
    adj: np.ndarray  # total-return (dividend-adjusted) close

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> PriceBook | None:
        if df is None or df.empty:
            return None
        return cls(
            df.index.values.astype("datetime64[D]"),
            df["close"].to_numpy(float),
            df["adj_close"].to_numpy(float),
        )

    def index_on_or_before(self, d: date) -> int | None:
        i = int(np.searchsorted(self.dates, np.datetime64(d, "D"), side="right")) - 1
        return i if i >= 0 else None


def score_calls(
    calls: list[Call],
    books: dict[str, PriceBook],
    benches: dict[str, tuple[str | None, str | None]],
    as_of: date,
    cfg: dict,
    sectors: dict[str, str],
) -> pd.DataFrame:
    """One row per call with its matured outcomes (NaN where the horizon has not passed)."""
    hz = cfg["horizons"]
    thr = float(cfg["implied_direction_threshold"])
    rows = []
    for c in calls:
        if c.date > as_of:
            continue
        book = books.get(c.ticker)
        if book is None:
            continue
        i = book.index_on_or_before(c.date)
        if i is None or book.dates[i] < np.datetime64(c.date, "D") - np.timedelta64(7, "D"):
            continue
        last = book.index_on_or_before(as_of)
        p0 = book.close[i]
        if not (p0 > 0):
            continue
        d, dsrc = direction(c, p0, thr)
        row = {
            "ticker": c.ticker,
            "sector": sectors.get(c.ticker, "unknown"),
            "date": c.date,
            "analyst_key": c.analyst_key,
            "firm": c.firm,
            "dir": d,
            "dir_source": dsrc,
            "target": c.target,
            "p0": p0,
            "implied": (c.target / p0 - 1) if c.target else np.nan,
            "age_years": (as_of - c.date).days / 365.25,
            "hit": np.nan,
            "ape": np.nan,
            "r12": np.nan,
        }
        mkt_t, sec_t = benches.get(c.ticker, (None, None))
        for name, h in hz.items():
            j = i + int(h)
            for bname in ("mkt", "sec"):
                row[f"x_{name}_{bname}"] = np.nan
            if last is None or j > last:
                continue
            r = book.adj[j] / book.adj[i] - 1
            if name == "12m":
                row["r12"] = book.close[j] / p0 - 1
                if c.target:
                    path = book.close[i + 1 : j + 1]
                    row["hit"] = (
                        float(path.max() >= c.target) if c.target >= p0 else float(path.min() <= c.target)
                    )
                    row["ape"] = abs(book.close[j] / c.target - 1)
            if d == 0:
                continue
            for bname, bt in (("mkt", mkt_t), ("sec", sec_t)):
                bb = books.get(bt) if bt else None
                if bb is None:
                    continue
                bi, bj = bb.index_on_or_before(c.date), bb.index_on_or_before(_date(book.dates[j]))
                if bi is None or bj is None or bj <= bi:
                    continue
                row[f"x_{name}_{bname}"] = d * (r - (bb.adj[bj] / bb.adj[bi] - 1))
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    hw = cfg["directional_horizon_weights"]
    num = np.zeros(len(df))
    den = np.zeros(len(df))
    for name, w in hw.items():
        cols = [f"x_{name}_mkt", f"x_{name}_sec"]
        m = df[cols].mean(axis=1, skipna=True)
        ok = m.notna().to_numpy()
        num[ok] += w * m.to_numpy()[ok]
        den[ok] += w
    df["directional"] = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
    df["optimism_bias"] = df["implied"] - df["r12"]
    df["weight"] = 0.5 ** (df["age_years"] / float(cfg["recency_half_life_years"]))
    df["scored"] = df[["hit", "directional", "ape"]].notna().any(axis=1)
    return df


def _date(x: np.datetime64) -> date:
    return pd.Timestamp(x).date()


def _wmean(df: pd.DataFrame, col: str) -> tuple[float | None, float]:
    s = df[col]
    ok = s.notna()
    if not ok.any():
        return None, 0.0
    w = df.loc[ok, "weight"].to_numpy()
    return float(np.sum(w * s[ok].to_numpy()) / np.sum(w)), float(np.sum(w))


def raw_metrics(df: pd.DataFrame) -> dict:
    out = {}
    for m, col in (
        ("hit_rate", "hit"),
        ("mape", "ape"),
        ("directional", "directional"),
        ("optimism_bias", "optimism_bias"),
    ):
        v, n = _wmean(df, col)
        out[m] = {"value": v, "n": n, "count": int(df[col].notna().sum())}
    rated = df[df["dir_source"] == "rating"]
    out["bullish_share"] = float((rated["dir"] > 0).mean()) if len(rated) else None
    out["n_calls"] = int(len(df))
    out["n_scored"] = int(df["scored"].sum())
    return out


def shrink(raw: dict, prior: dict, k: float) -> dict:
    """Shrink each metric toward the prior's value by its (recency-weighted) sample size."""
    out = {}
    for m in METRICS:
        r, p = raw[m], prior.get(m)
        pv = p if isinstance(p, float | int) or p is None else p.get("value")
        if r["value"] is None:
            out[m] = pv
        elif pv is None:
            out[m] = r["value"]
        else:
            out[m] = (r["n"] * r["value"] + k * pv) / (r["n"] + k)
    return out


def _lin(v: float | None, a: list[float]) -> float | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    a0, a100 = a
    return float(min(100.0, max(0.0, (v - a0) / (a100 - a0) * 100.0)))


def composite(m: dict, cfg: dict) -> tuple[float | None, dict]:
    anch, w = cfg["anchors"], cfg["score_weights"]
    comps = {
        "hit_rate": _lin(m.get("hit_rate"), anch["hit_rate"]),
        "accuracy": _lin(m.get("mape"), anch["mape"]),
        "directional": _lin(m.get("directional"), anch["directional"]),
        "bias": _lin(m.get("optimism_bias"), anch["optimism_bias"]),
    }
    num = sum(w[k] * v for k, v in comps.items() if v is not None)
    den = sum(w[k] for k, v in comps.items() if v is not None)
    return (num / den if den else None), comps


def herding(calls: list[Call], stale_days: int) -> dict[str, dict]:
    """How far each target revision moves toward the prevailing consensus of *other* analysts.

    For a revision from T_old to T_new, with C the median of other analysts' active targets the day before:
    gap closed = (|T_old − C| − |T_new − C|) ÷ |T_old − C|, only when T_old was more than 5% away from C.
    1 means the analyst jumped straight to the consensus; 0 means they ignored it.
    """
    by_ticker: dict[str, list[Call]] = defaultdict(list)
    for c in calls:
        if c.target is not None and c.analyst_key:
            by_ticker[c.ticker].append(c)
    acc: dict[str, list[float]] = defaultdict(list)
    for tcalls in by_ticker.values():
        tcalls.sort(key=lambda c: c.date)
        for idx, c in enumerate(tcalls):
            if c.target_prior is None:
                continue
            latest: dict[str, Call] = {}
            for o in tcalls[:idx]:
                if (
                    o.analyst_key != c.analyst_key
                    and (c.date - o.date).days <= stale_days
                    and o.date < c.date
                ):
                    latest[o.analyst_key] = o
            if len(latest) < 2:
                continue
            cons = float(np.median([o.target for o in latest.values()]))
            gap_old = abs(c.target_prior - cons)
            if gap_old <= 0.05 * cons:
                continue
            closed = (gap_old - abs(c.target - cons)) / gap_old
            acc[c.analyst_key].append(max(-1.0, min(1.0, closed)))
    return {k: {"value": float(np.mean(v)), "n": len(v)} for k, v in acc.items()}


def trust_scores(df: pd.DataFrame, subject: str, subject_sector: str, cfg: dict, level: str) -> dict:
    """Hierarchical scores for every analyst (level='analyst') or firm (level='firm') covering `subject`.

    Returns {who: {...}} plus a '_population' entry with the average-analyst metrics.
    """
    key = "analyst_key" if level == "analyst" else "firm"
    k = float(cfg["shrinkage_k"])
    data = df[df[key].notna()] if key in df else df.iloc[0:0]
    if data.empty:
        return {}
    pop_raw = raw_metrics(data)
    pop = {m: pop_raw[m]["value"] for m in METRICS}
    pop_score, _ = composite(pop, cfg)
    covering = data.loc[data["ticker"] == subject, key].dropna().unique().tolist()
    out: dict[str, dict] = {"_population": {"metrics": pop, "score": pop_score}}
    for who in covering:
        mine = data[data[key] == who]
        r_all = raw_metrics(mine)
        s_all = shrink(r_all, pop, k)
        sec = mine[mine["sector"] == subject_sector]
        r_sec = raw_metrics(sec) if len(sec) else raw_metrics(mine.iloc[0:0])
        s_sec = shrink(r_sec, s_all, k)
        tic = mine[mine["ticker"] == subject]
        r_tic = raw_metrics(tic)
        s_tic = shrink(r_tic, s_sec, k)
        score, comps = composite(s_tic, cfg)
        out[who] = {
            "score": score,
            "components": comps,
            "metrics": s_tic,
            "score_all": composite(s_all, cfg)[0],
            "score_sector": composite(s_sec, cfg)[0],
            "raw_all": r_all,
            "raw_sector": r_sec,
            "raw_ticker": r_tic,
            "n_scored": r_all["n_scored"],
            "n_scored_ticker": r_tic["n_scored"],
            "n_stocks": int(mine.loc[mine["scored"], "ticker"].nunique()),
            "hits_ticker": int(np.nansum(tic["hit"])) if len(tic) else 0,
            "hit_count_ticker": int(tic["hit"].notna().sum()) if len(tic) else 0,
            "bullish_share": r_all["bullish_share"],
            "since": min(mine["date"]).isoformat() if len(mine) else None,
        }
    return out


def all_scope_scores(df: pd.DataFrame, cfg: dict, level: str) -> dict:
    """Every analyst's (or firm's) record on all stocks, shrunk toward the average analyst."""
    key = "analyst_key" if level == "analyst" else "firm"
    k = float(cfg["shrinkage_k"])
    data = df[df[key].notna()]
    if data.empty:
        return {}
    pop_raw = raw_metrics(data)
    pop = {m: pop_raw[m]["value"] for m in METRICS}
    out = {}
    for who, mine in data.groupby(key):
        r = raw_metrics(mine)
        sh = shrink(r, pop, k)
        excess = {}
        for name in cfg["horizons"]:
            v = mine[[f"x_{name}_mkt", f"x_{name}_sec"]].mean(axis=1, skipna=True)
            ok = v.notna()
            if ok.any():
                w = mine.loc[ok, "weight"].to_numpy()
                excess[name] = float(np.sum(w * v[ok].to_numpy()) / np.sum(w))
        out[str(who)] = {
            "metrics": sh,
            "score": composite(sh, cfg)[0],
            "raw_score": composite({m: r[m]["value"] for m in METRICS}, cfg)[0],
            "n_scored": r["n_scored"],
            "excess": excess,
        }
    return out
