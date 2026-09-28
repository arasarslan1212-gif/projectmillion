"""All-analyst and trusted consensus from each analyst's latest call."""

from __future__ import annotations

import math

import numpy as np


def weight(score: float | None, prior: float | None, gamma: float) -> float:
    """Trusted-consensus weight: (Trust Score ÷ 100) ^ gamma; unscored analysts get the average analyst's score."""
    s = score if score is not None else (prior if prior is not None else 50.0)
    return (max(s, 0.0) / 100.0) ** gamma


def consensus(rows: list[dict], price: float | None, cfg: dict, prior_score: float | None) -> dict:
    """rows: latest call per analyst with target, stale, trust_score, rating_norm, days_old.

    Flags targets more than `outlier_factor`× away from the median active target as likely data errors
    (sets row["outlier"] and row["stale"]) and excludes them, like stale targets, from both figures.
    """
    gamma = float(cfg["trusted_weight_gamma"])
    rating_days = int(cfg["rating_stale_months"]) * 30
    cand = [r for r in rows if not r["stale"] and r.get("target")]
    if len(cand) >= 3:
        med = float(np.median([r["target"] for r in cand]))
        lim = math.log(float(cfg["outlier_factor"]))
        for r in cand:
            if abs(math.log(r["target"] / med)) > lim:
                r["outlier"] = True
                r["stale"] = True
    active = [r for r in rows if not r["stale"] and r.get("target")]
    tg = np.array([r["target"] for r in active], float)
    w = np.array([weight(r.get("trust_score"), prior_score, gamma) for r in active])
    out: dict = {
        "active": active,
        "n_active": len(active),
        "n_stale": sum(1 for r in rows if r["stale"] and r.get("target") and not r.get("outlier")),
        "n_outliers": sum(1 for r in rows if r.get("outlier")),
        "all": float(tg.mean()) if len(tg) else None,
        "median": float(np.median(tg)) if len(tg) else None,
        "trusted": float(np.sum(w * tg) / np.sum(w)) if len(tg) and np.sum(w) > 0 else None,
        "dispersion": float((tg.max() - tg.min()) / tg.mean()) if len(tg) >= 2 else None,
        "high": float(tg.max()) if len(tg) else None,
        "low": float(tg.min()) if len(tg) else None,
        "weights": {r["who"]: float(x / np.sum(w)) for r, x in zip(active, w, strict=True)}
        if len(w) and np.sum(w) > 0
        else {},
    }
    rated = [r for r in rows if r.get("rating_norm") is not None and r.get("days_old", 0) <= rating_days]
    rw = np.array([weight(r.get("trust_score"), prior_score, gamma) for r in rated])
    rv = np.array([r["rating_norm"] for r in rated], float)
    out["trust_weighted_rating"] = float(np.sum(rw * rv) / np.sum(rw)) if len(rv) and np.sum(rw) > 0 else None
    out["average_rating"] = float(rv.mean()) if len(rv) else None
    out["upside_all"] = out["all"] / price - 1 if (out["all"] and price) else None
    out["upside_trusted"] = out["trusted"] / price - 1 if (out["trusted"] and price) else None
    return out
