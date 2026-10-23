"""SQLite database interface & cache management."""
import sqlite3
import json
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime
from .config import DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

_init_lock = threading.Lock()

def init_db():
    """Create/upgrade the schema. Idempotent and serialized across threads; only additive migrations."""
    with _init_lock:
        _init_db_locked()

def _init_db_locked():
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass

        # Candles table (OHLCV)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                updated_at TEXT,
                PRIMARY KEY (ticker, date)
            )
        """)

        # Screener cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS screener_cache (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                price REAL,
                change_pct REAL,
                ema20 REAL,
                ema50 REAL,
                ema200 REAL,
                rsi14 REAL,
                macd_hist REAL,
                cmf20 REAL,
                vol_ratio REAL,
                money_flow_status TEXT,
                sentiment_score REAL,
                catalyst TEXT,
                score INTEGER,
                verdict TEXT DEFAULT 'NEUTRAL',
                badge_text TEXT DEFAULT '',
                reasons TEXT DEFAULT '[]',
                is_confirmed_breakout INTEGER DEFAULT 0,
                confluence_score INTEGER DEFAULT 0,
                target_tp REAL DEFAULT 0.0,
                target_tp1 REAL DEFAULT 0.0,
                target_tp2 REAL DEFAULT 0.0,
                stop_loss REAL DEFAULT 0.0,
                recommended_entry REAL DEFAULT 0.0,
                risk_reward_ratio REAL DEFAULT 1.0,
                candlestick TEXT DEFAULT '{}',
                updated_at TEXT
            )
        """)

        # Auto-migration for existing screener_cache databases
        cursor.execute("PRAGMA table_info(screener_cache)")
        existing_cols = {row["name"] for row in cursor.fetchall()}
        migration_cols = [
            ("verdict", "TEXT DEFAULT 'NEUTRAL'"),
            ("badge_text", "TEXT DEFAULT ''"),
            ("reasons", "TEXT DEFAULT '[]'"),
            ("is_confirmed_breakout", "INTEGER DEFAULT 0"),
            ("confluence_score", "INTEGER DEFAULT 0"),
            ("target_tp", "REAL DEFAULT 0.0"),
            ("target_tp1", "REAL DEFAULT 0.0"),
            ("target_tp2", "REAL DEFAULT 0.0"),
            ("stop_loss", "REAL DEFAULT 0.0"),
            ("recommended_entry", "REAL DEFAULT 0.0"),
            ("risk_reward_ratio", "REAL DEFAULT 1.0"),
            ("candlestick", "TEXT DEFAULT '{}'"),
            ("entry_low", "REAL DEFAULT 0.0"),
            ("entry_high", "REAL DEFAULT 0.0"),
            ("atr14", "REAL DEFAULT 0.0"),
            ("health_grade", "TEXT DEFAULT 'MODERATE'"),
            ("health_score", "INTEGER DEFAULT 50"),
            ("is_speculative", "INTEGER DEFAULT 0"),
            ("roe", "REAL DEFAULT 0.0"),
            ("net_margin", "REAL DEFAULT 0.0"),
            ("debt_to_equity", "REAL DEFAULT 0.0"),
            ("pe", "REAL DEFAULT 0.0"),
            ("pbv", "REAL DEFAULT 0.0"),
            ("direction_score", "INTEGER DEFAULT 0"),
            ("direction_data", "TEXT DEFAULT '{}'"),
        ]
        for col_name, col_def in migration_cols:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE screener_cache ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass

        # Fundamentals cache (7-day TTL)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fundamentals_cache (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                pe REAL,
                pbv REAL,
                roe REAL,
                debt_to_equity REAL,
                net_margin REAL,
                market_cap REAL,
                health_grade TEXT DEFAULT 'MODERATE',
                health_score INTEGER DEFAULT 50,
                is_speculative INTEGER DEFAULT 0,
                reasons TEXT DEFAULT '[]',
                updated_at TEXT
            )
        """)

        # Broker summary cache (24-hour TTL)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS broker_summary_cache (
                ticker TEXT,
                trade_date TEXT,
                source TEXT DEFAULT 'PROXY',
                top_buyers TEXT DEFAULT '[]',
                top_sellers TEXT DEFAULT '[]',
                net_foreign_val REAL DEFAULT 0.0,
                bandar_status TEXT DEFAULT 'NEUTRAL',
                bandar_status_label TEXT DEFAULT 'Netral',
                bandar_avg_price REAL DEFAULT 0.0,
                top3_ratio REAL DEFAULT 1.0,
                summary_notes TEXT DEFAULT '[]',
                updated_at TEXT,
                PRIMARY KEY (ticker, trade_date)
            )
        """)

        # News cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                title TEXT UNIQUE,
                link TEXT,
                source TEXT,
                published TEXT,
                sentiment_score REAL,
                catalyst_label TEXT,
                created_at TEXT
            )
        """)

        # Watchlist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker TEXT PRIMARY KEY,
                name TEXT,
                market TEXT,
                added_at TEXT,
                notes TEXT
            )
        """)

        # App & AI Settings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)

        # Prediction Snapshots for Tracking & Accuracy Audit
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prediction_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                rank INTEGER NOT NULL,
                score INTEGER NOT NULL,
                verdict TEXT DEFAULT 'NEUTRAL',
                badge_text TEXT DEFAULT '',
                price_at_prediction REAL NOT NULL,
                recommended_entry REAL DEFAULT 0.0,
                target_tp1 REAL DEFAULT 0.0,
                target_tp2 REAL DEFAULT 0.0,
                stop_loss REAL DEFAULT 0.0,
                risk_reward_ratio REAL DEFAULT 1.0,
                confluence_score INTEGER DEFAULT 0,
                money_flow_status TEXT DEFAULT 'NEUTRAL',
                reasons TEXT DEFAULT '[]',
                created_at TEXT,
                UNIQUE(snapshot_date, market, ticker)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pred_date ON prediction_snapshots(snapshot_date, market)")

        # Migration for prediction_snapshots table
        cursor.execute("PRAGMA table_info(prediction_snapshots)")
        existing_pred_cols = {row["name"] for row in cursor.fetchall()}
        pred_migration_cols = [
            ("entry_low", "REAL DEFAULT 0.0"),
            ("entry_high", "REAL DEFAULT 0.0"),
            ("atr14", "REAL DEFAULT 0.0"),
            ("health_grade", "TEXT DEFAULT 'MODERATE'"),
            ("health_score", "INTEGER DEFAULT 50"),
            ("is_speculative", "INTEGER DEFAULT 0"),
            ("roe", "REAL DEFAULT 0.0"),
            ("net_margin", "REAL DEFAULT 0.0"),
            ("debt_to_equity", "REAL DEFAULT 0.0"),
            ("pe", "REAL DEFAULT 0.0"),
            ("pbv", "REAL DEFAULT 0.0"),
        ]
        for col_name, col_def in pred_migration_cols:
            if col_name not in existing_pred_cols:
                try:
                    cursor.execute(f"ALTER TABLE prediction_snapshots ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass

        # Latest OHLCV data-quality report per ticker (JSON, see collectors/data_quality.py)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_quality_reports (
                ticker TEXT PRIMARY KEY,
                score INTEGER,
                report TEXT DEFAULT '{}',
                updated_at TEXT
            )
        """)

        # Hot-path indexes. candles(ticker, date) is already covered by its PRIMARY KEY autoindex.
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_screener_market_score ON screener_cache(market, score)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pred_market_ticker ON prediction_snapshots(market, ticker, snapshot_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_ticker ON news(ticker)")

        # Default 9router AI settings if not set
        cursor.execute("""
            INSERT OR IGNORE INTO app_settings (key, value, updated_at)
            VALUES ('ai_provider', '9router', datetime('now'))
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO app_settings (key, value, updated_at)
            VALUES ('ai_base_url', 'https://api.9router.com/v1', datetime('now'))
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO app_settings (key, value, updated_at)
            VALUES ('ai_model', 'deepseek-chat', datetime('now'))
        """)

        conn.commit()

def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default

def set_setting(key: str, value: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=excluded.updated_at
        """, (key, value, now))
        conn.commit()

def save_candles(ticker: str, rows: List[Dict[str, Any]]):
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.executemany("""
                INSERT INTO candles (ticker, date, open, high, low, close, volume, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    updated_at=excluded.updated_at
            """, [(ticker, r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"], now) for r in rows])
        conn.commit()

def get_candles(ticker: str, limit: int = 250) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, open, high, low, close, volume, updated_at
            FROM candles
            WHERE ticker = ?
            ORDER BY date ASC
        """, (ticker,))
        rows = cursor.fetchall()
        if not rows:
            return []
        data = [dict(r) for r in rows]
        return data[-limit:]

def save_data_quality_report(ticker: str, report: Dict[str, Any]):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO data_quality_reports (ticker, score, report, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                score=excluded.score,
                report=excluded.report,
                updated_at=excluded.updated_at
        """, (ticker, int(report.get("score", 0)), json.dumps(report), datetime.now().isoformat()))
        conn.commit()

def get_data_quality_report(ticker: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT report FROM data_quality_reports WHERE ticker = ?", (ticker,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["report"])
    except Exception:
        return None

def get_data_quality_reports() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT report FROM data_quality_reports ORDER BY score ASC, ticker ASC").fetchall()
    out = []
    for r in rows:
        try:
            out.append(json.loads(r["report"]))
        except Exception:
            pass
    return out

def save_fundamentals(data: Dict[str, Any]):
    """Save fundamental metrics to cache."""
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        reasons_json = json.dumps(data.get("reasons", []))
        cursor.execute("""
            INSERT INTO fundamentals_cache (
                ticker, market, pe, pbv, roe, debt_to_equity, net_margin,
                market_cap, health_grade, health_score, is_speculative, reasons, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market=excluded.market,
                pe=excluded.pe,
                pbv=excluded.pbv,
                roe=excluded.roe,
                debt_to_equity=excluded.debt_to_equity,
                net_margin=excluded.net_margin,
                market_cap=excluded.market_cap,
                health_grade=excluded.health_grade,
                health_score=excluded.health_score,
                is_speculative=excluded.is_speculative,
                reasons=excluded.reasons,
                updated_at=excluded.updated_at
        """, (
            data["ticker"],
            data.get("market", "IDX"),
            float(data.get("pe", 0.0) or 0.0),
            float(data.get("pbv", 0.0) or 0.0),
            float(data.get("roe", 0.0) or 0.0),
            float(data.get("debt_to_equity", 0.0) or 0.0),
            float(data.get("net_margin", 0.0) or 0.0),
            float(data.get("market_cap", 0.0) or 0.0),
            data.get("health_grade", "MODERATE"),
            int(data.get("health_score", 50)),
            1 if data.get("is_speculative") else 0,
            reasons_json,
            now
        ))
        conn.commit()

def get_fundamentals(ticker: str) -> Optional[Dict[str, Any]]:
    """Get cached fundamentals for a ticker."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fundamentals_cache WHERE ticker = ?", (ticker,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        raw_reasons = d.get("reasons")
        if isinstance(raw_reasons, str) and raw_reasons.strip():
            try:
                d["reasons"] = json.loads(raw_reasons)
            except Exception:
                d["reasons"] = []
        else:
            d["reasons"] = []
        d["is_speculative"] = bool(d.get("is_speculative", 0))
        return d

def save_broker_summary(data: Dict[str, Any]):
    """Save broker summary to cache."""
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO broker_summary_cache (
                ticker, trade_date, source, top_buyers, top_sellers,
                net_foreign_val, bandar_status, bandar_status_label,
                bandar_avg_price, top3_ratio, summary_notes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, trade_date) DO UPDATE SET
                source=excluded.source,
                top_buyers=excluded.top_buyers,
                top_sellers=excluded.top_sellers,
                net_foreign_val=excluded.net_foreign_val,
                bandar_status=excluded.bandar_status,
                bandar_status_label=excluded.bandar_status_label,
                bandar_avg_price=excluded.bandar_avg_price,
                top3_ratio=excluded.top3_ratio,
                summary_notes=excluded.summary_notes,
                updated_at=excluded.updated_at
        """, (
            data["ticker"],
            data.get("trade_date", now[:10]),
            data.get("source", "PROXY"),
            json.dumps(data.get("top_buyers", [])),
            json.dumps(data.get("top_sellers", [])),
            float(data.get("net_foreign_val", 0.0) or 0.0),
            data.get("bandar_status", "NEUTRAL"),
            data.get("bandar_status_label", "Netral"),
            float(data.get("bandar_avg_price", 0.0) or 0.0),
            float(data.get("top3_ratio", 1.0) or 1.0),
            json.dumps(data.get("summary_notes", [])),
            now
        ))
        conn.commit()

def get_cached_broker_summary(ticker: str, trade_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve cached broker summary."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if trade_date:
            cursor.execute("SELECT * FROM broker_summary_cache WHERE ticker = ? AND trade_date = ?", (ticker, trade_date))
        else:
            cursor.execute("SELECT * FROM broker_summary_cache WHERE ticker = ? ORDER BY trade_date DESC LIMIT 1", (ticker,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        for field in ["top_buyers", "top_sellers", "summary_notes"]:
            raw = d.get(field)
            if isinstance(raw, str) and raw.strip():
                try:
                    d[field] = json.loads(raw)
                except Exception:
                    d[field] = []
            elif not isinstance(raw, list):
                d[field] = []
        return d

# Trend-engine / pillar fields stored together as JSON in screener_cache.direction_data
DIRECTION_KEYS = ("direction", "direction_label", "trend_regime", "trend_confidence", "adx", "direction_notes", "pillars",
                  "market_mode", "pullback_state", "pullback_label",
                  "reading", "news_headlines", "sentiment_label", "news_checked_at", "levels", "screen",
                  # Fase 1-4: action status, ranking, raw score, pillars, abnormal days, sector
                  "action", "rank", "raw_score", "pillar_values", "abnormal_recent", "sector", "sector_rank",
                  # shown as badges in the screener/Top 10 (were lost when rows came from the cache)
                  "vsa_signal", "vsa_label", "vsa_desc", "spread_ratio", "confluence_gates",
                  # +1 / -1 / 0 per entry of `reasons` (supporting / against / note)
                  "reason_signs")

def save_screener_result(res: Dict[str, Any]):
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        reasons_json = json.dumps(res.get("reasons", []))
        candlestick_json = json.dumps(res.get("candlestick", {}))
        direction_json = json.dumps({k: res.get(k) for k in DIRECTION_KEYS if k in res})
        cursor.execute("""
            INSERT INTO screener_cache (
                ticker, market, price, change_pct, ema20, ema50, ema200,
                rsi14, macd_hist, cmf20, vol_ratio, money_flow_status,
                sentiment_score, catalyst, score, verdict, badge_text,
                reasons, is_confirmed_breakout, confluence_score,
                target_tp, target_tp1, target_tp2, stop_loss,
                recommended_entry, risk_reward_ratio, candlestick, updated_at,
                entry_low, entry_high, atr14, health_grade, health_score,
                is_speculative, roe, net_margin, debt_to_equity, pe, pbv,
                direction_score, direction_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market=excluded.market,
                price=excluded.price,
                change_pct=excluded.change_pct,
                ema20=excluded.ema20,
                ema50=excluded.ema50,
                ema200=excluded.ema200,
                rsi14=excluded.rsi14,
                macd_hist=excluded.macd_hist,
                cmf20=excluded.cmf20,
                vol_ratio=excluded.vol_ratio,
                money_flow_status=excluded.money_flow_status,
                sentiment_score=excluded.sentiment_score,
                catalyst=excluded.catalyst,
                score=excluded.score,
                verdict=excluded.verdict,
                badge_text=excluded.badge_text,
                reasons=excluded.reasons,
                is_confirmed_breakout=excluded.is_confirmed_breakout,
                confluence_score=excluded.confluence_score,
                target_tp=excluded.target_tp,
                target_tp1=excluded.target_tp1,
                target_tp2=excluded.target_tp2,
                stop_loss=excluded.stop_loss,
                recommended_entry=excluded.recommended_entry,
                risk_reward_ratio=excluded.risk_reward_ratio,
                candlestick=excluded.candlestick,
                updated_at=excluded.updated_at,
                entry_low=excluded.entry_low,
                entry_high=excluded.entry_high,
                atr14=excluded.atr14,
                health_grade=excluded.health_grade,
                health_score=excluded.health_score,
                is_speculative=excluded.is_speculative,
                roe=excluded.roe,
                net_margin=excluded.net_margin,
                debt_to_equity=excluded.debt_to_equity,
                pe=excluded.pe,
                pbv=excluded.pbv,
                direction_score=excluded.direction_score,
                direction_data=excluded.direction_data
        """, (
            res["ticker"], res.get("market", "IDX"), res.get("price", 0), res.get("change_pct", 0),
            res.get("ema20", 0), res.get("ema50", 0), res.get("ema200", 0),
            res.get("rsi14", 50), res.get("macd_hist", 0), res.get("cmf20", 0),
            res.get("vol_ratio", 1.0), res.get("money_flow_status", "NEUTRAL"),
            res.get("sentiment_score", 0), res.get("catalyst", ""), res.get("score", 50),
            res.get("verdict", "NEUTRAL"), res.get("badge_text", ""), reasons_json,
            1 if res.get("is_confirmed_breakout") else 0,
            int(res.get("confluence_score", 0)),
            float(res.get("target_tp", 0.0)),
            float(res.get("target_tp1", res.get("target_tp", 0.0))),
            float(res.get("target_tp2", 0.0)),
            float(res.get("stop_loss", 0.0)),
            float(res.get("recommended_entry", 0.0)),
            float(res.get("risk_reward_ratio", 1.0)),
            candlestick_json,
            now,
            float(res.get("entry_low", 0.0)),
            float(res.get("entry_high", 0.0)),
            float(res.get("atr14", 0.0)),
            res.get("health_grade", "MODERATE"),
            int(res.get("health_score", 50)),
            1 if res.get("is_speculative") else 0,
            float(res.get("roe", 0.0)),
            float(res.get("net_margin", 0.0)),
            float(res.get("debt_to_equity", 0.0)),
            float(res.get("pe", 0.0)),
            float(res.get("pbv", 0.0)),
            int(res.get("direction_score", 0) or 0),
            direction_json
        ))
        conn.commit()

def get_screener_results(market: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if market:
            cursor.execute("SELECT * FROM screener_cache WHERE market = ? ORDER BY score DESC", (market,))
        else:
            cursor.execute("SELECT * FROM screener_cache ORDER BY score DESC")
        rows = cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            raw_reasons = d.get("reasons")
            if isinstance(raw_reasons, str) and raw_reasons.strip():
                try:
                    d["reasons"] = json.loads(raw_reasons)
                except Exception:
                    d["reasons"] = []
            elif isinstance(raw_reasons, list):
                d["reasons"] = raw_reasons
            else:
                d["reasons"] = []

            raw_candle = d.get("candlestick")
            if isinstance(raw_candle, str) and raw_candle.strip():
                try:
                    parsed = json.loads(raw_candle)
                    d["candlestick"] = parsed if isinstance(parsed, dict) and parsed.get("pattern") else None
                except Exception:
                    d["candlestick"] = None
            elif isinstance(raw_candle, dict):
                d["candlestick"] = raw_candle if raw_candle.get("pattern") else None
            else:
                d["candlestick"] = None

            d["is_confirmed_breakout"] = bool(d.get("is_confirmed_breakout", 0))
            d["confluence_score"] = int(d.get("confluence_score", 0))
            d["verdict"] = d.get("verdict") or "NEUTRAL"
            d["badge_text"] = d.get("badge_text") or ""
            d["target_tp"] = float(d.get("target_tp") or 0.0)
            d["target_tp1"] = float(d.get("target_tp1") or d["target_tp"])
            d["target_tp2"] = float(d.get("target_tp2") or 0.0)
            d["stop_loss"] = float(d.get("stop_loss") or 0.0)
            d["recommended_entry"] = float(d.get("recommended_entry") or 0.0)
            d["entry_low"] = float(d.get("entry_low") or 0.0)
            d["entry_high"] = float(d.get("entry_high") or 0.0)
            d["atr14"] = float(d.get("atr14") or 0.0)
            d["risk_reward_ratio"] = float(d.get("risk_reward_ratio") or 1.0)
            d["health_grade"] = d.get("health_grade") or "MODERATE"
            d["health_score"] = int(d.get("health_score") or 50)
            d["is_speculative"] = bool(d.get("is_speculative", 0))
            d["roe"] = float(d.get("roe") or 0.0)
            d["net_margin"] = float(d.get("net_margin") or 0.0)
            d["debt_to_equity"] = float(d.get("debt_to_equity") or 0.0)
            d["pe"] = float(d.get("pe") or 0.0)
            d["pbv"] = float(d.get("pbv") or 0.0)
            try:
                d.update(json.loads(d.pop("direction_data", None) or "{}"))
            except Exception:
                pass
            d["direction_score"] = int(d.get("direction_score") or 0)
            d["financials"] = {
                "grade": d["health_grade"],
                "score": d["health_score"],
                "is_speculative": d["is_speculative"],
                "roe": d["roe"],
                "net_margin": d["net_margin"],
                "debt_to_equity": d["debt_to_equity"],
                "pe": d["pe"],
                "pbv": d["pbv"],
            }
            results.append(d)
        return results

def add_watchlist(ticker: str, name: str = "", market: str = "IDX", notes: str = ""):
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO watchlist (ticker, name, market, added_at, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (ticker, name, market, now, notes))
        conn.commit()

def remove_watchlist(ticker: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))
        conn.commit()

def delete_screener_rows_except(market: str, keep: List[str]) -> int:
    """Remove a market's cached screener rows for tickers not in `keep` (the latest scan)."""
    if not keep:
        return 0
    with get_connection() as conn:
        marks = ",".join("?" for _ in keep)
        cur = conn.execute(f"DELETE FROM screener_cache WHERE market = ? AND ticker NOT IN ({marks})", [market, *keep])
        conn.commit()
        return cur.rowcount


def get_watchlist() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM watchlist ORDER BY added_at DESC")
        return [dict(r) for r in cursor.fetchall()]

def save_prediction_snapshot(items: List[Dict[str, Any]], market: str = "IDX", snapshot_date: Optional[str] = None):
    """Replace the day's snapshot (max 10 rows) for historical performance tracking.

    The snapshot of a date is the latest scan's view of that date: rows from earlier scans
    that are no longer selected are removed (they used to accumulate beyond 10 per day).
    An empty `items` clears the date, so a day without any buy signal records no predictions.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now()
        target_date = snapshot_date or now.strftime("%Y-%m-%d")
        created_at = now.isoformat()
        cursor.execute("DELETE FROM prediction_snapshots WHERE snapshot_date = ? AND market = ?", (target_date, market))
        if not items:
            conn.commit()
            return

        # Take up to top 10 items
        for rank, item in enumerate(items[:10], start=1):
            reasons_json = json.dumps(item.get("reasons", []))
            cursor.execute("""
                INSERT INTO prediction_snapshots (
                    snapshot_date, market, ticker, rank, score, verdict, badge_text,
                    price_at_prediction, recommended_entry, target_tp1, target_tp2,
                    stop_loss, risk_reward_ratio, confluence_score, money_flow_status,
                    reasons, created_at, entry_low, entry_high, atr14, health_grade,
                    health_score, is_speculative, roe, net_margin, debt_to_equity, pe, pbv
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_date, market, ticker) DO UPDATE SET
                    rank=excluded.rank,
                    score=excluded.score,
                    verdict=excluded.verdict,
                    badge_text=excluded.badge_text,
                    price_at_prediction=excluded.price_at_prediction,
                    recommended_entry=excluded.recommended_entry,
                    target_tp1=excluded.target_tp1,
                    target_tp2=excluded.target_tp2,
                    stop_loss=excluded.stop_loss,
                    risk_reward_ratio=excluded.risk_reward_ratio,
                    confluence_score=excluded.confluence_score,
                    money_flow_status=excluded.money_flow_status,
                    reasons=excluded.reasons,
                    created_at=excluded.created_at,
                    entry_low=excluded.entry_low,
                    entry_high=excluded.entry_high,
                    atr14=excluded.atr14,
                    health_grade=excluded.health_grade,
                    health_score=excluded.health_score,
                    is_speculative=excluded.is_speculative,
                    roe=excluded.roe,
                    net_margin=excluded.net_margin,
                    debt_to_equity=excluded.debt_to_equity,
                    pe=excluded.pe,
                    pbv=excluded.pbv
            """, (
                target_date,
                market,
                item["ticker"],
                rank,
                int(item.get("score", 50)),
                item.get("verdict", "NEUTRAL"),
                item.get("badge_text", ""),
                float(item.get("price", 0.0)),
                float(item.get("recommended_entry", 0.0)),
                float(item.get("target_tp1", item.get("target_tp", 0.0))),
                float(item.get("target_tp2", 0.0)),
                float(item.get("stop_loss", 0.0)),
                float(item.get("risk_reward_ratio", 1.0)),
                int(item.get("confluence_score", 0)),
                item.get("money_flow_status", "NEUTRAL"),
                reasons_json,
                created_at,
                float(item.get("entry_low", 0.0)),
                float(item.get("entry_high", 0.0)),
                float(item.get("atr14", 0.0)),
                item.get("health_grade", "MODERATE"),
                int(item.get("health_score", 50)),
                1 if item.get("is_speculative") else 0,
                float(item.get("roe", 0.0)),
                float(item.get("net_margin", 0.0)),
                float(item.get("debt_to_equity", 0.0)),
                float(item.get("pe", 0.0)),
                float(item.get("pbv", 0.0))
            ))
        conn.commit()

def get_prediction_dates(market: str = "IDX") -> List[str]:
    """Get list of distinct dates where snapshots exist, newest first."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT snapshot_date
            FROM prediction_snapshots
            WHERE market = ?
            ORDER BY snapshot_date DESC
        """, (market,))
        return [row["snapshot_date"] for row in cursor.fetchall()]

def get_prediction_snapshot(snapshot_date: str, market: str = "IDX") -> List[Dict[str, Any]]:
    """Get snapshot items for specific date and market, ordered by rank."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM prediction_snapshots
            WHERE snapshot_date = ? AND market = ?
            ORDER BY rank ASC
        """, (snapshot_date, market))
        rows = cursor.fetchall()
        items = []
        for r in rows:
            d = dict(r)
            raw_reasons = d.get("reasons")
            if isinstance(raw_reasons, str) and raw_reasons.strip():
                try:
                    d["reasons"] = json.loads(raw_reasons)
                except Exception:
                    d["reasons"] = []
            elif isinstance(raw_reasons, list):
                d["reasons"] = raw_reasons
            else:
                d["reasons"] = []
            d["entry_low"] = float(d.get("entry_low") or 0.0)
            d["entry_high"] = float(d.get("entry_high") or 0.0)
            d["atr14"] = float(d.get("atr14") or 0.0)
            d["health_grade"] = d.get("health_grade") or "MODERATE"
            d["health_score"] = int(d.get("health_score") or 50)
            d["is_speculative"] = bool(d.get("is_speculative", 0))
            d["roe"] = float(d.get("roe") or 0.0)
            d["net_margin"] = float(d.get("net_margin") or 0.0)
            d["debt_to_equity"] = float(d.get("debt_to_equity") or 0.0)
            d["pe"] = float(d.get("pe") or 0.0)
            d["pbv"] = float(d.get("pbv") or 0.0)
            d["financials"] = {
                "grade": d["health_grade"],
                "score": d["health_score"],
                "is_speculative": d["is_speculative"],
                "roe": d["roe"],
                "net_margin": d["net_margin"],
                "debt_to_equity": d["debt_to_equity"],
                "pe": d["pe"],
                "pbv": d["pbv"],
            }
            items.append(d)
        return items

# Auto-initialize database schema upon import
init_db()
