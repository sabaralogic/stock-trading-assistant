from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_fetcher import normalize_symbols


ROOT_DIR = Path(__file__).resolve().parents[1]
API_CACHE_DIR = ROOT_DIR / "data" / "api_cache"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}

    if isinstance(value, list):
        return [json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [json_safe(item) for item in value]

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, (str, bool, int)) or value is None:
        return value

    if isinstance(value, float):
        return None if pd.isna(value) else value

    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    return value


def today_string() -> str:
    return date.today().isoformat()


def cache_dir() -> Path:
    API_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return API_CACHE_DIR


def cache_file_path(mode: str, cache_key_data: dict[str, Any]) -> Path:
    encoded_key = json.dumps(json_safe(cache_key_data), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded_key.encode("utf-8")).hexdigest()
    return cache_dir() / f"{mode}_{digest}.json"


def read_cached_response(mode: str, cache_key_data: dict[str, Any]) -> dict[str, Any] | None:
    path = cache_file_path(mode, cache_key_data)
    if not path.exists():
        return None

    with path.open(encoding="utf-8") as file:
        cached_response = json.load(file)

    if cached_response.get("cache_date") != today_string():
        return None

    cached_response["served_from_cache"] = True
    return cached_response


def write_cached_response(mode: str, cache_key_data: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    path = cache_file_path(mode, cache_key_data)
    response_to_store = dict(response)
    response_to_store["served_from_cache"] = False
    response_to_store["cache_date"] = today_string()

    with path.open("w", encoding="utf-8") as file:
        json.dump(json_safe(response_to_store), file, indent=2)

    return response_to_store


def scan_cache_key(payload: dict[str, Any], resolved_symbols: list[str] | None = None) -> dict[str, Any]:
    if resolved_symbols is None:
        raw_symbols = split_symbols(payload.get("symbols"))
        normalized_symbols = normalize_symbols(raw_symbols) if raw_symbols else []
    else:
        normalized_symbols = normalize_symbols(resolved_symbols)

    return {
        "symbols": normalized_symbols,
        "period": payload.get("period", "1y"),
        "interval": payload.get("interval", "1d"),
        "start": payload.get("start"),
        "end": payload.get("end"),
        "auto_adjust": bool_value(payload, "auto_adjust", True),
        "top_n": int(payload.get("top_n", 25)),
    }


def analyze_cache_key(symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized_symbol = normalize_symbols([symbol])
    return {
        "symbol": normalized_symbol[0] if normalized_symbol else symbol,
        "period": payload.get("period", "1y"),
        "interval": payload.get("interval", "1d"),
        "start": payload.get("start"),
        "end": payload.get("end"),
        "auto_adjust": bool_value(payload, "auto_adjust", True),
        "turning_point_threshold": float(payload.get("turning_point_threshold", 10.0)),
        "save_report": bool_value(payload, "save_report", True),
    }


def split_symbols(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        normalized = value.replace(",", " ").replace("\n", " ")
        return [item.strip() for item in normalized.split() if item.strip()]

    if isinstance(value, list):
        symbols: list[str] = []
        for item in value:
            symbols.extend(split_symbols(item))
        return symbols

    return []


def bool_value(payload: dict[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
