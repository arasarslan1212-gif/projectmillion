"""The engine's notion of "today".

Live mode uses the wall clock. Mock mode pins "today" to the fixture set's capture date, so replayed
requests (whose date ranges depend on today) always match what was recorded.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from engine.settings import get_settings


def today() -> date:
    s = get_settings()
    if s.as_of_override:
        return date.fromisoformat(s.as_of_override)
    if s.data_mode == "mock":
        if s.active_fixture_set == "synthetic":
            from engine.synthetic.world import AS_OF

            return AS_OF
        meta = s.fixtures_dir / s.active_fixture_set / "meta.json"
        if meta.exists():
            return date.fromisoformat(json.loads(meta.read_text())["as_of"])
    return datetime.now(UTC).date()


def now() -> datetime:
    t = today()
    real = datetime.now(UTC)
    if t == real.date():
        return real
    return datetime(t.year, t.month, t.day, 21, 0, tzinfo=UTC)


def is_synthetic() -> bool:
    s = get_settings()
    return s.data_mode == "mock" and s.active_fixture_set == "synthetic"
