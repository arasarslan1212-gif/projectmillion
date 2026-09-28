"""FastAPI application: the only interface between the web app and the engine."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

from engine import clock
from engine.config import ENGINE_VERSION, get_config, load_metric_defs
from engine.data.service import get_data
from engine.db.session import init_db
from engine.providers.registry import get_providers
from engine.report import builder
from engine.report.context import TickerNotFound
from engine.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    if get_settings().enable_scheduler:
        from engine.jobs.scheduler import start_scheduler

        start_scheduler()
    yield


app = FastAPI(title="Stock Analysis Engine", version=ENGINE_VERSION, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _not_found(ticker: str) -> HTTPException:
    return HTTPException(404, detail=f"'{ticker.upper()}' is not a US-listed ticker in the SEC ticker list.")


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "engine_version": ENGINE_VERSION,
        "config_hash": get_config().hash,
        "data_mode": s.data_mode,
        "fixture_set": s.active_fixture_set if s.data_mode == "mock" else None,
        "synthetic": clock.is_synthetic(),
        "data_tier": s.data_tier,
        "llm_enabled": s.llm_enabled,
        "today": clock.today().isoformat(),
        "providers": get_providers(s.data_tier).describe(),
    }


@app.get("/api/search")
def search(q: str = Query(..., min_length=1, max_length=60), limit: int = 10) -> dict:
    res = get_data().search(q, limit=min(limit, 25))
    return {"results": [{"ticker": r.ticker, "name": r.name, "exchange": r.exchange} for r in res]}


@app.get("/api/report/{ticker}/sections")
def sections(ticker: str) -> dict:
    return {"sections": builder.section_names()}


@app.get("/api/report/{ticker}/section/{name}")
def report_section(ticker: str, name: str, as_of: date | None = None, peers: str | None = None) -> dict:
    if name not in builder.section_names():
        raise HTTPException(404, detail=f"unknown section '{name}'")
    peer_list = (
        tuple(sorted({p.strip().upper() for p in peers.split(",") if p.strip()}))[:15] if peers else None
    )
    try:
        return builder.get_section(ticker, name, as_of=as_of, pit=as_of is not None, peers=peer_list)
    except TickerNotFound:
        raise _not_found(ticker) from None


@app.get("/api/report/{ticker}")
def report(ticker: str, sections: str | None = None) -> dict:
    names = [s for s in (sections or "").split(",") if s] or None
    try:
        return builder.build_report(ticker, names)
    except TickerNotFound:
        raise _not_found(ticker) from None


@app.post("/api/report/{ticker}/refresh")
def refresh(ticker: str) -> dict:
    t = ticker.upper()
    data = get_data()
    for prefix in (
        f"quote:{t}",
        f"prices:{t}",
        "news:",
        "analysts:",
        f"profile:{t}",
        f"estimates:{t}",
        "earnings:",
    ):
        data.invalidate(prefix)
    builder.contexts.drop(t)
    return {"status": "refreshed", "ticker": t}


class DcfOverrides(BaseModel):
    growth1: float | None = Field(None, ge=-0.5, le=1.5)
    margin_target: float | None = Field(None, ge=-1.0, le=0.9)
    wacc: float | None = Field(None, ge=0.02, le=0.3)
    terminal_growth: float | None = Field(None, ge=-0.02, le=0.05)
    capex_pct: float | None = Field(None, ge=0.0, le=1.0)


@app.post("/api/valuation/{ticker}/dcf")
def dcf_what_if(ticker: str, body: DcfOverrides) -> dict:
    """Recompute the DCF with user-chosen assumptions (the interactive sliders). Deterministic and fast."""
    from dataclasses import replace

    from engine.report.sections.valuation import compute
    from engine.valuation.dcf import DcfInputs, run_dcf

    try:
        ctx = builder.contexts.get(ticker, None, False)
        v = compute(ctx)
    except TickerNotFound:
        raise _not_found(ticker) from None
    dcf = (v or {}).get("dcf")
    if not dcf:
        raise HTTPException(422, detail="No DCF is available for this company (profile or data).")
    base = DcfInputs(**dcf["inputs"])
    changes = {k: val for k, val in body.model_dump().items() if val is not None}
    inp = replace(base, **changes)
    if inp.wacc - inp.terminal_growth < 0.005:
        raise HTTPException(422, detail="WACC must exceed terminal growth by at least 0.5 percentage points.")
    r = run_dcf(inp)
    price = v["price"]
    return {
        "per_share": r.per_share,
        "upside": (r.per_share / price - 1) if r.per_share is not None else None,
        "terminal_share": r.terminal_share,
        "enterprise_value": r.enterprise_value,
        "table": r.table,
        "inputs": inp.to_dict(),
        "base_per_share": dcf["per_share"],
        "price": price,
        "notes": r.notes,
        "disclaimer": "What-if calculation with your assumptions; not the app's estimate and not investment advice.",
    }


@app.get("/api/meta/definitions")
def definitions() -> dict:
    return {"definitions": load_metric_defs()}
