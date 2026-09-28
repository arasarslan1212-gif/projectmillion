"""What the track record feeds back into the model, always point-in-time.

- `bucket_calibration`: how often past P10–P90 ranges for stocks with similar volatility held the realized price,
  using only outcomes known by the report's date. It feeds the confidence score's calibration component.
- `method_accuracy_weights`: per-method multipliers for the blend from each method's measured 12-month error.
- `fit` / `recalibrate`: an isotonic map for prob-up and a scale for the range width, cross-validated by date and
  stored as a `CalibrationChange` whether applied or not, with the reason.
- `current`: the latest applied change fitted on or before a report's date.

Backtests run inside `raw_model()`, so they grade the uncalibrated engine and never learn from their own future.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import uuid
from datetime import date

import numpy as np
import pandas as pd
from scipy.optimize import isotonic_regression
from sqlalchemy import func, select

from engine.config import ENGINE_VERSION, get_config
from engine.db import models as m
from engine.db.session import session_scope
from engine.track.metrics import Z80, method_errors
from engine.track.scoring import outcomes_frame
from engine.track.snapshots import vol_bucket

log = logging.getLogger("engine.track")
_state = threading.local()
_frames: dict[tuple, pd.DataFrame] = {}
_changes: dict[tuple, dict | None] = {}


@contextlib.contextmanager
def raw_model():
    """Run the valuation engine without any feedback from the track record (for backtests)."""
    prev = getattr(_state, "raw", False)
    _state.raw = True
    try:
        yield
    finally:
        _state.raw = prev


def is_raw() -> bool:
    return getattr(_state, "raw", False)


def _db_version() -> tuple:
    with session_scope() as s:
        n = s.scalar(select(func.count()).select_from(m.SnapshotOutcome)) or 0
        last = s.scalar(select(func.max(m.SnapshotOutcome.scored_at)))
        c = s.scalar(select(func.count()).select_from(m.CalibrationChange)) or 0
    return n, str(last), c


def _frame(synthetic: bool, cutoff: date) -> pd.DataFrame:
    key = (synthetic, cutoff, _db_version())
    if key not in _frames:
        if len(_frames) > 32:
            _frames.clear()
        _frames[key] = outcomes_frame(synthetic=synthetic, cutoff=cutoff)
    return _frames[key]


def _z_raw(df: pd.DataFrame) -> np.ndarray:
    """Standardized realized log error against the raw (uncalibrated) range of each snapshot."""
    sigma = df["sigma_total_raw"].where(df["sigma_total_raw"].notna(), np.log(df["p90"] / df["p50"]) / Z80)
    return (np.log(df["realized_price"] / df["p50"]) / sigma).to_numpy(float)


# ---- feedback used by the valuation engine ---------------------------------------------------------------------


def bucket_calibration(ctx, vol: float | None) -> dict:
    if is_raw():
        return {"error": None, "note": "backtest run: graded without track-record feedback"}
    cfg = get_config()["track"]
    b = vol_bucket(vol)
    df = _frame(ctx.synthetic, ctx.as_of)
    need = int(cfg["min_outcomes"]["bucket_calibration"])
    g = df[df["vol_bucket"] == b] if not df.empty else df
    if b is None or len(g) < need:
        have = 0 if b is None else len(g)
        return {"error": None, "note": f"only {have} scored estimates for {b or 'similar'}-volatility stocks so far "
                                       f"(needs {need})"}  # fmt: skip
    cur = current(ctx.as_of, ctx.synthetic)
    k = cur["sigma_scale"] if cur else 1.0
    cov = float((np.abs(_z_raw(g)) <= Z80 * k).mean())
    kind = "backtest" if bool(g["is_backtest"].all()) else "live and backtest"
    return {
        "error": abs(cov - 0.8),
        "coverage": cov,
        "n": len(g),
        "note": f"{cov:.0%} of {len(g)} past 80% ranges for {b}-volatility stocks held the price ({kind})",
    }


def method_accuracy_weights(profile: str, as_of: date | None = None, synthetic: bool = False) -> dict:
    if is_raw():
        return {"_source": "backtest run: methods weighted without accuracy adjustment"}
    cfg = get_config()["track"]
    need = int(cfg["min_outcomes"]["method_accuracy"])
    lo, hi = cfg["method_accuracy_clip"]
    df = _frame(synthetic, as_of or date.max)
    if df.empty:
        return {"_source": "no scored estimates yet; all methods weighted equally on accuracy"}
    scope, errs = f"{profile} profile", method_errors(df[df["profile"] == profile])
    if sum(1 for e in errs if e["n"] >= need) < 2:
        scope, errs = "all profiles", method_errors(df)
    errs = [e for e in errs if e["n"] >= need]
    if len(errs) < 2:
        return {
            "_source": f"fewer than {need} scored estimates per method; all methods weighted equally on accuracy"
        }
    ref = float(np.median([e["median_abs_log_err"] for e in errs]))
    out: dict = {e["method"]: float(np.clip(ref / max(e["median_abs_log_err"], 1e-6), lo, hi)) for e in errs}
    out["_source"] = f"measured 12-month error of each method on {len(df)} scored estimates ({scope})"
    return out


def current(as_of: date, synthetic: bool) -> dict | None:
    """The latest applied recalibration fitted on or before `as_of`."""
    if is_raw():
        return None
    key = (as_of, synthetic, _db_version()[2])
    if key not in _changes:
        with session_scope() as s:
            r = s.scalars(
                select(m.CalibrationChange)
                .where(
                    m.CalibrationChange.applied.is_(True),
                    m.CalibrationChange.is_synthetic.is_(synthetic),
                    m.CalibrationChange.fitted_on <= as_of,
                )
                .order_by(m.CalibrationChange.fitted_on.desc(), m.CalibrationChange.created_at.desc())
                .limit(1)
            ).first()
            _changes[key] = (
                {"id": r.id, "fitted_on": r.fitted_on.isoformat(), "n": r.n, "sigma_scale": r.sigma_scale,
                 "prob_map": r.prob_map_json, "reason": r.reason}
                if r else None
            )  # fmt: skip
    return _changes[key]


def apply_prob_map(p: float, prob_map: dict | None) -> float:
    if not prob_map:
        return p
    return float(np.interp(p, prob_map["x"], prob_map["y"]))


# ---- fitting ---------------------------------------------------------------------------------------------------


def _isotonic(x: np.ndarray, y: np.ndarray) -> dict:
    """Increasing step map from forecast to observed frequency, kept away from 0 and 1."""
    order = np.argsort(x, kind="stable")
    xs, ys = x[order], y[order].astype(float)
    fitted = isotonic_regression(ys, increasing=True).x
    ux, idx = np.unique(xs, return_index=True)
    uy = np.array([fitted[i:j].mean() for i, j in zip(idx, [*idx[1:], len(xs)], strict=True)])
    keep = np.r_[True, np.diff(uy) != 0] | np.r_[np.diff(uy) != 0, True]  # step edges only
    ux, uy = ux[keep], np.clip(uy[keep], 0.02, 0.98)
    return {"x": [float(v) for v in ux], "y": [float(v) for v in uy]}


def _folds(dates: pd.Series, k: int) -> list[np.ndarray]:
    """Contiguous blocks of forecast dates, so each fold is tested on a period the fit did not see."""
    uniq = np.array(sorted(dates.unique()))
    blocks = np.array_split(uniq, min(k, len(uniq)))
    return [dates.isin(b).to_numpy() for b in blocks if len(b)]


def fit(df: pd.DataFrame, cfg: dict) -> dict:
    """Fit both corrections on `df` and measure them out of fold. Returns the decision and the evidence."""
    rc, t = cfg["track"]["recalibration"], cfg["track"]
    need = int(t["min_outcomes"]["recalibration"])
    n = len(df)
    res: dict = {"n": n, "sigma_scale": 1.0, "prob_map": None, "apply_scale": False, "apply_map": False}
    if n < need:
        res["reason"] = f"{n} scored estimates; at least {need} are needed before recalibrating"
        return res
    lo, hi = rc["sigma_scale_bounds"]
    z = np.abs(_z_raw(df))
    p = df["prob_up_raw"].to_numpy(float)
    y = df["realized_up"].to_numpy(bool)
    # out-of-fold evaluation
    b_raw, b_cal, cov_raw, cov_cal = [], [], [], []
    for test in _folds(df["as_of"], int(rc["folds"])):
        train = ~test
        if train.sum() < 20 or test.sum() == 0:
            continue
        mp = _isotonic(p[train], y[train])
        pc = np.interp(p[test], mp["x"], mp["y"])
        b_raw.append(((p[test] - y[test]) ** 2).sum())
        b_cal.append(((pc - y[test]) ** 2).sum())
        k = float(np.clip(np.quantile(z[train], 0.8) / Z80, lo, hi))
        cov_raw.append((z[test] <= Z80).sum())
        cov_cal.append((z[test] <= Z80 * k).sum())
    brier_raw, brier_cv = sum(b_raw) / n, sum(b_cal) / n
    cv_cov_raw, cv_cov_cal = sum(cov_raw) / n, sum(cov_cal) / n
    # the fit on everything is what gets applied
    res["prob_map"] = _isotonic(p, y)
    res["sigma_scale"] = float(np.clip(np.quantile(z, 0.8) / Z80, lo, hi))
    res["apply_map"] = brier_raw - brier_cv >= float(rc["min_brier_gain"])
    res["apply_scale"] = abs(cv_cov_raw - 0.8) - abs(cv_cov_cal - 0.8) >= float(rc["min_coverage_gain"])
    res["metrics"] = {
        "brier_raw": brier_raw, "brier_calibrated_out_of_fold": brier_cv,
        "coverage_raw": float((z <= Z80).mean()), "coverage_raw_out_of_fold": cv_cov_raw,
        "coverage_scaled_out_of_fold": cv_cov_cal, "sigma_scale_fitted": res["sigma_scale"],
    }  # fmt: skip
    parts = []
    parts.append(
        f"prob-up map {'applied' if res['apply_map'] else 'not applied'}: out-of-fold Brier {brier_raw:.4f} → "
        f"{brier_cv:.4f}"
    )
    parts.append(
        f"range scale ×{res['sigma_scale']:.2f} {'applied' if res['apply_scale'] else 'not applied'}: out-of-fold "
        f"P10–P90 coverage {cv_cov_raw:.1%} → {cv_cov_cal:.1%} (target 80%)"
    )
    res["reason"] = "; ".join(parts)
    return res


def recalibrate(today: date, synthetic: bool) -> dict:
    """Fit on every outcome known today and log the result. Stores a row only when the decision changes."""
    cfg = get_config()
    df = outcomes_frame(synthetic=synthetic, cutoff=today)
    res = fit(df, cfg)
    applied_any = bool(cfg["track"]["recalibration"]["apply"]) and (res["apply_map"] or res["apply_scale"])
    scale = res["sigma_scale"] if applied_any and res["apply_scale"] else 1.0
    pmap = res["prob_map"] if applied_any and res["apply_map"] else None
    prev = current(today, synthetic)
    same = (
        prev is not None
        and applied_any
        and abs(prev["sigma_scale"] - scale) < 0.02
        and (prev["prob_map"] is None) == (pmap is None)
    )
    if same or (prev is None and not applied_any and _has_unapplied(synthetic, res["reason"])):
        return {**res, "stored": False, "applied": applied_any}
    with session_scope() as s:
        s.add(
            m.CalibrationChange(
                id=str(uuid.uuid4()),
                fitted_on=today,
                data_cutoff=max(df["horizon_date"]) if len(df) else today,
                is_synthetic=synthetic,
                n=res["n"],
                sigma_scale=scale,
                prob_map_json=pmap,
                metrics_json={k: v for k, v in (res.get("metrics") or {}).items()},
                applied=applied_any,
                reason=res["reason"],
                engine_version=ENGINE_VERSION,
                config_hash=cfg.hash,
            )
        )
    _changes.clear()
    log.info("recalibration fitted (%s): %s", "applied" if applied_any else "not applied", res["reason"])
    return {**res, "stored": True, "applied": applied_any}


def _has_unapplied(synthetic: bool, reason: str) -> bool:
    with session_scope() as s:
        last = s.scalars(
            select(m.CalibrationChange)
            .where(m.CalibrationChange.is_synthetic.is_(synthetic))
            .order_by(m.CalibrationChange.created_at.desc())
            .limit(1)
        ).first()
        return last is not None and not last.applied and last.reason == reason


def changes(synthetic: bool) -> list[dict]:
    with session_scope() as s:
        rows = s.scalars(
            select(m.CalibrationChange)
            .where(m.CalibrationChange.is_synthetic.is_(synthetic))
            .order_by(m.CalibrationChange.fitted_on.desc(), m.CalibrationChange.created_at.desc())
        ).all()
        return [
            {"id": r.id, "fitted_on": r.fitted_on.isoformat(), "data_cutoff": r.data_cutoff.isoformat(), "n": r.n,
             "applied": r.applied, "sigma_scale": r.sigma_scale, "prob_map": r.prob_map_json,
             "metrics": r.metrics_json, "reason": r.reason, "engine_version": r.engine_version,
             "config_hash": r.config_hash}
            for r in rows
        ]  # fmt: skip


def prob_map_curve(pmap: dict | None) -> list[dict]:
    if not pmap:
        return []
    xs = np.linspace(0.02, 0.98, 25)
    return [{"raw": float(x), "calibrated": apply_prob_map(float(x), pmap)} for x in xs]
