from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .evidence import SourceRead


class SourceKey(str, Enum):
    RAW_HEROES = "00_原始数据/JSON/英雄牌.json"
    RAW_EQUIPMENT = "00_原始数据/JSON/装备牌.json"
    RAW_TALENTS = "00_原始数据/JSON/天赋牌.json"
    RAW_EFFECTS = "00_原始数据/JSON/效果牌.json"
    CARD_INDEX = "03_编译数据/knowledge-engine-card-index.json"
    RELATION_INDEX = "03_编译数据/knowledge-engine-relations.json"
    CHESSPLAYER_KB = "03_编译数据/compiled-chessplayer-kb.json"
    COMPILED_KB = "03_编译数据/compiled-kb.json"
    FORMAL_MECHANICS = "01_知识库/01_机制与数值总库.md"
    FORMAL_ECONOMY = "01_知识库/23_经济系统与阵容资源约束.md"


class UpstreamSchemaError(ValueError):
    pass


_SOURCE_CONTRACTS: dict[SourceKey, tuple[str, tuple[str, ...], str, str | None]] = {
    SourceKey.RAW_HEROES: (
        "official-raw-heroes",
        ("heroCards", "lords"),
        "heroCards",
        "count",
    ),
    SourceKey.RAW_EQUIPMENT: (
        "official-raw-equipment",
        ("equipCards", "lords"),
        "equipCards",
        "count",
    ),
    SourceKey.RAW_TALENTS: (
        "official-raw-talents",
        ("talentCards", "lords"),
        "talentCards",
        "count",
    ),
    SourceKey.RAW_EFFECTS: (
        "official-raw-effects",
        ("effectCards", "lords"),
        "effectCards",
        "count",
    ),
    SourceKey.CARD_INDEX: (
        "knowledge-engine-card-index",
        ("cards",),
        "cards",
        "cardCount",
    ),
    SourceKey.RELATION_INDEX: (
        "knowledge-engine-relations",
        ("nodes", "edges"),
        "nodes",
        None,
    ),
    SourceKey.CHESSPLAYER_KB: (
        "compiled-chessplayer-kb",
        ("players",),
        "players",
        "count",
    ),
    SourceKey.COMPILED_KB: (
        "compiled-kb-model-derivation",
        ("entities",),
        "entities",
        "entityCount",
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UpstreamReader:
    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.root = root.resolve(strict=False)
        self._clock = clock
        self._cache: dict[SourceKey, Any] = {}
        self._reads: dict[SourceKey, SourceRead] = {}
        self._text_cache: dict[SourceKey, str] = {}

    @property
    def source_reads(self) -> tuple[SourceRead, ...]:
        return tuple(self._reads.values())

    def read_json(self, source_key: SourceKey) -> Any:
        if not isinstance(source_key, SourceKey):
            raise TypeError("source_key must be a SourceKey allowlist member")
        if source_key in self._cache:
            return self._cache[source_key]

        path = (self.root / Path(source_key.value)).resolve(strict=False)
        if not path.is_relative_to(self.root):
            raise ValueError(f"allowlisted source escaped root: {source_key.value}")
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig", errors="strict")
        value = json.loads(text)
        schema = _validate_source(source_key, value)
        stat = path.stat()
        self._cache[source_key] = value
        self._reads[source_key] = SourceRead(
            source_key=source_key.name.lower(),
            path=str(path),
            byte_size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            modified_at=datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
            read_at=self._clock(),
            schema_id=schema["schema_id"],
            declared_version=schema["declared_version"],
            validation_status=schema["validation_status"],
            record_count=schema["record_count"],
            diagnostics=tuple(schema["diagnostics"]),
        )
        return value

    def read_text(self, source_key: SourceKey) -> str:
        allowed = {SourceKey.FORMAL_MECHANICS, SourceKey.FORMAL_ECONOMY}
        if not isinstance(source_key, SourceKey) or source_key not in allowed:
            raise TypeError("source_key must be an allowlisted formal text source")
        if source_key in self._text_cache:
            return self._text_cache[source_key]
        path = (self.root / Path(source_key.value)).resolve(strict=False)
        if not path.is_relative_to(self.root):
            raise ValueError(f"allowlisted source escaped root: {source_key.value}")
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig", errors="strict")
        stat = path.stat()
        self._text_cache[source_key] = text
        self._reads[source_key] = SourceRead(
            source_key=source_key.name.lower(),
            path=str(path),
            byte_size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            read_at=self._clock(),
            schema_id="formal-markdown-rules",
            validation_status="strict_utf8_text",
            diagnostics=(),
        )
        return text


def _validate_source(source_key: SourceKey, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise UpstreamSchemaError(f"{source_key.name} root must be a JSON object")
    schema_id, required_keys, collection_key, count_key = _SOURCE_CONTRACTS[source_key]
    missing = [key for key in required_keys if key not in value]
    if missing:
        raise UpstreamSchemaError(
            f"{source_key.name} missing required root keys: {', '.join(missing)}"
        )
    for key in required_keys:
        if not isinstance(value.get(key), list):
            raise UpstreamSchemaError(f"{source_key.name}.{key} must be a JSON array")
    collection = value[collection_key]
    declared_version = _declared_version(value)
    diagnostics: list[str] = []
    if declared_version is None:
        diagnostics.append(
            "上游未声明 schemaVersion；当前仅按必需顶层字段和集合类型校验兼容性。"
        )
    meta = value.get("meta") if isinstance(value.get("meta"), dict) else {}
    declared_count = meta.get(count_key) if count_key else None
    if isinstance(declared_count, int) and declared_count != len(collection):
        raise UpstreamSchemaError(
            f"{source_key.name} declared count={declared_count}, actual={len(collection)}"
        )
    return {
        "schema_id": schema_id,
        "declared_version": declared_version,
        "validation_status": (
            "compatible_versioned" if declared_version else "compatible_unversioned"
        ),
        "record_count": len(collection),
        "diagnostics": diagnostics,
    }


def _declared_version(value: dict[str, Any]) -> str | None:
    meta = value.get("meta") if isinstance(value.get("meta"), dict) else {}
    for candidate in (
        value.get("schemaVersion"),
        value.get("schema_version"),
        meta.get("schemaVersion"),
        meta.get("schema_version"),
    ):
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return None
