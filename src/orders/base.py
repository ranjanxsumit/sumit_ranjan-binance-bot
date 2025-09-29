"""Shared order dataclasses and mixins."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class OrderRequest:
    symbol: str
    side: str
    quantity: float
    price: Optional[float] = None
    time_in_force: Optional[str] = None
    reduce_only: bool = False
    close_position: bool = False
    extra_params: Optional[Dict[str, Any]] = None


@dataclass
class OrderResult:
    request: OrderRequest
    raw_response: Dict[str, Any]
    is_success: bool
    error_message: Optional[str] = None
