from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from ..upstream import SourceKey, UpstreamReader
from .models import SourceSnapshot


_AXIS_PATTERNS = {
    "physical_attack_per_level": r"(?:每级|[，,])\s*物攻\+([0-9.]+)",
    "magical_attack_per_level": r"(?:每级|[，,])\s*法攻\+([0-9.]+)",
    "health_per_level": r"(?:每级|[，,])\s*生命\+([0-9.]+)",
}


@dataclass(frozen=True)
class GrowthTemplateBaseline:
    template_id: str
    hero_count: int
    base_physical_attack: float | None
    base_magical_attack: float | None
    base_health: float | None
    base_physical_defense: float | None
    base_magical_defense: float | None
    base_attack_speed: float | None
    physical_attack_per_level: float | None
    magical_attack_per_level: float | None
    health_per_level: float | None
    status: str
    raw_growth_text: str
    snapshot: SourceSnapshot
    unresolved_items: tuple[str, ...]


@dataclass(frozen=True)
class GrowthTemplateCatalog:
    schema_version: str
    templates: tuple[GrowthTemplateBaseline, ...]
    compiled_hero_count: int
    unclassified_hero_count: int
    official_raw_hero_count: int
    snapshot: SourceSnapshot
    raw_hero_snapshot: SourceSnapshot


class GrowthTemplateLoader:
    """Extract normal growth baselines without changing the shared combat model."""

    def load(self, upstream_root: Path) -> GrowthTemplateCatalog:
        reader = UpstreamReader(upstream_root)
        compiled = reader.read_json(SourceKey.COMPILED_KB)
        raw_heroes = reader.read_json(SourceKey.RAW_HEROES)
        compiled_snapshot = _snapshot(reader, "compiled_kb", "model_derivation", "compiled growth template source; special nodes excluded from normal per-level baseline")
        raw_snapshot = _snapshot(reader, "raw_heroes", "official_raw", "current raw hero count used only for coverage gap")
        entities = tuple(item for item in compiled.get("entities", ()) if item.get("entityType") == "英雄")
        template_counts: dict[str, int] = {}
        unclassified = 0
        for entity in entities:
            growth = entity.get("growth") if isinstance(entity.get("growth"), dict) else {}
            template = str(growth.get("template") or "未判定模板")
            if template == "未判定模板":
                unclassified += 1
            else:
                template_counts[template] = template_counts.get(template, 0) + 1
        templates = tuple(
            _baseline(name, value if isinstance(value, dict) else {}, template_counts.get(name, 0), compiled_snapshot)
            for name, value in sorted((compiled.get("growthModels") or {}).items())
        )
        return GrowthTemplateCatalog(
            "equipment-growth-template-baseline-v0", templates, len(entities), unclassified,
            len(raw_heroes.get("heroCards") or ()), compiled_snapshot, raw_snapshot,
        )


def _baseline(name: str, source: dict[str, object], hero_count: int, snapshot: SourceSnapshot) -> GrowthTemplateBaseline:
    text = str(source.get("growth") or "")
    base_text = str(source.get("base") or "")
    values = {
        axis: float(match.group(1)) if (match := re.search(pattern, text)) else None
        for axis, pattern in _AXIS_PATTERNS.items()
    }
    legacy_conflict = "旧图口径" in text or "用户修正" in text
    unresolved = []
    if legacy_conflict:
        unresolved.append("legacy_growth_text_requires_current_rule_confirmation")
    if any(value is None for value in values.values()):
        unresolved.append("axis_absent_from_normal_growth_text")
    return GrowthTemplateBaseline(
        str(name), hero_count,
        _base_value(base_text, "物攻"), _base_value(base_text, "法攻"), _base_value(base_text, "生命"),
        _base_value(base_text, "双抗"), _base_value(base_text, "双抗"),
        _base_value(base_text, "基础攻速"),
        values["physical_attack_per_level"], values["magical_attack_per_level"],
        values["health_per_level"], "legacy_conflict" if legacy_conflict else "ready", text,
        snapshot, tuple(unresolved),
    )


def _snapshot(reader: UpstreamReader, source_key: str, layer: str, boundary: str) -> SourceSnapshot:
    read = next(item for item in reader.source_reads if item.source_key == source_key)
    return SourceSnapshot(read.path, layer, read.sha256, f"growth-template:{source_key}", boundary)


def _base_value(text: str, label: str) -> float | None:
    match = re.search(rf"{re.escape(label)}\s*(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None
