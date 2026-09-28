"""Every metric the engine emits must have a definition (tooltips, glossary and methodology depend on it)."""

from engine.config import load_metric_defs
from engine.report.builder import build_report


def _metrics(node, out):
    if isinstance(node, dict):
        if {"id", "value", "unit", "def"} <= node.keys():
            out.append(node)
        for v in node.values():
            _metrics(v, out)
    elif isinstance(node, list):
        for v in node:
            _metrics(v, out)
    return out


def test_all_emitted_metrics_are_defined():
    defs = load_metric_defs()
    missing = set()
    for t in ("ZZTEC", "ZZBNK", "ZZREI", "ZZGRO", "ZZUTL", "ZZSML"):
        report = build_report(t)
        for m in _metrics(report["sections"], []):
            if m["def"] not in defs and m["id"] not in defs:
                missing.add(m["def"])
    assert not missing, f"add definitions to config/metrics.yaml for: {sorted(missing)}"


def test_every_definition_has_text():
    for key, d in load_metric_defs().items():
        assert d.get("definition"), key
