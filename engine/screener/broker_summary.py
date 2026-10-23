"""Broker Summary (Bandarmologi) engine for Indonesian Stock Exchange (IDX).

Analyzes institutional broker flow, retail absorption, concentration ratios,
and Bandar Average Price.
"""

import json
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional
import urllib.request
import urllib.error

from ..db import (
    get_connection,
    get_setting,
    save_broker_summary,
    get_cached_broker_summary
)

logger = logging.getLogger(__name__)

# Master Registry of IDX Broker Codes
BROKER_REGISTRY: Dict[str, Dict[str, str]] = {
    # Foreign Institutional (Smart Money)
    "AK": {"name": "UBS Sekuritas Indonesia", "type": "FOREIGN"},
    "BK": {"name": "J.P. Morgan Sekuritas Indonesia", "type": "FOREIGN"},
    "KZ": {"name": "CLSA Sekuritas Indonesia", "type": "FOREIGN"},
    "ZP": {"name": "Maybank Sekuritas Indonesia", "type": "FOREIGN"},
    "RX": {"name": "Macquarie Sekuritas Indonesia", "type": "FOREIGN"},
    "CG": {"name": "CGS International Sekuritas", "type": "FOREIGN"},
    "CS": {"name": "Credit Suisse Sekuritas Indonesia", "type": "FOREIGN"},
    "MS": {"name": "Morgan Stanley Sekuritas Indonesia", "type": "FOREIGN"},
    "DB": {"name": "Deutsche Sekuritas Indonesia", "type": "FOREIGN"},
    "ML": {"name": "BofA Securities Indonesia", "type": "FOREIGN"},
    "AI": {"name": "UOB Kay Hian Sekuritas (Foreign)", "type": "FOREIGN"},
    "DP": {"name": "DBS Vickers Sekuritas Indonesia", "type": "FOREIGN"},
    "GW": {"name": "HSBC Securities Indonesia", "type": "FOREIGN"},
    "FS": {"name": "Yuanta Sekuritas Indonesia", "type": "FOREIGN"},

    # Domestic Institutions / BUMN / Asset Management
    "CC": {"name": "Mandiri Sekuritas", "type": "DOMESTIC_INSTITUTION"},
    "NI": {"name": "BNI Sekuritas", "type": "DOMESTIC_INSTITUTION"},
    "OD": {"name": "BRI Danareksa Sekuritas", "type": "DOMESTIC_INSTITUTION"},
    "BM": {"name": "Sucor Sekuritas (Institusi)", "type": "DOMESTIC_INSTITUTION"},
    "LG": {"name": "Trimegah Sekuritas Indonesia", "type": "DOMESTIC_INSTITUTION"},
    "DR": {"name": "RHB Sekuritas Indonesia", "type": "DOMESTIC_INSTITUTION"},
    "KI": {"name": "Ciptadana Sekuritas Asia", "type": "DOMESTIC_INSTITUTION"},
    "HP": {"name": "Henan Putihrai Sekuritas", "type": "DOMESTIC_INSTITUTION"},
    "HD": {"name": "KGI Sekuritas Indonesia", "type": "DOMESTIC_INSTITUTION"},
    "EP": {"name": "MNC Sekuritas", "type": "DOMESTIC_INSTITUTION"},
    "RG": {"name": "Profindo Sekuritas", "type": "DOMESTIC_INSTITUTION"},
    "SH": {"name": "Artha Sekuritas", "type": "DOMESTIC_INSTITUTION"},
    "SS": {"name": "Shinhan Sekuritas Indonesia", "type": "DOMESTIC_INSTITUTION"},

    # Retail Crowd / Followers
    "YP": {"name": "Mirae Asset Sekuritas Indonesia", "type": "RETAIL"},
    "XC": {"name": "Ajaib Sekuritas Asia", "type": "RETAIL"},
    "XL": {"name": "Stockbit Sekuritas", "type": "RETAIL"},
    "PD": {"name": "Indo Premier Sekuritas (IPOT)", "type": "RETAIL"},
    "SQ": {"name": "BCA Sekuritas", "type": "RETAIL"},
    "CP": {"name": "KB Valbury Sekuritas", "type": "RETAIL"},
    "KK": {"name": "Phillip Sekuritas Indonesia", "type": "RETAIL"},
    "AZ": {"name": "Sucor Sekuritas (Ritel)", "type": "RETAIL"},
    "GR": {"name": "Panin Sekuritas", "type": "RETAIL"},
    "SF": {"name": "Surya Fajar Sekuritas", "type": "RETAIL"},
    "BQ": {"name": "Korea Investment & Sekuritas", "type": "RETAIL"},
    "IH": {"name": "Pacific Sekuritas Indonesia", "type": "RETAIL"},
}

def get_broker_info(code: str) -> Dict[str, str]:
    """Retrieve name and category for broker code."""
    code_up = (code or "").upper().strip()
    if code_up in BROKER_REGISTRY:
        return BROKER_REGISTRY[code_up]
    return {
        "name": f"Sekuritas {code_up}",
        "type": "RETAIL"
    }

def evaluate_bandarmologi(
    top_buyers: List[Dict[str, Any]],
    top_sellers: List[Dict[str, Any]],
    current_price: float
) -> Dict[str, Any]:
    """Compute concentration ratios, bandar average price, and accumulation verdict."""
    top3_bval = sum(float(b.get("bval", 0)) for b in top_buyers[:3])
    top3_sval = sum(float(s.get("sval", 0)) for s in top_sellers[:3])

    top1_bval = float(top_buyers[0].get("bval", 0)) if top_buyers else 0
    top1_sval = float(top_sellers[0].get("sval", 0)) if top_sellers else 0

    top3_ratio = round(top3_bval / top3_sval, 2) if top3_sval > 0 else 2.0

    # Foreign & Institutional Dominance calculation
    foreign_buyers = [b for b in top_buyers[:5] if b.get("type") == "FOREIGN"]
    foreign_sellers = [s for s in top_sellers[:5] if s.get("type") == "FOREIGN"]

    foreign_bval = sum(float(b.get("bval", 0)) for b in foreign_buyers)
    foreign_sval = sum(float(s.get("sval", 0)) for s in foreign_sellers)
    net_foreign_val = round(foreign_bval - foreign_sval, 2)

    inst_buyers = [b for b in top_buyers[:3] if b.get("type") in ("FOREIGN", "DOMESTIC_INSTITUTION")]
    inst_sellers = [s for s in top_sellers[:3] if s.get("type") in ("FOREIGN", "DOMESTIC_INSTITUTION")]

    # Calculate Bandar Average Price of Top Buyers
    total_bvol = sum(float(b.get("bvol", 0)) for b in top_buyers[:3])
    if total_bvol > 0 and top3_bval > 0:
        # standard 1 lot = 100 shares
        raw_avg = top3_bval / (total_bvol * 100) if total_bvol < 1e8 else top3_bval / total_bvol
        # Normalize sanity check against current price
        if 0.5 * current_price <= raw_avg <= 1.5 * current_price:
            bandar_avg_price = round(raw_avg, 2)
        else:
            bandar_avg_price = round(current_price * 0.992, 2)
    else:
        bandar_avg_price = round(current_price * 0.99, 2)

    # Determine status & labels
    reasons = []
    if top3_ratio >= 1.65 or (top3_ratio >= 1.35 and len(inst_buyers) >= 2 and net_foreign_val > 0):
        bandar_status = "BIG_ACCUM"
        bandar_status_label = "🟢 AKUMULASI BESAR (BIG ACCUMULATION)"
        top_codes = ", ".join([b.get("broker", "") for b in top_buyers[:3]])
        reasons.append(f"Top 3 Buyer ({top_codes}) mendominasi {top3_ratio}x lebih besar dari Top 3 Seller.")
        if net_foreign_val > 0:
            reasons.append(f"Arus modal asing (Smart Money) mencatat Net Buy positif Rp {net_foreign_val / 1e9:.2f} Miliar.")
    elif top3_ratio >= 1.20:
        bandar_status = "ACCUM"
        bandar_status_label = "🟡 AKUMULASI RINGAN"
        reasons.append(f"Pembelian terkonsentrasi di broker utama (Rasio Top 3: {top3_ratio}x).")
    elif top3_ratio <= 0.65 or (top3_ratio <= 0.75 and len(inst_sellers) >= 2):
        bandar_status = "BIG_DIST"
        bandar_status_label = "🔴 DISTRIBUSI BESAR (BIG DISTRIBUTION)"
        seller_codes = ", ".join([s.get("broker", "") for s in top_sellers[:3]])
        reasons.append(f"Tekanan jual masif oleh Top 3 Seller ({seller_codes}). Rasio Buyer/Seller hanya {top3_ratio}x.")
        if net_foreign_val < 0:
            reasons.append(f"Asing keluar bersih (Net Sell) Rp {abs(net_foreign_val) / 1e9:.2f} Miliar.")
    elif top3_ratio <= 0.85:
        bandar_status = "DIST"
        bandar_status_label = "🟠 DISTRIBUSI RINGAN"
        reasons.append(f"Distribusi bertahap, tekanan jual lebih besar daripada daya serap pembeli.")
    else:
        bandar_status = "NEUTRAL"
        bandar_status_label = "⚪ TRANSAKSI NORMAL / NETRAL"
        reasons.append("Transaksi seimbang antara pembeli dan penjual.")

    # Price comparison note
    if bandar_avg_price > 0:
        diff_pct = round(((current_price - bandar_avg_price) / bandar_avg_price) * 100, 2)
        if diff_pct > 0:
            reasons.append(f"Harga saat ini +{diff_pct}% di atas estimasi harga modal rata-rata bandar (Rp {bandar_avg_price:,.0f}).")
        else:
            reasons.append(f"Harga saat ini {diff_pct}% di bawah harga modal rata-rata bandar (Rp {bandar_avg_price:,.0f}) — Zona Diskon Bandar.")

    return {
        "bandar_status": bandar_status,
        "bandar_status_label": bandar_status_label,
        "bandar_avg_price": bandar_avg_price,
        "top3_ratio": top3_ratio,
        "net_foreign_val": net_foreign_val,
        "summary_notes": reasons
    }

def fetch_from_sectors_app(symbol: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Fetch official Top Broker Summary from Sectors.app."""
    clean_sym = symbol.replace(".JK", "").upper().strip()
    url = f"https://api.sectors.app/v2/broker-summary/{clean_sym}/top/"
    req = urllib.request.Request(url, headers={
        "Authorization": api_key,
        "User-Agent": "SAHAM-Desktop/2.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                top_buyers = []
                for b in data.get("top_buyers", [])[:5]:
                    code = b.get("broker_code") or b.get("broker", "")
                    info = get_broker_info(code)
                    top_buyers.append({
                        "broker": code,
                        "name": info["name"],
                        "type": info["type"],
                        "bval": float(b.get("buy_value", 0)),
                        "bvol": float(b.get("buy_volume", 0)),
                        "avg_price": float(b.get("avg_price", 0))
                    })
                top_sellers = []
                for s in data.get("top_sellers", [])[:5]:
                    code = s.get("broker_code") or s.get("broker", "")
                    info = get_broker_info(code)
                    top_sellers.append({
                        "broker": code,
                        "name": info["name"],
                        "type": info["type"],
                        "sval": float(s.get("sell_value", 0)),
                        "svol": float(s.get("sell_volume", 0)),
                        "avg_price": float(s.get("avg_price", 0))
                    })
                return {
                    "source": "SECTORS_APP",
                    "trade_date": data.get("date") or str(date.today()),
                    "top_buyers": top_buyers,
                    "top_sellers": top_sellers
                }
    except Exception as e:
        logger.warning(f"Sectors.app request failed for {clean_sym}: {e}")
        return None

def generate_proxy_broker_summary(
    ticker: str,
    current_price: float,
    cmf20: float,
    vol_ratio: float,
    change_pct: float,
    vsa_signal: str
) -> Dict[str, Any]:
    """Generate SIMULATED broker rows from CMF/VSA/volume (not real transactions).

    Kept for experiments only: fetch_and_evaluate_broker_summary never returns this output,
    because fabricated broker codes must not be shown or evaluated as real flow.
    """
    clean_sym = ticker.replace(".JK", "").upper().strip()
    is_accum = (cmf20 >= 0.05 or vsa_signal in ("ABSORPTION", "MARKUP", "NO_SUPPLY_TEST") or (vol_ratio >= 1.4 and change_pct > 0))
    is_dist = (cmf20 <= -0.05 or vsa_signal in ("BUYING_CLIMAX", "SELLING_PRESSURE") or (vol_ratio >= 1.4 and change_pct < 0))

    # Base nominal estimation based on typical daily turnover
    base_val = max(current_price * 1500000 * max(vol_ratio, 0.8), 2_000_000_000)

    if is_accum:
        # Smart money buyers dominate
        buyers_pool = ["AK", "BK", "KZ", "CC", "ZP"]
        sellers_pool = ["YP", "XC", "XL", "PD", "SQ"]
        b_mult = 1.45 + min(abs(cmf20) * 2, 0.8)
        s_mult = 0.90
        bandar_avg = round(current_price * 0.994, 2)
    elif is_dist:
        # Institutions dump, retail absorbs
        buyers_pool = ["YP", "XC", "XL", "PD", "SQ"]
        sellers_pool = ["BK", "AK", "KZ", "CC", "RX"]
        b_mult = 0.85
        s_mult = 1.40 + min(abs(cmf20) * 2, 0.7)
        bandar_avg = round(current_price * 1.012, 2)
    else:
        # Neutral mix
        buyers_pool = ["CC", "YP", "AK", "PD", "NI"]
        sellers_pool = ["XC", "BK", "XL", "OD", "SQ"]
        b_mult = 1.05
        s_mult = 1.0
        bandar_avg = round(current_price * 0.998, 2)

    top_buyers = []
    top_sellers = []

    weights_b = [0.35, 0.25, 0.18, 0.12, 0.10]
    weights_s = [0.32, 0.26, 0.19, 0.13, 0.10]

    for code, w in zip(buyers_pool, weights_b):
        info = get_broker_info(code)
        val = round(base_val * b_mult * w, 2)
        vol = round(val / (bandar_avg * 100))
        top_buyers.append({
            "broker": code,
            "name": info["name"],
            "type": info["type"],
            "bval": val,
            "bvol": vol,
            "avg_price": bandar_avg
        })

    for code, w in zip(sellers_pool, weights_s):
        info = get_broker_info(code)
        val = round(base_val * s_mult * w, 2)
        vol = round(val / (current_price * 100))
        top_sellers.append({
            "broker": code,
            "name": info["name"],
            "type": info["type"],
            "sval": val,
            "svol": vol,
            "avg_price": round(current_price, 2)
        })

    return {
        "source": "PROXY",
        "trade_date": str(date.today()),
        "top_buyers": top_buyers,
        "top_sellers": top_sellers,
        "is_simulated": True
    }

NO_DATA_STATUS = "NO_DATA"
NO_DATA_LABEL = "⚪ DATA BROKER TIDAK TERSEDIA"


def is_simulated_summary(summary: Optional[Dict[str, Any]]) -> bool:
    """True when the broker rows were not fetched from a real provider."""
    if not summary:
        return True
    source = str(summary.get("source") or "").upper()
    return bool(summary.get("is_simulated")) or source in ("PROXY", "NO_DATA", "")


def no_data_broker_summary(ticker: str, market: str = "IDX", reason: str = "NO_KEY") -> Dict[str, Any]:
    """Neutral response used instead of fabricated (proxy) broker rows.

    It carries no buyers/sellers and a NO_DATA status so nothing downstream can read a
    bandar accumulation/distribution signal out of simulated numbers.
    """
    messages = {
        "NO_KEY": "Data broker summary asli belum tersedia. Masukkan API key Sectors.app di Pengaturan untuk melihat transaksi broker sebenarnya.",
        "FETCH_FAILED": "Gagal mengambil data broker summary dari Sectors.app. Periksa API key di Pengaturan atau coba lagi nanti.",
        "NOT_IDX": "Broker summary hanya tersedia untuk saham IDX.",
    }
    return {
        "ticker": ticker,
        "trade_date": str(date.today()),
        "source": "NO_DATA",
        "top_buyers": [],
        "top_sellers": [],
        "net_foreign_val": 0.0,
        "bandar_status": NO_DATA_STATUS,
        "bandar_status_label": NO_DATA_LABEL,
        "bandar_avg_price": 0.0,
        "top3_ratio": 0.0,
        "summary_notes": [],
        "is_simulated": False,
        "data_available": False,
        "no_data_reason": reason,
        "no_data_message": messages.get(reason, messages["NO_KEY"]),
    }


def fetch_and_evaluate_broker_summary(
    ticker: str,
    market: str = "IDX",
    current_price: float = 0.0,
    cmf20: float = 0.0,
    vol_ratio: float = 1.0,
    change_pct: float = 0.0,
    vsa_signal: str = "NORMAL",
    force_refresh: bool = False
) -> Dict[str, Any]:
    """Broker summary from a real provider (Sectors.app) with a 24h SQLite cache.

    Without a working provider a neutral NO_DATA summary is returned. Simulated proxy rows
    (generate_proxy_broker_summary) are never returned or cached as if they were real.
    """
    clean_ticker = ticker.upper().strip()
    today_str = str(date.today())

    if market != "IDX":
        return no_data_broker_summary(clean_ticker, market, "NOT_IDX")

    # 1. Cache (only real provider data counts; old cached PROXY rows are ignored)
    if not force_refresh:
        cached = get_cached_broker_summary(clean_ticker, today_str)
        if cached and not is_simulated_summary(cached):
            cached["is_simulated"] = False
            cached["data_available"] = True
            return cached

    # 2. Real provider (Sectors.app API key from Pengaturan)
    sectors_key = get_setting("sectors_api_key", "").strip()
    if not sectors_key:
        return no_data_broker_summary(clean_ticker, market, "NO_KEY")
    raw_summary = fetch_from_sectors_app(clean_ticker, sectors_key)
    if not raw_summary or not (raw_summary.get("top_buyers") or raw_summary.get("top_sellers")):
        return no_data_broker_summary(clean_ticker, market, "FETCH_FAILED")

    # 3. Bandarmologi evaluation on real rows
    eval_res = evaluate_bandarmologi(
        raw_summary.get("top_buyers", []),
        raw_summary.get("top_sellers", []),
        current_price
    )

    combined: Dict[str, Any] = {
        "ticker": clean_ticker,
        "trade_date": raw_summary.get("trade_date", today_str),
        "source": raw_summary.get("source", "SECTORS_APP"),
        "top_buyers": raw_summary.get("top_buyers", []),
        "top_sellers": raw_summary.get("top_sellers", []),
        "net_foreign_val": eval_res["net_foreign_val"],
        "bandar_status": eval_res["bandar_status"],
        "bandar_status_label": eval_res["bandar_status_label"],
        "bandar_avg_price": eval_res["bandar_avg_price"],
        "top3_ratio": eval_res["top3_ratio"],
        "summary_notes": eval_res["summary_notes"],
        "is_simulated": False,
        "data_available": True,
    }

    # 4. Persist to cache
    try:
        save_broker_summary(combined)
    except Exception as e:
        logger.warning(f"Failed to cache broker summary for {clean_ticker}: {e}")

    return combined
