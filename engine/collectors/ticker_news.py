"""Per-stock latest news (Google News RSS search, last 7 days).

The general RSS feeds rarely mention a specific issuer, so most stocks showed "no news".
This collector searches news for one ticker, keeps only headlines that really mention it,
drops evergreen/tutorial content, and caches results for 30 minutes per ticker.
"""
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import feedparser

TICKER_NEWS_TTL = 1800      # seconds
FETCH_TIMEOUT = 8
MAX_AGE_DAYS = 7
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SAHAM-Analyzer"

# Issuer names that headlines use instead of the ticker code
COMPANY_NAMES = {
    "BBCA": ["BCA", "Bank Central Asia"], "BBRI": ["BRI", "Bank Rakyat"], "BMRI": ["Mandiri"],
    "BBNI": ["BNI", "Bank Negara"], "TLKM": ["Telkom"], "ASII": ["Astra International"],
    "ADRO": ["Adaro", "Alamtri"], "ICBP": ["Indofood CBP"], "INDF": ["Indofood"], "UNVR": ["Unilever"],
    "KLBF": ["Kalbe"], "AMRT": ["Alfamart", "Sumber Alfaria"], "CPIN": ["Charoen"], "ANTM": ["Antam", "Aneka Tambang"],
    "INCO": ["Vale Indonesia"], "PTBA": ["Bukit Asam"], "MDKA": ["Merdeka Copper"], "PGAS": ["PGN", "Perusahaan Gas"],
    "GOTO": ["GoTo", "Gojek", "Tokopedia"], "BRIS": ["BSI", "Bank Syariah Indonesia"], "MEDC": ["Medco"],
    "INKP": ["Indah Kiat"], "SMGR": ["Semen Indonesia"], "ITMG": ["Indo Tambangraya"], "AKRA": ["AKR Corporindo"],
    "TPIA": ["Chandra Asri"], "BREN": ["Barito Renewables"], "AMMN": ["Amman Mineral"], "CUAN": ["Petrindo"],
    "BRPT": ["Barito Pacific"],
    "AAPL": ["Apple"], "NVDA": ["Nvidia"], "MSFT": ["Microsoft"], "AMZN": ["Amazon"], "GOOGL": ["Alphabet", "Google"],
    "META": ["Meta Platforms"], "TSLA": ["Tesla"], "AMD": ["AMD"], "PLTR": ["Palantir"], "AVGO": ["Broadcom"],
    "NFLX": ["Netflix"], "INTC": ["Intel"], "QCOM": ["Qualcomm"], "BABA": ["Alibaba"], "COIN": ["Coinbase"],
}

# Evergreen / tutorial / promo titles: not news about the company's situation
NOISE_PATTERNS = [
    r"^cara\b", r"\bcara (beli|membeli|investasi)\b", r"^apa itu\b", r"\bmengenal\b", r"\bpanduan\b",
    r"\btutorial\b", r"\bhow to buy\b", r"\bshould you buy\b", r"\bprediksi saham hari ini\b",
]

_lock = threading.Lock()
_cache: Dict[str, Dict[str, Any]] = {}


def _code(ticker: str) -> str:
    return ticker.upper().replace(".JK", "")


def _query_url(ticker: str, market: str) -> str:
    code = _code(ticker)
    if market == "IDX":
        q = f'"{code}" saham when:{MAX_AGE_DAYS}d'
        return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "id", "gl": "ID", "ceid": "ID:id"})
    q = f'"{code}" stock when:{MAX_AGE_DAYS}d'
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})


def _published(entry: Any) -> Optional[datetime]:
    raw = entry.get("published") or entry.get("updated")
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def is_relevant(title: str, ticker: str) -> bool:
    """Headline must name the ticker (as a word) or the issuer, and not be evergreen content."""
    low = title.lower()
    if any(re.search(p, low) for p in NOISE_PATTERNS):
        return False
    code = _code(ticker)
    if re.search(rf"\b{re.escape(code)}\b", title, flags=re.IGNORECASE):
        return True
    # Whole-word match: short names like "BRI"/"BCA"/"AMD" must not hit inside other words
    return any(re.search(rf"\b{re.escape(name)}\b", title, flags=re.IGNORECASE) for name in COMPANY_NAMES.get(code, []))


def parse_entries(entries: List[Any], ticker: str, now: Optional[datetime] = None, limit: int = 8) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    seen = set()
    out = []
    for e in entries:
        title = (e.get("title") or "").strip()
        source = ""
        src = e.get("source")
        if isinstance(src, dict):
            source = src.get("title", "") or ""
        # Google News appends " - Source" to the title
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].strip()
        if not title or not is_relevant(title, ticker):
            continue
        key = re.sub(r"\W+", "", title.lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        pub = _published(e)
        age_h = (now - pub).total_seconds() / 3600 if pub else None
        if age_h is not None and age_h > MAX_AGE_DAYS * 24:
            continue
        out.append({
            "title": title,
            "link": e.get("link", ""),
            "source": source or "Google News",
            "published": pub.isoformat() if pub else "",
            "age_hours": round(age_h, 1) if age_h is not None else None,
            "summary": "",
        })
    out.sort(key=lambda a: a["age_hours"] if a["age_hours"] is not None else 1e9)
    return out[:limit]


def fetch_ticker_news(ticker: str, market: str = "IDX", limit: int = 8, force: bool = False) -> List[Dict[str, Any]]:
    """Latest relevant headlines for one stock (newest first). Never raises; [] on failure."""
    key = f"{market}:{ticker.upper()}"
    with _lock:
        hit = _cache.get(key)
    if hit and not force and time.time() - hit["at"] < TICKER_NEWS_TTL:
        return list(hit["items"])
    try:
        req = urllib.request.Request(_query_url(ticker, market), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            feed = feedparser.parse(resp.read())
        items = parse_entries(list(feed.entries), ticker, limit=limit)
    except Exception as e:
        print(f"[TickerNews] {ticker}: {e}")
        return list(hit["items"]) if hit else []  # stale beats nothing
    with _lock:
        _cache[key] = {"at": time.time(), "items": items}
    return list(items)
