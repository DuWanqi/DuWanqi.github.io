from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .upstream import SourceKey, UpstreamReader


_PROPERTY_KEYS = (
    "生命",
    "物攻",
    "法攻",
    "物防",
    "法防",
    "基础攻速",
    "暴击率",
)
_GROWTH_PATTERNS = {
    "物攻": r"(?:每级|[，,])\s*物攻\+([0-9.]+)",
    "法攻": r"(?:每级[^，。]*?)?法攻\+([0-9.]+)",
    "生命": r"(?:每级[^，。]*?)?生命\+([0-9.]+)",
}


@dataclass(frozen=True)
class DerivedCombatStats:
    hero_id: str
    requested_level: int
    model_level: int
    values: tuple[tuple[str, float], ...]
    status: str
    model_version: str
    source_path: str
    source_sha256: str
    source_layer: str
    assumptions: tuple[str, ...]
    unresolved_items: tuple[str, ...]

    def value(self, name: str) -> float | None:
        return dict(self.values).get(name)


@dataclass(frozen=True)
class HeroGrowthModel:
    hero_id: str
    hero_name: str
    template: str
    base_properties: tuple[tuple[str, float], ...]
    growth_rates: tuple[tuple[str, float], ...]
    snapshots: tuple[tuple[int, tuple[tuple[str, float], ...]], ...]
    model_version: str
    source_path: str
    source_sha256: str
    special_notes: tuple[str, ...]
    status: str

    def derive(self, requested_level: int) -> DerivedCombatStats:
        model_level = max(1, int(requested_level))
        base = dict(self.base_properties)
        rates = dict(self.growth_rates)
        snapshots = {level: dict(values) for level, values in self.snapshots}
        checkpoints = tuple(sorted(level for level in snapshots if level <= model_level))
        checkpoint = checkpoints[-1] if checkpoints else 1
        checkpoint_values = snapshots.get(checkpoint, base)
        values = {}
        contradictory_axes = []
        for name in _PROPERTY_KEYS:
            base_value = float(base.get(name, 0.0))
            rate = float(rates.get(name, 0.0))
            linear = base_value + rate * max(0, model_level - 1)
            checkpoint_linear = base_value + rate * max(0, checkpoint - 1)
            snapshot_value = checkpoint_values.get(name)
            contradicts_declared_growth = (
                checkpoint > 1
                and rate > 0
                and snapshot_value is not None
                and float(snapshot_value) == base_value
            )
            if contradicts_declared_growth:
                contradictory_axes.append(name)
            checkpoint_value = (
                checkpoint_linear
                if contradicts_declared_growth
                else float(snapshot_value if snapshot_value is not None else checkpoint_linear)
            )
            adjustment = checkpoint_value - checkpoint_linear
            values[name] = linear + adjustment
        unresolved = []
        if self.status != "model_ready":
            unresolved.append("growth_template_unresolved")
        if self.special_notes:
            unresolved.append("hero_growth_special_notes_require_review")
        assumptions = (
            "displayed_base_level_is_one",
            "event_levels_are_added_to_the_model_base_level",
            "linear_growth_between_declared_snapshots",
            "latest_crossed_snapshot_supplies_step_adjustments",
        )
        if contradictory_axes:
            assumptions += (
                "declared_growth_overrides_frozen_contradictory_snapshot_axis",
            )
        if requested_level < 1:
            assumptions += ("requested_level_clamped_to_model_base_one",)
        return DerivedCombatStats(
            self.hero_id,
            int(requested_level),
            model_level,
            tuple((name, values[name]) for name in _PROPERTY_KEYS),
            "derived_with_model_warnings" if unresolved else "derived",
            self.model_version,
            self.source_path,
            self.source_sha256,
            "model_derivation",
            assumptions,
            tuple(unresolved),
        )


@dataclass(frozen=True)
class GrowthModelCatalog:
    schema_version: str
    models: tuple[HeroGrowthModel, ...]
    model_version: str
    source_path: str
    source_sha256: str
    source_layer: str = "model_derivation"

    def by_hero_id(self) -> dict[str, HeroGrowthModel]:
        return {item.hero_id: item for item in self.models}


class GrowthModelLoader:
    def load(self, source_root: Path) -> GrowthModelCatalog:
        reader = UpstreamReader(source_root)
        payload = reader.read_json(SourceKey.COMPILED_KB)
        source = reader.source_reads[0]
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        updated_at = str(meta.get("updatedAt", "unversioned"))
        version = f"compiled-kb-growth-v0:{updated_at}:{source.sha256[:12]}"
        models = []
        for entity in payload.get("entities", []):
            if str(entity.get("entityType")) != "英雄":
                continue
            growth = entity.get("growth") if isinstance(entity.get("growth"), dict) else {}
            template = str(growth.get("template", ""))
            base = _numeric_properties(growth.get("baseProperties"))
            snapshots = tuple(
                sorted(
                    (
                        int(level),
                        _numeric_properties(values),
                    )
                    for level, values in (growth.get("levelSnapshots") or {}).items()
                    if str(level).isdigit() and isinstance(values, dict)
                )
            )
            reference = growth.get("templateReference") if isinstance(growth.get("templateReference"), dict) else {}
            growth_text = str(reference.get("growth", ""))
            models.append(HeroGrowthModel(
                hero_id=f"hero:{entity.get('rawId')}",
                hero_name=str(entity.get("name", "")),
                template=template,
                base_properties=base,
                growth_rates=_growth_rates(growth_text),
                snapshots=snapshots,
                model_version=version,
                source_path=source.path,
                source_sha256=source.sha256,
                special_notes=tuple(str(item) for item in growth.get("specialNotes") or ()),
                status=(
                    "model_ready"
                    if template and template != "未判定模板" and base and snapshots
                    else "growth_template_unresolved"
                ),
            ))
        return GrowthModelCatalog(
            "growth-model-catalog-v0",
            tuple(models),
            version,
            source.path,
            source.sha256,
        )


def _numeric_properties(value: object) -> tuple[tuple[str, float], ...]:
    source = value if isinstance(value, dict) else {}
    result = []
    for name in _PROPERTY_KEYS:
        raw = source.get(name)
        if isinstance(raw, (int, float)):
            result.append((name, float(raw)))
    return tuple(result)


def _growth_rates(text: str) -> tuple[tuple[str, float], ...]:
    rates = []
    for name, pattern in _GROWTH_PATTERNS.items():
        match = re.search(pattern, text)
        if match:
            rates.append((name, float(match.group(1))))
    return tuple(rates)


__all__ = [
    "DerivedCombatStats",
    "GrowthModelCatalog",
    "GrowthModelLoader",
    "HeroGrowthModel",
]
