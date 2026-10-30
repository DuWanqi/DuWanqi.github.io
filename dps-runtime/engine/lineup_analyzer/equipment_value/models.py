from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSnapshot:
    source_path: str
    source_layer: str
    sha256: str
    record_id: str
    applicable_boundary: str


@dataclass(frozen=True)
class EvidenceFragment:
    evidence_id: str
    text: str
    snapshot: SourceSnapshot
    parse_status: str


@dataclass(frozen=True)
class ParsedAttribute:
    axis: str
    amount: float
    unit: str
    raw_fragment: str
    evidence_id: str
    parse_status: str = "explicit_static"


@dataclass(frozen=True)
class PassiveAssessment:
    classification: str
    trigger_condition: str
    beneficiary: str
    quantitative_scope: str
    unresolved_items: tuple[str, ...]
    evidence_id: str


@dataclass(frozen=True)
class LocalEquivalence:
    hero_id: str
    hero_name: str
    level_scenario: str
    axis: str
    status: str
    value: float | None
    formula: str
    model_version: str
    input_snapshots: tuple[SourceSnapshot, ...]
    unmodeled_items: tuple[str, ...]


@dataclass(frozen=True)
class AcquisitionRoute:
    source_kind: str
    status: str
    source_condition: str
    uncertainty: str
    evidence_id: str


@dataclass(frozen=True)
class RoleProfile:
    profile_id: str
    label: str
    profile_layer: str
    applicable_axes: tuple[str, ...]
    boundaries: tuple[str, ...]


@dataclass(frozen=True)
class EquipmentProfile:
    equipment_id: str
    name: str
    raw_description: EvidenceFragment
    static_attributes: tuple[ParsedAttribute, ...]
    passive: PassiveAssessment
    acquisition_routes: tuple[AcquisitionRoute, ...]
    formal_analysis_snapshot: SourceSnapshot | None
    role_profiles: tuple[RoleProfile, ...]
    unresolved_items: tuple[str, ...]
