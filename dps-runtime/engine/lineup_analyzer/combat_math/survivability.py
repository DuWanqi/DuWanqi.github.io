from __future__ import annotations

from .damage import MathResult, resistance_multiplier


def static_ehp(health: float, resistance: float, shield: float = 0.0) -> MathResult:
    hp = max(0.0, health)
    shield_value = max(0.0, shield)
    multiplier = resistance_multiplier(resistance)
    value = (hp + shield_value) / multiplier.value
    return MathResult(
        value=value,
        raw_value=hp + shield_value,
        formula="static_ehp=(health+shield)/damage_multiplier",
        components={"health": hp, "shield": shield_value},
        assumptions=("shield_uses_the_same_resistance_as_health",),
        unmodeled_items=multiplier.unmodeled_items + ("shield_expiry_and_order",),
    )


def dynamic_survival(
    *,
    health: float,
    resistance: float,
    shield: float,
    healing_events: tuple[float, ...],
    healing_reduction: float,
) -> MathResult:
    static = static_ehp(health, resistance, shield)
    reduction = min(1.0, max(0.0, healing_reduction))
    effective_healing = sum(max(0.0, item) for item in healing_events) * (1.0 - reduction)
    multiplier = resistance_multiplier(resistance)
    return MathResult(
        value=static.value + effective_healing / multiplier.value,
        raw_value=static.raw_value + effective_healing,
        formula="dynamic_survival=static_ehp+effective_healing/damage_multiplier",
        components={
            "static_ehp": static.value,
            "effective_healing": effective_healing,
            "healing_reduction": reduction,
        },
        assumptions=("all_healing_lands_before_lethal_damage",),
        unmodeled_items=tuple(
            dict.fromkeys(static.unmodeled_items + ("healing_timing_and_overheal",))
        ),
    )
