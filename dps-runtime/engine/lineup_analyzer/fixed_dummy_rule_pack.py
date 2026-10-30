from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from .upstream import SourceKey, UpstreamReader


RULE_PACK_SCHEMA_VERSION = "fixed-dummy-rule-pack-v1"
ENGINE_REVISION = "fixed-dummy-engine-v1"


@dataclass(frozen=True)
class FixedDummySourceSnapshot:
    source_key: str
    path: str
    sha256: str
    declared_version: str | None
    validation_status: str


@dataclass(frozen=True)
class FixedDummyRuleMetadata:
    rule_id: str
    trigger: str
    target_policy: str
    phase: str
    priority: int
    coverage_tier: str


@dataclass(frozen=True)
class FixedDummyRulePackV1:
    schema_version: str
    rule_pack_id: str
    rule_pack_sha256: str
    engine_revision: str
    source_snapshots: tuple[FixedDummySourceSnapshot, ...]
    rules: tuple[FixedDummyRuleMetadata, ...]

    def rule(self, rule_id: str) -> FixedDummyRuleMetadata:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        raise KeyError(f"unknown fixed-dummy rule: {rule_id}")

    def mechanism_rule(
        self,
        schedule_id: str,
        *,
        target_policy: str,
        coverage_tier: str,
    ) -> FixedDummyRuleMetadata:
        return FixedDummyRuleMetadata(
            rule_id=f"fixed-dummy:mechanism:{schedule_id}:v1",
            trigger="scheduled_mechanism",
            target_policy=target_policy,
            phase="scheduled_hit",
            priority=50,
            coverage_tier=coverage_tier,
        )


_BASE_RULES = (
    FixedDummyRuleMetadata(
        "fixed-dummy:basic-attack:v1",
        "basic_attack",
        "single_fixed_target",
        "basic_attack",
        20,
        "strict",
    ),
    FixedDummyRuleMetadata(
        "fixed-dummy:active-direct:v1",
        "mana_ready_cast",
        "single_fixed_target",
        "active_cast",
        30,
        "strict",
    ),
    FixedDummyRuleMetadata(
        "fixed-dummy:equipment-on-hit:v1",
        "basic_attack_damage",
        "single_fixed_target",
        "on_hit",
        60,
        "strict",
    ),
    FixedDummyRuleMetadata(
        "fixed-dummy:expected-critical:v1",
        "basic_attack_damage",
        "single_fixed_target",
        "model_increment",
        90,
        "exploratory",
    ),
    FixedDummyRuleMetadata(
        "fixed-dummy:expected-repeat:v1",
        "active_skill_damage",
        "single_fixed_target",
        "model_increment",
        90,
        "exploratory",
    ),
    FixedDummyRuleMetadata(
        "fixed-dummy:equipment-periodic:v1",
        "equipment_timer_or_threshold",
        "single_fixed_target",
        "delayed_effect",
        70,
        "strict",
    ),
)


def build_fixed_dummy_rule_pack(source_root: Path) -> FixedDummyRulePackV1:
    """Freeze the source fingerprints and stable rule metadata for one run."""
    reader = UpstreamReader(Path(source_root))
    for source_key in (
        SourceKey.RAW_HEROES,
        SourceKey.RAW_EQUIPMENT,
        SourceKey.COMPILED_KB,
    ):
        reader.read_json(source_key)
    snapshots = tuple(
        FixedDummySourceSnapshot(
            source_key=item.source_key,
            path=item.path,
            sha256=item.sha256,
            declared_version=item.declared_version,
            validation_status=item.validation_status,
        )
        for item in sorted(reader.source_reads, key=lambda value: value.source_key)
    )
    canonical = json.dumps(
        {
            "schema_version": RULE_PACK_SCHEMA_VERSION,
            "engine_revision": ENGINE_REVISION,
            "rules": [asdict(rule) for rule in _BASE_RULES],
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return FixedDummyRulePackV1(
        schema_version=RULE_PACK_SCHEMA_VERSION,
        rule_pack_id="fixed-dummy-core-rules",
        rule_pack_sha256=hashlib.sha256(canonical).hexdigest(),
        engine_revision=ENGINE_REVISION,
        source_snapshots=snapshots,
        rules=_BASE_RULES,
    )


__all__ = [
    "ENGINE_REVISION",
    "FixedDummyRuleMetadata",
    "FixedDummyRulePackV1",
    "FixedDummySourceSnapshot",
    "RULE_PACK_SCHEMA_VERSION",
    "build_fixed_dummy_rule_pack",
]
