from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.api_cache import json_safe, today_string


ROOT_DIR = Path(__file__).resolve().parents[1]
SITE_DATA_DIR = ROOT_DIR / "webapp" / "static" / "data"
SCAN_EXPORT_PATH = SITE_DATA_DIR / "scan" / "default.json"
ANALYZE_EXPORT_DIR = SITE_DATA_DIR / "analyze"
META_EXPORT_PATH = SITE_DATA_DIR / "meta.json"


def export_scan_response(response: dict[str, Any]) -> Path:
    return _write_json(SCAN_EXPORT_PATH, response)


def export_analyze_response(symbol: str, response: dict[str, Any]) -> Path:
    return _write_json(ANALYZE_EXPORT_DIR / f"{symbol}.json", response)


def export_meta(*, symbol_count: int, scan_path: str, analyze_count: int) -> Path:
    payload = {
        "generated_date": today_string(),
        "symbol_count": symbol_count,
        "scan_path": scan_path,
        "analyze_count": analyze_count,
    }
    return _write_json(META_EXPORT_PATH, payload)


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(json_safe(payload), file, indent=2)
    return path
