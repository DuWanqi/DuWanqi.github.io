from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class SourceLayer(str, Enum):
    OFFICIAL_RAW = "official_raw"
    MANUAL_GAME_EXTRACTION = "manual_game_extraction"
    FORMAL_ANALYSIS = "formal_analysis"
    STRUCTURED_RETRIEVAL = "structured_retrieval"
    EXTERNAL_OBSERVATION = "external_observation"
    MODEL_DERIVATION = "model_derivation"
    EXTERNAL_REFERENCE = "external_reference"


@dataclass(frozen=True)
class SourceRead:
    source_key: str
    path: str
    byte_size: int
    sha256: str
    modified_at: str
    read_at: str
    schema_id: str | None = None
    declared_version: str | None = None
    validation_status: str = "not_checked"
    record_count: int | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceField:
    name: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    subject_id: str
    claim: str
    source_layer: SourceLayer
    source_path: str
    source_locator: str
    confidence: str
    status: str
    applies_to: tuple[str, ...]
    uncertainties: tuple[str, ...]
    source_fields: tuple[str, ...] = ()
    freshness_status: str = "unknown"
    source_updated_at: str | None = None
    linked_source_path: str | None = None
    linked_source_modified_at: str | None = None
    structured_fields: tuple[EvidenceField, ...] = ()


@dataclass(frozen=True)
class RecallClue:
    source: str
    relation: str
    target: str
    why: str
    source_path: str
    usable_as_evidence: bool
    reason: str


@dataclass(frozen=True)
class EvidenceGap:
    code: str
    subject_id: str
    message: str
    source_path: str | None = None


@dataclass(frozen=True)
class EvidenceConflict:
    code: str
    subject_id: str
    message: str


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    node_type: str
    label: str
    source_layer: SourceLayer | None


@dataclass(frozen=True)
class GraphEdge:
    source: str
    relation: str
    target: str
    evidence_ids: tuple[str, ...]
    provenance: str


@dataclass(frozen=True)
class EvidenceGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


@dataclass(frozen=True)
class EvidencePack:
    schema_version: str
    evidence_policy: str
    input_summary: dict[str, Any]
    source_reads: tuple[SourceRead, ...]
    evidence: tuple[EvidenceItem, ...]
    graph: EvidenceGraph
    recall_clues: tuple[RecallClue, ...]
    gaps: tuple[EvidenceGap, ...]
    conflicts: tuple[EvidenceConflict, ...]
    analysis_status: str

    def to_dict(self) -> dict[str, Any]:
        return _json_values(asdict(self))


def _json_values(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_values(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_values(child) for child in value]
    return value
