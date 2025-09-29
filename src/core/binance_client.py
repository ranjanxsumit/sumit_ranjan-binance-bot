"""Factory helpers around python-binance's Client for Futures trading."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from binance.client import Client

from .config import BinanceConfig

LOGGER = logging.getLogger(__name__)


TESTNET_FUTURES_URL = "https://testnet.binancefuture.com/fapi"


class BinanceClientFactory:
    """Builds authenticated python-binance clients following project defaults."""

    @staticmethod
    def create_client(config: BinanceConfig) -> Client:
        client = Client(
            api_key=config.api_key,
            api_secret=config.api_secret,
            testnet=config.testnet,
        )

        sync_client_time(client)

        if config.testnet:
            LOGGER.info("Using Binance Futures testnet endpoint at %s", TESTNET_FUTURES_URL)
            client.FUTURES_URL = TESTNET_FUTURES_URL
        if config.base_url_override:
            LOGGER.info("Overriding Futures base URL to %s", config.base_url_override)
            client.FUTURES_URL = config.base_url_override.rstrip("/") + "/fapi"

        if hasattr(client, "FUTURES_DEFAULT_RECV_WINDOW"):
            client.FUTURES_DEFAULT_RECV_WINDOW = config.recv_window

        return client


def sync_client_time(client: Client) -> int | None:
    """Synchronize the local timestamp offset against Binance server time."""
    try:
        server_time = client.futures_time()["serverTime"]
        local_time = int(time.time() * 1000)
        offset = int(server_time) - local_time
        if hasattr(client, "timestamp_offset"):
            client.timestamp_offset = offset
        else:  # pragma: no cover - compatibility fallback
            setattr(client, "timestamp_offset", offset)
        LOGGER.info("Applied time offset %sms", offset)
        return offset
    except Exception as exc:  # pragma: no cover - best effort
        LOGGER.warning("Could not sync server time: %s", exc)
        return None


def is_timestamp_error(exc: Exception) -> bool:
    """Detect Binance timestamp errors (-1021) from various client exceptions."""
    code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
    if isinstance(code, str) and code.lstrip("-+").isdigit():
        code = int(code)
    try:
        numeric_code = int(code) if code is not None else None
    except (TypeError, ValueError):  # pragma: no cover - defensive
        numeric_code = None
    message = str(getattr(exc, "message", str(exc)))
    message_lower = message.lower()
    return (
        numeric_code == -1021
        or "-1021" in message
        or "outside of the recvwindow" in message_lower
    )


def build_order_payload(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str,
    price: float | None = None,
    time_in_force: str | None = None,
    extra_params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "quantity": quantity,
    }
    if price is not None:
        payload["price"] = price
    if time_in_force is not None:
        payload["timeInForce"] = time_in_force
    if extra_params:
        payload.update(extra_params)
    return payload
