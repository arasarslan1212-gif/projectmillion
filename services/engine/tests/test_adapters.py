"""Adapters parse each provider's documented response shape (served by the synthetic transport)."""

from datetime import date

from engine.providers.finnhub import Finnhub
from engine.providers.finra import Finra
from engine.providers.fmp import Fmp
from engine.providers.fred import Fred
from engine.providers.massive import MassiveBenzinga
from engine.providers.models import Filing
from engine.providers.sec_edgar import SecEdgar, html_to_text, parse_form4
from engine.providers.tiingo import Tiingo


def test_sec_symbols_meta_filings_facts():
    sec = SecEdgar()
    syms = {s.ticker: s for s in sec.all_symbols()}
    assert syms["ZZTEC"].cik == 9900001
    meta = sec.company_meta(9900001)
    assert meta.sic == 3571 and meta.is_synthetic
    filings = sec.filings(9900001)
    forms = {f.form for f in filings}
    assert {"10-K", "10-Q", "8-K", "4"} <= forms
    assert any("2.02" in f.items for f in filings if f.form == "8-K")
    facts = sec.company_facts(9900001)
    assert any(f.concept == "RevenueFromContractWithCustomerExcludingAssessedTax" for f in facts)
    assert all(f.filed >= f.end for f in facts if f.form in ("10-K", "10-Q"))


def test_sec_frames_and_sic_universe():
    sec = SecEdgar()
    pts = sec.frame("Revenues", "USD", "CY2025")
    assert len(pts) > 10 and all(p.value > 0 for p in pts)
    ciks = sec.ciks_for_sic(6021)
    assert 9900002 in ciks


def test_split_normalization_matches_between_providers():
    t = Tiingo().history("ZZTEC", date(2020, 8, 24), date(2020, 9, 4))
    f = Fmp().history("ZZTEC", date(2020, 8, 24), date(2020, 9, 4))
    assert [round(b.close, 2) for b in t.bars] == [round(b.close, 2) for b in f.bars]
    assert any(a.kind == "split" and a.value == 4.0 for a in t.actions)
    # continuity across the split date (no 4x jump)
    closes = [b.close for b in t.bars]
    assert max(closes) / min(closes) < 1.2


def test_form4_parsing_codes_and_plan_flag():
    xml = """<?xml version="1.0"?><ownershipDocument><aff10b5One>1</aff10b5One>
    <reportingOwner><reportingOwnerId><rptOwnerCik>0000000001</rptOwnerCik><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer><officerTitle>CFO</officerTitle></reportingOwnerRelationship></reportingOwner>
    <nonDerivativeTable><nonDerivativeTransaction><transactionDate><value>2026-01-05</value></transactionDate>
    <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
    <transactionAmounts><transactionShares><value>1,000</value></transactionShares><transactionPricePerShare><value>50.5</value></transactionPricePerShare>
    <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
    <postTransactionAmounts><sharesOwnedFollowingTransaction><value>9000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
    </nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""
    f = Filing(accession="1-26-1", cik=1, form="4", filed_at=date(2026, 1, 7))
    txs = parse_form4(xml, "XYZ", f, None)
    assert len(txs) == 1
    t = txs[0]
    assert (t.code, t.acquired, t.shares, t.price, t.plan_10b5_1, t.role) == (
        "S",
        False,
        1000.0,
        50.5,
        True,
        "CFO",
    )


def test_html_to_text_strips_markup():
    assert html_to_text("<p>Hello&nbsp;<b>world</b></p><script>x()</script><p>two</p>") == "Hello world\ntwo"


def test_fred_finra_finnhub_massive_parse():
    s = Fred().series("DGS10", date(2026, 1, 1))
    assert s.points and 0 < s.points[-1].value < 10
    si = Finra().short_interest("ZZSML")
    assert si and si[-1].days_to_cover and si[0].settlement_date < si[-1].settlement_date
    rec = Finnhub().recommendation_trends("ZZTEC")
    assert rec and rec[-1].buy + rec[-1].hold + rec[-1].sell > 0
    acts = MassiveBenzinga().actions("ZZTEC")
    assert acts and acts[0].analyst_name and acts[0].firm and acts[0].target
    assert {a.action for a in acts} & {
        "upgrade",
        "downgrade",
        "initiate",
        "reiterate",
        "target_raise",
        "target_cut",
    }


def test_fmp_analyst_and_estimates():
    fmp = Fmp()
    acts = fmp.actions("ZZBNK")
    per_analyst = [a for a in acts if a.analyst_name]
    firm_level = [a for a in acts if a.analyst_name is None]
    assert per_analyst and firm_level
    assert all(a.target for a in per_analyst)
    ests = fmp.estimates("ZZTEC")
    assert {e.metric for e in ests} >= {"eps", "revenue"}
    assert fmp.estimates("ZZSML") == []  # no coverage
