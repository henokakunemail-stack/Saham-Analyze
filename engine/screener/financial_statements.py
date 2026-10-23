"""Financial statements (annual + quarterly) from Yahoo, turned into plain-language quality checks.

Yahoo gives 4–5 years of annual statements and ~5 recent quarters for IDX stocks. Row names vary
between companies (e.g. operating cash flow is "Operating Cash Flow" for some and the direct-method
"Cash Flowsfromusedin Operating Activities Direct" for most IDX filers), so every metric reads a
list of candidate rows. Banks and other financials are judged without debt/current-ratio checks:
deposits make their "debt" large by design.

What is computed (each may be None when Yahoo has no data):
- growth: revenue and net income, last full year vs the year before; 3-year revenue CAGR
- trend: how many of the last 3 annual net incomes fell year on year; consecutive losses
- quality: operating cash flow ÷ net income (last year), free cash flow
- balance sheet: debt ÷ equity, current ratio, interest coverage (non-financials)
- red flags: the checks a beginner should not miss, in Indonesian

Only *annual* data is used for flags that are tested on history (point-in-time with a 90-day
publication lag, engine/screener/fundamental_study.py); quarterly data is shown, not scored.
"""
import json
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from ..db import get_connection

TTL_DAYS = 7
PUBLICATION_LAG_DAYS = 90   # an annual report is usually public within ~3 months of year end

ROWS = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "net_income": ["Net Income Common Stockholders", "Net Income"],
    "operating_income": ["Operating Income", "EBIT"],
    "interest_expense": ["Interest Expense"],
    "debt": ["Total Debt"],
    "equity": ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "ocf": ["Operating Cash Flow", "Cash Flowsfromusedin Operating Activities Direct",
            "Cash Flow From Continuing Operating Activities"],
    "fcf": ["Free Cash Flow"],
    "capex": ["Capital Expenditure"],
}
FINANCIAL_SECTORS = ("Financial Services", "Keuangan")


# ── storage ──────────────────────────────────────────────────────────────────

def _ensure_table() -> None:
    with get_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS financial_statements (
                            ticker TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        conn.commit()


def _load(ticker: str) -> Optional[Dict[str, Any]]:
    _ensure_table()
    with get_connection() as conn:
        row = conn.execute("SELECT data, updated_at FROM financial_statements WHERE ticker = ?", (ticker,)).fetchone()
    if not row:
        return None
    try:
        return {"data": json.loads(row[0]), "updated_at": row[1]}
    except ValueError:
        return None


def _save(ticker: str, data: Dict[str, Any]) -> None:
    _ensure_table()
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO financial_statements (ticker, data, updated_at) VALUES (?, ?, ?)",
                     (ticker, json.dumps(data), datetime.now().isoformat()))
        conn.commit()


# ── extraction ───────────────────────────────────────────────────────────────

def _series(df: Optional[pd.DataFrame], key: str) -> Dict[str, float]:
    """{period_end 'YYYY-MM-DD': value} for the first candidate row with data, newest first."""
    if df is None or df.empty:
        return {}
    for name in ROWS[key]:
        if name in df.index:
            s = df.loc[name]
            out = {str(c)[:10]: float(v) for c, v in s.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}
            if out:
                return dict(sorted(out.items(), reverse=True))
    return {}


def extract(income: Optional[pd.DataFrame], balance: Optional[pd.DataFrame], cashflow: Optional[pd.DataFrame]) -> Dict[str, Dict[str, float]]:
    out = {k: _series(income, k) for k in ("revenue", "net_income", "operating_income", "interest_expense")}
    out.update({k: _series(balance, k) for k in ("debt", "equity", "current_assets", "current_liabilities")})
    out.update({k: _series(cashflow, k) for k in ("ocf", "fcf", "capex")})
    if not out["ocf"] and out["fcf"] and out["capex"]:
        # OCF = FCF − CapEx (CapEx is reported negative)
        out["ocf"] = {d: out["fcf"][d] - out["capex"][d] for d in out["fcf"] if d in out["capex"]}
    return out


def fetch(ticker: str, force: bool = False) -> Dict[str, Any]:
    """Annual + quarterly series for a ticker (cached TTL_DAYS). {"annual": {...}, "quarterly": {...}}."""
    cached = _load(ticker)
    if cached and not force:
        age = datetime.now() - datetime.fromisoformat(cached["updated_at"])
        if age < timedelta(days=TTL_DAYS):
            return cached["data"]
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        data = {"annual": extract(tk.income_stmt, tk.balance_sheet, tk.cashflow),
                "quarterly": extract(tk.quarterly_income_stmt, tk.quarterly_balance_sheet, tk.quarterly_cashflow)}
    except Exception as e:
        print(f"[Statements] {ticker}: {e}")
        return cached["data"] if cached else {"annual": {}, "quarterly": {}}
    if any(data["annual"].values()):
        _save(ticker, data)
        return data
    return cached["data"] if cached else data


# ── analysis ─────────────────────────────────────────────────────────────────

def _latest(s: Dict[str, float], n: int = 1) -> List[float]:
    return [s[k] for k in sorted(s, reverse=True)[:n]]


def _ratio(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _pct(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x * 100, 1)


def as_of(annual: Dict[str, Dict[str, float]], when: str) -> Dict[str, Dict[str, float]]:
    """Only the annual periods already public at date `when` (year end + PUBLICATION_LAG_DAYS)."""
    cut = (datetime.fromisoformat(when[:10]) - timedelta(days=PUBLICATION_LAG_DAYS)).date().isoformat()
    return {k: {d: v for d, v in s.items() if d <= cut} for k, s in annual.items()}


def analyze(annual: Dict[str, Dict[str, float]], sector: Optional[str] = None,
            quarterly: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    """Metrics + red flags from annual series (newest period first)."""
    financial = (sector or "") in FINANCIAL_SECTORS
    rev = _latest(annual.get("revenue", {}), 4)
    ni = _latest(annual.get("net_income", {}), 4)
    years = sorted(annual.get("net_income", {}), reverse=True)
    m: Dict[str, Any] = {"last_year": years[0][:4] if years else None, "financial": financial}

    m["revenue_growth_pct"] = _pct(_ratio(rev[0] - rev[1], abs(rev[1]))) if len(rev) >= 2 else None
    m["net_income_growth_pct"] = _pct(_ratio(ni[0] - ni[1], abs(ni[1]))) if len(ni) >= 2 else None
    m["revenue_cagr_3y_pct"] = (round(((rev[0] / rev[3]) ** (1 / 3) - 1) * 100, 1)
                               if len(rev) >= 4 and rev[0] > 0 and rev[3] > 0 else None)
    m["profit_declines_3y"] = sum(1 for i in range(min(3, len(ni) - 1)) if ni[i] < ni[i + 1]) if len(ni) >= 2 else None
    m["loss_years"] = sum(1 for v in ni[:3] if v < 0) if ni else None
    m["net_margin_pct"] = _pct(_ratio(ni[0], rev[0])) if ni and rev else None

    ocf = _latest(annual.get("ocf", {}), 1)
    fcf = _latest(annual.get("fcf", {}), 1)
    m["ocf_to_net_income"] = round(_ratio(ocf[0], ni[0]), 2) if ocf and ni and ni[0] > 0 else None
    m["free_cash_flow"] = fcf[0] if fcf else None

    eq = _latest(annual.get("equity", {}), 2)
    m["roe_pct"] = _pct(_ratio(ni[0], (eq[0] + eq[1]) / 2 if len(eq) >= 2 else eq[0])) if ni and eq else None
    if not financial:
        debt = _latest(annual.get("debt", {}), 1)
        ca, cl = _latest(annual.get("current_assets", {}), 1), _latest(annual.get("current_liabilities", {}), 1)
        oi, ie = _latest(annual.get("operating_income", {}), 1), _latest(annual.get("interest_expense", {}), 1)
        m["debt_to_equity"] = round(_ratio(debt[0], eq[0]), 2) if debt and eq and eq[0] > 0 else None
        m["current_ratio"] = round(_ratio(ca[0], cl[0]), 2) if ca and cl else None
        m["interest_coverage"] = round(_ratio(oi[0], abs(ie[0])), 1) if oi and ie and ie[0] else None
    m["negative_equity"] = bool(eq and eq[0] <= 0)

    flags: List[Dict[str, str]] = []

    def flag(code: str, text: str, level: str = "warning") -> None:
        flags.append({"code": code, "text": text, "level": level})

    if m["negative_equity"]:
        flag("NEGATIVE_EQUITY", "Ekuitas negatif — utang lebih besar dari seluruh aset.", "danger")
    if m["loss_years"] and m["loss_years"] >= 2:
        flag("REPEATED_LOSS", f"Rugi bersih di {m['loss_years']} dari 3 tahun terakhir.", "danger")
    elif ni and ni[0] < 0:
        flag("LOSS", "Rugi bersih di tahun buku terakhir.", "warning")
    if m["profit_declines_3y"] is not None and m["profit_declines_3y"] >= 2 and not (ni and ni[0] < 0):
        flag("PROFIT_FALLING", "Laba bersih turun di 2 dari 3 tahun terakhir.", "warning")
    if ocf and ni and ni[0] > 0 and ocf[0] < 0:
        flag("CASH_NEGATIVE", "Laba positif tetapi arus kas operasi negatif — laba belum menjadi uang tunai.", "warning")
    elif m["ocf_to_net_income"] is not None and m["ocf_to_net_income"] < 0.5:
        flag("LOW_CASH_QUALITY", "Arus kas operasi kurang dari separuh laba — kualitas laba perlu dicek.", "info")
    if not financial and m.get("debt_to_equity") is not None and m["debt_to_equity"] > 2:
        flag("HIGH_DEBT", f"Utang {_fmt_x(m['debt_to_equity'])}× ekuitas — beban utang tinggi.", "warning")
    if not financial and m.get("current_ratio") is not None and m["current_ratio"] < 1:
        flag("LOW_LIQUIDITY", f"Aset lancar lebih kecil dari utang lancar (current ratio {_fmt_x(m['current_ratio'])}).", "info")
    if not financial and m.get("interest_coverage") is not None and 0 < m["interest_coverage"] < 1.5:
        flag("WEAK_COVERAGE", f"Laba operasi hanya {_fmt_x(m['interest_coverage'])}× beban bunga.", "warning")
    m["flags"] = flags

    if quarterly:
        q = quarterly.get("net_income", {})
        qs = sorted(q, reverse=True)
        m["quarters"] = [{"period": d, "revenue": quarterly.get("revenue", {}).get(d), "net_income": q[d]} for d in qs[:5]]
    m["years"] = [{"period": d, "revenue": annual.get("revenue", {}).get(d), "net_income": annual.get("net_income", {}).get(d),
                   "ocf": annual.get("ocf", {}).get(d)} for d in years[:5]]
    m["available"] = bool(years)
    return m


def _fmt_x(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")
