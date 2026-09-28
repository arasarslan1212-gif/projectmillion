import math

import numpy as np
import pandas as pd
import pytest

from engine.analysis.risk import beta_regression, historical_var, max_drawdown, realized_vol
from engine.analysis.technicals import bollinger, ema, macd, momentum_12_1, rsi, sma


def _s(vals, start="2024-01-01"):
    return pd.Series(vals, index=pd.bdate_range(start, periods=len(vals)), dtype=float)


def test_sma_ema_by_hand():
    s = _s([1, 2, 3, 4, 5])
    assert sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0]
    e = ema(s, 3)  # alpha = 0.5, seeded with the first value
    assert e.iloc[2] == pytest.approx(0.5 * 3 + 0.5 * (0.5 * 2 + 0.5 * 1))


def test_rsi_extremes_and_midpoint():
    up = _s(list(range(1, 40)))
    assert rsi(up).iloc[-1] == pytest.approx(100.0)
    alt = _s([10, 11] * 30)
    assert 40 < rsi(alt).iloc[-1] < 60


def test_bollinger_and_macd_shapes():
    s = _s(np.linspace(10, 20, 60))
    lo, mid, hi = bollinger(s)
    assert (hi.dropna() >= mid.dropna()).all() and (lo.dropna() <= mid.dropna()).all()
    line, sig, hist = macd(s)
    assert (hist.dropna() == (line - sig).dropna()).all()
    assert line.iloc[-1] > 0  # steady uptrend: fast EMA above slow EMA


def test_momentum_12_1():
    s = _s(np.linspace(100, 200, 300))
    assert momentum_12_1(s) == pytest.approx(s.iloc[-22] / s.iloc[-253] - 1)


def test_beta_regression_recovers_known_beta():
    rng = np.random.default_rng(1)
    n = 5 * 252
    m = np.cumsum(rng.normal(0.0003, 0.01, n))
    s = 1.6 * m + np.cumsum(rng.normal(0, 0.004, n))
    idx = pd.bdate_range("2019-01-01", periods=n)
    b = beta_regression(pd.Series(np.exp(s), idx), pd.Series(np.exp(m), idx), years=3)
    assert b is not None and b["raw"] == pytest.approx(1.6, abs=0.12)
    assert b["adjusted"] == pytest.approx(0.67 * b["raw"] + 0.33)


def test_drawdown_vol_var():
    s = _s([100, 120, 90, 60, 80, 130, 125] + [125] * 20)
    dd = max_drawdown(s)
    assert dd["max_drawdown"] == pytest.approx(60 / 120 - 1)
    assert dd["peak"] == str(s.index[1].date()) and dd["trough"] == str(s.index[3].date())
    assert dd["recovered"] == str(s.index[5].date())
    rng = np.random.default_rng(2)
    r = rng.normal(0, 0.01, 800)
    px = _s(100 * np.exp(np.cumsum(r)))
    assert realized_vol(px) == pytest.approx(0.01 * math.sqrt(252), rel=0.15)
    assert historical_var(px) == pytest.approx(1.645 * 0.01, rel=0.25)
