"""Phase 1 calibration of the actionability gates and the pillar weights (offline).

1. compute_rows(): the walk-forward backtest rows for the default IDX universe, computed once
   from the cached candles and saved (pickle) — about 15 CPU-minutes, split over processes.
2. The evaluation functions below re-apply actionability.assess with variant thresholds and
   re-weight the stored pillar values, without recomputing any indicator.
3. Choose on the in-sample period only (dates before SPLIT_DATE), then check the chosen
   configuration once on the out-of-sample period. Results: docs/hasil-kalibrasi-fase1.md.

Run:  python -m engine.screener.calibration compute <rows.pkl>
      python -m engine.screener.calibration report <rows.pkl>
"""
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .actionability import assess, default_config, BULLISH
from .plan_sim import summarize_sims
from .scoring import PILLAR_WEIGHTS

SPLIT_DATE = "2025-12-11"            # same split as docs/hasil-backtest-baseline.md
HORIZON, STEP = 10, 3
# Pillars that have history in the backtest (fundamental & sentiment have none)
BACKTEST_PILLARS = ("pullback", "trend", "money_flow", "momentum", "setup")
STATUSES = ("LAYAK", "TUNGGU", "HINDARI")
# Acceptance on out-of-sample (docs/RENCANA_5_POIN.md §3, revisi 23 Okt 2026)
MIN_LAYAK_AVG_R = 0.10
MIN_LAYAK_FILLED = 100


# ── 1. Rows ────────────────────────────────────────────────────────────────

def _load_idx_data(min_bars: int = 150) -> Tuple[Dict[str, pd.DataFrame], Optional[pd.DataFrame]]:
    from ..config import DEFAULT_IDX_TICKERS
    from ..db import get_candles
    from ..collectors.market_data import normalize_ticker, fetch_stock_ohlcv
    data = {}
    for t in DEFAULT_IDX_TICKERS:
        norm = normalize_ticker(t, "IDX")
        candles = get_candles(norm, limit=1000)
        if candles and len(candles) >= min_bars:
            data[norm] = pd.DataFrame(candles)
    bench = get_candles("^JKSE", limit=1000)
    bench_df = pd.DataFrame(bench) if bench and len(bench) >= 400 else fetch_stock_ohlcv("^JKSE", period="3y")
    return data, (bench_df if bench_df is not None and not bench_df.empty else None)


def _walk_chunk(args) -> pd.DataFrame:
    from .backtest import walk_forward
    data, bench = args
    return walk_forward(data, bench, horizon=HORIZON, step=STEP, market="IDX")


def compute_rows(path: str, workers: int = 6) -> pd.DataFrame:
    """Walk-forward rows for the default IDX universe (cached candles only), saved to `path`."""
    data, bench = _load_idx_data()
    names = sorted(data)
    chunks = [{n: data[n] for n in names[i::workers]} for i in range(workers)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        parts = list(ex.map(_walk_chunk, [(c, bench) for c in chunks]))
    rows = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    rows = rows.sort_values(["date", "ticker"]).reset_index(drop=True)
    rows.to_pickle(path)
    print(f"[calibration] {len(rows)} rows, {len(data)} tickers, {rows['date'].min()} .. {rows['date'].max()} -> {path}")
    return rows


# ── 2. Offline evaluation ──────────────────────────────────────────────────

def split(rows: pd.DataFrame, split_date: str = SPLIT_DATE) -> Tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.to_datetime(rows["date"])
    cut = pd.Timestamp(split_date)
    return rows[d < cut], rows[d >= cut]


def _sims(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    out = []
    for st, filled, r, ret, held in frame[["plan_status", "filled", "r", "plan_return_pct", "bars_held"]].itertuples(index=False):
        if st is None or (isinstance(st, float) and np.isnan(st)):
            continue
        out.append({"status": st, "filled": bool(filled), "r": None if pd.isna(r) else float(r),
                    "return_pct": None if pd.isna(ret) else float(ret),
                    "bars_held": None if pd.isna(held) else float(held)})
    return out


def stats(frame: pd.DataFrame) -> Dict[str, Any]:
    """plans, fill rate, TP-first rate, avg R, profit factor (plan_sim rules)."""
    s = summarize_sims(_sims(frame))
    return {"plans": s.get("plans", 0), "filled": s.get("filled", 0), "closed": s.get("closed", 0),
            "fill_rate_pct": s.get("fill_rate_pct"), "tp_first_pct": s.get("win_rate_pct"),
            "avg_r": s.get("avg_r"), "profit_factor": s.get("profit_factor")}


def row_dict(r: pd.Series) -> Dict[str, Any]:
    """Rebuild the minimal scan row backtest.default_score_fn gives to assess."""
    flags = [f for f in str(r.get("flags") or "").split(",") if f]
    return {
        "market": "IDX", "verdict": r.get("verdict"), "is_speculative": False,
        "market_mode": r.get("market_mode") or "NORMAL", "score": r.get("score"),
        "raw_score": r.get("raw_score"), "pillar_values": r.get("pillar_values") or {},
        "pullback_state": r.get("pullback_state"),
        "levels": {"risk_pct": r.get("risk_pct"), "risk_reward_ratio": r.get("rr"), "flags": flags},
        "screen": {"avg_value_20d": r.get("avg_value_20d"), "atr_pct": r.get("atr_pct"), "rs_60d": r.get("rs_60d")},
    }


def apply_config(rows: pd.DataFrame, config: Optional[Dict[str, Any]] = None,
                 dicts: Optional[List[Dict[str, Any]]] = None) -> pd.Series:
    """Status per row under a variant configuration (`dicts`: row_dict of every row, precomputed)."""
    if dicts is None:
        dicts = [row_dict(r) for _, r in rows.iterrows()]
    return pd.Series([assess(d, config)["status"] for d in dicts], index=rows.index, dtype=object)


def by_status(rows: pd.DataFrame, status: pd.Series) -> Dict[str, Dict[str, Any]]:
    return {s: stats(rows[status == s]) for s in STATUSES}


def per_day(rows: pd.DataFrame, count: int) -> Optional[float]:
    """Rough live frequency: rows are sampled every STEP trading days per ticker."""
    if rows.empty:
        return None
    d = pd.to_datetime(rows["date"])
    days = int(np.busday_count(d.min().date(), d.max().date())) + 1
    return round(count * STEP / days, 2) if days > 0 else None


def ordered(res: Dict[str, Dict[str, Any]]) -> bool:
    r = [res[s]["avg_r"] for s in STATUSES]
    return all(v is not None for v in r) and r[0] > r[1] > r[2]


def accepted(res: Dict[str, Dict[str, Any]]) -> bool:
    lay = res["LAYAK"]
    return ordered(res) and (lay["avg_r"] or -9) >= MIN_LAYAK_AVG_R and lay["filled"] >= MIN_LAYAK_FILLED


def _variants() -> Dict[str, Dict[str, Any]]:
    """Gate variants: market policy x signal basis x risk cap x liquidity x volatility gate."""
    markets = {
        "pasar-default": {"blocked_modes": ("CRASH",), "leaders_only_modes": ("BEARISH",)},
        "pasar-ketat": {"blocked_modes": ("CRASH", "BEARISH"), "leaders_only_modes": ()},
        "pasar-longgar": {"blocked_modes": (), "leaders_only_modes": ("CRASH", "BEARISH")},
    }
    out = {}
    for mk, mcfg in markets.items():
        for basis in ("verdict", "raw"):
            for risk in (6.0, 8.0, 10.0):
                for liq in (2e9, 5e9):
                    for vol in (True, False):
                        name = f"{mk}|sinyal-{basis}|risiko-{risk:g}|likuid-{liq / 1e9:g}M|{'vol' if vol else 'tanpa-vol'}"
                        out[name] = {**mcfg, "signal_basis": basis, "max_risk_pct": risk,
                                     "min_value_idx": liq, "require_not_volatile": vol}
    return out


def evaluate_gates(rows: pd.DataFrame, variants: Optional[Dict[str, Dict[str, Any]]] = None) -> pd.DataFrame:
    """One line per variant: LAYAK/TUNGGU/HINDARI stats on `rows`."""
    variants = variants if variants is not None else _variants()
    dicts = [row_dict(r) for _, r in rows.iterrows()]
    lines = []
    for name, cfg in variants.items():
        res = by_status(rows, apply_config(rows, cfg, dicts))
        line = {"variant": name}
        for s in STATUSES:
            for k, v in res[s].items():
                line[f"{s}_{k}"] = v
        line["LAYAK_per_day"] = per_day(rows, int(res["LAYAK"]["plans"]))
        line["ordered"] = ordered(res)
        line["accepted"] = accepted(res)
        lines.append(line)
    return pd.DataFrame(lines)


def reweight(rows: pd.DataFrame, weights: Dict[str, float]) -> pd.Series:
    """Score recomputed from the stored pillar values with other weights (backtest pillars only,
    same 50 + 60 × weighted mean as scoring; no confluence bonus, no market brake)."""
    def one(pv) -> float:
        pv = pv if isinstance(pv, dict) else {}
        keys = [k for k in BACKTEST_PILLARS if k in pv and weights.get(k, 0) > 0]
        tw = sum(weights[k] for k in keys)
        if not tw:
            return 50.0
        return 50.0 + 60.0 * sum(weights[k] * float(pv[k]) for k in keys) / tw
    return rows["pillar_values"].map(one)


WEIGHT_VARIANTS: Dict[str, Dict[str, float]] = {
    "sekarang": {k: PILLAR_WEIGHTS[k] for k in BACKTEST_PILLARS},
    "pullback-dominan": {"pullback": 0.50, "trend": 0.20, "money_flow": 0.10, "momentum": 0.10, "setup": 0.10},
    "tren-lebih-berat": {"pullback": 0.30, "trend": 0.35, "money_flow": 0.10, "momentum": 0.15, "setup": 0.10},
    "aliran-dana-lebih-berat": {"pullback": 0.30, "trend": 0.20, "money_flow": 0.25, "momentum": 0.15, "setup": 0.10},
    "momentum-setup-lebih-berat": {"pullback": 0.30, "trend": 0.15, "money_flow": 0.10, "momentum": 0.25, "setup": 0.20},
    "rata": {k: 0.2 for k in BACKTEST_PILLARS},
}


def top_n(rows: pd.DataFrame, score: pd.Series, n: int = 10) -> pd.DataFrame:
    """The n best-scoring plans of every date (ties broken by ticker for determinism)."""
    tmp = rows.assign(_s=score.values).sort_values(["date", "_s", "ticker"], ascending=[True, False, True])
    return tmp.groupby("date", sort=False).head(n)


def bucket_r(rows: pd.DataFrame, score: pd.Series, q: int = 5) -> List[Optional[float]]:
    """Average R per score quintile (lowest first): monotonic = the ranking means something."""
    tmp = rows.assign(_s=score.values)
    tmp = tmp[tmp["filled"] & tmp["r"].notna()]
    if len(tmp) < q * 5:
        return []
    tmp["_q"] = pd.qcut(tmp["_s"].rank(method="first"), q, labels=False)
    return [round(float(g["r"].mean()), 3) for _, g in tmp.groupby("_q")]


def monotonic_share(values: List[Optional[float]]) -> float:
    """Share of adjacent bucket pairs that rise (1.0 = perfectly monotonic)."""
    pairs = [(a, b) for a, b in zip(values, values[1:]) if a is not None and b is not None]
    return round(sum(b > a for a, b in pairs) / len(pairs), 2) if pairs else 0.0


def evaluate_weights(rows: pd.DataFrame, variants: Optional[Dict[str, Dict[str, float]]] = None,
                     n: int = 10) -> pd.DataFrame:
    variants = variants if variants is not None else WEIGHT_VARIANTS
    lines = []
    for name, w in variants.items():
        score = reweight(rows, w)
        top = stats(top_n(rows, score, n))
        buckets = bucket_r(rows, score)
        lines.append({"variant": name, **{f"top_{k}": v for k, v in top.items()},
                      "quintile_r": buckets, "monotonic": monotonic_share(buckets)})
    return pd.DataFrame(lines)


def best_gate_variant(table: pd.DataFrame) -> Optional[str]:
    """In-sample choice: among ordered variants with enough LAYAK trades, the highest LAYAK avg R
    (a frequency floor keeps a near-empty LAYAK set from winning on noise). Exact ties keep the
    variant listed first: the default market policy before the lenient one, with the volatility
    gate before without it."""
    ok = table[table["ordered"] & (table["LAYAK_filled"] >= MIN_LAYAK_FILLED)]
    if ok.empty:
        return None
    return str(ok.sort_values("LAYAK_avg_r", ascending=False, kind="mergesort").iloc[0]["variant"])


def best_weight_variant(table: pd.DataFrame) -> str:
    """In-sample choice: highest top-10 avg R, with quintile monotonicity as a tie-breaker."""
    return str(table.sort_values(["top_avg_r", "monotonic"], ascending=False, kind="mergesort").iloc[0]["variant"])


def single_changes(base: Dict[str, Any], variants: Dict[str, Dict[str, Any]]) -> List[str]:
    """Variant names that differ from `base` in at most one setting (for the readable table)."""
    # The two market keys form one setting (the market policy)
    settings = (("blocked_modes", "leaders_only_modes"), ("signal_basis",), ("max_risk_pct",),
                ("min_value_idx",), ("require_not_volatile",))
    out = []
    for name, cfg in variants.items():
        diff = sum(1 for keys in settings
                   if any(tuple(np.atleast_1d(cfg.get(k))) != tuple(np.atleast_1d(base.get(k))) for k in keys))
        if diff <= 1:
            out.append(name)
    return out


def run_report(path: str, out_json: Optional[str] = None) -> Dict[str, Any]:
    """Phase-1 calibration: choose in-sample, check the choice once out-of-sample."""
    rows = pd.read_pickle(path)
    ins, oos = split(rows)
    variants = _variants()
    base = default_config()
    default_name = next(n for n, c in variants.items()
                        if all(tuple(np.atleast_1d(c[k])) == tuple(np.atleast_1d(base[k])) for k in c))

    # Gates: every variant scored in-sample; the choice uses in-sample only
    gates_in = evaluate_gates(ins, variants)
    chosen = best_gate_variant(gates_in)
    # Out-of-sample: the chosen and the default (reference), plus the one-change variants as information
    shown = set(single_changes(variants[default_name], variants)) | {default_name}
    if chosen:
        # The in-sample period has no CRASH day, so the CRASH policy can only be shown out-of-sample
        lenient = chosen.replace("pasar-default", "pasar-longgar").replace("sinyal-verdict", "sinyal-raw")
        shown |= {chosen} | ({lenient} if lenient in variants else set())
    shown = sorted(shown)
    gates_oos = evaluate_gates(oos, {n: variants[n] for n in shown})
    chosen_oos = gates_oos[gates_oos["variant"] == chosen].iloc[0].to_dict() if chosen else None
    default_oos = gates_oos[gates_oos["variant"] == default_name].iloc[0].to_dict()

    # Pillar weights: top-10 per date, chosen in-sample, checked once out-of-sample
    weights_in = evaluate_weights(ins)
    w_chosen = best_weight_variant(weights_in)
    weights_oos = evaluate_weights(oos, {k: WEIGHT_VARIANTS[k] for k in dict.fromkeys(("sekarang", w_chosen))})

    result = {
        "rows": len(rows), "tickers": int(rows["ticker"].nunique()),
        "period": [str(rows["date"].min())[:10], str(rows["date"].max())[:10]], "split": SPLIT_DATE,
        "overall": {"all": stats(rows), "in_sample": stats(ins), "out_of_sample": stats(oos)},
        "default_variant": default_name, "chosen_variant": chosen,
        "gates_in": gates_in.to_dict("records"), "gates_oos": gates_oos.to_dict("records"),
        "chosen_oos": chosen_oos, "default_oos": default_oos,
        "chosen_accepted": bool(chosen_oos and chosen_oos["accepted"]),
        "modes": {p: rows_p["market_mode"].value_counts().to_dict() for p, rows_p in (("in", ins), ("oos", oos))},
        "weights": {k: WEIGHT_VARIANTS[k] for k in WEIGHT_VARIANTS},
        "weights_in": weights_in.to_dict("records"), "weights_oos": weights_oos.to_dict("records"),
        "weight_chosen": w_chosen,
    }
    if out_json:
        import json
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1, default=str)
    return result


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "compute":
        compute_rows(path)
    elif cmd == "report":
        res = run_report(path, sys.argv[3] if len(sys.argv) > 3 else None)
        print("default:", res["default_variant"], "| chosen:", res["chosen_variant"],
              "| accepted:", res["chosen_accepted"], "| weights:", res["weight_chosen"])
