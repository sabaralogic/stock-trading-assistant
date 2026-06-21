from __future__ import annotations

import argparse
import errno
import html
import json
import os
import sys
from pathlib import Path
from typing import Any
from wsgiref.simple_server import make_server

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
from flask import Flask, jsonify, request, render_template

try:
    from waitress import serve as _waitress_serve
except ImportError:
    _waitress_serve = None

from src.backtester import backtest_portfolio
from src.api_cache import (
    analyze_cache_key,
    bool_value,
    json_safe,
    read_cached_response,
    scan_cache_key,
    split_symbols,
    write_cached_response,
)
from src.data_fetcher import fetch_batch_stock_data, normalize_symbols
from src.evaluator import evaluate_predictions, load_previous_predictions, save_predictions
from src.stock_analysis import (
    analyze_stock,
    attach_analysis_metrics_to_evaluation,
    format_stock_analysis,
    save_stock_analysis_report,
)
from src.strategy import rank_stocks
from src.telegram_alert import send_telegram_message
from src.heuristic_history import load_stock_heuristic_history, save_heuristic_snapshots

NIFTY500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
TOP_STOCKS_PATH = ROOT_DIR / "data" / "top_stocks.json"

app = Flask(__name__)


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []

    serializable = frame.reset_index().copy()
    for column in serializable.columns:
        if pd.api.types.is_datetime64_any_dtype(serializable[column]):
            serializable[column] = serializable[column].dt.strftime("%Y-%m-%d")

    return json_safe(serializable.to_dict(orient="records"))


def _get_payload() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def _load_stocks_from_file(path: str | None) -> list[str]:
    if not path:
        return []

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Symbols file not found: {path}")

    return split_symbols(file_path.read_text(encoding="utf-8"))


def _get_default_symbols() -> list[str]:
    df = pd.read_csv(NIFTY500_URL)
    return [
        f"{symbol}.NS"
        for symbol in df["Symbol"].dropna()
        if not str(symbol).startswith("DUMMY")
    ]


def _read_symbols_from_payload(payload: dict[str, Any]) -> list[str]:
    symbols = split_symbols(payload.get("symbols"))
    symbols.extend(_load_stocks_from_file(payload.get("symbols_file")))

    if not symbols:
        symbols = _get_default_symbols()

    return normalize_symbols(symbols)


def _fetch_data(symbols: list[str], payload: dict[str, Any], *, max_workers: int | None = None) -> dict[str, pd.DataFrame]:
    workers = max_workers if max_workers is not None else int(payload.get("workers", 5))
    return fetch_batch_stock_data(
        symbols,
        max_workers=workers,
        period=payload.get("period", "1y"),
        interval=payload.get("interval", "1d"),
        start=payload.get("start"),
        end=payload.get("end"),
        auto_adjust=bool_value(payload, "auto_adjust", True),
    )


def _build_telegram_message(top_stocks: list[dict[str, Any]]) -> str:
    lines = [
        "🔥 <b>Top Opportunities</b>",
        "<b># | Stock | Signal | Return</b>",
    ]

    for index, stock in enumerate(top_stocks, start=1):
        symbol = str(stock["stock"]).upper()
        stock_link = f"https://stocks.sabaralogic.com/stock.html?symbol={symbol}"
        signal = html.escape(str(stock["signal"]))
        stock_label = html.escape(symbol)
        expected_annualized = stock.get("expected_xirr")
        expected_annualized_text = (
            f"{expected_annualized:.2f}%"
            if pd.notna(expected_annualized)
            else "N/A"
        )

        lines.append(
            f"{index} | <a href=\"{stock_link}\">{stock_label}</a> | "
            f"{signal} | {expected_annualized_text}"
        )

    return "\n".join(lines)


def _build_yesterday_performance(current_data: dict[str, pd.DataFrame]) -> dict[str, Any] | None:
    previous_predictions = load_previous_predictions()
    if previous_predictions.empty:
        return None

    evaluation_results, accuracy = evaluate_predictions(previous_predictions, current_data)
    if not evaluation_results:
        return None

    return {
        "results": json_safe(evaluation_results),
        "accuracy": accuracy,
    }


def _run_scan(payload: dict[str, Any]) -> dict[str, Any]:
    symbols = _read_symbols_from_payload(payload)
    if not symbols:
        raise ValueError("Please provide at least one ticker symbol.")

    result = _fetch_data(symbols, payload)
    evaluations: list[dict[str, Any]] = []
    analyses_by_symbol: dict[str, dict[str, Any]] = {}

    for symbol, data in sorted(result.items()):
        if data is None or data.empty:
            continue

        analysis = analyze_stock(
            data,
            symbol,
            turning_point_threshold_pct=float(payload.get("turning_point_threshold", 0.5)),
        )
        analyses_by_symbol[symbol] = analysis
        evaluations.append(
            attach_analysis_metrics_to_evaluation(
                analysis["evaluation"],
                analysis,
            )
        )

    yesterday_performance = _build_yesterday_performance(result)
    top_n = int(payload.get("top_n", 25))
    top_stocks = rank_stocks(evaluations, top_n=top_n)
    saved_predictions = save_predictions(evaluations)
    save_heuristic_snapshots(analyses_by_symbol)

    response = {
        "mode": "scan",
        "symbols": symbols,
        "fetched_symbol_count": len(result),
        "fetched_symbols": sorted(result.keys()),
        "evaluations": json_safe(evaluations),
        "top_stocks": json_safe(top_stocks),
        "saved_prediction_count": 0 if saved_predictions is None else len(saved_predictions),
        "yesterday_performance": yesterday_performance,
    }

    if top_stocks:
        response["telegram_message"] = _build_telegram_message(top_stocks)

        if bool_value(payload, "send_telegram", False):
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            if token and chat_id:
                send_telegram_message(token=token, chat_id=chat_id, message=response["telegram_message"])
                response["telegram_sent"] = True
            else:
                response["telegram_sent"] = False
                response["telegram_error"] = "Telegram credentials not found in environment variables."

    return response


def _get_or_create_scan_response(payload: dict[str, Any]) -> dict[str, Any]:
    symbols = _read_symbols_from_payload(payload)
    cache_key = scan_cache_key(payload, symbols)
    cached_response = read_cached_response("scan", cache_key)
    if cached_response is not None:
        if bool_value(payload, "send_telegram", False):
            cached_response["telegram_sent"] = False
            cached_response["telegram_notice"] = "Skipped Telegram send because a cached scan result was served."
        return cached_response

    response = _run_scan(payload)
    return write_cached_response("scan", cache_key, response)


def _run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    symbols = _read_symbols_from_payload(payload)
    if not symbols:
        raise ValueError("Please provide at least one ticker symbol.")

    historical_data = _fetch_data(symbols, payload)
    backtest_results, accuracy = backtest_portfolio(historical_data)
    graded_results = [result for result in backtest_results if result.get("correct") is not None]
    sortable_results = [result for result in graded_results if pd.notna(result.get("change_pct"))]
    valid_returns = [result["change_pct"] for result in sortable_results]

    if valid_returns:
        average_return = sum(valid_returns) / len(valid_returns)
        best_trade = max(valid_returns)
        worst_trade = min(valid_returns)
    else:
        average_return = None
        best_trade = None
        worst_trade = None

    sorted_trades = sorted(sortable_results, key=lambda result: result["change_pct"], reverse=True)

    return {
        "mode": "backtest",
        "symbols": symbols,
        "fetched_symbol_count": len(historical_data),
        "summary": json_safe(
            {
                "total_trades": len(graded_results),
                "accuracy": accuracy,
                "average_return": average_return,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
            }
        ),
        "best_trades": json_safe(sorted_trades[:25]),
        "worst_trades": json_safe(list(reversed(sorted_trades[-5:]))),
        "results": json_safe(backtest_results),
    }


def _run_analysis(symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
    analysis_symbols = normalize_symbols([symbol])
    if not analysis_symbols:
        raise ValueError("Please provide a valid stock symbol for analysis.")

    normalized_symbol = analysis_symbols[0]
    result = fetch_batch_stock_data(
        [normalized_symbol],
        max_workers=1,
        period=payload.get("period", "1y"),
        interval=payload.get("interval", "1d"),
        start=payload.get("start"),
        end=payload.get("end"),
        auto_adjust=bool_value(payload, "auto_adjust", True),
    )

    data = result.get(normalized_symbol)
    if data is None or data.empty:
        raise ValueError(f"No data available for {normalized_symbol}.")

    analysis = analyze_stock(
        data,
        normalized_symbol,
        turning_point_threshold_pct=float(payload.get("turning_point_threshold", 0.5)),
    )

    response = {
        "mode": "analyze",
        "stock": normalized_symbol,
        "summary": json_safe(analysis["summary"]),
        "insights": json_safe(analysis["insights"]),
        "evaluation": json_safe(analysis["evaluation"]),
        "turning_points": json_safe(analysis["turning_points"]),
        "all_turning_points": json_safe(analysis["all_turning_points"]),
        "chart_turning_points": json_safe(analysis.get("chart_turning_points", analysis["all_turning_points"])),
        "predicted_turning_point": json_safe(analysis["predicted_turning_point"]),
        "predicted_turning_points": json_safe(analysis.get("predicted_turning_points", [])),
        "heuristic_history": json_safe(load_stock_heuristic_history(normalized_symbol)),
        "recent_data": _frame_to_records(analysis["recent_data"]),
        "formatted_text": format_stock_analysis(analysis),
    }

    if bool_value(payload, "save_report", True):
        response["report_path"] = str(save_stock_analysis_report(analysis))

    return response


def _get_or_create_analysis_response(symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
    cache_key = analyze_cache_key(symbol, payload)
    cached_response = read_cached_response("analyze", cache_key)
    if cached_response is not None:
        return cached_response

    response = _run_analysis(symbol, payload)
    return write_cached_response("analyze", cache_key, response)


def _error_response(message: str, *, status_code: int = 400):
    return jsonify({"status": "error", "message": message}), status_code


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/top-stocks")
def top_stocks():
    if not TOP_STOCKS_PATH.exists():
        return _error_response(f"File not found: {TOP_STOCKS_PATH}", status_code=404)

    with TOP_STOCKS_PATH.open(encoding="utf-8") as file:
        return jsonify(json.load(file))


@app.route("/api/analyze", methods=["POST"])
def analyze():
    payload = _get_payload()
    symbol = payload.get("symbol")
    if not symbol:
        return _error_response("Please provide 'symbol' in the request body.")

    try:
        return jsonify(_get_or_create_analysis_response(str(symbol), payload))
    except Exception as exc:
        return _error_response(str(exc))


@app.route("/api/analyze/<symbol>", methods=["GET"])
def analyze_symbol(symbol: str):
    payload = dict(request.args)

    try:
        return jsonify(_get_or_create_analysis_response(symbol, payload))
    except Exception as exc:
        return _error_response(str(exc))


@app.route("/api/scan", methods=["POST"])
def scan():
    payload = _get_payload()

    try:
        return jsonify(_get_or_create_scan_response(payload))
    except Exception as exc:
        return _error_response(str(exc))


@app.route("/api/backtest", methods=["POST"])
def backtest():
    payload = _get_payload()

    try:
        return jsonify(_run_backtest(payload))
    except Exception as exc:
        return _error_response(str(exc))

@app.route("/stock/<symbol>")
def stock(symbol):
    return render_template(
        "stock.html",
        symbol=symbol
    )

@app.route("/")
def home():
    return render_template("index.html")


def _parse_cli_args() -> tuple[str, int, bool]:
    parser = argparse.ArgumentParser(description="Start the webapp server.")
    parser.add_argument("--host", default=os.environ.get("WEBAPP_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("WEBAPP_PORT", 5000)),
    )
    parser.add_argument(
        "--no-port-fallback",
        action="store_true",
        help="Do not try alternate ports if the requested port is already in use.",
    )
    args = parser.parse_args()
    return args.host, args.port, args.no_port_fallback


def _bind_server(host: str, port: int) -> None:
    if _waitress_serve is not None:
        print(f"Serving on http://{host}:{port} using waitress")
        _waitress_serve(app, host=host, port=port)
        return

    print(
        f"Serving on http://{host}:{port} using Python's built-in wsgiref server."
        " This is fine for local use, but for production install waitress or gunicorn."
    )
    with make_server(host, port, app) as server:
        server.serve_forever()


def _start_server(host: str = "0.0.0.0", port: int = 5000, no_port_fallback: bool = False) -> None:
    current_port = port
    while True:
        try:
            _bind_server(host, current_port)
            return
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise

            if no_port_fallback:
                raise RuntimeError(
                    f"Port {current_port} is already in use. "
                    "Please stop the other process or specify a different port with --port."
                ) from error

            next_port = current_port + 1
            print(
                f"Port {current_port} is already in use. Trying port {next_port} instead..."
            )
            current_port = next_port


if __name__ == "__main__":
    host, port, no_port_fallback = _parse_cli_args()
    _start_server(host=host, port=port, no_port_fallback=no_port_fallback)
