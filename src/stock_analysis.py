from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import pandas as pd

from src.indicators import add_moving_averages, add_rsi
from src.strategy import evaluate_stock


ANALYSIS_COLUMNS = ["Open", "High", "Low", "Close", "Volume", "RSI", "MA50", "MA200"]
DEFAULT_TURNING_POINT_THRESHOLD_PCT = 10.0
DEFAULT_HEURISTIC_FORECAST_DAYS = 30
HEURISTIC_REFINEMENT_WINDOWS: list[tuple[str, pd.Timedelta, float]] = [
    ("1m", pd.Timedelta(days=31), 5.0),
    ("3m", pd.Timedelta(days=92), 4.0),
    ("6m", pd.Timedelta(days=183), 3.0),
    ("1y", pd.Timedelta(days=365), 2.0),
    ("5y", pd.Timedelta(days=365 * 5), 1.0),
]


def analyze_stock(
    data: pd.DataFrame,
    stock: str,
    *,
    turning_point_threshold_pct: float = DEFAULT_TURNING_POINT_THRESHOLD_PCT,
) -> dict[str, Any]:
    if data is None or data.empty:
        raise ValueError(f"No data available for {stock}")

    enriched = add_moving_averages(add_rsi(data.copy()))
    evaluation = evaluate_stock(enriched, stock)
    latest = enriched.iloc[-1]

    close = _get_float(latest.get("Close"))
    high = _get_float(latest.get("High"))
    low = _get_float(latest.get("Low"))
    ma50 = _get_float(latest.get("MA50"))
    ma200 = _get_float(latest.get("MA200"))
    rsi = _get_float(latest.get("RSI"))

    change_1d = _pct_change(enriched["Close"], 1)
    change_5d = _pct_change(enriched["Close"], 5)
    change_20d = _pct_change(enriched["Close"], 20)
    daily_range_pct = _pct_range(high, low, close)
    period_high = _get_float(enriched["High"].max())
    period_low = _get_float(enriched["Low"].min())
    avg_volume_20 = _get_float(enriched["Volume"].tail(20).mean())

    insights = list(evaluation.get("reasons", [])) if evaluation else []
    insights.extend(
        build_stock_insights(
            close=close,
            ma50=ma50,
            ma200=ma200,
            rsi=rsi,
            change_1d=change_1d,
            change_5d=change_5d,
            daily_range_pct=daily_range_pct,
        )
    )
    insights = dedupe_preserve_order(insights)

    recent_data = enriched[[column for column in ANALYSIS_COLUMNS if column in enriched.columns]].tail(10).copy()
    raw_turning_points = _find_raw_turning_points(enriched)
    chart_turning_points = _append_latest_close_point(
        raw_turning_points,
        enriched.index.max(),
        close,
    )
    turning_points = find_turning_points(
        enriched,
        min_swing_pct=turning_point_threshold_pct,
    )
    predicted_turning_points = predict_next_turning_points(
        enriched["Close"],
        latest_available_date=enriched.index.max(),
        latest_available_price=close,
        count=DEFAULT_HEURISTIC_FORECAST_DAYS,
    )
    heuristic_stages = predict_refined_heuristic_stages(
        enriched["Close"],
        latest_available_date=enriched.index.max(),
        latest_available_price=close,
        count=DEFAULT_HEURISTIC_FORECAST_DAYS,
    )
    predicted_turning_point = predicted_turning_points[0] if predicted_turning_points else None
    expected_gain = compute_expected_gain_metric(
        close=close,
        latest_actual_date=enriched.index.max(),
        predicted_turning_points=predicted_turning_points,
    )

    return {
        "stock": stock,
        "data": enriched,
        "recent_data": recent_data,
        "all_turning_points": raw_turning_points,
        "chart_turning_points": chart_turning_points,
        "turning_points": turning_points,
        "predicted_turning_point": predicted_turning_point,
        "predicted_turning_points": predicted_turning_points,
        "heuristic_stages": heuristic_stages,
        "evaluation": evaluation,
        "summary": {
            "close": close,
            "high": high,
            "low": low,
            "rsi": rsi,
            "ma50": ma50,
            "ma200": ma200,
            "trend": evaluation.get("trend") if evaluation else "N/A",
            "signal": evaluation.get("signal") if evaluation else "HOLD",
            "score": evaluation.get("score") if evaluation else 0,
            "change_1d": change_1d,
            "change_5d": change_5d,
            "change_20d": change_20d,
            "daily_range_pct": daily_range_pct,
            "period_high": period_high,
            "period_low": period_low,
            "avg_volume_20": avg_volume_20,
            "turning_point_threshold_pct": turning_point_threshold_pct,
            "expected_xirr": expected_gain["annualized_gain"],
            "expected_entry_price": expected_gain["entry_price"],
            "expected_entry_date": expected_gain["entry_date"],
            "expected_low_price": expected_gain["low_price"],
            "expected_low_date": expected_gain["low_date"],
            "expected_peak_price": expected_gain["peak_price"],
            "expected_peak_date": expected_gain["peak_date"],
            "expected_peak_days": expected_gain["days_to_peak"],
        },
        "insights": insights,
    }


def compute_expected_gain_metric(
    *,
    close: float,
    latest_actual_date,
    predicted_turning_points: list[dict[str, Any]],
) -> dict[str, Any]:
    if pd.isna(close) or not predicted_turning_points:
        return {
            "annualized_gain": None,
            "entry_price": None,
            "entry_date": None,
            "low_price": None,
            "low_date": None,
            "peak_price": None,
            "peak_date": None,
            "days_to_peak": None,
        }

    latest_date = pd.Timestamp(latest_actual_date).normalize()
    future_points = []
    for point in predicted_turning_points:
        point_date = pd.Timestamp(point.get("date")).normalize()
        point_price = _get_float(point.get("price"))
        if pd.isna(point_price) or point_date <= latest_date:
            continue
        future_points.append({"date": point_date, "price": point_price})

    if not future_points:
        return {
            "annualized_gain": None,
            "entry_price": None,
            "entry_date": None,
            "low_price": None,
            "low_date": None,
            "peak_price": None,
            "peak_date": None,
            "days_to_peak": None,
        }

    target_low = None
    target_peak = None
    best_gain_pct = None

    for low_index, low_point in enumerate(future_points):
        for peak_point in future_points[low_index + 1 :]:
            if peak_point["date"] <= low_point["date"]:
                continue

            entry_price = min(close, low_point["price"])
            entry_date = latest_date if close < low_point["price"] else low_point["date"]
            days_to_peak = int((peak_point["date"] - entry_date).days)
            if days_to_peak <= 0:
                continue

            gain_pct = ((peak_point["price"] - entry_price) / entry_price) * 100
            if best_gain_pct is None or gain_pct > best_gain_pct:
                best_gain_pct = gain_pct
                target_low = low_point
                target_peak = peak_point

    if target_low is None or target_peak is None:
        target_peak = max(future_points, key=lambda point: (point["price"], point["date"]))
        entry_price = close
        entry_date = latest_date
        days_to_peak = int((target_peak["date"] - entry_date).days)
        if days_to_peak <= 0 or target_peak["price"] <= entry_price:
            return {
                "annualized_gain": None,
                "entry_price": None,
                "entry_date": None,
                "low_price": None,
                "low_date": None,
                "peak_price": None,
                "peak_date": None,
                "days_to_peak": None,
            }
        return {
            "annualized_gain": (((target_peak["price"] - entry_price) / entry_price) / days_to_peak) * 365 * 100,
            "entry_price": entry_price,
            "entry_date": entry_date,
            "low_price": entry_price,
            "low_date": entry_date,
            "peak_price": target_peak["price"],
            "peak_date": target_peak["date"],
            "days_to_peak": days_to_peak,
        }

    if close < target_low["price"]:
        entry_price = close
        entry_date = latest_date
    else:
        entry_price = target_low["price"]
        entry_date = target_low["date"]

    days_to_peak = int((target_peak["date"] - entry_date).days)
    if days_to_peak <= 0:
        return {
            "annualized_gain": None,
            "entry_price": entry_price,
            "entry_date": entry_date,
            "low_price": target_low["price"],
            "low_date": target_low["date"],
            "peak_price": target_peak["price"],
            "peak_date": target_peak["date"],
            "days_to_peak": None,
        }

    annualized_gain = (
        ((target_peak["price"] - entry_price) / entry_price)
        / days_to_peak
        * 365
        * 100
    )

    return {
        "annualized_gain": annualized_gain,
        "entry_price": entry_price,
        "entry_date": entry_date,
        "low_price": target_low["price"],
        "low_date": target_low["date"],
        "peak_price": target_peak["price"],
        "peak_date": target_peak["date"],
        "days_to_peak": days_to_peak,
    }


def attach_analysis_metrics_to_evaluation(
    evaluation: dict[str, Any] | None,
    analysis: dict[str, Any],
) -> dict[str, Any] | None:
    if not evaluation:
        return evaluation

    summary = analysis.get("summary", {})
    evaluation["expected_xirr"] = summary.get("expected_xirr")
    evaluation["expected_entry_price"] = summary.get("expected_entry_price")
    evaluation["expected_entry_date"] = summary.get("expected_entry_date")
    evaluation["expected_low_price"] = summary.get("expected_low_price")
    evaluation["expected_low_date"] = summary.get("expected_low_date")
    evaluation["expected_peak_price"] = summary.get("expected_peak_price")
    evaluation["expected_peak_date"] = summary.get("expected_peak_date")
    evaluation["expected_peak_days"] = summary.get("expected_peak_days")
    return evaluation


def build_stock_insights(
    *,
    close: float,
    ma50: float,
    ma200: float,
    rsi: float,
    change_1d: float,
    change_5d: float,
    daily_range_pct: float,
) -> list[str]:
    insights: list[str] = []

    if pd.notna(close) and pd.notna(ma50):
        if close > ma50:
            insights.append("Price is trading above MA50")
        elif close < ma50:
            insights.append("Price is trading below MA50")

    if pd.notna(ma50) and pd.notna(ma200):
        if ma50 > ma200:
            insights.append("Medium-term trend remains constructive")
        elif ma50 < ma200:
            insights.append("Medium-term trend remains weak")

    if pd.notna(rsi):
        if rsi < 30:
            insights.append("RSI is in oversold territory")
        elif rsi > 70:
            insights.append("RSI is in overbought territory")
        elif 45 <= rsi <= 55:
            insights.append("RSI is balanced and not giving a strong directional edge")

    if pd.notna(change_1d):
        if change_1d >= 2:
            insights.append("Strong positive one-day move")
        elif change_1d <= -2:
            insights.append("Sharp negative one-day move")

    if pd.notna(change_5d):
        if change_5d >= 5:
            insights.append("Short-term momentum is strong over 5 days")
        elif change_5d <= -5:
            insights.append("Short-term momentum is weak over 5 days")

    if pd.notna(daily_range_pct) and daily_range_pct > 3:
        insights.append("Recent candle range suggests elevated volatility")

    return insights


def format_stock_analysis(analysis: dict[str, Any]) -> str:
    summary = analysis["summary"]
    evaluation = analysis["evaluation"]
    recent_data = analysis["recent_data"]
    insights = analysis["insights"]
    turning_points = analysis["turning_points"]
    predicted_turning_points = analysis.get("predicted_turning_points", [])

    lines = []
    lines.append(f"\nSingle Stock Analysis: {analysis['stock']}\n")
    lines.append(
        f"Signal: {summary['signal']} | Score: {summary['score']} | Trend: {summary['trend']} | RSI: {_fmt(summary['rsi'])}"
    )
    lines.append(
        f"Close: {_fmt(summary['close'])} | High: {_fmt(summary['high'])} | Low: {_fmt(summary['low'])}"
    )
    lines.append(
        f"MA50: {_fmt(summary['ma50'])} | MA200: {_fmt(summary['ma200'])} | Avg Vol(20): {_fmt(summary['avg_volume_20'], digits=0)}"
    )
    lines.append(
        f"1D: {_fmt_pct(summary['change_1d'])} | 5D: {_fmt_pct(summary['change_5d'])} | 20D: {_fmt_pct(summary['change_20d'])} | Range: {_fmt_pct(summary['daily_range_pct'])}"
    )
    lines.append(
        f"Period High: {_fmt(summary['period_high'])} | Period Low: {_fmt(summary['period_low'])}"
    )
    lines.append(
        f"Turning Point Filter: {_fmt_pct(summary['turning_point_threshold_pct'])} minimum swing"
    )

    if insights:
        lines.append("\nInsights:")
        for insight in insights:
            lines.append(f"- {insight}")

    if evaluation:
        lines.append("\nStrategy Reasons:")
        for reason in evaluation.get("reasons", []):
            lines.append(f"- {reason}")

    if turning_points:
        lines.append("\nPeaks And Lows:")
        for point in turning_points:
            lines.append(
                f"- {point['type']}: {point['date']} at {_fmt(point['price'])} "
                f"({point['swing_pct']:+.2f}%)"
            )

    if predicted_turning_points:
        lines.append("\nProjected Next Turning Points:")
        for index, predicted_turning_point in enumerate(predicted_turning_points, start=1):
            lines.append(
                f"- Step {index}: {predicted_turning_point['type']} on {predicted_turning_point['date']} at "
                f"{_fmt(predicted_turning_point['price'])} "
                f"({predicted_turning_point['projected_swing_pct']:+.2f}%, heuristic)"
            )

    if not recent_data.empty:
        lines.append("\nRecent Data:")
        lines.append(recent_data.to_string())

    return "\n".join(lines)


def save_stock_analysis_report(analysis: dict[str, Any]) -> Path:
    stock = str(analysis["stock"]).replace(".", "_")
    output_path = Path(f"stock_analysis_{stock}.html")
    output_path.write_text(generate_stock_analysis_html(analysis), encoding="utf-8")
    return output_path


def generate_stock_analysis_html(analysis: dict[str, Any]) -> str:
    summary = analysis["summary"]
    insights = analysis["insights"]
    evaluation = analysis["evaluation"]
    turning_points = analysis["turning_points"]
    predicted_turning_points = analysis.get("predicted_turning_points", [])
    chart_svg = generate_stock_chart_svg(analysis)

    reasons_html = "".join(
        f"<li>{html.escape(reason)}</li>" for reason in (evaluation.get("reasons", []) if evaluation else [])
    )
    insights_html = "".join(f"<li>{html.escape(insight)}</li>" for insight in insights)
    turning_points_html = generate_turning_points_table_html(turning_points)
    predicted_turning_point_html = generate_predicted_turning_point_html(predicted_turning_points)

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Stock Analysis - {html.escape(str(analysis["stock"]))}</title>
  <style>
    body {{
      background: #0f172a;
      color: #e2e8f0;
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 24px;
    }}
    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
    }}
    h1 {{
      margin: 0 0 12px 0;
      color: #38bdf8;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }}
    .metric {{
      background: #1e293b;
      border-radius: 10px;
      padding: 14px;
    }}
    .metric .label {{
      color: #94a3b8;
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .metric .value {{
      color: #f8fafc;
      font-size: 18px;
      font-weight: bold;
    }}
    .panel {{
      background: #1e293b;
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 18px;
    }}
    .panel h2 {{
      margin: 0 0 12px 0;
      font-size: 18px;
      color: #f8fafc;
    }}
    .two-col {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
    li {{
      margin-bottom: 8px;
      line-height: 1.4;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      padding: 8px 10px;
      border-bottom: 1px solid #334155;
      text-align: right;
    }}
    th:first-child, td:first-child {{
      text-align: left;
    }}
    .legend {{
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      margin-top: 10px;
      color: #cbd5e1;
      font-size: 12px;
    }}
    .dot {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      margin-right: 6px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Single Stock Analysis: {html.escape(str(analysis["stock"]))}</h1>

    <div class="summary">
      <div class="metric"><div class="label">Signal</div><div class="value">{html.escape(str(summary["signal"]))}</div></div>
      <div class="metric"><div class="label">Trend</div><div class="value">{html.escape(str(summary["trend"]))}</div></div>
      <div class="metric"><div class="label">Score</div><div class="value">{html.escape(str(summary["score"]))}</div></div>
      <div class="metric"><div class="label">RSI</div><div class="value">{_fmt(summary["rsi"])}</div></div>
      <div class="metric"><div class="label">Close</div><div class="value">{_fmt(summary["close"])}</div></div>
      <div class="metric"><div class="label">MA50</div><div class="value">{_fmt(summary["ma50"])}</div></div>
      <div class="metric"><div class="label">MA200</div><div class="value">{_fmt(summary["ma200"])}</div></div>
      <div class="metric"><div class="label">Turning Point Filter</div><div class="value">{_fmt_pct(summary["turning_point_threshold_pct"])}</div></div>
    </div>

    <div class="panel">
      <h2>Price Chart With Peaks And Lows</h2>
      {chart_svg}
      <div class="legend">
        <span><span class="dot" style="background:#94a3b8;"></span>All turning-point path</span>
        <span><span class="dot" style="background:#38bdf8;"></span>Filtered turning-point path</span>
        <span><span class="dot" style="background:#22c55e;"></span>Projected next point</span>
      </div>
    </div>

    <div class="panel">
      <h2>Filtered Peaks And Lows</h2>
      {turning_points_html}
    </div>

    <div class="panel">
      <h2>Projected Next Turning Points</h2>
      {predicted_turning_point_html}
    </div>

    <div class="two-col">
      <div class="panel">
        <h2>Insights</h2>
        <ul>{insights_html}</ul>
      </div>
      <div class="panel">
        <h2>Strategy Reasons</h2>
        <ul>{reasons_html}</ul>
      </div>
    </div>

    <div class="panel">
      <h2>Recent Data</h2>
      {analysis["recent_data"].to_html(classes="", border=0)}
    </div>
  </div>
</body>
</html>
"""


def generate_stock_chart_svg(analysis: dict[str, Any]) -> str:
    data = analysis["data"]
    all_turning_points = analysis["all_turning_points"]
    turning_points = analysis["turning_points"]
    predicted_turning_points = analysis.get("predicted_turning_points", [])
    close_series = data["Close"].dropna()

    width = 1100
    height = 420
    margin_left = 60
    margin_right = 30
    margin_top = 20
    margin_bottom = 40
    inner_width = width - margin_left - margin_right
    inner_height = height - margin_top - margin_bottom

    if close_series.empty or not all_turning_points:
        return "<div>No chart data available.</div>"

    all_chart_points = []
    for point in all_turning_points:
        point_date = pd.to_datetime(point["date"], errors="coerce")
        point_price = float(point["price"])
        if pd.isna(point_date) or pd.isna(point_price):
            continue
        all_chart_points.append((point_date, point_price, point["type"]))

    filtered_chart_points = []
    for point in turning_points:
        point_date = pd.to_datetime(point["date"], errors="coerce")
        point_price = float(point["price"])
        if pd.isna(point_date) or pd.isna(point_price):
            continue
        filtered_chart_points.append((point_date, point_price, point["type"]))

    projected_chart_points = []
    for point in predicted_turning_points:
        point_date = pd.to_datetime(point.get("date"), errors="coerce")
        point_price = _get_float(point.get("price"))
        if pd.isna(point_date) or pd.isna(point_price):
            continue
        projected_chart_points.append((point_date, point_price, str(point.get("type", ""))))

    if not all_chart_points:
        return "<div>No turning-point chart data available.</div>"

    chart_domain_points = all_chart_points + projected_chart_points

    min_price = min(price for _, price, _ in chart_domain_points)
    max_price = max(price for _, price, _ in chart_domain_points)
    if max_price == min_price:
        max_price += 1
        min_price -= 1

    min_date = min(point_date for point_date, _, _ in chart_domain_points)
    max_date = max(point_date for point_date, _, _ in chart_domain_points)
    total_seconds = max((max_date - min_date).total_seconds(), 1)

    def x_pos(point_date: pd.Timestamp) -> float:
        if total_seconds == 0:
            return margin_left + inner_width / 2
        elapsed = (point_date - min_date).total_seconds()
        return margin_left + (elapsed / total_seconds) * inner_width

    def y_pos(price: float) -> float:
        return margin_top + (max_price - price) / (max_price - min_price) * inner_height

    all_points = " ".join(
        f"{x_pos(point_date):.2f},{y_pos(price):.2f}"
        for point_date, price, _ in all_chart_points
    )
    filtered_points = " ".join(
        f"{x_pos(point_date):.2f},{y_pos(price):.2f}"
        for point_date, price, _ in filtered_chart_points
    )

    date_axis_points = sorted(chart_domain_points, key=lambda point: point[0])
    date_labels = []
    tick_positions = [0, len(date_axis_points) // 3, (2 * len(date_axis_points)) // 3, len(date_axis_points) - 1]
    for pos in sorted(set(tick_positions)):
        label = _format_date(date_axis_points[pos][0])
        date_labels.append(
            f'<text x="{x_pos(date_axis_points[pos][0]):.2f}" y="{height - 12}" fill="#94a3b8" font-size="11" text-anchor="middle">{html.escape(label)}</text>'
        )

    price_labels = []
    for fraction in [0, 0.25, 0.5, 0.75, 1]:
        price = min_price + (max_price - min_price) * fraction
        y = y_pos(price)
        price_labels.append(
            f'<text x="10" y="{y + 4:.2f}" fill="#94a3b8" font-size="11">{_fmt(price)}</text>'
        )
        price_labels.append(
            f'<line x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#334155" stroke-width="1" />'
        )

    filtered_markers = []
    for point_date, point_price, point_type in filtered_chart_points:
        cx = x_pos(point_date)
        cy = y_pos(point_price)
        filtered_markers.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="6" fill="#38bdf8" stroke="#0f172a" stroke-width="2" />'
        )

    projected_elements = []
    if predicted_turning_points and filtered_chart_points:
        last_date, last_price, _ = filtered_chart_points[-1]
        for predicted_turning_point in predicted_turning_points:
            predicted_date = pd.to_datetime(predicted_turning_point["date"], errors="coerce")
            predicted_price = _get_float(predicted_turning_point["price"])
            if pd.isna(predicted_date) or pd.isna(predicted_price):
                continue
            projected_elements.append(
                f'<line x1="{x_pos(last_date):.2f}" y1="{y_pos(last_price):.2f}" '
                f'x2="{x_pos(predicted_date):.2f}" y2="{y_pos(predicted_price):.2f}" '
                f'stroke="#22c55e" stroke-width="3" stroke-dasharray="8 6" />'
            )
            projected_elements.append(
                f'<circle cx="{x_pos(predicted_date):.2f}" cy="{y_pos(predicted_price):.2f}" '
                f'r="6" fill="#22c55e" stroke="#0f172a" stroke-width="2" />'
            )
            last_date = predicted_date
            last_price = predicted_price

    return f"""
<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#0f172a" rx="10" />
  <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height - margin_bottom}" stroke="#475569" stroke-width="1.5" />
  <line x1="{margin_left}" y1="{height - margin_bottom}" x2="{width - margin_right}" y2="{height - margin_bottom}" stroke="#475569" stroke-width="1.5" />
  {''.join(price_labels)}
  <polyline fill="none" stroke="#94a3b8" stroke-width="2" points="{all_points}" opacity="0.85" />
  <polyline fill="none" stroke="#38bdf8" stroke-width="3" points="{filtered_points}" />
  {''.join(projected_elements)}
  {''.join(filtered_markers)}
  {''.join(date_labels)}
</svg>
"""


def generate_turning_points_table_html(turning_points: list[dict[str, Any]]) -> str:
    if not turning_points:
        return "<div>No filtered turning points available for the selected threshold.</div>"

    rows = []
    for point in turning_points:
        rows.append(
            f"""
            <tr>
              <td>{html.escape(str(point["type"]))}</td>
              <td>{html.escape(str(point["date"]))}</td>
              <td>{_fmt(_get_float(point["price"]))}</td>
              <td>{_fmt_pct(_get_float(point.get("swing_pct")))}</td>
            </tr>
            """
        )

    return f"""
    <table>
      <thead>
        <tr>
          <th>Type</th>
          <th>Date</th>
          <th>Price</th>
          <th>Swing</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """


def generate_predicted_turning_point_html(predicted_turning_points: list[dict[str, Any]]) -> str:
    if not predicted_turning_points:
        return "<div>Not enough filtered turning points to build a projection.</div>"

    rows = []
    for index, predicted_turning_point in enumerate(predicted_turning_points, start=1):
        rows.append(
            f"""
        <tr>
          <td>{index}</td>
          <td>{html.escape(str(predicted_turning_point["type"]))}</td>
          <td>{html.escape(str(predicted_turning_point["date"]))}</td>
          <td>{_fmt(_get_float(predicted_turning_point["price"]))}</td>
          <td>{_fmt_pct(_get_float(predicted_turning_point["projected_swing_pct"]))}</td>
          <td>Heuristic</td>
        </tr>
            """
        )

    return f"""
    <table>
      <thead>
        <tr>
          <th>Step</th>
          <th>Type</th>
          <th>Date</th>
          <th>Price</th>
          <th>Projected Swing</th>
          <th>Method</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """


def _pct_change(series: pd.Series, periods: int) -> float:
    if len(series) <= periods:
        return float("nan")
    current = _get_float(series.iloc[-1])
    previous = _get_float(series.iloc[-(periods + 1)])
    if pd.isna(current) or pd.isna(previous) or previous == 0:
        return float("nan")
    return ((current - previous) / previous) * 100


def _pct_range(high: float, low: float, close: float) -> float:
    if pd.isna(high) or pd.isna(low) or pd.isna(close) or close == 0:
        return float("nan")
    return ((high - low) / close) * 100


def _get_float(value: Any) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return float("nan")
    return float(numeric)


def _fmt(value: float, digits: int = 2) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{value:.{digits}f}"


def _fmt_pct(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{value:+.2f}%"


def _format_date(value: Any) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return ""
    return timestamp.date().isoformat()


def _next_weekday(value: Any) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return timestamp

    while timestamp.weekday() >= 5:
        timestamp = timestamp + pd.Timedelta(days=1)

    return timestamp


def _business_days_between(start: Any, end: Any) -> int:
    start_ts = pd.to_datetime(start, errors="coerce")
    end_ts = pd.to_datetime(end, errors="coerce")
    if pd.isna(start_ts) or pd.isna(end_ts):
        return 1

    start_day = start_ts.normalize()
    end_day = end_ts.normalize()
    if end_day <= start_day:
        return 1

    business_days = len(pd.bdate_range(start=start_day, end=end_day)) - 1
    return max(business_days, 1)


def _add_business_days(start: Any, days: int) -> pd.Timestamp:
    start_ts = pd.to_datetime(start, errors="coerce")
    if pd.isna(start_ts):
        return start_ts

    return start_ts + pd.offsets.BDay(max(int(days), 1))


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _append_latest_close_point(
    turning_points: list[dict[str, Any]],
    latest_date: Any,
    latest_close: Any,
) -> list[dict[str, Any]]:
    if not turning_points:
        return turning_points

    latest_timestamp = pd.to_datetime(latest_date, errors="coerce")
    latest_price = _get_float(latest_close)
    if pd.isna(latest_timestamp) or pd.isna(latest_price):
        return turning_points

    last_point = turning_points[-1]
    last_date = pd.to_datetime(last_point.get("date"), errors="coerce")
    if pd.isna(last_date) or latest_timestamp <= last_date:
        return turning_points

    latest_point = {
        "type": "Latest",
        "date": _format_date(latest_timestamp),
        "price": latest_price,
    }
    return [*turning_points, latest_point]


def find_turning_points(
    data: pd.DataFrame,
    *,
    min_swing_pct: float = DEFAULT_TURNING_POINT_THRESHOLD_PCT,
) -> list[dict[str, Any]]:
    if data is None or data.empty or "Close" not in data.columns:
        return []

    raw_turning_points = _find_raw_turning_points(data)
    return _filter_turning_points_by_swing(raw_turning_points, min_swing_pct)


def _find_raw_turning_points(data: pd.DataFrame) -> list[dict[str, Any]]:
    close_series = data["Close"].dropna()
    if len(close_series) < 3:
        return []

    raw_turning_points: list[dict[str, Any]] = []
    previous_direction = 0

    for index in range(1, len(close_series)):
        current_price = _get_float(close_series.iloc[index])
        previous_price = _get_float(close_series.iloc[index - 1])
        price_delta = current_price - previous_price

        if pd.isna(price_delta) or price_delta == 0:
            continue

        current_direction = 1 if price_delta > 0 else -1
        if previous_direction == 0:
            previous_direction = current_direction
            continue

        if current_direction != previous_direction:
            pivot_index = index - 1
            point_type = "Peak" if previous_direction > 0 else "Low"
            pivot_price = _get_float(close_series.iloc[pivot_index])
            pivot_date = _format_date(close_series.index[pivot_index])
            raw_turning_points.append(
                {
                    "type": point_type,
                    "date": pivot_date,
                    "price": pivot_price,
                }
            )

        previous_direction = current_direction

    return raw_turning_points


def _filter_turning_points_by_swing(
    turning_points: list[dict[str, Any]],
    min_swing_pct: float,
) -> list[dict[str, Any]]:
    if not turning_points:
        return []

    points = [dict(point, swing_pct=float("nan")) for point in turning_points]
    filtered: list[dict[str, Any]] = []
    accepted_anchor = points[0]
    candidate_point = points[0]

    def _append_if_new(point: dict[str, Any]) -> None:
        if not filtered:
            filtered.append(point)
            return

        last = filtered[-1]
        if (
            str(last.get("type", "")) == str(point.get("type", ""))
            and str(last.get("date", "")) == str(point.get("date", ""))
            and round(_get_float(last.get("price")), 6) == round(_get_float(point.get("price")), 6)
        ):
            return

        filtered.append(point)

    for point in points[1:]:
        anchor_price = _get_float(accepted_anchor.get("price"))
        current_price = _get_float(point.get("price"))
        if pd.isna(anchor_price) or pd.isna(current_price) or anchor_price == 0:
            continue

        candidate_price = _get_float(candidate_point.get("price"))
        candidate_type = str(candidate_point.get("type", ""))
        current_type = str(point.get("type", ""))

        if pd.notna(candidate_price):
            if current_type == candidate_type == "Peak" and current_price > candidate_price:
                candidate_point = point
                current_price = _get_float(candidate_point.get("price"))
            elif current_type == candidate_type == "Low" and current_price < candidate_price:
                candidate_point = point
                current_price = _get_float(candidate_point.get("price"))
            elif current_type != candidate_type:
                candidate_point = point
                current_price = _get_float(candidate_point.get("price"))
        else:
            candidate_point = point
            current_price = _get_float(candidate_point.get("price"))

        swing_pct = abs((current_price - anchor_price) / anchor_price) * 100
        if swing_pct < min_swing_pct:
            continue

        accepted_anchor["swing_pct"] = swing_pct
        candidate_point["swing_pct"] = swing_pct
        _append_if_new(accepted_anchor)
        _append_if_new(candidate_point)
        accepted_anchor = candidate_point
        candidate_point = accepted_anchor

    return filtered


def dedupe_turning_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, float]] = set()
    deduped: list[dict[str, Any]] = []
    for point in points:
        key = (
            str(point.get("type", "")),
            str(point.get("date", "")),
            round(_get_float(point.get("price")), 6),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(point)
    return deduped


def predict_next_turning_points(
    close_series: pd.Series,
    latest_available_date: Any | None = None,
    latest_available_price: Any | None = None,
    count: int = 2,
) -> list[dict[str, Any]]:
    heuristic_stages = predict_refined_heuristic_stages(
        close_series,
        latest_available_date=latest_available_date,
        latest_available_price=latest_available_price,
        count=count,
    )
    if heuristic_stages:
        return heuristic_stages[-1]["points"]

    return []


def predict_refined_heuristic_stages(
    close_series: pd.Series,
    latest_available_date: Any | None = None,
    latest_available_price: Any | None = None,
    count: int = 2,
) -> list[dict[str, Any]]:
    normalized_series = _normalize_close_series(close_series)
    if len(normalized_series) < 2:
        return []

    heuristic_stages: list[dict[str, Any]] = []
    active_stage_forecasts: list[dict[str, Any]] = []

    for window_name, window_delta, stage_weight in HEURISTIC_REFINEMENT_WINDOWS:
        cutoff_date = normalized_series.index[-1] - window_delta
        window_series = normalized_series[normalized_series.index >= cutoff_date]
        minimum_window_points = 10
        if len(window_series) < minimum_window_points:
            continue

        stage_points = _forecast_window_pattern(
            full_series=normalized_series,
            current_window_series=window_series,
            count=count,
        )
        if not stage_points:
            continue

        active_stage_forecasts.append(
            {
                "label": window_name,
                "weight": stage_weight,
                "points": stage_points,
            }
        )

        blended_points = _blend_projection_paths(
            active_stage_forecasts,
            count=count,
        )
        if blended_points:
            heuristic_stages.append(
                {
                    "label": " + ".join(stage["label"] for stage in active_stage_forecasts),
                    "points": blended_points,
                }
            )

    return heuristic_stages


def _normalize_close_series(close_series: pd.Series) -> pd.Series:
    if close_series is None:
        return pd.Series(dtype=float)

    normalized = pd.Series(close_series).dropna().copy()
    if normalized.empty:
        return normalized.astype(float)

    normalized.index = pd.to_datetime(normalized.index, errors="coerce")
    normalized = normalized[~normalized.index.isna()]
    normalized = normalized.sort_index()
    return normalized.astype(float)


def _forecast_window_pattern(
    *,
    full_series: pd.Series,
    current_window_series: pd.Series,
    count: int,
) -> list[dict[str, Any]]:
    if len(full_series) < 2 or len(current_window_series) < 2 or count <= 0:
        return []

    values = full_series.to_numpy(dtype=float)
    current_values = current_window_series.to_numpy(dtype=float)
    current_length = len(current_values)
    current_end_index = len(values) - 1
    current_start_index = current_end_index - current_length + 1
    current_date = current_window_series.index[-1]
    current_price = _get_float(current_window_series.iloc[-1])
    current_normalized = current_values / current_values[0]
    current_returns = (current_values[1:] / current_values[:-1]) - 1

    candidates: list[dict[str, Any]] = []
    max_candidate_start = current_start_index - count
    if max_candidate_start <= 0:
        return []

    for candidate_start in range(0, max_candidate_start):
        candidate_end = candidate_start + current_length - 1
        future_end = candidate_end + count
        if future_end >= len(values):
            break

        candidate_values = values[candidate_start : candidate_start + current_length]
        if candidate_values[0] <= 0 or candidate_values[-1] <= 0:
            continue

        candidate_normalized = candidate_values / candidate_values[0]
        candidate_returns = (candidate_values[1:] / candidate_values[:-1]) - 1

        shape_error = ((candidate_normalized - current_normalized) ** 2).mean()
        returns_error = ((candidate_returns - current_returns) ** 2).mean() if len(current_returns) else 0.0
        total_error = float(shape_error + (returns_error * 4))

        future_values = values[candidate_end + 1 : candidate_end + 1 + count]
        future_ratios = future_values / candidate_values[-1]
        recency_bias = 1 + (candidate_start / max(current_start_index, 1))
        candidates.append(
            {
                "error": total_error,
                "score": 1 / max(total_error, 1e-9) * recency_bias,
                "ratios": future_ratios,
            }
        )

    if not candidates:
        return []

    best_candidates = sorted(candidates, key=lambda item: item["error"])[: min(7, len(candidates))]
    total_score = sum(candidate["score"] for candidate in best_candidates)
    if total_score <= 0:
        return []

    projected_points: list[dict[str, Any]] = []
    previous_price = current_price
    for day_offset in range(1, count + 1):
        projected_date = _add_business_days(current_date, day_offset)
        blended_ratio = sum(
            candidate["ratios"][day_offset - 1] * candidate["score"]
            for candidate in best_candidates
        ) / total_score
        projected_price = current_price * blended_ratio
        swing_pct = 0.0 if previous_price == 0 else ((projected_price - previous_price) / previous_price) * 100
        projected_points.append(
            {
                "type": "Projected",
                "date": _format_date(projected_date),
                "price": projected_price,
                "projected_swing_pct": swing_pct,
            }
        )
        previous_price = projected_price

    return projected_points


def _blend_projection_paths(
    stage_forecasts: list[dict[str, Any]],
    *,
    count: int,
) -> list[dict[str, Any]]:
    if not stage_forecasts:
        return []

    blended_points: list[dict[str, Any]] = []
    previous_price: float | None = None
    for point_index in range(count):
        available_stages = [
            stage
            for stage in stage_forecasts
            if len(stage["points"]) > point_index
        ]
        if not available_stages:
            break

        reference_point = available_stages[0]["points"][point_index]
        total_weight = sum(stage["weight"] for stage in available_stages)
        if total_weight <= 0:
            continue

        blended_price = sum(
            stage["points"][point_index]["price"] * stage["weight"]
            for stage in available_stages
        ) / total_weight
        swing_pct = 0.0 if previous_price in (None, 0) else ((blended_price - previous_price) / previous_price) * 100
        blended_points.append(
            {
                "type": "Projected",
                "date": reference_point["date"],
                "price": blended_price,
                "projected_swing_pct": swing_pct,
            }
        )
        previous_price = blended_price

    return blended_points


def predict_next_turning_point(
    close_series: pd.Series,
    latest_available_date: Any | None = None,
    latest_available_price: Any | None = None,
) -> dict[str, Any] | None:
    projected_turning_points = predict_next_turning_points(
        close_series,
        latest_available_date=latest_available_date,
        latest_available_price=latest_available_price,
        count=1,
    )
    if not projected_turning_points:
        return None

    return projected_turning_points[0]


def _transition_sequences(points: list[dict[str, Any]]) -> dict[tuple[str, str], list[tuple[float, int]]]:
    sequences: dict[tuple[str, str], list[tuple[float, int]]] = {}
    for first, second in zip(points, points[1:]):
        first_type = str(first.get("type", ""))
        second_type = str(second.get("type", ""))

        first_price = _get_float(first.get("price"))
        second_price = _get_float(second.get("price"))
        first_date = pd.to_datetime(first.get("date"), errors="coerce")
        second_date = pd.to_datetime(second.get("date"), errors="coerce")
        if (
            pd.isna(first_price)
            or pd.isna(second_price)
            or first_price == 0
            or pd.isna(first_date)
            or pd.isna(second_date)
        ):
            continue

        transition_key = (first_type, second_type)
        sequences.setdefault(transition_key, []).append(
            (
                abs((second_price - first_price) / first_price) * 100,
                _business_days_between(first_date, second_date),
            )
        )

    for transition_key, values in sequences.items():
        sequences[transition_key] = list(reversed(values))

    return sequences


def _sequence_stat(sequence: list[tuple[float, int]], occurrence_index: int) -> tuple[float, int] | None:
    if not sequence:
        return None

    if occurrence_index < len(sequence):
        swing_pct, days = sequence[occurrence_index]
        return swing_pct, max(int(days), 1)

    recent_window = sequence[: min(3, len(sequence))]
    avg_swing = sum(item[0] for item in recent_window) / len(recent_window)
    avg_days = max(
        int(round(sum(item[1] for item in recent_window) / len(recent_window))),
        1,
    )
    return avg_swing, avg_days


def _project_turning_points_from_sequences(
    *,
    base_sequences: dict[tuple[str, str], list[tuple[float, int]]],
    refinement_sequences: list[tuple[float, dict[tuple[str, str], list[tuple[float, int]]]]],
    fallback_swing_pct: float,
    fallback_days: int,
    last_type: str,
    last_date: pd.Timestamp,
    last_price: float,
    latest_known_date: Any | None,
    latest_known_price: Any | None,
    count: int,
    fallback_sequences: dict[tuple[str, str], list[tuple[float, int]]] | None = None,
) -> list[dict[str, Any]]:
    transition_usage: dict[tuple[str, str], int] = {}

    def _transition_stats(from_type: str, to_type: str) -> tuple[float, int]:
        transition_key = (from_type, to_type)
        occurrence_index = transition_usage.get(transition_key, 0)

        refined_stat = _sequence_stat(base_sequences.get(transition_key, []), occurrence_index)
        if refined_stat is None and fallback_sequences is not None:
            refined_stat = _sequence_stat(fallback_sequences.get(transition_key, []), occurrence_index)

        for blend_weight, sequences in refinement_sequences:
            window_stat = _sequence_stat(sequences.get(transition_key, []), occurrence_index)
            if window_stat is None:
                continue

            if refined_stat is None:
                refined_stat = window_stat
                continue

            refined_swing = (refined_stat[0] * (1 - blend_weight)) + (window_stat[0] * blend_weight)
            refined_days = max(
                int(round((refined_stat[1] * (1 - blend_weight)) + (window_stat[1] * blend_weight))),
                1,
            )
            refined_stat = (refined_swing, refined_days)

        transition_usage[transition_key] = occurrence_index + 1
        if refined_stat is not None:
            return refined_stat

        return fallback_swing_pct, fallback_days

    current_type = last_type
    current_date = last_date
    current_price = last_price
    projected_turning_points: list[dict[str, Any]] = []
    accepted_points = 0

    for _ in range(24):
        target_type = "Low" if current_type == "Peak" else "Peak"
        projected_swing_pct, projected_days = _transition_stats(current_type, target_type)

        if target_type == "Peak":
            projected_price = current_price * (1 + projected_swing_pct / 100)
        else:
            projected_price = current_price * (1 - projected_swing_pct / 100)

        projected_date = _add_business_days(current_date, projected_days)
        projected_turning_point = {
            "type": target_type,
            "date": _format_date(projected_date),
            "price": projected_price,
            "projected_swing_pct": projected_swing_pct,
        }

        price_target_already_reached = False
        if accepted_points == 0 and pd.notna(latest_known_price):
            if target_type == "Low" and latest_known_price <= projected_price:
                price_target_already_reached = True
            elif target_type == "Peak" and latest_known_price >= projected_price:
                price_target_already_reached = True

        future_enough = accepted_points > 0 or pd.isna(latest_known_date) or projected_date > latest_known_date
        if future_enough and not price_target_already_reached:
            projected_turning_points.append(projected_turning_point)
            accepted_points += 1
            if accepted_points >= max(count, 1):
                return projected_turning_points

        current_type = target_type
        current_date = projected_date
        current_price = projected_price

    return projected_turning_points
