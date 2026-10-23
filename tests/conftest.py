"""Shared pytest setup: throwaway DB, no background scanner, no accidental network.

The environment is set at import time (conftest is imported before any test module), because
engine.config binds DB_PATH and engine.main decides on the autoscan thread at import.
"""
import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_TMP_DIR = tempfile.mkdtemp(prefix="saham_pytest_")
os.environ["SAHAM_DB_PATH"] = os.path.join(_TMP_DIR, "test.db")
os.environ["SAHAM_DISABLE_AUTOSCAN"] = "1"
sys.path.insert(0, str(ROOT))

from engine.config import BASE_DIR, DB_PATH  # noqa: E402

REAL_DB = (BASE_DIR / "saham.db").resolve()


class NetworkBlocked(OSError):
    """Raised when a test not marked `network` tries to reach the internet."""


def pytest_configure(config):
    # Last line of defence: never let the suite run against the user's real database
    if Path(DB_PATH).resolve() == REAL_DB:
        raise pytest.UsageError("engine is bound to the real saham.db; tests must use SAHAM_DB_PATH")


@pytest.fixture(autouse=True)
def _offline_unless_marked(request, monkeypatch):
    """Block outbound connections (sockets + yfinance's curl_cffi) for tests without @pytest.mark.network."""
    if request.node.get_closest_marker("network"):
        yield
        return

    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host in ("127.0.0.1", "::1", "localhost") or self.family == getattr(socket, "AF_UNIX", None):
            return real_connect(self, address)
        raise NetworkBlocked(f"network access blocked in offline test: {address!r}")

    def blocked(*args, **kwargs):
        raise NetworkBlocked("network access blocked in offline test (getaddrinfo/curl)")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", blocked)
    try:
        import curl_cffi.requests as curl_requests
        monkeypatch.setattr(curl_requests.Session, "request", blocked)
    except Exception:
        pass
    # Don't sleep through yfinance retry backoff when the network is blocked
    try:
        from engine.collectors import market_data
        monkeypatch.setattr(market_data, "YF_RETRIES", 1)
    except Exception:
        pass
    yield


@pytest.fixture
def client():
    from starlette.testclient import TestClient
    from engine.main import app
    return TestClient(app)


@pytest.fixture
def make_ohlcv():
    """Factory for synthetic daily OHLCV frames (string dates, like fresh yfinance rows)."""
    import numpy as np
    import pandas as pd

    def _make(n=260, drift=0.001, vol=0.01, seed=1, start=1000.0, end=None):
        rng = np.random.default_rng(seed)
        close = start * np.exp(np.cumsum(drift + rng.normal(0, vol, n)))
        open_ = np.concatenate([[start], close[:-1]])
        spread = np.abs(rng.normal(0, vol, n)) * close
        dates = pd.bdate_range(end=end or pd.Timestamp.today().normalize(), periods=n)
        return pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": open_, "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread, "close": close,
            "volume": rng.integers(800_000, 1_200_000, n).astype(float),
        })
    return _make
