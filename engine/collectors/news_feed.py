"""News RSS Aggregator for IDX and Global Stocks.

fetch_rss_news() is called by every scan and every stock-detail request, so the parsed
feeds are cached in memory for NEWS_CACHE_TTL seconds. Feeds are downloaded concurrently
with a per-feed timeout; if every feed fails the last good (stale) cache is returned.
"""
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from typing import List, Dict, Any, Optional
from datetime import datetime

import feedparser

from ..config import RSS_FEEDS

NEWS_CACHE_TTL = 600        # seconds a fetched article list stays fresh
FEED_TIMEOUT = 8            # seconds per feed download
MAX_ENTRIES_PER_FEED = 15

_cache_lock = threading.Lock()      # guards _cache
_refresh_lock = threading.Lock()    # only one thread downloads at a time
_cache: Dict[str, Any] = {"articles": None, "fetched_at": 0.0}


def _download(url: str) -> Any:
    """Fetch a feed with a hard timeout, then let feedparser parse the bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SAHAM Analyzer)"})
    with urllib.request.urlopen(req, timeout=FEED_TIMEOUT) as resp:
        data = resp.read()
    return feedparser.parse(data)


def _parse_feed(source_name: str, url: str) -> Optional[List[Dict[str, Any]]]:
    """Articles of one feed, or None when the feed could not be read."""
    try:
        feed = _download(url)
    except Exception as e:  # timeouts, DNS/HTTP errors, malformed URLs
        print(f"Error reading RSS {source_name}: {e}")
        return None

    articles = []
    for entry in getattr(feed, "entries", [])[:MAX_ENTRIES_PER_FEED]:
        title = (getattr(entry, "title", "") or "").strip()
        if not title:
            continue
        articles.append({
            "title": title,
            "link": getattr(entry, "link", ""),
            "published": getattr(entry, "published", datetime.now().strftime("%Y-%m-%d %H:%M")),
            "source": source_name,
            "summary": getattr(entry, "summary", ""),
        })
    if not articles and getattr(feed, "bozo", False):
        print(f"Error reading RSS {source_name}: {getattr(feed, 'bozo_exception', 'invalid feed')}")
        return None
    return articles


def _fetch_all() -> Optional[List[Dict[str, Any]]]:
    """Download all feeds concurrently. None when no feed succeeded."""
    feeds = list(RSS_FEEDS.items())
    if not feeds:
        return []
    pool = ThreadPoolExecutor(max_workers=len(feeds), thread_name_prefix="rss")
    try:
        futures = [pool.submit(_parse_feed, name, url) for name, url in feeds]
        wait(futures, timeout=FEED_TIMEOUT + 2)
        articles: List[Dict[str, Any]] = []
        any_ok = False
        for f in futures:
            if f.done() and f.exception() is None and f.result() is not None:
                any_ok = True
                articles.extend(f.result())
        return articles if any_ok else None
    finally:
        pool.shutdown(wait=False)


def _cached(max_age: float) -> Optional[List[Dict[str, Any]]]:
    with _cache_lock:
        arts = _cache["articles"]
        if arts is not None and time.time() - _cache["fetched_at"] < max_age:
            return list(arts)
    return None


def fetch_rss_news() -> List[Dict[str, Any]]:
    """Latest news articles from curated RSS feeds (cached, thread-safe)."""
    fresh = _cached(NEWS_CACHE_TTL)
    if fresh is not None:
        return fresh

    with _refresh_lock:
        # Another thread may have refreshed while we waited for the lock
        fresh = _cached(NEWS_CACHE_TTL)
        if fresh is not None:
            return fresh

        articles = _fetch_all()
        with _cache_lock:
            if articles is not None:
                _cache["articles"] = articles
                _cache["fetched_at"] = time.time()
                return list(articles)
            # Every feed failed: serve stale cache if we have one
            stale = _cache["articles"]
        return list(stale) if stale is not None else []


def clear_news_cache() -> None:
    """Drop the cached articles (used by tests)."""
    with _cache_lock:
        _cache["articles"] = None
        _cache["fetched_at"] = 0.0


def filter_news_for_ticker(ticker: str, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter news matching ticker symbol or company name."""
    clean_ticker = ticker.replace(".JK", "").upper()

    # Common company keywords
    name_map = {
        "BBCA": ["BCA", "BANK CENTRAL ASIA"],
        "BBRI": ["BRI", "BANK RAKYAT INDONESIA"],
        "BMRI": ["MANDIRI", "BANK MANDIRI"],
        "BBNI": ["BNI", "BANK NEGARA INDONESIA"],
        "TLKM": ["TELKOM"],
        "ASII": ["ASTRA"],
        "ADRO": ["ADARO"],
        "GOTO": ["GOTO", "GOJEK", "TOKOPEDIA"],
        "ANTM": ["ANTAM", "ANEKA TAMBANG"],
        "AAPL": ["APPLE", "IPHONE"],
        "NVDA": ["NVIDIA"],
        "TSLA": ["TESLA"],
        "MSFT": ["MICROSOFT"]
    }

    keywords = [clean_ticker]
    if clean_ticker in name_map:
        keywords.extend(name_map[clean_ticker])

    patterns = [re.compile(rf"(?<![A-Z0-9]){re.escape(kw)}(?![A-Z0-9])") for kw in keywords]
    matched = []
    for art in articles:
        text = f"{art['title']} {art.get('summary', '')}".upper()
        if any(p.search(text) for p in patterns):
            matched.append(art)

    return matched
