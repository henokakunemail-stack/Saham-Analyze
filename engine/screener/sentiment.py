"""Fast Local Financial Lexicon Sentiment Analyzer.

Phrase-weighted (Indonesian + English) headline scoring tuned for IDX news: insider buying,
buybacks, foreign net buy/sell, suspensions, dilution, earnings direction. Aggregation weights
each article by recency (3-day half-life), so last week's headline counts less than today's.
"""
import math
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

# (regex, weight, catalyst label). Order matters only for labels; all matches add up.
LEXICON: List[Tuple[str, float, str]] = [
    # Strong positives
    (r"\bbuy ?back\b|pembelian kembali saham", 2.0, "Buyback Saham"),
    (r"\b(direktur|komisaris|dirut|keluarga|pengendali|insider|bos)\b.{0,40}\b(borong|beli|tambah|memborong|membeli)\b"
     r"|\b(borong|memborong)\b.{0,30}\bsaham\b", 2.0, "Insider/Pengendali Membeli"),
    (r"\b(laba|profit|earnings|pendapatan)\b.{0,25}\b(melonjak|naik|tumbuh|meroket|rekor|jumps?|surges?|beats?|rises?)\b"
     r"|\brekor laba\b|\brecord (profit|revenue)\b", 2.0, "Kinerja Naik"),
    (r"\bdividen\b|\bdividend\b", 1.5, "Dividen"),
    (r"\b(net buy|beli bersih)\b|\basing\b.{0,20}\b(borong|net buy|beli)\b", 1.5, "Asing Net Buy"),
    (r"\b(akuisisi|acquisition|kontrak baru|new contract|ekspansi)\b", 1.0, "Ekspansi/Akuisisi"),
    (r"\b(upgrade|outperform|overweight|rekomendasi beli|target harga naik)\b", 1.0, "Analis Menaikkan Rekomendasi"),
    (r"\btarget harga\b|\bprice target\b", 0.4, ""),
    (r"\b(solid|menguat|rebound|bangkit|melesat|rally|gain)\b", 0.5, ""),
    # Strong negatives
    (r"\b(suspensi|suspend|disuspensi|penghentian sementara)\b", -2.5, "RISK: Suspensi"),
    (r"\b(pailit|bangkrut|gagal bayar|default|pkpu|bankruptcy)\b", -3.0, "RISK: Gagal Bayar/Pailit"),
    (r"\b(fraud|korupsi|manipulasi|investigasi|gugatan|lawsuit|delisting)\b", -2.5, "RISK: Hukum/Tata Kelola"),
    (r"\b(rugi|merugi|loss)\b|\b(laba|profit|earnings|pendapatan)\b.{0,25}\b(turun|anjlok|merosot|tergerus|falls?|drops?|misses?)\b",
     -2.0, "Kinerja Turun"),
    (r"\b(net sell|jual bersih)\b|\basing\b.{0,20}\b(jual|lepas|keluar|net sell)\b|\boutflow\b", -1.5, "Asing Net Sell"),
    (r"\b(uma|unusual market activity)\b", -1.0, "RISK: UMA (Aktivitas Tidak Wajar)"),
    (r"\b(rights issue|private placement|hmetd|penambahan modal)\b", -0.7, "Potensi Dilusi Saham"),
    (r"\b(downgrade|underweight|underperform|rekomendasi jual)\b", -1.0, "Analis Menurunkan Rekomendasi"),
    (r"\b(arb|auto reject bawah)\b", -1.0, ""),
    (r"\b(anjlok|ambruk|ambles|tertekan|melemah|longsor|terjun|slump|plunge)\b", -0.7, ""),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), w, label) for p, w, label in LEXICON]

HALF_LIFE_HOURS = 72.0

# Headlines that carry little stock-specific information get a lower weight:
# - round-ups naming several tickers ("Ide trading hari ini: AKRA, GOTO, MDKA")
# - price recaps ("Saham MEDC menguat 11%") — the chart already shows the move
ROUNDUP_MIN_CODES = 3
LOW_INFO_WEIGHT = 0.3
_TICKER_TOKEN = re.compile(r"\b[A-Z]{4}\b")
_PRICE_RECAP = re.compile(
    r"\b(saham|harga saham|shares?|stock)\b.{0,40}\b(menguat|melemah|naik|turun|rebound|anjlok|ambles|melonjak|"
    r"terkoreksi|ditutup|dibuka|rises?|falls?|jumps?|drops?|gains?)\b.{0,15}\d", re.IGNORECASE)


def _known_codes() -> set:
    """Ticker codes we recognise. Only these count toward 'round-up' detection, so Indonesian
    acronyms (DPRD, PLTU, BUMN, IHSG...) in a single-company story are not mistaken for tickers."""
    from ..config import DEFAULT_IDX_TICKERS, DEFAULT_US_TICKERS
    from ..collectors.ticker_news import COMPANY_NAMES
    codes = {t.replace(".JK", "") for t in DEFAULT_IDX_TICKERS + DEFAULT_US_TICKERS} | set(COMPANY_NAMES)
    codes |= set(EXTRA_IDX_CODES)
    return codes


# Other liquid IDX codes that often appear in round-up articles
EXTRA_IDX_CODES = (
    "EXCL", "ISAT", "JSMR", "MAPI", "ACES", "ERAA", "HRUM", "BUKA", "EMTK", "SIDO", "MYOR", "TOWR", "TBIG", "ESSA",
    "SCMA", "PWON", "BSDE", "CTRA", "SMRA", "INTP", "AALI", "LSIP", "TINS", "MBMA", "NCKL", "ADMR", "ARTO", "BBTN",
    "BJBR", "BNGA", "PNBN", "HMSP", "GGRM", "JPFA", "MIKA", "HEAL", "AUTO", "SRTG", "MAPA", "ELSA", "RAJA", "DSNG",
    "AADI", "PGEO", "DEWA", "PSAB", "BUMI", "WIFI", "DCII", "BYAN", "MTEL", "ARCI", "NICL", "CDIA", "RATU", "VKTR",
)
_KNOWN: set = set()


def headline_info_weight(title: str) -> float:
    global _KNOWN
    if not _KNOWN:
        _KNOWN = _known_codes()
    codes = {t for t in _TICKER_TOKEN.findall(title or "") if t in _KNOWN}
    if len(codes) >= ROUNDUP_MIN_CODES or _PRICE_RECAP.search(title or ""):
        return LOW_INFO_WEIGHT
    return 1.0


# Phrases that contain a lexicon word but mean something else (removed before scoring)
_NEUTRALIZE = re.compile(
    r"\b(stop ?loss|cut ?loss|take ?profit)\b"                      # trading advice, not "loss" news
    r"|\b(cabut|pencabutan|dibuka kembali|mencabut)\b.{0,25}\bsuspensi\b"  # suspension lifted
    r"|\bsuspensi\b.{0,25}\b(dicabut|berakhir)\b",
    re.IGNORECASE)
_NO_DIVIDEND = re.compile(r"\b(tidak|tak|batal|absen)\b.{0,20}\b(membagikan|bagi|tebar)?\s*dividen", re.IGNORECASE)


def score_article_sentiment(text: str) -> Dict[str, Any]:
    """Score one headline/text → sentiment_score in [-1, 1] and catalyst labels (strongest first)."""
    total = 0.0
    hits: List[Tuple[float, str]] = []
    no_dividend = bool(_NO_DIVIDEND.search(text or ""))
    text = _NEUTRALIZE.sub(" ", text or "")
    if no_dividend:
        total -= 1.0
        hits.append((-1.0, "Tidak Membagikan Dividen"))
    for rx, w, label in _COMPILED:
        if label == "Dividen" and no_dividend:
            continue
        if rx.search(text or ""):
            total += w
            if label:
                hits.append((w, label))
    score = math.tanh(total / 2.5) if total else 0.0
    label = "POSITIVE" if score > 0.15 else ("NEGATIVE" if score < -0.15 else "NEUTRAL")
    hits.sort(key=lambda h: abs(h[0]), reverse=True)
    return {"sentiment_score": round(score, 2), "sentiment_label": label, "catalysts": [h[1] for h in hits[:2]]}


def _age_hours(art: Dict[str, Any], now: datetime) -> Optional[float]:
    if art.get("age_hours") is not None:
        return float(art["age_hours"])
    raw = art.get("published")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
        dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return max(0.0, (now - dt).total_seconds() / 3600)
    except Exception:
        return None


def aggregate_news_sentiment(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Recency-weighted sentiment across a stock's articles (3-day half-life)."""
    if not articles:
        return {
            "sentiment_score": 0.0,
            "sentiment_label": "NEUTRAL",
            "catalyst": "Nol Berita Baru",
            "article_count": 0,
            "headlines": [],
        }

    now = datetime.now(timezone.utc)
    num = den = 0.0
    weighted_catalysts: Dict[str, float] = {}
    headlines = []
    for art in articles:
        res = score_article_sentiment(f"{art.get('title', '')} {art.get('summary', '')}")
        age = _age_hours(art, now)
        w = 0.5 ** (age / HALF_LIFE_HOURS) if age is not None else 0.5
        w *= headline_info_weight(art.get("title", ""))
        num += w * res["sentiment_score"]
        den += w
        for c in res["catalysts"]:
            weighted_catalysts[c] = weighted_catalysts.get(c, 0.0) + w * (abs(res["sentiment_score"]) + 0.1)
        headlines.append({
            "title": art.get("title", ""), "link": art.get("link", ""), "source": art.get("source", ""),
            "published": art.get("published", ""), "age_hours": age, "sentiment": res["sentiment_label"],
            "catalysts": res["catalysts"],
            "low_info": headline_info_weight(art.get("title", "")) < 1.0,
        })

    avg = num / den if den else 0.0
    # Few or stale articles → pull toward neutral (less evidence, less conviction)
    avg *= min(1.0, den / 1.5)
    label = "POSITIVE" if avg > 0.15 else ("NEGATIVE" if avg < -0.15 else "NEUTRAL")
    top_cat = max(weighted_catalysts.items(), key=lambda kv: kv[1])[0] if weighted_catalysts else None
    headlines.sort(key=lambda h: h["age_hours"] if h["age_hours"] is not None else 1e9)

    return {
        "sentiment_score": round(avg, 2),
        "sentiment_label": label,
        "catalyst": top_cat or ("Tidak Ada Katalis Khusus" if label != "NEGATIVE" else "Berita Cenderung Negatif"),
        "article_count": len(articles),
        "headlines": headlines[:6],
    }


# ─── Market-wide (systemic) news risk ────────────────────────────────────────
# Headlines about the market as a whole, not one issuer: index reclassification,
# trading halts, capital flight. These hit every stock regardless of its chart.
MARKET_RISK_KEYWORDS = {
    "msci": 1.0, "standalone": 2.0, "frontier market": 1.5, "downgrade": 1.0, "turun kasta": 2.0,
    "trading halt": 2.5, "penghentian perdagangan": 2.5, "circuit breaker": 2.0,
    "ihsg ambruk": 2.0, "ihsg anjlok": 1.5, "ihsg longsor": 1.5, "ihsg terjun": 1.5,
    "capital outflow": 1.5, "arus keluar modal": 1.5, "net sell asing": 1.0, "jual bersih asing": 1.0,
    "crash": 1.5, "krisis": 1.0, "rupiah anjlok": 1.0, "rupiah melemah tajam": 1.0,
}


def assess_market_news_risk(articles: List[Dict[str, Any]], max_headlines: int = 3) -> Dict[str, Any]:
    """Score systemic risk from the general news feed → level NONE / ELEVATED / HIGH."""
    total = 0.0
    hits: List[str] = []
    for art in articles or []:
        text = f"{art.get('title', '')} {art.get('summary', '')}".lower()
        weight = sum(w for kw, w in MARKET_RISK_KEYWORDS.items() if kw in text)
        if weight > 0:
            total += min(weight, 4.0)
            if len(hits) < max_headlines and art.get("title"):
                hits.append(art["title"])
    level = "HIGH" if total >= 8 else "ELEVATED" if total >= 3 else "NONE"
    return {"level": level, "score": round(total, 1), "headlines": hits}
