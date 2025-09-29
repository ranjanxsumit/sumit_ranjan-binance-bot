"""Streamlit dashboard for the Binance Futures order bot."""
from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

if __package__ in {None, ""}:  # Running as a script (e.g., streamlit run)
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.append(str(PROJECT_ROOT))
    from src.advanced.twap import TWAPExecutor, TWAPRequest
    from src.core.bot import BasicBot
    from src.core.config import BinanceConfig
    from src.core.logger import setup_logging
    from src.core.validators import validate_price, validate_quantity, validate_side
    from src.data.feeds import (
        DEFAULT_FEAR_GREED_PATH,
        DEFAULT_HISTORICAL_DATA_PATH,
        FearGreedSnapshot,
        HistoricalSummary,
        get_latest_fear_greed,
        summarize_historical_trades,
    )
    from src.signals.advisors import SentimentAdvisor, SentimentSignal
else:  # Imported as part of the src package (e.g., pytest or modules)
    from ..advanced.twap import TWAPExecutor, TWAPRequest
    from ..core.bot import BasicBot
    from ..core.config import BinanceConfig
    from ..core.logger import setup_logging
    from ..core.validators import validate_price, validate_quantity, validate_side
    from ..data.feeds import (
        DEFAULT_FEAR_GREED_PATH,
        DEFAULT_HISTORICAL_DATA_PATH,
        FearGreedSnapshot,
        HistoricalSummary,
        get_latest_fear_greed,
        summarize_historical_trades,
    )
    from ..signals.advisors import SentimentAdvisor, SentimentSignal


st.set_page_config(page_title="Binance Futures Bot", page_icon="🤖", layout="wide")

def _safe_get_bot() -> BasicBot | None:
    try:
        config = BinanceConfig.from_env()
    except EnvironmentError as exc:
        st.error(f"Configuration error: {exc}")
        return None
    setup_logging()
    return BasicBot.from_config(config)


@st.cache_data(show_spinner=False)
def load_fear_greed(path: str | None = None) -> FearGreedSnapshot | None:
    try:
        return get_latest_fear_greed(Path(path) if path else None)
    except FileNotFoundError:
        st.warning("Fear & Greed CSV not found. Place it in the project root or specify a path.")
    except Exception as exc:
        st.warning(f"Could not load Fear & Greed data: {exc}")
    return None


@st.cache_data(show_spinner=False)
def load_history(path: str | None = None) -> HistoricalSummary | None:
    try:
        return summarize_historical_trades(Path(path) if path else None)
    except FileNotFoundError:
        st.warning("Historical trades CSV not found. Place it in the project root or specify a path.")
    except Exception as exc:
        st.warning(f"Could not load historical trades: {exc}")
    return None


def _render_data_panel() -> tuple[FearGreedSnapshot | None, HistoricalSummary | None, SentimentSignal | None]:
    st.sidebar.header("Market Context")
    fear_path = st.sidebar.text_input("Fear & Greed CSV", value=str(DEFAULT_FEAR_GREED_PATH))
    history_path = st.sidebar.text_input("Historical Trades CSV", value=str(DEFAULT_HISTORICAL_DATA_PATH))

    fear = load_fear_greed(fear_path)
    history = load_history(history_path)
    sentiment: SentimentSignal | None = None

    if fear:
        st.sidebar.metric("Fear & Greed Index", f"{fear.value}", help=fear.classification)
        st.sidebar.caption(f"Last updated: {fear.date}")
    if history:
        st.sidebar.metric("Trades Loaded", f"{history.total_trades}")
        st.sidebar.metric("Gross Volume (USD)", f"{history.gross_volume_usd:,.2f}")
        st.sidebar.metric("Net Closed PnL (USD)", f"{history.net_closed_pnl:,.2f}")
        if history.latest_trades:
            st.sidebar.subheader("Recent Trades")
            rows = [asdict(trade) for trade in history.latest_trades]
            st.sidebar.dataframe(pd.DataFrame(rows))

    if fear or history:
        advisor = SentimentAdvisor(symbol="BTCUSDT", fear=fear, history=history)
        sentiment = advisor.build_signal()
        st.sidebar.markdown("---")
        st.sidebar.subheader("Sentiment Signal")
        st.sidebar.write(
            f"Bias: **{sentiment.bias}**  (confidence {int(sentiment.confidence * 100)}%)"
        )
        st.sidebar.caption(sentiment.rationale)
        if sentiment.reference_price:
            st.sidebar.metric("Reference Price", f"${sentiment.reference_price:,.2f}")
        if sentiment.suggested_quantity:
            st.sidebar.metric("Suggested Quantity", f"{sentiment.suggested_quantity}")

    return fear, history, sentiment


def _validate_numeric(label: str, value: float, allow_zero: bool = False) -> float:
    if value is None:
        raise ValueError(f"{label} is required")
    if not allow_zero and value <= 0:
        raise ValueError(f"{label} must be greater than zero")
    if allow_zero and value < 0:
        raise ValueError(f"{label} must be zero or greater")
    return float(value)


def _render_order_form(bot: BasicBot | None, signal: SentimentSignal | None) -> None:
    st.title("Binance Futures Order Bot")
    st.caption("Testnet trading assistant with market, limit, and TWAP support.")

    if bot is None:
        st.info("Configure your Binance API keys to enable order placement.")
        return

    if signal:
        st.info(
            f"Sentiment suggests **{signal.bias} {signal.symbol}** with {int(signal.confidence * 100)}% confidence."
            " Use the side panel to review the rationale."
        )

    def _side_index(options: list[str], value: str, fallback: int = 0) -> int:
        try:
            return options.index(value)
        except ValueError:
            return fallback

    tab_market, tab_limit, tab_twap = st.tabs(["Market Order", "Limit Order", "TWAP Strategy"])

    with tab_market:
        with st.form("market_form"):
            default_symbol = signal.symbol if signal else "BTCUSDT"
            symbol = st.text_input("Symbol", value=default_symbol).upper()
            side_options = ["BUY", "SELL"]
            suggested_side = signal.bias if signal and signal.bias in side_options else "BUY"
            side = st.selectbox("Side", options=side_options, index=_side_index(side_options, suggested_side))
            suggested_qty = float(signal.suggested_quantity) if signal and signal.suggested_quantity else 0.0
            quantity = st.number_input(
                "Quantity",
                min_value=0.0,
                value=max(suggested_qty, 0.0),
                step=0.001,
                format="%.6f",
            )
            if signal and signal.suggested_quantity:
                st.caption(f"Suggested quantity from sentiment: {signal.suggested_quantity}")
            submitted = st.form_submit_button("Submit Market Order")
            if submitted:
                try:
                    validate_side(side)
                    validated_qty = validate_quantity(quantity)
                    result = bot.place_market_order(symbol, side, validated_qty)
                    _render_result_panel(result)
                except Exception as exc:
                    st.error(f"Market order failed: {exc}")

    with tab_limit:
        with st.form("limit_form"):
            default_symbol = signal.symbol if signal else "BTCUSDT"
            symbol = st.text_input("Symbol ", value=default_symbol, key="limit_symbol").upper()
            side_options = ["BUY", "SELL"]
            suggested_side = signal.bias if signal and signal.bias in side_options else "SELL"
            side = st.selectbox(
                "Side ",
                options=side_options,
                index=_side_index(side_options, suggested_side, fallback=1),
                key="limit_side",
            )
            suggested_qty = float(signal.suggested_quantity) if signal and signal.suggested_quantity else 0.0
            quantity = st.number_input(
                "Quantity ",
                min_value=0.0,
                value=max(suggested_qty, 0.0),
                step=0.001,
                format="%.6f",
                key="limit_qty",
            )
            if signal and signal.suggested_quantity:
                st.caption(f"Suggested quantity: {signal.suggested_quantity}")
            suggested_price = float(signal.reference_price) if signal and signal.reference_price else 0.0
            price = st.number_input(
                "Limit Price",
                min_value=0.0,
                value=max(suggested_price, 0.0),
                step=0.5,
                format="%.2f",
            )
            if signal and signal.reference_price:
                st.caption(f"Reference price from sentiment: ${signal.reference_price:,.2f}")
            tif = st.selectbox("Time In Force", options=["GTC", "IOC", "FOK"], index=0)
            submitted = st.form_submit_button("Submit Limit Order")
            if submitted:
                try:
                    validate_side(side)
                    validated_qty = validate_quantity(quantity)
                    validated_price = validate_price(price)
                    result = bot.place_limit_order(symbol, side, validated_qty, validated_price, time_in_force=tif)
                    _render_result_panel(result)
                except Exception as exc:
                    st.error(f"Limit order failed: {exc}")

    with tab_twap:
        with st.form("twap_form"):
            default_symbol = signal.symbol if signal else "ETHUSDT"
            symbol = st.text_input("Symbol  ", value=default_symbol, key="twap_symbol").upper()
            side_options = ["BUY", "SELL"]
            suggested_side = signal.bias if signal and signal.bias in side_options else "BUY"
            side = st.selectbox(
                "Side  ",
                options=side_options,
                index=_side_index(side_options, suggested_side),
                key="twap_side",
            )
            suggested_qty = float(signal.suggested_quantity) if signal and signal.suggested_quantity else 0.0
            total_qty = st.number_input(
                "Total Quantity",
                min_value=0.0,
                value=max(suggested_qty, 0.0),
                step=0.01,
                format="%.6f",
            )
            if signal and signal.suggested_quantity:
                st.caption(f"Suggested total quantity: {signal.suggested_quantity}")
            slices = st.number_input("Slices", min_value=1, step=1, format="%d")
            interval = st.number_input("Interval (seconds)", min_value=0.0, step=5.0, format="%.1f")
            order_type = st.selectbox("Order Type", options=["MARKET", "LIMIT"], index=0)
            limit_price = None
            tif = "GTC"
            if order_type == "LIMIT":
                limit_price = st.number_input("Slice Limit Price", min_value=0.0, step=0.5, format="%.2f")
                tif = st.selectbox("Slice Time In Force", options=["GTC", "IOC", "FOK"], index=0)
            submitted = st.form_submit_button("Execute TWAP")
            if submitted:
                try:
                    validate_side(side)
                    validated_qty = validate_quantity(total_qty)
                    validated_slices = int(_validate_numeric("Slices", slices))
                    validated_interval = _validate_numeric("Interval", interval, allow_zero=True)
                    validated_price = validate_price(limit_price) if limit_price is not None else None

                    executor = TWAPExecutor(
                        place_market_order=bot.place_market_order,
                        place_limit_order=bot.place_limit_order,
                    )
                    request = TWAPRequest(
                        symbol=symbol,
                        side=side,
                        total_quantity=validated_qty,
                        slices=validated_slices,
                        interval_seconds=validated_interval,
                        order_type=order_type,
                        limit_price=validated_price,
                        time_in_force=tif,
                    )
                    result = executor.execute(request)
                    st.success(
                        f"Executed {result.executed_quantity} units across {len(result.slice_results)} slices"
                    )
                    if not result.is_success:
                        st.warning("Some slices failed. Check log output for details.")
                except Exception as exc:
                    st.error(f"TWAP execution failed: {exc}")


def _render_result_panel(result) -> None:
    st.write("---")
    status = "✅ Success" if result.is_success else "⚠️ Failed"
    st.subheader(status)
    st.json(
        {
            "symbol": result.request.symbol,
            "side": result.request.side,
            "quantity": result.request.quantity,
            "price": result.request.price,
            "time_in_force": result.request.time_in_force,
            "success": result.is_success,
            "error": result.error_message,
            "response": result.raw_response,
        }
    )


def main() -> None:
    _, _, sentiment = _render_data_panel()
    bot = _safe_get_bot()
    _render_order_form(bot, sentiment)


if __name__ == "__main__":
    main()
