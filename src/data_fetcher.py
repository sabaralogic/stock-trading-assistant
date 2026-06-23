from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Optional

import pandas as pd
import yfinance as yf


logger = logging.getLogger(__name__)


def fetch_stock_data(
    symbol: str,
    *,
    period: str = "10y",
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """Fetch historical stock data for one symbol."""
    symbol = normalize_symbol(symbol)
    if not symbol:
        raise ValueError("symbol cannot be empty")

    options = {
        "interval": interval,
        "auto_adjust": auto_adjust,
        "progress": False,
        "threads": False,
    }

    if start or end:
        options["start"] = start
        options["end"] = end
    else:
        options["period"] = period

    data = yf.download(symbol, **options)
    if data.empty:
        raise ValueError(f"No data returned for {symbol}")

    return normalize_downloaded_data(data, symbol)


def fetch_batch_stock_data(
    symbols: Iterable[str],
    *,
    period: str = "10y",
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    auto_adjust: bool = True,
    max_workers: int = 5,
) -> dict[str, pd.DataFrame]:
    """Fetch stock data for multiple symbols.

    Returns a dictionary keyed by ticker symbol. Failed symbols are logged and
    omitted from the result so one bad ticker does not fail the whole batch.
    """
    normalized_symbols = normalize_symbols(symbols)
    if not normalized_symbols:
        return {}
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")

    results: dict[str, pd.DataFrame] = {}

    with ThreadPoolExecutor(max_workers=min(max_workers, len(normalized_symbols))) as executor:
        futures = {
            executor.submit(
                fetch_stock_data,
                symbol,
                period=period,
                interval=interval,
                start=start,
                end=end,
                auto_adjust=auto_adjust,
            ): symbol
            for symbol in normalized_symbols
        }

        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results[symbol] = future.result()
            except Exception as exc:
                logger.warning("Failed to fetch data for %s: %s", symbol, exc)

    return results


def normalize_symbols(symbols: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []

    for raw_symbol in symbols:
        for symbol in re.split(r"[\s,]+", str(raw_symbol)):
            cleaned = normalize_symbol(symbol)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)

    return normalized


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def normalize_downloaded_data(data: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if not isinstance(data.columns, pd.MultiIndex):
        return data

    normalized_symbol = normalize_symbol(symbol)
    ticker_level = data.columns.nlevels - 1
    tickers = {
        str(ticker).upper()
        for ticker in data.columns.get_level_values(ticker_level)
    }

    if normalized_symbol in tickers:
        normalized = data.xs(normalized_symbol, axis=1, level=ticker_level)
    elif len(tickers) == 1:
        normalized = data.droplevel(ticker_level, axis=1)
    else:
        raise ValueError(
            f"Expected only data for {normalized_symbol}, but received columns for: {sorted(tickers)}"
        )

    return normalized.sort_index(axis=1)
