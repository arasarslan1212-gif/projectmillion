"""Engine configuration loader. The config hash is stamped on every report and snapshot."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from engine.settings import get_settings

ENGINE_VERSION = "0.9.0"


class Config:
    def __init__(self, data: dict[str, Any], path: Path | None = None) -> None:
        self.data = data
        self.path = path
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        self.hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def __getitem__(self, dotted: str) -> Any:
        v = self.get(dotted, _MISSING)
        if v is _MISSING:
            raise KeyError(dotted)
        return v


_MISSING = object()


@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> Config:
    p = Path(path) if path else get_settings().config_path
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Config(data, p)


def get_config() -> Config:
    return load_config(None)


@lru_cache(maxsize=2)
def load_metric_defs(path: str | None = None) -> dict[str, dict]:
    p = Path(path) if path else get_settings().metrics_path
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
