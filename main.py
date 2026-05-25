from __future__ import annotations

import os
import argparse
from pathlib import Path

import pandas as pd
import textwrap

from config import DEBUG_DATA_MODE, DEBUG_ENABLED, DEBUG_PREVIEW_ROWS
from src.backtester import backtest_portfolio
from src.data_fetcher import fetch_batch_stock_data, normalize_symbols
from src.evaluator import evaluate_predictions, load_previous_predictions, save_predictions
from src.indicators import add_rsi, add_moving_averages
from src.strategy import evaluate_stock, rank_stocks

from src.telegram_alert import send_telegram_message

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
        "--no-auto-adjust",
        action="store_true",
        help="Keep raw OHLC prices instead of yfinance auto-adjusted prices.",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run portfolio backtesting instead of normal daily evaluation.",
    )
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
    for evaluation in evaluation_results:
        if evaluation["status"] == "missing_current_data":
            print(f"{evaluation['stock']} → {evaluation['signal']} → MISSING DATA")
            print(f"   {evaluation['old_price']:g} → N/A\n")
            continue

        outcome = "CORRECT" if evaluation["correct"] else "WRONG"
        print(f"{evaluation['stock']} → {evaluation['signal']} → {outcome}")
        print(f"   {evaluation['old_price']:g} → {evaluation['new_price']:g}\n")

    print(f"Accuracy: {accuracy:.0f}%")


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

    lines = []

    lines.append("🔥 <b>Top Opportunities</b>\n")

    for i, r in enumerate(top_stocks, start=1):
        rsi = round(r["rsi"], 2) if pd.notna(r["rsi"]) else "N/A"

        lines.append(f"<b>{i}. {r['stock']}</b>")
        lines.append(f"Signal : {r['signal']}")
        lines.append(f"Score  : {r['score']}")
        lines.append(f"RSI    : {rsi}\n")

        lines.append("<b>Reasons</b>")

        for reason in r["reasons"]:
            lines.append(f"• {reason}")

        lines.append("\n━━━━━━━━━━━━━━\n")

    return "\n".join(lines)

def main() -> None:
    args = parse_args()
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
        auto_adjust=not args.no_auto_adjust,
    )

    print(f"Fetched data for {len(result)} symbols.")

    results = []

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

        # Evaluate stock
        evaluation = evaluate_stock(df, symbol)
        results.append(evaluation)

        if DEBUG_ENABLED:
            print_debug_data(df)

    previous_predictions = load_previous_predictions()
    print_yesterday_performance(previous_predictions, result)

    # Rank top stocks
    top_stocks = rank_stocks(results, top_n=25)

    if not top_stocks:
        print("\nNo stock opportunities to rank.")
        print("Check your fetch results, date range, or indicator inputs.")
        print("Possible reasons: market data unavailable, insufficient history, or no strong signals today.")
        save_predictions(results)
        return

    # print("\n🔥 Top Opportunities:\n")
    # for r in top_stocks:
    #     print(f"{r['stock']} → {r['signal']} (Score: {r['score']}, RSI: {round(r['rsi'], 2)})")
    #     print(f"   Reasons: {', '.join(r['reasons']) if r['reasons'] else 'None'}")

    table = build_opportunities_table(top_stocks)
    print(table)

    # telegram_message = f"<pre>{table}</pre>"
    message = build_telegram_message(top_stocks)
    save_predictions(results)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        send_telegram_message(
            token,
            chat_id,
            message
        )

if __name__ == "__main__":
    main()
