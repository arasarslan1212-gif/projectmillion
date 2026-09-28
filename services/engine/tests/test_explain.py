"""Explain: facts JSON, template narratives, the per-sentence fact check and the LLM narrative path (fake client)."""

from datetime import date
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from engine.explain import narrative
from engine.explain.facts import Fact, Facts, fmt
from engine.explain.narrative import Narrative, check_sentence
from engine.llm import client as llm
from engine.llm.validate import allowed_values, unsupported_numbers
from engine.report.builder import contexts, get_section, run_section

TICKERS = ["ZZTEC", "ZZBNK", "ZZREI", "ZZGRO", "ZZUTL", "ZZSML"]


def _facts(e: dict) -> Facts:
    F = Facts()
    F.items = {f["id"]: Fact(**f) for f in e["facts"]}
    return F


def _all_sentences(e: dict):
    for name, part in e["parts"].items():
        for mode in ("plain", "analyst"):
            for s in part.get(mode) or []:
                yield f"{name}.{mode}", s
    for c in e["cases"]:
        for mode in ("plain", "analyst"):
            for s in c[mode]:
                yield f"case.{c['name']}.{mode}", s
    for t in e["triggers"]:
        for mode in ("plain", "analyst"):
            yield f"trigger.{t['id']}.{mode}", {"text": t[mode], "facts": t["facts"]}


@pytest.mark.parametrize("ticker", TICKERS)
def test_templates_pass_the_fact_check(ticker):
    e = get_section(ticker, "explain")
    assert e["status"] in ("ok", "partial")
    assert e["method"] == "template"  # no API key in tests
    assert e["validation"]["template_problems"] == []
    F = _facts(e)
    for where, s in _all_sentences(e):
        assert check_sentence(s, F) == [], where
        assert all(fid in F.items for fid in s["facts"]), where
    for mode in ("plain", "analyst"):
        assert 3 <= len(e["verdict"][mode]) <= 4
        assert 1 <= len(e["parts"]["view"][mode]) <= 3
    assert "not investment advice" in e["disclaimer"]


def test_fact_values_match_their_sections():
    e = get_section("ZZTEC", "explain")
    F = _facts(e)
    v = get_section("ZZTEC", "valuation")
    t = get_section("ZZTEC", "trust")
    assert F.get("val.p50") == v["target"]["p50"]
    assert F.get("trust.score") == t["score"]
    band = next(x for x in e["triggers"] if x["id"] == "band")
    assert F.get("trigger.band.p90") == F.get("val.p90") and F.get("trigger.band.p10") == F.get("val.p10")
    # every Trust pillar in the path table sums to the raw score
    rows = e["parts"]["trust_path"]["table"]
    assert sum(r["points"] for r in rows) == pytest.approx(F.get("trust.raw"), abs=0.05)
    assert "val.range_coverage" in band["facts"]


def test_an_injected_wrong_number_is_caught():
    e = get_section("ZZTEC", "explain")
    F = _facts(e)
    s = dict(e["parts"]["view"]["analyst"][0])
    p50 = fmt(F.get("val.p50"), "usd_per_share")
    wrong = fmt(F.get("val.p50") * 1.07, "usd_per_share")
    assert check_sentence(s, F) == []
    bad = check_sentence({"text": s["text"].replace(p50, wrong, 1), "facts": s["facts"]}, F)
    assert bad and wrong in bad[0]
    # a true number is still rejected when the sentence does not cite the fact it comes from
    uncited = {"text": f"The model estimate is {p50}.", "facts": ["price"]}
    assert check_sentence(uncited, F)
    # unknown ids, directives and links are rejected
    assert "unknown fact ids" in check_sentence({"text": "Fine.", "facts": ["val.nope"]}, F)[0]
    assert check_sentence({"text": "You should buy this stock now.", "facts": []}, F)
    assert check_sentence({"text": "See https://example.com for more.", "facts": []}, F)


def test_validator_reads_numbers_inside_text_facts():
    facts = [
        {
            "id": "conf.data.note",
            "value": "3 of 4 valuation methods had data; 14 years of filings",
            "unit": "text",
        }
    ]
    assert unsupported_numbers("Data: 3 of 4 methods, 14 years of filings.", facts) == []
    assert unsupported_numbers("Data: 5 of 4 methods.", facts) == ["5"]
    # a numeric fact's formatted display does not widen what is allowed
    num = [{"id": "x", "value": 0.123, "unit": "pct", "display": "12.3% (was 99%)"}]
    assert (0.99, "pct") not in allowed_values(num)


def test_explain_is_point_in_time():
    as_of = date(2025, 12, 31)
    e = get_section("ZZTEC", "explain", as_of=as_of, pit=True)
    assert e["status"] in ("ok", "partial")
    for f in e["facts"]:
        if f["as_of"]:
            assert date.fromisoformat(f["as_of"][:10]) <= as_of, f["id"]
    assert e["validation"]["template_problems"] == []


# ---- LLM narrative path with a fake client -----------------------------------------------------------------------


def _resp(parsed, tin=5000, tout=1500):
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=tin, output_tokens=tout),
    )


def _from_templates(parts: dict, only: list[str], edit=None) -> Narrative:
    """A narrative that rephrases the templates (prefixing each part), for the requested parts only."""
    out = {}
    for name in narrative.PARTS:
        p = parts[name]
        modes = {}
        for mode in ("plain", "analyst"):
            sents = (
                [{"text": s["text"], "fact_ids": s["facts"]} for s in p.get(mode) or []]
                if name in only
                else []
            )
            if edit and name in only:
                sents = edit(name, mode, sents)
            modes[mode] = sents
        out[name] = modes
    return Narrative.model_validate(out)


def _requested(kw) -> list[str]:
    text = kw["messages"][0]["content"]
    line = next(x for x in text.splitlines() if x.startswith("Write these parts: "))
    return line.removeprefix("Write these parts: ").split(". ")[0].split(", ")


@pytest.fixture
def explain_ctx():
    """ZZTEC with every other section computed (templates only), and the LLM cache cleared."""
    from sqlalchemy import delete

    from engine.db import models as m
    from engine.db.session import session_scope

    with session_scope() as s:
        s.execute(delete(m.LlmCache))
    contexts.d.clear()
    ctx = contexts.get("ZZTEC", None, False)
    base = run_section(ctx, "explain")
    yield ctx, base
    llm.set_client_for_tests(None)
    contexts.d.clear()


def _rerun(ctx, client):
    llm.set_client_for_tests(client)
    ctx._sections.pop("explain", None)
    return run_section(ctx, "explain")


def test_llm_narrative_accepted_when_it_passes(explain_ctx):
    ctx, base = explain_ctx
    calls = []

    def parse(**kw):
        calls.append(kw)
        assert kw["output_format"] is Narrative and kw["thinking"] == {"type": "adaptive"}
        return _resp(_from_templates(base["parts"], _requested(kw)))

    e = _rerun(ctx, SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    assert len(calls) == 1
    assert e["method"] == "llm" and all(p["written_by"] != "template" for p in e["parts"].values())
    assert e["validation"]["failed_first"] == 0 and e["validation"]["fallback"] == []
    assert e["cost"]["calls"] == 1 and e["cost"]["usd"] > 0
    assert "<facts>" in calls[0]["messages"][0]["content"]


def test_failed_parts_are_regenerated_once_then_fall_back(explain_ctx):
    ctx, base = explain_ctx
    calls = []
    p50 = fmt(_facts(base).get("val.p50"), "usd_per_share")

    def corrupt(round_no):
        def edit(name, mode, sents):
            if name == "view" and round_no == 1 and sents:  # an invented number, fixed on the retry
                sents[0] = {
                    "text": sents[0]["text"].replace(p50, "$999.99"),
                    "fact_ids": sents[0]["fact_ids"],
                }
            if name == "against" and sents:  # a directive both times
                sents[0] = {"text": "You should buy this stock.", "fact_ids": []}
            return sents

        return edit

    def parse(**kw):
        calls.append(kw)
        return _resp(_from_templates(base["parts"], _requested(kw), corrupt(len(calls))))

    e = _rerun(ctx, SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    assert len(calls) == 2
    assert _requested(calls[1]) == ["against", "view"]  # only the failed parts are regenerated
    assert "$999.99" in calls[1]["messages"][0]["content"]  # the problems are fed back
    v = e["validation"]
    assert v["regenerated"] == ["against", "view"] and v["fallback"] == ["against"]
    assert e["method"] == "mixed"
    assert e["parts"]["against"]["written_by"] == "template"
    assert e["parts"]["against"]["plain"] == base["parts"]["against"]["plain"]
    assert e["parts"]["view"]["written_by"] != "template"
    assert all("$999.99" not in s["text"] for s in e["parts"]["view"]["analyst"])


def test_api_failure_keeps_templates(explain_ctx):
    ctx, base = explain_ctx

    def parse(**kw):
        raise anthropic.APIConnectionError(
            request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        )

    e = _rerun(ctx, SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    assert e["method"] == "template"
    assert e["parts"]["verdict"]["plain"] == base["parts"]["verdict"]["plain"]
    assert e["cost"]["errors"] == ["could not reach the Claude API"]
