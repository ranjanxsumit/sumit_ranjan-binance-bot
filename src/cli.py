"""Command line interface for the Binance Futures order bot."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

from binance.enums import ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET

from .advanced.twap import TWAPExecutor, TWAPRequest
from .core.bot import BasicBot
from .core.config import BinanceConfig
from .core.logger import setup_logging
from .core.validators import (
    normalize_symbol,
    validate_price,
    validate_quantity,
    validate_side,
    validate_time_in_force,
)
from .data.feeds import (
    FearGreedSnapshot,
    HistoricalSummary,
    get_latest_fear_greed,
    summarize_historical_trades,
)
from .signals.advisors import SentimentAdvisor, SentimentSignal

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="binance-bot",
        description="CLI wrapper for Binance Futures order placement on the testnet.",
    )
    parser.add_argument(
        "--log-file",
        default="bot.log",
        help="Path to write log output (default: bot.log)",
    )
    parser.add_argument(
        "--raw-json",
        action="store_true",
        help="Print raw JSON responses instead of the human-friendly summary.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    market_parser = subparsers.add_parser("market", help="Place a market order")
    _add_common_order_arguments(market_parser)

    limit_parser = subparsers.add_parser("limit", help="Place a limit order")
    _add_common_order_arguments(limit_parser)
    limit_parser.add_argument("price", type=float, help="Limit price")
    limit_parser.add_argument(
        "--time-in-force",
        default="GTC",
        help="Time in force (GTC, IOC, FOK). Default: GTC",
    )

    twap_parser = subparsers.add_parser("twap", help="Execute a TWAP strategy")
    twap_parser.add_argument("symbol", help="Trading symbol, e.g. BTCUSDT")
    twap_parser.add_argument("side", help="Order side BUY or SELL")
    twap_parser.add_argument("total_quantity", type=float, help="Total quantity to trade across slices")
    twap_parser.add_argument("slices", type=int, help="Number of slices to break the order into")
    twap_parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Seconds to wait between slices (default: 10)",
    )
    twap_parser.add_argument(
        "--order-type",
        choices=[ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT],
        default=ORDER_TYPE_MARKET,
        help="Use market or limit orders for each slice (default: MARKET)",
    )
    twap_parser.add_argument(
        "--price",
        type=float,
        help="Limit price when --order-type is LIMIT",
    )
    twap_parser.add_argument(
        "--time-in-force",
        default="GTC",
        help="Time in force for limit slices (default: GTC)",
    )

    interactive_parser = subparsers.add_parser(
        "interactive",
        help="Launch an interactive guided CLI with data insights",
    )
    interactive_parser.add_argument(
        "--fear-greed-csv",
        default=None,
        help="Path to fear_greed_index.csv (defaults to project root file)",
    )
    interactive_parser.add_argument(
        "--historical-csv",
        default=None,
        help="Path to historical_data.csv (defaults to project root file)",
    )

    return parser


def _add_common_order_arguments(sub_parser: argparse.ArgumentParser) -> None:
    sub_parser.add_argument("symbol", help="Trading symbol, e.g. BTCUSDT")
    sub_parser.add_argument("side", help="Order side BUY or SELL")
    sub_parser.add_argument("quantity", type=float, help="Order quantity (base asset amount)")


def _result_as_summary(payload: Dict[str, Any], raw_json: bool) -> str:
    if raw_json:
        return json.dumps(payload, indent=2, default=str)
    lines = ["Order Summary:"]
    for key, value in payload.items():
        lines.append(f"  - {key}: {value}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(args.log_file)
    LOGGER.info("Starting CLI with args: %s", args)

    try:
        config = BinanceConfig.from_env()
    except EnvironmentError as exc:
        LOGGER.error("Configuration error: %s", exc)
        parser.error(str(exc))
        return 1

    bot = BasicBot.from_config(config)

    try:
        if args.command == "market":
            return _handle_market(args, bot)
        if args.command == "limit":
            return _handle_limit(args, bot)
        if args.command == "twap":
            return _handle_twap(args, bot)
        if args.command == "interactive":
            return _handle_interactive(args, bot)
    except ValueError as exc:
        LOGGER.error("Validation error: %s", exc)
        parser.error(str(exc))
    except Exception as exc:  # pragma: no cover - catch-all for CLI robustness
        LOGGER.exception("Unexpected error: %s", exc)
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    parser.error("No command provided")
    return 1


def _handle_market(args: argparse.Namespace, bot: BasicBot) -> int:
    symbol = normalize_symbol(args.symbol)
    side = validate_side(args.side)
    quantity = validate_quantity(args.quantity)

    result = bot.place_market_order(symbol, side, quantity)
    payload = _build_order_payload(result)
    print(_result_as_summary(payload, args.raw_json))
    return 0 if result.is_success else 1


def _handle_limit(args: argparse.Namespace, bot: BasicBot) -> int:
    symbol = normalize_symbol(args.symbol)
    side = validate_side(args.side)
    quantity = validate_quantity(args.quantity)
    price = validate_price(args.price)
    tif = validate_time_in_force(args.time_in_force)

    result = bot.place_limit_order(symbol, side, quantity, price, time_in_force=tif)
    payload = _build_order_payload(result)
    print(_result_as_summary(payload, args.raw_json))
    return 0 if result.is_success else 1


def _handle_twap(args: argparse.Namespace, bot: BasicBot) -> int:
    symbol = normalize_symbol(args.symbol)
    side = validate_side(args.side)
    total_quantity = validate_quantity(args.total_quantity)
    slices = int(args.slices)
    interval = float(args.interval)
    order_type = args.order_type
    price = validate_price(args.price) if order_type == ORDER_TYPE_LIMIT else None
    tif = validate_time_in_force(args.time_in_force)

    executor = TWAPExecutor(
        place_market_order=bot.place_market_order,
        place_limit_order=bot.place_limit_order,
    )
    request = TWAPRequest(
        symbol=symbol,
        side=side,
        total_quantity=total_quantity,
        slices=slices,
        interval_seconds=interval,
        order_type=order_type,
        limit_price=price,
        time_in_force=tif,
    )
    result = executor.execute(request)

    payload = {
        "symbol": symbol,
        "side": side,
        "slices": slices,
        "interval_seconds": interval,
        "order_type": order_type,
        "executed_quantity": result.executed_quantity,
        "success": result.is_success,
        "slice_details": [
            {
                "quantity": slice_result.request.quantity,
                "is_success": slice_result.is_success,
                "error_message": slice_result.error_message,
                "response": slice_result.raw_response,
            }
            for slice_result in result.slice_results
        ],
    }
    print(_result_as_summary(payload, args.raw_json))
    return 0 if result.is_success else 1


def _build_order_payload(result) -> Dict[str, Any]:
    return {
        "symbol": result.request.symbol,
        "side": result.request.side,
        "quantity": result.request.quantity,
        "price": result.request.price,
        "time_in_force": result.request.time_in_force,
        "success": result.is_success,
        "error_message": result.error_message,
        "response": result.raw_response,
    }


def _handle_interactive(args: argparse.Namespace, bot: BasicBot) -> int:
    LOGGER.info("Launching interactive mode")
    fear = None
    history = None
    sentiment: SentimentSignal | None = None
    try:
        fear = get_latest_fear_greed(Path(args.fear_greed_csv) if args.fear_greed_csv else None)
    except Exception as exc:
        LOGGER.warning("Failed to load fear & greed index: %s", exc)
    try:
        history = summarize_historical_trades(Path(args.historical_csv) if args.historical_csv else None)
    except Exception as exc:
        LOGGER.warning("Failed to load historical data: %s", exc)

    if fear or history:
        sentiment = SentimentAdvisor(
            symbol="BTCUSDT",
            fear=fear,
            history=history,
        ).build_signal()

    _print_data_banner(fear, history, sentiment)

    while True:
        choice = input(
            "\nChoose an action [market/limit/twap/help/quit]: "
        ).strip().lower()
        if choice in {"quit", "exit", "q"}:
            print("Exiting interactive mode.")
            return 0
        if choice == "help":
            _print_help()
            continue
        try:
            if choice == "market":
                _interactive_market(bot, sentiment)
            elif choice == "limit":
                _interactive_limit(bot, sentiment)
            elif choice == "twap":
                _interactive_twap(bot, sentiment)
            else:
                print("Unknown choice. Type 'help' to list options.")
        except ValueError as exc:
            LOGGER.error("Validation error: %s", exc)
            print(f"Validation error: {exc}")
        except Exception as exc:  # pragma: no cover - keep CLI responsive
            LOGGER.exception("Interactive command failed: %s", exc)
            print(f"Unexpected error: {exc}")


def _print_data_banner(
    fear: FearGreedSnapshot | None,
    history: HistoricalSummary | None,
    sentiment: SentimentSignal | None,
) -> None:
    print("=" * 60)
    print(" Binance Futures Bot - Interactive Console ")
    print("=" * 60)
    if fear:
        print(f" Latest Fear & Greed Index: {fear.label}")
    else:
        print(" Fear & Greed data unavailable.\n")
    if history:
        print(
            f" Historical trades: {history.total_trades} events | "
            f"Gross volume: ${history.gross_volume_usd:,.2f} | "
            f"Net closed PnL: ${history.net_closed_pnl:,.2f}"
        )
        if history.latest_trades:
            print(" Recent activity:")
            for trade in history.latest_trades:
                print(
                    "  - "
                    f"{trade.timestamp} | {trade.symbol} | {trade.side} | "
                    f"${trade.execution_price:.4f} | ${trade.size_usd:,.2f}"
                    f" | PnL ${trade.closed_pnl:,.2f}"
                )
    else:
        print(" Historical trade data unavailable.")
    if sentiment:
        print("-" * 60)
        print(
            f" Sentiment signal: {sentiment.bias} (confidence {int(sentiment.confidence * 100)}%)"
        )
        print(f" Rationale: {sentiment.rationale}")
        if sentiment.reference_price:
            print(f" Reference price: ${sentiment.reference_price:.2f}")
        if sentiment.suggested_quantity:
            print(f" Suggested qty: {sentiment.suggested_quantity}")
    print("=" * 60)
    print("Type 'help' to list available actions.")


def _print_help() -> None:
    print(
        "Available actions:\n"
        "  market - Place a market order\n"
        "  limit  - Place a limit order\n"
        "  twap   - Execute a TWAP strategy\n"
        "  help   - Show this help menu\n"
        "  quit   - Exit interactive mode"
    )


def _interactive_market(bot: BasicBot, sentiment: SentimentSignal | None) -> None:
    default_symbol = sentiment.symbol if sentiment and sentiment.symbol else "BTCUSDT"
    symbol = normalize_symbol(input(f"Symbol (default {default_symbol}): ") or default_symbol)
    suggested_side = sentiment.bias if sentiment and sentiment.bias in {"BUY", "SELL"} else "BUY"
    side = validate_side(input(f"Side [BUY/SELL] (suggested {suggested_side}): ") or suggested_side)
    suggested_qty = sentiment.suggested_quantity if sentiment and sentiment.suggested_quantity else None
    qty_prompt = "Quantity (base asset)" + (f" (suggested {suggested_qty})" if suggested_qty else "") + ": "
    raw_qty = input(qty_prompt)
    if raw_qty:
        quantity = validate_quantity(raw_qty)
    elif suggested_qty is not None:
        quantity = validate_quantity(suggested_qty)
    else:
        raise ValueError("Quantity is required.")
    result = bot.place_market_order(symbol, side, quantity)
    _print_result(result)


def _interactive_limit(bot: BasicBot, sentiment: SentimentSignal | None) -> None:
    default_symbol = sentiment.symbol if sentiment and sentiment.symbol else "BTCUSDT"
    symbol = normalize_symbol(input(f"Symbol (default {default_symbol}): ") or default_symbol)
    suggested_side = sentiment.bias if sentiment and sentiment.bias in {"BUY", "SELL"} else "SELL"
    side = validate_side(input(f"Side [BUY/SELL] (suggested {suggested_side}): ") or suggested_side)
    suggested_qty = sentiment.suggested_quantity if sentiment and sentiment.suggested_quantity else None
    qty_prompt = "Quantity (base asset)" + (f" (suggested {suggested_qty})" if suggested_qty else "") + ": "
    raw_qty = input(qty_prompt)
    if raw_qty:
        quantity = validate_quantity(raw_qty)
    elif suggested_qty is not None:
        quantity = validate_quantity(suggested_qty)
    else:
        raise ValueError("Quantity is required.")
    suggested_price = sentiment.reference_price if sentiment and sentiment.reference_price else None
    price_prompt = "Limit price" + (f" (ref {suggested_price:.2f})" if suggested_price else "") + ": "
    raw_price = input(price_prompt)
    if raw_price:
        price = validate_price(raw_price)
    elif suggested_price is not None:
        price = validate_price(suggested_price)
    else:
        raise ValueError("Price is required for limit orders.")
    tif = validate_time_in_force(input("Time in force [GTC/IOC/FOK] (default GTC): ") or "GTC")
    result = bot.place_limit_order(symbol, side, quantity, price, time_in_force=tif)
    _print_result(result)


def _interactive_twap(bot: BasicBot, sentiment: SentimentSignal | None) -> None:
    default_symbol = sentiment.symbol if sentiment and sentiment.symbol else "BTCUSDT"
    symbol = normalize_symbol(input(f"Symbol (default {default_symbol}): ") or default_symbol)
    suggested_side = sentiment.bias if sentiment and sentiment.bias in {"BUY", "SELL"} else "BUY"
    side = validate_side(input(f"Side [BUY/SELL] (suggested {suggested_side}): ") or suggested_side)
    suggested_qty = sentiment.suggested_quantity if sentiment and sentiment.suggested_quantity else None
    total_prompt = "Total quantity" + (f" (suggested {suggested_qty})" if suggested_qty else "") + ": "
    raw_total = input(total_prompt)
    if raw_total:
        total_quantity = validate_quantity(raw_total)
    elif suggested_qty is not None:
        total_quantity = validate_quantity(suggested_qty)
    else:
        raise ValueError("Total quantity is required.")
    slices_input = input("Number of slices: ")
    try:
        slices = int(float(slices_input))
    except ValueError as exc:
        raise ValueError("Slices must be a positive integer.") from exc
    if slices <= 0:
        raise ValueError("Slices must be a positive integer.")
    interval_input = input("Interval seconds between slices (0 for immediate): ")
    try:
        interval = float(interval_input)
    except ValueError as exc:
        raise ValueError("Interval must be a non-negative number.") from exc
    if interval < 0:
        raise ValueError("Interval must be zero or greater.")
    order_type = input("Order type [MARKET/LIMIT] (default MARKET): ").strip().upper() or ORDER_TYPE_MARKET
    if order_type not in {ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT}:
        raise ValueError("Order type must be MARKET or LIMIT.")
    limit_price = None
    tif = "GTC"
    if order_type == ORDER_TYPE_LIMIT:
        limit_price = validate_price(float(input("Limit price for slices: ")))
        tif = validate_time_in_force(input("Time in force [GTC/IOC/FOK] (default GTC): ") or "GTC")

    executor = TWAPExecutor(
        place_market_order=bot.place_market_order,
        place_limit_order=bot.place_limit_order,
    )
    request = TWAPRequest(
        symbol=symbol,
        side=side,
        total_quantity=total_quantity,
        slices=slices,
        interval_seconds=interval,
        order_type=order_type,
        limit_price=limit_price,
        time_in_force=tif,
    )
    result = executor.execute(request)
    print(
        f"Executed TWAP: {result.executed_quantity} units across {len(result.slice_results)} slices."
    )
    if not result.is_success:
        for idx, slice_result in enumerate(result.slice_results, start=1):
            status = "OK" if slice_result.is_success else f"Error: {slice_result.error_message}"
            print(
                f"  Slice {idx}: qty={slice_result.request.quantity} -> {status}"
            )


def _print_result(result) -> None:
    status = "SUCCESS" if result.is_success else "FAILED"
    print("-" * 40)
    print(
        f"{status}: {result.request.symbol} {result.request.side} {result.request.quantity}"
    )
    if result.request.price:
        print(f"Price: {result.request.price}")
    if result.error_message:
        print(f"Error: {result.error_message}")
    print(f"Response: {result.raw_response}")
    print("-" * 40)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
