"""Helpers to read local CSV data sets for insights."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FEAR_GREED_PATH = PROJECT_ROOT / "fear_greed_index.csv"
DEFAULT_HISTORICAL_DATA_PATH = PROJECT_ROOT / "historical_data.csv"


@dataclass
class FearGreedSnapshot:
    value: int
    classification: str
    date: str

    @property
    def label(self) -> str:
        return f"{self.value} ({self.classification}) on {self.date}"


@dataclass
class HistoricalTrade:
    timestamp: str
    symbol: str
    side: str
    execution_price: float
    size_usd: float
    closed_pnl: float


@dataclass
class HistoricalSummary:
    total_trades: int
    gross_volume_usd: float
    net_closed_pnl: float
    latest_trades: List[HistoricalTrade]


def _load_csv(path: Path, parse_dates: Optional[Iterable[str]] = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    return pd.read_csv(path, parse_dates=parse_dates)


@lru_cache(maxsize=1)
def get_latest_fear_greed(path: Path | None = None) -> FearGreedSnapshot:
    csv_path = path or DEFAULT_FEAR_GREED_PATH
    df = _load_csv(csv_path, parse_dates=["date"])
    latest_row = df.sort_values("date").iloc[-1]
    return FearGreedSnapshot(
        value=int(latest_row["value"]),
        classification=str(latest_row["classification"]),
        date=str(latest_row["date"].date()),
    )


@lru_cache(maxsize=1)
def summarize_historical_trades(path: Path | None = None, latest: int = 5) -> HistoricalSummary:
    csv_path = path or DEFAULT_HISTORICAL_DATA_PATH
    df = _load_csv(csv_path)

    # Normalize column names for easier access.
    normalized = {col: col.strip().replace(" ", "_").lower() for col in df.columns}
    df.rename(columns=normalized, inplace=True)

    total_trades = len(df)
    gross_volume_usd = float(df["size_usd"].sum())
    pnl_col = "closed_pnl" if "closed_pnl" in df.columns else None
    net_closed_pnl = float(df[pnl_col].sum()) if pnl_col else 0.0

    recent_rows = df.sort_values("timestamp", ascending=False).head(latest)
    latest_trades = [
        HistoricalTrade(
            timestamp=str(row["timestamp"]),
            symbol=str(row.get("coin", row.get("symbol", ""))),
            side=str(row.get("side", "")),
            execution_price=float(row.get("execution_price", 0.0)),
            size_usd=float(row.get("size_usd", 0.0)),
            closed_pnl=float(row.get("closed_pnl", 0.0)) if pnl_col else 0.0,
        )
        for _, row in recent_rows.iterrows()
    ]

    return HistoricalSummary(
        total_trades=total_trades,
        gross_volume_usd=gross_volume_usd,
        net_closed_pnl=net_closed_pnl,
        latest_trades=latest_trades,
    )
