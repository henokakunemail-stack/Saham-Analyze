"""New candlestick detection: context, size, locked bars, bearish counterparts (offline)."""
import pandas as pd

from engine.indicators.candles import detect


def frame(bars, lead="down", n_lead=8, start=1000.0, step=10.0):
    """`bars` (o, h, l, c) appended after a lead-in trend of `n_lead` ordinary candles."""
    rows, p = [], start
    for _ in range(n_lead):
        nxt = p - step if lead == "down" else p + step
        rows.append((p, max(p, nxt) + 4, min(p, nxt) - 4, nxt))
        p = nxt
    rows += bars
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_locked_bar_is_never_a_hammer():
    df = frame([(920, 920, 920, 920)])
    assert detect(df, atr=20)["pattern"] == "LOCKED"


def test_doji_before_hammer():
    # tiny body with a long lower shadow: a doji, not a hammer
    df = frame([(920, 922, 890, 920.5)])
    assert detect(df, atr=20)["pattern"] == "DOJI"


def test_hammer_needs_a_decline_and_hanging_man_an_advance():
    hammer_bar = (915, 922, 890, 920)
    assert detect(frame([hammer_bar], lead="down"), atr=20)["pattern"] == "HAMMER"
    up = frame([(1085, 1092, 1060, 1090)], lead="up")
    assert detect(up, atr=20)["pattern"] == "HANGING_MAN"


def test_engulfing_both_directions_need_context_and_size():
    bull = frame([(925, 927, 905, 908), (905, 935, 903, 930)], lead="down")
    assert detect(bull, atr=20)["pattern"] == "BULLISH_ENGULFING"
    bear = frame([(1075, 1095, 1073, 1092), (1095, 1097, 1065, 1070)], lead="up")
    assert detect(bear, atr=20)["pattern"] == "BEARISH_ENGULFING"
    # the same bullish engulfing after an advance is not a reversal pattern
    no_ctx = frame([(1085, 1087, 1065, 1068), (1065, 1095, 1063, 1090)], lead="up")
    assert detect(no_ctx, atr=20)["pattern"] != "BULLISH_ENGULFING"
    # a tiny previous body (< 0.3 ATR) is not "engulfed"
    tiny = frame([(921, 923, 919, 920), (919, 935, 917, 930)], lead="down")
    assert detect(tiny, atr=20)["pattern"] != "BULLISH_ENGULFING"


def test_three_crows_and_soldiers():
    crows = frame([(1080, 1081, 1060, 1062), (1062, 1063, 1042, 1044), (1044, 1045, 1024, 1026)], lead="up")
    assert detect(crows, atr=20)["pattern"] == "THREE_BLACK_CROWS"
    soldiers = frame([(920, 939, 919, 938), (938, 957, 937, 956), (956, 975, 955, 974)], lead="down")
    assert detect(soldiers, atr=20)["pattern"] == "THREE_WHITE_SOLDIERS"


def test_plain_colour_is_labelled_as_colour_only():
    out = detect(frame([(920, 931, 918, 930)], lead="down"), atr=20)
    assert out["pattern"] == "BULLISH_BODY" and "bukan pola" in out["description"]
