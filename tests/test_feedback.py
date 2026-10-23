"""Speed & Feedback: live scan progress state + RSS news cache (fully offline)."""
import os
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

# Throwaway DB and no background scanner — must be set before importing engine
os.environ.setdefault("SAHAM_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="saham_fb_"), "test.db"))
os.environ["SAHAM_DISABLE_AUTOSCAN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from starlette.testclient import TestClient

from engine import scan_progress
from engine.collectors import news_feed


# ─── Scan progress ───────────────────────────────────────────────────────────

def test_progress_transitions_and_partial_results():
    scan_progress.start("IDX", 4)
    s = scan_progress.snapshot()
    assert s["active"] and s["market"] == "IDX"
    assert (s["total"], s["done"], s["failed"]) == (4, 0, 0)
    assert s["results"] == [] and s["eta_sec"] is None

    scan_progress.tick("AAAA.JK", {"ticker": "AAAA.JK", "score": 40})
    scan_progress.tick("BBBB.JK", {"ticker": "BBBB.JK", "score": 80})
    scan_progress.tick("CCCC.JK", None)
    s = scan_progress.snapshot()
    assert (s["done"], s["failed"]) == (3, 1)
    assert s["current_ticker"] == "CCCC.JK"
    assert [r["ticker"] for r in s["results"]] == ["BBBB.JK", "AAAA.JK"]  # sorted by score
    assert s["failed_tickers"] == ["CCCC.JK"]
    assert "CCCC.JK" in s["last_error"]
    assert s["eta_sec"] is not None and s["eta_sec"] >= 0
    assert s["percent"] == 75.0

    scan_progress.tick("DDDD.JK", {"ticker": "DDDD.JK", "score": 60})
    scan_progress.finish()
    s = scan_progress.snapshot()
    assert not s["active"] and s["error"] is None and s["finished_at"]
    assert s["eta_sec"] == 0
    assert [r["ticker"] for r in s["results"]] == ["BBBB.JK", "DDDD.JK", "AAAA.JK"]

    # A new scan resets everything
    scan_progress.start("US", 2)
    s = scan_progress.snapshot()
    assert s["results"] == [] and s["failed_tickers"] == [] and s["last_error"] is None


def test_progress_finish_with_error():
    scan_progress.start("IDX", 3)
    scan_progress.finish(error="boom")
    s = scan_progress.snapshot(include_results=False)
    assert not s["active"] and s["error"] == "boom" and s["last_error"] == "boom"
    assert "results" not in s


def test_progress_snapshot_is_a_copy():
    scan_progress.start("IDX", 1)
    scan_progress.tick("AAAA.JK", {"ticker": "AAAA.JK", "score": 10})
    s = scan_progress.snapshot()
    s["results"][0]["score"] = 999
    assert scan_progress.snapshot()["results"][0]["score"] == 10


def test_progress_endpoint():
    from engine.main import app
    client = TestClient(app)

    scan_progress.start("IDX", 2)
    scan_progress.tick("AAAA.JK", {"ticker": "AAAA.JK", "score": 70})
    r = client.get("/api/screener/progress")
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True and body["done"] == 1 and body["total"] == 2
    assert body["results"][0]["ticker"] == "AAAA.JK"

    r = client.get("/api/screener/progress", params={"include_results": "false"})
    assert "results" not in r.json()

    scan_progress.tick("BBBB.JK", None)
    scan_progress.finish()
    body = client.get("/api/screener/progress").json()
    assert body["active"] is False and body["failed"] == 1 and body["percent"] == 100.0


# ─── News cache ──────────────────────────────────────────────────────────────

def _fake_feed(title):
    return SimpleNamespace(entries=[SimpleNamespace(title=title, link="http://x", published="now", summary="s")],
                           bozo=False)


@pytest.fixture
def news(monkeypatch):
    """Offline news_feed: fake feeds, controllable clock, counted downloads."""
    calls = {"n": 0, "fail": False}
    lock = threading.Lock()

    def fake_download(url):
        with lock:
            calls["n"] += 1
        if calls["fail"]:
            raise TimeoutError("feed down")
        return _fake_feed(f"Berita {url}")

    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(news_feed, "_download", fake_download)
    monkeypatch.setattr(news_feed, "RSS_FEEDS", {"A": "http://a", "B": "http://b"})
    monkeypatch.setattr(news_feed.time, "time", lambda: clock["t"])
    news_feed.clear_news_cache()
    yield calls, clock
    news_feed.clear_news_cache()


def test_news_cache_hits_within_ttl(news):
    calls, clock = news
    first = news_feed.fetch_rss_news()
    assert {a["source"] for a in first} == {"A", "B"}
    assert calls["n"] == 2

    clock["t"] += news_feed.NEWS_CACHE_TTL - 1
    assert news_feed.fetch_rss_news() == first
    assert calls["n"] == 2  # served from cache

    clock["t"] += 2  # TTL expired
    news_feed.fetch_rss_news()
    assert calls["n"] == 4


def test_news_stale_cache_when_all_feeds_fail(news):
    calls, clock = news
    first = news_feed.fetch_rss_news()
    calls["fail"] = True
    clock["t"] += news_feed.NEWS_CACHE_TTL + 5
    assert news_feed.fetch_rss_news() == first  # stale but better than nothing


def test_news_empty_when_never_fetched_and_all_fail(news):
    calls, _ = news
    calls["fail"] = True
    assert news_feed.fetch_rss_news() == []


def test_news_partial_feed_failure(news, monkeypatch):
    def flaky(url):
        if url == "http://b":
            raise OSError("dns")
        return _fake_feed("ok")
    monkeypatch.setattr(news_feed, "_download", flaky)
    arts = news_feed.fetch_rss_news()
    assert [a["source"] for a in arts] == ["A"]


def test_news_concurrent_callers_download_once(news):
    calls, _ = news
    out = []
    threads = [threading.Thread(target=lambda: out.append(news_feed.fetch_rss_news())) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(out) == 8 and all(len(o) == 2 for o in out)
    assert calls["n"] == 2  # one refresh (2 feeds), not 8


def test_news_parses_through_feedparser(monkeypatch):
    """The real _download path hands bytes to feedparser; patch both ends."""
    monkeypatch.setattr(news_feed, "RSS_FEEDS", {"A": "http://a"})
    news_feed.clear_news_cache()

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"<rss/>"

    monkeypatch.setattr(news_feed.urllib.request, "urlopen", lambda req, timeout: _Resp())
    monkeypatch.setattr(news_feed.feedparser, "parse", lambda data: _fake_feed("Saham BBCA naik"))
    arts = news_feed.fetch_rss_news()
    assert arts and arts[0]["title"] == "Saham BBCA naik"
    assert news_feed.filter_news_for_ticker("BBCA.JK", arts)
    news_feed.clear_news_cache()
