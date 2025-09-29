"""Unit tests for Binance client helpers."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.binance_client import is_timestamp_error, sync_client_time


class DummyClient:
    """Minimal client stub implementing futures_time and timestamp offset."""

    def __init__(self, server_time: int) -> None:
        self._server_time = server_time
        self.timestamp_offset = 0

    def futures_time(self) -> dict[str, int]:
        return {"serverTime": self._server_time}


class DummyNoAttrClient(DummyClient):
    """Client stub without a pre-defined timestamp_offset attribute."""

    def __init__(self, server_time: int) -> None:
        super().__setattr__("_server_time", server_time)

    def futures_time(self) -> dict[str, int]:
        return {"serverTime": self._server_time}


class DummyException(Exception):
    def __init__(self, code=None, message: str | None = None):
        super().__init__(message or "")
        self.code = code
        if message is not None:
            self.message = message


@pytest.mark.parametrize(
    "exc,expected",
    [
        (DummyException(code=-1021), True),
        (DummyException(code="-1021"), True),
        (DummyException(code=0, message="Timestamp for this request is outside of the recvWindow."), True),
        (DummyException(code=400), False),
    ],
)
def test_is_timestamp_error(exc: DummyException, expected: bool) -> None:
    assert is_timestamp_error(exc) is expected


@pytest.mark.parametrize("client_cls", [DummyClient, DummyNoAttrClient])
def test_sync_client_time_applies_offset(monkeypatch: pytest.MonkeyPatch, client_cls) -> None:
    fake_now_ms = 1_700_000_000_000
    server_time_ms = fake_now_ms + 750
    client = client_cls(server_time_ms)

    monkeypatch.setattr(time, "time", lambda: fake_now_ms / 1000)

    offset = sync_client_time(client)  # type: ignore[arg-type]

    assert offset == server_time_ms - fake_now_ms
    assert getattr(client, "timestamp_offset") == offset