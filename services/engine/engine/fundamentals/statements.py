"""Point-in-time financial statements built from raw XBRL facts.

Rules:
- Only facts with `filed <= as_of` are visible (no look-ahead).
- For each period, the most recently filed value that was visible at `as_of` wins, so a restatement
  counts only once it has been filed.
- The first concept in a line item's priority list that has a value *for that period* wins, which
  handles companies switching tags over time.
- Quarterly flows use direct 3-month facts where reported, otherwise they are derived by differencing
  year-to-date facts (cash-flow statements in 10-Qs are YTD only; Q4 = FY − 9M YTD).
- Share counts and per-share values are converted to current share units using the split history:
  a value filed before a split is multiplied (shares) or divided (per-share) by the split ratio.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.fundamentals.concepts import LINE_ITEMS
from engine.providers.models import Fact

SHARE_KEYS = {"shares_diluted", "shares_basic", "shares_outstanding", "shares_outstanding_cover"}
PER_SHARE_KEYS = {"eps_diluted", "eps_basic", "dps"}
NON_ADDITIVE = SHARE_KEYS | PER_SHARE_KEYS


@dataclass
class Period:
    kind: str  # "FY" | "Q"
    start: date
    end: date
    fy_end: date  # end of the fiscal year this period belongs to
    quarter: int | None  # 1..4 for quarters
    values: dict[str, float] = field(default_factory=dict)
    concepts: dict[str, str] = field(default_factory=dict)  # key -> XBRL concept used
    filed: dict[str, date] = field(default_factory=dict)  # key -> filing date of the value
    derived: dict[str, str] = field(default_factory=dict)  # key -> how it was derived

    def get(self, key: str) -> float | None:
        return self.values.get(key)

    @property
    def label(self) -> str:
        return f"FY{self.fy_end.year}" if self.kind == "FY" else f"Q{self.quarter} FY{self.fy_end.year}"


@dataclass
class Financials:
    annual: list[Period]
    quarterly: list[Period]
    ttm: dict[str, float]
    ttm_end: date | None
    ttm_note: str
    latest_balance_date: date | None
    as_of: date
    concepts_used: dict[str, str]
    cover: dict[str, tuple[float, date]]  # dei cover-page values with their dates

    def annual_series(self, key: str) -> list[tuple[date, float]]:
        return [(p.end, p.values[key]) for p in self.annual if key in p.values]

    def quarterly_series(self, key: str) -> list[tuple[date, float]]:
        return [(p.end, p.values[key]) for p in self.quarterly if key in p.values]

    def latest(self, key: str) -> float | None:
        if key in self.ttm:
            return self.ttm[key]
        for p in reversed(self.quarterly or self.annual):
            if key in p.values:
                return p.values[key]
        return None

    @property
    def years_of_history(self) -> int:
        return len(self.annual)


def _split_factor(filed: date, splits: list[tuple[date, float]], as_of: date) -> float:
    f = 1.0
    for d, ratio in splits:
        if filed < d <= as_of:
            f *= ratio
    return f


def build_financials(
    facts: list[Fact], as_of: date, splits: list[tuple[date, float]] | None = None
) -> Financials:
    splits = sorted(splits or [])
    visible = [f for f in facts if f.filed <= as_of]
    concept_to_keys: dict[tuple[str, str], list[str]] = defaultdict(list)
    for key, li in LINE_ITEMS.items():
        for c in li.concepts:
            concept_to_keys[(li.taxonomy, c)].append(key)

    # key -> {(start,end) or end: (priority, filed, value, concept)}
    dur: dict[str, dict[tuple[date, date], tuple[int, date, float, str]]] = defaultdict(dict)
    inst: dict[str, dict[date, tuple[int, date, float, str]]] = defaultdict(dict)
    for f in visible:
        for key in concept_to_keys.get((f.taxonomy, f.concept), ()):
            li = LINE_ITEMS[key]
            if f.unit != li.unit:
                continue
            prio = li.concepts.index(f.concept)
            val = f.value
            if key in SHARE_KEYS:
                val *= _split_factor(f.filed, splits, as_of)
            elif key in PER_SHARE_KEYS:
                val /= _split_factor(f.filed, splits, as_of)
            if li.kind == "duration":
                if f.start is None:
                    continue
                k = (f.start, f.end)
                cur = dur[key].get(k)
                if cur is None or prio < cur[0] or (prio == cur[0] and f.filed >= cur[1]):
                    dur[key][k] = (prio, f.filed, val, f.concept)
            else:
                cur = inst[key].get(f.end)
                if cur is None or prio < cur[0] or (prio == cur[0] and f.filed >= cur[1]):
                    inst[key][f.end] = (prio, f.filed, val, f.concept)

    # --- fiscal years ---------------------------------------------------------------------
    annual_spans: Counter[tuple[date, date]] = Counter()
    for key in ("revenue", "net_income", "cfo", "operating_income", "net_interest_income"):
        for s, e in dur.get(key, {}):
            if 350 <= (e - s).days <= 380:
                annual_spans[(s, e)] += 1
    by_end: dict[date, date] = {}
    for (s, e), _n in annual_spans.most_common():
        # merge 52/53-week variations: one fiscal year per end date (±3 days)
        match = next((x for x in by_end if abs((x - e).days) <= 3), None)
        if match is None:
            by_end[e] = s
    fiscal_years = sorted((s, e) for e, s in by_end.items())

    def near(d1: date, d2: date, tol: int) -> bool:
        return abs((d1 - d2).days) <= tol

    def find_dur(key: str, start: date, end: date, tol_s: int = 7, tol_e: int = 4):
        m = dur.get(key)
        if not m:
            return None
        hit = m.get((start, end))
        if hit is not None:
            return hit
        for (s, e), v in m.items():
            if near(s, start, tol_s) and near(e, end, tol_e):
                return v
        return None

    def find_inst(key: str, end: date, tol: int = 4):
        m = inst.get(key)
        if not m:
            return None
        if end in m:
            return m[end]
        for e, v in m.items():
            if near(e, end, tol):
                return v
        return None

    annual: list[Period] = []
    quarterly: list[Period] = []
    duration_keys = [k for k, li in LINE_ITEMS.items() if li.kind == "duration"]
    instant_keys = [k for k, li in LINE_ITEMS.items() if li.kind == "instant"]

    for s, e in fiscal_years:
        p = Period("FY", s, e, e, None)
        for key in duration_keys:
            hit = find_dur(key, s, e)
            if hit:
                p.values[key], p.concepts[key], p.filed[key] = hit[2], hit[3], hit[1]
        for key in instant_keys:
            hit = find_inst(key, e)
            if hit:
                p.values[key], p.concepts[key], p.filed[key] = hit[2], hit[3], hit[1]
        if p.values:
            annual.append(p)

        # quarter ends inside the fiscal year
        q_ends: list[date] = []
        for key in ("revenue", "net_income", "operating_income", "net_interest_income", "cfo"):
            for qs, qe in list(dur.get(key, {})):
                if s < qe < e - timedelta(days=20) and (70 <= (qe - qs).days <= 100 or near(qs, s, 7)):
                    if not any(near(qe, x, 5) for x in q_ends):
                        q_ends.append(qe)
        q_ends = sorted(q_ends)[:3]
        if len(q_ends) != 3:
            continue  # cannot reliably split this year into quarters
        bounds = [s] + [q + timedelta(days=1) for q in q_ends]
        ends = q_ends + [e]
        for i in range(4):
            qp = Period("Q", bounds[i], ends[i], e, i + 1)
            for key in duration_keys:
                hit = find_dur(key, bounds[i], ends[i])
                if hit and (key in NON_ADDITIVE or 70 <= (ends[i] - bounds[i]).days <= 100):
                    qp.values[key], qp.concepts[key], qp.filed[key] = hit[2], hit[3], hit[1]
                    continue
                if key in NON_ADDITIVE:
                    continue
                ytd_now = find_dur(key, s, ends[i]) if i < 3 else find_dur(key, s, e)
                if ytd_now is None:
                    continue
                if i == 0:
                    qp.values[key], qp.concepts[key], qp.filed[key] = ytd_now[2], ytd_now[3], ytd_now[1]
                    continue
                ytd_prev = find_dur(key, s, ends[i - 1])
                if ytd_prev is None:
                    # fall back to summing previously derived quarters of this year
                    prev_q = [x for x in quarterly if x.fy_end == e and key in x.values]
                    if len(prev_q) != i:
                        continue
                    prev_val = sum(x.values[key] for x in prev_q)
                else:
                    prev_val = ytd_prev[2]
                qp.values[key] = ytd_now[2] - prev_val
                qp.concepts[key] = ytd_now[3]
                qp.filed[key] = ytd_now[1]
                qp.derived[key] = "derived from year-to-date values"
            # EPS for derived quarters (Q4 is rarely reported directly)
            if "eps_diluted" not in qp.values and "net_income" in qp.values:
                sh = qp.values.get("shares_diluted") or (
                    annual[-1].values.get("shares_diluted") if annual and annual[-1].end == e else None
                )
                if sh:
                    qp.values["eps_diluted"] = qp.values["net_income"] / sh
                    qp.derived["eps_diluted"] = "net income ÷ diluted shares"
            for key in instant_keys:
                hit = find_inst(key, ends[i])
                if hit:
                    qp.values[key], qp.concepts[key], qp.filed[key] = hit[2], hit[3], hit[1]
            if qp.values:
                quarterly.append(qp)

    # Quarters after the last completed fiscal year (current-year 10-Qs)
    if fiscal_years:
        last_s, last_e = fiscal_years[-1]
        next_s = last_e + timedelta(days=1)
        extra_ends: list[date] = []
        for key in ("revenue", "net_income", "operating_income", "net_interest_income", "cfo"):
            for qs, qe in dur.get(key, {}):
                if qe <= last_e + timedelta(days=20):
                    continue
                if near(qs, next_s, 7) or (70 <= (qe - qs).days <= 100 and qs > last_e):
                    if not any(near(qe, x, 5) for x in extra_ends):
                        extra_ends.append(qe)
        extra_ends = sorted(extra_ends)[:3]
        fy_end_guess = (
            last_e.replace(year=last_e.year + 1)
            if not (last_e.month == 2 and last_e.day == 29)
            else last_e + timedelta(days=365)
        )
        prev_bound = next_s
        for i, qe in enumerate(extra_ends):
            qp = Period("Q", prev_bound, qe, fy_end_guess, i + 1)
            for key in duration_keys:
                hit = find_dur(key, prev_bound, qe)
                if hit and (key in NON_ADDITIVE or 70 <= (qe - prev_bound).days <= 100):
                    qp.values[key], qp.concepts[key], qp.filed[key] = hit[2], hit[3], hit[1]
                    continue
                if key in NON_ADDITIVE:
                    continue
                ytd_now = find_dur(key, next_s, qe)
                if ytd_now is None:
                    continue
                if i == 0:
                    qp.values[key], qp.concepts[key], qp.filed[key] = ytd_now[2], ytd_now[3], ytd_now[1]
                    continue
                prev_q = [x for x in quarterly if x.fy_end == fy_end_guess and key in x.values]
                if len(prev_q) != i:
                    continue
                qp.values[key] = ytd_now[2] - sum(x.values[key] for x in prev_q)
                qp.concepts[key], qp.filed[key] = ytd_now[3], ytd_now[1]
                qp.derived[key] = "derived from year-to-date values"
            if (
                "eps_diluted" not in qp.values
                and "net_income" in qp.values
                and qp.values.get("shares_diluted")
            ):
                qp.values["eps_diluted"] = qp.values["net_income"] / qp.values["shares_diluted"]
                qp.derived["eps_diluted"] = "net income ÷ diluted shares"
            for key in instant_keys:
                hit = find_inst(key, qe)
                if hit:
                    qp.values[key], qp.concepts[key], qp.filed[key] = hit[2], hit[3], hit[1]
            if qp.values:
                quarterly.append(qp)
            prev_bound = qe + timedelta(days=1)

    quarterly.sort(key=lambda p: p.end)
    for p in annual + quarterly:
        derive(p)

    ttm, ttm_end, note = _ttm(annual, quarterly)
    cover: dict[str, tuple[float, date]] = {}
    for key in ("shares_outstanding_cover", "public_float", "employees"):
        m = inst.get(key)
        if m:
            end = max(m)
            cover[key] = (m[end][2], end)
    latest_bal = None
    for p in reversed(quarterly or annual):
        if "total_assets" in p.values:
            latest_bal = p.end
            break
    concepts_used: dict[str, str] = {}
    for p in annual + quarterly:
        concepts_used.update(p.concepts)
    return Financials(annual, quarterly, ttm, ttm_end, note, latest_bal, as_of, concepts_used, cover)


def _ttm(annual: list[Period], quarterly: list[Period]) -> tuple[dict[str, float], date | None, str]:
    ttm: dict[str, float] = {}
    last4 = quarterly[-4:]
    consecutive = len(last4) == 4 and all(0 < (last4[i + 1].start - last4[i].end).days <= 7 for i in range(3))
    base = last4[-1] if last4 else (annual[-1] if annual else None)
    if base is None:
        return ttm, None, "no financial statements available"
    if consecutive:
        flow_keys = {k for k, li in LINE_ITEMS.items() if li.kind == "duration" and k not in NON_ADDITIVE}
        for key in flow_keys | {"ebit", "ebitda", "fcf", "fcf_after_sbc", "gross_profit", "nopat_proxy"}:
            vals = [q.values.get(key) for q in last4]
            if all(v is not None for v in vals):
                ttm[key] = float(sum(vals))  # type: ignore[arg-type]
        note = f"trailing twelve months to {last4[-1].end.isoformat()} (sum of 4 quarters)"
        end = last4[-1].end
    else:
        a = annual[-1] if annual else None
        if a is None:
            return ttm, None, "no complete fiscal year available"
        for key, v in a.values.items():
            li = LINE_ITEMS.get(key)
            if (li and li.kind == "duration" and key not in NON_ADDITIVE) or key in (
                "ebit",
                "ebitda",
                "fcf",
                "fcf_after_sbc",
            ):
                ttm[key] = v
        note = f"latest fiscal year to {a.end.isoformat()} (quarterly data incomplete)"
        end = a.end
        last4 = []
    # non-additive and balance items from the latest period
    latest = (
        quarterly[-1]
        if quarterly and (not annual or quarterly[-1].end >= annual[-1].end)
        else (annual[-1] if annual else None)
    )
    if latest is not None:
        for key, v in latest.values.items():
            li = LINE_ITEMS.get(key)
            if li and li.kind == "instant":
                ttm[key] = v
            if key in ("total_debt", "net_debt", "tangible_equity", "working_capital", "invested_capital"):
                ttm[key] = v
    sh = None
    if last4:
        sh = last4[-1].values.get("shares_diluted")
    if sh is None and annual:
        sh = annual[-1].values.get("shares_diluted")
    if sh:
        ttm["shares_diluted"] = sh
        if "net_income" in ttm:
            ttm["eps_diluted"] = ttm["net_income"] / sh
    if last4 and all("dps" in q.values for q in last4):
        ttm["dps"] = sum(q.values["dps"] for q in last4)
    elif annual and "dps" in annual[-1].values:
        ttm["dps"] = annual[-1].values["dps"]
    return ttm, end, note


def derive(p: Period) -> None:
    v = p.values

    def put(key: str, val: float | None, how: str) -> None:
        if val is not None and key not in v:
            v[key] = val
            p.derived[key] = how

    if "gross_profit" not in v and "revenue" in v and "cost_of_revenue" in v:
        put("gross_profit", v["revenue"] - v["cost_of_revenue"], "revenue − cost of revenue")
    if "revenue" not in v and "net_interest_income" in v and "noninterest_income" in v:
        put(
            "revenue",
            v["net_interest_income"] + v["noninterest_income"],
            "net interest income + noninterest income",
        )
    if "net_interest_income" not in v and "interest_income" in v and "interest_expense" in v:
        put(
            "net_interest_income",
            v["interest_income"] - v["interest_expense"],
            "interest income − interest expense",
        )
    if "total_liabilities" not in v and "liabilities_and_equity" in v:
        eq = v.get("equity_incl_nci", v.get("equity"))
        if eq is not None:
            put("total_liabilities", v["liabilities_and_equity"] - eq, "liabilities & equity − equity")
    if "debt_total" in v:
        put("total_debt", v["debt_total"], "reported total long-term debt (incl. current portion)")
    elif "debt_noncurrent" in v or "debt_current" in v:
        put(
            "total_debt",
            v.get("debt_noncurrent", 0.0) + v.get("debt_current", 0.0),
            "current + non-current debt",
        )
    ebit = v.get("operating_income")
    if ebit is None and "pretax_income" in v and "interest_expense" in v:
        ebit = v["pretax_income"] + v["interest_expense"]
        p.derived["ebit"] = "pre-tax income + interest expense"
    if ebit is not None:
        v.setdefault("ebit", ebit)
    if "ebit" in v and "dna" in v:
        put("ebitda", v["ebit"] + v["dna"], "EBIT + D&A")
    if "cfo" in v:
        put("fcf", v["cfo"] - v.get("capex", 0.0), "operating cash flow − capex")
        if "sbc" in v:
            put(
                "fcf_after_sbc",
                v["cfo"] - v.get("capex", 0.0) - v["sbc"],
                "operating cash flow − capex − SBC",
            )
    cash = v.get("cash", 0.0) + v.get("st_investments", 0.0)
    if "cash" in v:
        v["cash_and_st"] = cash
    if "total_debt" in v:
        put("net_debt", v["total_debt"] - cash, "total debt − cash & short-term investments")
    if "equity" in v:
        put(
            "tangible_equity",
            v["equity"] - v.get("goodwill", 0.0) - v.get("intangibles", 0.0),
            "equity − goodwill − intangibles",
        )
    if "current_assets" in v and "current_liabilities" in v:
        put(
            "working_capital",
            v["current_assets"] - v["current_liabilities"],
            "current assets − current liabilities",
        )
    if "equity" in v and "total_debt" in v:
        put("invested_capital", v["equity"] + v["total_debt"] - cash, "equity + debt − cash")
