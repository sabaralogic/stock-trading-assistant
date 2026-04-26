from __future__ import annotations

import pandas as pd


def evaluate_stock(df: pd.DataFrame, stock: str) -> dict:
    """
    Evaluate a single stock and return signal + score
    """
    if df.empty:
        return None

    latest = df.iloc[-1]

    score = 0
    reasons = []
    rsi_bias = "NEUTRAL"

    # RSI logic
    rsi = latest.get("RSI")
    if pd.notna(rsi):
        if rsi < 30:
            score += 3
            rsi_bias = "BUY"
            reasons.append("RSI strong BUY")

        elif 30 <= rsi < 45:
            score += 1
            rsi_bias = "BUY"
            reasons.append("RSI mild BUY")

        elif 45 <= rsi <= 55:
            reasons.append("RSI neutral zone")

        elif 55 < rsi <= 70:
            reasons.append("RSI elevated but not a sell signal")

        elif rsi > 70:
            score -= 3
            rsi_bias = "SELL"
            reasons.append("RSI strong SELL")

    # Moving average logic
    close = _get_scalar_value(latest, "Close")
    high = _get_scalar_value(latest, "High")
    low = _get_scalar_value(latest, "Low")
    ma50 = _get_scalar_value(latest, "MA50")
    ma200 = _get_scalar_value(latest, "MA200")

    if pd.notna(close) and pd.notna(ma50):
        if close > ma50:
            score += 2
            reasons.append("Above MA50")
            if close > ma50 * 1.02:
                score += 1
                reasons.append("Strong uptrend")
        elif close < ma50:
            score -= 2
            reasons.append("Below MA50")
        else:
            reasons.append("At MA50 (neutral)")

    trend = "NEUTRAL"
    strong_downtrend = False
    if pd.notna(ma50) and pd.notna(ma200):
        if ma50 > ma200:
            trend = "UP"
            reasons.append("Uptrend confirmed")
        elif ma50 < ma200:
            trend = "DOWN"
            strong_downtrend = ma50 < ma200 * 0.98
            reasons.append("Downtrend confirmed")
        else:
            reasons.append("No clear trend")
    else:
        reasons.append("No clear trend")

    if (rsi_bias == "BUY" and trend == "UP") or (rsi_bias == "SELL" and strong_downtrend):
        score += 2
        reasons.append("RSI + Trend aligned")
    elif (rsi_bias == "BUY" and trend == "DOWN") or (rsi_bias == "SELL" and trend == "UP"):
        score -= 4
        reasons.append("RSI conflicts with trend")

    if trend == "UP":
        if rsi_bias == "BUY" or (pd.notna(close) and pd.notna(ma50) and close > ma50):
            score += 2
            reasons.append("Trend supports BUY")
    elif trend == "DOWN" and rsi_bias == "BUY":
        score -= 2

    overextended_move = False
    if pd.notna(rsi) and rsi > 65:
        overextended_move = True
    if pd.notna(close) and pd.notna(ma50) and close > ma50 * 1.05:
        overextended_move = True

    volatility_risk = False
    daily_range = pd.NA
    if pd.notna(high) and pd.notna(low) and pd.notna(close) and close != 0:
        daily_range = (high - low) / close
        if pd.notna(daily_range) and daily_range > 0.03:
            volatility_risk = True

    momentum = pd.NA
    close_series = df.get("Close")
    if close_series is not None and len(close_series) >= 4:
        momentum = close_series.iloc[-1] - close_series.iloc[-4]
        if pd.notna(momentum):
            if momentum > 0:
                score += 1
                reasons.append("Momentum supports direction")
            elif momentum < 0:
                score -= 1
                reasons.append("Momentum supports direction")

    # Final signal
    if score >= 3:
        if volatility_risk:
            reasons.append("High volatility risk")
            score -= 2
            signal = "HOLD"
        elif overextended_move:
            reasons.append("Overextended move, skipping")
            score -= 2
            signal = "HOLD"
        elif trend == "UP":
            signal = "BUY"
        else:
            score -= 1
            signal = "HOLD"
    elif score <= -3:
        if volatility_risk:
            reasons.append("High volatility risk")
            score += 2
            signal = "HOLD"
        elif strong_downtrend and pd.notna(rsi) and rsi > 70:
            signal = "SELL"
            reasons.append("Strong downtrend sell")
        else:
            score += 1
            signal = "HOLD"
    else:
        signal = "HOLD"

    if not reasons:
        reasons.append("No signal drivers")

    return {
        "stock": stock,
        "signal": signal,
        "score": score,
        "rsi": rsi,
        "close": close,
        "trend": trend,
        "reasons": reasons
    }


def rank_stocks(results: list, top_n: int = 5) -> list:
    """
    Sort stocks by score and return top N
    """
    results = [r for r in results if r is not None]

    return sorted(results, key=lambda x: x["score"], reverse=True)[:top_n]


def _get_scalar_value(row: pd.Series, key: str):
    value = row.get(key)
    if isinstance(value, pd.Series):
        if value.empty:
            return pd.NA
        if len(value) != 1:
            raise ValueError(f"Expected a single value for '{key}', but found {len(value)} values.")
        return value.iloc[0]
    return value
