from __future__ import annotations

import re

from .models import EvidenceFragment, ParsedAttribute, PassiveAssessment


_STATIC_PATTERNS = (
    ("max_health_percent", r"(?:增加|获得)\s*([+-]?\d+(?:\.\d+)?)%\s*(?:最大)?生命值", "%"),
    ("max_health_percent", r"最大生命值\s*([+-]\d+(?:\.\d+)?)%", "%"),
    ("max_health_flat", r"(?:最大)?生命值\s*([+-]\d+(?:\.\d+)?)(?![\d.%])点?", "point"),
    ("physical_attack_percent", r"(?:基础)?物理攻击力\s*([+-]\d+(?:\.\d+)?)%", "%"),
    ("physical_attack_flat", r"物理攻击力\s*([+-]\d+(?:\.\d+)?)(?![\d.%])点?", "point"),
    ("magical_attack_percent", r"法术攻击力\s*([+-]\d+(?:\.\d+)?)%", "%"),
    ("magical_attack_flat", r"法术攻击力\s*([+-]\d+(?:\.\d+)?)(?![\d.%])点?", "point"),
    ("physical_defense_flat", r"物理防御(?:力)?\s*([+-]\d+(?:\.\d+)?)(?![\d.%])点?", "point"),
    ("magical_defense_flat", r"法术防御(?:力)?\s*([+-]\d+(?:\.\d+)?)(?![\d.%])点?", "point"),
    ("attack_speed_percent", r"攻击速度\s*([+-]\d+(?:\.\d+)?)%", "%"),
    ("critical_rate_percent", r"暴击率\s*([+-]\d+(?:\.\d+)?)%", "%"),
    ("critical_effect_percent", r"暴击效果\s*([+-]\d+(?:\.\d+)?)%", "%"),
    ("initial_energy_flat", r"初始法力(?:值)?\s*([+-]\d+(?:\.\d+)?)(?![\d.%])", "point"),
    ("max_energy_percent", r"(?:最大)?法力(?:值)?上限\s*([+-]\d+(?:\.\d+)?)%", "%"),
    ("max_energy_flat", r"(?:最大)?法力(?:值)?上限\s*([+-]\d+(?:\.\d+)?)(?![\d.%])", "point"),
)


def strip_markup(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("。", "。")


def parse_static_attributes(evidence: EvidenceFragment) -> tuple[ParsedAttribute, ...]:
    """Extract only literal, unconditional property clauses from raw card text."""
    text = strip_markup(evidence.text)
    parsed: list[ParsedAttribute] = []
    consumed: set[tuple[int, int]] = set()
    for axis, pattern, unit in _STATIC_PATTERNS:
        for match in re.finditer(pattern, text):
            if match.span() in consumed:
                continue
            # A combat-start clause is state-dependent rather than paper static.
            prefix = text[max(0, match.start() - 12):match.start()]
            if any(term in prefix for term in ("战斗开始", "每", "首次", "受到", "获得")):
                continue
            consumed.add(match.span())
            parsed.append(ParsedAttribute(
                axis=axis,
                amount=float(match.group(1)),
                unit=unit,
                raw_fragment=match.group(0),
                evidence_id=evidence.evidence_id,
            ))
    return tuple(parsed)


def classify_passive(evidence: EvidenceFragment) -> PassiveAssessment:
    """Classify a passive without estimating an unproven expected benefit."""
    text = strip_markup(evidence.text)
    if any(term in text for term in ("无敌", "不可选中", "复生", "免疫控制", "不会超过")):
        return PassiveAssessment(
            "capability_only", _trigger(text), "wearer", "rule-changing survival/control capability",
            ("no_expected_combat_value_modeled",), evidence.evidence_id,
        )
    if "周围1格每有1个敌方单位" in text or "根据" in text or "随机" in text:
        return PassiveAssessment(
            "conditional_range", _trigger(text), "wearer_or_declared_target", "condition function; target/count/position scenario required",
            ("condition_distribution",), evidence.evidence_id,
        )
    if "生命恢复和护盾效果提升" in text:
        return PassiveAssessment(
            "conditional_range", _trigger(text), "wearer", "multiplier applied to declared heal/shield sources",
            ("base_heal_or_shield_total", "trigger_count_and_modifier_stacking"), evidence.evidence_id,
        )
    if "最多叠加" in text and re.search(r"(?:释放|获得|造成|受到).*(?:\+|获得).*\d+", text):
        return PassiveAssessment(
            "direct_bounded", _trigger(text), "wearer", "literal per-trigger increment with stated stack ceiling",
            ("actual_trigger_count_is_scene_input",), evidence.evidence_id,
        )
    if all(term in text for term in ("每", "持续")) and re.search(r"\d+", text):
        return PassiveAssessment(
            "direct_bounded", _trigger(text), "wearer_or_declared_target", "literal amount/cadence/duration requires declared scene",
            (), evidence.evidence_id,
        )
    if text and not parse_static_attributes(evidence):
        return PassiveAssessment(
            "unresolved", "not mechanically isolated", "unknown", "no quantitative result",
            ("passive_semantics_or_trigger_frequency",), evidence.evidence_id,
        )
    return PassiveAssessment(
        "unresolved", "static attributes only or mixed clause", "unknown", "no passive quantity asserted",
        ("passive_clause_not_mechanically_separable",), evidence.evidence_id,
    )


def _trigger(text: str) -> str:
    for delimiter in ("。", "，"):
        first = text.split(delimiter, 1)[0].strip()
        if first:
            return first
    return text.strip() or "missing_raw_text"
