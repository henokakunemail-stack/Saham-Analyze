"""Configuration & Constants for SAHAM Desktop Analyzer."""
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def get_resource_path(relative_path: str = "") -> Path:
    """Get absolute path to resource, works for dev and for PyInstaller frozen binary."""
    if getattr(sys, 'frozen', False):
        candidates = []
        if hasattr(sys, '_MEIPASS'):
            candidates.append(Path(sys._MEIPASS))
            candidates.append(Path(sys._MEIPASS) / "_internal")
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal")
        candidates.append(exe_dir)
        for base in candidates:
            target = base / relative_path if relative_path else base
            if target.exists():
                return target
        return candidates[0] / relative_path if relative_path else candidates[0]
    else:
        base_path = BASE_DIR.parent
        return base_path / relative_path if relative_path else base_path

# SQLite Database Path (In APPDATA if frozen, to prevent permission issues in Program Files)
if os.environ.get('SAHAM_DB_PATH'):
    # Override for tests/scripts: point the whole engine at a throwaway database
    DB_PATH = Path(os.environ['SAHAM_DB_PATH'])
elif getattr(sys, 'frozen', False):
    appdata_dir = Path(os.environ.get('APPDATA', str(Path.home()))) / "SAHAM"
    appdata_dir.mkdir(parents=True, exist_ok=True)
    DB_PATH = appdata_dir / "saham.db"
else:
    DB_PATH = BASE_DIR / "saham.db"

# Default Markets & Tickers
# Default scan universe. IDX: the original 30 first, then names that traded at least Rp5 miliar/day
# (20-day average) in Oct 2026; US: large caps trading at least US$200 juta/day.
DEFAULT_IDX_TICKERS = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "TLKM.JK", "ASII.JK", "ADRO.JK", "ICBP.JK",
    "INDF.JK", "UNVR.JK", "KLBF.JK", "AMRT.JK", "CPIN.JK", "ANTM.JK", "INCO.JK", "PTBA.JK",
    "MDKA.JK", "PGAS.JK", "GOTO.JK", "BRIS.JK", "MEDC.JK", "INKP.JK", "SMGR.JK", "ITMG.JK",
    "AKRA.JK", "TPIA.JK", "BREN.JK", "AMMN.JK", "CUAN.JK", "BRPT.JK", "BUMI.JK", "DSSA.JK",
    "PTRO.JK", "TINS.JK", "DEWA.JK", "ENRG.JK", "PACK.JK", "BRMS.JK", "AADI.JK", "SINI.JK",
    "FORU.JK", "ISAT.JK", "UNTR.JK", "INET.JK", "DOOH.JK", "ERAA.JK", "BUVA.JK", "VKTR.JK",
    "ADMR.JK", "WIFI.JK", "ULTJ.JK", "BNBR.JK", "IATA.JK", "TOWR.JK", "MBMA.JK", "INDY.JK",
    "ESSA.JK", "DMAS.JK", "SGER.JK", "PSAB.JK", "RAJA.JK", "NCKL.JK", "KIJA.JK", "AALI.JK",
    "PANI.JK", "ARCI.JK", "BDMN.JK", "HRTA.JK", "JPFA.JK", "TAPG.JK", "CDIA.JK", "EXCL.JK",
    "BBTN.JK", "RATU.JK", "BSDE.JK", "GGRM.JK", "SSIA.JK", "EMTK.JK", "ARKO.JK", "MAPI.JK",
    "MARK.JK", "PGEO.JK", "BFIN.JK", "PWON.JK", "TKIM.JK", "ACES.JK", "SMDR.JK", "MAPA.JK",
    "MYOR.JK", "BNGA.JK", "LSIP.JK", "ELSA.JK", "BUKA.JK", "JSMR.JK", "BSSR.JK", "MNCN.JK",
    "HMSP.JK", "TRUE.JK", "CMRY.JK", "TCPI.JK", "AUTO.JK", "ARTO.JK", "CBRE.JK", "SMRA.JK",
    "CBDK.JK", "SSMS.JK", "CTRA.JK", "BTPS.JK", "BMTR.JK", "SCMA.JK", "INTP.JK", "SIDO.JK",
    "HRUM.JK", "NICL.JK", "FILM.JK", "NISP.JK", "VICI.JK", "CLEO.JK", "MSIN.JK", "BBYB.JK",
    "HATM.JK", "POWR.JK", "LPKR.JK", "TOBA.JK", "SMSM.JK", "DSNG.JK",
]

DEFAULT_US_TICKERS = [
    "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AMD", "PLTR", "AVGO",
    "NFLX", "INTC", "QCOM", "BABA", "COIN", "MU", "ORCL", "MDT", "AMAT", "LLY",
    "JPM", "LRCX", "WMT", "UNH", "BAC", "V", "BRK-B", "COST", "GS", "CAT",
    "CRM", "PANW", "JNJ", "XOM", "CSCO", "MA", "HD", "ACN", "CVX", "NKE",
    "MCD", "TMO", "TXN", "NOW", "KO", "ABBV", "PG", "GE", "MRK", "PEP",
    "IBM", "BKNG", "AMGN", "MS", "INTU", "UBER", "DHR", "ADBE", "LIN", "ABT",
    "DIS", "SBUX", "PFE", "RTX", "ISRG", "DE", "SPGI", "BLK", "LOW", "UNP",
    "LMT", "ADP", "HON", "UPS",
]

# Verified reachable 2026-10-21. Bisnis.com (403 for all automated clients) and the old
# Yahoo rssindex (404) were removed.
RSS_FEEDS = {
    "CNBC_ID": "https://www.cnbcindonesia.com/market/rss",
    "KONTAN_INVESTASI": "https://investasi.kontan.co.id/rss",
    "ANTARA_BURSA": "https://www.antaranews.com/rss/ekonomi-bursa.xml",
    "OKEZONE_EKONOMI": "https://sindikasi.okezone.com/index.php/rss/11/RSS2.0",
    "YAHOO_SP500": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
    "CNBC_US_MARKETS": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
}
