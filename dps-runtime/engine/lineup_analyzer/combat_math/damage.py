from __future__ import annotations

from dataclasses import dataclass

from ..user_confirmed_rules import RESISTANCE_MULTIPLIER_RULE


@dataclass(frozen=True)
class MathResult:
    value: float
    raw_value: float
    formula: str
    components: dict[str, float]
    assumptions: tuple[str, ...]
    unmodeled_items: tuple[str, ...]


def resistance_multiplier(resistance: float) -> MathResult:
    normalized = max(0.0, resistance)
    value = 40.0 / (normalized + 40.0)
    return MathResult(
        value=value,
        raw_value=normalized,
        formula="damage_multiplier=40/(max(0,resistance)+40)",
        components={"resistance": normalized},
        assumptions=(
            "negative_resistance_is_clamped_to_zero",
            RESISTANCE_MULTIPLIER_RULE.rule_id,
        ),
        unmodeled_items=(),
    )


def damage_packet(
    *,
    fixed_damage: float,
    attack_value: float,
    attack_ratio: float,
    target_max_health: float,
    target_health_ratio: float,
    resistance: float,
) -> MathResult:
    fixed = max(0.0, fixed_damage)
    attack_scaled = max(0.0, attack_value) * max(0.0, attack_ratio)
    health_scaled = max(0.0, target_max_health) * max(0.0, target_health_ratio)
    raw = fixed + attack_scaled + health_scaled
    multiplier = resistance_multiplier(resistance)
    return MathResult(
        value=raw * multiplier.value,
        raw_value=raw,
        formula=(
            "raw=fixed+attack*attack_ratio+target_max_health*health_ratio; "
            "effective=raw*resistance_multiplier"
        ),
        components={
            "fixed": fixed,
            "attack_scaled": attack_scaled,
            "target_health_scaled": health_scaled,
            "resistance_multiplier": multiplier.value,
        },
        assumptions=("all_components_share_one_damage_type_and_resistance",)
        + multiplier.assumptions,
        unmodeled_items=multiplier.unmodeled_items
        + ("rounding_order", "damage_caps_and_amplifiers"),
    )
