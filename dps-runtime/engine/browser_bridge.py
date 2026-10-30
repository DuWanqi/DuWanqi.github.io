from __future__ import annotations

import json
import os
from pathlib import Path

from lineup_analyzer.fixed_dummy_web_service import FixedDummyWebService


DATA_ROOT = Path(os.environ.get("DPS_RUNTIME_DATA_ROOT", "/home/pyodide/dps-runtime/data"))
SERVICE = FixedDummyWebService(DATA_ROOT)


def bootstrap_json() -> str:
    result = SERVICE.bootstrap()
    result["assumptions"] = ("browser_computes_all_damage_and_timing",)
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def run_json(payload_json: str) -> str:
    payload = json.loads(payload_json)
    return json.dumps(SERVICE.run(payload), ensure_ascii=False, separators=(",", ":"))


def run_trial_json(payload_json: str) -> str:
    payload = json.loads(payload_json)
    return json.dumps(SERVICE.run_trial(payload), ensure_ascii=False, separators=(",", ":"))
