from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any, Callable
from urllib.parse import quote, urlparse

from .equipment_value.catalog import EquipmentValueCatalog
from .equipment_value.growth_templates import GrowthTemplateLoader
from .fixed_dummy_damage import (
    DpsFixtureInputV0,
    FixedDummyDamageEngine,
    fixed_dummy_equipment_support,
    fixed_dummy_target_equipment_support,
)
from .fixed_dummy_trials import FixedDummyTrialEngine, FixedDummyTrialInputV1, trial_profiles
from .fixed_dummy_rule_pack import build_fixed_dummy_rule_pack
from .combat_math.damage import resistance_multiplier
from .upstream import SourceKey, UpstreamReader


_WEB_ROOT = Path(__file__).resolve().parent / "fixed_dummy_web"
_KNOWLEDGE_UI_HERO_DATA = Path("万象棋知识工作台") / "网站ui" / "src" / "data" / "official-hero-cards.json"
_PUBLICATION_STATUS_FILE = Path("object-publication-status.json")
_STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/fixed-dummy.css": ("fixed-dummy.css", "text/css; charset=utf-8"),
    "/static/fixed-dummy.js": ("fixed-dummy.js", "application/javascript; charset=utf-8"),
}
_IMAGE_HOSTS = {"game-os-cos.kohsocialapp.qq.com", "staticimage.osgame.qq.com"}
_ASSET_CDN_ORIGIN = "https://assets.wanxiangqiwiki.com"
_CSP_HEADER = ("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' https://assets.wanxiangqiwiki.com https://game-os-cos.kohsocialapp.qq.com https://staticimage.osgame.qq.com; object-src 'none'; base-uri 'none'; frame-ancestors 'self' http://127.0.0.1:4188 https://wanxiangqiwiki.pages.dev https://wanxiangqi.wiki https://www.wanxiangqi.wiki https://wanxiangwiki.com https://www.wanxiangwiki.com https://wanxiangqiwiki.com https://www.wanxiangqiwiki.com")
_HEADERS = (_CSP_HEADER, ("Cache-Control", "no-store"))
_ASSET_HEADERS = (_CSP_HEADER, ("Cache-Control", "private, max-age=300"))
_BOOTSTRAP_SOURCE_KEYS = (
    SourceKey.RAW_HEROES,
    SourceKey.RAW_EQUIPMENT,
    SourceKey.COMPILED_KB,
)


class FixedDummyWebService:
    def __init__(self, source_root: Path) -> None:
        self.source_root = Path(source_root)
        self.engine = FixedDummyDamageEngine(self.source_root)
        self.trial_engine = FixedDummyTrialEngine(self.source_root)
        self._bootstrap_lock = RLock()
        self._bootstrap_source_revision: tuple[tuple[str, int, int], ...] | None = None
        self._bootstrap_cache: dict[str, object] | None = None
        self._asset_urls: dict[str, dict[str, str]] = {}

    def bootstrap(self) -> dict[str, object]:
        revision = _bootstrap_source_revision(self.source_root)
        with self._bootstrap_lock:
            if revision == self._bootstrap_source_revision and self._bootstrap_cache is not None:
                return self._bootstrap_cache
            bootstrap, asset_urls = self._build_bootstrap()
            self._bootstrap_source_revision = revision
            self._bootstrap_cache = bootstrap
            self._asset_urls = asset_urls
            return bootstrap

    def _build_bootstrap(self) -> tuple[dict[str, object], dict[str, dict[str, str]]]:
        reader = UpstreamReader(self.source_root)
        heroes = reader.read_json(SourceKey.RAW_HEROES)["heroCards"]
        published_hero_ids = _published_hero_ids(self.source_root)
        raw_equipment = reader.read_json(SourceKey.RAW_EQUIPMENT)["equipCards"]
        presentation_heroes, presentation_source = _verified_presentation_heroes(
            self.source_root,
            heroes,
        )
        presentation_by_id = {
            str(item["id"]): item
            for item in presentation_heroes
            if item.get("id") is not None
        }
        equipment = EquipmentValueCatalog(self.source_root).fixed_dummy_profiles()
        equipment_options = []
        target_equipment_options = []
        supported_axes = {
            "physical_attack_flat",
            "magical_attack_flat",
            "attack_speed_percent",
            "physical_defense_flat",
            "magical_defense_flat",
            "max_health_percent",
            "max_energy_flat",
            "magical_attack_percent",
            "critical_rate_percent",
            "critical_effect_percent",
        }
        for profile in equipment:
            axes = {item.axis for item in profile.static_attributes}
            support = fixed_dummy_equipment_support(profile.equipment_id)
            if support is not None:
                status, reason = support
            elif axes.intersection({"critical_rate_percent", "critical_effect_percent"}):
                status = "supported_deterministic_effect"
                reason = "固定暴击率按普攻期望增量计入，不生成随机暴击"
            elif axes and axes.issubset(supported_axes):
                status = "supported_static_only"
                reason = "只计算明确静态属性，被动效果不计入"
            elif not axes:
                status = "unsupported"
                reason = "只有被动效果，当前无法完整计算"
            else:
                status = "unsupported"
                reason = "静态属性尚未接入"
            equipment_options.append({
                "equipment_id": profile.equipment_id,
                "name": profile.name,
                "static_attributes": [
                    {"axis": item.axis, "amount": item.amount}
                    for item in profile.static_attributes
                ],
                "support_status": status,
                "support_reason": reason,
                "effect_summary": _plain_card_text(profile.raw_description.text),
                "equippable": True,
                "passive_status": (
                    "supported"
                    if status == "supported_deterministic_effect"
                    else "supported_partial"
                    if status == "supported_partial_effect"
                    else "excluded"
                    if status == "supported_static_only"
                    else "unsupported"
                ),
            })
            target_support = fixed_dummy_target_equipment_support(profile.equipment_id)
            if target_support is not None:
                target_status, target_reason = target_support
                target_equipment_options.append({
                    "equipment_id": profile.equipment_id,
                    "name": profile.name,
                    "asset_url": _cdn_thumbnail_url("装备牌", profile.name, profile.equipment_id),
                    "support_status": target_status,
                    "support_reason": target_reason,
                    "effect_summary": _plain_card_text(profile.raw_description.text),
                })
        bootstrap = {
            "schema_version": "fixed-dummy-bootstrap-v2",
            "engine_contract": asdict(build_fixed_dummy_rule_pack(self.source_root)),
            "heroes": [
                {
                    "hero_id": f"hero:{item['id']}",
                    "name": item["name"],
                    "asset_url": _cdn_thumbnail_url("英雄牌", item["name"], item["id"]),
                    "relation_name": str(item.get("relationName") or "无阵营"),
                    "quality": int(item.get("quality") or 0),
                    "awakening": _awakening_metadata(item),
                    **_skill_summary(presentation_by_id.get(str(item["id"]), item)),
                }
                for item in heroes
                if str(item.get("id") or "") in published_hero_ids and item.get("name")
            ],
            "equipment": [
                {
                    **item,
                    "asset_url": _cdn_thumbnail_url("装备牌", item["name"], item["equipment_id"]),
                }
                for item in equipment_options
            ],
            "target_dummy_equipment": target_equipment_options,
            "dummy_defense_presets": _dummy_defense_presets(self.source_root),
            "trial_profiles": trial_profiles(),
            "presentation_source": presentation_source,
            "assumptions": ("server_computes_all_damage_and_timing",),
        }
        return bootstrap, {
            "heroes": _asset_url_map(heroes),
            "equipment": _asset_url_map(raw_equipment),
        }

    def asset_url(self, kind: str, raw_id: str) -> str | None:
        if kind not in {"heroes", "equipment"} or not raw_id.isdecimal():
            return None
        with self._bootstrap_lock:
            if self._bootstrap_cache is not None:
                return self._asset_urls.get(kind, {}).get(raw_id)
        self.bootstrap()
        with self._bootstrap_lock:
            return self._asset_urls.get(kind, {}).get(raw_id)

    def run(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.engine.run(DpsFixtureInputV0.from_dict(payload)).to_dict()

    def run_trial(self, payload: dict[str, Any]) -> dict[str, object]:
        return self.trial_engine.run(FixedDummyTrialInputV1.from_dict(payload)).to_dict()


def create_fixed_dummy_wsgi_app(source_root: Path) -> Callable[..., list[bytes]]:
    service = FixedDummyWebService(source_root)
    def application(environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        path, method = str(environ.get("PATH_INFO", "")), str(environ.get("REQUEST_METHOD", "")).upper()
        try:
            if path == "/favicon.ico" and method == "GET":
                start_response("204 No Content", [*_HEADERS]); return [b""]
            if path in _STATIC_FILES:
                if method != "GET": return _json(start_response, "405 Method Not Allowed", {"error":"method_not_allowed"})
                return _static(start_response, *_STATIC_FILES[path])
            if path == "/api/fixed-dummy/bootstrap" and method == "GET": return _json(start_response, "200 OK", service.bootstrap())
            if path == "/api/fixed-dummy/run" and method == "POST": return _json(start_response, "200 OK", service.run(_request(environ)))
            if path == "/api/fixed-dummy/trial" and method == "POST": return _json(start_response, "200 OK", service.run_trial(_request(environ)))
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "assets" and method == "GET":
                raw_id = parts[2].split(".", 1)[0]
                url = service.asset_url(parts[1], raw_id)
                if url:
                    start_response("302 Found", [("Location", url), *_ASSET_HEADERS]); return [b""]
            return _json(start_response, "404 Not Found", {"error":"not_found"})
        except ValueError as error:
            return _json(start_response, "400 Bad Request", {"error": str(error)})
    return application


def _request(environ: dict[str, Any]) -> dict[str, Any]:
    if str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0] != "application/json": raise ValueError("unsupported_media_type")
    length = int(str(environ.get("CONTENT_LENGTH", "0")))
    value = json.loads(environ["wsgi.input"].read(length).decode("utf-8"))
    if not isinstance(value, dict): raise ValueError("request_must_be_json_object")
    return value


def _json(start_response, status, value):
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    start_response(status, [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body))), *_HEADERS]); return [body]


def _static(start_response, filename, content_type):
    body = (_WEB_ROOT / filename).read_bytes(); start_response("200 OK", [("Content-Type", content_type), ("Content-Length", str(len(body))), *_HEADERS]); return [body]


def _skill_summary(hero: dict[str, Any]) -> dict[str, object]:
    skills = (hero.get("heroCard") or {}).get("skillList") or ()
    if not skills or not isinstance(skills[0], dict):
        return {"skill_name": None, "skill_description": None, "skill_enhancements": ()}
    skill = skills[0]
    description = skill.get("desc") or skill.get("description") or skill.get("content")
    enhancement = skill.get("enhanceSkill") if isinstance(skill.get("enhanceSkill"), dict) else {}
    enhancements = tuple(
        {
            "level": int(item["level"]),
            "description": str(item.get("desc") or "").strip(),
        }
        for item in enhancement.get("params") or ()
        if isinstance(item, dict) and str(item.get("level", "")).isdigit()
    )
    return {
        "skill_name": str(skill["name"]) if skill.get("name") else None,
        "skill_description": str(description).strip() if description else None,
        "skill_enhancements": enhancements,
    }


def _awakening_metadata(hero: dict[str, Any]) -> dict[str, object]:
    hero_card = hero.get("heroCard") if isinstance(hero.get("heroCard"), dict) else {}
    awakened_card = hero_card.get("awakeingCard") if isinstance(hero_card.get("awakeingCard"), dict) else {}
    return {
        "supported": str(hero.get("id") or "") == "3551",
        "normal_summary": _plain_card_text(str(hero.get("desc") or "")),
        "awakened_summary": _plain_card_text(str(awakened_card.get("desc") or "")),
    }


def _plain_card_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value or "")).strip()


def _cdn_thumbnail_url(card_type: str, name: object, raw_id: object) -> str:
    normalized_id = str(raw_id).split(":", 1)[-1]
    filename = f"{card_type}_{str(name)}_{normalized_id}_缩略图.webp"
    return f"{_ASSET_CDN_ORIGIN}/assets/webp/{quote(filename)}"


def _verified_presentation_heroes(
    source_root: Path,
    formal_heroes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    """Use the knowledge UI snapshot only when its skill payload matches the formal root."""
    relative_path = _KNOWLEDGE_UI_HERO_DATA.as_posix()
    path = source_root / _KNOWLEDGE_UI_HERO_DATA
    fallback = {
        "kind": "formal_root",
        "path": SourceKey.RAW_HEROES.value,
        "verification_status": "knowledge_ui_snapshot_unavailable",
    }
    if not path.is_file():
        return formal_heroes, fallback
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fallback["verification_status"] = "knowledge_ui_snapshot_unreadable"
        return formal_heroes, fallback
    candidates = payload.get("heroCards") if isinstance(payload, dict) else None
    if not isinstance(candidates, list):
        fallback["verification_status"] = "knowledge_ui_snapshot_invalid"
        return formal_heroes, fallback
    formal_by_id = {str(item.get("id")): item for item in formal_heroes}
    candidate_by_id = {str(item.get("id")): item for item in candidates}
    if set(formal_by_id) != set(candidate_by_id):
        fallback["verification_status"] = "knowledge_ui_snapshot_roster_mismatch"
        return formal_heroes, fallback
    for hero_id, formal in formal_by_id.items():
        candidate = candidate_by_id[hero_id]
        if candidate.get("name") != formal.get("name") or (
            candidate.get("heroCard", {}).get("skillList")
            != formal.get("heroCard", {}).get("skillList")
        ):
            fallback["verification_status"] = "knowledge_ui_snapshot_skill_mismatch"
            return formal_heroes, fallback
    return candidates, {
        "kind": "knowledge_workbench_ui_read_only",
        "path": relative_path,
        "verification_status": "verified_equal_to_formal_root",
        "verified_hero_count": len(candidates),
    }


def _bootstrap_source_revision(source_root: Path) -> tuple[tuple[str, int, int], ...]:
    root = Path(source_root)
    paths = [root / source_key.value for source_key in _BOOTSTRAP_SOURCE_KEYS]
    paths.append(root / _PUBLICATION_STATUS_FILE)
    presentation_path = root / _KNOWLEDGE_UI_HERO_DATA
    if presentation_path.is_file():
        paths.append(presentation_path)
    return tuple(
        (path.relative_to(root).as_posix(), path.stat().st_mtime_ns, path.stat().st_size)
        for path in paths
    )


def _published_hero_ids(source_root: Path) -> set[str]:
    policy_path = Path(source_root) / _PUBLICATION_STATUS_FILE
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("schema") != "object-publication-status/v1":
        raise ValueError("unsupported_object_publication_status_schema")
    raw_ids = policy.get("types", {}).get("hero", {}).get("publishedRawIds")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError("published_hero_policy_is_missing")
    normalized = {str(raw_id) for raw_id in raw_ids}
    if len(normalized) != len(raw_ids) or any(not raw_id.isdecimal() for raw_id in normalized):
        raise ValueError("published_hero_policy_is_invalid")
    return normalized


def _asset_url_map(cards: list[dict[str, Any]]) -> dict[str, str]:
    result = {}
    for card in cards:
        raw_id = str(card.get("id") or "")
        value = _trusted_image_url(card.get("thumb"))
        if raw_id.isdecimal() and value:
            result[raw_id] = value
    return result


def _trusted_image_url(raw_value: object) -> str | None:
    value = str(raw_value or "")
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.hostname in _IMAGE_HOSTS else None


def _dummy_defense_presets(source_root: Path) -> list[dict[str, object]]:
    catalog = GrowthTemplateLoader().load(source_root)
    grouped: dict[float, list[str]] = {}
    for template in catalog.templates:
        if template.base_physical_defense is None or template.base_magical_defense is None:
            continue
        if abs(template.base_physical_defense - template.base_magical_defense) > 1e-9:
            continue
        grouped.setdefault(template.base_physical_defense, []).append(template.template_id)
    presets = []
    for resistance, templates in sorted(grouped.items()):
        if resistance not in {14.0, 16.0, 18.0, 20.0}:
            continue
        multiplier = resistance_multiplier(resistance)
        presets.append({
            "value": resistance,
            "template_names": sorted(templates),
            "label": f"{resistance:g}抗性",
            "damage_multiplier": multiplier.value,
            "damage_reduction_percent": (1.0 - multiplier.value) * 100.0,
            "formula": "damage_multiplier=40/(resistance+40)",
            "evidence_id": catalog.snapshot.record_id,
        })
    return presets
