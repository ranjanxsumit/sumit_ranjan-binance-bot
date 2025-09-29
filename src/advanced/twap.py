"""Time-Weighted Average Price (TWAP) execution strategy."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, List

from binance.enums import ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET

from ..orders.base import OrderResult

LOGGER = logging.getLogger(__name__)


@dataclass
class TWAPRequest:
    symbol: str
    side: str
    total_quantity: float
    slices: int
    interval_seconds: float
    order_type: str = ORDER_TYPE_MARKET
    limit_price: float | None = None
    time_in_force: str = "GTC"


@dataclass
class TWAPResult:
    request: TWAPRequest
    slice_results: List[OrderResult] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return all(result.is_success for result in self.slice_results)

    @property
    def executed_quantity(self) -> float:
        return sum(result.request.quantity for result in self.slice_results if result.is_success)


class TWAPExecutor:
    """Executes TWAP by sending fixed-size orders at regular intervals."""

    def __init__(
        self,
        place_market_order: Callable[[str, str, float], OrderResult],
        place_limit_order: Callable[[str, str, float, float, str], OrderResult],
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._place_market_order = place_market_order
        self._place_limit_order = place_limit_order
        self._sleep_fn = sleep_fn

    def execute(self, request: TWAPRequest) -> TWAPResult:
        if request.slices <= 0:
            raise ValueError("TWAP slices must be a positive integer.")
        if request.interval_seconds < 0:
            raise ValueError("TWAP interval must be zero or positive seconds.")
        if request.order_type == ORDER_TYPE_LIMIT and request.limit_price is None:
            raise ValueError("Limit TWAP orders require a limit_price.")

        base_size = request.total_quantity / request.slices
        slice_sizes = [round(base_size, 8) for _ in range(request.slices)]
        # Adjust final slice to absorb rounding drift.
        total = sum(slice_sizes)
        drift = request.total_quantity - total
        slice_sizes[-1] = round(slice_sizes[-1] + drift, 8)
        LOGGER.info(
            "Submitting TWAP order: %s slices of ~%s %s at %ss intervals.",
            request.slices,
            base_size,
            request.symbol,
            request.interval_seconds,
        )
        results: List[OrderResult] = []
        for idx, qty in enumerate(slice_sizes, start=1):
            extra = ""
            if request.order_type == ORDER_TYPE_LIMIT:
                extra = f" @ {request.limit_price}"
            LOGGER.info("TWAP slice %s/%s: quantity=%s%s", idx, request.slices, qty, extra)
            if request.order_type == ORDER_TYPE_MARKET:
                result = self._place_market_order(
                    request.symbol,
                    request.side,
                    qty,
                )
            elif request.order_type == ORDER_TYPE_LIMIT:
                result = self._place_limit_order(
                    request.symbol,
                    request.side,
                    qty,
                    request.limit_price,
                    request.time_in_force,
                )
            else:
                raise ValueError(f"Unsupported TWAP order type '{request.order_type}'.")
            results.append(result)
            if idx < request.slices and request.interval_seconds:
                self._sleep_fn(request.interval_seconds)
        return TWAPResult(request=request, slice_results=results)
