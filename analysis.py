from datetime import datetime, timedelta


def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 1)


def calc_rvol(hist):
    if len(hist) < 21:
        return None
    avg = hist["Volume"].iloc[-21:-1].mean()
    today = hist["Volume"].iloc[-1]
    return round(today / avg, 2) if avg > 0 else None


def calc_atr(hist, period=14):
    if len(hist) < period + 1:
        return None
    trs = []
    for i in range(1, len(hist)):
        h = float(hist["High"].iloc[i])
        l = float(hist["Low"].iloc[i])
        pc = float(hist["Close"].iloc[i - 1])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return round(sum(trs[-period:]) / period, 2)


def get_trend(price, hist):
    closes = list(hist["Close"])
    ma50 = round(sum(closes[-50:]) / min(50, len(closes)), 2) if len(closes) >= 10 else None
    ma200 = round(sum(closes[-200:]) / min(200, len(closes)), 2) if len(closes) >= 50 else None
    return (
        ma50, ma200,
        price > ma50 if ma50 else None,
        price > ma200 if ma200 else None,
    )


def get_vol_structure(hist):
    if len(hist) < 10:
        return None, None, None
    r = hist.tail(10)
    up = r[r["Close"] > r["Open"]]
    dn = r[r["Close"] <= r["Open"]]
    avg_up = up["Volume"].mean() if len(up) else 0
    avg_dn = dn["Volume"].mean() if len(dn) else 1
    return round(avg_up), round(avg_dn), round(avg_up / avg_dn, 2) if avg_dn else None


def detect_catalysts(news_items):
    keywords = {
        "earnings": ["earnings", "eps", "revenue", "beat", "miss", "quarterly", "guidance"],
        "fda":      ["fda", "approval", "clinical", "trial", "drug", "nda", "bla", "pdufa"],
        "merger":   ["merger", "acquisition", "buyout", "takeover", "deal", "acquired"],
        "analyst":  ["upgrade", "downgrade", "price target", "analyst", "rating", "initiated"],
        "insider":  ["insider", "ceo", "cfo", "director", "officer", "bought", "purchased"],
        "contract": ["contract", "partnership", "agreement", "awarded", "won", "signed"],
    }
    found = set()
    for item in news_items:
        title = (item.get("title") or "").lower()
        for cat, kws in keywords.items():
            if any(k in title for k in kws):
                found.add(cat)
    return list(found)


def score_stock(d):
    bd = {}
    red_flags = []

    # Momentum (max 30)
    m = 0
    rsi = d.get("rsi") or 0
    if 55 <= rsi <= 72:    m += 15
    elif 40 <= rsi < 55:   m += 8
    elif rsi > 72:         m += 5
    elif rsi < 30:         m += 2
    else:                  m += 4

    chg = d.get("change_pct", 0)
    if chg >= 5:    m += 10
    elif chg >= 2:  m += 7
    elif chg >= 0:  m += 3
    elif chg >= -2: m += 1
    else:           m += 0

    gap = d.get("gap_pct", 0)
    if gap >= 3:   m += 5
    elif gap >= 1: m += 3
    elif gap < -2: m -= 3

    vol_ratio = d.get("vol_ratio") or 1
    if chg < 0 and vol_ratio < 1:
        m -= 5
        red_flags.append("Selling on above-avg volume")

    bd["momentum"] = max(min(m, 30), 0)

    # RVOL (max 25)
    rv = d.get("rvol") or 0
    if rv >= 3:     bd["rvol"] = 25
    elif rv >= 2:   bd["rvol"] = 18
    elif rv >= 1.5: bd["rvol"] = 12
    elif rv >= 1:   bd["rvol"] = 5
    elif rv >= 0.5: bd["rvol"] = 2
    else:           bd["rvol"] = 0

    # Catalyst (max 15)
    c = 0
    cats = d.get("catalysts", [])
    if "earnings" in cats: c += 8
    if "fda"      in cats: c += 10
    if "merger"   in cats: c += 10
    if "analyst"  in cats: c += 5
    if "contract" in cats: c += 6
    if "insider"  in cats: c += 4
    ins = len(d.get("insider_trades", []))
    if ins >= 2:   c += 5
    elif ins >= 1: c += 2
    bd["catalyst"] = min(c, 15)

    # Float (max 10)
    fl = (d.get("float_shares") or 0) / 1e6
    if 0 < fl < 20:  bd["float"] = 10
    elif fl < 50:    bd["float"] = 7
    elif fl < 100:   bd["float"] = 4
    elif fl > 0:     bd["float"] = 1
    else:            bd["float"] = 0

    # Trend (max 10)
    t = 0
    above50  = d.get("above_50ma")
    above200 = d.get("above_200ma")
    if above50  is True:   t += 5
    elif above50 is False: t -= 3
    if above200 is True:   t += 5
    elif above200 is False: t -= 3

    prox = d.get("week52_proximity_pct")
    if prox is not None:
        if prox <= 5:    t += 2
        elif prox <= 15: t += 1
        elif prox >= 50:
            t -= 3
            red_flags.append("More than 50% below 52W high")

    bd["trend"] = max(min(t, 10), -6)

    # Short squeeze (max 10)
    sp = d.get("short_pct_float") or 0
    dc = d.get("days_to_cover") or 0
    sq = 0
    if sp >= 30:   sq += 8
    elif sp >= 20: sq += 5
    elif sp >= 10: sq += 2
    if dc >= 5: sq += 2
    bd["squeeze"] = min(sq, 10)

    # Hard penalties
    penalties = 0
    if rsi > 80:
        penalties += 5
        red_flags.append("RSI overbought (>80) — chasing a top")
    if rsi < 25:
        penalties += 3
        red_flags.append("RSI extremely oversold — falling knife risk")
    if rv < 0.7:
        penalties += 5
        red_flags.append("Very low volume — no institutional interest")
    if above50 is False and above200 is False:
        penalties += 5
        red_flags.append("Below both MAs — confirmed downtrend")
    if chg <= -5:
        penalties += 5
        red_flags.append(f"Large down day ({chg:.1f}%) — momentum broken")
    if gap < -3:
        penalties += 3
        red_flags.append(f"Gap down ({gap:.1f}%) — sellers in control")

    total = max(sum(bd.values()) - penalties, 0)

    if total >= 72:   rating, color = "STRONG BUY",       "#4ade80"
    elif total >= 55: rating, color = "BUY",               "#86efac"
    elif total >= 38: rating, color = "NEUTRAL",           "#fbbf24"
    elif total >= 22: rating, color = "WEAK — HIGH RISK",  "#fb923c"
    else:             rating, color = "AVOID",             "#f87171"

    return {
        "total": total,
        "breakdown": bd,
        "penalties": penalties,
        "red_flags": red_flags,
        "rating": rating,
        "color": color,
    }


def _add_trading_days(start, n):
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def estimate_trade_plan(d, score, market=None):
    price     = d.get("price", 0)
    atr       = d.get("atr") or (price * 0.025)
    total     = score.get("total", 0)
    rvol      = d.get("rvol") or 1
    short_pct = d.get("short_pct_float") or 0
    above50   = d.get("above_50ma")
    above200  = d.get("above_200ma")
    rsi       = d.get("rsi") or 50
    chg       = d.get("change_pct", 0)
    mkt_mult  = (market or {}).get("return_multiplier", 1.0)

    if total >= 72:   conviction, hold_days = "High",     5
    elif total >= 55: conviction, hold_days = "Moderate", 4
    elif total >= 38: conviction, hold_days = "Low",      3
    else:             conviction, hold_days = "Very Low", 2

    if rvol < 1 or (above50 is False and above200 is False):
        hold_days = max(hold_days - 1, 2)

    entry_date = datetime.now()
    exit_date  = _add_trading_days(entry_date, hold_days)

    atr_pct   = (atr / price) if price else 0.025
    stop_loss = round(price - atr * 1.2, 2)
    stop_pct  = round((stop_loss - price) / price * 100, 1)

    bull_pct = round(min((total / 100) * 18 + (rvol - 1) * 2, 25), 1)
    if short_pct >= 20:
        bull_pct = round(min(bull_pct * 1.3, 35), 1)
    bull_pct = round(bull_pct * mkt_mult, 1)

    base_mult = 0.45 if (above50 is False or above200 is False) else 0.55
    base_pct  = round(bull_pct * base_mult, 1)

    bear_mkt = 1.0 + max(0, 1.0 - mkt_mult)
    if total < 38 or (above50 is False and above200 is False):
        bear_pct = round(-(atr_pct * 100 * 2.5 * bear_mkt), 1)
    elif rsi > 72 or chg >= 8:
        bear_pct = round(-(atr_pct * 100 * 2.0 * bear_mkt), 1)
    else:
        bear_pct = round(stop_pct * 1.1 * bear_mkt, 1)

    if total >= 72:   p_bull, p_base, p_bear = 40, 40, 20
    elif total >= 55: p_bull, p_base, p_bear = 30, 40, 30
    elif total >= 38: p_bull, p_base, p_bear = 20, 35, 45
    else:             p_bull, p_base, p_bear = 10, 25, 65

    ev       = round((p_bull/100)*bull_pct + (p_base/100)*base_pct + (p_bear/100)*bear_pct, 1)
    avg_win  = (bull_pct + base_pct) / 2
    avg_loss = abs(bear_pct)
    rr_ratio = round(avg_win / avg_loss, 2) if avg_loss else 0

    scenarios = [
        {
            "label": "Bull Case", "color": "#4ade80",
            "probability": p_bull, "gain_pct": bull_pct,
            "price_target": round(price * (1 + bull_pct / 100), 2),
            "description": "Momentum holds, volume stays elevated, no major resistance",
            "exit_date": _add_trading_days(entry_date, hold_days).strftime("%b %d"),
        },
        {
            "label": "Base Case", "color": "#fbbf24",
            "probability": p_base, "gain_pct": base_pct,
            "price_target": round(price * (1 + base_pct / 100), 2),
            "description": "Partial move then stall, exit at resistance",
            "exit_date": _add_trading_days(entry_date, max(hold_days - 1, 1)).strftime("%b %d"),
        },
        {
            "label": "Bear Case", "color": "#f87171",
            "probability": p_bear, "gain_pct": bear_pct,
            "price_target": round(price * (1 + bear_pct / 100), 2),
            "description": "Setup fails, stop triggered or trend reverses",
            "exit_date": _add_trading_days(entry_date, 2).strftime("%b %d"),
        },
    ]

    return {
        "entry_date":        entry_date.strftime("%b %d, %Y"),
        "recommended_exit":  exit_date.strftime("%b %d, %Y"),
        "hold_days":         hold_days,
        "stop_loss":         stop_loss,
        "stop_pct":          stop_pct,
        "conviction":        conviction,
        "rr_ratio":          rr_ratio,
        "expected_value":    ev,
        "scenarios":         scenarios,
        "base_bull_pct":     bull_pct,
        "base_base_pct":     base_pct,
        "base_bear_pct":     bear_pct,
        "market_multiplier": mkt_mult,
    }
