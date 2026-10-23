"""One analysis pipeline per stock, shared by the scan rows, the detail page and AI validation.

Before this module the three call sites each wired indicators → score → plan → status by hand
and had drifted apart (missing fields, the split check in only one of them).

Final bars only for scoring: while a session is trading, today's half-formed candle would move
indicators, money flow and the confluence gates in ways the calibration never saw (e.g. a quiet
first hour reads as a "no supply" test). Scores, verdicts and the plan therefore come from the
last final close; the live bar is used only for the price shown and the plan's live position.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from ..collectors import abnormal_days
from ..collectors.data_quality import bar_is_final
from ..indicators.money_flow import compute_money_flow
from ..indicators.screen_metrics import compute_screen_metrics
from ..indicators.technical import compute_technical_indicators
from ..indicators.trend import compute_trend_direction
from .actionability import assess
from .scoring import compute_composite_score


def scoring_frame(df: pd.DataFrame, market: str) -> Tuple[pd.DataFrame, bool]:
    """(frame ending at the last final bar, whether today's bar is still trading)."""
    if "date" in df.columns and len(df) > 60 and bar_is_final(df["date"].iloc[-1], market) is False:
        return df.iloc[:-1], True
    return df, False


def _bench_until(bench_df: Optional[pd.DataFrame], last_date: Any) -> Optional[pd.DataFrame]:
    if bench_df is None or bench_df.empty or "date" not in bench_df.columns:
        return bench_df
    cut = pd.to_datetime(bench_df["date"]).dt.strftime("%Y-%m-%d") <= str(last_date)[:10]
    return bench_df[cut]


def align_reading(reading: Optional[Dict[str, Any]], action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The card's plain-language reading must not contradict the action status."""
    if not reading:
        return reading
    out = dict(reading)
    status, reasons = action.get("status"), action.get("reasons") or []
    if status == "HINDARI" and out.get("stance") != "HINDARI":
        out.update(stance="HINDARI", headline=reasons[0] if reasons else out.get("headline"))
    elif status == "TUNGGU" and out.get("stance") == "LAYAK_DIPERTIMBANGKAN":
        out.update(stance="TUNGGU_PEMICU",
                   headline=f"Syarat eksekusi belum terpenuhi — {reasons[0]}" if reasons else out.get("headline"))
    elif status == "LAYAK":
        out.update(stance="LAYAK_DIPERTIMBANGKAN")
    return out


def live_reading(reading: Optional[Dict[str, Any]], levels: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """During the session the reading is about a plan from the last close; when today's price has
    already settled that plan (target reached, cut loss broken, ran far above the zone) the card
    must say so instead of repeating yesterday's "pemicu sudah muncul"."""
    if not reading or not isinstance(levels, dict) or not levels.get("frozen"):
        return reading
    live = levels.get("live")
    if not isinstance(live, dict):
        return reading
    status = live.get("status")
    out = dict(reading)
    out["base_stance"] = reading.get("stance")
    if status == "BELOW_STOP" or live.get("touched_stop"):
        out.update(stance="BATAL", headline="Cut loss sudah tertembus hari ini — rencana ini batal. "
                   "Rencana baru dibuat dari penutupan hari ini; jangan masuk hanya karena harga 'sudah murah'.")
    elif status in ("AT_TP1", "AT_TP2"):
        n = "TP1" if status == "AT_TP1" else "TP2"
        out.update(stance="LEWAT", headline=f"Hari ini harga sudah menyentuh {n} — untuk yang belum punya posisi, "
                   "rencana ini sudah lewat (mengejar = membeli di target orang lain). Yang punya posisi: ikuti aturan di "
                   f"{n}. Tunggu rencana baru dari penutupan hari ini.")
    elif live.get("far_above"):
        out.update(stance="JANGAN_KEJAR", headline=f"Harga sudah {float(live.get('dist_atr') or 0):.1f}×ATR di atas zona beli "
                   "— jangan dikejar. Order limit di zona kemungkinan kecil terisi hari ini; pemicu di bawah adalah bacaan "
                   "dari penutupan terakhir.")
    else:
        return reading
    return out


def analyze_frame(df: pd.DataFrame, ticker: str, market: str, sentiment: Dict[str, Any],
                  bench_df: Optional[pd.DataFrame], market_regime: Optional[Dict[str, Any]],
                  financials_fn: Callable[..., Dict[str, Any]],
                  splits: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Everything the app shows about one stock, from its daily frame."""
    live_tech = compute_technical_indicators(df, market)       # plan frozen on the final close + live position
    base, live = scoring_frame(df, market)
    scored = compute_technical_indicators(base, market, freeze_live_bar=False) if live else live_tech
    # Shown to the user: the live price with the scored (final-bar) indicators and the live plan
    tech = ({**scored, "price": live_tech.get("price"), "change_pct": live_tech.get("change_pct"),
             "levels": live_tech.get("levels"), "final_close": scored.get("price")}
            if live and scored else live_tech)
    flow = compute_money_flow(base)
    bench = _bench_until(bench_df, base["date"].iloc[-1]) if "date" in base.columns else bench_df
    direction = compute_trend_direction(base, bench)
    financials = financials_fn(ticker, market, scored.get("vol_ratio", 1.0), scored.get("change_pct", 0.0))
    composite = compute_composite_score(scored, flow, sentiment, financials, direction, market_regime)
    if live:
        composite["levels"] = live_tech.get("levels")          # same plan, plus the live position
    screen = compute_screen_metrics(base, scored, direction, financials, market)
    abnormal = abnormal_days.recent(df, market, days=20, splits=splits)   # today's lock counts too
    action = assess({
        "ticker": ticker, "market": market, "verdict": composite.get("verdict"),
        "is_speculative": composite.get("is_speculative"), "market_mode": composite.get("market_mode"),
        "score": composite.get("score"), "raw_score": composite.get("raw_score"),
        "pillar_values": composite.get("pillar_values"), "pullback_state": composite.get("pullback_state"),
        "levels": composite.get("levels"), "screen": screen, "abnormal_recent": abnormal,
        "catalyst": sentiment.get("catalyst", ""),
    })
    composite["action"] = action
    composite["reading"] = live_reading(align_reading(composite.get("reading"), action), composite.get("levels"))
    return {"tech": tech, "flow": flow, "direction": direction, "composite": composite, "financials": financials,
            "screen": screen, "abnormal_recent": abnormal, "action": action, "live": live, "scoring_df": base}
