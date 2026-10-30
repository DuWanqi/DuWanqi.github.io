from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..combat_growth import GrowthModelLoader
from ..upstream import SourceKey, UpstreamReader
from .models import (
    AcquisitionRoute,
    EquipmentProfile,
    EvidenceFragment,
    RoleProfile,
    SourceSnapshot,
)
from .parser import classify_passive, parse_static_attributes


REPRESENTATIVE_IDS = (
    42103,  # double sword: spell growth on kill
    643702,  # neighbor count
    643703,  # lethal protection
    643301,  # paper attack speed
    643503,  # magic-defense plus level shield
    643802,  # cast-stacking attack
    643207,  # spell-scaling attack speed
    643501,  # high-health mitigation threshold
    644120,  # controlled-enemy cadence
    7542,  # faction-limited summon
    641016,  # faction-limited revival
    641002,  # flat physical attack plus kill growth
    641023,  # shared equipment count level growth
    643104,  # neighbor stat transfer
)

FIXED_DUMMY_EXTRA_IDS = frozenset((42102, 42103))


ROLE_PROFILES = (
    RoleProfile("physical_sustained_output", "物理持续输出", "model_profile", ("physical_attack_flat", "physical_attack_percent", "attack_speed_percent", "critical_rate_percent"), ("not an official职业标签",)),
    RoleProfile("spell_casting", "法术施法", "model_profile", ("magical_attack_flat", "magical_attack_percent", "initial_energy_flat", "max_energy_flat", "max_energy_percent"), ("not an official职业标签",)),
    RoleProfile("frontline_tanking", "前排承伤", "model_profile", ("max_health_flat", "max_health_percent", "physical_defense_flat", "magical_defense_flat"), ("not an official职业标签",)),
    RoleProfile("attack_speed_output", "攻速输出", "model_profile", ("attack_speed_percent",), ("not an official职业标签",)),
    RoleProfile("mana_cycle", "法力循环", "model_profile", ("initial_energy_flat", "max_energy_flat", "max_energy_percent"), ("not an official职业标签",)),
    RoleProfile("summon_or_growth", "召唤或成长", "model_profile", (), ("requires explicit trigger and receiver",)),
    RoleProfile("mixed", "混合", "model_profile", (), ("does not merge axes into one value",)),
)


class EquipmentValueCatalog:
    """Read-only bridge to a live official snapshot; it never persists upstream data."""

    def __init__(self, upstream_root: Path) -> None:
        self.upstream_root = upstream_root
        self.reader = UpstreamReader(upstream_root)

    def load_profiles(self, representative_only: bool = True) -> tuple[EquipmentProfile, ...]:
        payload = self.reader.read_json(SourceKey.RAW_EQUIPMENT)
        items = payload["equipCards"]
        selected = set(REPRESENTATIVE_IDS) if representative_only else None
        return tuple(
            self._profile(item)
            for item in items
            if selected is None or int(item.get("id", -1)) in selected
        )

    def normal_second_tier_profiles(self) -> tuple[EquipmentProfile, ...]:
        """Current common equipment with a directly listed basic-equipment source."""
        payload = self.reader.read_json(SourceKey.RAW_EQUIPMENT)
        return tuple(
            self._profile(item)
            for item in payload["equipCards"]
            if self._is_normal_second_tier(item)
        )

    def fixed_dummy_profiles(self) -> tuple[EquipmentProfile, ...]:
        """Common equipment plus hero-granted equipment supported by the lab."""
        payload = self.reader.read_json(SourceKey.RAW_EQUIPMENT)
        profiles = {
            int(item["id"]): self._profile(item)
            for item in payload["equipCards"]
            if self._is_normal_second_tier(item) or int(item.get("id", -1)) in FIXED_DUMMY_EXTRA_IDS
        }
        # Granted equipment may only be published inside a hero's previewCards.
        # Preserve that source instead of fabricating a top-level equipment row.
        heroes = self.reader.read_json(SourceKey.RAW_HEROES)
        source = next(item for item in self.reader.source_reads if item.source_key == "raw_heroes")
        snapshot = SourceSnapshot(source.path, "official_raw", source.sha256, "official-raw:hero-preview-equipment", "equipment text from official hero previewCards")
        for hero in heroes["heroCards"]:
            for item in hero.get("previewCards") or ():
                item_id = int(item.get("id", -1))
                if item_id in FIXED_DUMMY_EXTRA_IDS and item_id not in profiles and item.get("equipCard") and item.get("desc"):
                    profiles[item_id] = self._profile(item, snapshot)
        return tuple(profiles.values())

    def inventory(self) -> dict[str, object]:
        payload = self.reader.read_json(SourceKey.RAW_EQUIPMENT)
        records = payload["equipCards"]
        snapshot = self._raw_snapshot()
        parsed_count = 0
        classifications: dict[str, int] = {}
        by_subtype: dict[str, int] = {}
        missing: dict[str, int] = {"description": 0, "type": 0, "source_cards": 0}
        for item in records:
            profile = self._profile(item)
            if profile.static_attributes:
                parsed_count += 1
            classifications[profile.passive.classification] = classifications.get(profile.passive.classification, 0) + 1
            subtype = str((item.get("equipCard") or {}).get("atlasSubTypeName") or "missing")
            by_subtype[subtype] = by_subtype.get(subtype, 0) + 1
            if not item.get("desc"):
                missing["description"] += 1
            if not item.get("equipCard"):
                missing["type"] += 1
            if not item.get("sourceCards"):
                missing["source_cards"] += 1
        return {
            "snapshot": snapshot,
            "total": len(records),
            "subtypes": by_subtype,
            "static_parseable": parsed_count,
            "passive_classifications": classifications,
            "missing": missing,
        }

    def growth_models(self):
        return GrowthModelLoader().load(self.upstream_root)

    def _profile(self, item: dict[str, Any], snapshot: SourceSnapshot | None = None) -> EquipmentProfile:
        raw = snapshot or self._raw_snapshot()
        equipment_id = f"equipment:{item['id']}"
        evidence = EvidenceFragment(
            f"official-raw:{equipment_id}:desc", str(item.get("desc", "")), raw, "raw_text",
        )
        deep_dive = self._formal_analysis_snapshot(int(item["id"]))
        return EquipmentProfile(
            equipment_id, str(item.get("name", "")), evidence,
            parse_static_attributes(evidence), classify_passive(evidence),
            self._acquisition_routes(item, evidence.evidence_id), deep_dive,
            ROLE_PROFILES, self._profile_unknowns(item, deep_dive),
        )

    def _raw_snapshot(self) -> SourceSnapshot:
        self.reader.read_json(SourceKey.RAW_EQUIPMENT)
        source = next(item for item in self.reader.source_reads if item.source_key == "raw_equipment")
        return SourceSnapshot(source.path, "official_raw", source.sha256, "official-raw:equipment-snapshot", "current official raw card snapshot; no battle-event semantics inferred")

    def _formal_analysis_snapshot(self, item_id: int) -> SourceSnapshot | None:
        directory = self.upstream_root / "知识库" / "卡牌深拆" / "装备牌"
        candidates = tuple(directory.glob(f"{item_id}_*.md"))
        if not candidates:
            return None
        path = candidates[0]
        return SourceSnapshot(str(path), "formal_analysis", hashlib.sha256(path.read_bytes()).hexdigest(), f"formal-analysis:equipment:{item_id}", "secondary formal analysis; freshness/conflicts must be checked against current official raw text")

    def _acquisition_routes(self, item: dict[str, Any], evidence_id: str) -> tuple[AcquisitionRoute, ...]:
        routes: list[AcquisitionRoute] = []
        for source in item.get("sourceCards") or ():
            routes.append(AcquisitionRoute("named_source_card", "official_raw_reference", f"source card {source.get('id')}:{source.get('name')}", "source reference does not prove a complete acquisition sequence", evidence_id))
        routes.extend((
            AcquisitionRoute("effect_card", "unresolved", "generic raw source text names effect-card route", "identity and trigger conditions unresolved", evidence_id),
            AcquisitionRoute("auction", "unresolved", "generic raw source text names auction route", "availability and selection conditions unresolved", evidence_id),
        ))
        return tuple(routes)

    @staticmethod
    def _profile_unknowns(item: dict[str, Any], deep_dive: SourceSnapshot | None) -> tuple[str, ...]:
        unknowns = ["no_global_score_or_recommendation", "no_acquisition_value_comparison"]
        if not item.get("sourceCards"):
            unknowns.append("named_source_card_absent_in_current_raw_record")
        if deep_dive is None:
            unknowns.append("no_matching_formal_analysis_file")
        return tuple(unknowns)

    @staticmethod
    def _is_normal_second_tier(item: dict[str, Any]) -> bool:
        equipment = item.get("equipCard") or {}
        if equipment.get("atlasSubTypeName") != "普通装备":
            return False
        return any(
            (source.get("equipCard") or {}).get("atlasSubTypeName") == "基础装备"
            for source in item.get("sourceCards") or ()
        )
