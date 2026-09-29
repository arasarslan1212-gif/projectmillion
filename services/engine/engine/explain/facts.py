"""The facts JSON: every number the narratives may use, each with an id, unit, source and as-of date.

Narratives (templates and LLM text alike) may only state numbers that appear here, and every claim sentence cites
the fact ids it relies on. Values are the engine's exact computed numbers; `display` is how the app formats them.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from engine.report.context import ReportContext


def fmt(value, unit: str, digits: int | None = None, signed: bool = False) -> str:
    """Python twin of the web formatter, used for templates and fact chips."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "n/a"
    if isinstance(value, str):
        return value
    sign = "+" if signed and value > 0 else ""
    if unit == "prob":
        # a model probability is never shown as certain (same rule as the web formatter)
        d = 1 if digits is None else digits
        edge = 0.5 * 10 ** -(d + 2)
        if value >= 1 - edge:
            return f">{100 - 10**-d:.{d}f}%"
        if value < edge:
            return f"<{10**-d:.{d}f}%"
        s = f"{sign}{value * 100:.{d}f}%"
    elif unit == "pct":
        d = 1 if digits is None else digits
        s = f"{sign}{value * 100:.{d}f}%"
    elif unit == "usd_per_share":
        d = (0 if abs(value) >= 1000 else 2) if digits is None else digits
        s = f"{sign}{'-' if value < 0 else ''}${abs(value):,.{d}f}"
    elif unit == "usd":
        a = abs(value)
        d = 1 if digits is None else digits
        for scale, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if a >= scale:
                s = f"{sign}{'-' if value < 0 else ''}${a / scale:.{d}f}{suf}"
                break
        else:
            s = f"{sign}{'-' if value < 0 else ''}${a:,.0f}"
    elif unit == "x":
        s = f"{sign}{value:.{1 if digits is None else digits}f}x"
    elif unit in ("score", "count", "years", "days"):
        s = f"{sign}{value:.{0 if digits is None else digits}f}"
    else:  # ratio / plain
        s = f"{sign}{value:.{2 if digits is None else digits}f}"
    return s[1:] if s[:1] in "+-" and not any(ch in "123456789" for ch in s) else s


@dataclass
class Fact:
    id: str
    label: str
    value: float | int | str | None
    unit: str
    group: str
    source: str | None = None
    as_of: str | None = None
    display: str | None = None


class Facts:
    def __init__(self) -> None:
        self.items: dict[str, Fact] = {}

    def add(
        self,
        id: str,
        label: str,
        value,
        unit: str,
        group: str,
        source: str | None = None,
        as_of=None,
        digits=None,
    ):
        if value is None or (isinstance(value, float) and not math.isfinite(value)):
            return
        if hasattr(value, "item"):
            value = value.item()
        disp = value if isinstance(value, str) else fmt(value, unit, digits)
        self.items[id] = Fact(id, label, value, unit, group, source, str(as_of) if as_of else None, disp)

    def get(self, id: str):
        f = self.items.get(id)
        return f.value if f else None

    def has(self, *ids: str) -> bool:
        return all(i in self.items for i in ids)

    def to_list(self) -> list[dict]:
        return [asdict(f) for f in self.items.values()]


def _m(section: dict | None, key: str):
    if not section:
        return None
    m = (section.get("metrics") or {}).get(key)
    return m.get("value") if isinstance(m, dict) else None


def build_facts(ctx: ReportContext, s: dict[str, dict | None]) -> Facts:
    """`s` maps section name -> section output (or None when unavailable)."""
    F = Facts()
    as_of = ctx.as_of.isoformat()
    comp = s.get("company") or {}
    ident = comp.get("identity") or {}
    F.add("company.name", "Company", ident.get("name"), "text", "company")
    F.add("company.ticker", "Ticker", ident.get("ticker"), "text", "company")
    F.add("company.profile", "Analysis profile", ident.get("profile_label"), "text", "company")
    F.add("company.sector", "Sector", ident.get("sector_label"), "text", "company")
    price = ctx.last_price
    F.add("price", "Last close", price, "usd_per_share", "company", "prices", ctx.last_price_date)
    st = comp.get("stats") or {}
    for key, label, unit in (
        ("market_cap", "Market cap", "usd"),
        ("pe", "P/E (trailing)", "x"),
        ("ev_ebitda", "EV/EBITDA", "x"),
        ("dividend_yield", "Dividend yield", "pct"),
        ("beta", "Beta", "ratio"),
        ("high_52w", "52-week high", "usd_per_share"),
        ("low_52w", "52-week low", "usd_per_share"),
    ):
        m = st.get(key) or {}
        F.add(f"company.{key}", label, m.get("value"), unit, "company", m.get("source"), m.get("as_of"))

    # ---- Trust Rating ---------------------------------------------------------------------------
    t = s.get("trust")
    if t and t.get("status") == "ok":
        F.add("trust.score", "Trust Rating", t["score"], "score", "trust", "app", as_of)
        F.add("trust.grade", "Trust Rating grade", t["grade"], "text", "trust")
        F.add(
            "trust.raw",
            "Trust Rating before red-flag deductions",
            t.get("raw_score"),
            "score",
            "trust",
            digits=1,
        )
        ded = sum(d.get("points", 0) for d in (t.get("deductions") or []))
        F.add("trust.deductions", "Red-flag deduction points", ded, "score", "trust")
        F.add(
            "trust.coverage",
            "Share of Trust Rating weight with data",
            t.get("coverage"),
            "pct",
            "trust",
            digits=0,
        )
        for p in t["pillars"]:
            if p.get("score") is None:
                continue
            pid = p["id"]
            F.add(f"trust.pillar.{pid}", f"{p['label']} pillar score", p["score"], "score", "trust")
            F.add(
                f"trust.pillar.{pid}.weight",
                f"{p['label']} weight",
                p.get("effective_weight"),
                "pct",
                "trust",
                digits=0,
            )
            F.add(f"trust.pillar.{pid}.points", f"{p['label']} contribution (points)",
                  (p.get("effective_weight") or 0) * p["score"], "score", "trust", digits=1)  # fmt: skip
            if p.get("explanation"):
                F.add(
                    f"trust.pillar.{pid}.why", f"{p['label']}: explanation", p["explanation"], "text", "trust"
                )
            for k in ("raise_if", "lower_if"):
                if p.get(k):
                    F.add(
                        f"trust.pillar.{pid}.{k}",
                        f"{p['label']}: {k.replace('_', ' ')}",
                        p[k],
                        "text",
                        "trust",
                    )
            for mt in p.get("metrics") or []:
                if mt.get("value") is None or mt.get("score") is None:
                    continue
                F.add(
                    f"metric.{mt['id']}",
                    mt["label"],
                    mt["value"],
                    mt.get("unit") or "ratio",
                    "metrics",
                    mt.get("source"),
                    as_of,
                )
                F.add(f"metric.{mt['id']}.score", f"{mt['label']} score", mt["score"], "score", "metrics")
        for m in t.get("missing_pillars") or []:
            F.add(
                f"gap.pillar.{m['id']}",
                f"{m['label']} pillar missing",
                m.get("reason", "insufficient data"),
                "text",
                "gaps",
            )

    rk = s.get("risk")
    if rk:
        fired = (rk.get("red_flags") or {}).get("triggered") or []
        F.add("risk.n_flags", "Red flags triggered", len(fired), "count", "risk")
        for f in fired:
            F.add(
                f"flag.{f['id']}",
                f"Red flag: {f['title']}",
                f.get("explanation") or f["title"],
                "text",
                "risk",
            )
        for m in rk.get("metrics") or []:
            if m["id"] in ("volatility_1y", "max_drawdown_3y", "beta", "current_drawdown"):
                F.add(
                    f"risk.{m['id']}",
                    m["label"],
                    m.get("value"),
                    m.get("unit") or "pct",
                    "risk",
                    m.get("source"),
                    m.get("as_of"),
                )

    # ---- valuation -----------------------------------------------------------------------------------
    v = s.get("valuation")
    if v and v.get("status") == "ok":
        tg = v["target"]
        for k, label, unit in (
            ("p50", "App 12-month target (P50)", "usd_per_share"),
            ("p10", "P10 (low end of the 80% range)", "usd_per_share"),
            ("p90", "P90 (high end of the 80% range)", "usd_per_share"),
            ("implied_return", "Implied return to P50", "pct"),
            ("expected_return", "Expected return (mean)", "pct"),
            ("prob_up", "Probability price is higher in 12 months", "prob"),
            ("prob_drawdown_20", "Probability of a 20% drawdown", "prob"),
        ):
            F.add(f"val.{k}", label, tg.get(k), unit, "valuation", "app valuation engine", as_of)
        F.add("val.range_coverage", "Coverage of the P10–P90 range", 0.8, "pct", "valuation", digits=0)
        F.add("val.horizon_months", "Target horizon (months)", 12, "count", "valuation")
        F.add(
            "premortem.fall", "Hypothetical fall used in the pre-mortem", -0.4, "pct", "premortem", digits=0
        )
        F.add("val.intrinsic", "Long-term intrinsic value", v.get("intrinsic"), "usd_per_share", "valuation")
        w = v.get("wacc") or {}
        F.add("val.wacc", "WACC", w.get("value"), "pct", "valuation")
        F.add("val.cost_of_equity", "Cost of equity", w.get("cost_of_equity"), "pct", "valuation")
        sg = v.get("sigma") or {}
        F.add("val.sigma_market", "Market volatility (σ)", sg.get("market"), "pct", "valuation", digits=0)
        F.add("val.sigma_total", "Total uncertainty (σ)", sg.get("total"), "pct", "valuation", digits=0)
        if sg.get("calibration_scale") not in (None, 1, 1.0):
            F.add("val.calibration_scale", "Range scale from the track-record recalibration", sg["calibration_scale"],
                  "x", "valuation", "track record", digits=2)  # fmt: skip
        F.add(
            "val.convergence",
            "Share of the gap to value closed in 12 months",
            sg.get("convergence"),
            "pct",
            "valuation",
            digits=0,
        )
        F.add("val.n_methods", "Methods in the blend", len(v.get("blend") or []), "count", "valuation")
        for b in v.get("blend") or []:
            F.add(
                f"val.method.{b['id']}.value", f"{b['label']} value", b["value"], "usd_per_share", "valuation"
            )
            F.add(
                f"val.method.{b['id']}.weight",
                f"{b['label']} weight",
                b["weight"],
                "pct",
                "valuation",
                digits=0,
            )
            F.add(
                f"val.method.{b['id']}.target",
                f"{b['label']} 12-month figure",
                b["target_12m"],
                "usd_per_share",
                "valuation",
            )
            F.add(f"val.method.{b['id']}.label", "Method", b["label"], "text", "valuation")
        for name, sc in (v.get("scenarios") or {}).items():
            base = f"val.scenario.{name}"
            F.add(
                f"{base}.value", f"{name.title()} case value", sc.get("value"), "usd_per_share", "valuation"
            )
            F.add(
                f"{base}.probability",
                f"{name.title()} case probability",
                sc.get("probability"),
                "pct",
                "valuation",
                digits=0,
            )
            for k, label in (("growth1", "near-term revenue growth"), ("margin_target", "target operating margin"),
                             ("wacc", "WACC"), ("roe", "return on equity"), ("cost_of_equity", "cost of equity")):  # fmt: skip
                if sc.get(k) is not None:
                    F.add(f"{base}.{k}", f"{name.title()} case {label}", sc[k], "pct", "valuation")
        r = v.get("reverse_dcf") or {}
        if r.get("implied_growth") is not None or r.get("implied_roe") is not None:
            if r.get("implied_roe") is not None:
                F.add(
                    "val.rdcf.implied",
                    "Return on equity implied by the price",
                    r["implied_roe"],
                    "pct",
                    "valuation",
                )
                F.add("val.rdcf.history", "5-year median ROE", r.get("history_roe"), "pct", "valuation")
                F.add("val.rdcf.trailing", "Trailing ROE", r.get("trailing_roe"), "pct", "valuation")
            else:
                F.add(
                    "val.rdcf.implied",
                    f"Growth implied by the price ({r.get('basis')})",
                    r["implied_growth"],
                    "pct",
                    "valuation",
                )
                F.add("val.rdcf.history", "Delivered growth", r.get("history_growth"), "pct", "valuation")
                F.add("val.rdcf.consensus", "Consensus growth", r.get("consensus_growth"), "pct", "valuation")
            F.add(
                "val.rdcf.assessment",
                "Assessment of what the price implies",
                r.get("assessment"),
                "text",
                "valuation",
            )
            F.add("val.rdcf.statement", "Reverse valuation", r.get("statement"), "text", "valuation")
        dcf = v.get("dcf") or {}
        if dcf:
            F.add(
                "val.dcf.years",
                "DCF explicit forecast years",
                (dcf.get("inputs") or {}).get("years"),
                "count",
                "valuation",
            )
            F.add(
                "val.dcf.terminal_share",
                "Terminal value share of DCF value",
                dcf.get("terminal_share"),
                "pct",
                "valuation",
                digits=0,
            )
            for i, d in enumerate((dcf.get("tornado") or [])[:3]):
                F.add(f"val.driver.{i}.label", "Driver", d["driver"], "text", "valuation")
                F.add(f"val.driver.{i}.delta", f"{d['driver']} test change", d["delta"], "pct", "valuation")
                F.add(
                    f"val.driver.{i}.low",
                    f"DCF value with lower {d['driver'].lower()}",
                    d["low"],
                    "usd_per_share",
                    "valuation",
                )
                F.add(
                    f"val.driver.{i}.high",
                    f"DCF value with higher {d['driver'].lower()}",
                    d["high"],
                    "usd_per_share",
                    "valuation",
                )
        c = v.get("confidence") or {}
        F.add("conf.score", "Confidence", c.get("score"), "score", "confidence")
        F.add("conf.level", "Confidence level", c.get("level"), "text", "confidence")
        for b in c.get("breakdown") or []:
            F.add(f"conf.{b['id']}", f"Confidence: {b['label'].lower()}", b["score"], "score", "confidence")
            F.add(
                f"conf.{b['id']}.note",
                f"Confidence: {b['label'].lower()} (detail)",
                b.get("note"),
                "text",
                "confidence",
            )
        for sw in v.get("sanity") or []:
            F.add(f"gap.sanity.{sw['id']}", "Valuation warning", sw["message"], "text", "gaps")

    # ---- analysts, news, earnings, dividends, ownership --------------------------------------------------
    a = s.get("analysts")
    if a and a.get("status") in ("ok", "partial"):
        F.add(
            "an.consensus_all",
            "All-analyst consensus target",
            a.get("consensus_all"),
            "usd_per_share",
            "analysts",
        )
        F.add(
            "an.consensus_trusted",
            "Trusted consensus target",
            a.get("consensus_trusted"),
            "usd_per_share",
            "analysts",
        )
        F.add("an.upside_trusted", "Upside to trusted consensus", a.get("trusted_upside"), "pct", "analysts")
        F.add("an.upside_all", "Upside to all-analyst consensus", a.get("all_upside"), "pct", "analysts")
        F.add(
            "an.rating", "Trust-weighted analyst rating", a.get("trust_weighted_rating"), "ratio", "analysts"
        )
        F.add(
            "an.rating_label",
            "Trust-weighted analyst rating (label)",
            a.get("trust_weighted_rating_label"),
            "text",
            "analysts",
        )
        F.add("an.n_active", "Active analyst targets", _m(a, "n_active"), "count", "analysts")
        F.add(
            "an.dispersion",
            "Analyst target dispersion",
            a.get("target_dispersion"),
            "pct",
            "analysts",
            digits=0,
        )
    n = s.get("news")
    if n and n.get("status") == "ok":
        F.add(
            "news.sentiment_30d",
            "News sentiment, 30 days (−1 to +1)",
            n.get("sentiment_30d"),
            "ratio",
            "news",
        )
        F.add(
            "news.sentiment_7d", "News sentiment, 7 days (−1 to +1)", n.get("sentiment_7d"), "ratio", "news"
        )
        F.add("news.trend", "News sentiment trend", n.get("trend"), "text", "news")
        F.add("news.stories_30d", "Stories in 30 days", _m(n, "stories_30d"), "count", "news")
    e = s.get("earnings")
    if e and e.get("status") in ("ok", "partial"):
        F.add(
            "earn.beat_rate", "EPS beat rate (12 quarters)", _m(e, "beat_rate"), "pct", "earnings", digits=0
        )
        F.add("earn.avg_move", "Average move after earnings", _m(e, "avg_move"), "pct", "earnings")
        F.add("earn.next_date", "Next earnings date", e.get("next_date"), "text", "earnings")
    dv = s.get("dividends")
    if dv and dv.get("status") == "ok":
        F.add("div.yield", "Dividend yield", _m(dv, "yield"), "pct", "dividends", digits=2)
        F.add("div.payout", "Payout ratio", _m(dv, "payout_earnings"), "pct", "dividends", digits=0)
        F.add("div.safety", "Dividend safety score", _m(dv, "safety"), "score", "dividends")
        F.add("div.safety_level", "Dividend safety", dv.get("safety_level"), "text", "dividends")
        F.add("div.streak", "Years of dividend increases", _m(dv, "streak"), "count", "dividends")
    ow = s.get("ownership")
    if ow and ow.get("status") in ("ok", "partial"):
        F.add(
            "own.insider_buy_6m",
            "Insider open-market purchases (6 months)",
            _m(ow, "insider_buy_6m"),
            "usd",
            "ownership",
        )
        F.add(
            "own.insider_sell_6m",
            "Insider open-market sales (6 months)",
            _m(ow, "insider_sell_6m"),
            "usd",
            "ownership",
        )
        F.add("own.clusters", "Insider cluster buys (24 months)", _m(ow, "clusters"), "count", "ownership")
        F.add("own.short_pct", "Short interest (% of float)", _m(ow, "short_pct"), "pct", "ownership")
        F.add(
            "own.share_change_3y",
            "Share count change (3-year CAGR)",
            _m(ow, "share_change_3y"),
            "pct",
            "ownership",
        )

    # ---- gaps and caveats ----------------------------------------------------------------------------------
    for name, sec in s.items():
        if sec is None or sec.get("status") == "error":
            F.add(f"gap.section.{name}", f"{name.title()} section", "could not be computed", "text", "gaps")
        elif sec.get("status") in ("missing", "partial") and sec.get("reason"):
            F.add(f"gap.section.{name}", f"{name.title()} section", sec["reason"], "text", "gaps")
    if (s.get("dividends") or {}).get("status") == "not_applicable":
        F.add("div.none", "Dividend", "the company does not pay a dividend", "text", "dividends")
    if ctx.synthetic:
        F.add("gap.synthetic", "Data", "synthetic test data, not real market data", "text", "gaps")
    return F
