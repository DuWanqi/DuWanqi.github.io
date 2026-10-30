from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from pathlib import Path
import re
from threading import RLock
from typing import Any

from .combat_growth import GrowthModelLoader
from .combat_math.damage import resistance_multiplier
from .equipment_value.catalog import EquipmentValueCatalog
from .equipment_value.hero_attack_style import resolve_hero_attack_style
from .fixed_dummy_rule_pack import FixedDummyRulePackV1, build_fixed_dummy_rule_pack
from .skill_formula import SkillDamageComponent, SkillFormulaResult, parse_active_skill_damage
from .upstream import SourceKey, UpstreamReader
from .user_confirmed_rules import ATTACK_SPEED_CAP_RULE, SIKONGZHEN_LIGHTNING_CHAIN_RULE


_FORBIDDEN_INPUT_KEYS = {
    "board", "lineup", "chessplayer", "shop", "replay", "rng", "random",
    "effect_cards", "stage", "recommendation", "candidate", "formation",
}
_SUPPORTED_EQUIPMENT_AXES = {
    "physical_attack_flat",
    "physical_attack_percent",
    "magical_attack_flat",
    "attack_speed_percent",
    "physical_defense_flat",
    "magical_defense_flat",
    "max_health_percent",
    "max_energy_flat",
    "magical_attack_percent",
    "critical_rate_percent",
    "critical_effect_percent",
}
_FIXTURE_LEVEL_PRESETS = (1, 10, 40, 100, 150, 200, 300, 400, 500, 999)
_MAX_FIXTURE_LEVEL = 999
_MAX_FIXTURE_HORIZON_SECONDS = 120.0
_MAX_DUMMY_HP = 1_000_000_000.0
_MAX_DUMMY_DEFENSE = 10_000.0
_STANDARD_ATTACK_SPEED_CAP = 4.0
_GOLDEN_STAFF_ID = "equipment:643207"
_TARGET_DUMMY_EQUIPMENT_SUPPORT = {
    "equipment:643501": (
        "supported_deterministic_effect",
        "生命高于70%时，全部伤害减免40%",
    ),
    "equipment:643601": (
        "supported_deterministic_effect",
        "战斗前15秒，普通攻击伤害格挡50%；攻击者攻速高于1.5时格挡70%",
    ),
    "equipment:643602": (
        "supported_partial_effect",
        "每次受到普攻后使攻击者攻速降低20%，持续2秒；五次普攻后的冻结不计入",
    ),
}
_RUNTIME_SOURCE_KEYS = (
    SourceKey.RAW_HEROES,
    SourceKey.RAW_EQUIPMENT,
    SourceKey.COMPILED_KB,
)

# This is a player-facing support contract, not a second equipment database.
# Names and formulas still come from the read-only formal equipment snapshot.
_FIXED_DUMMY_EQUIPMENT_SUPPORT = {
    "equipment:42102": ("supported_deterministic_effect", "攻速+30%；干将莫邪穿戴时法力上限降至10"),
    "equipment:42103": ("supported_partial_effect", "法强+15%；击败后的永久等级成长不计入固定木桩"),
    "equipment:643301": ("supported_static_only", "计入明确静态属性"),
    "equipment:643503": ("supported_static_only", "计入明确静态属性"),
    "equipment:643502": ("supported_static_only", "计入明确静态属性"),
    "equipment:643208": ("supported_static_only", "计入明确静态属性"),
    "equipment:643207": ("supported_deterministic_effect", "计入法强联动攻速与普攻附加法术伤害"),
    "equipment:643402": ("supported_deterministic_effect", "每秒回蓝，影响施法时点"),
    "equipment:643802": ("supported_deterministic_effect", "施法后叠加法强，最多6层"),
    "equipment:643302": ("supported_deterministic_effect", "普攻减物防并记录首次归零伤害"),
    "equipment:643205": ("supported_deterministic_effect", "第5次普攻后开启5秒增伤窗口"),
    "equipment:643504": ("supported_deterministic_effect", "每2秒对固定目标造成法术伤害"),
    "equipment:643704": ("supported_deterministic_effect", "单英雄固定条件下增伤25%"),
    "equipment:643401": ("supported_deterministic_effect", "合格法术命中后记录3段真实灼烧"),
    "equipment:641015": ("supported_deterministic_effect", "固定单目标下每次远程普攻追加箭矢"),
    "equipment:643304": ("supported_deterministic_effect", "战斗开始及每8秒追加4次普攻"),
    "equipment:643105": ("supported_deterministic_effect", "每2秒增加10点法强"),
    "equipment:643202": ("supported_deterministic_effect", "提供15点法术穿透"),
    "equipment:643403": ("supported_deterministic_effect", "初始法力增加15，随机眩晕排除"),
    "equipment:643603": ("supported_deterministic_effect", "固定单英雄条件下自身双防各增加20"),
    "equipment:641010": ("supported_deterministic_effect", "20%固定暴击率与约20%受击叠层计入普攻期望增量"),
    "equipment:643103": ("supported_deterministic_effect", "30%暴击率与60%暴击效果计入普攻期望增量"),
    "equipment:643702": ("supported_deterministic_effect", "默认身边1名敌人，计入15%基础物攻与10点物防"),
    "equipment:643705": ("supported_deterministic_effect", "按等级重复施法概率计入技能期望增量"),
    "equipment:643803": ("supported_partial_effect", "控制试验计入首次受控后15秒免控；300点护盾暂不计入"),
}


def fixed_dummy_equipment_support(equipment_id: str) -> tuple[str, str] | None:
    """Return the analyzer-local support status for a known equipment effect."""
    return _FIXED_DUMMY_EQUIPMENT_SUPPORT.get(equipment_id)


def fixed_dummy_target_equipment_support(equipment_id: str) -> tuple[str, str] | None:
    """Return the explicitly modeled support status for target-dummy equipment."""
    return _TARGET_DUMMY_EQUIPMENT_SUPPORT.get(equipment_id)


def _target_dummy_equipment_effects(
    fixture: "DpsFixtureInputV0",
) -> tuple["FixedDummyTargetEquipmentEffect", ...]:
    effects: list[FixedDummyTargetEquipmentEffect] = []
    for equipment_id in fixture.dummy_equipment_instance_ids:
        support = fixed_dummy_target_equipment_support(equipment_id)
        if support is None:
            raise ValueError(f"unsupported target dummy equipment: {equipment_id}")
        status, summary = support
        exclusions = (
            ("target_equipment:643602:five_hit_freeze_branch_excluded",)
            if equipment_id == "equipment:643602"
            else ()
        )
        assumptions = (
            "target_dummy_equipment_effect_uses_formal_card_description",
            "target_effect_applies_before_dummy_resistance",
        ) + (
            ("target_equipment:643602:only_attack_speed_slow_is_scheduled",)
            if equipment_id == "equipment:643602"
            else ()
        )
        effects.append(FixedDummyTargetEquipmentEffect(
            equipment_id=equipment_id,
            effect_id=f"target-dummy:{equipment_id}:v1",
            status=status,
            summary=summary,
            evidence_ids=(f"official-raw:{equipment_id}:desc",),
            assumptions=assumptions,
            excluded_components=exclusions,
        ))
    return tuple(effects)


def _runtime_source_revision(source_root: Path) -> tuple[tuple[str, int, int], ...]:
    """Use source metadata solely to invalidate the in-memory read-only snapshot."""
    root = Path(source_root)
    snapshots = []
    for source_key in _RUNTIME_SOURCE_KEYS:
        stat = (root / source_key.value).stat()
        snapshots.append((source_key.value, stat.st_mtime_ns, stat.st_size))
    return tuple(snapshots)


_FIXED_ASSUMPTIONS = (
    "single_fixed_target",
    "no_counterattack",
    "no_movement",
    "continuous_contact",
    "no_retargeting",
)
_EXCLUDED_COMPONENTS = (
    "equipment_passives_not_explicitly_modeled",
    "unmodeled_periodic_damage_except_explicit_skill_and_equipment_events", "summon_damage", "split_or_multi_target_damage",
    "control", "movement", "death_effects", "retargeting", "shield", "healing",
    "random_targeting", "active_skill_critical_rules_without_explicit_evidence",
)


@dataclass(frozen=True)
class FixtureLevel:
    value: int
    kind: str


@dataclass(frozen=True)
class DpsFixtureInputV0:
    hero_id: str
    fixture_level: FixtureLevel
    equipment_instance_ids: tuple[str, ...]
    dummy_hp: float
    dummy_physical_defense: float
    dummy_magical_defense: float
    horizon_seconds: float
    coverage_mode: str
    awakening_mode: str
    maximum_mana_override: int | None
    dummy_equipment_instance_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DpsFixtureInputV0":
        forbidden = _FORBIDDEN_INPUT_KEYS.intersection(value)
        if forbidden:
            raise ValueError("fixed dummy input rejects: " + ", ".join(sorted(forbidden)))
        required = {"hero_id", "fixture_level", "equipment_instance_ids", "dummy_hp", "dummy_physical_defense", "dummy_magical_defense", "horizon_seconds"}
        missing = required.difference(value)
        if missing:
            raise ValueError("fixed dummy input missing: " + ", ".join(sorted(missing)))
        raw_level = value["fixture_level"]
        if not isinstance(raw_level, dict) or raw_level.get("kind") != "mathematical_fixture":
            raise ValueError("fixture_level.kind must be mathematical_fixture")
        level = raw_level.get("value")
        if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= _MAX_FIXTURE_LEVEL:
            raise ValueError(f"fixture_level.value must be an integer from 1 to {_MAX_FIXTURE_LEVEL}")
        equipment = value["equipment_instance_ids"]
        if not isinstance(equipment, list) or len(equipment) != len(set(equipment)):
            raise ValueError("equipment_instance_ids must be a unique list")
        if len(equipment) > 3:
            raise ValueError("equipment_instance_ids supports at most three items")
        dummy_equipment = value.get("dummy_equipment_instance_ids", [])
        if not isinstance(dummy_equipment, list) or len(dummy_equipment) != len(set(dummy_equipment)):
            raise ValueError("dummy_equipment_instance_ids must be a unique list")
        if len(dummy_equipment) > 3:
            raise ValueError("dummy_equipment_instance_ids supports at most three items")
        if any(fixed_dummy_target_equipment_support(str(item)) is None for item in dummy_equipment):
            raise ValueError("dummy_equipment_instance_ids contains unsupported target equipment")
        maximum_mana_override = value.get("maximum_mana_override")
        if maximum_mana_override is not None and (
            isinstance(maximum_mana_override, bool)
            or not isinstance(maximum_mana_override, int)
            or maximum_mana_override < 10
        ):
            raise ValueError("maximum_mana_override must be an integer no lower than 10")
        numeric = {key: value[key] for key in ("dummy_hp", "dummy_physical_defense", "dummy_magical_defense", "horizon_seconds")}
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) for item in numeric.values()):
            raise ValueError("dummy and horizon values must be numeric")
        if not 0 < numeric["dummy_hp"] <= _MAX_DUMMY_HP:
            raise ValueError("dummy_hp must be positive and within fixed-dummy bounds")
        if not 0 < numeric["horizon_seconds"] <= _MAX_FIXTURE_HORIZON_SECONDS:
            raise ValueError("horizon_seconds must be positive and within fixed-dummy bounds")
        if any(not 0 <= numeric[key] <= _MAX_DUMMY_DEFENSE for key in ("dummy_physical_defense", "dummy_magical_defense")):
            raise ValueError("dummy defenses must be non-negative and within fixed-dummy bounds")
        coverage_mode = value.get("coverage_mode", "strict")
        if coverage_mode not in {"strict", "exploratory"}:
            raise ValueError("coverage_mode must be strict or exploratory")
        awakening_mode = value.get("awakening_mode", "normal")
        if awakening_mode not in {"normal", "awakened"}:
            raise ValueError("awakening_mode must be normal or awakened")
        return cls(
            str(value["hero_id"]),
            FixtureLevel(level, "mathematical_fixture"),
            tuple(str(item) for item in equipment),
            float(numeric["dummy_hp"]),
            float(numeric["dummy_physical_defense"]),
            float(numeric["dummy_magical_defense"]),
            float(numeric["horizon_seconds"]),
            coverage_mode,
            awakening_mode,
            maximum_mana_override,
            tuple(str(item) for item in dummy_equipment),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EquipmentContribution:
    equipment_id: str
    axis: str
    value: float
    evidence_id: str
    formula: str
    excluded_passive: bool


@dataclass(frozen=True)
class DerivedHeroStat:
    name: str
    value: float
    formula: str
    evidence_ids: tuple[str, ...]
    previous_fixture_level: int | None = None
    previous_fixture_value: float | None = None
    delta_from_previous_fixture_level: float | None = None


@dataclass(frozen=True)
class FixedDummyTargetEquipmentEffect:
    equipment_id: str
    effect_id: str
    status: str
    summary: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    excluded_components: tuple[str, ...]


@dataclass(frozen=True)
class FixedDummyDamageEvent:
    time: float
    event_id: str
    event_type: str
    source_id: str
    target_id: str
    damage_type: str
    raw_value: float
    unmitigated_value: float
    applied_value: float
    cumulative_actual_damage: float
    dummy_remaining_hp: float
    overkill_damage: float
    mana_before: int
    mana_after: int
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    unresolved_items: tuple[str, ...]
    event_semantics: str = "deterministic"
    deterministic_applied_value: float = 0.0
    model_applied_value: float = 0.0
    cumulative_model_damage: float = 0.0
    model_remaining_hp: float = 0.0
    rule_id: str = "fixed-dummy:legacy:v0"
    phase: str = "damage"
    priority: int = 0
    caused_by_event_id: str | None = None
    coverage_tier: str = "strict"


@dataclass(frozen=True)
class FixedDummyStep:
    time: float
    value: float


@dataclass(frozen=True)
class FixedDummyBreakdownEntry:
    key: str
    applied_damage: float
    share: float
    event_count: int


@dataclass(frozen=True)
class FixedDummySkillDamageComponent:
    component_index: int
    damage_type: str
    hit_count: int
    raw_value_per_hit: float
    raw_value_per_cast: float
    formula: str
    source_text: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class FixedDummySkillAuxiliaryValue:
    unlock_level: int
    kind: str
    value: float
    formula: str
    source_text: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    included_in_damage_timeline: bool
    damage_type: str | None = None


@dataclass(frozen=True)
class FixedDummySkillFormulaValue:
    unlock_level: int
    kind: str
    semantic: str
    damage_type: str | None
    raw_value_per_hit: float
    hit_count: int
    raw_value_total: float
    formula: str
    source_text: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    included_in_damage_timeline: bool


@dataclass(frozen=True)
class FixedDummySkillMechanismSchedule:
    schedule_id: str
    unlock_level: int
    status: str
    trigger: str
    event_type: str
    damage_type: str | None
    start_offset_seconds: float | None
    interval_seconds: float | None
    hit_count: int
    raw_value_per_hit: float | None
    raw_value_total: float | None
    formula: str
    source_text: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    unresolved_items: tuple[str, ...]
    included_in_damage_timeline: bool
    target_repeat_policy: str = "single_fixed_target_only"
    cast_every: int = 1
    rule_id: str = "fixed-dummy:legacy-mechanism:v0"
    phase: str = "scheduled_hit"
    priority: int = 50
    coverage_tier: str = "strict"
    hits_per_tick: int = 1


@dataclass(frozen=True)
class FixedDummySkillNodeValue:
    unlock_level: int
    kind: str
    damage_type: str
    raw_value_per_hit: float
    raw_value_per_cast: float
    hit_count: int
    formula: str
    source_text: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    unresolved_items: tuple[str, ...]
    included_in_damage_timeline: bool


@dataclass(frozen=True)
class FixedDummyGrowthResolution:
    status: str
    template: str | None
    source_layer: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    unresolved_items: tuple[str, ...]


@dataclass(frozen=True)
class FixedDummyGrowthAxis:
    stat_name: str
    level_one_value: float
    current_value: float
    delta_from_level_one: float
    previous_fixture_level: int
    previous_value: float
    delta_from_previous_fixture_level: float
    growth_status: str
    formula: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class FixedDummyMitigationSummary:
    damage_type: str
    resistance: float
    damage_multiplier: float
    damage_reduction_percent: float
    formula: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class _BasicAttackBonus:
    event_type: str
    source_id: str
    raw_value: float
    damage_type: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    every_nth_transformed_basic_attack: int = 1


@dataclass(frozen=True)
class _PendingSkillHit:
    time: float
    queue_sequence: int
    schedule_id: str
    event_type: str
    damage_type: str
    raw_value: float
    hit_index: int
    hit_count: int
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    target_repeat_policy: str
    rule_id: str
    phase: str
    priority: int
    caused_by_event_id: str | None
    coverage_tier: str


@dataclass(frozen=True)
class _CombatModifiers:
    opening_attack_speed_percent: float = 0.0
    cast_attack_speed_percent: float = 0.0
    # Base attack-speed changes are resolved before percentage attack speed.
    # This matches the 司空震 in-game measurement: 0.60 -> 0.75, then Golden
    # Staff's percentage is applied.
    opening_attack_speed_base_delta: float = 0.0
    cast_attack_speed_base_delta: float = 0.0
    cast_buff_seconds: float = 0.0
    cast_physical_attack_percent: float = 0.0
    cast_physical_attack_seconds: float = 0.0
    cast_transformed_seconds: float = 0.0
    cast_transformation_persists_to_horizon: bool = False
    transformed_basic_mana_restore: int = 0
    transformed_basic_mana_regeneration_disabled: bool = False
    battle_start_cast: bool = False
    transformed_from_start: bool = False
    always_basic_attack_bonuses: tuple[_BasicAttackBonus, ...] = ()
    transformed_basic_attack_bonuses: tuple[_BasicAttackBonus, ...] = ()
    equipment_contributions: tuple[EquipmentContribution, ...] = ()
    excluded_components: tuple[str, ...] = ()
    unresolved_items: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    damage_amplification_percent: float = 0.0
    magical_penetration: float = 0.0


@dataclass(frozen=True)
class FixedDummyDamageResult:
    schema_version: str
    validated_input: DpsFixtureInputV0
    rule_pack: FixedDummyRulePackV1
    assumptions: tuple[str, ...]
    derived_hero_stats: tuple[DerivedHeroStat, ...]
    equipment_contributions: tuple[EquipmentContribution, ...]
    target_equipment_effects: tuple[FixedDummyTargetEquipmentEffect, ...]
    events: tuple[FixedDummyDamageEvent, ...]
    cumulative_damage_steps: tuple[FixedDummyStep, ...]
    dummy_hp_steps: tuple[FixedDummyStep, ...]
    damage_type_breakdown: tuple[FixedDummyBreakdownEntry, ...]
    damage_source_breakdown: tuple[FixedDummyBreakdownEntry, ...]
    base_skill_damage_components: tuple[FixedDummySkillDamageComponent, ...]
    skill_damage_components: tuple[FixedDummySkillDamageComponent, ...]
    skill_auxiliary_values: tuple[FixedDummySkillAuxiliaryValue, ...]
    skill_formula_values: tuple[FixedDummySkillFormulaValue, ...]
    skill_mechanism_schedules: tuple[FixedDummySkillMechanismSchedule, ...]
    skill_node_values: tuple[FixedDummySkillNodeValue, ...]
    growth_resolution: FixedDummyGrowthResolution
    growth_axes: tuple[FixedDummyGrowthAxis, ...]
    dummy_mitigation: tuple[FixedDummyMitigationSummary, ...]
    kill_status: str
    death_time: float | None
    overkill_damage: float
    total_applied_damage: float
    constrained_average_throughput: float
    total_model_damage: float
    model_average_throughput: float
    unmitigated_model_damage: float
    unmitigated_model_average_throughput: float
    unmitigated_model_scope: str
    model_expected_zero_time: float | None
    kill_confidence: str
    coverage_mode: str
    coverage_gate_status: str
    coverage_gate_notes: tuple[str, ...]
    curve_coverage_status: str
    curve_coverage_summary: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    excluded_components: tuple[str, ...]
    unresolved_items: tuple[str, ...]
    comparison_eligible: bool

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        # These named series keep the two player-facing charts semantically
        # separate even when both are derived from the same event timeline.
        value["chart_series"] = {
            "cumulative_model_damage": {
                "value_semantics": "model_applied_damage",
                "direction": "nondecreasing",
                "steps": [asdict(step) for step in self.cumulative_damage_steps],
            },
            "dummy_remaining_hp": {
                "value_semantics": "deterministic_remaining_hp",
                "direction": "nonincreasing",
                "steps": [asdict(step) for step in self.dummy_hp_steps],
            },
        }
        return value


class FixedDummyDamageEngine:
    def __init__(self, source_root: Path) -> None:
        self.source_root = Path(source_root)
        self._runtime_lock = RLock()
        self._runtime_source_revision: tuple[tuple[str, int, int], ...] | None = None
        self._runtime_rule_pack: FixedDummyRulePackV1 | None = None
        self._runtime_heroes: dict[str, dict[str, Any]] = {}
        self._runtime_growth_catalog: Any = None
        self._runtime_equipment_profiles: dict[str, Any] = {}

    def run(self, fixture: DpsFixtureInputV0) -> FixedDummyDamageResult:
        self._refresh_read_only_runtime_sources()
        rule_pack = self._runtime_rule_pack
        if rule_pack is None:
            raise RuntimeError("fixed dummy runtime sources were not initialized")
        hero, hero_evidence = self._hero(fixture.hero_id)
        attack_style = resolve_hero_attack_style(hero)
        stats, stats_evidence, growth_resolution, growth_axes = self._derived_stats(fixture, hero)
        equipment, contributions, equipment_exclusions = self._equipment(fixture)
        max_health = float(math.floor(
            stats["max_health"] * (1.0 + equipment["max_health_percent"] / 100.0)
        ))
        physical = float(math.floor(
            stats["physical_attack"] * (1.0 + equipment["physical_attack_percent"] / 100.0)
            + equipment["physical_attack"]
        ))
        magical = float(math.floor(
            (stats["magical_attack"] + equipment["magical_attack"]) * (
                1.0 + equipment["magical_attack_percent"] / 100.0
            )
        ))
        physical_defense = stats["physical_defense"] + equipment["physical_defense"]
        magical_defense = stats["magical_defense"] + equipment["magical_defense"]
        critical_rate = min(100.0, max(0.0, stats["critical_rate"] + equipment["critical_rate_percent"]))
        base_critical_effect = 100.0 + float(hero.get("heroCard", {}).get("properties", {}).get("criticalEffect", 0)) / 100.0
        critical_effect = max(0.0, base_critical_effect + equipment["critical_effect_percent"])
        combat_modifiers = _combat_modifiers(
            hero,
            fixture.fixture_level.value,
            magical,
            fixture.equipment_instance_ids,
            fixture.awakening_mode,
        )
        contributions = contributions + combat_modifiers.equipment_contributions
        critical_contributions = tuple(
            item for item in contributions
            if item.axis in {"critical_rate_percent", "critical_effect_percent"}
        )
        critical_source_ids = tuple(dict.fromkeys(item.equipment_id for item in critical_contributions))
        critical_source_id = critical_source_ids[0] if len(critical_source_ids) == 1 else "fixture:critical-model"
        critical_evidence_ids = tuple(dict.fromkeys(
            hero_evidence + tuple(item.evidence_id for item in critical_contributions)
        ))
        opening_attack_speed_percent = (
            equipment["attack_speed_percent"]
            + combat_modifiers.opening_attack_speed_percent
        )
        attack_speed = _capped_attack_speed((
            stats["attack_speed"] + combat_modifiers.opening_attack_speed_base_delta
        ) * (
            1.0 + opening_attack_speed_percent / 100.0
        ))
        attack_speed_during_skill = _capped_attack_speed((
            stats["attack_speed"]
            + combat_modifiers.opening_attack_speed_base_delta
            + combat_modifiers.cast_attack_speed_base_delta
        ) * (
            1.0
            + (
                opening_attack_speed_percent
                + combat_modifiers.cast_attack_speed_percent
            ) / 100.0
        ))
        if attack_speed <= 0:
            raise ValueError("derived attack speed must be positive")
        # The fixture contract never permits a usable skill bar below 10.  This
        # keeps a negative maximum-mana item legal when a player deliberately
        # selects the minimum base cap for a comparison.
        source_maximum_mana = max(10, int(stats["maximum_mana"] + equipment["max_energy_flat"]))
        if str(hero.get("id") or "") == "1821" and "equipment:42102" in fixture.equipment_instance_ids:
            source_maximum_mana = 10
        if fixture.maximum_mana_override is not None and fixture.maximum_mana_override > source_maximum_mana:
            raise ValueError("maximum_mana_override cannot exceed the resolved source maximum mana")
        maximum_mana = fixture.maximum_mana_override if fixture.maximum_mana_override is not None else source_maximum_mana
        source_initial_mana = max(0, int(stats["initial_mana"] + equipment["initial_energy_flat"]))
        initial_mana = min(maximum_mana, source_initial_mana)
        mana_selection_assumptions = (
            ("selected_maximum_mana_fixture_override",)
            if fixture.maximum_mana_override is not None
            else ("source_maximum_mana_used",)
        ) + (
            ("initial_mana_clipped_to_selected_maximum",)
            if initial_mana < source_initial_mana
            else ()
        )
        target_equipment_effects = _target_dummy_equipment_effects(fixture)
        formulas = _active_skill_formulas(hero, physical, magical)
        direct = tuple(item for item in formulas if item.raw_damage_per_cast is not None and not _mechanism_managed(item.active_text))
        base_direct = direct
        direct = _apply_unlocked_active_skill_enhancements(
            hero,
            fixture.fixture_level.value,
            direct,
            physical,
            magical,
        )
        base_hit_count = (
            direct[0].components[0].hit_count
            if len(direct) == 1 and len(direct[0].components) == 1
            else 1
        )
        base_component = (
            direct[0].components[0]
            if len(direct) == 1 and len(direct[0].components) == 1
            else None
        )
        skill_node_values, selected_node, node_unresolved = _skill_node_values(
            hero,
            fixture.fixture_level.value,
            physical,
            magical,
            base_hit_count,
            (
                base_component.raw_damage(physical, magical) / max(1, base_component.hit_count)
                if base_component is not None
                else None
            ),
            base_component.damage_type if base_component is not None else None,
            hero_evidence,
        )
        if selected_node is not None and len(direct) == 1 and len(direct[0].components) == 1:
            direct = (_formula_from_skill_node(selected_node, direct[0], physical, magical),)
        base_skill_damage_components = _skill_damage_components(
            base_direct,
            physical,
            magical,
            hero_evidence,
        )
        skill_damage_components = _skill_damage_components(direct, physical, magical, hero_evidence)
        active_hits = tuple(
            (
                component.raw_damage(physical, magical) / max(1, component.hit_count),
                component.damage_type,
            )
            for formula in direct
            for component in formula.components
            for _ in range(max(1, component.hit_count))
        )
        active_assumptions = tuple(dict.fromkeys(
            assumption
            for formula in direct
            for assumption in formula.assumptions
        ))
        unresolved = [
            *(("active_skill_hit_time_is_cast_start_proxy",) if active_hits else ()),
            *growth_resolution.unresolved_items,
            *node_unresolved,
            *combat_modifiers.unresolved_items,
        ]
        if active_hits and any(
            damage_type not in {"physical", "magical", "true"}
            for _, damage_type in active_hits
        ):
            active_hits = ()
            unresolved.append("mixed_or_unknown_active_damage_type_excluded")
        mechanism_schedules = _skill_mechanism_schedules(
            hero,
            fixture.fixture_level.value,
            physical,
            magical,
            fixture.dummy_hp,
            fixture.horizon_seconds,
            hero_evidence,
            attack_speed,
            rule_pack,
        )
        unresolved.extend(
            item
            for schedule in mechanism_schedules
            for item in schedule.unresolved_items
        )
        basic_attack_bonus_hits, basic_attack_bonus_assumptions = _basic_attack_bonus_hits(
            hero,
            fixture.fixture_level.value,
            physical,
        )
        events, magical_end, coverage_gate_exclusions = self._simulate(
            fixture, physical, magical, max_health, attack_speed, attack_speed_during_skill,
            initial_mana, maximum_mana,
            active_hits, active_assumptions, hero_evidence,
            basic_attack_bonus_hits, basic_attack_bonus_assumptions,
            combat_modifiers, hero, fixture.fixture_level.value,
            attack_style.is_ranged,
            critical_rate, critical_effect, critical_source_id, critical_evidence_ids,
            rule_pack, target_equipment_effects,
        )
        events, total_model, model_expected_zero_time = _with_model_counters(events, fixture.dummy_hp)
        total = events[-1].cumulative_actual_damage if events else 0.0
        unmitigated_model_damage = sum(item.unmitigated_value for item in events)
        killed = bool(events and events[-1].dummy_remaining_hp <= 0)
        damage_type_breakdown, damage_source_breakdown = _damage_breakdowns(events)
        expected_event_count = sum(item.event_semantics == "expected_value_increment" for item in events)
        proxy_event_count = sum(any("proxy" in assumption for assumption in item.assumptions) for item in events)
        curve_coverage_status = (
            "strict_with_timing_proxy"
            if fixture.coverage_mode == "strict" and proxy_event_count
            else "strict_deterministic_events"
            if fixture.coverage_mode == "strict"
            else "partial_with_model_proxies"
            if expected_event_count or proxy_event_count
            else "partial_deterministic_events"
        )
        curve_coverage_summary = tuple(filter(None, (
            f"deterministic_events:{len(events) - expected_event_count}",
            f"expected_value_events:{expected_event_count}" if expected_event_count else "",
            f"proxy_timed_events:{proxy_event_count}" if proxy_event_count else "",
            f"scheduled_skill_nodes:{sum(item.included_in_damage_timeline for item in mechanism_schedules)}",
            f"coverage_mode:{fixture.coverage_mode}",
        )))
        coverage_gate_notes = tuple(sorted(coverage_gate_exclusions)) + (
            ("growth_model_is_inferred_for_fixture",)
            if growth_resolution.status != "model_ready"
            else ()
        )
        coverage_gate_status = (
            "strict_with_exclusions"
            if fixture.coverage_mode == "strict" and coverage_gate_notes
            else "strict_deterministic_scope"
            if fixture.coverage_mode == "strict"
            else "exploratory_modeled_scope"
        )
        kill_confidence = (
            "deterministic_events_only"
            if killed
            else "model_expected_zero_not_deterministic_kill"
            if model_expected_zero_time is not None
            else "not_killed_within_horizon"
        )
        max_health_evidence = tuple(
            evidence_id
            for stat in stats_evidence
            if stat.name == "max_health"
            for evidence_id in stat.evidence_ids
        )
        auxiliary_values = _skill_auxiliary_values(
            hero,
            fixture.fixture_level.value,
            max_health,
            fixture.dummy_hp,
            physical,
            skill_damage_components,
            hero_evidence + max_health_evidence,
        )
        formula_values = _skill_formula_values(
            hero,
            fixture.fixture_level.value,
            max_health,
            fixture.dummy_hp,
            physical,
            magical,
            hero_evidence,
        )
        current_node_values = tuple(
            item for item in skill_node_values if item.included_in_damage_timeline
        )
        formula_values = tuple(
            replace(item, included_in_damage_timeline=True)
            if item.semantic == "damage" and (
                any(
                    item.unlock_level == node.unlock_level
                    and item.damage_type == node.damage_type
                    and abs(item.raw_value_per_hit - node.raw_value_per_hit) < 1e-9
                    and item.hit_count == node.hit_count
                    for node in current_node_values
                )
                or (
                    not current_node_values
                    and item.unlock_level == 1
                    and any(
                        item.damage_type == component.damage_type
                        and abs(item.raw_value_per_hit - component.raw_value_per_hit) < 1e-9
                        and item.hit_count == component.hit_count
                        for component in skill_damage_components
                    )
                )
                or any(
                    schedule.included_in_damage_timeline
                    and schedule.unlock_level == item.unlock_level
                    and schedule.damage_type == item.damage_type
                    and schedule.raw_value_per_hit is not None
                    and abs(item.raw_value_per_hit - schedule.raw_value_per_hit) < 1e-9
                    for schedule in mechanism_schedules
                )
            )
            else item
            for item in formula_values
        )
        contribution_evidence = tuple(item.evidence_id for item in contributions)
        previous_fixture_level = _previous_fixture_level(fixture.fixture_level.value)
        previous_growth_values = {
            item.stat_name: item.previous_value
            for item in growth_axes
        }
        previous_magical = float(math.floor(
            (previous_growth_values["magical_attack"] + equipment["magical_attack"]) * (
                1.0 + equipment["magical_attack_percent"] / 100.0
            )
        ))
        previous_modifiers = _combat_modifiers(
            hero,
            previous_fixture_level,
            previous_magical,
            fixture.equipment_instance_ids,
            fixture.awakening_mode,
        )
        previous_equipped_values = {
            "max_health_with_equipment": float(math.floor(
                previous_growth_values["max_health"] * (1.0 + equipment["max_health_percent"] / 100.0)
            )),
            "physical_attack_with_equipment": float(math.floor(
                previous_growth_values["physical_attack"] * (1.0 + equipment["physical_attack_percent"] / 100.0)
                + equipment["physical_attack"]
            )),
            "magical_attack_with_equipment": previous_magical,
            "attack_speed_with_equipment": _capped_attack_speed((
                previous_growth_values["attack_speed"] + previous_modifiers.opening_attack_speed_base_delta
            ) * (
                1.0 + (equipment["attack_speed_percent"] + previous_modifiers.opening_attack_speed_percent) / 100.0
            )),
            "critical_rate_with_equipment": min(
                100.0,
                max(0.0, previous_growth_values["critical_rate"] + equipment["critical_rate_percent"]),
            ),
            "critical_effect_with_equipment": critical_effect,
            "damage_amplification_percent": combat_modifiers.damage_amplification_percent,
        }

        def equipped_stat(name, value, formula, evidence):
            previous_value = previous_equipped_values.get(name)
            return DerivedHeroStat(
                name,
                value,
                formula,
                evidence,
                previous_fixture_level if previous_value is not None else None,
                previous_value,
                value - previous_value if previous_value is not None else None,
            )

        derived_with_equipment = (
            equipped_stat("max_health_with_equipment", max_health, "base_max_health*(1+equipment_max_health_percent/100)", hero_evidence + contribution_evidence),
            equipped_stat("physical_attack_with_equipment", physical, "floor(base_physical_attack*(1+equipment_base_physical_attack_percent/100)+equipment_flat_physical_attack)", hero_evidence + contribution_evidence),
            equipped_stat("magical_attack_with_equipment", magical, "(base_magical_attack+equipment_flat_magical_attack)*(1+equipment_magical_attack_percent/100)", hero_evidence + contribution_evidence),
            DerivedHeroStat("physical_defense_with_equipment", physical_defense, "base_physical_defense+equipment_flat_physical_defense", hero_evidence + contribution_evidence),
            DerivedHeroStat("magical_defense_with_equipment", magical_defense, "base_magical_defense+equipment_flat_magical_defense", hero_evidence + contribution_evidence),
            equipped_stat("attack_speed_with_equipment", attack_speed, "min(attack_speed_cap=4.0,(base_attack_speed+opening_base_attack_speed_delta)*(1+(opening_and_equipment_attack_speed_percent)/100))", hero_evidence + contribution_evidence + (ATTACK_SPEED_CAP_RULE.rule_id,)),
            equipped_stat("critical_rate_with_equipment", critical_rate, "min(100,base_critical_rate+equipment_critical_rate_percent)", critical_evidence_ids),
            equipped_stat("critical_effect_with_equipment", critical_effect, "base_critical_effect_percent+equipment_critical_effect_percent", critical_evidence_ids),
            DerivedHeroStat(
                "initial_mana_with_equipment",
                float(initial_mana),
                "min(selected_maximum_mana,base_initial_mana+equipment_initial_energy_flat)",
                hero_evidence + contribution_evidence,
            ),
            DerivedHeroStat(
                "maximum_mana_source_cap",
                float(source_maximum_mana),
                "max(0,base_maximum_mana+equipment_max_energy_flat)",
                hero_evidence + contribution_evidence,
            ),
            DerivedHeroStat(
                "maximum_mana_with_equipment",
                float(maximum_mana),
                "maximum_mana_override_if_supplied_else_max(0,base_maximum_mana+equipment_max_energy_flat)",
                hero_evidence + contribution_evidence,
            ),
            equipped_stat("damage_amplification_percent", combat_modifiers.damage_amplification_percent, "red_demon_no_adjacent_ally_fixture_amplification" if combat_modifiers.damage_amplification_percent else "no_supported_damage_amplification_source", hero_evidence + contribution_evidence),
        ) + (
            (
                DerivedHeroStat(
                    "magical_attack_end_of_horizon",
                    magical_end,
                    "initial_magical_attack+pure_sky_ticks+sage_book_post_cast_stacks+erin_level_40_basic_attack_stacks",
                    hero_evidence + contribution_evidence,
                ),
            )
            if abs(magical_end - magical) > 1e-9
            else ()
        ) + (
            (
                DerivedHeroStat(
                    "attack_speed_during_skill",
                    attack_speed_during_skill,
                    "min(attack_speed_cap=4.0,(base_attack_speed+opening_base_attack_speed_delta+cast_base_attack_speed_delta)*(1+(opening_and_equipment_attack_speed_percent+cast_attack_speed_percent)/100))",
                    hero_evidence + contribution_evidence + (ATTACK_SPEED_CAP_RULE.rule_id,),
                ),
            )
            if combat_modifiers.cast_attack_speed_percent > 0 or combat_modifiers.cast_attack_speed_base_delta > 0
            else ()
        )
        return FixedDummyDamageResult(
            schema_version="fixed-dummy-damage-result-v1",
            validated_input=fixture,
            rule_pack=rule_pack,
            assumptions=_FIXED_ASSUMPTIONS + combat_modifiers.assumptions + mana_selection_assumptions + tuple(
                assumption
                for effect in target_equipment_effects
                for assumption in effect.assumptions
            ),
            derived_hero_stats=stats_evidence + derived_with_equipment,
            equipment_contributions=contributions,
            target_equipment_effects=target_equipment_effects,
            events=events,
            cumulative_damage_steps=(FixedDummyStep(0.0, 0.0),) + tuple(FixedDummyStep(item.time, item.cumulative_model_damage) for item in events),
            dummy_hp_steps=(FixedDummyStep(0.0, fixture.dummy_hp),) + tuple(FixedDummyStep(item.time, item.dummy_remaining_hp) for item in events),
            damage_type_breakdown=damage_type_breakdown,
            damage_source_breakdown=damage_source_breakdown,
            base_skill_damage_components=base_skill_damage_components,
            skill_damage_components=skill_damage_components,
            skill_auxiliary_values=auxiliary_values,
            skill_formula_values=formula_values,
            skill_mechanism_schedules=mechanism_schedules,
            skill_node_values=skill_node_values,
            growth_resolution=growth_resolution,
            growth_axes=growth_axes,
            dummy_mitigation=_dummy_mitigation(fixture, combat_modifiers),
            kill_status="killed" if killed else "not_killed_within_horizon",
            death_time=events[-1].time if killed else None,
            overkill_damage=events[-1].overkill_damage if killed else 0.0,
            total_applied_damage=total,
            constrained_average_throughput=total / fixture.horizon_seconds,
            total_model_damage=total_model,
            model_average_throughput=total_model / fixture.horizon_seconds,
            unmitigated_model_damage=unmitigated_model_damage,
            unmitigated_model_average_throughput=unmitigated_model_damage / fixture.horizon_seconds,
            unmitigated_model_scope="generated_trace_no_dummy_resistance_death_truncated",
            model_expected_zero_time=model_expected_zero_time,
            kill_confidence=kill_confidence,
            coverage_mode=fixture.coverage_mode,
            coverage_gate_status=coverage_gate_status,
            coverage_gate_notes=coverage_gate_notes,
            curve_coverage_status=curve_coverage_status,
            curve_coverage_summary=curve_coverage_summary,
            evidence_ids=tuple(dict.fromkeys(hero_evidence + contribution_evidence + growth_resolution.evidence_ids)),
            excluded_components=_EXCLUDED_COMPONENTS + tuple(equipment_exclusions) + combat_modifiers.excluded_components + tuple(
                excluded
                for effect in target_equipment_effects
                for excluded in effect.excluded_components
            ),
            unresolved_items=tuple(dict.fromkeys(unresolved)),
            comparison_eligible=False,
        )

    def supporting_context(self, fixture: DpsFixtureInputV0) -> dict[str, object]:
        """Resolve the static inputs needed by non-damage fixture trials.

        This deliberately stops before formula parsing and event scheduling.  A
        durability trial needs derived attributes and target effects, not a
        discarded attack trace.
        """
        self._refresh_read_only_runtime_sources()
        hero, hero_evidence = self._hero(fixture.hero_id)
        stats, stats_evidence, growth_resolution, growth_axes = self._derived_stats(fixture, hero)
        equipment, contributions, equipment_exclusions = self._equipment(fixture)
        max_health = float(math.floor(
            stats["max_health"] * (1.0 + equipment["max_health_percent"] / 100.0)
        ))
        physical = float(math.floor(
            stats["physical_attack"] * (1.0 + equipment["physical_attack_percent"] / 100.0)
            + equipment["physical_attack"]
        ))
        magical = float(math.floor(
            (stats["magical_attack"] + equipment["magical_attack"]) * (
                1.0 + equipment["magical_attack_percent"] / 100.0
            )
        ))
        physical_defense = stats["physical_defense"] + equipment["physical_defense"]
        magical_defense = stats["magical_defense"] + equipment["magical_defense"]
        critical_rate = min(100.0, max(0.0, stats["critical_rate"] + equipment["critical_rate_percent"]))
        base_critical_effect = 100.0 + float(hero.get("heroCard", {}).get("properties", {}).get("criticalEffect", 0)) / 100.0
        critical_effect = max(0.0, base_critical_effect + equipment["critical_effect_percent"])
        combat_modifiers = _combat_modifiers(
            hero,
            fixture.fixture_level.value,
            magical,
            fixture.equipment_instance_ids,
            fixture.awakening_mode,
        )
        contributions = contributions + combat_modifiers.equipment_contributions
        critical_contributions = tuple(
            item for item in contributions
            if item.axis in {"critical_rate_percent", "critical_effect_percent"}
        )
        critical_evidence_ids = tuple(dict.fromkeys(
            hero_evidence + tuple(item.evidence_id for item in critical_contributions)
        ))
        opening_attack_speed_percent = (
            equipment["attack_speed_percent"]
            + combat_modifiers.opening_attack_speed_percent
        )
        attack_speed = _capped_attack_speed((
            stats["attack_speed"] + combat_modifiers.opening_attack_speed_base_delta
        ) * (
            1.0 + opening_attack_speed_percent / 100.0
        ))
        attack_speed_during_skill = _capped_attack_speed((
            stats["attack_speed"]
            + combat_modifiers.opening_attack_speed_base_delta
            + combat_modifiers.cast_attack_speed_base_delta
        ) * (
            1.0
            + (
                opening_attack_speed_percent
                + combat_modifiers.cast_attack_speed_percent
            ) / 100.0
        ))
        if attack_speed <= 0:
            raise ValueError("derived attack speed must be positive")
        source_maximum_mana = max(10, int(stats["maximum_mana"] + equipment["max_energy_flat"]))
        if str(hero.get("id") or "") == "1821" and "equipment:42102" in fixture.equipment_instance_ids:
            source_maximum_mana = 10
        if fixture.maximum_mana_override is not None and fixture.maximum_mana_override > source_maximum_mana:
            raise ValueError("maximum_mana_override cannot exceed the resolved source maximum mana")
        maximum_mana = fixture.maximum_mana_override if fixture.maximum_mana_override is not None else source_maximum_mana
        source_initial_mana = max(0, int(stats["initial_mana"] + equipment["initial_energy_flat"]))
        initial_mana = min(maximum_mana, source_initial_mana)
        target_equipment_effects = _target_dummy_equipment_effects(fixture)

        previous_fixture_level = _previous_fixture_level(fixture.fixture_level.value)
        previous_growth_values = {
            item.stat_name: item.previous_value
            for item in growth_axes
        }
        previous_magical = float(math.floor(
            (previous_growth_values["magical_attack"] + equipment["magical_attack"]) * (
                1.0 + equipment["magical_attack_percent"] / 100.0
            )
        ))
        previous_modifiers = _combat_modifiers(
            hero,
            previous_fixture_level,
            previous_magical,
            fixture.equipment_instance_ids,
            fixture.awakening_mode,
        )
        previous_equipped_values = {
            "max_health_with_equipment": float(math.floor(
                previous_growth_values["max_health"] * (1.0 + equipment["max_health_percent"] / 100.0)
            )),
            "physical_attack_with_equipment": float(math.floor(
                previous_growth_values["physical_attack"] * (1.0 + equipment["physical_attack_percent"] / 100.0)
                + equipment["physical_attack"]
            )),
            "magical_attack_with_equipment": previous_magical,
            "attack_speed_with_equipment": _capped_attack_speed((
                previous_growth_values["attack_speed"] + previous_modifiers.opening_attack_speed_base_delta
            ) * (
                1.0 + (equipment["attack_speed_percent"] + previous_modifiers.opening_attack_speed_percent) / 100.0
            )),
            "critical_rate_with_equipment": min(
                100.0,
                max(0.0, previous_growth_values["critical_rate"] + equipment["critical_rate_percent"]),
            ),
            "critical_effect_with_equipment": critical_effect,
            "damage_amplification_percent": combat_modifiers.damage_amplification_percent,
        }

        contribution_evidence = tuple(item.evidence_id for item in contributions)

        def equipped_stat(name: str, value: float, formula: str, evidence: tuple[str, ...]) -> DerivedHeroStat:
            previous_value = previous_equipped_values.get(name)
            return DerivedHeroStat(
                name,
                value,
                formula,
                evidence,
                previous_fixture_level if previous_value is not None else None,
                previous_value,
                value - previous_value if previous_value is not None else None,
            )

        derived_with_equipment = (
            equipped_stat("max_health_with_equipment", max_health, "base_max_health*(1+equipment_max_health_percent/100)", hero_evidence + contribution_evidence),
            equipped_stat("physical_attack_with_equipment", physical, "floor(base_physical_attack*(1+equipment_base_physical_attack_percent/100)+equipment_flat_physical_attack)", hero_evidence + contribution_evidence),
            equipped_stat("magical_attack_with_equipment", magical, "(base_magical_attack+equipment_flat_magical_attack)*(1+equipment_magical_attack_percent/100)", hero_evidence + contribution_evidence),
            DerivedHeroStat("physical_defense_with_equipment", physical_defense, "base_physical_defense+equipment_flat_physical_defense", hero_evidence + contribution_evidence),
            DerivedHeroStat("magical_defense_with_equipment", magical_defense, "base_magical_defense+equipment_flat_magical_defense", hero_evidence + contribution_evidence),
            equipped_stat("attack_speed_with_equipment", attack_speed, "min(attack_speed_cap=4.0,(base_attack_speed+opening_base_attack_speed_delta)*(1+(opening_and_equipment_attack_speed_percent)/100))", hero_evidence + contribution_evidence + (ATTACK_SPEED_CAP_RULE.rule_id,)),
            equipped_stat("critical_rate_with_equipment", critical_rate, "min(100,base_critical_rate+equipment_critical_rate_percent)", critical_evidence_ids),
            equipped_stat("critical_effect_with_equipment", critical_effect, "base_critical_effect_percent+equipment_critical_effect_percent", critical_evidence_ids),
            DerivedHeroStat(
                "initial_mana_with_equipment",
                float(initial_mana),
                "min(selected_maximum_mana,base_initial_mana+equipment_initial_energy_flat)",
                hero_evidence + contribution_evidence,
            ),
            DerivedHeroStat(
                "maximum_mana_source_cap",
                float(source_maximum_mana),
                "max(0,base_maximum_mana+equipment_max_energy_flat)",
                hero_evidence + contribution_evidence,
            ),
            DerivedHeroStat(
                "maximum_mana_with_equipment",
                float(maximum_mana),
                "maximum_mana_override_if_supplied_else_max(0,base_maximum_mana+equipment_max_energy_flat)",
                hero_evidence + contribution_evidence,
            ),
            equipped_stat("damage_amplification_percent", combat_modifiers.damage_amplification_percent, "red_demon_no_adjacent_ally_fixture_amplification" if combat_modifiers.damage_amplification_percent else "no_supported_damage_amplification_source", hero_evidence + contribution_evidence),
        ) + (
            (
                DerivedHeroStat(
                    "attack_speed_during_skill",
                    attack_speed_during_skill,
                    "min(attack_speed_cap=4.0,(base_attack_speed+opening_base_attack_speed_delta+cast_base_attack_speed_delta)*(1+(opening_and_equipment_attack_speed_percent+cast_attack_speed_percent)/100))",
                    hero_evidence + contribution_evidence + (ATTACK_SPEED_CAP_RULE.rule_id,),
                ),
            )
            if combat_modifiers.cast_attack_speed_percent > 0 or combat_modifiers.cast_attack_speed_base_delta > 0
            else ()
        )
        all_stats = stats_evidence + derived_with_equipment
        serialized_stats = tuple(asdict(item) for item in all_stats)
        serialized_equipment = tuple(asdict(item) for item in contributions)
        serialized_target_equipment = tuple(asdict(item) for item in target_equipment_effects)
        serialized_growth = asdict(growth_resolution)
        evidence_ids = tuple(dict.fromkeys(
            evidence_id
            for item in (*serialized_stats, *serialized_equipment, *serialized_target_equipment)
            for evidence_id in item.get("evidence_ids", (item.get("evidence_id"),))
            if evidence_id
        )) + tuple(
            evidence_id
            for evidence_id in serialized_growth.get("evidence_ids", ())
            if evidence_id
        )
        excluded = tuple(
            item
            for item in (
                *equipment_exclusions,
                *combat_modifiers.excluded_components,
                *(excluded for effect in target_equipment_effects for excluded in effect.excluded_components),
            )
            if str(item).startswith("equipment_")
        )
        return {
            "schema_version": "fixed-dummy-trial-supporting-context-v1",
            "derived_hero_stats": serialized_stats,
            "equipment_contributions": serialized_equipment,
            "target_equipment_effects": serialized_target_equipment,
            "growth_resolution": serialized_growth,
            "growth_axes": tuple(asdict(item) for item in growth_axes),
            "evidence_ids": tuple(dict.fromkeys(evidence_ids)),
            "assumptions": (
                "mathematical_fixture_level_not_valid_for_p5_or_p6",
                "supporting_context_contains_derived_properties_only",
                *tuple(serialized_growth.get("assumptions", ())),
            ),
            "excluded_components": excluded,
            "unresolved_items": tuple(serialized_growth.get("unresolved_items", ())),
        }

    def _refresh_read_only_runtime_sources(self) -> None:
        """Keep one in-memory read-only snapshot until an upstream file changes."""
        revision = _runtime_source_revision(self.source_root)
        with self._runtime_lock:
            if revision == self._runtime_source_revision:
                return
            reader = UpstreamReader(self.source_root)
            raw_heroes = reader.read_json(SourceKey.RAW_HEROES)
            heroes = {
                f"hero:{item['id']}": item
                for item in raw_heroes["heroCards"]
                if item.get("id") is not None and isinstance(item.get("heroCard"), dict)
            }
            growth_catalog = GrowthModelLoader().load(self.source_root)
            equipment_profiles = {
                item.equipment_id: item
                for item in EquipmentValueCatalog(self.source_root).fixed_dummy_profiles()
            }
            rule_pack = build_fixed_dummy_rule_pack(self.source_root)
            self._runtime_source_revision = revision
            self._runtime_heroes = heroes
            self._runtime_growth_catalog = growth_catalog
            self._runtime_equipment_profiles = equipment_profiles
            self._runtime_rule_pack = rule_pack

    def _hero(self, hero_id: str) -> tuple[dict[str, Any], tuple[str, ...]]:
        self._refresh_read_only_runtime_sources()
        hero = self._runtime_heroes.get(hero_id)
        if hero is None:
            raise ValueError("unknown or non-combat hero_id")
        return hero, (f"official-raw:{hero_id}:hero-card",)

    def _derived_stats(self, fixture: DpsFixtureInputV0, hero: dict[str, Any]) -> tuple[dict[str, float], tuple[DerivedHeroStat, ...], FixedDummyGrowthResolution, tuple[FixedDummyGrowthAxis, ...]]:
        self._refresh_read_only_runtime_sources()
        catalog = self._runtime_growth_catalog
        model = catalog.by_hero_id().get(fixture.hero_id)
        properties = hero.get("heroCard", {}).get("properties", {})
        previous_fixture_level = _previous_fixture_level(fixture.fixture_level.value)
        if model is None:
            level_one_properties = _official_base_properties(properties)
            inferred = _infer_fixture_growth(
                catalog.models,
                level_one_properties,
                fixture.fixture_level.value,
            )
            if inferred is None:
                raise ValueError("hero growth model unavailable")
            derived_values, template, inference_evidence = inferred
            previous_inferred = _infer_fixture_growth(
                catalog.models,
                level_one_properties,
                previous_fixture_level,
            )
            if previous_inferred is None:
                raise ValueError("hero previous fixture growth unavailable")
            previous_derived_values = previous_inferred[0]
            level_one_values = dict(level_one_properties)
            formula = "fixed_dummy_template_inference_from_official_base_stat_signature"
            evidence = (inference_evidence,)
            resolution = FixedDummyGrowthResolution(
                "fixture_template_inferred",
                template,
                "model_derivation",
                evidence,
                (
                    "fallback_template_inferred_from_official_base_stat_signature",
                    "fixed_dummy_lab_only",
                    "not_valid_for_p5_or_p6",
                ),
                ("official_growth_model_missing",),
            )
        else:
            derived = model.derive(fixture.fixture_level.value)
            previous_derived_values = dict(model.derive(previous_fixture_level).values)
            level_one_values = dict(model.derive(1).values)
            formula = "growth_model_fixture_level"
            evidence = (f"model:{derived.model_version}:{fixture.hero_id}",)
            resolution = FixedDummyGrowthResolution(
                "model_ready" if model.status == "model_ready" else "growth_template_unresolved",
                model.template or None,
                "model_derivation",
                evidence,
                derived.assumptions,
                derived.unresolved_items,
            )
            if model.status != "model_ready":
                inferred = _infer_fixture_growth(
                    catalog.models,
                    model.base_properties,
                    fixture.fixture_level.value,
                )
            else:
                inferred = None
            if inferred is not None:
                inferred_values, template, inference_evidence = inferred
                derived_values = inferred_values
                previous_inferred = _infer_fixture_growth(
                    catalog.models,
                    model.base_properties,
                    previous_fixture_level,
                )
                if previous_inferred is None:
                    raise ValueError("hero previous fixture growth unavailable")
                previous_derived_values = previous_inferred[0]
                level_one_values = dict(model.base_properties)
                formula = "fixed_dummy_template_inference_from_base_stat_signature"
                evidence = (inference_evidence,)
                resolution = FixedDummyGrowthResolution(
                    "fixture_template_inferred",
                    template,
                    "model_derivation",
                    evidence,
                    (
                        "fallback_template_inferred_from_base_stat_signature",
                        "fixed_dummy_lab_only",
                        "not_valid_for_p5_or_p6",
                    ),
                    ("official_growth_template_unresolved",),
                )
            else:
                derived_values = dict(derived.values)
        values = {
            "max_health": float(math.floor(float(derived_values.get("生命", 0)))),
            "physical_attack": float(math.floor(float(derived_values.get("物攻", 0)))),
            "magical_attack": float(math.floor(float(derived_values.get("法攻", 0)))),
            "physical_defense": float(derived_values.get("物防", 0)),
            "magical_defense": float(derived_values.get("法防", 0)),
            "attack_speed": float(derived_values.get("基础攻速", 0)),
            "critical_rate": float(derived_values.get("暴击率", 0)),
            "initial_mana": float(properties.get("initEnergy", 0)),
            "maximum_mana": float(properties.get("energy", 0)),
        }
        source_names = {
            "max_health": "生命",
            "physical_attack": "物攻",
            "magical_attack": "法攻",
            "physical_defense": "物防",
            "magical_defense": "法防",
            "attack_speed": "基础攻速",
            "critical_rate": "暴击率",
        }
        level_one = {
            key: (
                float(properties.get("initEnergy", 0))
                if key == "initial_mana"
                else float(properties.get("energy", 0))
                if key == "maximum_mana"
                else float(math.floor(float(level_one_values.get(source_names[key], 0))))
                if key in {"max_health", "physical_attack", "magical_attack"}
                else float(level_one_values.get(source_names[key], 0))
            )
            for key in values
        }
        previous = {
            key: (
                float(properties.get("initEnergy", 0))
                if key == "initial_mana"
                else float(properties.get("energy", 0))
                if key == "maximum_mana"
                else float(math.floor(float(previous_derived_values.get(source_names[key], 0))))
                if key in {"max_health", "physical_attack", "magical_attack"}
                else float(previous_derived_values.get(source_names[key], 0))
            )
            for key in values
        }
        stats = tuple(
            DerivedHeroStat(
                key,
                value,
                "official_raw_hero_energy" if key in {"initial_mana", "maximum_mana"} else formula,
                (f"official-raw:{fixture.hero_id}:hero-card",) if key in {"initial_mana", "maximum_mana"} else evidence,
            )
            for key, value in values.items()
        )
        growth_axes = tuple(
            FixedDummyGrowthAxis(
                stat_name=key,
                level_one_value=level_one[key],
                current_value=value,
                delta_from_level_one=value - level_one[key],
                previous_fixture_level=previous_fixture_level,
                previous_value=previous[key],
                delta_from_previous_fixture_level=value - previous[key],
                growth_status="changing" if abs(value - level_one[key]) > 1e-9 else "fixed",
                formula="current_fixture_value-previous_fixture_preset_value",
                evidence_ids=(f"official-raw:{fixture.hero_id}:hero-card",) if key in {"initial_mana", "maximum_mana"} else evidence,
                assumptions=(
                    "compares_selected_fixture_level_to_previous_fixture_preset",
                    "equipment_contributions_excluded_from_growth_axis",
                ) + (
                    ("health_and_attack_axes_floor_fractional_part",)
                    if key in {"max_health", "physical_attack", "magical_attack"}
                    else ()
                ),
            )
            for key, value in values.items()
        )
        return values, stats, resolution, growth_axes

    def _equipment(self, fixture: DpsFixtureInputV0) -> tuple[dict[str, float], tuple[EquipmentContribution, ...], tuple[str, ...]]:
        self._refresh_read_only_runtime_sources()
        profiles = self._runtime_equipment_profiles
        totals = {
            "physical_attack": 0.0,
            "physical_attack_percent": 0.0,
            "magical_attack": 0.0,
            "physical_defense": 0.0,
            "magical_defense": 0.0,
            "attack_speed_percent": 0.0,
            "max_health_percent": 0.0,
            "max_energy_flat": 0.0,
            "initial_energy_flat": 0.0,
            "magical_attack_percent": 0.0,
            "critical_rate_percent": 0.0,
            "critical_effect_percent": 0.0,
        }
        contributions = []
        exclusions = []
        for equipment_id in fixture.equipment_instance_ids:
            profile = profiles.get(equipment_id)
            if profile is None:
                raise ValueError(f"unsupported equipment: {equipment_id}")
            if equipment_id == _GOLDEN_STAFF_ID:
                continue
            axes = {item.axis for item in profile.static_attributes}
            if (not axes or not axes.issubset(_SUPPORTED_EQUIPMENT_AXES)) and fixed_dummy_equipment_support(equipment_id) is None:
                exclusions.append(
                    f"equipment_static_and_passive_effects_excluded:{equipment_id}"
                )
                continue
            support = fixed_dummy_equipment_support(equipment_id)
            if support is None:
                exclusions.append(f"equipment_passive_excluded:{equipment_id}")
            elif support[0] == "supported_static_only":
                exclusions.append(f"equipment_passive_excluded:{equipment_id}")
            elif equipment_id == "equipment:42103":
                exclusions.append("equipment:42103:kill_level_growth_excluded_in_fixed_dummy")
            elif equipment_id == "equipment:643803":
                exclusions.append("equipment:643803:shield_300_excluded_outside_survivability_event_model")
            for attribute in profile.static_attributes:
                target = {
                    "physical_attack_flat": "physical_attack",
                    "physical_attack_percent": "physical_attack_percent",
                    "magical_attack_flat": "magical_attack",
                    "physical_defense_flat": "physical_defense",
                    "magical_defense_flat": "magical_defense",
                    "attack_speed_percent": "attack_speed_percent",
                    "max_health_percent": "max_health_percent",
                    "max_energy_flat": "max_energy_flat",
                    "initial_energy_flat": "initial_energy_flat",
                    "magical_attack_percent": "magical_attack_percent",
                    "critical_rate_percent": "critical_rate_percent",
                    "critical_effect_percent": "critical_effect_percent",
                }[attribute.axis]
                totals[target] += attribute.amount
                contributions.append(EquipmentContribution(
                    equipment_id,
                    attribute.axis,
                    attribute.amount,
                    attribute.evidence_id,
                    f"{target}+=static_attribute",
                    fixed_dummy_equipment_support(equipment_id) is None
                    or fixed_dummy_equipment_support(equipment_id)[0] == "supported_static_only",
                ))
            evidence_id = f"official-raw:{equipment_id}:desc"
            if equipment_id == "equipment:643403":
                totals["initial_energy_flat"] += 15.0
                contributions.append(EquipmentContribution(equipment_id, "initial_energy_flat", 15.0, evidence_id, "initial_mana+=15", False))
            elif equipment_id == "equipment:643603":
                for axis, target in (("physical_defense_flat", "physical_defense"), ("magical_defense_flat", "magical_defense")):
                    totals[target] += 20.0
                    contributions.append(EquipmentContribution(equipment_id, axis, 20.0, evidence_id, f"{target}+=20;fixed_single_hero_wearer", False))
            elif equipment_id == "equipment:641010":
                totals["critical_rate_percent"] += 20.0
                contributions.append(EquipmentContribution(
                    equipment_id,
                    "critical_rate_percent",
                    20.0,
                    evidence_id,
                    "critical_rate_percent+=20;fixed_dummy_received_hit_stack_proxy",
                    False,
                ))
            elif equipment_id == "equipment:643702":
                totals["physical_attack_percent"] += 15.0
                totals["physical_defense"] += 10.0
                contributions.extend((
                    EquipmentContribution(equipment_id, "physical_attack_percent", 15.0, evidence_id, "base_physical_attack_percent+=15;one_adjacent_enemy_fixture", False),
                    EquipmentContribution(equipment_id, "physical_defense_flat", 10.0, evidence_id, "physical_defense+=10;one_adjacent_enemy_fixture", False),
                ))
        return totals, tuple(contributions), tuple(exclusions)

    def _simulate(
        self,
        fixture,
        physical,
        magical,
        max_health,
        attack_speed,
        attack_speed_during_skill,
        mana,
        maximum_mana,
        active_hits,
        active_assumptions,
        evidence_ids,
        basic_attack_bonus_hits,
        basic_attack_bonus_assumptions,
        combat_modifiers,
        hero,
        fixture_level,
        sun_chaser_is_ranged,
        critical_rate,
        critical_effect,
        critical_source_id,
        critical_evidence_ids,
        rule_pack,
        target_equipment_effects,
    ):
        equipment_ids = set(fixture.equipment_instance_ids)
        target_equipment_ids = {effect.equipment_id for effect in target_equipment_effects}
        magic_law_repeat_probability = (
            min(1.0, (35.0 + math.floor(fixture_level / 7.0)) / 100.0)
            if "equipment:643705" in equipment_ids
            else 0.0
        )
        events: list[FixedDummyDamageEvent] = []
        hp = fixture.dummy_hp
        cumulative = 0.0
        current_magical = magical
        hero_id = str(hero.get("id") or "")
        erin_blessing_stacks = 0
        sage_stacks = 0
        buff_until = float("inf") if combat_modifiers.transformed_from_start else -1.0
        physical_buff_until = -1.0
        transformed_until = float("inf") if combat_modifiers.transformed_from_start else -1.0
        transformed_basic_sequence = 0
        daybreak_expiries: list[float] = []
        daybreak_zero_triggered = False
        frost_stack_hit_times: list[float] = []
        frost_amp_start = -1.0
        frost_amp_until = -1.0
        frost_cooldown_until = -1.0
        target_attack_speed_slow_until = -1.0
        pain_mask_until = -1.0
        pain_mask_ticks: list[tuple[float, float]] = []
        pending_skill_hits: list[_PendingSkillHit] = []
        skill_queue_sequence = 0
        event_sequence = 0
        basic_sequence = 0
        cast_sequence = 0
        coverage_gate_exclusions: set[str] = set()

        def next_event_id(kind: str) -> str:
            nonlocal event_sequence
            event_sequence += 1
            return f"fixed-dummy:{event_sequence:06d}:{kind}"

        def damage_multiplier_at(time: float) -> tuple[float, tuple[str, ...]]:
            multiplier = 1.0 + combat_modifiers.damage_amplification_percent / 100.0
            assumptions: tuple[str, ...] = ()
            if frost_amp_start + 1e-9 < time < frost_amp_until - 1e-9:
                multiplier *= 1.2
                assumptions = ("frost_invasion_five_stack_damage_window",)
            if combat_modifiers.damage_amplification_percent:
                assumptions += ("red_demon_no_adjacent_ally_fixture_amplification",)
            return multiplier, assumptions

        def target_damage_multiplier_at(
            time: float,
            event_type: str,
            source_attack_speed: float | None,
        ) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
            multiplier = 1.0
            assumptions: list[str] = []
            target_evidence: list[str] = []
            if (
                "equipment:643601" in target_equipment_ids
                and time < 15.0 - 1e-9
                and (
                    event_type in {"basic_attack", "equipment_rapid_basic_attack"}
                    or hero_id == "5371" and event_type == "passive_basic_attack_magical_damage"
                    or hero_id == "1771" and event_type == "passive_basic_attack_physical_damage"
                )
            ):
                reduction = 0.70 if (source_attack_speed or 0.0) > 1.5 else 0.50
                multiplier *= 1.0 - reduction
                assumptions.extend((
                    "target_equipment:643601:ordinary_attack_reduction",
                    f"target_equipment:643601:reduction_percent:{reduction * 100:g}",
                    "target_equipment:643601:first_fifteen_seconds",
                ))
                target_evidence.append("official-raw:equipment:643601:desc")
            if "equipment:643501" in target_equipment_ids and hp > fixture.dummy_hp * 0.70 + 1e-9:
                multiplier *= 0.60
                assumptions.extend((
                    "target_equipment:643501:above_70_percent_damage_reduction",
                    "target_equipment:643501:damage_reduction_percent:40",
                ))
                target_evidence.append("official-raw:equipment:643501:desc")
            return multiplier, tuple(assumptions), tuple(target_evidence)

        def append_damage(
            time: float,
            kind: str,
            event_type: str,
            raw: float,
            damage_type: str,
            mana_before: int,
            mana_after: int,
            event_evidence: tuple[str, ...],
            assumptions: tuple[str, ...] = (),
            source_id: str = "fixture:hero",
            allow_equipment_damage_triggers: bool = True,
            event_semantics: str = "deterministic",
            rule_id: str | None = None,
            phase: str | None = None,
            priority: int | None = None,
            caused_by_event_id: str | None = None,
            coverage_tier: str | None = None,
            source_attack_speed: float | None = None,
        ) -> FixedDummyDamageEvent | None:
            nonlocal hp, cumulative, pain_mask_until, pain_mask_ticks
            if rule_id is None:
                rule = (
                    rule_pack.rule("fixed-dummy:basic-attack:v1")
                    if event_type == "basic_attack"
                    else rule_pack.rule("fixed-dummy:active-direct:v1")
                    if event_type == "parsed_active_skill_damage"
                    else rule_pack.rule("fixed-dummy:equipment-on-hit:v1")
                    if event_type.startswith(("equipment_", "passive_basic_"))
                    else rule_pack.rule("fixed-dummy:active-direct:v1")
                )
                rule_id, phase, priority, coverage_tier = (
                    rule.rule_id,
                    rule.phase,
                    rule.priority,
                    rule.coverage_tier,
                )
            if fixture.coverage_mode == "strict" and coverage_tier != "strict":
                coverage_gate_exclusions.add(f"coverage_mode_excludes:{rule_id}")
                return None
            daybreak_expiries[:] = [expiry for expiry in daybreak_expiries if expiry > time + 1e-9]
            resistance_override = None
            if damage_type == "physical":
                resistance_override = max(0.0, fixture.dummy_physical_defense - 3.0 * len(daybreak_expiries))
            elif damage_type == "magical":
                resistance_override = max(0.0, fixture.dummy_magical_defense - combat_modifiers.magical_penetration)
            multiplier, multiplier_assumptions = damage_multiplier_at(time)
            target_multiplier, target_assumptions, target_evidence = target_damage_multiplier_at(
                time,
                event_type,
                source_attack_speed,
            )
            hp, cumulative, event = _apply_event(
                time,
                next_event_id(kind),
                event_type,
                raw,
                damage_type,
                fixture,
                hp,
                cumulative,
                mana_before,
                mana_after,
                event_evidence + target_evidence,
                assumptions + multiplier_assumptions + target_assumptions,
                source_id=source_id,
                resistance_override=resistance_override,
                damage_multiplier=multiplier * target_multiplier,
                event_semantics=event_semantics,
                rule_id=rule_id,
                phase=phase or "damage",
                priority=priority if priority is not None else 0,
                caused_by_event_id=caused_by_event_id,
                coverage_tier=coverage_tier or "strict",
            )
            events.append(event)
            if (
                allow_equipment_damage_triggers
                and
                "equipment:643401" in equipment_ids
                and damage_type == "magical"
                and event.applied_value > fixture.dummy_hp * 0.08
                and time >= pain_mask_until - 1e-9
                and hp > 0
            ):
                pain_mask_until = time + 3.0
                burn_raw = 0.75 * current_magical
                pain_mask_ticks.extend((time + offset, burn_raw) for offset in (1.0, 2.0, 3.0))
            return event

        critical_expected_bonus_factor = (critical_rate / 100.0) * max(0.0, critical_effect / 100.0 - 1.0)

        def append_expected_critical_bonus(
            time: float,
            eligible_raw: float,
            mana_value: int,
            receipt_key: str,
            base_assumptions: tuple[str, ...] = (),
            caused_by_event_id: str | None = None,
        ) -> None:
            if critical_expected_bonus_factor <= 0 or hp <= 0:
                return
            rule = rule_pack.rule("fixed-dummy:expected-critical:v1")
            append_damage(
                time,
                f"critical:{receipt_key}",
                "equipment_expected_critical_physical_damage",
                eligible_raw * critical_expected_bonus_factor,
                "physical",
                mana_value,
                mana_value,
                critical_evidence_ids,
                base_assumptions + (
                    "deterministic_expected_critical_value_no_rng",
                    "only_physical_basic_attack_damage_is_crit_eligible",
                    f"critical_rate_percent:{critical_rate:g}",
                    f"critical_effect_total_percent:{critical_effect:g}",
                    "expected_bonus=eligible_raw*critical_rate*(critical_multiplier-1)",
                    "not_an_observed_random_critical_hit",
                ),
                source_id=critical_source_id,
                allow_equipment_damage_triggers=False,
                event_semantics="expected_value_increment",
                rule_id=rule.rule_id,
                phase=rule.phase,
                priority=rule.priority,
                caused_by_event_id=caused_by_event_id,
                coverage_tier=rule.coverage_tier,
            )

        def append_expected_skill_repeat(
            time: float,
            eligible_raw: float,
            damage_type: str,
            mana_value: int,
            receipt_key: str,
            base_assumptions: tuple[str, ...] = (),
            caused_by_event_id: str | None = None,
        ) -> None:
            if magic_law_repeat_probability <= 0 or hp <= 0:
                return
            probability_percent = magic_law_repeat_probability * 100.0
            rule = rule_pack.rule("fixed-dummy:expected-repeat:v1")
            append_damage(
                time,
                f"magic-law:{receipt_key}",
                "equipment_expected_repeat_active_skill_damage",
                eligible_raw * magic_law_repeat_probability,
                damage_type,
                mana_value,
                mana_value,
                ("official-raw:equipment:643705:desc",),
                base_assumptions + (
                    "magic_law_repeat_cast_uses_level_probability_expected_value",
                    f"magic_law_repeat_probability_percent:{probability_percent:g}",
                    "expected_repeat_damage=original_skill_damage*repeat_probability",
                    "expected_repeat_does_not_retrigger_cast_or_equipment_state",
                    "not_an_observed_random_repeat_cast",
                ),
                source_id="equipment:643705",
                allow_equipment_damage_triggers=False,
                event_semantics="expected_value_increment",
                rule_id=rule.rule_id,
                phase=rule.phase,
                priority=rule.priority,
                caused_by_event_id=caused_by_event_id,
                coverage_tier=rule.coverage_tier,
            )

        def runtime_active_hits() -> tuple[tuple[tuple[float, str], ...], tuple[str, ...]]:
            formulas = _active_skill_formulas(hero, physical, current_magical)
            direct = tuple(item for item in formulas if item.raw_damage_per_cast is not None and not _mechanism_managed(item.active_text))
            direct = _apply_unlocked_active_skill_enhancements(hero, fixture_level, direct, physical, current_magical)
            if len(direct) == 1 and len(direct[0].components) == 1:
                component = direct[0].components[0]
                nodes, selected, _ = _skill_node_values(
                    hero,
                    fixture_level,
                    physical,
                    current_magical,
                    component.hit_count,
                    component.raw_damage(physical, current_magical) / max(1, component.hit_count),
                    component.damage_type,
                    evidence_ids,
                )
                if selected is not None:
                    direct = (_formula_from_skill_node(selected, direct[0], physical, current_magical),)
            hits = tuple(
                (component.raw_damage(physical, current_magical) / max(1, component.hit_count), component.damage_type)
                for formula in direct
                for component in formula.components
                for _ in range(max(1, component.hit_count))
            )
            if any(damage_type not in {"physical", "magical", "true"} for _, damage_type in hits):
                hits = ()
            assumptions = tuple(dict.fromkeys(assumption for formula in direct for assumption in formula.assumptions))
            return hits, assumptions

        def runtime_mechanism_schedules() -> tuple[FixedDummySkillMechanismSchedule, ...]:
            return _skill_mechanism_schedules(
                hero,
                fixture_level,
                physical,
                current_magical,
                fixture.dummy_hp,
                fixture.horizon_seconds,
                evidence_ids,
                attack_speed,
                rule_pack,
            )

        def enqueue_schedule(
            time: float,
            schedule: FixedDummySkillMechanismSchedule,
            caused_by_event_id: str | None = None,
        ) -> None:
            nonlocal skill_queue_sequence
            if (
                not schedule.included_in_damage_timeline
                or schedule.damage_type not in {"physical", "magical", "true"}
                or schedule.raw_value_per_hit is None
                or schedule.start_offset_seconds is None
            ):
                return
            if fixture.coverage_mode == "strict" and schedule.coverage_tier != "strict":
                coverage_gate_exclusions.add(f"coverage_mode_excludes:{schedule.rule_id}")
                return
            skill_queue_sequence += 1
            for hit_index in range(1, schedule.hit_count + 1):
                offset = schedule.start_offset_seconds
                if schedule.interval_seconds is not None:
                    offset += ((hit_index - 1) // max(1, schedule.hits_per_tick)) * schedule.interval_seconds
                pending_skill_hits.append(_PendingSkillHit(
                    time + offset,
                    skill_queue_sequence,
                    schedule.schedule_id,
                    schedule.event_type,
                    schedule.damage_type,
                    schedule.raw_value_per_hit,
                    hit_index,
                    schedule.hit_count,
                    schedule.evidence_ids,
                    schedule.assumptions + (
                        f"mechanism_schedule_status:{schedule.status}",
                        f"mechanism_hit_index:{hit_index}",
                        f"mechanism_hit_count:{schedule.hit_count}",
                        f"target_repeat_policy:{schedule.target_repeat_policy}",
                    ),
                    schedule.target_repeat_policy,
                    schedule.rule_id,
                    schedule.phase,
                    schedule.priority,
                    caused_by_event_id,
                    schedule.coverage_tier,
                ))

        def cast_if_ready(
            time: float,
            trigger: str,
            caused_by_event_id: str | None = None,
        ) -> None:
            nonlocal mana, sage_stacks, current_magical, buff_until, physical_buff_until, transformed_until, hp, cast_sequence
            hits, assumptions = runtime_active_hits()
            schedules = tuple(
                item for item in runtime_mechanism_schedules()
                if item.trigger == "active_cast" and item.included_in_damage_timeline
            )
            if not (
                maximum_mana > 0
                and mana >= maximum_mana
                and (
                    hits
                    or schedules
                    or combat_modifiers.cast_attack_speed_percent > 0
                    or combat_modifiers.cast_attack_speed_base_delta > 0
                    or combat_modifiers.cast_physical_attack_percent > 0
                    or combat_modifiers.cast_transformed_seconds > 0
                    or combat_modifiers.cast_transformation_persists_to_horizon
                )
            ):
                return
            cast_sequence += 1
            hit_count = len(hits)
            equipment_cast_assumptions = (
                (("source_cup_mana_regeneration_applied_each_second",) if trigger == "source-cup" else ())
                + (("skill_damage_recomputed_from_dynamic_magical_attack",) if abs(current_magical - magical) > 1e-9 else ())
                + (("sage_book_current_cast_uses_pre_stack_magical_attack",) if "equipment:643802" in equipment_ids else ())
            )
            direct_rule = rule_pack.rule("fixed-dummy:active-direct:v1")
            first_cast_event_id = caused_by_event_id
            for hit_index, (raw, damage_type) in enumerate(hits, start=1):
                cast_event = append_damage(
                    time,
                    f"cast:{trigger}:hit:{hit_index:03d}",
                    "parsed_active_skill_damage",
                    raw,
                    damage_type,
                    mana if hit_index == 1 else 0,
                    0,
                    evidence_ids,
                    assumptions + equipment_cast_assumptions + (
                        "cast_start_proxy",
                        f"active_hit_index:{hit_index}",
                        f"active_hit_count:{hit_count}",
                    ),
                    rule_id=direct_rule.rule_id,
                    phase=direct_rule.phase,
                    priority=direct_rule.priority,
                    caused_by_event_id=caused_by_event_id,
                    coverage_tier=direct_rule.coverage_tier,
                )
                if first_cast_event_id is None and cast_event is not None:
                    first_cast_event_id = cast_event.event_id
                if hp <= 0:
                    break
                append_expected_skill_repeat(
                    time,
                    raw,
                    damage_type,
                    0,
                    f"cast:{trigger}:hit:{hit_index:03d}",
                    assumptions + equipment_cast_assumptions + (
                        "cast_start_proxy",
                        f"active_hit_index:{hit_index}",
                        f"active_hit_count:{hit_count}",
                    ),
                    caused_by_event_id=cast_event.event_id if cast_event is not None else caused_by_event_id,
                )
                if hp <= 0:
                    break
            if hp > 0:
                for schedule in schedules:
                    if cast_sequence % schedule.cast_every == 0:
                        enqueue_schedule(time, schedule, first_cast_event_id)
            mana = 0
            if combat_modifiers.cast_attack_speed_percent > 0 or combat_modifiers.cast_attack_speed_base_delta > 0:
                buff_until = max(buff_until, time + combat_modifiers.cast_buff_seconds)
            if combat_modifiers.cast_physical_attack_percent > 0:
                physical_buff_until = max(physical_buff_until, time + combat_modifiers.cast_physical_attack_seconds)
            if combat_modifiers.cast_transformation_persists_to_horizon:
                transformed_until = fixture.horizon_seconds + 1e-9
            elif combat_modifiers.cast_transformed_seconds > 0:
                transformed_until = max(
                    transformed_until,
                    time + combat_modifiers.cast_transformed_seconds,
                )
            if "equipment:643802" in equipment_ids and sage_stacks < 6:
                sage_stacks += 1
                current_magical += magical * 0.20

        def basic_attack(time: float, event_type: str, source_id: str, action_attack_speed: float) -> None:
            nonlocal mana, basic_sequence, daybreak_zero_triggered, current_magical, erin_blessing_stacks
            nonlocal transformed_basic_sequence
            nonlocal skill_queue_sequence
            nonlocal frost_amp_start, frost_amp_until, frost_cooldown_until, hp
            nonlocal target_attack_speed_slow_until
            basic_sequence += 1
            before = mana
            is_transformed = (
                combat_modifiers.transformed_from_start
                or time < transformed_until
                or time < buff_until
            )
            if is_transformed:
                transformed_basic_sequence += 1
            transformed_mana_gain = (
                0
                if is_transformed and combat_modifiers.transformed_basic_mana_regeneration_disabled
                else 5 + (combat_modifiers.transformed_basic_mana_restore if is_transformed else 0)
            )
            after = min(
                maximum_mana,
                mana + transformed_mana_gain,
            )
            is_dasim = hero_id == "5171"
            is_cang_double_attack = hero_id == "1771" and is_transformed
            current_physical = physical * (1.0 + combat_modifiers.cast_physical_attack_percent / 100.0) if time < physical_buff_until else physical
            physical_buff_assumptions = ("caocao_cast_base_physical_attack_buff_active",) if time < physical_buff_until else ()
            critical_eligible_raw = current_physical
            critical_base_assumptions: tuple[str, ...] = ()
            action_event: FixedDummyDamageEvent | None = None
            if is_dasim:
                link_schedule = next(
                    (
                        item for item in runtime_mechanism_schedules()
                        if item.trigger == "basic_attack" and item.event_type == "passive_basic_attack_link_damage"
                    ),
                    None,
                )
                link_raw = 0.50 * current_physical
                critical_eligible_raw = link_raw
                link_assumptions = (
                    "five_link_hits_are_one_basic_attack_action",
                    "basic_attack_equipment_effects_trigger_once_at_full_value",
                    "three_second_connection_cycle_compressed_by_attack_speed",
                    "uniform_within_cycle_timing_proxy",
                    f"target_repeat_policy:{link_schedule.target_repeat_policy if link_schedule else 'five_link_hits_repeat_same_target'}",
                    "cast_start_proxy",
                )
                critical_base_assumptions = link_assumptions + ("mechanism_hit_index:1", "mechanism_hit_count:5")
                link_rule = (
                    link_schedule
                    if link_schedule is not None
                    else rule_pack.rule("fixed-dummy:basic-attack:v1")
                )
                action_event = append_damage(
                    time,
                    f"attack:{basic_sequence:04d}:link:1",
                    "passive_basic_attack_link_damage",
                    link_raw,
                    "physical",
                    before,
                    after,
                    evidence_ids,
                    link_assumptions + ("mechanism_hit_index:1", "mechanism_hit_count:5"),
                    source_id=source_id,
                    rule_id=link_rule.rule_id,
                    phase=link_rule.phase,
                    priority=link_rule.priority,
                    coverage_tier=link_rule.coverage_tier,
                    source_attack_speed=action_attack_speed,
                )
                if hp > 0:
                    skill_queue_sequence += 1
                    connection_cycle = 3.0 / max(action_attack_speed, 1e-9)
                    link_interval = connection_cycle / 5.0
                    target_policy = link_schedule.target_repeat_policy if link_schedule else "five_link_hits_repeat_same_target"
                    for hit_index in range(2, 6):
                        pending_skill_hits.append(_PendingSkillHit(
                            time + (hit_index - 1) * link_interval,
                            skill_queue_sequence,
                            "hero:5171:spirit_link",
                            "passive_basic_attack_link_damage",
                            "physical",
                            link_raw,
                            hit_index,
                            5,
                            evidence_ids,
                            link_assumptions + (f"mechanism_hit_index:{hit_index}", "mechanism_hit_count:5"),
                            target_policy,
                            link_rule.rule_id,
                            link_rule.phase,
                            link_rule.priority,
                            action_event.event_id if action_event is not None else None,
                            link_rule.coverage_tier,
                        ))
            else:
                sikongzhen_lightning_chain = hero_id == "5371" and fixture_level >= 40 and is_transformed
                basic_evidence = (
                    evidence_ids + (SIKONGZHEN_LIGHTNING_CHAIN_RULE.rule_id,)
                    if sikongzhen_lightning_chain
                    else evidence_ids
                )
                basic_assumptions = physical_buff_assumptions + (
                    ("sikongzhen_physical_basic_attack_with_additional_lightning_chain",)
                    if sikongzhen_lightning_chain
                    else ()
                ) + (
                    ("cang_transformed_double_basic_attack", "cang_first_shot_is_sixty_percent_physical_attack")
                    if is_cang_double_attack
                    else ()
                )
                action_event = append_damage(
                    time,
                    f"attack:{basic_sequence:04d}",
                    event_type,
                    0.60 * current_physical if is_cang_double_attack else current_physical,
                    "physical",
                    before,
                    after,
                    basic_evidence,
                    basic_assumptions,
                    source_id=source_id,
                    source_attack_speed=action_attack_speed,
                )
            mana = after
            if hp <= 0:
                return
            if "equipment:643602" in target_equipment_ids and action_event is not None:
                target_attack_speed_slow_until = max(target_attack_speed_slow_until, time + 2.0)
                updated_event = replace(
                    action_event,
                    assumptions=action_event.assumptions + (
                        "target_equipment:643602:attack_speed_reduction_after_basic_attack",
                        "target_equipment:643602:attack_speed_reduction_percent:20",
                        "target_equipment:643602:duration_seconds:2",
                    ),
                    evidence_ids=tuple(dict.fromkeys(
                        action_event.evidence_ids + ("official-raw:equipment:643602:desc",)
                    )),
                )
                events[-1] = updated_event
                action_event = updated_event
            if action_event is not None and action_event.damage_type == "physical" and not is_cang_double_attack:
                append_expected_critical_bonus(
                    time,
                    critical_eligible_raw,
                    mana,
                    f"attack:{basic_sequence:04d}",
                    critical_base_assumptions,
                    action_event.event_id,
                )
            if hp <= 0:
                return

            if hero_id == "5371" and fixture_level >= 40 and is_transformed:
                append_damage(
                    time,
                    f"attack:{basic_sequence:04d}:lightning-chain",
                    "passive_basic_attack_magical_damage",
                    75.0 + 0.50 * current_magical,
                    "magical",
                    mana,
                    mana,
                    evidence_ids + (SIKONGZHEN_LIGHTNING_CHAIN_RULE.rule_id,),
                    ("sikongzhen_physical_basic_attack_with_additional_lightning_chain",
                     "sikongzhen_lightning_chain_primary_target_only"),
                    caused_by_event_id=action_event.event_id if action_event is not None else None,
                    source_attack_speed=action_attack_speed,
                )
                if hp <= 0:
                    return

            if is_cang_double_attack:
                append_damage(
                    time,
                    f"attack:{basic_sequence:04d}:second",
                    "passive_basic_attack_physical_damage",
                    0.80 * current_physical,
                    "physical",
                    mana,
                    mana,
                    evidence_ids,
                    physical_buff_assumptions + (
                        "cang_transformed_double_basic_attack",
                        "cang_second_shot_is_eighty_percent_physical_attack",
                        "target_repeat_policy:one_fixed_target",
                    ),
                    source_id=source_id,
                    source_attack_speed=action_attack_speed,
                )
                if hp <= 0:
                    return

            if hero_id == "3551":
                erin_blessing_stacks += 1
                if fixture_level >= 40 and erin_blessing_stacks >= 30:
                    current_magical += 2.0
                    append_damage(
                        time,
                        f"erin-blessing:{basic_sequence:04d}",
                        "passive_basic_attack_magical_damage",
                        0.10 * current_magical,
                        "magical",
                        mana,
                        mana,
                        evidence_ids,
                        (
                            "one_blessing_stack_per_scheduled_basic_attack",
                            "level_40_on_hit_activates_at_thirty_blessing_stacks",
                            "magical_attack_gain_applies_before_current_on_hit_damage",
                            f"erin_blessing_stacks:{erin_blessing_stacks}",
                            "target_repeat_policy:one_on_hit_per_basic_attack_action",
                        ),
                        source_id=source_id,
                    )
                    if hp <= 0:
                        return

            if "equipment:643302" in equipment_ids:
                previous_defense = max(0.0, fixture.dummy_physical_defense - 3.0 * len(daybreak_expiries))
                daybreak_expiries.append(time + 5.0)
                current_defense = max(0.0, fixture.dummy_physical_defense - 3.0 * len(daybreak_expiries))
            else:
                previous_defense = current_defense = fixture.dummy_physical_defense

            if "equipment:643205" in equipment_ids:
                # The card only declares a five-second stack duration.  Requiring
                # all five same-target hits inside that window is sufficient under
                # either independent-stack or refresh-on-hit interpretations.
                frost_stack_hit_times[:] = [
                    hit_time
                    for hit_time in frost_stack_hit_times
                    if time - hit_time < 5.0 - 1e-9
                ]
                frost_stack_hit_times.append(time)
                if len(frost_stack_hit_times) >= 5 and time >= frost_cooldown_until - 1e-9:
                    frost_amp_start = time
                    frost_amp_until = time + 5.0
                    frost_cooldown_until = time + 10.0
                    frost_stack_hit_times.clear()

            if (
                "equipment:643302" in equipment_ids
                and not daybreak_zero_triggered
                and previous_defense > 0
                and current_defense <= 0
            ):
                daybreak_zero_triggered = True
                append_damage(
                    time,
                    "daybreak-zero",
                    "equipment_dawn_zero_defense_physical_damage",
                    fixture.dummy_hp * 0.15,
                    "physical",
                    mana,
                    mana,
                    ("official-raw:equipment:643302:desc",),
                    ("first_zero_physical_defense_crossing_only",),
                    source_id="equipment:643302",
                )
            if hp <= 0:
                return

            for bonus_index, (bonus_raw, bonus_type) in enumerate(basic_attack_bonus_hits, start=1):
                append_damage(time, f"passive:{basic_sequence}:{bonus_index}", "passive_basic_attack_true_damage", bonus_raw, bonus_type, mana, mana, evidence_ids, basic_attack_bonus_assumptions)
                if hp <= 0:
                    return

            bonuses = list(combat_modifiers.always_basic_attack_bonuses)
            if is_transformed:
                bonuses.extend(
                    bonus
                    for bonus in combat_modifiers.transformed_basic_attack_bonuses
                    if transformed_basic_sequence % bonus.every_nth_transformed_basic_attack == 0
                )
            for bonus_index, bonus in enumerate(bonuses, start=1):
                raw = (
                    20.0 + 0.30 * current_magical
                    if bonus.source_id == _GOLDEN_STAFF_ID
                    else 100.0 + 0.50 * current_magical
                    if hero_id == "5371" and bonus.event_type == "passive_basic_attack_magical_damage"
                    else 0.50 * current_magical
                    if hero_id == "1591" and bonus.event_type == "passive_basic_attack_magical_damage"
                    else physical
                    if hero_id == "1931" and bonus.event_type == "passive_basic_attack_magical_damage"
                    else bonus.raw_value
                )
                append_damage(time, f"bonus:{basic_sequence}:{bonus_index}", bonus.event_type, raw, bonus.damage_type, mana, mana, bonus.evidence_ids, bonus.assumptions, source_id=bonus.source_id)
                if hp <= 0:
                    return
            if "equipment:641015" in equipment_ids and sun_chaser_is_ranged:
                append_damage(
                    time,
                    f"sun-chaser:{basic_sequence}",
                    "equipment_ranged_arrow_physical_damage",
                    physical * 0.45,
                    "physical",
                    mana,
                    mana,
                    ("official-raw:equipment:641015:desc",),
                    ("single_lowest_health_target_is_fixed_dummy", "ranged_wearer_confirmed"),
                    source_id="equipment:641015",
                )
            if hp > 0:
                cast_if_ready(
                    time,
                    f"attack:{basic_sequence}",
                    action_event.event_id if action_event is not None else None,
                )

        if combat_modifiers.battle_start_cast and (
            active_hits
            or combat_modifiers.cast_attack_speed_percent > 0
            or combat_modifiers.cast_attack_speed_base_delta > 0
            or combat_modifiers.cast_transformed_seconds > 0
            or combat_modifiers.cast_transformation_persists_to_horizon
        ):
            saved_mana = mana
            mana = maximum_mana
            cast_if_ready(0.0, "battle-start")
            mana = min(saved_mana, maximum_mana)
            if hp <= 0:
                return events, current_magical, coverage_gate_exclusions

        for schedule in runtime_mechanism_schedules():
            if schedule.trigger == "battle_start" and schedule.included_in_damage_timeline:
                enqueue_schedule(0.0, schedule)

        next_attack_time = 1.0 / attack_speed
        next_source_tick = 1.0 if "equipment:643402" in equipment_ids else float("inf")
        next_sky_tick = 2.0 if "equipment:643105" in equipment_ids else float("inf")
        next_lotus_tick = 2.0 if "equipment:643504" in equipment_ids else float("inf")
        next_rapid_time = 0.0 if "equipment:643304" in equipment_ids else float("inf")

        while hp > 0:
            next_burn_time = min((item[0] for item in pain_mask_ticks), default=float("inf"))
            next_skill_time = min((item.time for item in pending_skill_hits), default=float("inf"))
            time = min(
                next_attack_time,
                next_source_tick,
                next_sky_tick,
                next_lotus_tick,
                next_rapid_time,
                next_burn_time,
                next_skill_time,
            )
            if time > fixture.horizon_seconds + 1e-9:
                break

            if abs(time - next_sky_tick) <= 1e-9:
                current_magical += 10.0
                next_sky_tick += 2.0
            if abs(time - next_source_tick) <= 1e-9:
                regeneration_disabled = (
                    combat_modifiers.transformed_basic_mana_regeneration_disabled
                    and (combat_modifiers.transformed_from_start or time < transformed_until)
                )
                if not regeneration_disabled:
                    mana = min(maximum_mana, mana + 5)
                next_source_tick += 1.0
                cast_if_ready(time, "source-cup")
            if hp <= 0:
                break
            if abs(time - next_lotus_tick) <= 1e-9:
                scheduled_event = append_damage(
                    time,
                    "red-lotus",
                    "equipment_red_lotus_magical_damage",
                    20.0 + 0.05 * max_health,
                    "magical",
                    mana,
                    mana,
                    ("official-raw:equipment:643504:desc",),
                    ("adjacent_fixed_dummy_proxy",),
                    source_id="equipment:643504",
                )
                next_lotus_tick += 2.0
            if hp <= 0:
                break
            if abs(time - next_attack_time) <= 1e-9:
                base_attack_speed = attack_speed_during_skill if time < buff_until else attack_speed
                action_attack_speed = base_attack_speed * (0.80 if time < target_attack_speed_slow_until - 1e-9 else 1.0)
                basic_attack(
                    time,
                    "basic_attack",
                    "fixture:hero",
                    action_attack_speed,
                )
                next_base_attack_speed = attack_speed_during_skill if time < buff_until else attack_speed
                current_attack_speed = next_base_attack_speed * (0.80 if time < target_attack_speed_slow_until - 1e-9 else 1.0)
                next_attack_time = time + (3.0 if hero_id == "5171" else 1.0) / current_attack_speed
            if hp <= 0:
                break
            if abs(time - next_rapid_time) <= 1e-9:
                for _ in range(4):
                    basic_attack(time, "equipment_rapid_basic_attack", "equipment:643304", attack_speed)
                    if hp <= 0:
                        break
                next_rapid_time += 8.0
            if hp <= 0:
                break
            due_burns = [item for item in pain_mask_ticks if abs(item[0] - time) <= 1e-9]
            pain_mask_ticks[:] = [item for item in pain_mask_ticks if abs(item[0] - time) > 1e-9]
            for _, raw in due_burns:
                append_damage(
                    time,
                    "pain-mask",
                    "equipment_pain_mask_true_damage",
                    raw,
                    "true",
                    mana,
                    mana,
                    ("official-raw:equipment:643401:desc",),
                    ("one_true_damage_tick_per_second_for_three_seconds",),
                    source_id="equipment:643401",
                )
                if hp <= 0:
                    break
            if hp <= 0:
                break
            due_skill_hits = sorted(
                (item for item in pending_skill_hits if abs(item.time - time) <= 1e-9),
                key=lambda item: (item.queue_sequence, item.hit_index, item.schedule_id),
            )
            pending_skill_hits[:] = [
                item for item in pending_skill_hits if abs(item.time - time) > 1e-9
            ]
            for hit in due_skill_hits:
                scheduled_event = append_damage(
                    time,
                    f"mechanism:{hit.queue_sequence}:{hit.schedule_id}:hit:{hit.hit_index}",
                    hit.event_type,
                    hit.raw_value,
                    hit.damage_type,
                    mana,
                    mana,
                    hit.evidence_ids,
                    hit.assumptions,
                    rule_id=hit.rule_id,
                    phase=hit.phase,
                    priority=hit.priority,
                    caused_by_event_id=hit.caused_by_event_id,
                    coverage_tier=hit.coverage_tier,
                )
                if hp <= 0:
                    break
                if hit.event_type.startswith("active_skill_"):
                    append_expected_skill_repeat(
                        time,
                        hit.raw_value,
                        hit.damage_type,
                        mana,
                        f"mechanism:{hit.queue_sequence}:{hit.schedule_id}:hit:{hit.hit_index}",
                        hit.assumptions,
                        scheduled_event.event_id if scheduled_event is not None else hit.caused_by_event_id,
                    )
                    if hp <= 0:
                        break
                if hit.event_type == "passive_basic_attack_link_damage":
                    append_expected_critical_bonus(
                        time,
                        hit.raw_value,
                        mana,
                        f"mechanism:{hit.queue_sequence}:{hit.schedule_id}:hit:{hit.hit_index}",
                        hit.assumptions,
                        scheduled_event.event_id if scheduled_event is not None else hit.caused_by_event_id,
                    )
                    if hp <= 0:
                        break
        return events, current_magical, coverage_gate_exclusions


def _official_base_properties(properties):
    return (
        ("生命", float(properties.get("HP", 0))),
        ("物攻", float(properties.get("phyAttack", 0))),
        ("法攻", float(properties.get("magAttack", 0))),
        ("物防", float(properties.get("phyDefense", 0))),
        ("法防", float(properties.get("magDefense", 0))),
        ("基础攻速", float(properties.get("attackSpeed", 0)) / 10000.0),
        ("暴击率", float(properties.get("criticalRate", 0)) / 100.0),
    )


def _previous_fixture_level(level: int) -> int:
    return max(item for item in _FIXTURE_LEVEL_PRESETS if item < level) if level > 1 else 1


def _infer_fixture_growth(models, target_base_properties, requested_level):
    target = dict(target_base_properties)
    signature_keys = ("生命", "物防", "法防", "基础攻速")
    candidates = []
    for candidate in models:
        if candidate.status != "model_ready":
            continue
        base = dict(candidate.base_properties)
        if any(abs(float(target.get(key, -1)) - float(base.get(key, -2))) > 1e-9 for key in signature_keys):
            continue
        if (float(target.get("法攻", 0)) > 0) != (float(base.get("法攻", 0)) > 0):
            continue
        candidates.append(candidate)
    templates = {item.template for item in candidates}
    if len(templates) != 1:
        return None
    template = next(iter(templates))
    representative = min(
        candidates,
        key=lambda item: (
            bool(item.special_notes),
            abs(float(dict(item.base_properties).get("物攻", 0)) - float(target.get("物攻", 0))),
            item.hero_id,
        ),
    )
    representative_base = dict(representative.base_properties)
    derived = dict(representative.derive(requested_level).values)
    values = {
        name: float(derived.get(name, 0))
        + float(target.get(name, 0))
        - float(representative_base.get(name, 0))
        for name in derived
    }
    evidence_id = f"model:{representative.model_version}:fixture-template:{template}:{representative.hero_id}"
    return values, template, evidence_id


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value or "")).strip()


def _active_skill_formulas(hero, physical, magical):
    hero_id = str(hero.get("id") or "")
    results = []
    for skill in hero.get("heroCard", {}).get("skillList", ()):
        if not isinstance(skill, dict):
            continue
        text = str(skill.get("desc") or "")
        plain = _plain_text(text)
        if hero_id == "1541" and "轻剑形态下" in plain and "重剑形态下" in plain:
            text = "主动：" + plain.split("轻剑形态下", 1)[1].split("重剑形态下", 1)[0]
        elif hero_id == "5371" and "雷霆之王：" in plain:
            text = "主动：" + plain.split("雷霆之王：", 1)[0]
        elif hero_id == "3551" and "主动：" in plain and "10层进化" in plain:
            text = "主动：" + plain.split("主动：", 1)[1].split("10层进化", 1)[0]
        results.append(parse_active_skill_damage(
            text,
            physical_attack=physical,
            magical_attack=magical,
        ))
    return tuple(results)


def _capped_attack_speed(value: float) -> float:
    return min(_STANDARD_ATTACK_SPEED_CAP, value)


def _combat_modifiers(hero, fixture_level, magical, equipment_ids, awakening_mode):
    hero_id = str(hero.get("id") or "")
    hero_evidence = (f"official-raw:hero:{hero_id}:hero-card",)
    opening_speed = 0.0
    cast_speed = 0.0
    opening_speed_base_delta = 0.0
    cast_speed_base_delta = 0.0
    cast_seconds = 0.0
    cast_transformed_seconds = 0.0
    cast_transformation_persists_to_horizon = False
    transformed_basic_mana_restore = 0
    transformed_basic_mana_regeneration_disabled = False
    battle_start_cast = False
    transformed_from_start = False
    always_bonuses = []
    transformed_bonuses = []
    equipment_contributions = []
    excluded = []
    unresolved = []
    assumptions = []
    damage_amplification = 0.0
    magical_penetration = 0.0

    def equipment_effect(equipment_id, axis, value, formula):
        equipment_contributions.append(EquipmentContribution(
            equipment_id,
            axis,
            value,
            f"official-raw:{equipment_id}:desc",
            formula,
            False,
        ))

    if hero_id == "3551":
        opening_speed += float(fixture_level) * (2.0 if awakening_mode == "awakened" else 1.0)
        assumptions.append(
            "erin_awakened_opening_attack_speed"
            if awakening_mode == "awakened"
            else "erin_normal_opening_attack_speed"
        )
        if fixture_level >= 40:
            assumptions.extend((
                "one_blessing_stack_per_scheduled_basic_attack",
                "level_40_on_hit_activates_at_thirty_blessing_stacks",
                "magical_attack_gain_applies_before_current_on_hit_damage",
            ))
    if hero_id == "1491" and fixture_level >= 10:
        opening_speed += math.floor(magical / 15.0) * 20.0
        assumptions.append("liubang_level_10_battle_start_attack_speed")
    if hero_id == "1281":
        cast_physical_attack_percent = 50.0 if fixture_level >= 10 else 20.0
        cast_physical_attack_seconds = 10.0 if fixture_level >= 40 else 5.0
        assumptions.append("caocao_cast_base_physical_attack_buff_uses_formal_duration")
    else:
        cast_physical_attack_percent = 0.0
        cast_physical_attack_seconds = 0.0
    if hero_id == "1991" and fixture_level >= 10:
        opening_speed += 50.0 if fixture_level >= 40 else 30.0
        assumptions.append("gongsunli_paper_away_attack_speed_persists_in_fixed_dummy_fixture")
    if hero_id == "5021" and fixture_level >= 40:
        opening_speed += 60.0 if fixture_level >= 100 else 30.0
        transformed_from_start = True
        assumptions.append("peiqinhu_battle_start_tiger_attack_speed_fixture")
    if hero_id == "1931" and fixture_level >= 40:
        kai_assumptions = (
            "kai_magic_armor_state_required",
            "kai_every_third_basic_attack_in_magic_armor",
            "kai_magic_armor_duration_not_given_in_formal_card",
            "kai_magic_armor_persists_to_horizon_after_cast_fixture",
        ) + (("kai_battle_start_magic_armor",) if fixture_level >= 100 else ())
        transformed_bonuses.append(_BasicAttackBonus(
            "passive_basic_attack_magical_damage",
            "fixture:hero",
            0.0,
            "magical",
            hero_evidence,
            kai_assumptions,
            every_nth_transformed_basic_attack=3,
        ))
        cast_transformation_persists_to_horizon = True
        assumptions.append("kai_magic_armor_persists_to_horizon_after_cast_fixture")
        unresolved.append("kai_magic_armor_duration_not_given_in_formal_card")
        if fixture_level >= 100:
            battle_start_cast = True
            transformed_from_start = True
            assumptions.append("kai_battle_start_magic_armor")
    if hero_id == "1591":
        transformed_bonuses.append(_BasicAttackBonus(
            "passive_basic_attack_magical_damage",
            "fixture:hero",
            0.5 * magical,
            "magical",
            hero_evidence,
            (
                "dolia_water_state_after_cast",
                "dolia_mermaid_basic_attack_adds_fifty_percent_magical_attack",
                "dolia_water_state_last_ten_seconds",
            ),
        ))
        cast_transformed_seconds = 10.0
        transformed_basic_mana_restore = 5
        assumptions.append("dolia_water_state_last_ten_seconds")
    if hero_id == "1771":
        cast_transformed_seconds = 8.0
        transformed_basic_mana_regeneration_disabled = True
        assumptions.append("cang_transformed_double_basic_attack_last_eight_seconds")
        excluded.extend((
            "cang_wolf_soul_damage_and_attack_gain_not_modeled",
            "cang_wolf_soul_death_condition_for_mana_restore_not_modeled",
            "cang_second_projectile_equipment_on_hit_triggers_unverified",
            "cang_double_attack_critical_rules_unverified",
        ))
        unresolved.append("cang_double_attack_projectile_spacing_not_measured")
    if hero_id == "1331":
        excluded.append("direnjie_swiftness_stacking_attack_speed_not_modeled")
        if fixture_level >= 40:
            excluded.append("direnjie_blue_card_attack_replacement_not_modeled")
        unresolved.append("direnjie_base_attack_speed_bonus_requires_game_measurement")
    if hero_id == "1501":
        excluded.append("hanxin_every_third_attack_replacement_not_modeled")
    if hero_id == "5371" and fixture_level >= 40:
        if fixture_level >= 100:
            opening_speed_base_delta += 0.15
            battle_start_cast = True
            transformed_from_start = True
            assumptions.extend((
                "sikongzhen_transformed_base_attack_speed_delta_user_measured",
            ))
        else:
            cast_speed_base_delta += 0.15
            cast_seconds = max(cast_seconds, 8.0)
        assumptions.append("sikongzhen_physical_basic_attack_with_additional_lightning_chain")
        excluded.append("sikongzhen_lightning_chain_secondary_targets")
    if hero_id == "1541":
        excluded.append("heavy_sword_form_excluded_user_selected_light_sword_fixture")

    if _GOLDEN_STAFF_ID in equipment_ids:
        speed = 30.0 + 0.15 * magical
        opening_speed += speed
        evidence_id = "official-raw:equipment:643207:desc"
        equipment_contributions.append(EquipmentContribution(
            _GOLDEN_STAFF_ID,
            "attack_speed_percent",
            speed,
            evidence_id,
            "attack_speed_percent=30+0.15*magical_attack",
            False,
        ))
        always_bonuses.append(_BasicAttackBonus(
            "equipment_basic_attack_magical_damage",
            _GOLDEN_STAFF_ID,
            20.0 + 0.30 * magical,
            "magical",
            (evidence_id,),
            ("golden_staff_on_hit_applies_to_each_scheduled_basic_attack",),
        ))

    if "equipment:42102" in equipment_ids and hero_id == "1821":
        evidence_id = "official-raw:equipment:42102:desc"
        equipment_contributions.append(EquipmentContribution(
            "equipment:42102",
            "maximum_mana_override",
            10.0,
            evidence_id,
            "maximum_mana=10 when wearer is Ganjiang Moye",
            False,
        ))
        assumptions.append("male_sword_ganjiang_moye_maximum_mana_is_ten")

    if "equipment:643402" in equipment_ids:
        assumptions.append("source_cup_mana_regeneration_applied_each_second")
        equipment_effect("equipment:643402", "mana_per_second", 5.0, "mana+=5 at each elapsed second")
    if "equipment:643802" in equipment_ids:
        assumptions.append("sage_book_stacks_apply_after_cast_damage_max_six")
        equipment_effect("equipment:643802", "base_magical_attack_percent_per_cast", 20.0, "magical_attack+=20%*initial_magical_attack after cast;max_stacks=6")
    if "equipment:643302" in equipment_ids:
        assumptions.append("daybreak_reduction_applies_after_current_basic_attack_damage")
        equipment_effect("equipment:643302", "target_physical_defense_reduction_per_basic_attack", 3.0, "active_target_physical_defense-=3 for 5 seconds after each basic attack")
    if "equipment:643205" in equipment_ids:
        assumptions.append("frost_invasion_five_stack_damage_window")
        equipment_effect("equipment:643205", "conditional_damage_amplification_percent", 20.0, "after_five_basic_attacks:damage_multiplier*=1.20 for 5 seconds;cooldown=10 seconds")
    if "equipment:643504" in equipment_ids:
        assumptions.append("red_lotus_adjacent_target_proxy_is_fixed_dummy")
        equipment_effect("equipment:643504", "periodic_max_health_magical_damage_percent", 5.0, "raw_per_2_seconds=20+5%*wearer_max_health")
    if "equipment:643704" in equipment_ids:
        damage_amplification = 25.0
        assumptions.append("red_demon_no_adjacent_ally_fixture_amplification")
        equipment_effect("equipment:643704", "damage_amplification_percent", 25.0, "damage_multiplier=1.25 when no adjacent ally")
    if "equipment:643401" in equipment_ids:
        assumptions.append("pain_mask_qualifying_magic_hit_uses_applied_damage_threshold")
        equipment_effect("equipment:643401", "true_damage_magical_attack_percent_per_tick", 75.0, "three_ticks_each=75%*current_magical_attack after qualifying magic hit")
    attack_style = resolve_hero_attack_style(hero)
    if "equipment:641015" in equipment_ids and attack_style.is_ranged:
        assumptions.append("sun_chaser_ranged_wearer_and_single_target_proxy")
        equipment_effect("equipment:641015", "ranged_arrow_physical_attack_percent", 45.0, "one_fixed_target_arrow_per_basic_attack=45%*physical_attack")
    elif "equipment:641015" in equipment_ids:
        excluded.append("sun_chaser_requires_ranged_wearer")
    if "equipment:643304" in equipment_ids:
        assumptions.append("dreamforged_wind_four_basic_attacks_at_start_and_eight_second_boundaries")
        equipment_effect("equipment:643304", "rapid_basic_attacks_per_trigger", 4.0, "four_basic_attacks at battle start and each elapsed 8-second boundary")
    if "equipment:643105" in equipment_ids:
        assumptions.append("pure_sky_adds_ten_magical_attack_each_two_seconds")
        equipment_effect("equipment:643105", "magical_attack_per_two_seconds", 10.0, "magical_attack+=10 at each elapsed 2-second boundary")
    if "equipment:643202" in equipment_ids:
        magical_penetration = 15.0
        assumptions.append("void_staff_flat_magical_defense_penetration")
        equipment_effect("equipment:643202", "flat_magical_defense_penetration", 15.0, "effective_target_magical_defense=max(0,target_magical_defense-15)")
    if "equipment:643403" in equipment_ids:
        assumptions.append("cocoon_breaker_initial_mana_plus_fifteen_random_stun_excluded")
    if "equipment:643603" in equipment_ids:
        assumptions.append("guard_glory_wearer_defense_plus_twenty_each")
    if "equipment:641010" in equipment_ids:
        assumptions.append("ningyuan_default_twenty_received_hit_critical_rate_stacks_fixture")
    if "equipment:643702" in equipment_ids:
        assumptions.append("nether_king_one_adjacent_enemy_fixture")
    if "equipment:643705" in equipment_ids:
        repeat_probability = min(100.0, 35.0 + math.floor(fixture_level / 7.0))
        assumptions.append("magic_law_repeat_cast_uses_level_probability_expected_value")
        equipment_effect(
            "equipment:643705",
            "expected_repeat_cast_probability_percent",
            repeat_probability,
            "min(100,35+floor(fixture_level/7))",
        )

    return _CombatModifiers(
        opening_attack_speed_percent=opening_speed,
        cast_attack_speed_percent=cast_speed,
        opening_attack_speed_base_delta=opening_speed_base_delta,
        cast_attack_speed_base_delta=cast_speed_base_delta,
        cast_buff_seconds=cast_seconds,
        cast_physical_attack_percent=cast_physical_attack_percent,
        cast_physical_attack_seconds=cast_physical_attack_seconds,
        cast_transformed_seconds=cast_transformed_seconds,
        cast_transformation_persists_to_horizon=cast_transformation_persists_to_horizon,
        transformed_basic_mana_restore=transformed_basic_mana_restore,
        transformed_basic_mana_regeneration_disabled=transformed_basic_mana_regeneration_disabled,
        battle_start_cast=battle_start_cast,
        transformed_from_start=transformed_from_start,
        always_basic_attack_bonuses=tuple(always_bonuses),
        transformed_basic_attack_bonuses=tuple(transformed_bonuses),
        equipment_contributions=tuple(equipment_contributions),
        excluded_components=tuple(excluded),
        unresolved_items=tuple(unresolved),
        assumptions=tuple(assumptions),
        damage_amplification_percent=damage_amplification,
        magical_penetration=magical_penetration,
    )


def _parse_skill_node_formula(text: str):
    plain = _plain_text(text)
    match = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*\+\s*([0-9]+(?:\.[0-9]+)?)%\s*(物理|法术)攻击力",
        plain,
    )
    if match:
        fixed = float(match.group(1))
        ratio = float(match.group(2)) / 100.0
        axis = match.group(3)
        return plain, fixed, ratio, axis
    match = re.search(
        r"(?:伤害(?:增加|提升)?至|伤害提升为)([0-9]+(?:\.[0-9]+)?)%\s*(物理|法术)攻击力",
        plain,
    )
    if not match:
        return None
    fixed = 0.0
    ratio = float(match.group(1)) / 100.0
    axis = match.group(2)
    return plain, fixed, ratio, axis


def _apply_unlocked_active_skill_enhancements(
    hero,
    fixture_level,
    formulas,
    physical,
    magical,
):
    if len(formulas) != 1:
        return formulas
    formula = formulas[0]
    components = list(formula.components)
    if len(components) == 1:
        component = components[0]
        current_hit_count = component.hit_count
        current_fixed = component.fixed_damage
        current_physical_ratio = component.physical_attack_ratio
        current_magical_ratio = component.magical_attack_ratio
        changed = False
        nodes = []
        for skill in hero.get("heroCard", {}).get("skillList", ()):
            enhancement = skill.get("enhanceSkill") if isinstance(skill, dict) else None
            if not isinstance(enhancement, dict):
                continue
            nodes.extend(
                item for item in enhancement.get("params") or ()
                if isinstance(item, dict)
                and str(item.get("level", "")).isdigit()
                and int(item["level"]) <= fixture_level
            )
        for node in sorted(nodes, key=lambda item: int(item["level"])):
            text = _plain_text(str(node.get("desc") or ""))
            parsed = _parse_skill_node_formula(text)
            if parsed is not None:
                _, fixed, ratio, axis = parsed
                current_fixed = fixed
                current_physical_ratio = ratio if axis == "物理" else 0.0
                current_magical_ratio = ratio if axis == "法术" else 0.0
                changed = True
            current_hit_count = max(
                current_hit_count,
                _effective_skill_hit_count(
                    str(hero.get("id") or ""),
                    int(node["level"]),
                    current_hit_count,
                    text,
                ),
            )
        if changed or current_hit_count != component.hit_count:
            enhanced_component = replace(
                component,
                fixed_damage=current_fixed,
                physical_attack_ratio=current_physical_ratio,
                magical_attack_ratio=current_magical_ratio,
                hit_count=current_hit_count,
            )
            return (replace(
                formula,
                status="parsed_active_damage_with_unlocked_enhancement",
                components=(enhanced_component,),
                raw_damage_per_cast=enhanced_component.raw_damage(physical, magical),
                assumptions=tuple(dict.fromkeys(formula.assumptions + (
                    "unlocked_enhancement_formula_replaces_base_damage_formula",
                ))),
            ),)
        return formulas
    if (
        "分别造成" not in formula.active_text
        or len(components) != 2
        or {item.damage_type for item in components} != {"physical", "magical"}
    ):
        return formulas
    magical_index = next(
        index for index, item in enumerate(components)
        if item.damage_type == "magical"
    )
    physical_index = next(
        index for index, item in enumerate(components)
        if item.damage_type == "physical"
    )
    segment_count = sum(item.hit_count for item in components)
    physical_ratio = components[physical_index].physical_attack_ratio
    full_skill_text = " ".join(
        _plain_text(str(skill.get("desc") or ""))
        for skill in hero.get("heroCard", {}).get("skillList", ())
        if isinstance(skill, dict)
    )
    segment_changed = False
    ratio_changed = False
    nodes = []
    for skill in hero.get("heroCard", {}).get("skillList", ()):
        enhancement = skill.get("enhanceSkill") if isinstance(skill, dict) else None
        if not isinstance(enhancement, dict):
            continue
        nodes.extend(
            item for item in enhancement.get("params") or ()
            if isinstance(item, dict)
            and str(item.get("level", "")).isdigit()
            and int(item["level"]) <= fixture_level
        )
    for node in sorted(nodes, key=lambda item: int(item["level"])):
        text = _plain_text(str(node.get("desc") or ""))
        segment = re.search(r"技能提升至([0-9]+)段", text)
        if segment and int(segment.group(1)) > sum(item.hit_count for item in components):
            segment_count = int(segment.group(1))
            segment_changed = True
        coefficient = re.search(
            r"物理伤害提升至([0-9]+(?:\.[0-9]+)?)%",
            text,
        )
        if coefficient:
            physical_ratio = float(coefficient.group(1)) / 100.0
            ratio_changed = True
    if not (segment_changed or ratio_changed):
        return formulas
    physical_component = components[physical_index]
    if segment_changed and "双剑合击时造成真实伤害" in full_skill_text:
        paired_hits = max(1, (segment_count - 1) // 2)
        magical_component = components[magical_index]
        components[magical_index] = replace(magical_component, hit_count=paired_hits)
        components[physical_index] = replace(
            physical_component,
            hit_count=paired_hits,
            physical_attack_ratio=physical_ratio,
        )
        components.append(SkillDamageComponent(
            fixed_damage=0.0,
            physical_attack_ratio=physical_ratio,
            magical_attack_ratio=magical_component.magical_attack_ratio,
            hit_count=1,
            damage_type="true",
            source_text="双剑合击时造成真实伤害",
        ))
    else:
        magical_hits = sum(
            item.hit_count for item in components if item.damage_type == "magical"
        )
        components[physical_index] = replace(
            physical_component,
            hit_count=segment_count - magical_hits,
            physical_attack_ratio=physical_ratio,
        )
    assumptions = formula.assumptions
    if segment_changed:
        assumptions += (
            "user_confirmed_mixed_segment_distribution_reserves_one_dual_blade_true_hit",
            "dual_blade_true_hit_combines_current_magical_and_physical_segment_formulas",
        )
    if ratio_changed:
        assumptions += (
            "unlocked_physical_damage_coefficient_applied_to_physical_hits",
        )
    enhanced_components = tuple(components)
    return (replace(
        formula,
        status="parsed_active_damage_with_unlocked_enhancement",
        components=enhanced_components,
        raw_damage_per_cast=sum(
            item.raw_damage(physical, magical) for item in enhanced_components
        ),
        assumptions=tuple(dict.fromkeys(assumptions)),
    ),)


def _effective_skill_hit_count(hero_id, node_level, current_hit_count, source_text):
    if hero_id == "1541":
        return 7
    if hero_id == "1501":
        return 3 if node_level >= 100 else 2 if node_level >= 40 else current_hit_count
    if hero_id == "1481" and node_level >= 40:
        return 3
    match = re.search(r"技能提升至([0-9]+)段", source_text)
    if match:
        return max(current_hit_count, int(match.group(1)))
    extra = re.search(r"额外发射([0-9]+)道冲击波", source_text)
    if extra:
        return max(current_hit_count, current_hit_count + int(extra.group(1)))
    return current_hit_count


def _explicit_extra_cast_node_specs(hero_id, fixture_level, physical, magical):
    if hero_id == "1111" and fixture_level >= 100:
        return ((100, "extra_projectile_damage", "physical", 1.5 * (50.0 + 1.5 * physical), 1, "1.5*(50+1.5*physical_attack)"),)
    if hero_id == "1821" and fixture_level >= 40:
        ratio = 2.0 if fixture_level >= 100 else 1.0
        return ((40, "extra_cast_damage", "magical", 150.0 + ratio * magical, 1, f"150+{ratio:g}*magical_attack;every_second_cast"),)
    if hero_id == "1911" and fixture_level >= 40:
        return ((100 if fixture_level >= 100 else 40, "extra_cast_damage", "magical", 0.5 * magical, 1, "0.5*magical_attack;giant_wave"),)
    if hero_id == "1901" and fixture_level >= 100:
        return ((100, "extra_projectile_damage", "magical", 0.25 * (250.0 + 3.0 * magical), 4, "0.25*(250+3*magical_attack);projectiles=4"),)
    if hero_id == "1361" and fixture_level >= 40:
        return ((40, "extra_area_damage", "magical", 100.0 + 1.25 * magical, 1, "100+1.25*magical_attack;channel_end=8"),)
    return ()


def _skill_node_values(
    hero,
    fixture_level,
    physical,
    magical,
    base_hit_count,
    base_raw_per_hit,
    base_damage_type,
    evidence_ids,
):
    provisional = []
    unresolved = []
    enhancement_nodes = []
    for skill in hero.get("heroCard", {}).get("skillList", ()):
        if not isinstance(skill, dict):
            continue
        enhancement = skill.get("enhanceSkill")
        if not isinstance(enhancement, dict):
            continue
        for item in enhancement.get("params") or ():
            if not isinstance(item, dict) or not str(item.get("level", "")).isdigit():
                continue
            level = int(item["level"])
            source_text = _plain_text(str(item.get("desc") or ""))
            enhancement_nodes.append((level, source_text))
            parsed = _parse_skill_node_formula(source_text)
            if parsed is None:
                continue
            if base_raw_per_hit is None or base_damage_type is None:
                continue
            _, fixed, ratio, axis = parsed
            damage_type = "physical" if axis == "物理" else "magical"
            attack = physical if damage_type == "physical" else magical
            raw_per_hit = fixed + ratio * attack
            attack_name = "physical_attack" if damage_type == "physical" else "magical_attack"
            provisional.append(FixedDummySkillNodeValue(
                unlock_level=level,
                kind="damage_formula_replacement",
                damage_type=damage_type,
                raw_value_per_hit=raw_per_hit,
                raw_value_per_cast=raw_per_hit * max(1, base_hit_count),
                hit_count=max(1, base_hit_count),
                formula=f"per_hit={fixed}+{ratio}*{attack_name};per_cast=per_hit*{max(1, base_hit_count)}",
                source_text=source_text,
                evidence_ids=evidence_ids,
                assumptions=(
                    "fixture_stats_at_selected_level",
                    "enhancement_formula_replaces_base_damage_formula_when_unlocked",
                    "conditional_extra_cast_or_multi_target_nodes_excluded",
                ),
                unresolved_items=(),
                included_in_damage_timeline=False,
            ))
    eligible = [
        item for item in provisional
        if item.kind == "damage_formula_replacement" and item.unlock_level <= fixture_level
    ]
    selected = max(eligible, key=lambda item: item.unlock_level) if eligible else None
    reference_raw = selected.raw_value_per_hit if selected is not None else base_raw_per_hit
    reference_type = selected.damage_type if selected is not None else base_damage_type
    hero_id = str(hero.get("id") or "")
    scheduled_specs = _explicit_extra_cast_node_specs(hero_id, fixture_level, physical, magical)
    scheduled_levels = {item[0] for item in scheduled_specs}
    if reference_raw is not None and reference_type is not None:
        for level, source_text in enhancement_nodes:
            if level in scheduled_levels:
                continue
            percent = re.search(r"([0-9]+(?:\.[0-9]+)?)%\s*的技能伤害", source_text)
            multiple = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*倍(?:的)?伤害", source_text)
            if percent is None and multiple is None:
                if any(term in source_text for term in ("额外释放", "额外发射", "附近敌人", "每第", "每隔")):
                    unresolved.append(f"skill_enhancement_node_not_scheduled:{level}")
                continue
            multiplier = (
                float(percent.group(1)) / 100.0
                if percent is not None
                else float(multiple.group(1))
            )
            kind = (
                "nearby_area_damage_ratio"
                if percent is not None and any(term in source_text for term in ("附近", "爆炸"))
                else "extra_projectile_damage_multiplier"
                if multiple is not None and any(term in source_text for term in ("额外", "发射", "释放"))
                else "relative_damage_multiplier"
            )
            unresolved_item = f"skill_enhancement_node_not_scheduled:{level}"
            unresolved.append(unresolved_item)
            provisional.append(FixedDummySkillNodeValue(
                unlock_level=level,
                kind=kind,
                damage_type=reference_type,
                raw_value_per_hit=reference_raw * multiplier,
                raw_value_per_cast=reference_raw * multiplier,
                hit_count=1,
                formula=f"display_only_raw={reference_raw}*{multiplier}",
                source_text=source_text,
                evidence_ids=evidence_ids,
                assumptions=(
                    "fixture_stats_at_selected_level",
                    "relative_value_uses_current_direct_skill_damage_per_hit",
                    "display_only_not_scheduled_in_damage_timeline",
                    "conditional_extra_cast_or_multi_target_nodes_excluded",
                ),
                unresolved_items=(unresolved_item,),
                included_in_damage_timeline=False,
            ))
    source_by_level = {level: source_text for level, source_text in enhancement_nodes}
    for level, kind, damage_type, raw_per_hit, hit_count, formula in scheduled_specs:
        provisional.append(FixedDummySkillNodeValue(
            unlock_level=level,
            kind=kind,
            damage_type=damage_type,
            raw_value_per_hit=raw_per_hit,
            raw_value_per_cast=raw_per_hit * hit_count,
            hit_count=hit_count,
            formula=formula,
            source_text=source_by_level.get(level, "formal_explicit_extra_damage_node"),
            evidence_ids=evidence_ids,
            assumptions=(
                "fixture_stats_at_selected_level",
                "explicit_extra_cast_or_projectile_scheduled_to_fixed_target",
                "cast_start_proxy" if hero_id != "1361" else "eight_second_channel_end",
            ),
            unresolved_items=(),
            included_in_damage_timeline=True,
        ))
    values = tuple(
        replace(item, included_in_damage_timeline=selected is item or item.kind in {"extra_projectile_damage", "extra_cast_damage", "extra_area_damage"})
        for item in sorted(provisional, key=lambda item: item.unlock_level)
    )
    selected_value = next((item for item in values if item.included_in_damage_timeline), None)
    return values, selected_value, tuple(dict.fromkeys(unresolved))


def _formula_from_skill_node(node, base_formula, physical, magical):
    parsed = _parse_skill_node_formula(node.source_text)
    if parsed is None:
        return base_formula
    _, fixed, ratio, axis = parsed
    effective_hit_count = (
        base_formula.components[0].hit_count
        if len(base_formula.components) == 1
        else node.hit_count
    )
    component = SkillDamageComponent(
        fixed_damage=fixed,
        physical_attack_ratio=ratio if axis == "物理" else 0.0,
        magical_attack_ratio=ratio if axis == "法术" else 0.0,
        hit_count=effective_hit_count,
        damage_type=node.damage_type,
        source_text=node.source_text,
    )
    return SkillFormulaResult(
        status="parsed_active_damage_with_unlocked_enhancement",
        active_text=node.source_text,
        components=(component,),
        raw_damage_per_cast=(fixed + ratio * (physical if axis == "物理" else magical)) * effective_hit_count,
        assumptions=tuple(dict.fromkeys(base_formula.assumptions + (
            "unlocked_enhancement_formula_replaces_base_damage_formula",
        ))),
        unresolved_items=base_formula.unresolved_items,
    )


def _dummy_mitigation(fixture, combat_modifiers=None):
    result = []
    for damage_type, resistance in (
        ("physical", fixture.dummy_physical_defense),
        (
            "magical",
            max(
                0.0,
                fixture.dummy_magical_defense
                - (combat_modifiers.magical_penetration if combat_modifiers else 0.0),
            ),
        ),
    ):
        multiplier = resistance_multiplier(resistance)
        result.append(FixedDummyMitigationSummary(
            damage_type=damage_type,
            resistance=resistance,
            damage_multiplier=multiplier.value,
            damage_reduction_percent=(1.0 - multiplier.value) * 100.0,
            formula=(
                "effective_resistance=max(0,resistance-flat_penetration);damage_multiplier=40/(effective_resistance+40);damage_reduction=1-damage_multiplier"
                if damage_type == "magical" and combat_modifiers and combat_modifiers.magical_penetration
                else "damage_multiplier=40/(resistance+40);damage_reduction=1-damage_multiplier"
            ),
            evidence_ids=("model:combat-math:resistance-multiplier-v0",) + (
                ("official-raw:equipment:643202:desc",)
                if damage_type == "magical" and combat_modifiers and combat_modifiers.magical_penetration
                else ()
            ),
        ))
    return tuple(result)


def _apply_event(
    time,
    event_id,
    event_type,
    raw,
    damage_type,
    fixture,
    hp,
    cumulative,
    mana_before,
    mana_after,
    evidence_ids,
    assumptions,
    source_id="fixture:hero",
    resistance_override=None,
    damage_multiplier=1.0,
    event_semantics="deterministic",
    rule_id="fixed-dummy:legacy:v0",
    phase="damage",
    priority=0,
    caused_by_event_id=None,
    coverage_tier="strict",
):
    resistance = (
        fixture.dummy_physical_defense
        if damage_type == "physical"
        else fixture.dummy_magical_defense
        if damage_type == "magical"
        else 0.0
    )
    if resistance_override is not None:
        resistance = resistance_override
    unmitigated = raw * damage_multiplier
    applied = unmitigated * resistance_multiplier(resistance).value
    deterministic = event_semantics == "deterministic"
    remaining = max(0.0, hp - applied) if deterministic else hp
    overkill = max(0.0, applied - hp) if deterministic else 0.0
    deterministic_applied = min(applied, hp) if deterministic else 0.0
    cumulative += deterministic_applied
    return remaining, cumulative, FixedDummyDamageEvent(
        time=time,
        event_id=event_id,
        event_type=event_type,
        source_id=source_id,
        target_id="fixture:dummy",
        damage_type=damage_type,
        raw_value=raw,
        unmitigated_value=unmitigated,
        applied_value=applied,
        cumulative_actual_damage=cumulative,
        dummy_remaining_hp=remaining,
        overkill_damage=overkill,
        mana_before=mana_before,
        mana_after=mana_after,
        evidence_ids=evidence_ids,
        assumptions=_FIXED_ASSUMPTIONS + assumptions,
        unresolved_items=("rounding_order",),
        event_semantics=event_semantics,
        deterministic_applied_value=deterministic_applied,
        rule_id=rule_id,
        phase=phase,
        priority=priority,
        caused_by_event_id=caused_by_event_id,
        coverage_tier=coverage_tier,
    )


def _with_model_counters(events, dummy_hp):
    model_cumulative = 0.0
    model_expected_zero_time = None
    enriched = []
    for event in events:
        model_increment = (
            event.deterministic_applied_value
            if event.event_semantics == "deterministic"
            else event.applied_value
        )
        model_cumulative += model_increment
        model_remaining = max(0.0, dummy_hp - model_cumulative)
        if model_expected_zero_time is None and model_remaining <= 0:
            model_expected_zero_time = event.time
        enriched.append(replace(
            event,
            model_applied_value=model_increment,
            cumulative_model_damage=model_cumulative,
            model_remaining_hp=model_remaining,
        ))
    return tuple(enriched), model_cumulative, model_expected_zero_time


def _skill_mechanism_schedules(
    hero,
    fixture_level: int,
    physical: float,
    magical: float,
    dummy_hp: float,
    horizon_seconds: float,
    evidence_ids: tuple[str, ...],
    attack_speed: float | None = None,
    rule_pack: FixedDummyRulePackV1 | None = None,
) -> tuple[FixedDummySkillMechanismSchedule, ...]:
    """Return explicit mechanism schedules; unresolved mechanisms stay receipts only."""
    hero_id = str(hero.get("id") or "")
    schedules: list[FixedDummySkillMechanismSchedule] = []

    def add(
        schedule_id: str,
        unlock_level: int,
        status: str,
        trigger: str,
        event_type: str,
        damage_type: str | None,
        start_offset: float | None,
        interval: float | None,
        hit_count: int,
        raw_per_hit: float | None,
        formula: str,
        source_text: str,
        assumptions: tuple[str, ...] = (),
        unresolved: tuple[str, ...] = (),
        included: bool = False,
        target_repeat_policy: str = "single_fixed_target_only",
        cast_every: int = 1,
        coverage_tier: str | None = None,
        hits_per_tick: int = 1,
    ) -> None:
        resolved_coverage_tier = coverage_tier or (
            "exploratory" if status == "bounded_proxy" else "strict"
        )
        rule = (
            rule_pack.mechanism_rule(
                schedule_id,
                target_policy=target_repeat_policy,
                coverage_tier=resolved_coverage_tier,
            )
            if rule_pack is not None
            else None
        )
        schedules.append(FixedDummySkillMechanismSchedule(
            schedule_id,
            unlock_level,
            status,
            trigger,
            event_type,
            damage_type,
            start_offset,
            interval,
            max(0, int(hit_count)),
            raw_per_hit,
            None if raw_per_hit is None else raw_per_hit * max(0, int(hit_count)),
            formula,
            source_text,
            evidence_ids,
            tuple(dict.fromkeys(item for item in assumptions if item)),
            tuple(dict.fromkeys(unresolved)),
            included,
            target_repeat_policy,
            max(1, int(cast_every)),
            rule.rule_id if rule is not None else f"fixed-dummy:mechanism:{schedule_id}:v1",
            rule.phase if rule is not None else "scheduled_hit",
            rule.priority if rule is not None else 50,
            resolved_coverage_tier,
            max(1, int(hits_per_tick)),
        ))

    if hero_id == "1421":
        unlock = 40 if fixture_level >= 40 else 10 if fixture_level >= 10 else 1
        ratio = 0.17 if unlock >= 10 else 0.10
        laser_count = 3 if unlock >= 40 else 1
        add(
            "hero:1421:hot_glory",
            unlock,
            "fully_schedulable",
            "active_cast",
            "active_skill_periodic_damage",
            "magical",
            0.1,
            0.1,
            30 * laser_count,
            ratio * magical,
            f"{ratio:g}*magical_attack;laser_count={laser_count};ticks=30;interval=0.1",
            "three_second_hot_glory_hits_once_each_0_1_seconds_per_laser",
            (
                "single_fixed_target_remains_on_laser_path",
                "cast_start_proxy",
                "laser_count_hits_share_each_0_1_second_tick",
            ),
            target_repeat_policy="repeat_same_target_each_laser_tick",
            included=True,
            hits_per_tick=laser_count,
        )
    elif hero_id == "1061":
        unlock = 10 if fixture_level >= 10 else 1
        ratio = 0.15 if unlock == 10 else 0.10
        add(
            "hero:1061:whirlwind",
            unlock,
            "fully_schedulable",
            "active_cast",
            "active_skill_periodic_damage",
            "magical",
            0.2,
            0.2,
            15,
            ratio * magical,
            f"{ratio:g}*magical_attack;hits=15;interval=0.2",
            "every_0.2_seconds_for_up_to_3_seconds",
            ("single_fixed_target_remains_in_whirlwind", "cast_start_proxy"),
            target_repeat_policy="repeat_same_target_each_tick",
            included=True,
        )
    elif hero_id == "1191":
        unlock = 10 if fixture_level >= 10 else 1
        ratio = 0.90 if unlock == 10 else 0.60
        add(
            "hero:1191:liquid",
            unlock,
            "fully_schedulable",
            "active_cast",
            "active_skill_periodic_damage",
            "magical",
            1.0,
            1.0,
            5,
            20.0 + ratio * magical,
            f"20+{ratio:g}*magical_attack;hits=5;interval=1",
            "enemy_in_liquid_takes_damage_each_second_for_5_seconds",
            ("single_fixed_target_uses_one_liquid_pool", "overlapping_liquid_pools_stack", "cast_start_proxy"),
            target_repeat_policy="one_liquid_pool_per_cast_on_fixed_dummy",
            included=True,
        )
    elif hero_id == "1101":
        unlock = 100 if fixture_level >= 100 else 40 if fixture_level >= 40 else 10 if fixture_level >= 10 else 1
        ratio = 0.15 if fixture_level >= 10 else 0.10
        fixed = 15.0 if fixture_level >= 10 else 10.0
        count = 120 if unlock == 100 else 100 if unlock == 40 else 80
        add(
            "hero:1101:swords",
            unlock,
            "bounded_proxy",
            "active_cast",
            "active_skill_projectile_damage_proxy",
            "magical",
            5.0 / count,
            5.0 / count,
            count,
            fixed + ratio * magical,
            f"{fixed:g}+{ratio:g}*magical_attack;hits={count};uniform_over_5_seconds_proxy",
            "five_second_projectile_total_with_no_per_projectile_timestamps",
            (
                "uniform_projectile_distribution_over_five_seconds_proxy",
                "single_fixed_target_remains_on_projectile_path",
                "cast_start_proxy",
            ),
            target_repeat_policy="repeat_same_target_projectile_proxy",
            included=True,
            coverage_tier="strict",
        )
    elif hero_id == "5311" and fixture_level >= 40:
        clone_count = 2 if fixture_level >= 100 else 1
        add(
            "hero:5311:mirror_clone",
            100 if fixture_level >= 100 else 40,
            "fully_schedulable",
            "active_cast",
            "active_skill_clone_damage",
            "physical",
            0.0,
            None,
            clone_count,
            80.0 + 1.5 * physical,
            f"80+1.5*physical_attack;clone_count={clone_count}",
            "formal_level_40_or_100_mirror_clone_hits_current_target",
            (
                "mirror_clone_hits_same_fixed_target_as_current_cast",
                "cast_start_proxy",
            ),
            target_repeat_policy="one_clone_skill_hit_to_current_fixed_target",
            included=True,
        )
    elif hero_id == "5091":
        unlock = 1
        battle_start = fixture_level >= 100
        duration = horizon_seconds if battle_start else 8.0 if fixture_level >= 10 else 3.0
        count = max(1, int(math.ceil(duration - 1e-9)))
        add(
            "hero:5091:shield",
            unlock,
            "fully_schedulable",
            "battle_start" if battle_start else "active_cast",
            "active_skill_periodic_damage",
            "magical",
            1.0,
            1.0,
            count,
            50.0,
            f"50;interval=1;duration={duration:g}",
            "shield_form_hits_front_target_each_second",
            (
                "single_fixed_target_is_in_front_one_cell",
                "battle_start_proxy" if battle_start else "cast_start_proxy",
                "horizon_bounded_persistent_form" if battle_start else "",
            ),
            target_repeat_policy="repeat_same_target_each_tick",
            included=True,
        )
    elif hero_id == "1661":
        unlock = 10 if fixture_level >= 10 else 1
        duration = 8.0 if fixture_level >= 40 else 5.0
        add(
            "hero:1661:holy_shield",
            unlock,
            "fully_schedulable",
            "active_cast",
            "active_skill_periodic_damage",
            "physical",
            1.0,
            1.0,
            int(duration),
            (0.80 if fixture_level >= 10 else 0.50) * physical,
            f"{0.80 if fixture_level >= 10 else 0.50:g}*physical_attack;interval=1;duration={duration:g}",
            "holy_shield_hits_adjacent_fixed_target_each_second",
            ("single_fixed_target_is_within_one_cell", "cast_start_proxy"),
            target_repeat_policy="repeat_same_target_each_tick",
            included=True,
        )
        if fixture_level >= 100:
            add(
                "hero:1661:target_max_health_sword",
                100,
                "fully_schedulable",
                "active_cast",
                "active_skill_target_max_health_damage",
                "magical",
                0.0,
                None,
                1,
                dummy_hp * 0.15,
                "0.15*dummy_max_health",
                "level_100_extra_sword_damage",
                ("dummy_hp_is_target_max_health_proxy", "cast_start_proxy"),
                target_repeat_policy="one_target_max_health_hit",
                included=True,
            )
    elif hero_id == "1111" and fixture_level >= 100:
        base_ratio = 1.5 if fixture_level >= 10 else 1.0
        add(
            "hero:1111:extra_cannon",
            100,
            "bounded_proxy",
            "active_cast",
            "active_skill_extra_projectile_damage",
            "physical",
            0.0,
            None,
            1,
            1.5 * (50.0 + base_ratio * physical),
            f"1.5*(50+{base_ratio:g}*physical_attack);extra_projectile=1",
            "formal_level_100_extra_cannon_node",
            (
                "single_fixed_target_extra_projectile_hits_original_target_proxy",
                "cast_start_proxy",
            ),
            target_repeat_policy="one_explicit_extra_projectile_to_fixed_target",
            included=True,
            coverage_tier="strict",
        )
    elif hero_id == "1821" and fixture_level >= 40:
        ratio = 2.0 if fixture_level >= 100 else 1.0
        add(
            "hero:1821:second_cast_extra_sword_pair",
            40,
            "fully_schedulable",
            "active_cast",
            "active_skill_extra_cast_damage",
            "magical",
            0.0,
            None,
            1,
            150.0 + ratio * magical,
            f"150+{ratio:g}*magical_attack;extra_sword_pair_every_second_cast",
            "formal_level_40_second_cast_extra_sword_pair_node",
            ("single_fixed_target_extra_sword_pair_hits_original_target", "cast_start_proxy"),
            target_repeat_policy="one_extra_sword_pair_to_fixed_target",
            cast_every=2,
            included=True,
        )
    elif hero_id == "1911" and fixture_level >= 40:
        add(
            "hero:1911:giant_wave",
            100 if fixture_level >= 100 else 40,
            "fully_schedulable",
            "active_cast",
            "active_skill_extra_cast_damage",
            "magical",
            0.0,
            None,
            1,
            0.50 * magical,
            "0.5*magical_attack;giant_wave",
            "formal_level_40_or_100_giant_wave_node",
            ("single_fixed_target_giant_wave_hits_original_target", "cast_start_proxy"),
            target_repeat_policy="one_giant_wave_to_fixed_target",
            cast_every=1 if fixture_level >= 100 else 3,
            included=True,
        )
    elif hero_id == "1901" and fixture_level >= 100:
        base = 250.0 + 3.0 * magical
        add(
            "hero:1901:four_small_orbs",
            100,
            "bounded_proxy",
            "active_cast",
            "active_skill_extra_projectile_damage",
            "magical",
            0.0,
            None,
            4,
            0.25 * base,
            "0.25*(250+3*magical_attack);extra_projectiles=4",
            "formal_level_100_four_small_orbs_node",
            (
                "single_fixed_target_extra_projectiles_hit_original_target_proxy",
                "cast_start_proxy",
            ),
            target_repeat_policy="four_explicit_extra_projectiles_to_fixed_target",
            included=True,
            coverage_tier="strict",
        )
    elif hero_id == "1361" and fixture_level >= 40:
        add(
            "hero:1361:channel_end_large_formation",
            40,
            "fully_schedulable",
            "active_cast",
            "active_skill_extra_area_damage",
            "magical",
            8.0,
            None,
            1,
            100.0 + 1.25 * magical,
            "100+1.25*magical_attack;channel_end_offset=8",
            "formal_level_40_channel_end_large_formation_node",
            ("all_enemies_includes_fixed_dummy", "eight_second_channel_end"),
            target_repeat_policy="one_channel_end_area_hit_to_fixed_target",
            included=True,
        )
    elif hero_id == "3551" and fixture_level >= 40:
        add(
            "hero:3551:thirty_blessing_on_hit",
            40,
            "fully_schedulable",
            "basic_attack_after_30_blessing_stacks",
            "passive_basic_attack_magical_damage",
            "magical",
            0.0,
            None,
            1,
            0.10 * (magical + 2.0),
            "each_qualifying_basic_attack:magical_attack+=2;raw=0.10*current_magical_attack",
            "at_30_blessing_stacks_each_basic_attack_gains_2_magical_attack_and_deals_10_percent_current_magical_attack",
            (
                "one_blessing_stack_per_scheduled_basic_attack",
                "level_40_on_hit_activates_at_thirty_blessing_stacks",
                "magical_attack_gain_applies_before_current_on_hit_damage",
            ),
            target_repeat_policy="one_on_hit_per_basic_attack_action",
            included=True,
        )
    elif hero_id == "5171":
        connection_cycle = 3.0 / max(attack_speed or 1.0, 1e-9)
        add(
            "hero:5171:spirit_link",
            1,
            "fully_schedulable",
            "basic_attack",
            "passive_basic_attack_link_damage",
            "physical",
            0.0,
            connection_cycle / 5.0,
            5,
            0.50 * physical,
            f"0.5*physical_attack;hits=5;base_cycle=3;effective_cycle=3/attack_speed={connection_cycle:g};uniform_interval={connection_cycle / 5.0:g}",
            "basic_attack_connects_for_five_hits_over_three_seconds",
            (
                "five_link_hits_are_one_basic_attack_action",
                "basic_attack_equipment_effects_trigger_once_at_full_value",
                "three_second_connection_cycle_compressed_by_attack_speed",
                "uniform_within_cycle_timing_proxy",
                "cast_start_proxy",
            ),
            target_repeat_policy="five_link_hits_repeat_same_target",
            included=True,
        )

    return tuple(schedules)


def _mechanism_managed(text: str) -> bool:
    return (
        "每秒" in text
        or "每隔" in text
        or re.search(r"每(?:0?\.\d+|\d+(?:\.\d+)?)秒", text) is not None
        or "衰减" in text
        or ("5秒内" in text and "每把" in text)
    )


def _single_damage_type(formulas) -> str | None:
    types = {component.damage_type for formula in formulas for component in formula.components}
    return next(iter(types)) if len(types) == 1 and next(iter(types)) in {"physical", "magical", "true"} else None


def _skill_damage_components(formulas, physical, magical, evidence_ids):
    result = []
    index = 1
    for formula in formulas:
        for component in formula.components:
            per_cast = component.raw_damage(physical, magical)
            result.append(FixedDummySkillDamageComponent(
                component_index=index,
                damage_type=component.damage_type,
                hit_count=component.hit_count,
                raw_value_per_hit=per_cast / max(1, component.hit_count),
                raw_value_per_cast=per_cast,
                formula=_component_formula(component),
                source_text=component.source_text,
                evidence_ids=evidence_ids,
                assumptions=formula.assumptions + ("per_hit_value_derived_from_fixture_stats",),
            ))
            index += 1
    return tuple(result)


def _component_formula(component):
    parts = []
    if component.fixed_damage:
        parts.append(str(component.fixed_damage))
    if component.physical_attack_ratio:
        parts.append(f"{component.physical_attack_ratio}*physical_attack")
    if component.magical_attack_ratio:
        parts.append(f"{component.magical_attack_ratio}*magical_attack")
    per_hit = "+".join(parts) or "0"
    return f"per_hit={per_hit};per_cast=per_hit*{component.hit_count}"


def _formula_hit_count(text: str, formula_start: int, formula_end: int, hero_id: str, unlock_level: int) -> tuple[int, tuple[str, ...]]:
    context = text[max(0, formula_start - 140):formula_end]
    active_boundary = context.rfind("主动：")
    if active_boundary >= 0:
        context = context[active_boundary:]
    assumptions: tuple[str, ...] = ()
    if hero_id == "1421":
        laser_count = 3 if unlock_level >= 40 else 1
        return 30 * laser_count, (
            f"angela_laser_count_{laser_count}",
            "three_second_hot_glory_tick_count_30",
            "damage_total_is_display_only",
        )
    if hero_id == "1191":
        return 5, ("bianque_liquid_five_second_tick_window", "damage_total_is_display_only")
    if hero_id == "1101":
        if unlock_level >= 100:
            return 120, ("yingzheng_level_100_base_projectile_count_120", "damage_total_is_display_only")
        if unlock_level >= 40:
            return 100, ("yingzheng_level_40_base_projectile_count_100", "damage_total_is_display_only")
        return 80, ("yingzheng_base_projectile_count_80", "damage_total_is_display_only")
    count_match = re.search(
        r"(\d+)\s*(片|把|枚|支|段|次)[^。；]{0,80}?每(?:片|把|枚|支|段|次)",
        context,
    )
    if count_match:
        return int(count_match.group(1)), (f"formula_hit_count_from_{count_match.group(2)}_each_clause", "damage_total_is_display_only")
    repeated_match = re.search(r"(?:造成|进行)(\d+)次[^。；]{0,30}?每次", context)
    if repeated_match:
        return int(repeated_match.group(1)), ("formula_hit_count_from_repeated_action_clause", "damage_total_is_display_only")
    interval = re.search(r"每(0?\.\d+|\d+(?:\.\d+)?)秒", context)
    duration = re.search(r"(?:最多|持续)(\d+(?:\.\d+)?)秒", text)
    if interval and duration:
        seconds = float(interval.group(1))
        if seconds > 0:
            count = max(1, int(round(float(duration.group(1)) / seconds)))
            return count, ("formula_hit_count_from_interval_and_duration", "damage_total_is_display_only")
    if "每秒" in context and duration:
        return max(1, int(round(float(duration.group(1)))),), ("formula_hit_count_from_one_second_interval", "damage_total_is_display_only")
    return 1, assumptions


def _skill_formula_values(hero, fixture_level, max_health, dummy_hp, physical, magical, evidence_ids):
    """Extract bounded formula values from all skill text for player-facing display.

    This parser deliberately produces display receipts only. It never creates a
    combat event; lifecycle/targeting assumptions stay attached to each value.
    """
    hero_id = str(hero.get("id") or "")
    values = []

    def parse(level, raw_text):
        text = _plain_text(raw_text)
        candidates = []

        def candidate(match, kind, semantic, damage_type, per_hit, formula, assumptions, priority):
            candidates.append((match.start(), match.end(), priority, kind, semantic, damage_type, per_hit, formula, assumptions, match.group(0)))

        for match in re.finditer(
            r"(?:(\d+(?:\.\d+)?)\s*\+\s*)?(\d+(?:\.\d+)?)%\s*(法术攻击力|物理攻击力)(?:的)?(法术伤害|物理伤害|伤害)?",
            text,
        ):
            base = float(match.group(1) or 0.0)
            ratio = float(match.group(2)) / 100.0
            stat_label = match.group(3)
            label = match.group(4) or ""
            before = text[max(0, match.start() - 36):match.start()]
            after = text[match.end():match.end() + 28]
            if label:
                semantic, kind = "damage", "damage"
            elif "护盾" in before or "护盾" in after:
                semantic, kind = "shield", "shield"
            else:
                damage_index = max(before.rfind("伤害"), before.rfind("伤"))
                healing_index = max(before.rfind("恢复"), before.rfind("回复"), before.rfind("治疗"))
                if healing_index > damage_index:
                    semantic, kind = "healing", "healing"
                elif damage_index >= 0 or "伤害" in after:
                    semantic, kind = "damage", "damage"
                elif "生命值" in after:
                    semantic, kind = "healing", "healing"
                else:
                    semantic, kind = "effect", "scaling_effect"
            damage_type = "magical" if stat_label == "法术攻击力" else "physical" if stat_label == "物理攻击力" else None
            stat = magical if damage_type == "magical" else physical
            value = base + ratio * stat
            candidate(
                match,
                kind,
                semantic,
                damage_type if semantic == "damage" else None,
                value,
                f"{base:g}+{ratio:g}*{('magical_attack' if stat_label == '法术攻击力' else 'physical_attack')}",
                ("formula_damage_type_inferred_from_attack_axis" if not label and semantic == "damage" else "",),
                10,
            )

        for match in re.finditer(
            r"(?:(\d+(?:\.\d+)?)\s*\+\s*)?(\d+(?:\.\d+)?)%\s*(法术伤害|物理伤害)",
            text,
        ):
            base = float(match.group(1) or 0.0)
            ratio = float(match.group(2)) / 100.0
            damage_type = "magical" if match.group(3) == "法术伤害" else "physical"
            stat = magical if damage_type == "magical" else physical
            candidate(
                match,
                "damage",
                "damage",
                damage_type,
                base + ratio * stat,
                f"{base:g}+{ratio:g}*{('magical_attack' if damage_type == 'magical' else 'physical_attack')}",
                ("attack_axis_inferred_from_damage_type",),
                12,
            )

        for match in re.finditer(r"(\d+(?:\.\d+)?)%\s*最大生命(?:值)?(?:的)?(法术伤害|物理伤害|护盾)", text):
            ratio = float(match.group(1)) / 100.0
            label = match.group(2)
            semantic = "shield" if label == "护盾" else "damage"
            before = text[max(0, match.start() - 36):match.start()]
            target_max_health = semantic == "damage" and any(
                term in before for term in ("目标敌人", "敌人", "其")
            )
            health_value = dummy_hp if target_max_health else max_health
            candidate(
                match,
                semantic,
                semantic,
                None if semantic == "shield" else ("magical" if label == "法术伤害" else "physical"),
                ratio * health_value,
                f"{ratio:g}*{'dummy_max_health' if target_max_health else 'source_max_health'}",
                ("fixed_dummy_target_max_health" if target_max_health else "fixed_dummy_source_max_health",),
                8,
            )

        for match in re.finditer(r"(?:(\d+(?:\.\d+)?)\s*\+\s*)?(\d+(?:\.\d+)?)%\s*最大生命值(?:的生命值)?", text):
            before = text[max(0, match.start() - 30):match.start()]
            after = text[match.end():match.end() + 12]
            if not any(term in before for term in ("恢复", "回复", "治疗")) and "生命值" not in after:
                continue
            base = float(match.group(1) or 0.0)
            ratio = float(match.group(2)) / 100.0
            candidate(
                match,
                "healing",
                "healing",
                None,
                base + ratio * max_health,
                f"{base:g}+{ratio:g}*max_health",
                ("fixed_dummy_source_max_health",),
                9,
            )

        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*点(法术伤害|物理伤害)", text):
            candidate(match, "damage", "damage", "magical" if match.group(2) == "法术伤害" else "physical", float(match.group(1)), f"fixed_damage={match.group(1)}", (), 20)

        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*点(?:的)?护盾", text):
            candidate(match, "shield", "shield", None, float(match.group(1)), f"fixed_shield={match.group(1)}", (), 20)

        for match in re.finditer(r"(?:恢复|回复)[^。；]{0,20}?(\d+(?:\.\d+)?)\s*点生命值", text):
            candidate(match, "healing", "healing", None, float(match.group(1)), f"fixed_healing={match.group(1)}", (), 20)

        for start, end, priority, kind, semantic, damage_type, per_hit, formula, assumptions, source_text in sorted(candidates):
            if any(start < existing_end and end > existing_start for existing_start, existing_end, *_ in []):
                continue
            hit_count, hit_assumptions = _formula_hit_count(text, start, end, hero_id, level)
            values.append(FixedDummySkillFormulaValue(
                level,
                kind,
                semantic,
                damage_type,
                float(per_hit),
                hit_count,
                float(per_hit) * hit_count,
                formula,
                source_text,
                evidence_ids,
                tuple(dict.fromkeys(tuple(item for item in assumptions if item) + tuple(hit_assumptions) + ("display_only_formula_value",))),
                False,
            ))

    for skill in hero.get("heroCard", {}).get("skillList", ()):
        if not isinstance(skill, dict):
            continue
        parse(1, str(skill.get("desc") or ""))
        enhancement = skill.get("enhanceSkill")
        if isinstance(enhancement, dict):
            for item in enhancement.get("params") or ():
                if isinstance(item, dict) and str(item.get("level", "")).isdigit():
                    parse(int(item["level"]), str(item.get("desc") or ""))
    if hero_id == "1101":
        per_hit = 15.0 + 0.15 * magical
        for level, hit_count, source_text in (
            (40, 100, "飞剑基础数量增加到100把"),
            (100, 120, "飞剑基础数量增加到120把"),
        ):
            values.append(FixedDummySkillFormulaValue(
                level,
                "projectile_count_damage_total",
                "damage",
                "magical",
                per_hit,
                hit_count,
                per_hit * hit_count,
                "per_hit=15+0.15*magical_attack;total=per_hit*projectile_count",
                source_text,
                evidence_ids,
                (
                    f"yingzheng_level_{level}_base_projectile_count_{hit_count}",
                    "inherits_latest_unlocked_per_projectile_formula",
                    "damage_total_is_display_only",
                    "display_only_formula_value",
                ),
                False,
            ))
    return tuple(values)


def _skill_auxiliary_values(
    hero,
    fixture_level,
    max_health,
    dummy_hp,
    physical,
    skill_damage_components,
    evidence_ids,
):
    values = []

    def add(level, kind, value, formula, source_text, assumptions, damage_type=None):
        key = (level, kind)
        if any((item.unlock_level, item.kind) == key for item in values):
            return
        values.append(FixedDummySkillAuxiliaryValue(
            level,
            kind,
            value,
            formula,
            source_text,
            evidence_ids,
            assumptions + ("display_only_not_applied_to_damage_trace",),
            False,
            damage_type,
        ))

    def parse(level, text):
        plain = _plain_text(text)
        for match in re.finditer(
            r"([0-9]+(?:\.[0-9]+)?)%最大生命值的法术伤害",
            plain,
        ):
            ratio = float(match.group(1)) / 100.0
            add(
                level,
                "target_max_health_magical_damage",
                ratio * dummy_hp,
                f"{ratio}*target_max_health",
                match.group(0),
                ("fixed_dummy_target_max_health", "contact_frequency_unresolved"),
                "magical",
            )
        for match in re.finditer(
            r"恢复[^。；\n]*?([0-9]+(?:\.[0-9]+)?)%的?最大生命值",
            plain,
        ):
            if "普攻" in plain[max(0, match.start() - 3):match.start()]:
                continue
            ratio = float(match.group(1)) / 100.0
            kind = (
                "source_max_health_healing"
                if "恢复东皇" in match.group(0)
                else "healing"
            )
            add(
                level,
                kind,
                ratio * max_health,
                f"{ratio}*source_max_health",
                match.group(0),
                ("source_hero_max_health", "contact_frequency_unresolved"),
            )
        for match in re.finditer(
            r"([0-9]+(?:\.[0-9]+)?)\s*\+\s*([0-9]+(?:\.[0-9]+)?)%\s*最大生命(?:值)?的护盾",
            plain,
        ):
            fixed, ratio = float(match.group(1)), float(match.group(2)) / 100.0
            add(
                level,
                "shield",
                fixed + ratio * max_health,
                f"{fixed}+{ratio}*source_max_health",
                match.group(0),
                ("source_hero_max_health",),
            )
        for match in re.finditer(
            r"普攻附带([0-9]+(?:\.[0-9]+)?)%物理攻击力的真实伤害|真实伤害提升至([0-9]+(?:\.[0-9]+)?)%物理攻击力",
            plain,
        ):
            percent = next(value for value in match.groups() if value is not None)
            ratio = float(percent) / 100.0
            add(
                level,
                "basic_attack_true_damage",
                ratio * physical,
                f"{ratio}*physical_attack",
                match.group(0),
                ("fixture_physical_attack", "weapon_branch_condition_not_scheduled_before_level_100"),
                "true",
            )
        basic_heal = re.search(
            r"普攻恢复(?:提升至)?([0-9]+(?:\.[0-9]+)?)(?:\s*\+\s*([0-9]+(?:\.[0-9]+)?)%最大生命值)?",
            plain,
        )
        if basic_heal:
            fixed = float(basic_heal.group(1))
            ratio = float(basic_heal.group(2) or 0) / 100.0
            add(
                level,
                "basic_attack_healing",
                fixed + ratio * max_health,
                f"{fixed}+{ratio}*source_max_health",
                basic_heal.group(0),
                ("source_hero_max_health", "weapon_branch_condition_not_scheduled_before_level_100"),
            )
        cast_heal = re.search(
            r"施法(?:额外)?恢复(?:提升至)?([0-9]+(?:\.[0-9]+)?)点?",
            plain,
        )
        if cast_heal:
            fixed = float(cast_heal.group(1))
            add(
                level,
                "cast_healing",
                fixed,
                f"fixed_healing={fixed}",
                cast_heal.group(0),
                ("weapon_branch_condition_not_scheduled_before_level_100",),
            )
        periodic = re.search(
            r"每[0-9]+(?:\.[0-9]+)?秒[^。；\n]*?自身([0-9]+(?:\.[0-9]+)?)%最大生命值的真实伤害",
            plain,
        )
        if periodic:
            ratio = float(periodic.group(1)) / 100.0
            add(
                level,
                "periodic_true_damage",
                ratio * max_health,
                f"{ratio}*source_max_health",
                periodic.group(0),
                ("source_hero_max_health", "periodic_mechanism_excluded"),
                "true",
            )

    for skill in hero.get("heroCard", {}).get("skillList", ()):
        if not isinstance(skill, dict):
            continue
        base_text = str(skill.get("desc") or "")
        parse(1, base_text)
        if (
            "发出3枚" in _plain_text(base_text)
            and "随后2枚" in _plain_text(base_text)
            and "伤害减半" in _plain_text(base_text)
            and skill_damage_components
        ):
            component = skill_damage_components[0]
            add(
                1,
                "secondary_projectile_damage",
                component.raw_value_per_hit * 0.5,
                f"{component.raw_value_per_hit}*0.5",
                "随后2枚对附近敌人造成的伤害减半",
                ("uses_current_first_projectile_value", "nearby_target_damage_excluded"),
                component.damage_type,
            )
        enhancement = skill.get("enhanceSkill")
        if not isinstance(enhancement, dict):
            continue
        for item in enhancement.get("params") or ():
            if not isinstance(item, dict) or not str(item.get("level", "")).isdigit():
                continue
            level = int(item["level"])
            text = str(item.get("desc") or "")
            parse(level, text)
            coefficient = re.search(
                r"伤害及恢复的最大生命值系数提升至([0-9]+(?:\.[0-9]+)?)%",
                _plain_text(text),
            )
            if coefficient and "能量球" in _plain_text(base_text):
                ratio = float(coefficient.group(1)) / 100.0
                add(
                    level,
                    "target_max_health_magical_damage",
                    ratio * dummy_hp,
                    f"{ratio}*target_max_health",
                    coefficient.group(0),
                    ("fixed_dummy_target_max_health", "contact_frequency_unresolved"),
                    "magical",
                )
                add(
                    level,
                    "source_max_health_healing",
                    ratio * max_health,
                    f"{ratio}*source_max_health",
                    coefficient.group(0),
                    ("source_hero_max_health", "contact_frequency_unresolved"),
                )
    return tuple(sorted(values, key=lambda item: (item.unlock_level, item.kind)))


def _basic_attack_bonus_hits(hero, fixture_level, physical):
    if str(hero.get("id")) != "5191" or fixture_level < 100:
        return (), ()
    ratio = 0.0
    for skill in hero.get("heroCard", {}).get("skillList", ()):
        enhancement = skill.get("enhanceSkill") if isinstance(skill, dict) else None
        if not isinstance(enhancement, dict):
            continue
        for item in enhancement.get("params") or ():
            if not isinstance(item, dict) or not str(item.get("level", "")).isdigit():
                continue
            if int(item["level"]) > fixture_level:
                continue
            text = _plain_text(str(item.get("desc") or ""))
            match = re.search(
                r"普攻附带([0-9]+(?:\.[0-9]+)?)%物理攻击力的真实伤害|真实伤害提升至([0-9]+(?:\.[0-9]+)?)%物理攻击力",
                text,
            )
            if match:
                ratio = float(next(value for value in match.groups() if value is not None)) / 100.0
    if ratio <= 0:
        return (), ()
    return (
        ((ratio * physical, "true"),),
        (
            "level_100_both_weapon_branches_are_deterministically_active",
            "passive_true_damage_applies_on_each_basic_attack",
            "true_damage_ignores_dummy_defenses",
        ),
    )


def _damage_breakdowns(events):
    by_type = {key: [0.0, 0] for key in ("physical", "magical", "true")}
    by_source = {key: [0.0, 0] for key in ("basic_attack", "active_skill", "equipment")}
    for event in events:
        dealt = max(0.0, event.model_applied_value)
        damage_key = event.damage_type
        if damage_key not in by_type:
            by_type[damage_key] = [0.0, 0]
        source_key = (
            "basic_attack"
            if event.event_type in {
                "basic_attack",
                "passive_basic_attack_true_damage",
                "passive_basic_attack_magical_damage",
                "passive_basic_attack_link_damage",
                "equipment_expected_critical_physical_damage",
            }
            else "active_skill"
            if event.event_type == "parsed_active_skill_damage"
            or event.event_type.startswith("active_skill_")
            or event.event_type == "equipment_expected_repeat_active_skill_damage"
            else "equipment"
        )
        by_type[damage_key][0] += dealt
        by_type[damage_key][1] += 1
        by_source[source_key][0] += dealt
        by_source[source_key][1] += 1
    total = sum(event.model_applied_value for event in events)
    build = lambda values: tuple(
        FixedDummyBreakdownEntry(key, amount, amount / total if total > 0 else 0.0, count)
        for key, (amount, count) in values.items()
    )
    return build(by_type), build(by_source)


__all__ = ["DpsFixtureInputV0", "FixedDummyDamageEngine", "FixedDummyDamageResult"]
