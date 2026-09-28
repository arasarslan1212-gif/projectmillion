"""Section registry and orchestration. Each section is computed in isolation: one failing section
never prevents the others from rendering."""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections import OrderedDict
from collections.abc import Callable
from datetime import date

from engine import clock
from engine.config import ENGINE_VERSION, get_config
from engine.report.context import ReportContext, TickerNotFound
from engine.report.metric import section
from engine.settings import get_settings

log = logging.getLogger("engine.report")

SectionFn = Callable[[ReportContext], dict]
_REGISTRY: OrderedDict[str, SectionFn] = OrderedDict()


def register(name: str, fn: SectionFn) -> None:
    _REGISTRY[name] = fn


def section_names() -> list[str]:
    _ensure_registered()
    return list(_REGISTRY)


_registered = False


def _ensure_registered() -> None:
    global _registered
    if _registered:
        return
    from engine.report.sections import catalog

    for name, fn in catalog.SECTIONS:
        register(name, fn)
    _registered = True


class _ContextCache:
    def __init__(self, ttl_s: int = 600, cap: int = 64) -> None:
        self.ttl = ttl_s
        self.cap = cap
        self.d: OrderedDict[tuple, tuple[float, ReportContext]] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, ticker: str, as_of: date | None, pit: bool) -> ReportContext:
        key = (ticker.upper(), as_of, pit, get_settings().data_tier, get_config().hash)
        now = time.time()
        with self.lock:
            hit = self.d.get(key)
            if hit and now - hit[0] < self.ttl:
                self.d.move_to_end(key)
                return hit[1]
            ctx = ReportContext(ticker, as_of=as_of, pit=pit)
            self.d[key] = (now, ctx)
            while len(self.d) > self.cap:
                self.d.popitem(last=False)
            return ctx

    def drop(self, ticker: str) -> None:
        with self.lock:
            for k in [k for k in self.d if k[0] == ticker.upper()]:
                del self.d[k]


contexts = _ContextCache()


def run_section(ctx: ReportContext, name: str) -> dict:
    _ensure_registered()
    fn = _REGISTRY.get(name)
    if fn is None:
        return section(name, status="error", reason=f"unknown section '{name}'")
    t0 = time.perf_counter()
    try:
        out = ctx.section(name, fn)
    except TickerNotFound:
        raise
    except Exception as exc:  # isolate failures per section
        log.error("section %s failed for %s: %s\n%s", name, ctx.ticker, exc, traceback.format_exc())
        out = section(
            name, status="error", reason=f"this section could not be computed ({type(exc).__name__}: {exc})"
        )
        with ctx._lock:
            ctx._sections[name] = out
    out = dict(out)
    out.setdefault("timing_ms", round((time.perf_counter() - t0) * 1000))
    return out


def get_section(ticker: str, name: str, as_of: date | None = None, pit: bool = False) -> dict:
    ctx = contexts.get(ticker, as_of, pit)
    _ = ctx.symbol  # raises TickerNotFound early
    out = run_section(ctx, name)
    out["ticker"] = ctx.ticker
    out["generated_at"] = clock.now().isoformat()
    out["engine_version"] = ENGINE_VERSION
    out["config_hash"] = get_config().hash
    return out


def build_report(
    ticker: str, names: list[str] | None = None, as_of: date | None = None, pit: bool = False
) -> dict:
    names = names or section_names()
    ctx = contexts.get(ticker, as_of, pit)
    _ = ctx.symbol
    sections = {n: run_section(ctx, n) for n in names}
    return {
        "ticker": ctx.ticker,
        "as_of": ctx.as_of.isoformat(),
        "generated_at": clock.now().isoformat(),
        "engine_version": ENGINE_VERSION,
        "config_hash": get_config().hash,
        "data_tier": get_settings().data_tier,
        "synthetic": ctx.synthetic,
        "sections": sections,
    }
