"""High level bot facade used by the CLI."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL

try:
    from binance.error import ClientError  # Older python-binance versions
except ModuleNotFoundError:  # pragma: no cover - fallback for newer packages
    from binance.exceptions import BinanceAPIException as ClientError

from .binance_client import BinanceClientFactory
from .config import BinanceConfig
from .validators import (
    normalize_symbol,
    validate_price,
    validate_quantity,
    validate_side,
)
from ..orders.base import OrderRequest, OrderResult
from ..orders.limit_orders import LimitOrderExecutor
from ..orders.market_orders import MarketOrderExecutor

LOGGER = logging.getLogger(__name__)


@dataclass
class ExchangeCache:
    symbols: Iterable[str]


class BasicBot:
    """High-level façade orchestrating the order executors and validations."""

    def __init__(self, client: Client, exchange_cache: Optional[ExchangeCache] = None):
        self._client = client
        self._market_executor = MarketOrderExecutor(client)
        self._limit_executor = LimitOrderExecutor(client)
        self._exchange_cache = exchange_cache or self._load_exchange_cache()

    @classmethod
    def from_config(cls, config: BinanceConfig) -> "BasicBot":
        client = BinanceClientFactory.create_client(config)
        return cls(client)

    def _load_exchange_cache(self) -> ExchangeCache:
        try:
            info = self._client.futures_exchange_info()
            symbols = [entry["symbol"] for entry in info.get("symbols", []) if entry.get("contractType") == "PERPETUAL"]
            LOGGER.info("Loaded %d available perpetual futures symbols.", len(symbols))
            return ExchangeCache(symbols=symbols)
        except ClientError as exc:
            LOGGER.warning("Could not load exchange info: %s", exc)
            return ExchangeCache(symbols=[])

    def _validate_common(self, symbol: str, side: str, quantity: float) -> tuple[str, str, float]:
        normalized_symbol = normalize_symbol(symbol)
        validated_symbol = normalized_symbol
        if self._exchange_cache.symbols:
            validated_symbol = normalize_symbol(symbol)
            if normalized_symbol not in {s.upper() for s in self._exchange_cache.symbols}:
                raise ValueError(f"Symbol '{symbol}' is not in cached exchange info list.")
        validated_side = validate_side(side)
        validated_quantity = validate_quantity(quantity)
        return validated_symbol, validated_side, validated_quantity

    def place_market_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        validated_symbol, validated_side, validated_quantity = self._validate_common(symbol, side, quantity)
        request = OrderRequest(symbol=validated_symbol, side=validated_side, quantity=validated_quantity)
        return self._market_executor.execute(request)

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: str = "GTC",
    ) -> OrderResult:
        validated_symbol, validated_side, validated_quantity = self._validate_common(symbol, side, quantity)
        validated_price = validate_price(price)
        if validated_price is None:
            raise ValueError("Price is required for limit orders.")
        request = OrderRequest(
            symbol=validated_symbol,
            side=validated_side,
            quantity=validated_quantity,
            price=validated_price,
            time_in_force=time_in_force,
        )
        return self._limit_executor.execute(request)
