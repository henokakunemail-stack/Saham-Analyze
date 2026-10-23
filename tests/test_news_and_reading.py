"""Per-stock news filtering, recency-weighted sentiment and the Top-10 action plan (offline)."""
from datetime import datetime, timedelta, timezone

from engine.collectors.ticker_news import parse_entries, is_relevant
from engine.screener.sentiment import aggregate_news_sentiment, score_article_sentiment
from engine.screener.scoring import build_reading

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def entry(title, hours_ago, source="KONTAN"):
    pub = (NOW - timedelta(hours=hours_ago)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    return {"title": f"{title} - {source}", "link": "https://example.test/x", "published": pub, "source": {"title": source}}


def test_relevance_requires_ticker_or_issuer_and_drops_tutorials():
    assert is_relevant("Direktur Borong 1,1 Juta Saham BBRI", "BBRI.JK")
    assert is_relevant("Laba Bank Rakyat Indonesia naik", "BBRI.JK")
    assert not is_relevant("Cara Beli Saham Bank BRI (BBRI) Online dan Mudah", "BBRI.JK")
    assert not is_relevant("IHSG ditutup melemah sore ini", "BBRI.JK")
    assert not is_relevant("BBRIX fund launch", "BBRI.JK")  # code must be a whole word


def test_parse_entries_strips_source_dedupes_sorts_and_drops_old():
    items = parse_entries([
        entry("ADRO lanjutkan buyback saham", 30),
        entry("ADRO lanjutkan buyback saham", 31, source="Ajaib"),   # duplicate story
        entry("Keluarga Thohir borong saham ADRO", 2),
        entry("ADRO cetak laba rekor", 24 * 9),                       # older than 7 days
    ], "ADRO.JK", now=NOW)
    assert [i["title"] for i in items] == ["Keluarga Thohir borong saham ADRO", "ADRO lanjutkan buyback saham"]
    assert items[0]["source"] == "KONTAN" and items[0]["age_hours"] == 2.0


def test_indonesian_market_phrases():
    assert score_article_sentiment("Direktur Borong 1,1 Juta Saham BBRI")["sentiment_label"] == "POSITIVE"
    assert score_article_sentiment("Net sell asing BBRI tembus Rp1 triliun")["sentiment_label"] == "NEGATIVE"
    assert score_article_sentiment("BEI suspensi saham XYZ")["catalysts"][0].startswith("RISK:")
    assert score_article_sentiment("Laba TLKM turun 12%")["sentiment_label"] == "NEGATIVE"


def test_recent_news_outweighs_old_news():
    fresh_bad = {"title": "Net sell asing BBRI Rp1 triliun", "age_hours": 3}
    old_good = {"title": "Direktur borong saham BBRI", "age_hours": 150}
    agg = aggregate_news_sentiment([fresh_bad, old_good])
    assert agg["sentiment_score"] < 0 and agg["catalyst"] == "Asing Net Sell"
    assert agg["headlines"][0]["title"] == fresh_bad["title"]  # newest first


def _tech(price=100.0, ema20=98.0, hist=0.2, hist_prev=0.1):
    return {"price": price, "ema20": ema20, "macd_hist": hist, "macd_hist_prev": hist_prev}


def _dir(state, rel=5.0, support=95.0):
    return {"pullback": {"state": state, "relative_momentum_pct": rel, "support_level": support}}


NEUTRAL_NEWS = {"sentiment_label": "NEUTRAL", "catalyst": "Nol Berita Baru"}


def test_reading_pullback_with_both_triggers_is_actionable_in_normal_market():
    r = build_reading(_tech(), _dir("PULLBACK_IDEAL"), NEUTRAL_NEWS, "NORMAL", "MILD_BULLISH", False, 94.0, 110.0)
    assert r["stance"] == "LAYAK_DIPERTIMBANGKAN" and r["triggers_met"] == 2
    assert r["invalidation_level"] == 94.0 and "110" in r["target"]   # the plan's cut loss, same number as the card


def test_reading_waits_when_trigger_missing():
    r = build_reading(_tech(price=97, hist=-0.2, hist_prev=-0.1), _dir("PULLBACK_IDEAL"), NEUTRAL_NEWS, "NORMAL",
                      "MILD_BULLISH", False, 94.0, 110.0)
    assert r["stance"] == "TUNGGU_PEMICU" and r["triggers_met"] == 0


def test_reading_market_and_news_overrides():
    crash = build_reading(_tech(), _dir("PULLBACK_IDEAL"), NEUTRAL_NEWS, "CRASH", "NEUTRAL", False, 94.0, 110.0)
    assert crash["stance"] == "TAHAN"
    risk = build_reading(_tech(), _dir("PULLBACK_IDEAL"), {"sentiment_label": "NEGATIVE", "catalyst": "RISK: Suspensi"},
                         "NORMAL", "MILD_BULLISH", False, 94.0, 110.0)
    assert risk["stance"] == "HINDARI" and "Suspensi" in risk["headline"]
    bear = build_reading(_tech(), _dir("PULLBACK_IDEAL"), NEUTRAL_NEWS, "BEARISH", "MILD_BULLISH", False, 94.0, 110.0)
    assert bear["stance"] == "TUNGGU_PEMICU"


def test_reading_states():
    for state, stance in (("UPTREND_EXTENDED", "TUNGGU_PULLBACK"), ("TREND_BROKEN", "HINDARI"),
                          ("NO_UPTREND", "HINDARI"), ("UPTREND_RUNNING", "PANTAU")):
        assert build_reading(_tech(), _dir(state), NEUTRAL_NEWS, "NORMAL", "NEUTRAL", False, 94.0, 110.0)["stance"] == stance


def test_roundups_and_price_recaps_weigh_less():
    from engine.screener.sentiment import headline_info_weight
    assert headline_info_weight("Ide Trading Hari Ini: AKRA, GOTO, PSAB, MDKA") < 1
    assert headline_info_weight("Saham MEDC Menguat 11,11 Persen Saat Death Cross Membayangi") < 1
    assert headline_info_weight("Trinugraha Thohir Borong Saham ADRO Senilai Rp 1 M") == 1
    specific = aggregate_news_sentiment([{"title": "Direktur borong saham BBRI", "age_hours": 5}])
    recap = aggregate_news_sentiment([{"title": "Saham BBRI melonjak 9,8 persen, rebound", "age_hours": 5}])
    assert specific["sentiment_score"] > recap["sentiment_score"]


def test_acronyms_are_not_counted_as_tickers():
    from engine.screener.sentiment import headline_info_weight
    assert headline_info_weight("Padamnya PLTU Banjarsari Milik PTBA: DPRD Lahat Cium Manipulasi Kuota") == 1


def test_locked_one_price_bar_is_not_no_supply():
    import pandas as pd
    from engine.indicators.money_flow import compute_money_flow
    n = 40
    close = [1000 - i * 5 for i in range(n - 1)] + [1000 - (n - 2) * 5 - 15]
    df = pd.DataFrame({"open": [c + 5 for c in close], "high": [c + 10 for c in close], "low": [c - 10 for c in close],
                       "close": close, "volume": [1_000_000] * n})
    last = close[-1]
    df.loc[n - 1, ["open", "high", "low", "volume"]] = [last, last, last, 200_000]   # ARB lock
    flow = compute_money_flow(df)
    assert flow["vsa_signal"] == "LOCKED" and "turun" in flow["vsa_label"]
