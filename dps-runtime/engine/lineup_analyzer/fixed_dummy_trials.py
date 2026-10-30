"""Server-side fixture trials built on top of the fixed dummy damage run.

The lab has three deliberately separate questions: generated damage events,
static incoming-damage capacity, and declared action-lock coverage.  The
second and third questions do not turn into a battle simulator or a score.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .combat_math.damage import resistance_multiplier
from .combat_math.survivability import static_ehp
from .fixed_dummy_damage import DpsFixtureInputV0, FixedDummyDamageEngine


TRIAL_SCHEMA_VERSION = "fixed-dummy-trial-result-v2"
_TRIAL_KINDS = frozenset({"damage", "durability", "control"})
_PRESSURE_PROFILES = {
    "physical": ("物理来伤", 1.0, 0.0),
    "magical": ("法术来伤", 0.0, 1.0),
    "mixed": ("混合来伤", 0.5, 0.5),
}
_CONTROL_DUMMY_PROFILES = {
    "periodic_stun": {
        "label": "眩晕木桩",
        "control_type": "stun",
        "first_seconds": 3.0,
        "interval_seconds": 5.0,
        "duration_seconds": 1.0,
        "summary": "第3秒开始每5秒眩晕输出棋子1秒。",
    },
    "periodic_silence": {
        "label": "沉默木桩",
        "control_type": "silence",
        "first_seconds": 3.0,
        "interval_seconds": 5.0,
        "duration_seconds": 1.0,
        "summary": "第3秒开始每5秒沉默输出棋子1秒，只拦截主动施法。",
    },
    "periodic_disarm": {
        "label": "缴械木桩",
        "control_type": "disarm",
        "first_seconds": 3.0,
        "interval_seconds": 5.0,
        "duration_seconds": 1.0,
        "summary": "第3秒开始每5秒缴械输出棋子1秒，只拦截普攻。",
    },
}
_LEGACY_CONTROL_PROFILE_ALIASES = {
    "shooter": "periodic_stun",
    "caster": "periodic_silence",
    "skirmisher": "periodic_disarm",
}
_CONTROL_LABELS = {
    "stun": "眩晕",
    "freeze": "冻结",
    "knockup": "击飞",
    "suppress": "压制",
    "root": "定身",
    "silence": "沉默",
    "disarm": "缴械",
}
_FIERY_RULER_ID = "equipment:643803"
_FIERY_RULER_IMMUNITY_SECONDS = 15.0
@dataclass(frozen=True)
class FixedDummyTrialInputV1:
    fixture: DpsFixtureInputV0
    trial_kind: str
    pressure_profile_id: str
    control_dummy_profile_id: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FixedDummyTrialInputV1":
        allowed = {
            "hero_id",
            "fixture_level",
            "equipment_instance_ids",
            "dummy_hp",
            "dummy_physical_defense",
            "dummy_magical_defense",
            "horizon_seconds",
            "coverage_mode",
            "awakening_mode",
            "maximum_mana_override",
            "dummy_equipment_instance_ids",
            "trial_kind",
            "pressure_profile_id",
            "control_dummy_profile_id",
            "control_target_profile_id",
        }
        unknown = set(value).difference(allowed)
        if unknown:
            raise ValueError("fixed dummy trial input rejects: " + ", ".join(sorted(unknown)))
        kind = str(value.get("trial_kind", "damage"))
        if kind not in _TRIAL_KINDS:
            raise ValueError("trial_kind must be damage, durability, or control")
        pressure = str(value.get("pressure_profile_id", "mixed"))
        if pressure not in _PRESSURE_PROFILES:
            raise ValueError("pressure_profile_id is not supported")
        control_dummy = value.get("control_dummy_profile_id")
        legacy_control_target = value.get("control_target_profile_id")
        if control_dummy is not None and legacy_control_target is not None:
            raise ValueError("control_dummy_profile_id and control_target_profile_id cannot be used together")
        if control_dummy is None and legacy_control_target is not None:
            control_dummy = _LEGACY_CONTROL_PROFILE_ALIASES.get(str(legacy_control_target))
        control_dummy = str(control_dummy or "periodic_stun")
        if control_dummy not in _CONTROL_DUMMY_PROFILES:
            raise ValueError("control_dummy_profile_id is not supported")
        fixture_payload = {key: item for key, item in value.items() if key in allowed - {"trial_kind", "pressure_profile_id", "control_dummy_profile_id", "control_target_profile_id"}}
        return cls(DpsFixtureInputV0.from_dict(fixture_payload), kind, pressure, control_dummy)

    def to_dict(self) -> dict[str, object]:
        return {
            **self.fixture.to_dict(),
            "trial_kind": self.trial_kind,
            "pressure_profile_id": self.pressure_profile_id,
            "control_dummy_profile_id": self.control_dummy_profile_id,
        }


@dataclass(frozen=True)
class FixedDummyTrialResult:
    validated_input: FixedDummyTrialInputV1
    damage_run: dict[str, object] | None
    supporting_context: dict[str, object] | None
    trial: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        context = self.damage_run if self.damage_run is not None else self.supporting_context or {}
        value = {
            "schema_version": TRIAL_SCHEMA_VERSION,
            "validated_input": self.validated_input.to_dict(),
            "trial": self.trial,
            "evidence_ids": tuple(dict.fromkeys(
                tuple(context.get("evidence_ids", ())) + tuple(self.trial.get("evidence_ids", ()))
            )),
            "assumptions": tuple(dict.fromkeys(
                tuple(context.get("assumptions", ())) + tuple(self.trial.get("assumptions", ()))
            )),
            "excluded_components": tuple(dict.fromkeys(
                tuple(context.get("excluded_components", ())) + tuple(self.trial.get("excluded_components", ()))
            )),
            "unresolved_items": tuple(dict.fromkeys(
                tuple(context.get("unresolved_items", ())) + tuple(self.trial.get("unresolved_items", ()))
            )),
            "comparison_eligible": False,
        }
        if self.damage_run is not None:
            value["damage_run"] = self.damage_run
        if self.supporting_context is not None:
            value["supporting_context"] = self.supporting_context
        return value


class FixedDummyTrialEngine:
    """Builds each fixture trial from one authoritative damage-engine run."""

    def __init__(self, source_root: Path) -> None:
        self.source_root = Path(source_root)
        self.damage_engine = FixedDummyDamageEngine(self.source_root)

    def run(self, value: FixedDummyTrialInputV1) -> FixedDummyTrialResult:
        if value.trial_kind == "durability":
            supporting_context = self.damage_engine.supporting_context(value.fixture)
            trial = _durability_trial(value, supporting_context)
            return FixedDummyTrialResult(value, None, supporting_context, trial)
        if value.trial_kind == "control":
            control_fixture = replace(value.fixture, dummy_hp=1_000_000_000.0)
            control_source_run = self.damage_engine.run(control_fixture).to_dict()
            trial = _control_trial(value, control_source_run)
            return FixedDummyTrialResult(value, None, _supporting_context(control_source_run), trial)
        damage_run = self.damage_engine.run(value.fixture).to_dict()
        trial = _damage_trial(value, damage_run)
        return FixedDummyTrialResult(value, damage_run, None, trial)

def trial_profiles() -> dict[str, tuple[dict[str, object], ...]]:
    return {
        "kinds": (
            {
                "id": "damage",
                "label": "伤害计算",
                "summary": "固定单目标；设置生命和双抗，记录已生成的伤害事件。",
            },
            {
                "id": "durability",
                "label": "承伤估算",
                "summary": "按当前生命和双抗，估算能承受多少减伤前的伤害。",
            },
            {
                "id": "control",
                "label": "控制覆盖",
                "summary": "控制木桩作用于当前输出棋子，查看已生成事件如何被拦下。",
            },
        ),
        "pressure": tuple(
            {"id": key, "label": label, "physical_share": physical, "magical_share": magical}
            for key, (label, physical, magical) in _PRESSURE_PROFILES.items()
        ),
        "control_dummies": tuple(
            {"id": key, "label": str(profile["label"]), "summary": str(profile["summary"])}
            for key, profile in _CONTROL_DUMMY_PROFILES.items()
        ),
    }


def _damage_trial(value: FixedDummyTrialInputV1, damage_run: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "fixed-dummy-damage-trial-v1",
        "kind": "damage",
        "status": "generated_trace",
        "title": "伤害计算",
        "summary": "当前已生成事件对固定单目标造成的伤害；不等同实战 DPS。",
        "metrics": {
            "modeled_damage": damage_run["total_model_damage"],
            "unmitigated_modeled_damage": damage_run["unmitigated_model_damage"],
            "event_count": len(damage_run["events"]),
        },
        "assumptions": ("uses_same_fixed_dummy_damage_run",),
        "excluded_components": (),
        "unresolved_items": (),
    }


def _supporting_context(damage_run: dict[str, object]) -> dict[str, object]:
    stats = tuple(damage_run["derived_hero_stats"])
    equipment = tuple(damage_run["equipment_contributions"])
    target_equipment = tuple(damage_run.get("target_equipment_effects", ()))
    growth = dict(damage_run["growth_resolution"])
    evidence_ids = tuple(dict.fromkeys(
        evidence_id
        for item in (*stats, *equipment, *target_equipment)
        for evidence_id in item.get("evidence_ids", (item.get("evidence_id"),))
        if evidence_id
    )) + tuple(
        evidence_id
        for evidence_id in growth.get("evidence_ids", ())
        if evidence_id
    )
    return {
        "schema_version": "fixed-dummy-trial-supporting-context-v1",
        "derived_hero_stats": stats,
        "equipment_contributions": equipment,
        "target_equipment_effects": target_equipment,
        "growth_resolution": growth,
        "growth_axes": tuple(damage_run["growth_axes"]),
        "evidence_ids": tuple(dict.fromkeys(evidence_ids)),
        "assumptions": (
            "mathematical_fixture_level_not_valid_for_p5_or_p6",
            "supporting_context_contains_derived_properties_only",
            *tuple(growth.get("assumptions", ())),
        ),
        "excluded_components": tuple(
            item for item in damage_run["excluded_components"]
            if str(item).startswith("equipment_")
        ),
        "unresolved_items": tuple(growth.get("unresolved_items", ())),
    }


def _durability_trial(value: FixedDummyTrialInputV1, damage_run: dict[str, object]) -> dict[str, object]:
    stats = _stats_by_name(damage_run)
    health = stats["max_health_with_equipment"]
    physical_defense = stats["physical_defense_with_equipment"]
    magical_defense = stats["magical_defense_with_equipment"]
    physical = static_ehp(health, physical_defense)
    magical = static_ehp(health, magical_defense)
    label, physical_share, magical_share = _PRESSURE_PROFILES[value.pressure_profile_id]
    physical_multiplier = resistance_multiplier(physical_defense)
    magical_multiplier = resistance_multiplier(magical_defense)
    blended_multiplier = physical_share * physical_multiplier.value + magical_share * magical_multiplier.value
    target_equipment_ids = _target_equipment_ids(damage_run)
    physical_capacity = _target_adjusted_raw_capacity(health, physical_multiplier.value, target_equipment_ids)
    magical_capacity = _target_adjusted_raw_capacity(health, magical_multiplier.value, target_equipment_ids)
    raw_capacity = _target_adjusted_raw_capacity(health, blended_multiplier, target_equipment_ids)
    curve = _remaining_health_curve(health, blended_multiplier, target_equipment_ids)
    static_exclusions = _target_equipment_static_capacity_exclusions(target_equipment_ids)
    evidence_ids = _stat_evidence(damage_run, {
        "max_health_with_equipment", "physical_defense_with_equipment", "magical_defense_with_equipment"
    })
    return {
        "schema_version": "fixed-dummy-durability-trial-v1",
        "kind": "durability",
        "status": "static_capacity_derived",
        "title": "承伤估算",
        "summary": f"面对{label}，按当前生命和双抗，约能承受 {raw_capacity:g} 点减伤前伤害。",
        "profile": {
            "id": value.pressure_profile_id,
            "label": label,
            "physical_share": physical_share,
            "magical_share": magical_share,
        },
        "metrics": {
            "max_health": health,
            "physical_defense": physical_defense,
            "magical_defense": magical_defense,
            "physical_damage_multiplier": physical_multiplier.value,
            "magical_damage_multiplier": magical_multiplier.value,
            "physical_damage_multiplier_percent": physical_multiplier.value * 100.0,
            "magical_damage_multiplier_percent": magical_multiplier.value * 100.0,
            "physical_effective_health": physical_capacity,
            "magical_effective_health": magical_capacity,
            "selected_pressure_raw_capacity": raw_capacity,
        },
        "visualization": {
            "kind": "incoming_damage_capacity_flow",
            "capacity_chart": {
                "selected_lane_id": value.pressure_profile_id,
                "lanes": (
                    _capacity_chart_lane("physical", "物理来伤", physical_capacity, physical_multiplier.value, health),
                    _capacity_chart_lane("magical", "法术来伤", magical_capacity, magical_multiplier.value, health),
                    _capacity_chart_lane("mixed", "混合来伤", raw_capacity, blended_multiplier, health),
                ),
            },
            "remaining_health_curve": curve,
        },
        "formulae": (
            {"label": "物理承伤", "formula": _target_capacity_formula(physical.formula, target_equipment_ids)},
            {"label": "法术承伤", "formula": _target_capacity_formula(magical.formula, target_equipment_ids)},
            {"label": "混合承伤", "formula": _target_capacity_formula("max_health/(physical_share*physical_multiplier+magical_share*magical_multiplier)", target_equipment_ids)},
        ),
        "evidence_ids": evidence_ids,
        "assumptions": (
            "static_single_target_incoming_damage_capacity",
            "pressure_profile_mix_is_a_mathematical_fixture",
            "no_healing_shield_damage_reduction_or_control_timing",
            *(
                ("target_equipment:643501:above_70_percent_damage_reduction_in_capacity_curve",)
                if "equipment:643501" in target_equipment_ids
                else ()
            ),
        ),
        "excluded_components": (
            "skill_shields_and_healing_not_applied_to_static_capacity",
            "enemy_attack_schedule_and_damage_not_simulated",
            "death_and_overkill_not_simulated",
            *static_exclusions,
        ),
        "unresolved_items": ("incoming_damage_timing_and_source_profile",),
        "comparison_eligible": False,
    }


def _control_trial(
    value: FixedDummyTrialInputV1,
    damage_run: dict[str, object],
) -> dict[str, object]:
    controller = _CONTROL_DUMMY_PROFILES[value.control_dummy_profile_id]
    control_events = list(_control_dummy_events(value, controller))
    control_timeline = _control_timeline(
        damage_run,
        tuple(control_events),
        value.fixture.horizon_seconds,
        value.fixture.hero_id,
    )
    source_events = control_timeline["source_events"]
    for control_event in control_events:
        blocked = [
            event for event in source_events
            if str(control_event["event_id"]) in event["blocked_by_control_event_ids"]
        ]
        control_event["blocked_basic_attack_events"] = sum(
            1 for event in blocked if event["action_kind"] == "basic_attack" and event["is_primary_action"]
        )
        control_event["blocked_skill_cast_events"] = sum(
            1 for event in blocked if event["action_kind"] == "active_skill" and event["is_primary_action"]
        )
        control_event["blocked_model_damage"] = sum(float(event["model_output_value"]) for event in blocked)
    output_curve = _control_model_output_curve(control_timeline)
    has_fiery_ruler = _FIERY_RULER_ID in value.fixture.equipment_instance_ids
    declared_action_lock = sum(float(item["declared_duration_seconds"]) for item in control_events)
    action_lock = sum(float(item["duration_seconds"]) for item in control_events)
    prevented_control = sum(float(item["prevented_duration_seconds"]) for item in control_events)
    fiery_trigger = next(
        (item for item in control_events if item["resolution_status"] == "applied_and_triggered_immunity"),
        None,
    )
    control_mitigation = {
        "status": "triggered" if fiery_trigger is not None else "equipped_not_triggered" if has_fiery_ruler else "not_equipped",
        "source_equipment_id": _FIERY_RULER_ID if has_fiery_ruler else None,
        "label": "炽热支配者" if has_fiery_ruler else None,
        "trigger_time": float(fiery_trigger["time"]) if fiery_trigger is not None else None,
        "immunity_start_time": float(fiery_trigger["immunity_start_time"]) if fiery_trigger is not None else None,
        "immunity_end_time_exclusive": float(fiery_trigger["immunity_end_time_exclusive"]) if fiery_trigger is not None else None,
        "immunity_duration_seconds": _FIERY_RULER_IMMUNITY_SECONDS if fiery_trigger is not None else 0.0,
        "prevented_control_event_count": sum(
            1 for item in control_events if item["resolution_status"] == "prevented_by_control_immunity"
        ),
        "suppression_is_not_prevented": True if has_fiery_ruler else None,
    }
    blocked_basic = sum(float(event["blocked_basic_attack_events"]) for event in control_events)
    blocked_skill = sum(float(event["blocked_skill_cast_events"]) for event in control_events)
    blocked_damage = sum(
        float(event["model_output_value"])
        for event in source_events
        if event["status"] == "blocked"
    )
    status = "action_lock_coverage_derived" if any(event["status"] == "blocked" for event in source_events) else "no_source_action_covered"
    return {
        "schema_version": "fixed-dummy-control-trial-v3",
        "kind": "control",
        "status": status,
        "title": "控制覆盖",
        "summary": _control_trial_summary(
            str(controller["label"]), status, blocked_basic, blocked_skill, action_lock, prevented_control,
        ),
        "controller_profile": {
            "id": value.control_dummy_profile_id,
            "label": controller["label"],
            "summary": controller["summary"],
            "control_type": controller["control_type"],
        },
        "metrics": {
            "control_event_count": len(control_events),
            "effective_control_event_count": sum(1 for item in control_events if float(item["duration_seconds"]) > 0),
            "prevented_control_event_count": sum(1 for item in control_events if float(item["prevented_duration_seconds"]) > 0),
            "blocked_basic_attack_events": blocked_basic,
            "blocked_skill_cast_events": blocked_skill,
            "declared_action_lock_seconds": declared_action_lock,
            "action_lock_seconds": action_lock,
            "prevented_control_seconds": prevented_control,
            "source_event_count": len(source_events),
            "blocked_damage_event_count": sum(1 for event in source_events if event["status"] == "blocked"),
            "blocked_model_damage": blocked_damage,
            "baseline_model_damage": output_curve["baseline_cumulative"][-1]["value"],
            "controlled_model_damage": output_curve["controlled_cumulative"][-1]["value"],
        },
        "control_mitigation": control_mitigation,
        "control_events": tuple(control_events),
        "visualization": {
            "kind": "control_dummy_on_source_damage_trace",
            "control_timeline": control_timeline,
            "model_output_curve": output_curve,
        },
        "evidence_ids": (
            "model:fixed-dummy-control-dummy-v1",
            *((f"official-raw:{_FIERY_RULER_ID}:desc",) if has_fiery_ruler else ()),
        ),
        "assumptions": (
            "control_dummy_targets_selected_output_hero",
            "declared_control_dummy_schedule",
            "control_blocks_only_resolved_source_basic_attack_or_active_cast_events",
            "fiery_ruler_immunity_window_is_half_open_and_does_not_cancel_triggering_control"
            if has_fiery_ruler else "no_equipment_control_immunity_rule_active",
            "control_schedule_uses_nonlethal_source_run",
        ),
        "excluded_components": (
            "control_dummy_deals_no_damage",
            "control_does_not_reschedule_mana_or_future_cast_timing",
            "already_scheduled_projectile_periodic_clone_and_summon_damage_not_cancelled",
            "control_resistance_other_immunity_cleanse_knockback_distance_movement_and_retargeting",
            *(("equipment:643803:shield_300_not_applied_to_control_output_curve",) if has_fiery_ruler else ()),
        ),
        "unresolved_items": (
            "control_action_delay_and_cast_interruption_recovery_not_fully_modeled",
        ),
        "comparison_eligible": False,
    }


def _control_trial_summary(
    controller_label: str,
    status: str,
    blocked_basic: float,
    blocked_skill: float,
    action_lock: float,
    prevented_control: float,
) -> str:
    if status != "action_lock_coverage_derived":
        if prevented_control > 0:
            return f"{controller_label}已按声明时间尝试控制；{prevented_control:g}秒被免疫，当前没有其他可拦下动作。"
        return "控制木桩已按声明时间施加控制，但当前输出棋子没有可被该控制类型拦下的已生成动作。"
    mitigation = f"{prevented_control:g}秒控制被免疫，实际控制{action_lock:g}秒；" if prevented_control > 0 else ""
    return (
        f"{controller_label}会作用于当前输出棋子：{mitigation}"
        f"在已生成事件中拦下 {blocked_basic:g} 次普攻、{blocked_skill:g} 次主动施法。"
    )


def _capacity_chart_lane(
    lane_id: str,
    label: str,
    raw_capacity: float,
    damage_multiplier: float,
    surviving_health: float,
) -> dict[str, object]:
    return {
        "id": lane_id,
        "label": label,
        "raw_capacity": raw_capacity,
        "post_mitigation_value": surviving_health,
        "damage_pass_through_percent": damage_multiplier * 100.0,
        "damage_reduction_percent": (1.0 - damage_multiplier) * 100.0,
    }


def _target_equipment_ids(damage_run: dict[str, object]) -> frozenset[str]:
    return frozenset(
        str(item["equipment_id"])
        for item in damage_run.get("target_equipment_effects", ())
        if isinstance(item, dict) and item.get("equipment_id")
    )


def _target_adjusted_raw_capacity(
    health: float,
    damage_multiplier: float,
    target_equipment_ids: frozenset[str],
) -> float:
    if damage_multiplier <= 0:
        return 0.0
    if "equipment:643501" not in target_equipment_ids:
        return health / damage_multiplier
    # 霸者重铠 applies while the pre-hit target HP remains above 70%.
    return 0.30 * health / (damage_multiplier * 0.60) + 0.70 * health / damage_multiplier


def _remaining_health_curve(
    health: float,
    damage_multiplier: float,
    target_equipment_ids: frozenset[str],
) -> tuple[dict[str, float], ...]:
    if damage_multiplier <= 0:
        return ({"raw_incoming_damage": 0.0, "remaining_health": health},)
    if "equipment:643501" not in target_equipment_ids:
        capacity = health / damage_multiplier
        return tuple(
            {
                "raw_incoming_damage": capacity * ratio,
                "remaining_health": max(0.0, health - capacity * ratio * damage_multiplier),
            }
            for ratio in (0.0, 0.25, 0.50, 0.75, 1.0)
        )
    threshold_raw = 0.30 * health / (damage_multiplier * 0.60)
    final_raw = threshold_raw + 0.70 * health / damage_multiplier
    values = (0.0, threshold_raw * 0.5, threshold_raw, threshold_raw + (final_raw - threshold_raw) * 0.5, final_raw)
    return tuple(
        {
            "raw_incoming_damage": raw,
            "remaining_health": (
                max(0.0, health - raw * damage_multiplier * 0.60)
                if raw <= threshold_raw + 1e-9
                else max(0.0, 0.70 * health - (raw - threshold_raw) * damage_multiplier)
            ),
        }
        for raw in values
    )


def _target_capacity_formula(base_formula: str, target_equipment_ids: frozenset[str]) -> str:
    if "equipment:643501" not in target_equipment_ids:
        return base_formula
    return f"{base_formula}; above_70_percent_hp_target_damage_multiplier=0.60"


def _target_equipment_static_capacity_exclusions(target_equipment_ids: frozenset[str]) -> tuple[str, ...]:
    excluded: list[str] = []
    if "equipment:643601" in target_equipment_ids:
        excluded.append("target_equipment:643601:ordinary_attack_only_not_applied_to_untyped_static_capacity")
    if "equipment:643602" in target_equipment_ids:
        excluded.append("target_equipment:643602:requires_attacker_action_schedule_not_applied_to_static_capacity")
    return tuple(excluded)


def _control_dummy_events(
    value: FixedDummyTrialInputV1,
    controller: dict[str, object],
) -> tuple[dict[str, object], ...]:
    horizon = value.fixture.horizon_seconds
    has_fiery_ruler = _FIERY_RULER_ID in value.fixture.equipment_instance_ids
    immunity_start: float | None = None
    immunity_end: float | None = None
    events: list[dict[str, object]] = []
    for index, timestamp in enumerate(
        (time for time in _times(float(controller["first_seconds"]), float(controller["interval_seconds"]), horizon) if time < horizon),
        start=1,
    ):
        declared_duration = float(controller["duration_seconds"])
        control_type = str(controller["control_type"])
        prevented = (
            has_fiery_ruler
            and control_type != "suppress"
            and immunity_start is not None
            and immunity_end is not None
            and immunity_start <= timestamp < immunity_end
        )
        triggered_immunity = has_fiery_ruler and immunity_start is None
        if triggered_immunity:
            immunity_start = timestamp
            immunity_end = timestamp + _FIERY_RULER_IMMUNITY_SECONDS
        resolution_status = (
            "prevented_by_control_immunity"
            if prevented
            else "applied_and_triggered_immunity"
            if triggered_immunity
            else "applied"
        )
        events.append({
            "event_id": f"control-dummy:{value.control_dummy_profile_id}:{index:03d}",
            "time": timestamp,
            "declared_duration_seconds": declared_duration,
            "duration_seconds": 0.0 if prevented else declared_duration,
            "prevented_duration_seconds": declared_duration if prevented else 0.0,
            "control_type": control_type,
            "label": _CONTROL_LABELS[control_type],
            "source_id": "fixture:control-dummy",
            "target_id": "fixture:hero",
            "status": "prevented" if prevented else "applied",
            "resolution_status": resolution_status,
            "immunity_start_time": immunity_start if triggered_immunity else None,
            "immunity_end_time_exclusive": immunity_end if triggered_immunity else None,
            "evidence_ids": (
                "model:fixed-dummy-control-dummy-v1",
                *((f"official-raw:{_FIERY_RULER_ID}:desc",) if has_fiery_ruler else ()),
            ),
            "assumptions": (
                "declared_control_dummy_schedule",
                "control_dummy_targets_selected_output_hero",
                "control_schedule_uses_nonlethal_source_run",
                *(("fiery_ruler_immunity_window_is_half_open",) if has_fiery_ruler else ()),
            ),
            "unresolved_items": (
                *(("equipment:643803:shield_300_not_applied_to_control_output_curve",) if has_fiery_ruler else ()),
            ),
        })
    return tuple(events)


def _control_timeline(
    damage_run: dict[str, object],
    control_events: tuple[dict[str, object], ...],
    horizon: float,
    hero_id: str,
) -> dict[str, object]:
    windows = tuple(
        {
            "event_id": str(event["event_id"]),
            "label": str(event["label"]),
            "control_type": str(event["control_type"]),
            "start_seconds": float(event["time"]),
            "declared_duration_seconds": float(event["declared_duration_seconds"]),
            "duration_seconds": float(event["duration_seconds"]),
            "prevented_duration_seconds": float(event["prevented_duration_seconds"]),
            "resolution_status": str(event["resolution_status"]),
            "start_percent": float(event["time"]) / horizon * 100.0,
            "width_percent": min(float(event["declared_duration_seconds"]), horizon - float(event["time"])) / horizon * 100.0,
            "effective_width_percent": min(float(event["duration_seconds"]), horizon - float(event["time"])) / horizon * 100.0,
        }
        for event in control_events
    )
    immunity_windows = tuple(
        {
            "source_equipment_id": _FIERY_RULER_ID,
            "start_seconds": float(event["immunity_start_time"]),
            "end_seconds_exclusive": min(float(event["immunity_end_time_exclusive"]), horizon),
            "start_percent": float(event["immunity_start_time"]) / horizon * 100.0,
            "width_percent": max(0.0, min(float(event["immunity_end_time_exclusive"]), horizon) - float(event["immunity_start_time"])) / horizon * 100.0,
            "suppression_is_not_prevented": True,
        }
        for event in control_events
        if event["resolution_status"] == "applied_and_triggered_immunity"
        and float(event["immunity_start_time"]) < horizon
    )
    source_events = []
    for event in damage_run["events"]:
        action_kind, is_primary_action = _source_action_kind(event, hero_id)
        blocked_by = tuple(
            window["event_id"]
            for window in windows
            if _control_blocks_action(str(window["control_type"]), action_kind)
            and window["start_seconds"] <= float(event["time"]) < window["start_seconds"] + window["duration_seconds"]
        )
        source_events.append({
            "event_id": str(event["event_id"]),
            "time": float(event["time"]),
            "event_type": str(event["event_type"]),
            "source_id": str(event["source_id"]),
            "action_kind": action_kind,
            "is_primary_action": is_primary_action,
            "label": _source_action_label(action_kind, str(event["event_type"]), hero_id),
            "model_output_value": float(event["model_applied_value"]),
            "position_percent": float(event["time"]) / horizon * 100.0,
            "blocked_by_control_event_ids": blocked_by,
            "status": "blocked" if blocked_by else "available" if action_kind in {"basic_attack", "active_skill"} else "not_affected",
        })
    return {
        "horizon_seconds": horizon,
        "control_windows": windows,
        "immunity_windows": immunity_windows,
        "source_events": tuple(source_events),
    }


def _source_action_kind(event: dict[str, object], hero_id: str) -> tuple[str, bool]:
    event_type = str(event["event_type"])
    phase = str(event.get("phase") or "")
    if event_type in {"basic_attack", "equipment_rapid_basic_attack"}:
        return "basic_attack", True
    if phase == "basic_attack" or "basic_attack" in event_type:
        return "basic_attack", False
    if event_type == "parsed_active_skill_damage" or phase == "active_cast":
        return "active_skill", True
    return "persistent_or_auxiliary", False


def _source_action_label(action_kind: str, event_type: str, hero_id: str) -> str:
    if hero_id == "hero:5371" and event_type == "passive_basic_attack_magical_damage":
        return "闪电链"
    if action_kind == "basic_attack":
        return "普攻" if event_type == "basic_attack" else "普攻附带效果"
    if action_kind == "active_skill":
        return "主动施法"
    return "已排程后续效果"


def _control_blocks_action(control_type: str, action_kind: str) -> bool:
    if control_type in {"stun", "freeze", "knockup", "suppress"}:
        return action_kind in {"basic_attack", "active_skill"}
    if control_type == "silence":
        return action_kind == "active_skill"
    if control_type == "disarm":
        return action_kind == "basic_attack"
    return False


def _control_model_output_curve(control_timeline: dict[str, object]) -> dict[str, object]:
    horizon = float(control_timeline["horizon_seconds"])
    baseline = 0.0
    controlled = 0.0
    baseline_steps: list[dict[str, float]] = [{"time": 0.0, "value": 0.0}]
    controlled_steps: list[dict[str, float]] = [{"time": 0.0, "value": 0.0}]
    for event in control_timeline["source_events"]:
        amount = float(event["model_output_value"])
        baseline += amount
        if event["status"] != "blocked":
            controlled += amount
        baseline_steps.append({"time": float(event["time"]), "value": baseline})
        controlled_steps.append({"time": float(event["time"]), "value": controlled})
    if baseline_steps[-1]["time"] < horizon:
        baseline_steps.append({"time": horizon, "value": baseline})
        controlled_steps.append({"time": horizon, "value": controlled})
    return {
        "throughput_label": "已生成事件的累计模型伤害",
        "value_unit": "减伤后模型伤害",
        "baseline_cumulative": tuple(baseline_steps),
        "controlled_cumulative": tuple(controlled_steps),
    }


def _stats_by_name(damage_run: dict[str, object]) -> dict[str, float]:
    values = {
        str(item["name"]): float(item["value"])
        for item in damage_run["derived_hero_stats"]
    }
    required = {"max_health_with_equipment", "physical_defense_with_equipment", "magical_defense_with_equipment", "attack_speed_with_equipment", "initial_mana_with_equipment", "maximum_mana_with_equipment"}
    missing = required.difference(values)
    if missing:
        raise ValueError("trial requires derived hero stats: " + ", ".join(sorted(missing)))
    return values


def _stat_evidence(damage_run: dict[str, object], names: set[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        evidence_id
        for stat in damage_run["derived_hero_stats"]
        if stat["name"] in names
        for evidence_id in stat["evidence_ids"]
    ))


def _times(first: float, interval: float, horizon: float) -> tuple[float, ...]:
    if interval <= 0:
        return ()
    values: list[float] = []
    time = first
    while time <= horizon + 1e-9:
        values.append(round(time, 6))
        time += interval
    return tuple(values)


__all__ = [
    "FixedDummyTrialEngine",
    "FixedDummyTrialInputV1",
    "FixedDummyTrialResult",
    "TRIAL_SCHEMA_VERSION",
    "trial_profiles",
]
