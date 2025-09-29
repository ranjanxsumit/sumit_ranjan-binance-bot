"""Input validation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from binance.enums import FuturesType, SIDE_BUY, SIDE_SELL


SUPPORTED_SIDES = {SIDE_BUY, SIDE_SELL}


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    base_asset: str | None = None
    quote_asset: str | None = None


def normalize_symbol(symbol: str) -> str:
    if not symbol or not symbol.strip():
        raise ValueError("Symbol must be a non-empty string.")
    return symbol.strip().upper()


def validate_symbol(symbol: str, available_symbols: Iterable[str] | None = None) -> str:
    normal_symbol = normalize_symbol(symbol)
    if available_symbols is not None and normal_symbol not in {s.upper() for s in available_symbols}:
        raise ValueError(f"Symbol '{normal_symbol}' is not supported by the Binance Futures exchange info cache.")
    return normal_symbol


def validate_side(side: str) -> str:
    normalized = side.upper()
    if normalized not in SUPPORTED_SIDES:
        raise ValueError(f"Side must be BUY or SELL. Got '{side}'.")
    return normalized


def validate_quantity(quantity: float) -> float:
    try:
        qty = float(quantity)
    except (TypeError, ValueError) as exc:
        raise ValueError("Quantity must be a number.") from exc
    if qty <= 0:
        raise ValueError("Quantity must be greater than zero.")
    return qty


def validate_price(price: float | None) -> float | None:
    if price is None:
        return None
    try:
        price_val = float(price)
    except (TypeError, ValueError) as exc:
        raise ValueError("Price must be a number when provided.") from exc
    if price_val <= 0:
        raise ValueError("Price must be greater than zero.")
    return price_val


def validate_time_in_force(tif: str) -> str:
    tif_normalized = tif.upper()
    allowed = {"GTC", "IOC", "FOK"}
    if tif_normalized not in allowed:
        raise ValueError(f"Time in force must be one of {allowed}.")
    return tif_normalized


def validate_futures_type(futures_type: int | None) -> int:
    if futures_type is None:
        return FuturesType.USD_M
    if futures_type not in (FuturesType.USD_M, FuturesType.COIN_M):
        raise ValueError("Futures type must be either USD-M or COIN-M (per binance.enums.FuturesType).")
    return futures_type
