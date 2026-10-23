"""FastAPI Entrypoint for SAHAM Desktop Analytical Engine."""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import pandas as pd
import os
import threading
import time

from .config import DEFAULT_IDX_TICKERS, DEFAULT_US_TICKERS
from .db import (
    get_candles, save_screener_result, get_screener_results, delete_screener_rows_except,
    add_watchlist, remove_watchlist, get_watchlist,
    get_setting, set_setting,
    save_prediction_snapshot
)
from .collectors.market_data import fetch_stock_ohlcv, fetch_market_indices, normalize_ticker, prefetch_daily
from .collectors.news_feed import fetch_rss_news, filter_news_for_ticker
from .collectors.ticker_news import fetch_ticker_news
from .indicators.technical import compute_technical_indicators
from .indicators.money_flow import compute_money_flow, summarize_flow_proxy
from .indicators.trend import compute_trend_direction
from .indicators.screen_metrics import compute_screen_metrics
from .screener.sentiment import aggregate_news_sentiment, score_article_sentiment
from .screener.scoring import compute_composite_score
from .market_context import get_benchmark_context, direction_fields, with_news_risk
from .screener.predictions import select_predictions
from .collectors.data_quality import with_staleness, bar_is_final
from .db import get_data_quality_report
from . import scan_progress, universe, market_hours, notifications, app_lifecycle
from .routes import signals as signals_routes, feedback as feedback_routes
from .routes import universe as universe_routes, system as system_routes
from .routes import telegram as telegram_routes
from .telegram import service as telegram_service
from .collectors import abnormal_days, corp_actions
from .routes import market as market_routes
from . import market_breadth, sectors
from .screener.actionability import assess as assess_action, rank_key
from .screener.pipeline import analyze_frame
from .screener import session_recap, closing_review, financial_statements
from .screener.scoring import PILLAR_WEIGHTS
from .screener.fundamentals import fetch_and_evaluate_financials, MAX_SANE_PBV
from .screener.broker_summary import fetch_and_evaluate_broker_summary, fetch_from_sectors_app
from .ai import validation_log
from .ai.client import test_ai_connection, validate_signal_with_ai, get_ai_config, fetch_ai_models, list_router_accounts
from .ai import anthropic_login

app = FastAPI(title="SAHAM Desktop Analyzer Engine", version="2.0.0")

# Server mode (Linux deployment, docs/DEPLOY_LINUX.md): the UI is served by this app on the
# same origin, so cross-origin access stays off; SAHAM_BASIC_AUTH="user:password" puts the
# whole app (UI + API) behind a login. The desktop app keeps the open CORS of a local tool.
SERVER_MODE = os.environ.get("SAHAM_SERVER_MODE") == "1"
_BASIC_AUTH = os.environ.get("SAHAM_BASIC_AUTH", "")

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")   # Vite dev server (npm run dev)

if not SERVER_MODE:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

from fastapi import Request as _Request  # noqa: E402
from fastapi.responses import JSONResponse as _JSONResponse  # noqa: E402


@app.middleware("http")
async def _block_cross_site(request: _Request, call_next):
    """The UI is served by this app (same origin). A request a *different* website makes from
    the user's browser (img/form/fetch) must not read or change anything: CORS alone cannot stop
    "simple" requests such as GET with side effects or a POST beacon."""
    if request.url.path.startswith("/api/") and request.headers.get("sec-fetch-site") == "cross-site" \
            and request.headers.get("origin") not in DEV_ORIGINS:
        return _JSONResponse({"detail": "Permintaan lintas situs ditolak"}, status_code=403)
    return await call_next(request)

if _BASIC_AUTH:
    import base64
    import hmac
    from fastapi import Request
    from fastapi.responses import Response

    @app.middleware("http")
    async def _basic_auth(request: Request, call_next):
        if request.url.path != "/api/health":
            header = request.headers.get("authorization", "")
            ok = False
            if header.lower().startswith("basic "):
                try:
                    ok = hmac.compare_digest(base64.b64decode(header[6:]).decode("utf-8"), _BASIC_AUTH)
                except Exception:
                    ok = False
            if not ok:
                return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="SAHAM"'})
        return await call_next(request)

# ─── Background Auto-Scanner State ───────────────────────────────────────────
_scan_lock = threading.Lock()
_scan_state = {
    "is_scanning": False,
    "last_scan_time": None,
    "last_scan_market": None,
    "next_scan_in_sec": 300,
    "scan_count": 0
}
AUTO_SCAN_INTERVAL = 300  # 5 minutes

class WatchlistRequest(BaseModel):
    ticker: str
    name: Optional[str] = ""
    market: Optional[str] = "IDX"
    notes: Optional[str] = ""

class SettingsUpdateRequest(BaseModel):
    provider: Optional[str] = "9router"
    base_url: Optional[str] = "https://api.9router.com/v1"
    api_key: Optional[str] = ""
    model: Optional[str] = "deepseek-chat"
    sectors_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    anthropic_model: Optional[str] = None
    anthropic_auth_mode: Optional[str] = None   # "api_key" | "login"

class BrokerApiKeyTestRequest(BaseModel):
    provider: str = "sectors"
    api_key: str

class AiTestRequest(BaseModel):
    provider: Optional[str] = "9router"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    auth_mode: Optional[str] = None
    refresh: Optional[bool] = False

class OpenUrlRequest(BaseModel):
    url: str

class AiValidateSignalRequest(BaseModel):
    ticker: str
    market: Optional[str] = "IDX"

@app.post("/api/app/heartbeat")
def app_heartbeat():
    """Desktop window is alive (sent by the UI every 20 s)."""
    app_lifecycle.touch()
    return {"ok": True}


@app.post("/api/app/bye")
def app_bye():
    """Desktop window is closing (sendBeacon on pagehide). A reload sends heartbeats again."""
    app_lifecycle.bye()
    return {"ok": True}


@app.get("/api/health")
def health_check():
    return {"status": "online", "service": "SAHAM Analytical Engine", "version": "2.0.0"}

@app.get("/api/market/summary")
def get_market_summary():
    """Get macro index ribbon: IHSG, S&P 500, USD/IDR."""
    return fetch_market_indices()

# Per-stock news (Google News search) is fetched for the highest-ranked names only, to keep
# request volume reasonable; results are cached 30 minutes per ticker.
NEWS_ENRICH_TOP_N = 20


def _merge_news(general: List[Dict[str, Any]], specific: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for art in (specific or []) + general:
        key = (art.get("title") or "").strip().lower()[:80]
        if key and key not in seen:
            seen.add(key)
            out.append(art)
    return out


def _analyze_single_ticker(ticker: str, market: str, all_news: List[Dict[str, Any]], force_refresh: bool = False,
                           extra_news: Optional[List[Dict[str, Any]]] = None,
                           fresh_since: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    try:
        norm_ticker = normalize_ticker(ticker, market)
        # 1y of history so EMA200, weekly trend and swing structure are meaningful
        df = fetch_stock_ohlcv(norm_ticker, period="1y", force_refresh=force_refresh, fresh_since=fresh_since)
        if df.empty or len(df) < 15:
            return None

        bench_df, market_regime = get_benchmark_context(market)
        market_regime = with_news_risk(market_regime, all_news)
        ticker_news = _merge_news(filter_news_for_ticker(norm_ticker, all_news), extra_news)
        sent = aggregate_news_sentiment(ticker_news)
        a = analyze_frame(df, norm_ticker, market, sent, bench_df, market_regime, fetch_and_evaluate_financials)
        tech, flow, direction = a["tech"], a["flow"], a["direction"]
        composite, financials = a["composite"], a["financials"]

        result = {
            "ticker": norm_ticker,
            "market": market,
            "price": tech.get("price", 0),
            "change_pct": tech.get("change_pct", 0),
            "ema20": tech.get("ema20", 0),
            "ema50": tech.get("ema50", 0),
            "ema200": tech.get("ema200", 0),
            "rsi14": tech.get("rsi14", 50),
            "macd_hist": tech.get("macd_hist", 0),
            "cmf20": flow.get("cmf20", 0.0),
            "vol_ratio": tech.get("vol_ratio", 1.0),
            "money_flow_status": flow.get("money_flow_status", "NEUTRAL"),
            "vsa_signal": flow.get("vsa_signal", "NORMAL"),
            "vsa_label": flow.get("vsa_label", ""),
            "vsa_desc": flow.get("vsa_desc", ""),
            "spread_ratio": flow.get("spread_ratio", 1.0),
            "sentiment_score": sent.get("sentiment_score", 0.0),
            "catalyst": sent.get("catalyst", ""),
            "sentiment_label": sent.get("sentiment_label", "NEUTRAL"),
            "news_headlines": sent.get("headlines", [])[:4],
            "news_checked_at": datetime.now().isoformat() if extra_news is not None else None,
            "reading": composite.get("reading"),
            "score": composite.get("score", 50),
            "verdict": composite.get("verdict", "NEUTRAL"),
            "badge_text": composite.get("badge_text", "⚪ KONSOLIDASI"),
            "reasons": composite.get("reasons", []),
            "reason_signs": composite.get("reason_signs", []),
            "is_confirmed_breakout": composite.get("is_confirmed_breakout", False),
            "confluence_score": composite.get("confluence_score", 0),
            "confluence_gates": composite.get("confluence_gates", {}),
            "risk_reward_ratio": composite.get("risk_reward_ratio", 1.0),
            "target_tp": composite.get("target_tp", 0.0),
            "target_tp1": composite.get("target_tp1", composite.get("target_tp", 0.0)),
            "target_tp2": composite.get("target_tp2", round(tech.get("price", 0) * 1.15, 2)),
            "stop_loss": composite.get("stop_loss", 0.0),
            "entry_low": composite.get("entry_low", tech.get("entry_low", 0.0)),
            "entry_high": composite.get("entry_high", tech.get("entry_high", 0.0)),
            "recommended_entry": composite.get("recommended_entry", tech.get("recommended_entry", tech.get("price", 0))),
            "atr14": tech.get("atr14", 0.0),
            "candlestick": tech.get("candlestick", None),
            # Financial Health
            "health_grade": financials.get("health_grade", "MODERATE"),
            "health_score": financials.get("health_score", 50),
            "is_speculative": composite.get("is_speculative", False),
            "roe": financials.get("roe", 0.0),
            "net_margin": financials.get("net_margin", 0.0),
            "debt_to_equity": financials.get("debt_to_equity", 0.0),
            "pe": financials.get("pe", 0.0),
            "pbv": financials.get("pbv", 0.0),
            "pillars": composite.get("pillars", {}),
            "raw_score": composite.get("raw_score"),
            "pillar_values": composite.get("pillar_values", {}),
            "market_mode": composite.get("market_mode", "NORMAL"),
            "levels": composite.get("levels"),
            "screen": a["screen"],
            # ARA/ARB locks, suspension, corporate actions in the last 20 bars (incl. today)
            "abnormal_recent": a["abnormal_recent"],
            "action": a["action"],
            "pullback_state": composite.get("pullback_state"),
            "pullback_label": composite.get("pullback_label"),
            **direction_fields(direction),
        }

        if (result.get("screen") or {}).get("illiquid"):
            result["reasons"] = ["⚠️ Likuiditas rendah — sinyal teknikal kurang andal"] + list(result.get("reasons", []))[:4]
            result["reason_signs"] = [-1] + list(result.get("reason_signs", []))[:4]
        save_screener_result(result)
        return result
    except Exception as e:
        print(f"Error scanning {ticker}: {e}")
        return None

def _finalize_rows(results: List[Dict[str, Any]], market: str) -> None:
    """Fields that need the whole scan (sector rank, market breadth), stored with each row."""
    if not results:
        return
    try:
        sectors.annotate(results, market)          # row["sector"], row["sector_rank"]
    except Exception as e:
        print(f"[Sectors] {e}")
    # Status first (LAYAK > TUNGGU > HINDARI), then the score before the market brake
    results.sort(key=rank_key)
    for i, r in enumerate(results, 1):
        r["rank"] = i
        save_screener_result(r)
    # Rows of stocks no longer scanned (removed from the universe, or no data this time) would
    # linger with old ranks in the Top 10, the checkpoint and Telegram
    delete_screener_rows_except(market, [r["ticker"] for r in results])
    tickers = [r["ticker"] for r in results]
    try:
        market_breadth.update_today(market, tickers)
        sectors.refresh_async(tickers, market)     # Yahoo sector labels, weekly, in the background
    except Exception as e:
        print(f"[Breadth] {e}")


def _run_scan(market: str, force: bool = True) -> List[Dict[str, Any]]:
    """Core scan logic, returns sorted results.

    Hooks: universe.get_scan_universe (which tickers), scan_progress (live progress
    and partial results), notifications.on_scan_complete (alerts after a scan).
    """
    tickers = universe.get_scan_universe(market)
    scan_progress.start(market, len(tickers))
    results: List[Dict[str, Any]] = []
    try:
        t0 = time.time()
        all_news = fetch_rss_news()
        get_benchmark_context(market, force_refresh=force)
        t1 = time.time()
        # One batched download for the whole universe; the analysis below then reads the cache
        # (per-ticker requests for 100+ stocks every few minutes would hit Yahoo's rate limit)
        scan_progress.set_phase("download", f"Mengunduh harga terbaru {len(tickers)} saham")
        scan_started = datetime.now().astimezone()
        try:
            pre = prefetch_daily([normalize_ticker(t, market) for t in tickers], '1y', force)
            print(f"[Scan] prefetch {pre}")
            if pre.get("downloaded") and not pre.get("saved"):
                # Yahoo answered nothing: per-ticker retries would take ~15 min; use the cache
                print("[Scan] batch download returned nothing — analysing from the cache")
                scan_started = datetime.min.replace(tzinfo=scan_started.tzinfo)
        except Exception as e:
            print(f"[Scan] batch prefetch failed, falling back to per-ticker fetches: {e}")
        t2 = time.time()

        scan_progress.set_phase("analysis", "Menganalisis saham")
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(_analyze_single_ticker, t, market, all_news, False, None, scan_started): t
                       for t in tickers}
            for f in as_completed(futures):
                res = f.result()
                if res:
                    results.append(res)
                scan_progress.tick(futures[f], res)

        results.sort(key=lambda x: x["score"], reverse=True)

        t3 = time.time()
        # Second pass: fresh per-stock news for the top names, then re-score them with it
        scan_progress.set_phase("news", f"Memperbarui berita {NEWS_ENRICH_TOP_N} saham teratas")
        top = results[:NEWS_ENRICH_TOP_N]
        if top:
            def _enrich(row):
                news = fetch_ticker_news(row["ticker"], market)
                return _analyze_single_ticker(row["ticker"], market, all_news, False, extra_news=news,
                                              fresh_since=scan_started) or row
            with ThreadPoolExecutor(max_workers=4) as executor:
                enriched = list(executor.map(_enrich, top))
            by_ticker = {r["ticker"]: r for r in enriched}
            results = [by_ticker.get(r["ticker"], r) for r in results]
            results.sort(key=lambda x: x["score"], reverse=True)
        t4 = time.time()
        scan_progress.set_phase("finalize", "Menyimpan hasil, status, sektor & breadth")
        _finalize_rows(results, market)
        print(f"[Scan] {market} timings: news+index {t1 - t0:.1f}s · prices {t2 - t1:.1f}s · analysis {t3 - t2:.1f}s · "
              f"top news {t4 - t3:.1f}s · finalize {time.time() - t4:.1f}s")
        if results:
            # Predictions = the closing plan's LAYAK stocks, dated by that plan's close (an intraday
            # scan only re-checks today's position against yesterday's plan; a weekend rescan
            # rewrites the same date instead of adding a duplicate day)
            plan_dates = {str((r.get("levels") or {}).get("as_of") or "")[:10] for r in results
                          if (r.get("levels") or {}).get("bar_final") and not (r.get("levels") or {}).get("frozen")}
            if len(plan_dates) == 1 and "" not in plan_dates:
                plan_date = plan_dates.pop()
                save_prediction_snapshot(select_predictions(results), market=market, snapshot_date=plan_date)
                # The list the next session trades against, for the after-close recap
                session_recap.save_plan_list(market, plan_date, [r["ticker"] for r in results[:10]])
            market_hours.mark_scan_done(market)
    except Exception as e:
        scan_progress.finish(error=str(e))
        raise
    scan_progress.finish()
    try:
        notifications.on_scan_complete(market, results)
    except Exception as e:
        print(f"[Notifications] Error: {e}")
    telegram_service.on_scan_complete(market, results, [normalize_ticker(w["ticker"], market) for w in get_watchlist()
                                                         if (w.get("market") or "IDX") == market])
    return results

@app.get("/api/screener")
def run_screener(
    market: str = Query("IDX", pattern="^(IDX|US)$", description="Market: IDX or US"),
    force_refresh: bool = False,
    limit: int = Query(30, ge=1, le=500),
    cached_only: bool = False,
):
    """Run screening and ranking across top tickers. `cached_only` never starts a scan (the UI's
    quiet reload after each scan; otherwise a thin cache would make every reload rescan)."""
    if not force_refresh or cached_only:
        cached = get_screener_results(market=market)
        if any(r.get("rank") for r in cached):
            cached.sort(key=lambda r: r.get("rank") or 10**6)
        if cached_only or (cached and len(cached) >= 10):
            return {"count": len(cached[:limit]), "results": cached[:limit]}

    requested_at = datetime.now().isoformat()
    with _scan_lock:
        # A Scan pressed while another scan ran waited for it: serve that result, don't rescan
        last = _scan_state.get("last_scan_time")
        if last and _scan_state.get("last_scan_market") == market and last > requested_at:
            cached = get_screener_results(market=market)
            cached.sort(key=lambda r: r.get("rank") or 10**6)
            return {"count": len(cached[:limit]), "results": cached[:limit]}
        _scan_state["is_scanning"] = True
        _scan_state["last_scan_market"] = market
        try:
            results = _run_scan(market, force=True)
        finally:
            _scan_state["is_scanning"] = False
            _scan_state["last_scan_time"] = datetime.now().isoformat()
            _scan_state["scan_count"] += 1

    return {"count": len(results[:limit]), "results": results[:limit]}

@app.get("/api/screener/status")
def get_scan_status():
    """Get background auto-scanner status."""
    # No lock: _scan_lock is held for the whole scan, and a dict copy is atomic enough for a status read
    return dict(_scan_state)

# ─── Background Auto-Scanner Daemon ──────────────────────────────────────────
def _background_scanner():
    """Background daemon: scan each market every AUTO_SCAN_INTERVAL seconds while its exchange is open."""
    time.sleep(10)  # Wait for server startup
    while True:
        try:
            for market in ["IDX", "US"]:  # each gated by its own exchange hours
                if not market_hours.should_auto_scan_now(market):
                    continue
                acquired = _scan_lock.acquire(blocking=False)
                if not acquired:
                    break  # Manual scan running, skip this cycle
                try:
                    _scan_state["is_scanning"] = True
                    _scan_state["last_scan_market"] = market
                    print(f"[AutoScan] Starting background scan for {market}...")
                    _run_scan(market, force=True)
                    _scan_state["last_scan_time"] = datetime.now().isoformat()
                    _scan_state["scan_count"] += 1
                    print(f"[AutoScan] Completed scan for {market}")
                finally:
                    _scan_state["is_scanning"] = False
                    _scan_lock.release()
        except Exception as e:
            print(f"[AutoScan] Error: {e}")

        _scan_state["next_scan_in_sec"] = AUTO_SCAN_INTERVAL
        time.sleep(AUTO_SCAN_INTERVAL)

# SAHAM_DISABLE_AUTOSCAN=1 disables the daemon (tests, scripts) so importing the app has no side effects
if os.environ.get("SAHAM_DISABLE_AUTOSCAN") != "1":
    _scanner_thread = threading.Thread(target=_background_scanner, daemon=True, name="AutoScanner")
    _scanner_thread.start()

@app.get("/api/stock/{ticker}/chart")
def get_stock_chart(
    ticker: str,
    market: str = Query("IDX", pattern="^(IDX|US)$"),
    interval: str = Query("1d", pattern="^(1m|2m|5m|15m|30m|60m|1h|1d)$"),
    force_refresh: bool = False
):
    """Get candlestick OHLCV formatted for the in-app chart (lightweight-charts)."""
    norm_ticker = normalize_ticker(ticker, market)
    df = fetch_stock_ohlcv(norm_ticker, period="1y", interval=interval, force_refresh=force_refresh)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for {ticker}")

    candles = []
    volume_bars = []
    cmf_bars = []

    hl_diff = (df['high'] - df['low']).replace(0, 1e-9)
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / hl_diff
    mfv = mfm * df['volume']
    cmf_series = mfv.rolling(20, min_periods=1).sum() / df['volume'].rolling(20, min_periods=1).sum().replace(0, 1e-9)

    is_intraday = interval in ["1m", "2m", "5m", "15m", "30m", "60m", "1h"]

    for i, row in df.iterrows():
        t_val = int(row["date"]) if is_intraday else str(row["date"])[:10]
        candles.append({
            "time": t_val,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"])
        })
        is_green = float(row["close"]) >= float(row["open"])
        volume_bars.append({
            "time": t_val,
            "value": float(row["volume"]),
            "color": "rgba(16, 185, 129, 0.6)" if is_green else "rgba(239, 68, 68, 0.6)"
        })
        cmf_val = float(cmf_series.iloc[i]) if not cmf_series.isna().iloc[i] else 0.0
        cmf_bars.append({
            "time": t_val,
            "value": round(cmf_val, 4)
        })

    return {
        "ticker": norm_ticker,
        "interval": interval,
        "candles": candles,
        "volume": volume_bars,
        "cmf": cmf_bars,
        # Abnormal days as chart markers (daily chart only)
        "markers": [] if is_intraday else abnormal_days.markers(df, market),
    }

def _session_recap(market: str, ranked: List[Dict[str, Any]], picks: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """After the close: the last session against the plans it traded on (the Top 10 that was
    shown during it when remembered, else today's list) plus the watchlist."""
    try:
        dates = [str((r.get("levels") or {}).get("as_of") or "")[:10] for r in ranked[:20]]
        latest = max((d for d in dates if d), default="")
        plan_date, tickers = session_recap.plan_list_before(market, latest) if latest else (None, [])
        if tickers:
            chosen = {t: "Top 10" for t in tickers}
            chosen.update({t: s for t, s in picks.items() if s == "Watchlist" and t not in chosen})
        else:
            chosen = picks
        out = session_recap.recap(
            market, chosen,
            fetch=lambda t: fetch_stock_ohlcv(t, period="1y"),
            plan_fn=lambda f: compute_technical_indicators(f, market, freeze_live_bar=False).get("levels") or {},
            final_fn=lambda d: bar_is_final(d, market))
        return {**out, "list_from_plan": plan_date}
    except Exception as e:  # the recap is a convenience: never break the checkpoint
        print(f"[Recap] {e}")
        return None


@app.get("/api/plan/closing-review")
def plan_closing_review(market: str = Query("IDX", pattern="^(IDX|US)$"), top: int = 10):
    """Analisa Penutupan: everything measured from the last final close — what the last session did
    to the plans it traded on, and the plan for the next session with an honest assessment."""
    ranked = get_screener_results(market=market)
    if any(r.get("rank") for r in ranked):
        ranked.sort(key=lambda r: r.get("rank") or 10**6)
    watch = [normalize_ticker(w["ticker"], market) for w in get_watchlist()
             if (w.get("market") or ("IDX" if str(w["ticker"]).endswith(".JK") else "US")) == market]
    picks = {r["ticker"]: "Top 10" for r in ranked[:max(1, min(top, 20))]}
    picks.update({t: "Watchlist" for t in watch if t not in picks})
    recap = _session_recap(market, ranked, picks)
    out = closing_review.build(ranked, recap, watch, top=max(1, min(top, 20)))
    out["session"] = market_hours.session_status(market)
    out["market_mode"] = next((r.get("market_mode") for r in ranked[:top] if r.get("market_mode")), None)
    return out


@app.get("/api/plan/checkpoint")
def plan_checkpoint(market: str = Query("IDX", pattern="^(IDX|US)$"), top: int = 10):
    """Where today's price stands against each Top-10 / watchlist plan (made from the last final
    close). Meant for the lunch break, but answers during any live part of the day."""
    from .screener.trade_levels import POSITION_ORDER
    session = market_hours.session_status(market)
    picks: Dict[str, str] = {}
    ranked = get_screener_results(market=market)
    if any(r.get("rank") for r in ranked):
        ranked.sort(key=lambda r: r.get("rank") or 10**6)   # same Top 10 as the UI and Telegram
    for row in ranked[:max(1, min(top, 20))]:
        picks.setdefault(row["ticker"], "Top 10")
    for w in get_watchlist():
        if (w.get("market") or ("IDX" if str(w["ticker"]).endswith(".JK") else "US")) == market:
            picks.setdefault(normalize_ticker(w["ticker"], market), "Watchlist")
    if not session.get("trading_day_live"):
        return {"session": session, "live": False, "rows": [],
                "message": "Bursa tidak sedang berjalan — rencana berlaku untuk sesi berikutnya.",
                "recap": _session_recap(market, ranked, picks)}

    statuses = {r["ticker"]: (r.get("action") or {}).get("status") for r in ranked}

    def one(ticker: str, source: str) -> Optional[Dict[str, Any]]:
        df = fetch_stock_ohlcv(ticker, period="1y")
        if df.empty:
            return None
        lv = compute_technical_indicators(df, market).get("levels") or {}
        live = lv.get("live")
        if not live:  # no partial bar for today yet (holiday, or the feed has not caught up)
            return None
        return {"ticker": ticker, "source": source, "as_of": lv.get("as_of"), **live,
                # "Di zona beli" must not read as "buy" for a stock that is not LAYAK
                "action_status": statuses.get(ticker),
                "entry_low": lv["entry_low"], "entry_high": lv["entry_high"], "stop_loss": lv["stop_loss"],
                "recommended_entry": lv.get("recommended_entry"),
                "target_tp1": lv["target_tp1"], "target_tp2": lv["target_tp2"]}

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = [r for r in pool.map(lambda kv: one(*kv), picks.items()) if r]
    rows.sort(key=lambda r: POSITION_ORDER.index(r["status"]))
    msg = None if rows else "Harga hari ini belum tersedia dari sumber data (tertunda ±15 menit)."
    return {"session": session, "live": True, "rows": rows, "message": msg,
            "checked_at": datetime.now().astimezone().isoformat(timespec="minutes")}


@app.get("/api/stock/{ticker}/resolve")
def resolve_stock_market(ticker: str, market: str = Query("IDX", pattern="^(IDX|US)$")):
    """Which exchange has data for a code typed without its suffix: MSFT opened while the IDX
    tab is active must become a US stock, not MSFT.JK."""
    raw = ticker.strip().upper()
    if raw.endswith(".JK"):
        order = ["IDX"]
    elif raw.startswith("^"):
        order = [market]
    else:
        order = [market, "US" if market == "IDX" else "IDX"]
    for mk in order:
        norm = normalize_ticker(raw, mk)
        if not fetch_stock_ohlcv(norm, period="1y").empty:
            return {"ticker": norm, "market": mk}
    raise HTTPException(status_code=404, detail=f"Kode saham {raw} tidak ditemukan di BEI maupun bursa AS.")


@app.get("/api/stock/{ticker}/statements")
def get_stock_statements(ticker: str, market: str = Query("IDX", pattern="^(IDX|US)$"), refresh: bool = False):
    """Financial statements (annual + quarterly, Yahoo) read for a beginner: growth, cash quality,
    balance sheet, red flags, and valuation against the sector median of the scanned universe.
    Information only: none of this changes the score or the status (docs/hasil-uji-fundamental.md)."""
    norm = normalize_ticker(ticker, market)
    sector = sectors.sector_of(norm, market)
    data = financial_statements.fetch(norm, force=refresh)
    out = financial_statements.analyze(data.get("annual", {}), sector=sector, quarterly=data.get("quarterly"))
    out.update({"ticker": norm, "sector": sector,
                "currency": data.get("currency") or ("IDR" if market == "IDX" else "USD")})
    # Valuation vs peers: median PER / PBV of the same sector among the scanned stocks
    peers = [r for r in get_screener_results(market=market) if r.get("sector") == sector and r["ticker"] != norm]
    me = next((r for r in get_screener_results(market=market) if r["ticker"] == norm), None)

    def median(key: str) -> Optional[float]:
        # PBV above MAX_SANE_PBV is a currency mix-up (USD book value, IDR price), never a valuation
        vals = sorted(float(r[key]) for r in peers if r.get(key) and 0 < float(r[key]) <= MAX_SANE_PBV * 20
                      and (key != "pbv" or float(r[key]) <= MAX_SANE_PBV))
        return round(vals[len(vals) // 2], 2) if len(vals) >= 3 else None

    my_pbv = (me or {}).get("pbv") or None
    out["valuation"] = {"pe": (me or {}).get("pe") or None,
                        "pbv": my_pbv if my_pbv and my_pbv <= MAX_SANE_PBV else None,
                        "sector_pe": median("pe"), "sector_pbv": median("pbv"), "peers": len(peers)}
    return out


@app.get("/api/stock/{ticker}/analysis")
def get_stock_analysis(ticker: str, market: str = Query("IDX", pattern="^(IDX|US)$"), force_refresh: bool = False):
    """Get comprehensive indicators & status for detail page."""
    norm_ticker = normalize_ticker(ticker, market)
    df = fetch_stock_ohlcv(norm_ticker, period="1y", force_refresh=force_refresh)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    splits = corp_actions.fetch_splits(norm_ticker) if market == "IDX" else None
    if splits and not force_refresh:
        cached = get_candles(norm_ticker, limit=260)
        since = min((str(c.get("updated_at") or "")[:10] for c in cached if c.get("updated_at")), default="")
        if since and corp_actions.needs_refetch(norm_ticker, since, splits=splits):
            # A split after our candles were cached: the stored history is unadjusted
            df = fetch_stock_ohlcv(norm_ticker, period="1y", force_refresh=True)

    all_news = fetch_rss_news()
    ticker_news = _merge_news(filter_news_for_ticker(norm_ticker, all_news), fetch_ticker_news(norm_ticker, market))
    sent = aggregate_news_sentiment(ticker_news)
    bench_df, market_regime = get_benchmark_context(market)
    market_regime = with_news_risk(market_regime, all_news)
    a = analyze_frame(df, norm_ticker, market, sent, bench_df, market_regime, fetch_and_evaluate_financials, splits)
    tech, flow, direction, comp, financials = a["tech"], a["flow"], a["direction"], a["composite"], a["financials"]
    abnormal = a["abnormal_recent"]
    vol_ratio = tech.get("vol_ratio", 1.0)
    change_pct = tech.get("change_pct", 0.0)
    current_price = tech.get("price", 0.0)
    cmf20 = flow.get("cmf20", 0.0)
    vsa_signal = flow.get("vsa_signal", "NORMAL")
    comp["pillar_weights"] = PILLAR_WEIGHTS
    broker_sum = fetch_and_evaluate_broker_summary(
        ticker=norm_ticker,
        market=market,
        current_price=current_price,
        cmf20=cmf20,
        vol_ratio=vol_ratio,
        change_pct=change_pct,
        vsa_signal=vsa_signal
    )

    return {
        "ticker": norm_ticker,
        "technical": tech,
        "money_flow": flow,
        "sentiment": sent,
        "composite": comp,
        "direction": direction,
        "market_regime": market_regime,
        "flow_summary": summarize_flow_proxy(a["scoring_df"], flow),
        "financials": financials,
        "broker_summary": broker_sum,
        "news": ticker_news[:8],
        "data_quality": with_staleness(dq) if (dq := get_data_quality_report(norm_ticker)) else None,
        "abnormal_recent": abnormal,
    }

@app.get("/api/stock/{ticker}/broker-summary")
def get_broker_summary_endpoint(ticker: str, market: str = Query("IDX", pattern="^(IDX|US)$"), refresh: bool = False):
    norm_ticker = normalize_ticker(ticker, market)
    df = fetch_stock_ohlcv(norm_ticker, period="3mo")
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No price data for {ticker}")

    tech = compute_technical_indicators(df, market)
    flow = compute_money_flow(df)
    current_price = tech.get("price", 0.0)
    cmf20 = flow.get("cmf20", 0.0)
    vol_ratio = tech.get("vol_ratio", 1.0)
    change_pct = tech.get("change_pct", 0.0)
    vsa_signal = flow.get("vsa_signal", "NORMAL")

    return fetch_and_evaluate_broker_summary(
        ticker=norm_ticker,
        market=market,
        current_price=current_price,
        cmf20=cmf20,
        vol_ratio=vol_ratio,
        change_pct=change_pct,
        vsa_signal=vsa_signal,
        force_refresh=refresh
    )

@app.post("/api/broker/test-connection")
def test_broker_api_key_endpoint(req: BrokerApiKeyTestRequest):
    key = req.api_key.strip()
    stored = get_setting("sectors_api_key", "")
    if key and not _is_new_secret(key, stored):
        key = stored  # masked value from the UI: test the stored key
    if not key:
        return {"ok": False, "message": "API Key tidak boleh kosong"}
    res = fetch_from_sectors_app("BBCA", key)
    if res and res.get("top_buyers"):
        return {
            "ok": True,
            "message": f"Koneksi berhasil! Terhubung ke Sectors.app IDX Feed ({len(res['top_buyers'])} Top Buyers terverifikasi)."
        }
    return {
        "ok": False,
        "message": "Gagal menghubungi Sectors.app. Periksa apakah API Key aktif dan kuota tersedia."
    }

@app.get("/api/watchlist")
def get_user_watchlist():
    return get_watchlist()

@app.post("/api/watchlist")
def add_to_watchlist(item: WatchlistRequest):
    add_watchlist(item.ticker, item.name, item.market, item.notes)
    return {"status": "added", "ticker": item.ticker}

@app.delete("/api/watchlist/{ticker}")
def delete_from_watchlist(ticker: str):
    remove_watchlist(ticker)
    return {"status": "removed", "ticker": ticker}

def _mask(secret: str) -> str:
    if not secret:
        return ""
    return secret[:4] + "..." + secret[-4:] if len(secret) > 8 else "***"


def _is_new_secret(value: Optional[str], current: str) -> bool:
    """True only for a real new value: not empty and not the masked form we sent to the UI
    (saving the masked string back would overwrite the real key)."""
    if value is None or not value.strip():
        return False
    v = value.strip()
    return v != _mask(current) and v != "***"


@app.get("/api/settings")
def get_settings_endpoint():
    cfg = get_ai_config()
    raw_key = cfg.get("api_key", "")
    masked_key = _mask(raw_key)
    anthropic_key = cfg.get("anthropic_api_key", "")

    sectors_key = get_setting("sectors_api_key", "")

    return {
        "provider": cfg.get("provider", "9router"),
        "base_url": cfg.get("base_url", "https://api.9router.com/v1"),
        "model": cfg.get("model", "deepseek-chat"),
        "is_api_key_set": bool(raw_key),
        "masked_api_key": masked_key,
        "is_sectors_key_set": bool(sectors_key),
        "masked_sectors_key": _mask(sectors_key),
        "anthropic_model": cfg.get("anthropic_model"),
        "anthropic_auth_mode": cfg.get("anthropic_auth_mode", "api_key"),
        "is_anthropic_key_set": bool(anthropic_key),
        "masked_anthropic_key": _mask(anthropic_key),
    }

@app.post("/api/settings")
def update_settings_endpoint(req: SettingsUpdateRequest):
    if req.provider is not None:
        set_setting("ai_provider", req.provider)
    if req.base_url is not None:
        set_setting("ai_base_url", req.base_url.rstrip("/"))
    if req.model is not None:
        set_setting("ai_model", req.model)
    if _is_new_secret(req.api_key, get_setting("ai_api_key", "")):
        set_setting("ai_api_key", req.api_key.strip())
    if req.sectors_api_key is not None and (not req.sectors_api_key.strip() or _is_new_secret(req.sectors_api_key, get_setting("sectors_api_key", ""))):
        set_setting("sectors_api_key", req.sectors_api_key.strip())
    if _is_new_secret(req.anthropic_api_key, get_setting("anthropic_api_key", "")):
        set_setting("anthropic_api_key", req.anthropic_api_key.strip())
    if req.anthropic_model is not None and req.anthropic_model.strip():
        set_setting("anthropic_model", req.anthropic_model.strip())
    if req.anthropic_auth_mode in ("api_key", "login"):
        set_setting("anthropic_auth_mode", req.anthropic_auth_mode)
    return {"status": "saved"}

@app.post("/api/ai/test-connection")
def test_ai_connection_endpoint(req: AiTestRequest):
    key = req.api_key
    if key and not _is_new_secret(key, get_setting("anthropic_api_key" if req.provider == "anthropic" else "ai_api_key", "")):
        key = None  # masked value from the UI: use the stored key
    return test_ai_connection(
        base_url=req.base_url,
        api_key=key,
        model=req.model,
        provider=req.provider,
        auth_mode=req.auth_mode,
    )

@app.post("/api/ai/models")
def get_ai_models_endpoint(req: AiTestRequest):
    key = req.api_key
    if key and not _is_new_secret(key, get_setting("anthropic_api_key" if req.provider == "anthropic" else "ai_api_key", "")):
        key = None
    return fetch_ai_models(
        base_url=req.base_url,
        api_key=key,
        provider=req.provider,
        auth_mode=req.auth_mode,
        refresh=bool(req.refresh),
    )


# ─── AI account sign-in ──────────────────────────────────────────────────────
@app.get("/api/ai/accounts")
def get_ai_accounts(base_url: Optional[str] = None, refresh: bool = False):
    """AI accounts connected inside 9router (Antigravity, Codex, Claude Code, ...)."""
    return list_router_accounts(base_url=base_url, refresh=refresh)


@app.get("/api/ai/anthropic/login-status")
def anthropic_login_status():
    return anthropic_login.login_status()


@app.post("/api/ai/anthropic/install-cli")
def anthropic_install_cli():
    """Download the official Anthropic CLI (pinned version, SHA-256 verified) in the background."""
    return anthropic_login.start_install()


@app.post("/api/ai/anthropic/login")
def anthropic_login_start():
    res = anthropic_login.start_login()
    if res.get("ok"):
        set_setting("anthropic_auth_mode", "login")
    return res


@app.post("/api/ai/anthropic/logout")
def anthropic_logout():
    return anthropic_login.logout()


_OPENABLE_HOSTS = ("localhost", "127.0.0.1", "console.anthropic.com", "platform.claude.com")


@app.post("/api/system/open-url")
def open_url_in_browser(req: OpenUrlRequest):
    """Open a sign-in page in the user's default browser. Only a short allow-list of hosts
    (local 9router dashboard, Anthropic Console) can be opened."""
    from urllib.parse import urlparse
    import webbrowser
    u = urlparse(req.url)
    raw = req.url or ""
    if (u.scheme not in ("http", "https") or (u.hostname or "") not in _OPENABLE_HOSTS
            or "\\" in raw or u.username or u.password or any(c.isspace() or ord(c) < 32 for c in raw)):
        raise HTTPException(status_code=400, detail="URL tidak diizinkan")
    from urllib.parse import urlunparse
    webbrowser.open(urlunparse(u))
    return {"ok": True}

@app.post("/api/ai/validate-signal")
def validate_signal_endpoint(req: AiValidateSignalRequest):
    norm_ticker = normalize_ticker(req.ticker, req.market or "IDX")
    df = fetch_stock_ohlcv(norm_ticker, period="1y")
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {norm_ticker}")

    market = req.market or "IDX"
    # Independent network fetches run side by side before the (slow) model call
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_news = pool.submit(fetch_rss_news)
        f_ticker_news = pool.submit(fetch_ticker_news, norm_ticker, market)
        f_bench = pool.submit(get_benchmark_context, market)
        all_news = f_news.result()
        ticker_news = _merge_news(filter_news_for_ticker(norm_ticker, all_news), f_ticker_news.result())
        bench_df, market_regime = f_bench.result()
    sent = aggregate_news_sentiment(ticker_news)
    market_regime = with_news_risk(market_regime, all_news)
    a = analyze_frame(df, norm_ticker, market, sent, bench_df, market_regime, fetch_and_evaluate_financials)
    tech, flow, direction, comp = a["tech"], a["flow"], a["direction"], a["composite"]

    headlines = [n.get("title", "") for n in ticker_news if n.get("title")]

    result = validate_signal_with_ai(
        ticker=norm_ticker,
        market=market,
        technical=tech,
        money_flow=flow,
        composite=comp,
        news_headlines=headlines,
        direction=direction
    )
    try:  # track record: the outcome is measured later (see engine/ai/validation_log.py)
        validation_log.record(norm_ticker, market, result, comp, tech.get("price", 0),
                              get_ai_config()["provider"], str(df["date"].iloc[-1])[:10])
    except Exception as e:
        print(f"[AI log] could not record validation: {e}")
    return result


@app.get("/api/ai/validations")
def get_ai_validations(market: str = Query("IDX", pattern="^(IDX|US)$")):
    """AI validation track record: outcome after N trading days, AI verdicts vs engine verdicts."""
    bench_df, _ = get_benchmark_context(market)
    return validation_log.summary(market, lambda t: fetch_stock_ohlcv(t, period="1y"), bench_df)

# ─── Feature routers (must be registered before the SPA catch-all below) ─────
app.include_router(signals_routes.router)
app.include_router(feedback_routes.router)
app.include_router(universe_routes.router)
app.include_router(system_routes.router)
app.include_router(telegram_routes.router)
app.include_router(market_routes.router)


# ─── Telegram bot: data the bot reads from the engine ───────────────────────
def _tg_analysis(code: str, market: str):
    found = resolve_stock_market(code, market)
    return get_stock_analysis(found["ticker"], found["market"]), found["market"]


def _tg_request_scan(market: str) -> None:
    """Closing scan that was missed (app/server was off at 16:50): run it once, never alongside another."""
    if not _scan_lock.acquire(blocking=False):
        return
    try:
        _scan_state["is_scanning"] = True
        _run_scan(market, force=True)
        _scan_state["last_scan_time"] = datetime.now().isoformat()
    finally:
        _scan_state["is_scanning"] = False
        _scan_lock.release()


def _tg_history(market: str, days: int):
    from .screener.predictions import recent_summary
    return recent_summary(market, days)


def _tg_expected_close(market: str) -> str:
    from .collectors.data_quality import last_closed_session
    return last_closed_session("^JKSE" if market == "IDX" else "^GSPC").date().isoformat()


telegram_service.configure(
    scanning=lambda: bool(scan_progress.snapshot(include_results=False).get("active")),
    results=lambda m: get_screener_results(market=m),
    checkpoint=plan_checkpoint,
    analysis=_tg_analysis,
    session=market_hours.session_status,
    history=_tg_history,
    expected_close=_tg_expected_close,
    request_scan=_tg_request_scan,
)
if os.environ.get("SAHAM_DISABLE_AUTOSCAN") != "1":
    telegram_service.start()

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from .config import get_resource_path

dist_dir = get_resource_path("ui/dist")
if dist_dir.exists():
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    _dist_root = dist_dir.resolve()

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Endpoint tidak ditemukan")
        file_path = (dist_dir / full_path).resolve()
        # Never serve anything outside ui/dist (e.g. "/../../engine/saham.db" on a server)
        if file_path.is_relative_to(_dist_root) and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(dist_dir / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("engine.main:app", host="127.0.0.1", port=8765, reload=True)
