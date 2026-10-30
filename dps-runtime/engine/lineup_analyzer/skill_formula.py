from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SkillDamageComponent:
    fixed_damage: float
    physical_attack_ratio: float
    magical_attack_ratio: float
    hit_count: int
    damage_type: str
    source_text: str

    def raw_damage(self, physical_attack: float, magical_attack: float) -> float:
        per_hit = (
            self.fixed_damage
            + max(0.0, physical_attack) * self.physical_attack_ratio
            + max(0.0, magical_attack) * self.magical_attack_ratio
        )
        return per_hit * self.hit_count


@dataclass(frozen=True)
class SkillFormulaResult:
    status: str
    active_text: str
    components: tuple[SkillDamageComponent, ...]
    raw_damage_per_cast: float | None
    assumptions: tuple[str, ...]
    unresolved_items: tuple[str, ...]


def parse_active_skill_damage(
    description: str,
    *,
    physical_attack: float,
    magical_attack: float,
) -> SkillFormulaResult:
    text = _plain_text(description)
    has_active_marker = "主动：" in text
    if has_active_marker:
        active = text.split("主动：", 1)[1]
    elif "被动：" in text:
        return SkillFormulaResult(
            "passive_only_not_evaluated",
            "",
            (),
            None,
            (),
            ("passive_trigger_frequency",),
        )
    else:
        active = text
    attack_replacement_excluded = "攻击替换为" in active
    if attack_replacement_excluded:
        active = active.split("攻击替换为", 1)[0]
    summon_attack_excluded = bool(re.search(
        r"(?:仆从|士兵|狼魂|灵体|召唤物)[^。；]{0,60}?每次攻击[^。；]{0,30}?造成",
        active,
    ))
    if summon_attack_excluded:
        active = re.split(
            r"(?:仆从|士兵|狼魂|灵体|召唤物)[^。；]{0,60}?每次攻击",
            active,
            maxsplit=1,
        )[0]

    components = []
    unresolved = []
    mixed_spans = []
    for mixed in re.finditer(
        r"(?P<total>[0-9]+)次[^。；]{0,80}?分别造成"
        r"(?P<first>[^。；]{1,80}?伤害)和"
        r"(?P<second_count>[0-9]+)次(?P<second>[^。；]{1,80}?伤害)",
        active,
    ):
        total = int(mixed.group("total"))
        second_count = int(mixed.group("second_count"))
        first_count = total - second_count
        if first_count < 1:
            unresolved.append("mixed_damage_hit_distribution_invalid")
            continue
        for body, hit_count, source in (
            (mixed.group("first"), first_count, f"造成{mixed.group('first')}"),
            (mixed.group("second"), second_count, f"造成{mixed.group('second')}"),
        ):
            component, component_unresolved = _damage_component(
                body,
                source,
                hit_count,
            )
            unresolved.extend(component_unresolved)
            if component is not None:
                components.append(component)
        mixed_spans.append(mixed.span())

    for match in re.finditer(r"造成(?P<body>[^。；]{1,100}?)伤害", active):
        if any(start <= match.start() < end for start, end in mixed_spans):
            continue
        body = match.group("body")
        source = match.group(0)
        hit_count = _hit_count(active[max(0, match.start() - 60): match.end()])
        component, component_unresolved = _damage_component(
            body,
            source,
            hit_count,
        )
        unresolved.extend(component_unresolved)
        if component is not None:
            components.append(component)

    if "平均分摊" in active:
        unresolved.append("multi_target_damage_split")
    unique_unresolved = tuple(dict.fromkeys(unresolved))
    if not components:
        return SkillFormulaResult(
            "active_damage_unparsed" if "伤害" in active else "no_active_damage",
            active,
            (),
            None,
            tuple(dict.fromkeys(
                (("active_clause_only",) if has_active_marker else ())
                + (
                    ("summon_attack_damage_excluded_from_direct_cast",)
                    if summon_attack_excluded
                    else ()
                )
            )),
            unique_unresolved or (("no_provable_active_damage_component",) if "伤害" in active else ()),
        )
    raw = sum(
        item.raw_damage(physical_attack, magical_attack) for item in components
    )
    return SkillFormulaResult(
        "partial_active_damage" if unique_unresolved else "parsed_active_damage",
        active,
        tuple(components),
        raw,
        tuple(dict.fromkeys(
            (
                "active_clause_only",
                "listed_damage_components_are_unconditional_within_the_active_clause",
                "damage_is_before_resistance_amplifiers_crit_and_rounding",
            )
            + (
                ("persistent_basic_attack_replacement_excluded_from_cast_damage",)
                if attack_replacement_excluded
                else ()
            )
            + (
                ("summon_attack_damage_excluded_from_direct_cast",)
                if summon_attack_excluded
                else ()
            )
            + (
                ("mixed_damage_distribution_parsed_from_explicit_hit_counts",)
                if mixed_spans
                else ()
            )
            + (
                ("shorthand_damage_percentage_inferred_from_damage_type",)
                if re.search(r"[0-9]+(?:\.[0-9]+)?%\s*(?:的)?(?:物理|法术)伤害", active)
                else ()
            )
        )),
        unique_unresolved,
    )


def _plain_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _ratio(body: str, stat: str) -> float:
    match = re.search(rf"([0-9]+(?:\.[0-9]+)?)%\s*{stat}", body)
    return float(match.group(1)) / 100.0 if match else 0.0


def _fixed_value(body: str) -> float:
    plus = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*\+", body)
    if plus:
        return float(plus.group(1))
    points = re.search(r"([0-9]+(?:\.[0-9]+)?)点", body)
    return float(points.group(1)) if points else 0.0


def _damage_component(
    body: str,
    source: str,
    hit_count: int,
) -> tuple[SkillDamageComponent | None, tuple[str, ...]]:
    unresolved = []
    physical_ratio = _ratio(body, "物理攻击力")
    magical_ratio = _ratio(body, "法术攻击力")
    fixed = _fixed_value(body)
    shorthand = re.search(
        r"([0-9]+(?:\.[0-9]+)?)%\s*(?:的)?(物理|法术)(?:伤害)?",
        source,
    )
    if shorthand and not (physical_ratio or magical_ratio):
        ratio = float(shorthand.group(1)) / 100.0
        if shorthand.group(2) == "物理":
            physical_ratio = ratio
        else:
            magical_ratio = ratio
    if "最大生命值" in body:
        unresolved.append("max_health_damage_owner_or_target_unknown")
    if not (fixed or physical_ratio or magical_ratio):
        unresolved.append("unparsed_active_damage_clause")
        return None, tuple(unresolved)
    damage_type = (
        "true"
        if "真实伤害" in source
        else "physical"
        if "物理伤害" in source or physical_ratio
        else "magical"
        if "法术伤害" in source or magical_ratio
        else "unknown"
    )
    return SkillDamageComponent(
        fixed_damage=fixed,
        physical_attack_ratio=physical_ratio,
        magical_attack_ratio=magical_ratio,
        hit_count=hit_count,
        damage_type=damage_type,
        source_text=source,
    ), tuple(unresolved)


def _hit_count(context: str) -> int:
    for pattern in (
        r"([0-9]+)\s*(?:次|段|枚|支|朵|发)[^。；]{0,50}?每(?:次|段|枚|支|朵|发)[^。；]{0,30}?造成",
        r"([0-9]+)次[^。；]{0,40}?每次[^。；]{0,30}?造成",
        r"([0-9]+)枚[^。；]{0,50}?每枚造成",
        r"([0-9]+)支[^。；]{0,50}?每支[^。；]{0,12}?造成",
        r"([0-9]+)朵[^。；]{0,50}?每朵[^。；]{0,12}?造成",
    ):
        match = re.search(pattern, context)
        if match:
            return max(1, int(match.group(1)))
    return 1


__all__ = [
    "SkillDamageComponent",
    "SkillFormulaResult",
    "parse_active_skill_damage",
]
