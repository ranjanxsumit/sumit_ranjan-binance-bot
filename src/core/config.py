"""Configuration helpers for the Binance Futures bot."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


_DOTENV_LOADED = False


def _load_dotenv_if_available() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        _DOTENV_LOADED = True
        return

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        load_dotenv(override=False)
    _DOTENV_LOADED = True


@dataclass
class BinanceConfig:
    """Holds configuration values required to talk to Binance Futures."""

    api_key: str
    api_secret: str
    testnet: bool = True
    recv_window: int = 5000
    base_url_override: Optional[str] = None

    @classmethod
    def from_env(cls) -> "BinanceConfig":
        """Load credentials and options from environment variables."""
        _load_dotenv_if_available()
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        if not api_key or not api_secret:
            raise EnvironmentError(
                "BINANCE_API_KEY and BINANCE_API_SECRET must be set as environment variables."
            )

        testnet_str = os.getenv("BINANCE_TESTNET", "true").lower()
        testnet = testnet_str in {"1", "true", "yes", "on"}

        recv_window = int(os.getenv("BINANCE_RECV_WINDOW", "5000"))
        base_url_override = os.getenv("BINANCE_BASE_URL")

        return cls(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            recv_window=recv_window,
            base_url_override=base_url_override,
        )
