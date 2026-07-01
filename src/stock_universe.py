from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import pandas as pd


DEFAULT_STOCK_UNIVERSE_URL = (
    "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"
)
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STOCK_UNIVERSE_CACHE_PATH = ROOT_DIR / "data" / "default_stock_universe.csv"
DEFAULT_SYMBOLS_FALLBACK_PATH = ROOT_DIR / "data" / "stocks.txt"

SYMBOL_COLUMN_CANDIDATES = (
    "Symbol",
    "SYMBOL",
)

SECTOR_COLUMN_CANDIDATES = (
    "Industry",
    "Sector",
    "Index Industry",
    "Industry Name",
    "Basic Industry",
)


def load_default_universe_frame() -> pd.DataFrame:
    remote_error: Exception | None = None

    try:
        csv_text = _download_default_universe_csv()
        DEFAULT_STOCK_UNIVERSE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_STOCK_UNIVERSE_CACHE_PATH.write_text(csv_text, encoding="utf-8")
        return pd.read_csv(StringIO(csv_text))
    except Exception as error:
        remote_error = error

    if DEFAULT_STOCK_UNIVERSE_CACHE_PATH.exists():
        return pd.read_csv(DEFAULT_STOCK_UNIVERSE_CACHE_PATH)

    if DEFAULT_SYMBOLS_FALLBACK_PATH.exists():
        symbols = [
            line.strip().removesuffix(".NS")
            for line in DEFAULT_SYMBOLS_FALLBACK_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return pd.DataFrame({
            "Symbol": symbols,
            "Sector": ["Unknown"] * len(symbols),
        })

    raise RuntimeError(
        "Unable to load the default stock universe from NSE, and no local fallback is available."
    ) from remote_error


def load_default_symbols() -> list[str]:
    frame = load_default_universe_frame()
    symbol_column = _first_matching_column(frame, SYMBOL_COLUMN_CANDIDATES)
    if symbol_column is None:
        raise ValueError("Could not find a symbol column in the default stock universe file.")

    return [
        f"{str(symbol).strip()}.NS"
        for symbol in frame[symbol_column].dropna()
        if not str(symbol).startswith("DUMMY")
    ]


def load_default_symbol_metadata() -> dict[str, dict[str, Any]]:
    frame = load_default_universe_frame()
    symbol_column = _first_matching_column(frame, SYMBOL_COLUMN_CANDIDATES)
    if symbol_column is None:
        raise ValueError("Could not find a symbol column in the default stock universe file.")

    sector_column = _first_matching_column(frame, SECTOR_COLUMN_CANDIDATES)
    metadata: dict[str, dict[str, Any]] = {}

    for _, row in frame.iterrows():
        raw_symbol = row.get(symbol_column)
        if pd.isna(raw_symbol):
            continue

        symbol = f"{str(raw_symbol).strip()}.NS"
        if symbol.startswith("DUMMY"):
            continue

        sector = "Unknown"
        if sector_column is not None:
            raw_sector = row.get(sector_column)
            if pd.notna(raw_sector):
                cleaned_sector = str(raw_sector).strip()
                if cleaned_sector:
                    sector = cleaned_sector

        metadata[symbol] = {
            "sector": sector,
        }

    return metadata


def _first_matching_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _download_default_universe_csv() -> str:
    request = Request(
        DEFAULT_STOCK_UNIVERSE_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8",
        },
    )

    last_error: Exception | None = None

    for _attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8")
        except (OSError, URLError) as error:
            last_error = error

    raise RuntimeError(
        f"Could not download default stock universe from {DEFAULT_STOCK_UNIVERSE_URL}"
    ) from last_error
