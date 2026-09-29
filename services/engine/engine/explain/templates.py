"""Template narratives for every Explain part, in Plain and Analyst modes.

These are always computed. They are what the app shows without an LLM, and the fallback for any part whose LLM text
fails validation. Each sentence cites the fact ids its numbers come from, so templates pass the same number validator
as model text (a test enforces it).
"""

from __future__ import annotations

from engine.explain.facts import Facts, fmt

PILLAR_PLAIN = {
    "financial_health": "its balance sheet",
    "earnings_quality": "the quality of its reported earnings",
    "profitability": "profitability",
    "growth": "growth",
    "valuation": "price relative to value",
    "momentum": "share-price momentum",
    "sentiment": "news and insider sentiment",
    "analyst": "analyst views",
    "management": "management's track record",
    "risk": "stability of the share price",
}


def S(text: str, *facts: str) -> dict:
    return {"text": text, "facts": [f for f in facts if f]}


def _pillars(F: Facts) -> list[tuple[str, float]]:
    out = []
    for fid, f in F.items.items():
        if fid.startswith("trust.pillar.") and fid.count(".") == 2:
            out.append((fid.split(".")[2], float(f.value)))
    return sorted(out, key=lambda x: -x[1])


def _label(F: Facts, fid: str) -> str:
    f = F.items.get(fid)
    return f.label.replace(" pillar score", "") if f else fid


def _lc(label: str) -> str:
    """Lower-case a label for use mid-sentence, keeping acronyms ("ROE", "DCF") intact."""
    words = str(label).split(" ")
    return " ".join(w if sum(c.isupper() for c in w) > 1 else w.lower() for w in words)


def _n_flags(F: Facts) -> tuple[int, list[str]]:
    flags = [fid for fid in F.items if fid.startswith("flag.")]
    n = int(F.get("risk.n_flags") or len(flags))
    return n, ["risk.n_flags", *flags] if F.has("risk.n_flags") else flags


_NO_HISTORY = "no history to compare"
_IN_LINE = "in line with history and expectations"


def _implied(F: Facts, plain: bool) -> str:
    """What the reverse valuation solved for, phrased for its basis (ROE, first-year revenue growth or FCF growth)."""
    label = F.items["val.rdcf.implied"].label.lower()
    x = fmt(F.get("val.rdcf.implied"), "pct")
    if "return on equity" in label:
        return (
            f"a return on equity of about {x} a year" if plain else f"a sustainable return on equity of {x}"
        )
    if "revenue" in label:
        return (f"sales growth of about {x} next year, slowing after that" if plain
                else f"first-year revenue growth of {x}, fading thereafter")  # fmt: skip
    return (
        f"cash-flow growth of about {x} a year for a decade"
        if plain
        else f"free-cash-flow growth of {x} a year"
    )


def _judged(F: Facts, plain: bool) -> str:
    ass = F.get("val.rdcf.assessment")
    refs = "the company's record" + (" and analysts' forecasts" if F.has("val.rdcf.consensus") else "")
    if ass == _NO_HISTORY:
        return ("; there is too little history to judge whether that is realistic." if plain
                else "; there is no delivered history or consensus to compare it with.")  # fmt: skip
    if ass == _IN_LINE:
        return f", which is in line with {refs}."
    return (
        f", which the app rates as {ass} next to {refs}." if plain else f", which looks {ass} against {refs}."
    )


_TREND = {"improving": "getting better", "deteriorating": "getting worse", "stable": "steady"}


def view(F: Facts) -> dict:
    p, pl = [], []
    if F.has("val.p50", "val.p10", "val.p90", "price", "val.implied_return"):
        p50, p10, p90, px, ir = (
            F.get(k) for k in ("val.p50", "val.p10", "val.p90", "price", "val.implied_return")
        )
        pl.append(S(
            f"The app's model puts the share price 12 months from now at about {fmt(p50, 'usd_per_share')}, against "
            f"{fmt(px, 'usd_per_share')} today, and treats anything from {fmt(p10, 'usd_per_share')} to "
            f"{fmt(p90, 'usd_per_share')} as a reasonable outcome.",
            "val.p50", "price", "val.p10", "val.p90", "val.horizon_months",
        ))  # fmt: skip
        p.append(S(
            f"The app's 12-month model estimate is {fmt(p50, 'usd_per_share')} (80% range {fmt(p10, 'usd_per_share')}–"
            f"{fmt(p90, 'usd_per_share')}), {fmt(ir, 'pct', signed=True)} from {fmt(px, 'usd_per_share')}"
            + (f", with {str(F.get('conf.level')).lower()} confidence ({fmt(F.get('conf.score'), 'score')}/100)."
               if F.has("conf.score", "conf.level") else "."),
            "val.p50", "val.p10", "val.p90", "val.implied_return", "price", "val.range_coverage", "val.horizon_months",
            "conf.score" if F.has("conf.score") else "", "conf.level" if F.has("conf.level") else "",
        ))  # fmt: skip
    ps = _pillars(F)
    if F.has("trust.score", "trust.grade") and ps:
        hi, lo = ps[0], ps[-1]
        pl.append(S(
            f"As a business it scores {fmt(F.get('trust.score'), 'score')} out of 100 ({F.get('trust.grade')}): "
            f"strongest on {PILLAR_PLAIN.get(hi[0], hi[0])}, weakest on {PILLAR_PLAIN.get(lo[0], lo[0])}.",
            "trust.score", "trust.grade", f"trust.pillar.{hi[0]}", f"trust.pillar.{lo[0]}",
        ))  # fmt: skip
        p.append(S(
            f"The Trust Rating is {fmt(F.get('trust.score'), 'score')}/100 ({F.get('trust.grade')}); the strongest pillar is "
            f"{_lc(_label(F, f'trust.pillar.{hi[0]}'))} ({fmt(hi[1], 'score')}) and the weakest "
            f"{_lc(_label(F, f'trust.pillar.{lo[0]}'))} ({fmt(lo[1], 'score')}).",
            "trust.score", "trust.grade", f"trust.pillar.{hi[0]}", f"trust.pillar.{lo[0]}",
        ))  # fmt: skip
    if F.has("val.rdcf.implied", "val.rdcf.assessment"):
        refs = [k for k in ("val.rdcf.history", "val.rdcf.consensus") if F.has(k)]
        pl.append(S(f"Today's price already assumes {_implied(F, True)}{_judged(F, True)}",
                    "val.rdcf.implied", "val.rdcf.assessment", *refs))  # fmt: skip
        p.append(S(f"The market price implies {_implied(F, False)}{_judged(F, False)}",
                   "val.rdcf.implied", "val.rdcf.assessment", *refs))  # fmt: skip
    elif F.has("conf.level"):
        pl.append(
            S(f"The app's confidence in this estimate is {str(F.get('conf.level')).lower()}.", "conf.level")
        )
    return {"plain": pl[:3], "analyst": p[:3]}


def verdict(F: Facts) -> dict:
    v = view(F)
    plain, analyst = list(v["plain"][:2]), list(v["analyst"][:2])
    if F.has("an.consensus_trusted", "an.upside_trusted"):
        tc, up = F.get("an.consensus_trusted"), F.get("an.upside_trusted")
        plain.append(S(
            f"Analysts with the best track records expect about {fmt(tc, 'usd_per_share')} on average "
            f"({fmt(up, 'pct', signed=True)} from today).",
            "an.consensus_trusted", "an.upside_trusted",
        ))  # fmt: skip
        analyst.append(S(
            f"The trusted analyst consensus is {fmt(tc, 'usd_per_share')} ({fmt(up, 'pct', signed=True)}).",
            "an.consensus_trusted", "an.upside_trusted",
        ))  # fmt: skip
    n_flags, flag_facts = _n_flags(F)
    if n_flags:
        sfx = "s" if n_flags != 1 else ""
        plain.append(
            S(f"The app found {n_flags} warning sign{sfx} worth checking in the risk section.", *flag_facts)
        )
        analyst.append(S(f"{n_flags} red flag{sfx} fired; see Risk.", *flag_facts))
    elif F.has("news.sentiment_30d"):
        s30, trend = F.get("news.sentiment_30d"), F.get("news.trend")
        tr = _TREND.get(str(trend))
        plain.append(S(f"Recent news has been {_tone(s30)}" + (f", and the tone is {tr}." if tr else "."),
                       "news.sentiment_30d", "news.trend" if tr else ""))  # fmt: skip
        analyst.append(S(f"30-day news sentiment is {fmt(s30, 'ratio')}" + (f" ({trend} vs. the prior 30 days)." if tr else "."),
                         "news.sentiment_30d", "news.trend" if tr else ""))  # fmt: skip
    return {"plain": plain[:4], "analyst": analyst[:4]}


def _tone(s: float) -> str:
    return "positive" if s >= 0.1 else "negative" if s <= -0.1 else "mostly neutral"


def trust_path(F: Facts, trust: dict | None) -> dict:
    if not F.has("trust.score"):
        return {"plain": [], "analyst": [], "table": []}
    table = []
    for p in (trust or {}).get("pillars", []):
        if p.get("score") is None:
            continue
        table.append({
            "id": p["id"], "label": p["label"], "score": p["score"], "weight": p.get("effective_weight"),
            "points": (p.get("effective_weight") or 0) * p["score"],
            "metrics": [{"id": m["id"], "label": m["label"], "value": m["value"], "unit": m.get("unit"), "score": m["score"]}
                        for m in p.get("metrics") or [] if m.get("score") is not None],
            "facts": [f"trust.pillar.{p['id']}", f"trust.pillar.{p['id']}.weight", f"trust.pillar.{p['id']}.points"],
        })  # fmt: skip
    top = sorted(table, key=lambda r: -r["points"])[:2]
    ded = F.get("trust.deductions") or 0
    analyst = [S(
        "Each metric is scored 0–100 against sector percentiles or fixed anchors; each pillar averages its metrics, and "
        f"the pillars are weighted to give {fmt(F.get('trust.raw'), 'score', 1)}"
        + (f", less {fmt(ded, 'score')} points of red-flag deductions" if ded else "")
        + f", for a Trust Rating of {fmt(F.get('trust.score'), 'score')}.",
        "trust.raw", "trust.score", "trust.deductions" if ded else "",
    )]  # fmt: skip
    if top:
        analyst.append(S(
            "The largest contributions come from "
            + " and ".join(f"{_lc(r['label'])} ({fmt(r['points'], 'score', 1)} points at {fmt(r['weight'], 'pct', 0)} weight)" for r in top)
            + ".",
            *[f for r in top for f in (f"trust.pillar.{r['id']}.points", f"trust.pillar.{r['id']}.weight")],
        ))  # fmt: skip
    plain = [S(
        "The Trust Rating adds up ten report cards (balance sheet, profitability, growth and so on), each graded against "
        f"similar companies, into one score of {fmt(F.get('trust.score'), 'score')} out of 100.",
        "trust.score",
    )]  # fmt: skip
    if ded:
        plain.append(S(f"Warning signs cost it {fmt(ded, 'score')} points.", "trust.deductions"))
    return {"plain": plain, "analyst": analyst, "table": table}


def target_path(F: Facts, val: dict | None) -> dict:
    if not F.has("val.p50"):
        return {"plain": [], "analyst": [], "table": []}
    table = [
        {"id": b["id"], "label": b["label"], "value": b["value"], "weight": b["weight"], "target_12m": b["target_12m"],
         "facts": [f"val.method.{b['id']}.value", f"val.method.{b['id']}.weight", f"val.method.{b['id']}.target"]}
        for b in (val or {}).get("blend", [])
    ]  # fmt: skip
    lead = max(table, key=lambda r: r["weight"]) if table else None
    analyst = [S(
        f"Each method's long-term value is converted to a 12-month figure by assuming the price earns its "
        f"{fmt(F.get('val.cost_of_equity'), 'pct')} cost of equity net of dividends and closes "
        f"{fmt(F.get('val.convergence'), 'pct', 0)} of the gap to that value; the weighted blend of those figures is "
        f"{fmt(F.get('val.p50'), 'usd_per_share')}.",
        "val.cost_of_equity", "val.convergence", "val.p50", "val.horizon_months",
    )]  # fmt: skip
    if lead:
        analyst.append(S(
            f"The heaviest-weighted method is {_lc(lead['label'])} ({fmt(lead['weight'], 'pct', 0)}, "
            f"{fmt(lead['value'], 'usd_per_share')} long-term, {fmt(lead['target_12m'], 'usd_per_share')} in 12 months).",
            *lead["facts"],
        ))  # fmt: skip
    if F.has("val.sigma_market", "val.sigma_total"):
        analyst.append(S(
            f"The 80% range comes from market volatility of {fmt(F.get('val.sigma_market'), 'pct', 0)} a year plus "
            f"disagreement between methods, widened for confidence"
            + (f" and scaled by {fmt(F.get('val.calibration_scale'), 'x', 2)} by the track-record recalibration"
               if F.has("val.calibration_scale") else "")
            + f" to a total of {fmt(F.get('val.sigma_total'), 'pct', 0)}.",
            "val.range_coverage", "val.sigma_market", "val.sigma_total",
            "val.calibration_scale" if F.has("val.calibration_scale") else "",
        ))  # fmt: skip
    plain = [S(
        f"The app values the company {fmt(F.get('val.n_methods'), 'count')} different ways and averages them, giving "
        f"more say to the methods that suit this kind of company; the result is {fmt(F.get('val.p50'), 'usd_per_share')}.",
        "val.n_methods", "val.p50",
    )]  # fmt: skip
    if lead:
        plain.append(S(
            f"The method with the most say ({_lc(lead['label'])}) on its own points to "
            f"{fmt(lead['target_12m'], 'usd_per_share')} a year from now.",
            f"val.method.{lead['id']}.target", f"val.method.{lead['id']}.label",
        ))  # fmt: skip
    return {"plain": plain, "analyst": analyst, "table": table}


def cases(F: Facts) -> list[dict]:
    out = []
    names = [n for n in ("bear", "base", "bull") if F.has(f"val.scenario.{n}.value")]
    for n in names:
        b = f"val.scenario.{n}"
        val, prob = F.get(f"{b}.value"), F.get(f"{b}.probability")
        assumptions = []
        for k, label in (("growth1", "near-term revenue growth"), ("margin_target", "target operating margin"),
                         ("roe", "return on equity"), ("wacc", "WACC"), ("cost_of_equity", "cost of equity")):  # fmt: skip
            if F.has(f"{b}.{k}"):
                assumptions.append((k, label, F.get(f"{b}.{k}")))
        a_txt = ", ".join(f"{label} {fmt(v, 'pct')}" for _, label, v in assumptions)
        facts = [f"{b}.value", f"{b}.probability"] + [f"{b}.{k}" for k, _, _ in assumptions]
        plain_word = {
            "bear": "If things go badly",
            "base": "In the middle case",
            "bull": "If things go well",
        }[n]
        out.append(
            {
                "name": n,
                "value": val,
                "probability": prob,
                "assumptions": [{"id": k, "label": lb, "value": v} for k, lb, v in assumptions],
                "facts": facts,
                "plain": [
                    S(
                        f"{plain_word}, the model's long-term value is {fmt(val, 'usd_per_share')}; the app gives this case "
                        f"roughly a {fmt(prob, 'pct', 0)} weight.",
                        f"{b}.value",
                        f"{b}.probability",
                    )
                ],  # fmt: skip
                "analyst": [
                    S(
                        f"{n.title()} case: {a_txt}; value {fmt(val, 'usd_per_share')}, probability {fmt(prob, 'pct', 0)}.",
                        *facts,
                    )
                ],  # fmt: skip
            }
        )
    return out


def pricing_in(F: Facts) -> dict:
    if not F.has("val.rdcf.statement"):
        return {"plain": [], "analyst": []}
    analyst = [S(F.get("val.rdcf.statement"), "val.rdcf.statement", "val.rdcf.implied")]
    refs = [k for k in ("val.rdcf.history", "val.rdcf.consensus", "val.rdcf.trailing") if F.has(k)]
    if refs and F.has("val.rdcf.assessment") and F.get("val.rdcf.assessment") != _NO_HISTORY:
        analyst.append(S(
            f"Against {', '.join(_lc(F.items[k].label) + ' of ' + fmt(F.get(k), 'pct') for k in refs)}, that looks "
            f"{F.get('val.rdcf.assessment')}.", *refs, "val.rdcf.assessment",
        ))  # fmt: skip
    plain = []
    if F.has("val.rdcf.implied", "val.rdcf.assessment"):
        plain.append(S(
            f"Working backwards from today's price, buyers are paying for {_implied(F, True)}{_judged(F, True)}",
            "val.rdcf.implied", "val.rdcf.assessment", *[k for k in ("val.rdcf.history", "val.rdcf.consensus") if F.has(k)],
        ))  # fmt: skip
    return {"plain": plain, "analyst": analyst}


def drivers(F: Facts) -> dict:
    analyst, plain, items = [], [], []
    for i in range(3):
        if not F.has(f"val.driver.{i}.label", f"val.driver.{i}.low", f"val.driver.{i}.high"):
            break
        lab, d, lo, hi = (F.get(f"val.driver.{i}.{k}") for k in ("label", "delta", "low", "high"))
        items.append({"label": lab, "delta": d, "low": lo, "high": hi})
        fids = [
            f"val.driver.{i}.label",
            f"val.driver.{i}.delta",
            f"val.driver.{i}.low",
            f"val.driver.{i}.high",
        ]
        analyst.append(S(
            f"{lab}: ±{fmt(d, 'pct')} moves the DCF value between {fmt(min(lo, hi), 'usd_per_share')} and "
            f"{fmt(max(lo, hi), 'usd_per_share')}.", *fids,
        ))  # fmt: skip
        if i == 0:
            plain.append(S(
                f"The single assumption that matters most is {_lc(lab)}: small changes to it move the model's value "
                f"between {fmt(min(lo, hi), 'usd_per_share')} and {fmt(max(lo, hi), 'usd_per_share')}.", *fids,
            ))  # fmt: skip
    if F.has("val.dcf.terminal_share"):
        analyst.append(S(
            f"{fmt(F.get('val.dcf.terminal_share'), 'pct', 0)} of the DCF value sits beyond the "
            f"{fmt(F.get('val.dcf.years'), 'count')}-year forecast, in the terminal value.",
            "val.dcf.terminal_share", "val.dcf.years",
        ))  # fmt: skip
    if not items and F.has("val.n_methods"):
        plain.append(
            S(
                "For this kind of company the app relies on comparisons with peers and history rather than a cash-flow forecast.",
                "val.n_methods",
            )
        )
        analyst.append(
            S(
                "No DCF applies to this profile, so the target moves most with the peer and history multiples and the equity-return model.",
                "val.n_methods",
            )
        )
    return {"plain": plain, "analyst": analyst, "items": items}


def against(F: Facts) -> dict:
    """Steelman the opposite of the app's view, using only facts."""
    ir = F.get("val.implied_return")
    if ir is None:
        return {"plain": [], "analyst": [], "stance": None}
    bearish = ir < 0
    pts: list[tuple[str, str, list[str]]] = []  # (plain, analyst, facts)
    pillars = _pillars(F)
    if bearish:
        strong = [p for p in pillars if p[1] >= 65][:2]
        for pid, sc in strong:
            pts.append((f"it scores well on {PILLAR_PLAIN.get(pid, pid)}",
                        f"{_label(F, f'trust.pillar.{pid}').lower()} scores {fmt(sc, 'score')}", [f"trust.pillar.{pid}"]))  # fmt: skip
        if (F.get("an.upside_trusted") or 0) > 0:
            pts.append(("the analysts with the best records see the price going up",
                        f"the trusted consensus implies {fmt(F.get('an.upside_trusted'), 'pct', signed=True)}", ["an.upside_trusted"]))  # fmt: skip
        if (F.get("news.sentiment_30d") or 0) >= 0.1:
            pts.append(("recent news has been positive", f"30-day news sentiment is {fmt(F.get('news.sentiment_30d'), 'ratio')}",
                        ["news.sentiment_30d"]))  # fmt: skip
        if (F.get("earn.beat_rate") or 0) >= 0.75:
            pts.append(("it usually beats earnings expectations", f"it beat EPS estimates {fmt(F.get('earn.beat_rate'), 'pct', 0)} of the time",
                        ["earn.beat_rate"]))  # fmt: skip
        if (F.get("own.clusters") or 0) > 0:
            pts.append(
                (
                    "several insiders have bought shares together",
                    "insiders made a cluster purchase",
                    ["own.clusters"],
                )
            )
        if (F.get("val.prob_up") or 0) > 0.3:
            pts.append((f"even the app gives a {fmt(F.get('val.prob_up'), 'prob', 0)} chance of the price being higher in a year",
                        f"the model's own probability of a higher price is {fmt(F.get('val.prob_up'), 'prob', 0)}", ["val.prob_up"]))  # fmt: skip
    else:
        weak = [p for p in reversed(pillars) if p[1] <= 45][:2]
        for pid, sc in weak:
            pts.append((f"it scores poorly on {PILLAR_PLAIN.get(pid, pid)}",
                        f"{_label(F, f'trust.pillar.{pid}').lower()} scores only {fmt(sc, 'score')}", [f"trust.pillar.{pid}"]))  # fmt: skip
        n_flags, flag_facts = _n_flags(F)
        if n_flags:
            pts.append(("the app found warning signs", f"{n_flags} red flag{'s' if n_flags != 1 else ''} fired",
                        flag_facts))  # fmt: skip
        if (F.get("an.upside_trusted") or 0) < 0:
            pts.append(("the analysts with the best records see the price falling",
                        f"the trusted consensus implies {fmt(F.get('an.upside_trusted'), 'pct', signed=True)}", ["an.upside_trusted"]))  # fmt: skip
        if (F.get("news.sentiment_30d") or 0) <= -0.1:
            pts.append(("recent news has been negative", f"30-day news sentiment is {fmt(F.get('news.sentiment_30d'), 'ratio')}",
                        ["news.sentiment_30d"]))  # fmt: skip
        if (F.get("val.prob_drawdown_20") or 0) >= 0.4:
            pts.append((f"there is a {fmt(F.get('val.prob_drawdown_20'), 'prob', 0)} chance of a 20% fall along the way",
                        f"the path simulation puts a 20% drawdown at {fmt(F.get('val.prob_drawdown_20'), 'prob', 0)}",
                        ["val.prob_drawdown_20"]))  # fmt: skip
    if not pts:
        pts.append(
            (
                "the model's inputs could simply be wrong",
                "the model's assumptions may be wrong in ways its range does not capture",
                [],
            )
        )
    view_word = "fall" if bearish else "rise"
    opp = "rise" if bearish else "fall"
    plain = [S(f"The app leans towards the price being more likely to {view_word}. The best case for it to {opp} "
               "instead: " + "; ".join(p[0] for p in pts[:4]) + ".",
               *[f for p in pts[:4] for f in p[2]])]  # fmt: skip
    analyst = [S(f"The strongest case against the app's view that the price is more likely to {view_word}: "
                 + "; ".join(p[1] for p in pts[:4]) + ".",
                 *[f for p in pts[:4] for f in p[2]])]  # fmt: skip
    return {"plain": plain, "analyst": analyst, "stance": "bearish" if bearish else "bullish"}


def confidence(F: Facts) -> dict:
    if not F.has("conf.score", "conf.level"):
        return {"plain": [], "analyst": []}
    comps = sorted(
        ((fid.split(".")[1], F.get(fid)) for fid in F.items if fid.startswith("conf.") and fid.count(".") == 1
         and fid not in ("conf.score", "conf.level")),
        key=lambda x: x[1],
    )  # fmt: skip
    lo, hi = comps[0], comps[-1]
    analyst = [S(
        f"Confidence is {fmt(F.get('conf.score'), 'score')}/100 ({F.get('conf.level')}): highest on "
        f"{hi[0].replace('_', ' ')} ({F.get(f'conf.{hi[0]}.note') or fmt(hi[1], 'score')}), lowest on "
        f"{lo[0].replace('_', ' ')} ({F.get(f'conf.{lo[0]}.note') or fmt(lo[1], 'score')}).",
        "conf.score", "conf.level", f"conf.{hi[0]}", f"conf.{hi[0]}.note", f"conf.{lo[0]}", f"conf.{lo[0]}.note",
    )]  # fmt: skip
    plain = [S(
        f"The app is {_CONF_WORD.get(str(F.get('conf.level')), 'somewhat')} confident. It helps that {_plain_conf(hi[0], True)}; it hurts "
        f"that {_plain_conf(lo[0], False)}.",
        "conf.level", f"conf.{hi[0]}", f"conf.{lo[0]}",
    )]  # fmt: skip
    return {"plain": plain, "analyst": analyst}


_CONF_WORD = {"High": "quite", "Medium": "moderately", "Low": "not very"}


def _plain_conf(cid: str, good: bool) -> str:
    return {
        "agreement": (
            "the different valuation methods roughly agree",
            "the valuation methods disagree a lot",
        ),
        "data": ("the data is complete and recent", "some data is missing or old"),
        "predictability": ("the business has been steady", "results have been hard to predict"),
        "volatility": ("the share price is fairly calm", "the share price swings a lot"),
        "analyst_dispersion": ("analysts broadly agree", "analysts disagree with each other"),
        "calibration": (
            "similar past estimates held up",
            "there is little track record for stocks like this",
        ),
    }.get(cid, ("this factor looks good", "this factor looks weak"))[0 if good else 1]


def gaps(F: Facts) -> list[dict]:
    out = []
    for fid, f in F.items.items():
        if f.group == "gaps":
            out.append({"id": fid, "label": f.label, "text": str(f.value), "facts": [fid]})
    return out


def premortem(F: Facts) -> dict:
    """ "It is 12 months later and the stock fell 40%: the likeliest reasons", ranked from today's facts.

    A thought exercise, not a forecast: every reason is a weakness already visible in the data."""
    if not F.has("premortem.fall", "price"):
        return {"plain": [], "analyst": [], "reasons": []}
    cands: list[tuple[float, str, str, list[str]]] = []  # (priority, plain, analyst, facts)
    px = F.get("price")
    if F.get("val.rdcf.assessment") == "demanding" and F.has("val.rdcf.implied"):
        refs = [k for k in ("val.rdcf.history", "val.rdcf.consensus") if F.has(k)]
        cands.append((9, f"The price already assumed {_implied(F, True)}; the business fell short of that, and "
                         "the market stopped paying for it.",
                      f"The price implied {_implied(F, False)}, above the company's record; delivery closer to history "
                      "would compress the multiple.", ["val.rdcf.implied", "val.rdcf.assessment", *refs]))  # fmt: skip
    bear = F.get("val.scenario.bear.value")
    if (
        bear is not None and px and 0.05 * px < bear < 0.8 * px
    ):  # a near-zero bear value is a degenerate model
        cands.append((8, f"Things went the way of the app's bear case, where the model's long-term value is "
                         f"{fmt(bear, 'usd_per_share')} against {fmt(px, 'usd_per_share')} today.",
                      f"The bear scenario's value of {fmt(bear, 'usd_per_share')} (vs. {fmt(px, 'usd_per_share')}) played "
                      "out.", ["val.scenario.bear.value", "price"]))  # fmt: skip
    n_flags, flag_facts = _n_flags(F)
    if n_flags:
        first = next((fid for fid in F.items if fid.startswith("flag.")), None)
        title = f"“{F.items[first].label.replace('Red flag: ', '')}”" if first else "a warning sign"
        cands.append((7 + min(n_flags, 3), f"Warning signs the app flagged today ({title} among them) turned into real "
                                           "problems.",
                      f"{n_flags} red flag{'s' if n_flags != 1 else ''} (including {title}) materialized.",
                      flag_facts))  # fmt: skip
    for pid, sc in [p for p in reversed(_pillars(F)) if p[1] <= 35][:2]:
        cands.append((6 + (35 - sc) / 35, f"Weakness in {PILLAR_PLAIN.get(pid, pid)} (score {fmt(sc, 'score')}) left "
                                          "little room for error.",
                      f"The weak {_lc(_label(F, f'trust.pillar.{pid}'))} pillar ({fmt(sc, 'score')}) proved decisive.",
                      [f"trust.pillar.{pid}"]))  # fmt: skip
    lev = F.get("metric.net_debt_to_ebitda")
    if lev is not None and lev >= 3:
        cands.append((7, f"Debt of {fmt(lev, 'x')} a year's operating cash earnings magnified a drop in profits.",
                      f"Leverage of {fmt(lev, 'x')} net debt ÷ EBITDA amplified an earnings decline.",
                      ["metric.net_debt_to_ebitda"]))  # fmt: skip
    dd = F.get("risk.max_drawdown_3y")
    if dd is not None and dd <= -0.35:
        cands.append((6, f"A fall this size is not unusual for this stock: it dropped {fmt(abs(dd), 'pct', 0)} from a "
                         "peak within the last three years.",
                      f"A three-year maximum drawdown of {fmt(abs(dd), 'pct', 0)} shows falls of this size are within "
                      "its recent range.", ["risk.max_drawdown_3y"]))  # fmt: skip
    ts = F.get("val.dcf.terminal_share")
    if ts is not None and ts >= 0.7:
        cands.append((5, f"Most of the value ({fmt(ts, 'pct', 0)}) depends on results more than ten years away, so a "
                         "small change in long-run expectations cut it sharply.",
                      f"With {fmt(ts, 'pct', 0)} of DCF value in the terminal period, a modest de-rating of long-run "
                      "assumptions has an outsized effect.", ["val.dcf.terminal_share"]))  # fmt: skip
    if F.has("val.driver.0.label", "val.driver.0.low", "val.driver.0.high"):
        lab, lo, hi = (F.get(f"val.driver.0.{k}") for k in ("label", "low", "high"))
        cands.append((4, f"{lab} came in at the weak end of the range, which on its own takes the model's value to "
                         f"{fmt(min(lo, hi), 'usd_per_share')}.",
                      f"{lab} at the low end of its sensitivity range cuts the DCF value to "
                      f"{fmt(min(lo, hi), 'usd_per_share')}.",
                      ["val.driver.0.label", "val.driver.0.low", "val.driver.0.high"]))  # fmt: skip
    up = F.get("an.upside_trusted")
    if up is not None and up < -0.05:
        cands.append((4, f"The analysts with the best records were right: they already expected a lower price "
                         f"({fmt(up, 'pct', signed=True)}).",
                      f"The trusted consensus ({fmt(up, 'pct', signed=True)}) was the better guide.",
                      ["an.upside_trusted"]))  # fmt: skip
    si = F.get("own.short_pct")
    if si is not None and si >= 0.08:
        cands.append((4, f"Short sellers, who held {fmt(si, 'pct')} of the tradable shares, were proved right.",
                      f"Short interest of {fmt(si, 'pct')} of float reflected a bearish view that played out.",
                      ["own.short_pct"]))  # fmt: skip
    sc3 = F.get("own.share_change_3y")
    if sc3 is not None and sc3 >= 0.03:
        cands.append((3, f"The company kept issuing shares ({fmt(sc3, 'pct', signed=True)} a year), shrinking each "
                         "holder's slice.",
                      f"Dilution of {fmt(sc3, 'pct', signed=True)} a year eroded per-share value.",
                      ["own.share_change_3y"]))  # fmt: skip
    br = F.get("earn.beat_rate")
    if br is not None and br <= 0.5:
        cands.append((3, f"Results kept missing expectations, as they did in {fmt(br, 'pct', 0)} beats out of recent "
                         "quarters.",
                      f"A weak EPS beat rate ({fmt(br, 'pct', 0)}) continued.", ["earn.beat_rate"]))  # fmt: skip
    cands.sort(key=lambda c: -c[0])
    top = cands[:4]
    intro_p = S("Imagine it is 12 months from now and the stock has fallen 40%. Based on what the data shows today, "
                "the likeliest explanations are:", "premortem.fall", "val.horizon_months")  # fmt: skip
    intro_a = S("Pre-mortem, assuming a 40% decline over 12 months; most likely causes given current facts:",
                "premortem.fall", "val.horizon_months")  # fmt: skip
    if not top:
        vol = F.get("risk.volatility_1y")
        tail = (S(f"No specific weakness stands out; with volatility of {fmt(vol, 'pct', 0)} a year, a fall this large "
                  "would most likely come from the whole market or from news the data cannot anticipate.",
                  "risk.volatility_1y") if vol is not None
                else S("No specific weakness stands out; a fall this large would most likely come from the whole "
                       "market or from news the data cannot anticipate."))  # fmt: skip
        return {"plain": [intro_p, tail], "analyst": [intro_a, tail], "reasons": []}
    tail_facts = ["val.prob_drawdown_20"] if F.has("val.prob_drawdown_20") else []
    tail = (
        [S(f"For scale: the app's simulation gives a {fmt(F.get('val.prob_drawdown_20'), 'prob', 0)} chance of a 20% "
           "fall at some point in the next year.", *tail_facts)]
        if tail_facts else []
    )  # fmt: skip
    return {
        "plain": [intro_p, *[S(c[1], *c[3]) for c in top], *tail],
        "analyst": [intro_a, *[S(c[2], *c[3]) for c in top], *tail],
        "reasons": [{"plain": c[1], "analyst": c[2], "facts": c[3]} for c in top],
    }
