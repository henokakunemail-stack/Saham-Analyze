"""Live track record of the current rules, judged against the backtest with rules fixed in advance.

Pools every prediction (status LAYAK at a closing plan) recorded under the current RULES_VERSION,
evaluates it with the same simulator as the backtest (buy limit 5 days, half at TP1, breakeven
stop, 10-day horizon) and compares the average R with what the backtest led us to expect.

Per-trade results vary a lot (backtest sd ≈ 1.5 R), so nothing is concluded before MIN_TRADES
closed trades, and the conclusion uses the 90 % interval of the mean — the verdict rules below
were written before any live data existed (docs/RENCANA_PERBAIKAN_OKT2026.md §4).
"""
import math
from typing import Any, Callable, Dict, List, Optional

# Backtest yardstick for LAYAK under RULES_VERSION 2026-10-24 (walk-forward, both periods):
# 164 filled trades, mean +0.361 R, sd 1.534 R, 51 % positive.
EXPECTED_R = 0.36
EXPECTED_SD = 1.53
MIN_TRADES = 30
Z90 = 1.645

VERDICTS = {
    "BELUM_CUKUP": "Belum cukup data",
    "MERUGI": "Merugi di pasar nyata",
    "DI_BAWAH_HARAPAN": "Di bawah harapan uji historis",
    "TERBUKTI_POSITIF": "Terbukti positif",
    "SESUAI_BELUM_PASTI": "Sesuai harapan, belum pasti",
}


def _fmt_r(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.2f}".replace(".", ",") + " R"


def judge(rs: List[float]) -> Dict[str, Any]:
    """Verdict for a list of closed-trade R multiples (rules fixed in advance)."""
    n = len(rs)
    mean = sum(rs) / n if n else None
    sd = (math.sqrt(sum((r - mean) ** 2 for r in rs) / (n - 1)) if n >= MIN_TRADES else EXPECTED_SD) if n >= 2 else EXPECTED_SD
    half = Z90 * sd / math.sqrt(n) if n else None
    lo, hi = (mean - half, mean + half) if n else (None, None)
    if n < MIN_TRADES:
        code = "BELUM_CUKUP"
        text = (f"Baru {n} dari minimal {MIN_TRADES} transaksi selesai — belum bisa disimpulkan."
                + (f" Rata-rata sementara {_fmt_r(mean)} (rentang 90 %: {_fmt_r(lo)} s/d {_fmt_r(hi)})." if n else ""))
    elif hi < 0:
        code = "MERUGI"
        text = (f"{n} transaksi, rata-rata {_fmt_r(mean)}; bahkan batas atas rentang 90 % ({_fmt_r(hi)}) di bawah nol — "
                f"aturan ini merugi di kondisi pasar sekarang. Jangan dipakai dengan uang sungguhan sampai ditinjau ulang.")
    elif hi < EXPECTED_R:
        code = "DI_BAWAH_HARAPAN"
        text = (f"{n} transaksi, rata-rata {_fmt_r(mean)} (rentang 90 %: {_fmt_r(lo)} s/d {_fmt_r(hi)}) — lebih rendah dari "
                f"harapan uji historis {_fmt_r(EXPECTED_R)}. Kondisi pasar sekarang mungkin berbeda dari masa uji.")
    elif lo > 0:
        code = "TERBUKTI_POSITIF"
        text = (f"{n} transaksi, rata-rata {_fmt_r(mean)}; batas bawah rentang 90 % ({_fmt_r(lo)}) di atas nol — "
                f"sejauh ini terbukti positif sebelum biaya (biaya ±0,1 R per transaksi).")
    else:
        code = "SESUAI_BELUM_PASTI"
        text = (f"{n} transaksi, rata-rata {_fmt_r(mean)} (rentang 90 %: {_fmt_r(lo)} s/d {_fmt_r(hi)}) — sesuai harapan uji "
                f"historis, tetapi belum pasti positif.")
    return {"code": code, "label": VERDICTS[code], "text": text, "n": n,
            "mean_r": round(mean, 3) if mean is not None else None,
            "ci90": [round(lo, 3), round(hi, 3)] if n else None,
            "expected_r": EXPECTED_R, "min_trades": MIN_TRADES}


def build(dates: List[str], snapshot: Callable[[str], List[Dict[str, Any]]],
          evaluate: Callable[[List[Dict[str, Any]]], Dict[str, Any]], rules_version: str) -> Dict[str, Any]:
    """Pool the predictions of `rules_version` over `dates` (newest first) and judge them."""
    items: List[Dict[str, Any]] = []
    older = 0
    for d in dates:
        snap = snapshot(d)
        mine = [x for x in snap if (x.get("rules_version") or "") == rules_version]
        older += len(snap) - len(mine)
        if mine:
            for ev in evaluate(mine)["items"]:
                ev["snapshot_date"] = d
                items.append(ev)
    closed = [x for x in items if x.get("status") in ("HIT_TP1", "HIT_TP2", "STOPPED_OUT", "EXPIRED")
              and x.get("r_multiple") is not None]
    rs = [float(x["r_multiple"]) for x in closed]
    wins = [r for r in rs if r > 0]
    losses = [-r for r in rs if r < 0]
    count = lambda st: sum(1 for x in items if x.get("status") == st)  # noqa: E731
    return {
        "rules_version": rules_version,
        "since": min((x["snapshot_date"] for x in items), default=None),
        "predictions": len(items),
        "filled": sum(1 for x in items if x.get("status") in ("HIT_TP1", "HIT_TP2", "STOPPED_OUT", "EXPIRED", "IN_PROGRESS")),
        "closed": len(closed),
        "in_progress": count("IN_PROGRESS"),
        "waiting": count("WAITING_ENTRY"),
        "not_filled": count("NOT_FILLED") + count("CANCELLED"),
        "win_pct": round(100 * len(wins) / len(rs), 1) if rs else None,
        "profit_factor": round(sum(wins) / sum(losses), 2) if losses else None,
        "older_rules_predictions": older,
        "verdict": judge(rs),
        "trades": sorted(({"ticker": x["ticker"], "date": x["snapshot_date"], "status": x["status"],
                           "r": x.get("r_multiple")} for x in closed), key=lambda t: t["date"], reverse=True)[:50],
    }
