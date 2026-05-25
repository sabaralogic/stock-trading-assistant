from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd


PREDICTIONS_FILE = Path("data/predictions.csv")
PREDICTION_COLUMNS = ["date", "stock", "signal", "price"]


def save_predictions(results: Iterable[dict]) -> pd.DataFrame:
    rows = []
    today = date.today().isoformat()

    for result in results or []:
        if not result:
            continue

        stock = result.get("stock")
        signal = result.get("signal")
        price = _coerce_price(result.get("price", result.get("close")))

        if not stock or signal is None or pd.isna(price):
            continue

        rows.append(
            {
                "date": today,
                "stock": str(stock).upper(),
                "signal": str(signal).upper(),
                "price": price,
            }
        )

    new_predictions = pd.DataFrame(rows, columns=PREDICTION_COLUMNS)
    if new_predictions.empty:
        return new_predictions

    PREDICTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if PREDICTIONS_FILE.exists() and PREDICTIONS_FILE.stat().st_size > 0:
        existing = pd.read_csv(PREDICTIONS_FILE)
        combined = pd.concat([existing, new_predictions], ignore_index=True)
    else:
        combined = new_predictions

    combined.to_csv(PREDICTIONS_FILE, index=False)
    return new_predictions


def load_previous_predictions() -> pd.DataFrame:
    if not PREDICTIONS_FILE.exists() or PREDICTIONS_FILE.stat().st_size == 0:
        return pd.DataFrame(columns=PREDICTION_COLUMNS)

    predictions = pd.read_csv(PREDICTIONS_FILE)
    if predictions.empty:
        return pd.DataFrame(columns=PREDICTION_COLUMNS)

    predictions = predictions.copy()
    predictions["date"] = pd.to_datetime(predictions["date"], errors="coerce")
    predictions = predictions.dropna(subset=["date"])
    if predictions.empty:
        return pd.DataFrame(columns=PREDICTION_COLUMNS)

    unique_dates = sorted(predictions["date"].unique())
    if len(unique_dates) < 2:
        return pd.DataFrame(columns=PREDICTION_COLUMNS)
    previous_date = unique_dates[-2]

    latest_predictions = predictions.loc[
        predictions["date"] == previous_date
    ].copy()
    latest_predictions["date"] = latest_predictions["date"].dt.date.astype(str)
    
    return latest_predictions.reset_index(drop=True)


def evaluate_predictions(
    previous_df: pd.DataFrame,
    current_data: dict[str, pd.DataFrame],
) -> tuple[list[dict], float]:
    if previous_df is None or previous_df.empty:
        return [], 0.0

    evaluations = []
    graded_predictions = 0
    correct_predictions = 0

    for row in previous_df.to_dict(orient="records"):
        stock = str(row.get("stock", "")).upper()
        signal = str(row.get("signal", "")).upper()
        old_price = _coerce_price(row.get("price"))

        if not stock or signal == "HOLD" or pd.isna(old_price):
            continue

        current_frame = current_data.get(stock)
        new_price = _extract_latest_price(current_frame)

        evaluation = {
            "date": row.get("date"),
            "stock": stock,
            "signal": signal,
            "old_price": old_price,
            "new_price": new_price,
            "correct": None,
            "status": "missing_current_data",
        }

        if pd.isna(new_price):
            evaluations.append(evaluation)
            continue

        graded_predictions += 1

        if signal == "BUY":
            is_correct = bool(new_price > old_price)
        elif signal == "SELL":
            is_correct = bool(new_price < old_price)
        else:
            evaluation["status"] = "ignored"
            evaluations.append(evaluation)
            continue

        if is_correct:
            correct_predictions += 1

        evaluation["correct"] = is_correct
        evaluation["status"] = "correct" if is_correct else "incorrect"
        evaluations.append(evaluation)

    accuracy = (correct_predictions / graded_predictions * 100) if graded_predictions else 0.0
    return evaluations, accuracy


def _extract_latest_price(data: pd.DataFrame | None) -> float:
    if data is None or data.empty:
        return float("nan")
    if "Close" not in data.columns:
        return float("nan")

    close_series = data["Close"]
    if isinstance(close_series, pd.DataFrame):
        if close_series.empty or close_series.shape[1] == 0:
            return float("nan")
        close_series = close_series.iloc[:, 0]

    latest_price = close_series.iloc[-1]
    return _coerce_price(latest_price)


def _coerce_price(value) -> float:
    numeric_value = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric_value):
        return float("nan")
    return float(numeric_value)
