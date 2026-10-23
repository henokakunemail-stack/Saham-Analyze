"""FastAPI endpoints via Starlette TestClient — offline: candles are seeded into the temp DB."""
import pytest

from engine.db import save_candles


@pytest.fixture
def seeded(make_ohlcv):
    # Freshly cached daily bars satisfy the cache rule, so no yfinance call is made
    for ticker, seed in (("BBCA.JK", 3), ("^JKSE", 4)):
        save_candles(ticker, make_ohlcv(n=260, seed=seed).to_dict("records"))


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "online"


def test_market_summary_survives_network_failure(client):
    res = client.get("/api/market/summary")
    assert res.status_code == 200
    assert set(res.json()) == {"IHSG", "S&P 500", "USD/IDR"}


def test_chart(client, seeded):
    res = client.get("/api/stock/BBCA/chart")
    assert res.status_code == 200
    data = res.json()
    assert len(data["candles"]) >= 200
    assert len(data["volume"]) == len(data["candles"])
    assert len(data["cmf"]) == len(data["candles"])
    assert data["candles"][0]["time"] < data["candles"][-1]["time"]


def test_analysis(client, seeded):
    res = client.get("/api/stock/BBCA/analysis")
    assert res.status_code == 200
    analysis = res.json()
    assert 0 <= analysis["composite"]["score"] <= 100
    assert "cmf20" in analysis["money_flow"]
    assert analysis["ticker"] == "BBCA.JK"


def test_unknown_ticker_404(client):
    assert client.get("/api/stock/ZZZZ/chart").status_code == 404


def test_watchlist_roundtrip(client):
    client.post("/api/watchlist", json={"ticker": "BBCA.JK", "name": "BCA", "market": "IDX", "notes": "Top pick"})
    assert any(w["ticker"] == "BBCA.JK" for w in client.get("/api/watchlist").json())
    client.delete("/api/watchlist/BBCA.JK")
    assert not any(w["ticker"] == "BBCA.JK" for w in client.get("/api/watchlist").json())


def test_ai_models_offline_returns_structured_response(client):
    res = client.post("/api/ai/models", json={"base_url": "https://api.9router.com/v1", "api_key": "test_key"})
    assert res.status_code == 200
    assert "models" in res.json()


@pytest.mark.network
def test_live_chart_and_analysis(client):
    res = client.get("/api/stock/BBCA.JK/chart?force_refresh=true")
    assert res.status_code == 200
    assert len(res.json()["candles"]) > 100
    assert client.get("/api/stock/BBCA.JK/analysis").status_code == 200
