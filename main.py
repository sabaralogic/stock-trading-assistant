from __future__ import annotations

import os
import argparse
import html
from pathlib import Path

import pandas as pd
import textwrap

from config import DEBUG_DATA_MODE, DEBUG_ENABLED, DEBUG_PREVIEW_ROWS
from src.api_cache import analyze_cache_key, json_safe, scan_cache_key, write_cached_response
from src.backtester import backtest_portfolio
from src.data_fetcher import fetch_batch_stock_data, normalize_symbols
from src.evaluator import evaluate_predictions, load_previous_predictions, save_predictions
from src.indicators import add_rsi, add_moving_averages
from src.stock_analysis import (
    analyze_stock,
    attach_analysis_metrics_to_evaluation,
    format_stock_analysis,
    save_stock_analysis_report,
)
from src.strategy import rank_stocks
from src.site_export import export_analyze_response, export_meta, export_scan_response
from src.heuristic_history import load_stock_heuristic_history, save_heuristic_snapshots

from src.telegram_alert import send_telegram_message
from src.telegram_alert import send_telegram_photo
from src.report_image import save_html_report

from src.html_to_image import html_to_png

NIFTY500_URL = (
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
)

def build_opportunities_table(top_stocks: list[dict]) -> str:

    separator = (
        "+------+---------------+--------+-------+--------+----------------------------------+"
    )

    lines = []

    lines.append("🔥 Top Opportunities\n")

    lines.append(separator)
    lines.append(
        "| Rank | Stock         | Signal | Score | RSI    | Comments                         |"
    )
    lines.append(separator)

    for i, r in enumerate(top_stocks, start=1):

        rsi = round(r["rsi"], 2) if pd.notna(r["rsi"]) else "N/A"

        comments = ", ".join(r["reasons"])

        wrapped_comments = textwrap.wrap(comments, width=32)

        first_line = True

        for line in wrapped_comments:

            if first_line:
                lines.append(
                    f"| {i:<4} "
                    f"| {r['stock']:<13} "
                    f"| {r['signal']:<6} "
                    f"| {r['score']:<5} "
                    f"| {str(rsi):<6} "
                    f"| {line:<32} |"
                )

                first_line = False

            else:
                lines.append(
                    f"| {'':<4} "
                    f"| {'':<13} "
                    f"| {'':<6} "
                    f"| {'':<5} "
                    f"| {'':<6} "
                    f"| {line:<32} |"
                )

        lines.append(separator)

    return "\n".join(lines)

def get_default_symbols() -> list[str]:

    df = pd.read_csv(NIFTY500_URL)

    return [
        f"{symbol}.NS"
        for symbol in df["Symbol"].dropna()
        if not symbol.startswith("DUMMY")
    ]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch historical stock data in batches.")
    parser.add_argument(
        "symbols",
        nargs="*",
        help="Ticker symbols separated by spaces or commas, for example: AAPL MSFT,NVDA",
    )
    parser.add_argument(
        "--symbols-file",
        type=Path,
        help="Optional text file containing ticker symbols separated by commas, spaces, or new lines.",
    )
    parser.add_argument("--period", default="1y", help="yfinance period, for example 1mo, 6mo, 1y, 5y.")
    parser.add_argument("--interval", default="1d", help="yfinance interval, for example 1d, 1h, 5m.")
    parser.add_argument("--start", help="Start date in YYYY-MM-DD format. Overrides --period when provided.")
    parser.add_argument("--end", help="End date in YYYY-MM-DD format.")
    parser.add_argument("--workers", type=int, default=5, help="Maximum concurrent fetches.")
    parser.add_argument(
        "--auto-adjust",
        dest="auto_adjust",
        action="store_true",
        help="Use yfinance auto-adjusted prices instead of raw OHLC prices. Default: raw prices.",
    )
    parser.add_argument(
        "--no-auto-adjust",
        dest="auto_adjust",
        action="store_false",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run portfolio backtesting instead of normal daily evaluation.",
    )
    parser.add_argument(
        "--analyze",
        help="Analyze one particular stock in detail, for example: --analyze AAPL or --analyze RELIANCE.NS",
    )
    parser.add_argument(
        "--turning-point-threshold",
        type=float,
        default=0.5,
        help="Minimum swing percentage required to show peaks and lows in analyze mode. Default: 0.5",
    )
    parser.set_defaults(auto_adjust=False)
    return parser.parse_args()

def load_stocks_from_file(path: str) -> list[str]:
    with open(path, "r") as file:
        return [
            line.strip()
            for line in file
            if line.strip()
        ]

def read_symbols(args: argparse.Namespace) -> list[str]:
    symbols = list(args.symbols)

    if symbols:
        print(f"Loaded {len(symbols)} symbols from command line arguments.")
    
    if args.symbols_file:
        file_symbols = load_stocks_from_file(args.symbols_file)
        symbols.extend(file_symbols)
        if file_symbols:
            print(f"Loaded {len(file_symbols)} symbols from file: {args.symbols_file}")

    if not symbols:
        try:
            print("Loading default NIFTY500 symbols...")
            symbols.extend(get_default_symbols())
        except Exception as e:
            print(f"Failed to load default symbols: {e}")
            return []

    print(f"Loaded {len(symbols)} normalized symbols.")

    return normalize_symbols(symbols)

def print_debug_data(data) -> None:
    row_count, column_count = data.shape

    if DEBUG_DATA_MODE == "full":
        print(f"    showing all {row_count} rows x {column_count} columns")
        print(data.to_string())
        print()
        return

    preview_rows = min(DEBUG_PREVIEW_ROWS, row_count)
    print(f"    showing last {preview_rows} of {row_count} rows x {column_count} columns")
    print(data.tail(preview_rows).to_string())
    print()


def print_yesterday_performance(previous_predictions, current_data) -> None:
    if previous_predictions.empty:
        return

    evaluation_results, accuracy = evaluate_predictions(previous_predictions, current_data)
    if not evaluation_results:
        return

    print("\n📊 Yesterday Performance:\n")
    missing_count = sum(
        1 for evaluation in evaluation_results if evaluation["status"] == "missing_current_data"
    )
    graded_results = [
        evaluation
        for evaluation in evaluation_results
        if evaluation["status"] != "missing_current_data"
    ]
    correct_count = sum(1 for evaluation in graded_results if evaluation["correct"])
    wrong_count = sum(1 for evaluation in graded_results if evaluation["correct"] is False)

    print(f"Evaluated: {len(graded_results)}")
    print(f"Correct: {correct_count}")
    print(f"Wrong: {wrong_count}")
    if missing_count:
        print(f"Missing current data: {missing_count}")
    print(f"Accuracy: {accuracy:.0f}%")

    for evaluation in evaluation_results:
        if evaluation["status"] == "missing_current_data":
            print(f"{evaluation['stock']} → {evaluation['signal']} → MISSING DATA")
            print(f"   {evaluation['old_price']:g} → N/A\n")
            continue

        outcome = "CORRECT" if evaluation["correct"] else "WRONG"
        print(f"{evaluation['stock']} → {evaluation['signal']} → {outcome}")
        print(f"   {evaluation['old_price']:g} → {evaluation['new_price']:g}\n")


def print_backtest_summary(historical_data) -> None:
    backtest_results, accuracy = backtest_portfolio(historical_data)
    graded_results = [result for result in backtest_results if result["correct"] is not None]
    sortable_results = [
        result for result in graded_results if pd.notna(result.get("change_pct"))
    ]
    valid_returns = [result["change_pct"] for result in sortable_results]

    print("\nBacktest Summary:\n")
    print(f"Total Trades: {len(graded_results)}")
    print(f"Accuracy: {accuracy:.0f}%")

    if valid_returns:
        average_return = sum(valid_returns) / len(valid_returns)
        best_trade = max(valid_returns)
        worst_trade = min(valid_returns)
    else:
        average_return = float("nan")
        best_trade = float("nan")
        worst_trade = float("nan")

    print(f"Average Return: {_format_pct(average_return)}")
    print(f"Best Trade: {_format_pct(best_trade)}")
    print(f"Worst Trade: {_format_pct(worst_trade)}")

    sorted_trades = sorted(
        sortable_results,
        key=lambda result: result["change_pct"],
        reverse=True,
    )
    best_trades = sorted_trades[:25]
    worst_trades = list(reversed(sorted_trades[-5:]))

    if not best_trades:
        return

    print(f"\nTop {len(best_trades)} Best Trades:\n")
    for trade in best_trades:
        print(
            f"{trade['stock']} → {trade['signal']} → {trade['status']} "
            f"({trade['change_pct']:.2f}%)"
        )
        print(f"   {trade['date']} → {trade['exit_date']}")

    print(f"\nTop {len(worst_trades)} Worst Trades:\n")
    for trade in worst_trades:
        print(
            f"{trade['stock']} → {trade['signal']} → {trade['status']} "
            f"({trade['change_pct']:.2f}%)"
        )
        print(f"   {trade['date']} → {trade['exit_date']}")


def _format_pct(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{value:+.1f}%"

def build_telegram_message(top_stocks: list[dict]) -> str:
    lines = [
        "🔥 <b>Top Opportunities</b>",
        "<b># | Stock | Signal | Return</b>",
    ]

    for i, r in enumerate(top_stocks, start=1):
        stock = str(r["stock"]).upper()
        stock_link = f"https://stocks.sabaralogic.com/stock.html?symbol={stock}"
        signal = html.escape(str(r["signal"]))
        stock_label = html.escape(stock)
        expected_annualized = r.get("expected_xirr")
        expected_annualized_text = (
            f"{expected_annualized:.2f}%"
            if pd.notna(expected_annualized)
            else "N/A"
        )

        lines.append(
            f"{i} | <a href=\"{stock_link}\">{stock_label}</a> | "
            f"{signal} | {expected_annualized_text}"
        )

    return "\n".join(lines)


def build_scan_api_response(
    symbols: list[str],
    fetched_data: dict[str, pd.DataFrame],
    evaluations: list[dict],
    top_stocks: list[dict],
    previous_predictions: pd.DataFrame,
    saved_predictions: pd.DataFrame | None,
) -> dict:
    yesterday_performance = None
    if previous_predictions is not None and not previous_predictions.empty:
        evaluation_results, accuracy = evaluate_predictions(previous_predictions, fetched_data)
        if evaluation_results:
            yesterday_performance = {
                "results": json_safe(evaluation_results),
                "accuracy": accuracy,
            }

    response = {
        "mode": "scan",
        "symbols": symbols,
        "fetched_symbol_count": len(fetched_data),
        "fetched_symbols": sorted(fetched_data.keys()),
        "evaluations": json_safe(evaluations),
        "top_stocks": json_safe(top_stocks),
        "saved_prediction_count": 0 if saved_predictions is None else len(saved_predictions),
        "yesterday_performance": yesterday_performance,
    }

    if top_stocks:
        response["telegram_message"] = build_telegram_message(top_stocks)

    return response


def build_analyze_api_response(
    analysis: dict,
    symbol: str,
    *,
    save_report: bool,
) -> dict:
    response = {
        "mode": "analyze",
        "stock": symbol,
        "summary": json_safe(analysis["summary"]),
        "insights": json_safe(analysis["insights"]),
        "evaluation": json_safe(analysis["evaluation"]),
        "turning_points": json_safe(analysis["turning_points"]),
        "all_turning_points": json_safe(analysis["all_turning_points"]),
        "chart_turning_points": json_safe(analysis.get("chart_turning_points", analysis["all_turning_points"])),
        "predicted_turning_point": json_safe(analysis["predicted_turning_point"]),
        "predicted_turning_points": json_safe(analysis.get("predicted_turning_points", [])),
        "heuristic_history": json_safe(load_stock_heuristic_history(symbol)),
        "recent_data": json_safe(analysis["recent_data"].reset_index().to_dict(orient="records")),
        "formatted_text": format_stock_analysis(analysis),
    }

    if save_report:
        response["report_path"] = str(save_stock_analysis_report(analysis))

    return response


def precompute_api_caches(
    args: argparse.Namespace,
    symbols: list[str],
    fetched_data: dict[str, pd.DataFrame],
    evaluations: list[dict],
    top_stocks: list[dict],
    previous_predictions: pd.DataFrame,
    saved_predictions: pd.DataFrame | None,
    analyses_by_symbol: dict[str, dict],
) -> None:
    scan_payload = {
        "symbols": symbols,
        "period": args.period,
        "interval": args.interval,
        "start": args.start,
        "end": args.end,
        "auto_adjust": args.auto_adjust,
        "top_n": 25,
    }
    scan_response = build_scan_api_response(
        symbols,
        fetched_data,
        evaluations,
        top_stocks,
        previous_predictions,
        saved_predictions,
    )
    write_cached_response("scan", scan_cache_key(scan_payload, symbols), scan_response)
    export_scan_response(scan_response)

    analyze_payload = {
        "period": args.period,
        "interval": args.interval,
        "start": args.start,
        "end": args.end,
        "auto_adjust": args.auto_adjust,
        "turning_point_threshold": args.turning_point_threshold,
        "save_report": False,
    }

    cached_analyze_count = 0
    for symbol, analysis in sorted(analyses_by_symbol.items()):
        if not analysis:
            continue
        analyze_response = build_analyze_api_response(analysis, symbol, save_report=False)
        write_cached_response("analyze", analyze_cache_key(symbol, analyze_payload), analyze_response)
        export_analyze_response(symbol, analyze_response)
        cached_analyze_count += 1

    export_meta(
        symbol_count=len(symbols),
        scan_path="/static/data/scan/default.json",
        analyze_count=cached_analyze_count,
    )
    print(f"Precomputed API cache for 1 scan response and {cached_analyze_count} analyze responses.")

def main() -> None:
    args = parse_args()

    if args.analyze:
        analysis_symbols = normalize_symbols([args.analyze])
        if not analysis_symbols:
            raise SystemExit("Please provide a valid stock symbol for analysis.")

        symbol = analysis_symbols[0]
        result = fetch_batch_stock_data(
            [symbol],
            max_workers=1,
            period=args.period,
            interval=args.interval,
            start=args.start,
            end=args.end,
            auto_adjust=args.auto_adjust,
        )

        data = result.get(symbol)
        if data is None or data.empty:
            raise SystemExit(f"No data available for {symbol}.")

        analysis = analyze_stock(
            data,
            symbol,
            turning_point_threshold_pct=args.turning_point_threshold,
        )
        print(format_stock_analysis(analysis))
        report_path = save_stock_analysis_report(analysis)
        print(f"\nAnalysis chart saved to: {report_path}")
        return

    symbols = read_symbols(args)

    if not symbols:
        raise SystemExit("Please provide at least one ticker symbol.")

    result = fetch_batch_stock_data(
        symbols,
        max_workers=args.workers,
        period=args.period,
        interval=args.interval,
        start=args.start,
        end=args.end,
        auto_adjust=args.auto_adjust,
    )

    print(f"Fetched data for {len(result)} symbols.")

    results = []
    analyses_by_symbol: dict[str, dict] = {}

    # for symbol, data in sorted(result.items()):
    #     print(f"  {symbol}: {len(data)} rows")
    
    if args.backtest:
        print_backtest_summary(result)
        return

    for symbol, data in sorted(result.items()):

        if data is None or data.empty:
            continue

        # Add indicators
        df = add_rsi(data)
        df = add_moving_averages(df)

        analysis = analyze_stock(
            data,
            symbol,
            turning_point_threshold_pct=args.turning_point_threshold,
        )
        analyses_by_symbol[symbol] = analysis
        evaluation = attach_analysis_metrics_to_evaluation(
            analysis["evaluation"],
            analysis,
        )
        results.append(evaluation)

        if DEBUG_ENABLED:
            print_debug_data(df)

    previous_predictions = load_previous_predictions()
    print_yesterday_performance(previous_predictions, result)

    # Rank top stocks
    top_stocks = rank_stocks(results, top_n=25)
    saved_predictions = save_predictions(results)
    save_heuristic_snapshots(analyses_by_symbol)
    precompute_api_caches(
        args,
        symbols,
        result,
        results,
        top_stocks,
        previous_predictions,
        saved_predictions,
        analyses_by_symbol,
    )

    if not top_stocks:
        print("\nNo stock opportunities to rank.")
        print("Check your fetch results, date range, or indicator inputs.")
        print("Possible reasons: market data unavailable, insufficient history, or no strong signals today.")
        return

    print("\n🔥 Top Opportunities:\n")
    for r in top_stocks:
        print(f"{r['stock']} → {r['signal']} (Score: {r['score']}, RSI: {round(r['rsi'], 2)})")
        print(f"   Reasons: {', '.join(r['reasons']) if r['reasons'] else 'None'}")

    # table = build_opportunities_table(top_stocks)
    # print(table)

    # html_report = save_html_report(top_stocks)
    # print(f"HTML report generated: {html_report}")

    # html_report = save_html_report(top_stocks)
    # image_path = html_to_png(str(html_report))
    # print(f"Generated image: {image_path}")

    # telegram_message = f"<pre>{table}</pre>"
    message = build_telegram_message(top_stocks)
    print("\nTelegram Message:\n")
    print(message)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        send_telegram_message(
            token=token,
            chat_id=chat_id,
            message=message
        )
    else:
        print("\nTelegram credentials not found in environment variables.")
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable Telegram alerts.")


if __name__ == "__main__":
    main()
