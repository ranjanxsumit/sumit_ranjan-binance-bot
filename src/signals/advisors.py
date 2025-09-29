"""Sentiment-based trade recommendations using local CSV datasets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..data.feeds import (
    FearGreedSnapshot,
    HistoricalSummary,
    get_latest_fear_greed,
    summarize_historical_trades,
)


@dataclass
class SentimentSignal:
    symbol: str
    bias: str
    confidence: float
    rationale: str
    reference_price: Optional[float] = None
    suggested_quantity: Optional[float] = None


class SentimentAdvisor:
    """Combines fear/greed and historical trades to suggest a trade idea."""

    def __init__(
        self,
        symbol: str,
        fear: FearGreedSnapshot | None = None,
        history: HistoricalSummary | None = None,
    ) -> None:
        self.symbol = symbol
        self._fear = fear or get_latest_fear_greed()
        self._history = history or summarize_historical_trades()

    def build_signal(self) -> SentimentSignal:
        bias, confidence = self._compute_bias()
        rationale = self._build_rationale(bias, confidence)
        reference_price = None
        quantity = None

        if self._history and self._history.latest_trades:
            recent_symbol_trades = [
                trade for trade in self._history.latest_trades if trade.symbol.upper().endswith(self.symbol.upper())
            ]
            if recent_symbol_trades:
                reference_price = sum(t.execution_price for t in recent_symbol_trades) / len(recent_symbol_trades)
                quantity = sum(t.size_usd for t in recent_symbol_trades) / (len(recent_symbol_trades) * reference_price)

        return SentimentSignal(
            symbol=self.symbol,
            bias=bias,
            confidence=confidence,
            rationale=rationale,
            reference_price=reference_price,
            suggested_quantity=round(quantity, 4) if quantity else None,
        )

    def _compute_bias(self) -> tuple[str, float]:
        if not self._fear:
            return "HOLD", 0.0
        value = self._fear.value
        if value <= 25:
            return "BUY", 0.8
        if value <= 45:
            return "BUY", 0.6
        if value < 55:
            return "HOLD", 0.5
        if value < 75:
            return "SELL", 0.6
        return "SELL", 0.85

    def _build_rationale(self, bias: str, confidence: float) -> str:
        parts = []
        if self._fear:
            parts.append(
                f"Fear & Greed index {self._fear.value} ({self._fear.classification})"
            )
        if self._history:
            parts.append(
                f"Historical trades: {self._history.total_trades} events, net PnL ${self._history.net_closed_pnl:,.2f}"
            )
        parts.append(f"Suggested bias: {bias} ({int(confidence * 100)}% confidence)")
        return " | ".join(parts)
