from __future__ import annotations

import pandas as pd


def add_rsi(data: pd.DataFrame, window: int = 14, price_column: str = "Close") -> pd.DataFrame:
    if window < 1:
        raise ValueError("window must be at least 1")

    result = data.copy()
    price_series = _get_price_series(result, price_column)
    delta = price_series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/window, adjust=False).mean()

    rs = avg_gain / avg_loss
    result["RSI"] = 100 - (100 / (1 + rs))

    return result

def add_moving_averages(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    close_series = _get_price_series(result, "Close")
    result["MA50"] = close_series.rolling(window=50).mean()
    result["MA200"] = close_series.rolling(window=200).mean()
    return result


def _get_price_series(data: pd.DataFrame, price_column: str) -> pd.Series:
    if price_column not in data.columns:
        raise KeyError(f"Missing required column: {price_column}")

    selected = data[price_column]
    if isinstance(selected, pd.DataFrame):
        if selected.shape[1] != 1:
            raise ValueError(
                f"Expected a single '{price_column}' series, but found {selected.shape[1]} columns."
            )
        return selected.iloc[:, 0]

    return selected
