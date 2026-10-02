"""SEC EDGAR adapter (free, official).

Endpoints (https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data):
- https://www.sec.gov/files/company_tickers_exchange.json   ticker → CIK map
- https://data.sec.gov/submissions/CIK##########.json        company meta + recent filings
- https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json  all XBRL facts, each with `filed`
- https://data.sec.gov/api/xbrl/frames/{tax}/{tag}/{unit}/{period}.json  one fact across companies
- https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC=####   companies by SIC (HTML)
- https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{doc}  filing documents (Form 4 XML, 10-K)

Fair access: ≤10 requests/second and a descriptive User-Agent with a contact email.
"""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

from engine.fundamentals.concepts import LINE_ITEMS
from engine.http.client import HttpClient, ProviderError, get_http
from engine.providers.models import (
    CompanyMeta,
    Fact,
    Filing,
    FramePoint,
    InsiderTransaction,
    InstitutionalHolding,
    SymbolInfo,
)
from engine.settings import get_settings

DATA = "https://data.sec.gov"
WWW = "https://www.sec.gov"

log = logging.getLogger("engine.sec")


def _d(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def cik10(cik: int) -> str:
    return f"{int(cik):010d}"


class SecEdgar:
    name = "SEC EDGAR"
    provider_key = "sec"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or get_http()

    @property
    def _headers(self) -> dict[str, str]:
        return {"User-Agent": get_settings().sec_user_agent, "Accept-Encoding": "gzip, deflate"}

    def _get(self, url: str, params: dict | None = None, expect: str = "json"):
        return self.http.get(self.provider_key, url, params=params, headers=self._headers, expect=expect).body

    # -- symbols ---------------------------------------------------------------------
    def all_symbols(self) -> list[SymbolInfo]:
        body = self._get(f"{WWW}/files/company_tickers_exchange.json")
        try:
            fields = body["fields"]
            idx = {f: i for i, f in enumerate(fields)}
            out = []
            for row in body["data"]:
                ticker = row[idx["ticker"]]
                if not ticker:
                    continue
                out.append(
                    SymbolInfo(
                        ticker=str(ticker).upper(),
                        cik=int(row[idx["cik"]]),
                        name=str(row[idx["name"]]),
                        exchange=row[idx["exchange"]] if "exchange" in idx else None,
                    )
                )
            return out
        except (KeyError, TypeError) as exc:
            raise ProviderError("sec", "bad_response", f"ticker file: {exc}") from exc

    # -- submissions -----------------------------------------------------------------
    def _submissions(self, cik: int) -> dict:
        return self._get(f"{DATA}/submissions/CIK{cik10(cik)}.json")

    def company_meta(self, cik: int) -> CompanyMeta:
        s = self._submissions(cik)
        addr = (s.get("addresses") or {}).get("business") or {}
        sic = s.get("sic")
        return CompanyMeta(
            cik=int(s.get("cik", cik)),
            name=s.get("name") or "",
            tickers=[t.upper() for t in s.get("tickers") or []],
            exchanges=list(s.get("exchanges") or []),
            sic=int(sic) if sic not in (None, "") else None,
            sic_description=s.get("sicDescription"),
            fiscal_year_end=s.get("fiscalYearEnd"),
            state_of_incorporation=s.get("stateOfIncorporation"),
            hq_city=addr.get("city"),
            hq_state=addr.get("stateOrCountry"),
            entity_type=s.get("entityType"),
            is_synthetic=bool(s.get("_synthetic", False)),
        )

    def filings(self, cik: int) -> list[Filing]:
        s = self._submissions(cik)
        recent = (s.get("filings") or {}).get("recent") or {}
        n = len(recent.get("accessionNumber", []))
        out: list[Filing] = []
        for i in range(n):

            def col(name: str, i: int = i):
                arr = recent.get(name)
                return arr[i] if arr and i < len(arr) else None

            accn = col("accessionNumber")
            filed = _d(col("filingDate"))
            if not accn or not filed:
                continue
            items_raw = col("items") or ""
            items = [x.strip() for x in str(items_raw).split(",") if x.strip()]
            accepted = col("acceptanceDateTime")
            try:
                accepted_dt = datetime.fromisoformat(accepted.replace("Z", "+00:00")) if accepted else None
            except ValueError:
                accepted_dt = None
            primary = col("primaryDocument")
            out.append(
                Filing(
                    accession=accn,
                    cik=int(cik),
                    form=str(col("form") or ""),
                    filed_at=filed,
                    report_date=_d(col("reportDate")),
                    accepted_at=accepted_dt,
                    items=items,
                    primary_doc=primary,
                    description=col("primaryDocDescription"),
                    url=self.document_url(cik, accn, primary) if primary else None,
                )
            )
        return out

    @staticmethod
    def document_url(cik: int, accession: str, doc: str | None) -> str:
        base = f"{WWW}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
        return f"{base}/{doc}" if doc else f"{base}/"

    def document_text(self, filing: Filing) -> str:
        if not filing.primary_doc:
            raise ProviderError("sec", "not_found", "filing has no primary document")
        raw = self._get(self.document_url(filing.cik, filing.accession, filing.primary_doc), expect="text")
        return html_to_text(str(raw))

    # -- XBRL ------------------------------------------------------------------------
    def company_facts(self, cik: int) -> list[Fact]:
        """The facts behind the standard line items (fundamentals/concepts.py). A large filer reports thousands of
        other concepts that nothing reads; keeping them would multiply the memory each company takes."""
        body = self._get(f"{DATA}/api/xbrl/companyfacts/CIK{cik10(cik)}.json")
        wanted = {(li.taxonomy, c) for li in LINE_ITEMS.values() for c in li.concepts}
        facts: list[Fact] = []
        for taxonomy, concepts in (body.get("facts") or {}).items():
            for concept, spec in concepts.items():
                if (taxonomy, concept) not in wanted:
                    continue
                for unit, rows in (spec.get("units") or {}).items():
                    for r in rows:
                        end = _d(r.get("end"))
                        filed = _d(r.get("filed"))
                        val = r.get("val")
                        if end is None or filed is None or val is None:
                            continue
                        try:
                            v = float(val)
                        except (TypeError, ValueError):
                            continue
                        facts.append(
                            Fact(
                                taxonomy=taxonomy,
                                concept=concept,
                                unit=unit,
                                start=_d(r.get("start")),
                                end=end,
                                value=v,
                                fy=r.get("fy"),
                                fp=r.get("fp"),
                                form=r.get("form"),
                                accn=r.get("accn"),
                                filed=filed,
                                frame=r.get("frame"),
                            )
                        )
        return facts

    def frame(self, concept: str, unit: str, period: str, taxonomy: str = "us-gaap") -> list[FramePoint]:
        body = self._get(f"{DATA}/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{period}.json")
        out = []
        for r in body.get("data") or []:
            end = _d(r.get("end"))
            if end is None or r.get("val") is None:
                continue
            out.append(
                FramePoint(
                    cik=int(r["cik"]),
                    entity_name=r.get("entityName") or "",
                    value=float(r["val"]),
                    start=_d(r.get("start")),
                    end=end,
                    accn=r.get("accn"),
                )
            )
        return out

    def ciks_for_sic(self, sic: int, max_pages: int = 10) -> list[int]:
        """Companies registered under a SIC code, from EDGAR's company browse (HTML).

        Includes inactive registrants; callers intersect with the current ticker list.
        """
        found: list[int] = []
        seen: set[int] = set()
        for page in range(max_pages):
            raw = self._get(
                f"{WWW}/cgi-bin/browse-edgar",
                params={
                    "action": "getcompany",
                    "SIC": f"{int(sic):04d}",
                    "owner": "include",
                    "count": "100",
                    "start": str(page * 100),
                },
                expect="text",
            )
            ciks = [int(m) for m in re.findall(r"CIK=(\d{10})", str(raw))]
            new = [c for c in ciks if c not in seen]
            for c in new:
                seen.add(c)
                found.append(c)
            if len(set(ciks)) < 100:
                break
        return found

    # -- ownership -------------------------------------------------------------------
    def insider_transactions(self, ticker: str, cik: int, since: date, max_filings: int = 150):
        forms = [f for f in self.filings(cik) if f.form in ("4", "4/A") and f.filed_at >= since]
        out: list[InsiderTransaction] = []
        for f in forms[:max_filings]:
            if not f.primary_doc:
                continue
            doc = re.sub(r"^xslF345X\d+/", "", f.primary_doc)
            url = self.document_url(cik, f.accession, doc)
            try:
                xml_text = self._get(url, expect="text")
            except ProviderError:
                continue
            out.extend(
                parse_form4(str(xml_text), ticker, f, self.document_url(cik, f.accession, f.primary_doc))
            )
        return out

    def institutional_holders(self, ticker: str) -> list[InstitutionalHolding]:
        # 13F is filed by managers, not issuers; there is no issuer-centric free SEC endpoint.
        raise ProviderError("sec", "not_configured", "issuer-level 13F holdings need a commercial provider")


# -- parsing helpers -----------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v\xa0\u2009\u202f]+")


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|ix:header)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>|</li>", "\n", raw)
    text = html.unescape(_TAG_RE.sub(" ", raw))
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _txt(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    node = el.find(path)
    if node is None:
        return None
    v = node.find("value")
    s = (v.text if v is not None else node.text) or ""
    s = s.strip()
    return s or None


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def parse_form4(xml_text: str, ticker: str, filing: Filing, url: str | None) -> list[InsiderTransaction]:
    """Parse an SEC ownership document (Form 4). Returns one record per transaction row."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as e:
        log.warning("unparseable Form 4 %s for %s: %s", filing.accession, ticker, e)
        return []
    owner = root.find("reportingOwner")
    name = _txt(owner, "reportingOwnerId/rptOwnerName") or "Unknown filer"
    owner_cik = _txt(owner, "reportingOwnerId/rptOwnerCik")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None

    def flag(tag: str) -> bool:
        v = _txt(rel, tag)
        return (v or "").lower() in ("1", "true")

    title = _txt(rel, "officerTitle")
    is_dir, is_off, is_ten = flag("isDirector"), flag("isOfficer"), flag("isTenPercentOwner")
    role = title or ("Director" if is_dir else "10% owner" if is_ten else "Officer" if is_off else None)
    aff = (root.findtext("aff10b5One") or "").strip().lower()
    plan: bool | None = True if aff in ("1", "true") else False if aff in ("0", "false") else None
    if plan is None:
        # Before the April 2023 checkbox, plan trades were only mentioned in footnotes.
        foot = " ".join((f.text or "") for f in root.iter("footnote"))
        if re.search(r"10b5-1", foot, re.I):
            plan = True

    out: list[InsiderTransaction] = []
    for table, derivative in (
        ("nonDerivativeTable/nonDerivativeTransaction", False),
        ("derivativeTable/derivativeTransaction", True),
    ):
        for tx in root.findall(table):
            d = _d(_txt(tx, "transactionDate"))
            code = (tx.findtext("transactionCoding/transactionCode") or "").strip()
            shares = _num(_txt(tx, "transactionAmounts/transactionShares"))
            if d is None or not code or shares is None:
                continue
            ad = _txt(tx, "transactionAmounts/transactionAcquiredDisposedCode") or ""
            out.append(
                InsiderTransaction(
                    ticker=ticker,
                    filer_name=name,
                    filer_cik=owner_cik,
                    role=role,
                    is_director=is_dir,
                    is_officer=is_off,
                    is_ten_pct_owner=is_ten,
                    tx_date=d,
                    filed_at=filing.filed_at,
                    code=code,
                    acquired=ad.upper() == "A",
                    shares=shares,
                    price=_num(_txt(tx, "transactionAmounts/transactionPricePerShare")),
                    owned_after=_num(_txt(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction")),
                    plan_10b5_1=plan,
                    accession=filing.accession,
                    url=url,
                    derivative=derivative,
                )
            )
    return out
