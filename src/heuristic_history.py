from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.api_cache import today_string


ROOT_DIR = Path(__file__).resolve().parents[1]
HEURISTIC_HISTORY_FILE = ROOT_DIR / "data" / "heuristic_history.csv"
HEURISTIC_HISTORY_COLUMNS = [
    "snapshot_date",
    "stock",
    "signal",
    "score",
    "close",
    "expected_xirr",
    "expected_entry_price",
    "expected_entry_date",
    "expected_low_price",
    "expected_low_date",
    "expected_peak_price",
    "expected_peak_date",
    "expected_peak_days",
]


def save_heuristic_snapshots(analyses_by_symbol: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    snapshot_date = today_string()

    for symbol, analysis in (analyses_by_symbol or {}).items():
        summary = (analysis or {}).get("summary", {})
        if not summary:
            continue

        rows.append(
            {
                "snapshot_date": snapshot_date,
                "stock": str(symbol).upper(),
                "signal": summary.get("signal"),
                "score": summary.get("score"),
                "close": summary.get("close"),
                "expected_xirr": summary.get("expected_xirr"),
                "expected_entry_price": summary.get("expected_entry_price"),
                "expected_entry_date": summary.get("expected_entry_date"),
                "expected_low_price": summary.get("expected_low_price"),
                "expected_low_date": summary.get("expected_low_date"),
                "expected_peak_price": summary.get("expected_peak_price"),
                "expected_peak_date": summary.get("expected_peak_date"),
                "expected_peak_days": summary.get("expected_peak_days"),
            }
        )

    new_rows = pd.DataFrame(rows, columns=HEURISTIC_HISTORY_COLUMNS)
    if new_rows.empty:
        return new_rows

    HEURISTIC_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    if HEURISTIC_HISTORY_FILE.exists() and HEURISTIC_HISTORY_FILE.stat().st_size > 0:
        existing = pd.read_csv(HEURISTIC_HISTORY_FILE)
        existing = existing.loc[
            ~(
                (existing["snapshot_date"] == snapshot_date)
                & (existing["stock"].isin(new_rows["stock"]))
            )
        ].copy()
        combined = pd.concat([existing, new_rows], ignore_index=True)
    else:
        combined = new_rows

    combined = combined.drop_duplicates(subset=["snapshot_date", "stock"], keep="last")
    combined.to_csv(HEURISTIC_HISTORY_FILE, index=False)
    return new_rows


def load_stock_heuristic_history(symbol: str, *, limit: int = 30) -> list[dict[str, Any]]:
    if not HEURISTIC_HISTORY_FILE.exists() or HEURISTIC_HISTORY_FILE.stat().st_size == 0:
        return []

    history = pd.read_csv(HEURISTIC_HISTORY_FILE)
    if history.empty:
        return []

    normalized_symbol = str(symbol).upper()
    stock_history = history.loc[history["stock"].astype(str).str.upper() == normalized_symbol].copy()
    if stock_history.empty:
        return []

    stock_history["snapshot_date"] = pd.to_datetime(stock_history["snapshot_date"], errors="coerce")
    stock_history = stock_history.dropna(subset=["snapshot_date"])
    if stock_history.empty:
        return []

    stock_history = stock_history.sort_values("snapshot_date", ascending=False).head(limit)
    stock_history["snapshot_date"] = stock_history["snapshot_date"].dt.date.astype(str)
    return stock_history.to_dict(orient="records")
