"""Cross-sectional data: the industry universe (for sector-relative percentiles) and the peer set.

Fundamentals come from SEC "frames" (one XBRL concept across all filers for a calendar period), so a
whole industry costs a few dozen requests instead of one per company. Frames are aligned to calendar
years; every company in a comparison, including the subject company, uses the same calendar-year
basis. In point-in-time mode a year is only used once `pit.frames_filing_lag_days` have passed since it
ended (frames carry no filing date), and later restatements may already be reflected. That caveat is
shown wherever frames feed a backtest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING

import numpy as np

from engine.fundamentals.ratios import cagr, div, period_ratios, yoy
from engine.fundamentals.statements import Period, derive

if TYPE_CHECKING:
    from engine.report.context import ReportContext

DURATION_ITEMS = [
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "cfo",
    "capex",
    "dna",
    "sbc",
    "interest_expense",
    "shares_diluted",
    "dividends_paid",
    "net_interest_income",
    "noninterest_income",
    "noninterest_expense",
]
INSTANT_ITEMS = [
    "total_assets",
    "current_assets",
    "current_liabilities",
    "total_liabilities",
    "equity",
    "cash",
    "debt_noncurrent",
    "debt_current",
    "receivables",
    "retained_earnings",
    "deposits",
    "loans",
]
PRIOR_YEAR_ITEMS = ["revenue", "net_income", "cfo", "total_assets", "equity"]


def frame_year(as_of: date, lag_days: int) -> int:
    y = as_of.year - 1
    while date(y, 12, 31) + timedelta(days=lag_days) > as_of:
        y -= 1
    return y


@dataclass
class UniverseRow:
    cik: int
    ticker: str | None
    name: str
    values: dict[str, float] = field(default_factory=dict)
    prior: dict[str, float] = field(default_factory=dict)
    ratios: dict[str, float | None] = field(default_factory=dict)

    def period(self, year: int) -> Period:
        p = Period("FY", date(year, 1, 1), date(year, 12, 31), date(year, 12, 31), None)
        p.values = dict(self.values)
        derive(p)
        return p


@dataclass
class Universe:
    year: int
    sic_codes: list[int]
    rows: list[UniverseRow]
    note: str
    widened: bool = False

    def by_cik(self) -> dict[int, UniverseRow]:
        return {r.cik: r for r in self.rows}


def _cik_to_ticker(ctx: ReportContext) -> dict[int, tuple[str, str]]:
    out: dict[int, tuple[str, str]] = {}
    for s in ctx.data.symbols().value or []:
        if s.cik is None:
            continue
        cur = out.get(s.cik)
        if cur is None or len(s.ticker) < len(cur[0]):
            out[s.cik] = (s.ticker, s.name)
    return out


def build_universe(ctx: ReportContext, min_n: int = 8) -> Universe | None:
    sic = ctx.sector.sic
    if sic is None:
        return None
    lag = int(ctx.cfg.get("pit.frames_filing_lag_days", 120))
    year = frame_year(ctx.as_of, lag)
    listed = _cik_to_ticker(ctx)

    def ciks_for(codes: list[int]) -> set[int]:
        out: set[int] = set()
        for c in codes:
            fx = ctx.data.universe_ciks(c)
            out.update(fx.value or [])
        return out

    codes = [sic]
    ciks = {c for c in ciks_for(codes) if c in listed}
    widened = False
    if len(ciks) < min_n * 2:
        group = [sic // 10 * 10 + i for i in range(10)]
        ciks |= {c for c in ciks_for([g for g in group if g != sic]) if c in listed}
        codes = group
        widened = True
    if ctx.cik is not None:
        ciks.add(ctx.cik)

    rows: dict[int, UniverseRow] = {
        c: UniverseRow(cik=c, ticker=listed.get(c, (None, ""))[0], name=listed.get(c, ("", ""))[1])
        for c in ciks
    }
    for item in DURATION_ITEMS:
        fx = ctx.data.frame_item(item, f"CY{year}")
        for cik, val in (fx.value or {}).items():
            if cik in rows:
                rows[cik].values[item] = val
    for item in INSTANT_ITEMS:
        fx = ctx.data.frame_item(item, f"CY{year}Q4I")
        for cik, val in (fx.value or {}).items():
            if cik in rows:
                rows[cik].values[item] = val
    for item in PRIOR_YEAR_ITEMS:
        period = f"CY{year - 1}Q4I" if item in INSTANT_ITEMS else f"CY{year - 1}"
        fx = ctx.data.frame_item(item, period)
        for cik, val in (fx.value or {}).items():
            if cik in rows:
                rows[cik].prior[item] = val
    out = []
    for r in rows.values():
        if "revenue" not in r.values and "total_assets" not in r.values:
            continue
        cur = r.period(year)
        prev = Period("FY", date(year - 1, 1, 1), date(year - 1, 12, 31), date(year - 1, 12, 31), None)
        prev.values = dict(r.prior)
        rat = period_ratios(cur, prev, 1.0)
        rat["revenue_growth"] = yoy(r.values.get("revenue"), r.prior.get("revenue"))
        avg_assets = None
        if r.values.get("total_assets") and r.prior.get("total_assets"):
            avg_assets = (r.values["total_assets"] + r.prior["total_assets"]) / 2
        if r.values.get("net_income") is not None and r.values.get("cfo") is not None and avg_assets:
            rat["accruals_ratio"] = (r.values["net_income"] - r.values["cfo"]) / avg_assets
        r.values.update({k: v for k, v in cur.values.items() if k not in r.values})
        r.ratios = rat
        out.append(r)
    sic_text = f"SIC {sic}" if not widened else f"SIC {sic // 10 * 10}–{sic // 10 * 10 + 9}"
    note = (
        f"{len(out)} SEC filers in {sic_text} with calendar-year {year} data (SEC frames). "
        "Frames align fiscal years to calendar periods and may include later restatements."
    )
    return Universe(year=year, sic_codes=codes, rows=out, note=note, widened=widened)


def percentile_of(
    value: float | None, population: list[float], higher_is_better: bool = True
) -> float | None:
    """Percentile rank (0–100) of `value` within `population`, with 1st/99th-percentile winsorizing.

    Ties count half. Returned so that 100 is always "best" given the metric's direction.
    """
    pop = [x for x in population if x is not None and math.isfinite(x)]
    if value is None or not math.isfinite(value) or len(pop) < 2:
        return None
    arr = np.array(pop)
    lo, hi = np.percentile(arr, [1, 99])
    arr = np.clip(arr, lo, hi)
    v = min(max(value, lo), hi)
    below = float(np.sum(arr < v))
    equal = float(np.sum(arr == v))
    pct = 100.0 * (below + 0.5 * equal) / len(arr)
    return pct if higher_is_better else 100.0 - pct


@dataclass
class PeerRow:
    ticker: str
    name: str
    cik: int | None
    is_subject: bool
    metrics: dict[str, float | None]


def select_peers(
    ctx: ReportContext, universe: Universe | None, override: list[str] | None = None
) -> tuple[list[str], str]:
    max_peers = int(ctx.cfg.get("peers.max_peers", 12))
    if override:
        return [t.upper() for t in override if t.upper() != ctx.ticker][:max_peers], "chosen by you"
    provider_peers: list[str] = []
    if not ctx.pit:
        fx = ctx.data.provider_peers(ctx.ticker)
        provider_peers = [t for t in (fx.value or []) if t != ctx.ticker]
    if universe is None:
        return provider_peers[:max_peers], "provider peer list"
    rev = ctx.fin.ttm.get("revenue")
    band = float(ctx.cfg.get("peers.size_band", 10.0))
    cands = [r for r in universe.rows if r.ticker and r.cik != ctx.cik and r.values.get("revenue")]
    if rev and rev > 0:

        def dist(r: UniverseRow) -> float:
            return abs(math.log(max(r.values["revenue"], 1.0) / rev))

        cands.sort(key=dist)
        similar = [r for r in cands if dist(r) <= math.log(band)]
        cands = similar if len(similar) >= 3 else cands
    same_sic = [r.ticker for r in cands]
    ordered = [t for t in provider_peers if t in set(same_sic)] + [
        t for t in same_sic if t not in provider_peers
    ]
    if not ordered:
        ordered = provider_peers
    how = "same industry (SIC) and similar revenue" + (
        ", led by the provider's peer list" if provider_peers else ""
    )
    return ordered[:max_peers], how


def peer_table(ctx: ReportContext, universe: Universe | None, tickers: list[str]) -> list[PeerRow]:
    rows: list[PeerRow] = []
    by_ticker = {r.ticker: r for r in (universe.rows if universe else []) if r.ticker}
    subject = next((r for r in (universe.rows if universe else []) if r.cik == ctx.cik), None)
    todo = [(ctx.ticker, subject, True)] + [(t, by_ticker.get(t), False) for t in tickers]
    days = int(ctx.cfg.get("data.peer_price_days", 420))
    for t, urow, is_subject in todo:
        m: dict[str, float | None] = {}
        v = urow.values if urow else {}
        rat = urow.ratios if urow else {}
        px = ctx.prices if is_subject else ctx.other_prices(t, days)
        price = float(px["close"].iloc[-1]) if not px.empty else None
        shares = v.get("shares_diluted")
        mcap = price * shares if (price and shares) else None
        if is_subject and ctx.market_cap:
            mcap = ctx.market_cap
        debt = (v.get("debt_noncurrent") or 0.0) + (v.get("debt_current") or 0.0)
        ev = mcap + debt - (v.get("cash") or 0.0) if mcap else None
        ebitda = (
            (v.get("operating_income") + v.get("dna", 0.0)) if v.get("operating_income") is not None else None
        )
        fcf = v.get("cfo") - v.get("capex", 0.0) if v.get("cfo") is not None else None
        ni = v.get("net_income")
        m["market_cap"] = mcap
        m["revenue"] = v.get("revenue")
        m["revenue_growth"] = rat.get("revenue_growth")
        m["gross_margin"] = rat.get("gross_margin")
        m["operating_margin"] = rat.get("operating_margin")
        m["net_margin"] = rat.get("net_margin")
        m["roe"] = rat.get("roe")
        m["debt_to_equity"] = rat.get("debt_to_equity")
        m["pe"] = div(mcap, ni) if (ni and ni > 0) else None
        m["ev_ebitda"] = div(ev, ebitda) if (ebitda and ebitda > 0) else None
        m["ev_sales"] = div(ev, v.get("revenue")) if v.get("revenue") else None
        m["p_fcf"] = div(mcap, fcf) if (fcf and fcf > 0) else None
        m["p_b"] = div(mcap, v.get("equity")) if (v.get("equity") and v["equity"] > 0) else None
        if not px.empty and len(px) > 252:
            m["return_1y"] = float(px["adj_close"].iloc[-1] / px["adj_close"].iloc[-253] - 1)
        else:
            m["return_1y"] = None
        m["fcf_margin"] = rat.get("fcf_margin")
        m["rule_of_40"] = (
            (rat["revenue_growth"] + rat["fcf_margin"])
            if (rat.get("revenue_growth") is not None and rat.get("fcf_margin") is not None)
            else None
        )
        name = urow.name if urow else t
        if is_subject and ctx.meta:
            name = ctx.meta.name
        rows.append(
            PeerRow(ticker=t, name=name, cik=urow.cik if urow else None, is_subject=is_subject, metrics=m)
        )
    return rows


def peer_medians(rows: list[PeerRow]) -> dict[str, float | None]:
    keys = rows[0].metrics.keys() if rows else []
    out: dict[str, float | None] = {}
    for k in keys:
        vals = [r.metrics[k] for r in rows if not r.is_subject and r.metrics.get(k) is not None]
        out[k] = float(np.median(vals)) if len(vals) >= 3 else None
    return out


def company_growth_vs_history(values: list[float]) -> float | None:
    """CAGR across a list of annual values (oldest first)."""
    if len(values) < 2:
        return None
    return cagr(values[0], values[-1], len(values) - 1)
