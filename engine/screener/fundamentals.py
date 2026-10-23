"""Fundamental & Financial Health Analyzer for SAHAM Engine."""
import yfinance as yf
from typing import Dict, Any, Optional
from datetime import datetime
from ..db import get_fundamentals, save_fundamentals
from ..collectors.market_data import normalize_ticker

# Rows written before the debt-to-equity fix (×100 on values Yahoo already gives in %) are refetched
CACHE_VALID_FROM = "2026-10-23T12:00:00"


def _ttl_days(ticker: str) -> int:
    """6–8 days, spread per ticker so the whole universe never expires (and refetches) at once."""
    return 6 + sum(map(ord, ticker)) % 3

def fetch_and_evaluate_financials(
    ticker: str,
    market: str = "IDX",
    vol_ratio: float = 1.0,
    change_pct: float = 0.0,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """Fetch fundamental data from cache or yfinance, evaluate financial health."""
    norm_ticker = normalize_ticker(ticker, market)

    # 1. Check local SQLite cache (7-day TTL)
    if not force_refresh:
        cached = get_fundamentals(norm_ticker)
        if cached:
            try:
                up_dt = datetime.fromisoformat(cached["updated_at"])
                if (datetime.now() - up_dt).days < _ttl_days(norm_ticker) and cached["updated_at"] >= CACHE_VALID_FROM:
                    # Dynamically check speculative pump with current volume/price
                    is_spec = (
                        (cached.get("roe", 0) < 0 or cached.get("net_margin", 0) < 0 or cached.get("health_grade") == "DISTRESSED")
                        and (vol_ratio >= 1.8 or abs(change_pct) >= 5.0)
                    )
                    cached["is_speculative"] = bool(is_spec)
                    return cached
            except Exception:
                pass

    # 2. Fetch from yfinance
    roe = 0.0
    net_margin = 0.0
    der = 0.0
    pe = 0.0
    pbv = 0.0
    market_cap = 0.0

    ok = False
    try:
        t = yf.Ticker(norm_ticker)
        info = t.info or {}
        ok = any(info.get(k) is not None for k in ("returnOnEquity", "profitMargins", "marketCap", "trailingPE", "priceToBook"))
        if ok:
            try:  # the same (heavy, rate-limited) .info call also gives the sector
                from ..sectors import _save as save_sector
                save_sector(norm_ticker, info.get("sector"), info.get("industry"), "yahoo")
            except Exception:
                pass

        # ROE: yfinance returns e.g. 0.18 for 18%
        raw_roe = info.get("returnOnEquity")
        if raw_roe is not None:
            roe = round(float(raw_roe) * 100, 2)

        # Net Profit Margin: returns decimal e.g. 0.15 for 15%
        raw_margin = info.get("profitMargins")
        if raw_margin is not None:
            net_margin = round(float(raw_margin) * 100, 2)

        # Debt to Equity: returns e.g. 75.5 for 75.5% (or 0.75 in some markets)
        raw_der = info.get("debtToEquity")
        if raw_der is not None:
            der = round(float(raw_der), 2)

        # Valuation
        pe = round(float(info.get("trailingPE") or info.get("forwardPE") or 0.0), 2)
        pbv = round(float(info.get("priceToBook") or 0.0), 2)
        market_cap = float(info.get("marketCap") or 0.0)

    except Exception as e:
        print(f"Warning: could not fetch fundamentals for {norm_ticker}: {e}")
    if not ok:
        # A failed/empty fetch must not be cached as zeros for a week (it would read as a
        # "moderate" company and switch the speculative shield off): reuse the old row if any
        stale = get_fundamentals(norm_ticker) if not force_refresh else None
        if stale:
            return stale
        return {"ticker": norm_ticker, "market": market, "unavailable": True, "health_grade": "MODERATE",
                "health_score": 50, "is_speculative": False, "reasons": ["Data fundamental belum tersedia"],
                "pe": 0.0, "pbv": 0.0, "roe": 0.0, "debt_to_equity": 0.0, "net_margin": 0.0, "market_cap": 0.0}

    # 3. Financial Health Scoring (Base 50)
    score = 50
    reasons = []

    # Profitability (Weight: 40%)
    if roe >= 15.0:
        score += 20
        reasons.append(f"ROE sangat prima ({roe}%)")
    elif roe >= 8.0:
        score += 10
        reasons.append(f"ROE solid ({roe}%)")
    elif roe > 0.0:
        score += 4
    elif roe < 0.0:
        score -= 25
        reasons.append(f"Perusahaan merugi (ROE {roe}%)")

    if net_margin >= 15.0:
        score += 15
        reasons.append(f"Profit margin tebal ({net_margin}%)")
    elif net_margin >= 5.0:
        score += 8
    elif net_margin < 0.0:
        score -= 15
        reasons.append(f"Margin laba negatif ({net_margin}%)")

    # Solvency & Debt (Weight: 35%)
    if 0 < der <= 80.0:
        score += 15
        reasons.append(f"Utang terkendali (DER {der}%)")
    elif 80.0 < der <= 150.0:
        score += 5
    elif der > 250.0:
        score -= 20
        reasons.append(f"Beban utang tinggi (DER {der}%)")

    # Valuation (Weight: 25%)
    if 0 < pe <= 20.0 and 0 < pbv <= 2.5:
        score += 10
        reasons.append(f"Valuasi wajar (PER {pe}x, PBV {pbv}x)")
    elif pe > 60.0 or pbv > 8.0:
        score -= 10
        reasons.append(f"Valuasi premium/mahal (PER {pe}x)")
    elif pe < 0:
        score -= 10

    # Clamp 0-100
    health_score = int(max(10, min(100, round(score))))

    # Categorize Grade
    if health_score >= 65:
        health_grade = "HEALTHY"
    elif health_score >= 45:
        health_grade = "MODERATE"
    else:
        health_grade = "DISTRESSED"

    # Saham Spekulatif / Pom-pom detector (Saham Gorengan Shield)
    is_speculative = (
        (roe < 0 or net_margin < 0 or health_grade == "DISTRESSED")
        and (vol_ratio >= 1.8 or abs(change_pct) >= 5.0)
    )
    if is_speculative:
        reasons.append("⚠️ Waspada: Sinyal spike volume pada emiten kinerja lemah")

    result = {
        "ticker": norm_ticker,
        "market": market,
        "pe": pe,
        "pbv": pbv,
        "roe": roe,
        "debt_to_equity": der,
        "net_margin": net_margin,
        "market_cap": market_cap,
        "health_grade": health_grade,
        "health_score": health_score,
        "is_speculative": is_speculative,
        "reasons": reasons,
        "updated_at": datetime.now().isoformat()
    }

    # Save to SQLite cache
    try:
        save_fundamentals(result)
    except Exception as e:
        print(f"Error caching fundamentals for {norm_ticker}: {e}")

    return result
