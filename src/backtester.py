from __future__ import annotations

from typing import Iterable

import pandas as pd

from src.indicators import add_moving_averages, add_rsi
from src.strategy import evaluate_stock


MIN_LOOKBACK = 50
STOP_LOSS_PCT = 0.02
TRAILING_STOP_PCT = 0.05
MAX_HOLD_DAYS = 5


def backtest_stock(data: pd.DataFrame, stock: str) -> tuple[list[dict], float]:
    if data is None or data.empty or "Close" not in data.columns:
        return [], 0.0

    prepared = _prepare_historical_data(data)
    full_ind = add_moving_averages(add_rsi(prepared))

    results = []
    graded_predictions = 0
    correct_predictions = 0

    i = MIN_LOOKBACK - 1

    while i < len(prepared) - 1:
        history_with_indicators = full_ind.iloc[: i + 1]

        prediction = evaluate_stock(history_with_indicators, stock)
        if not prediction:
            i += 1
            continue

        signal = str(prediction.get("signal", "HOLD")).upper()
        if signal == "HOLD":
            i += 1
            continue

        entry_row = prepared.iloc[i]
        entry_price = _coerce_price(entry_row.get("Close"))

        stop_loss = (
            entry_price * (1 - STOP_LOSS_PCT)
            if signal == "BUY"
            else entry_price * (1 + STOP_LOSS_PCT)
        )

        exit_price = None
        exit_index = None
        stop_loss_triggered = False

        highest_price = entry_price
        lowest_price = entry_price

        # 🔁 HOLD LOOP
        for j in range(i + 1, min(i + 1 + MAX_HOLD_DAYS, len(prepared))):
            day = prepared.iloc[j]

            open_price = _coerce_price(day.get("Open"))
            high = _coerce_price(day.get("High"))
            low = _coerce_price(day.get("Low"))
            close = _coerce_price(day.get("Close"))

            # STEP 1: update extremes
            if signal == "BUY" and pd.notna(high):
                highest_price = max(highest_price, high)

            if signal == "SELL" and pd.notna(low):
                lowest_price = min(lowest_price, low)

            # STEP 2: compute trailing stop
            if signal == "BUY":
                trailing_stop = highest_price * (1 - TRAILING_STOP_PCT)
                trailing_stop = max(stop_loss, trailing_stop)
            else:
                trailing_stop = lowest_price * (1 + TRAILING_STOP_PCT)
                trailing_stop = min(stop_loss, trailing_stop)

            # STEP 3: gap exit
            if signal == "BUY" and pd.notna(open_price) and open_price <= trailing_stop:
                exit_price = open_price
                exit_index = j
                break

            if signal == "SELL" and pd.notna(open_price) and open_price >= trailing_stop:
                exit_price = open_price
                exit_index = j
                break

            # STEP 4: intraday exit
            if signal == "BUY" and pd.notna(low) and low <= trailing_stop:
                exit_price = trailing_stop
                exit_index = j
                break

            if signal == "SELL" and pd.notna(high) and high >= trailing_stop:
                exit_price = trailing_stop
                exit_index = j
                break

            # STEP 5: reverse signal
            sub_ind = full_ind.iloc[: j + 1]
            new_signal = evaluate_stock(sub_ind, stock).get("signal", "HOLD")

            if new_signal != signal and new_signal != "HOLD":
                exit_price = close
                exit_index = j
                break

        # fallback exit
        if exit_price is None:
            exit_index = min(i + MAX_HOLD_DAYS, len(prepared) - 1)
            exit_price = _coerce_price(prepared.iloc[exit_index].get("Close"))

        # return calculation
        if signal == "BUY":
            change_pct = ((exit_price - entry_price) / entry_price) * 100
        else:
            change_pct = ((entry_price - exit_price) / entry_price) * 100

        result = {
            "date": _format_date(entry_row.name),
            "stock": stock,
            "signal": signal,
            "price": entry_price,
            "exit_price": exit_price,
            "exit_date": _format_date(prepared.iloc[exit_index].name),
            "score": prediction.get("score"),
            "rsi": prediction.get("rsi"),
            "reasons": prediction.get("reasons", []),
            "change_pct": change_pct,
            "stop_loss_triggered": stop_loss_triggered,
            "correct": change_pct > 0,
            "status": "CORRECT" if change_pct > 0 else "WRONG",
        }

        graded_predictions += 1
        if result["correct"]:
            correct_predictions += 1

        results.append(result)

        i = exit_index + 1

    accuracy = (correct_predictions / graded_predictions * 100) if graded_predictions else 0.0
    return results, accuracy


def backtest_portfolio(historical_data: dict[str, pd.DataFrame]) -> tuple[list[dict], float]:
    all_results: list[dict] = []
    graded_predictions = 0
    correct_predictions = 0

    for stock, data in sorted((historical_data or {}).items()):
        stock_results, _ = backtest_stock(data, stock)
        all_results.extend(stock_results)

        for result in stock_results:
            if result["correct"] is None:
                continue
            graded_predictions += 1
            if result["correct"]:
                correct_predictions += 1

    accuracy = (correct_predictions / graded_predictions * 100) if graded_predictions else 0.0
    return all_results, accuracy


def backtest_results_to_frame(results: Iterable[dict]) -> pd.DataFrame:
    columns = [
        "date",
        "stock",
        "signal",
        "price",
        "exit_price",
        "exit_date",
        "change_pct",
        "score",
        "rsi",
        "reasons",
        "stop_loss_triggered",
        "correct",
        "status",
    ]
    return pd.DataFrame(list(results or []), columns=columns)


def _prepare_historical_data(data: pd.DataFrame) -> pd.DataFrame:
    prepared = data.copy()
    if not isinstance(prepared.index, pd.DatetimeIndex):
        prepared.index = pd.to_datetime(prepared.index, errors="coerce")
    prepared = prepared[prepared.index.notna()]
    prepared = prepared.sort_index()
    return prepared


def _format_date(value) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return ""
    return timestamp.date().isoformat()


def _coerce_price(value) -> float:
    numeric_value = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric_value):
        return float("nan")
    return float(numeric_value)