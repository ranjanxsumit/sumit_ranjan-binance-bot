"""Market order execution logic."""
from __future__ import annotations

import logging

from binance.client import Client
from binance.enums import ORDER_TYPE_MARKET

try:
    from binance.error import ClientError
except ModuleNotFoundError:  # pragma: no cover
    from binance.exceptions import BinanceAPIException as ClientError

from ..core.binance_client import build_order_payload, is_timestamp_error, sync_client_time
from .base import OrderRequest, OrderResult

LOGGER = logging.getLogger(__name__)


class MarketOrderExecutor:
    """Encapsulates the logic for sending Binance Futures market orders."""

    def __init__(self, client: Client):
        self._client = client

    def execute(self, request: OrderRequest) -> OrderResult:
        payload = build_order_payload(
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=ORDER_TYPE_MARKET,
            extra_params=request.extra_params,
        )
        LOGGER.info("Submitting market order: %s", payload)
        try:
            response = self._client.futures_create_order(**payload)
            LOGGER.info("Market order accepted: %s", response)
            return OrderResult(request=request, raw_response=response, is_success=True)
        except ClientError as exc:
            final_exc = exc
            if is_timestamp_error(exc):
                LOGGER.warning("Market order hit timestamp error (-1021). Resyncing client clock and retrying once.")
                sync_client_time(self._client)
                try:
                    response = self._client.futures_create_order(**payload)
                    LOGGER.info("Market order accepted after time resync: %s", response)
                    return OrderResult(request=request, raw_response=response, is_success=True)
                except ClientError as retry_exc:  # pragma: no cover - retry path
                    final_exc = retry_exc
            LOGGER.error("Market order failed: %s", final_exc, exc_info=True)
            return OrderResult(
                request=request,
                raw_response=getattr(final_exc, "error_response", getattr(final_exc, "response", {})),
                is_success=False,
                error_message=str(final_exc),
            )
