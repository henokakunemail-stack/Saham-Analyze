"""Financial statement metrics and red flags (offline, synthetic statements)."""
import pandas as pd

from engine.screener import financial_statements as fs


def frame(rows):
    cols = ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"]
    return pd.DataFrame({c: [v[i] for v in rows.values()] for i, c in enumerate(cols)}, index=list(rows))


INCOME = frame({"Total Revenue": [1200, 1100, 1000, 900], "Net Income Common Stockholders": [100, 120, 130, 90],
                "Operating Income": [180, 190, 200, 150], "Interest Expense": [-150, -40, -40, -40]})
BALANCE = frame({"Total Debt": [1500, 600, 600, 600], "Stockholders Equity": [600, 580, 560, 500],
                 "Current Assets": [400, 400, 400, 400], "Current Liabilities": [500, 300, 300, 300]})
CASH = frame({"Free Cash Flow": [-80, 50, 60, 40], "Capital Expenditure": [-60, -40, -40, -40]})


def test_extract_falls_back_to_fcf_minus_capex_for_operating_cash():
    a = fs.extract(INCOME, BALANCE, CASH)
    assert a["ocf"]["2025-12-31"] == -80 - (-60) and a["revenue"]["2025-12-31"] == 1200


def test_metrics_and_flags():
    m = fs.analyze(fs.extract(INCOME, BALANCE, CASH), sector="Industrials")
    assert m["revenue_growth_pct"] == 9.1 and m["net_income_growth_pct"] == -16.7
    assert m["profit_declines_3y"] == 2 and m["debt_to_equity"] == 2.5 and m["current_ratio"] == 0.8
    codes = {f["code"] for f in m["flags"]}
    assert {"PROFIT_FALLING", "CASH_NEGATIVE", "HIGH_DEBT", "LOW_LIQUIDITY", "WEAK_COVERAGE"} <= codes
    assert m["last_year"] == "2025" and m["available"]


def test_banks_are_not_judged_on_debt():
    m = fs.analyze(fs.extract(INCOME, BALANCE, CASH), sector="Financial Services")
    codes = {f["code"] for f in m["flags"]}
    assert "HIGH_DEBT" not in codes and "LOW_LIQUIDITY" not in codes and m.get("debt_to_equity") is None


def test_point_in_time_hides_reports_not_yet_published():
    a = fs.extract(INCOME, BALANCE, CASH)
    early = fs.as_of(a, "2026-02-15")            # FY2025 not public until ~31 Mar 2026
    assert "2025-12-31" not in early["revenue"] and "2024-12-31" in early["revenue"]
    assert "2025-12-31" in fs.as_of(a, "2026-04-15")["revenue"]


def test_statements_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from engine import main
    monkeypatch.setattr(fs, "fetch", lambda t, force=False: {"annual": fs.extract(INCOME, BALANCE, CASH), "quarterly": {}})
    r = TestClient(main.app).get("/api/stock/ABCD/statements?market=IDX").json()
    assert r["ticker"] == "ABCD.JK" and r["available"] and "valuation" in r and r["flags"]


def test_losses_and_empty_data():
    loss = frame({"Total Revenue": [100, 100, 100, 100], "Net Income": [-5, -3, 2, 4]})
    m = fs.analyze(fs.extract(loss, None, None))
    assert any(f["code"] == "REPEATED_LOSS" for f in m["flags"])
    assert fs.analyze({})["available"] is False
