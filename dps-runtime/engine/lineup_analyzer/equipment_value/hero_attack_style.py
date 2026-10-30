"""Traceable attack-style resolution for equipment wearer gates.

The official hero card exposes ``attackDistance`` but not a separate melee/ranged
flag. Distance one is treated as melee and positive longer ranges as ranged,
except for the two confirmed distance-two melee records. Those exceptions are
an explicit model-profile layer rather than a fabricated official field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ATTACK_STYLE_MODEL_VERSION = "equipment-hero-attack-style-v1"
_CONFIRMED_DISTANCE_TWO_MELEE_IDS = frozenset({"1211", "1951"})


@dataclass(frozen=True)
class HeroAttackStyle:
    style_id: str
    label: str
    attack_distance: int | None
    source_layers: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    model_version: str = ATTACK_STYLE_MODEL_VERSION

    @property
    def is_ranged(self) -> bool:
        return self.style_id == "ranged"


def resolve_hero_attack_style(raw_hero: dict[str, Any]) -> HeroAttackStyle:
    """Resolve only the wearer gate needed by cards such as 日渊."""

    hero_id = str(raw_hero.get("id") or "")
    properties = ((raw_hero.get("heroCard") or {}).get("properties") or {})
    raw_distance = properties.get("attackDistance")
    try:
        attack_distance = int(raw_distance)
    except (TypeError, ValueError):
        attack_distance = None
    evidence_ids = (f"official-raw:hero:{hero_id}:attack-distance",) if hero_id else ()
    if attack_distance is None or attack_distance <= 0:
        return HeroAttackStyle(
            "unresolved",
            "攻击方式待确认",
            attack_distance,
            ("official_raw",),
            evidence_ids,
            ("official_attack_distance_missing_or_nonpositive",),
        )
    if hero_id in _CONFIRMED_DISTANCE_TWO_MELEE_IDS:
        return HeroAttackStyle(
            "melee",
            "近战",
            attack_distance,
            ("official_raw", "model_profile"),
            evidence_ids,
            ("confirmed_distance_two_melee_exception",),
        )
    return HeroAttackStyle(
        "melee" if attack_distance == 1 else "ranged",
        "近战" if attack_distance == 1 else "远程",
        attack_distance,
        ("official_raw",),
        evidence_ids,
        ("official_attack_distance_gate",),
    )


__all__ = [
    "ATTACK_STYLE_MODEL_VERSION",
    "HeroAttackStyle",
    "resolve_hero_attack_style",
]
