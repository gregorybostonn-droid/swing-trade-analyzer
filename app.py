from flask import Flask, render_template, request, jsonify
import yfinance as yf
import requests
import json
import os
from datetime import datetime, timedelta
app = Flask(__name__)
WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")

# ─── Helpers ────────────────────────────────────────────────────────────────

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


def score_stock(d):
    bd = {}
    red_flags = []

    # ── Momentum (max 30) ────────────────────────────────────────────────────
    m = 0
    rsi = d.get("rsi") or 0
    if 55 <= rsi <= 72:   m += 15
    elif 40 <= rsi < 55:  m += 8
    elif rsi > 72:        m += 5   # overbought — late entry risk
    elif rsi < 30:        m += 2   # very weak
    else:                 m += 4

    chg = d.get("change_pct", 0)
    if chg >= 5:     m += 10
    elif chg >= 2:   m += 7
    elif chg >= 0:   m += 3
    elif chg >= -2:  m += 1        # small red day
    else:            m += 0        # significant red day

    gap = d.get("gap_pct", 0)
    if gap >= 3:     m += 5
    elif gap >= 1:   m += 3
    elif gap < -2:   m -= 3        # gap down is a red flag

    # Penalty: down day on high volume = distribution
    vol_ratio = d.get("vol_ratio") or 1
    if chg < 0 and vol_ratio < 1:
        m -= 5
        red_flags.append("Selling on above-avg volume")

    bd["momentum"] = max(min(m, 30), 0)

    # ── RVOL (max 25) ────────────────────────────────────────────────────────
    rv = d.get("rvol") or 0
    if rv >= 3:     bd["rvol"] = 25
    elif rv >= 2:   bd["rvol"] = 18
    elif rv >= 1.5: bd["rvol"] = 12
    elif rv >= 1:   bd["rvol"] = 5
    elif rv >= 0.5: bd["rvol"] = 2
    else:           bd["rvol"] = 0   # essentially no volume

    # ── Catalyst (max 15) ────────────────────────────────────────────────────
    # Count only if catalysts detected — raw news count is not a catalyst
    c = 0
    cats = d.get("catalysts", [])
    if "earnings" in cats:   c += 8
    if "fda" in cats:        c += 10
    if "merger" in cats:     c += 10
    if "analyst" in cats:    c += 5
    if "contract" in cats:   c += 6
    if "insider" in cats:    c += 4
    ins = len(d.get("insider_trades", []))
    if ins >= 2:   c += 5
    elif ins >= 1: c += 2
    bd["catalyst"] = min(c, 15)

    # ── Float (max 10) ───────────────────────────────────────────────────────
    fl = (d.get("float_shares") or 0) / 1e6
    if 0 < fl < 20:   bd["float"] = 10
    elif fl < 50:      bd["float"] = 7
    elif fl < 100:     bd["float"] = 4
    elif fl > 0:       bd["float"] = 1
    else:              bd["float"] = 0

    # ── Trend (max 10) ───────────────────────────────────────────────────────
    t = 0
    above50  = d.get("above_50ma")
    above200 = d.get("above_200ma")
    if above50  is True:   t += 5
    elif above50 is False: t -= 3    # below 50 MA = counter-trend
    if above200 is True:   t += 5
    elif above200 is False: t -= 3   # below 200 MA = downtrend

    prox = d.get("week52_proximity_pct")
    if prox is not None:
        if prox <= 5:     t += 2
        elif prox <= 15:  t += 1
        elif prox >= 50:
            t -= 3
            red_flags.append("More than 50% below 52W high")

    bd["trend"] = max(min(t, 10), -6)

    # ── Short squeeze (max 10) ───────────────────────────────────────────────
    sp = d.get("short_pct_float") or 0
    dc = d.get("days_to_cover") or 0
    sq = 0
    if sp >= 30:   sq += 8
    elif sp >= 20: sq += 5
    elif sp >= 10: sq += 2
    if dc >= 5:    sq += 2
    bd["squeeze"] = min(sq, 10)

    # ── Hard red-flag penalties ───────────────────────────────────────────────
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

    raw_total = sum(bd.values()) - penalties
    total = max(raw_total, 0)

    if total >= 72:   rating, color = "STRONG BUY", "#4ade80"
    elif total >= 55: rating, color = "BUY", "#86efac"
    elif total >= 38: rating, color = "NEUTRAL", "#fbbf24"
    elif total >= 22: rating, color = "WEAK — HIGH RISK", "#fb923c"
    else:             rating, color = "AVOID", "#f87171"

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
    """Realistic trade plan with bull / base / bear scenarios."""
    price = d.get("price", 0)
    atr   = d.get("atr") or (price * 0.025)
    total = score.get("total", 0)
    rvol  = d.get("rvol") or 1
    short_pct = d.get("short_pct_float") or 0
    above50   = d.get("above_50ma")
    above200  = d.get("above_200ma")
    rsi       = d.get("rsi") or 50
    chg       = d.get("change_pct", 0)
    mkt_mult  = (market or {}).get("return_multiplier", 1.0)

    # ── Conviction & hold length ─────────────────────────────────────────────
    if total >= 72:
        conviction, hold_days = "High", 5
    elif total >= 55:
        conviction, hold_days = "Moderate", 4
    elif total >= 38:
        conviction, hold_days = "Low", 3
    else:
        conviction, hold_days = "Very Low", 2

    # Shorten hold for weak setups or low volume
    if rvol < 1 or (above50 is False and above200 is False):
        hold_days = max(hold_days - 1, 2)

    entry_date = datetime.now()
    exit_date  = _add_trading_days(entry_date, hold_days)

    # ── ATR-based price levels ───────────────────────────────────────────────
    atr_pct = (atr / price) if price else 0.025

    # Stop loss: always 1.2× ATR below entry (hard rule)
    stop_loss = round(price - atr * 1.2, 2)
    stop_pct  = round((stop_loss - price) / price * 100, 1)

    # ── Three scenarios ──────────────────────────────────────────────────────
    # Bull: momentum carries, volume stays elevated
    # Base: partial move, some resistance
    # Bear: setup fails, price returns to support / stop triggers

    # Bull gain scales with score, capped, then adjusted for market conditions
    bull_pct  = round(min((total / 100) * 18 + (rvol - 1) * 2, 25), 1)
    if short_pct >= 20:
        bull_pct = round(min(bull_pct * 1.3, 35), 1)
    bull_pct = round(bull_pct * mkt_mult, 1)

    # Base is partial bull, reduced if weak trend, also market-adjusted
    base_mult = 0.45 if (above50 is False or above200 is False) else 0.55
    base_pct  = round(bull_pct * base_mult, 1)

    # Bear: ATR-based downside — market weakness increases bear magnitude
    bear_mkt = 1.0 + max(0, 1.0 - mkt_mult)   # bear gets worse in bad markets
    if total < 38 or (above50 is False and above200 is False):
        bear_pct = round(-(atr_pct * 100 * 2.5 * bear_mkt), 1)
    elif rsi > 72 or chg >= 8:
        bear_pct = round(-(atr_pct * 100 * 2.0 * bear_mkt), 1)
    else:
        bear_pct = round(stop_pct * 1.1 * bear_mkt, 1)

    # Probabilities based on score (must sum to 100)
    if total >= 72:
        p_bull, p_base, p_bear = 40, 40, 20
    elif total >= 55:
        p_bull, p_base, p_bear = 30, 40, 30
    elif total >= 38:
        p_bull, p_base, p_bear = 20, 35, 45
    else:
        p_bull, p_base, p_bear = 10, 25, 65

    # Expected value
    ev = round((p_bull/100) * bull_pct + (p_base/100) * base_pct + (p_bear/100) * bear_pct, 1)

    # Risk/reward
    avg_win  = (bull_pct + base_pct) / 2
    avg_loss = abs(bear_pct)
    rr_ratio = round(avg_win / avg_loss, 2) if avg_loss else 0

    scenarios = [
        {
            "label": "Bull Case",
            "color": "#4ade80",
            "probability": p_bull,
            "gain_pct": bull_pct,
            "price_target": round(price * (1 + bull_pct / 100), 2),
            "description": "Momentum holds, volume stays elevated, no major resistance",
            "exit_date": _add_trading_days(entry_date, hold_days).strftime("%b %d"),
        },
        {
            "label": "Base Case",
            "color": "#fbbf24",
            "probability": p_base,
            "gain_pct": base_pct,
            "price_target": round(price * (1 + base_pct / 100), 2),
            "description": "Partial move then stall, exit at resistance",
            "exit_date": _add_trading_days(entry_date, max(hold_days - 1, 1)).strftime("%b %d"),
        },
        {
            "label": "Bear Case",
            "color": "#f87171",
            "probability": p_bear,
            "gain_pct": bear_pct,
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


def get_market_conditions():
    """Fetch SPY + VIX to assess current macro environment and return a multiplier."""
    try:
        spy_hist = yf.Ticker("SPY").history(period="1y")
        vix_hist = yf.Ticker("^VIX").history(period="5d")
        qqq_hist = yf.Ticker("QQQ").history(period="3mo")

        spy_closes  = list(spy_hist["Close"])
        spy_price   = spy_closes[-1]
        spy_ma50    = round(sum(spy_closes[-50:])  / min(50,  len(spy_closes)), 2)
        spy_ma200   = round(sum(spy_closes[-200:]) / min(200, len(spy_closes)), 2)
        spy_rsi     = calc_rsi(spy_closes)
        spy_rvol    = calc_rvol(spy_hist)
        spy_chg     = round((spy_closes[-1] - spy_closes[-2]) / spy_closes[-2] * 100, 2) if len(spy_closes) > 1 else 0

        vix = round(float(vix_hist["Close"].iloc[-1]), 2) if not vix_hist.empty else 20.0

        # QQQ trend (tech sector proxy for small/mid growth stocks)
        qqq_closes = list(qqq_hist["Close"])
        qqq_chg_1m = round((qqq_closes[-1] - qqq_closes[0]) / qqq_closes[0] * 100, 1) if len(qqq_closes) > 1 else 0

        above_50  = spy_price > spy_ma50
        above_200 = spy_price > spy_ma200

        # Trend label + base return multiplier
        if above_50 and above_200 and spy_rsi and spy_rsi >= 55:
            trend, trend_mult, trend_color = "Strong Bull", 1.25, "#4ade80"
        elif above_50 and above_200:
            trend, trend_mult, trend_color = "Bull",         1.10, "#86efac"
        elif above_200:
            trend, trend_mult, trend_color = "Neutral",      1.00, "#fbbf24"
        elif above_50:
            trend, trend_mult, trend_color = "Caution",      0.85, "#fb923c"
        else:
            trend, trend_mult, trend_color = "Bear",         0.65, "#f87171"

        # VIX label + volatility multiplier (high VIX = wider swings both ways)
        if vix >= 35:
            vix_label, vix_mult = "Extreme Fear", 1.40
        elif vix >= 25:
            vix_label, vix_mult = "High Fear",    1.20
        elif vix >= 18:
            vix_label, vix_mult = "Elevated",     1.05
        elif vix <= 13:
            vix_label, vix_mult = "Complacent",   0.85
        else:
            vix_label, vix_mult = "Normal",       1.00

        combined_mult = round(trend_mult * vix_mult, 3)

        return {
            "spy_price":        round(spy_price, 2),
            "spy_ma50":         spy_ma50,
            "spy_ma200":        spy_ma200,
            "spy_rsi":          spy_rsi,
            "spy_rvol":         spy_rvol,
            "spy_chg":          spy_chg,
            "qqq_chg_1m":       qqq_chg_1m,
            "vix":              vix,
            "vix_label":        vix_label,
            "trend":            trend,
            "trend_color":      trend_color,
            "above_50":         above_50,
            "above_200":        above_200,
            "return_multiplier": combined_mult,
        }
    except Exception as e:
        return {
            "trend": "Unknown", "trend_color": "#7c8db5",
            "vix": None, "vix_label": "N/A",
            "return_multiplier": 1.0,
            "spy_price": None, "spy_rsi": None, "spy_rvol": None,
            "spy_chg": None, "qqq_chg_1m": None,
            "above_50": None, "above_200": None,
        }


def get_insider_trades(ticker):
    try:
        start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        end   = datetime.now().strftime("%Y-%m-%d")
        url = (
            f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22"
            f"&forms=4&dateRange=custom&startdt={start}&enddt={end}"
        )
        r = requests.get(url, headers={"User-Agent": "SwingAnalyzer app@example.com"}, timeout=10)
        hits = r.json().get("hits", {}).get("hits", [])
        out = []
        for h in hits[:8]:
            s = h.get("_source", {})
            names = s.get("display_names", [])
            out.append({
                "date": s.get("file_date", "N/A"),
                "name": names[0] if names else "Unknown",
                "form": s.get("form_type", "4"),
            })
        return out
    except:
        return []


def detect_catalysts(news_items):
    keywords = {
        "earnings": ["earnings", "eps", "revenue", "beat", "miss", "quarterly", "guidance"],
        "fda": ["fda", "approval", "clinical", "trial", "drug", "nda", "bla", "pdufa"],
        "merger": ["merger", "acquisition", "buyout", "takeover", "deal", "acquired"],
        "analyst": ["upgrade", "downgrade", "price target", "analyst", "rating", "initiated"],
        "insider": ["insider", "ceo", "cfo", "director", "officer", "bought", "purchased"],
        "contract": ["contract", "partnership", "agreement", "awarded", "won", "signed"],
    }
    found = set()
    for item in news_items:
        title = (item.get("title") or "").lower()
        for cat, kws in keywords.items():
            if any(k in title for k in kws):
                found.add(cat)
    return list(found)


# ─── Main data fetch ─────────────────────────────────────────────────────────

def get_stock_data(ticker):
    try:
        stock  = yf.Ticker(ticker)
        info   = stock.info
        hist1y = stock.history(period="1y")
        hist3m = stock.history(period="3mo")
        news   = stock.news or []

        if hist1y.empty:
            return {"success": False, "error": f"No data found for '{ticker}'."}

        closes = list(hist1y["Close"])
        price      = float(info.get("currentPrice") or info.get("regularMarketPrice") or closes[-1])
        prev_close = float(info.get("previousClose") or (closes[-2] if len(closes) > 1 else price))
        open_price = float(info.get("open") or info.get("regularMarketOpen") or price)

        change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
        gap_pct    = round((open_price - prev_close) / prev_close * 100, 2) if prev_close else 0

        rsi  = calc_rsi(closes)
        rvol = calc_rvol(hist1y)
        atr  = calc_atr(hist1y)
        ma50, ma200, a50, a200 = get_trend(price, hist1y)
        avg_up, avg_dn, vol_ratio = get_vol_structure(hist1y)

        week_high = float(info.get("fiftyTwoWeekHigh") or max(hist1y["High"]))
        week_low  = float(info.get("fiftyTwoWeekLow")  or min(hist1y["Low"]))
        prox52    = round((week_high - price) / week_high * 100, 1) if week_high else None

        float_sh  = info.get("floatShares")
        short_pct = info.get("shortPercentOfFloat")
        short_rat = info.get("shortRatio")

        news_items = []
        for n in news[:10]:
            c     = n.get("content", {})
            title = c.get("title", "") if isinstance(c, dict) else n.get("title", "")
            pub   = c.get("pubDate", "") if isinstance(c, dict) else ""
            prov  = c.get("provider", {}) if isinstance(c, dict) else {}
            src   = prov.get("displayName", "") if isinstance(prov, dict) else ""
            link  = c.get("canonicalUrl", {}) if isinstance(c, dict) else {}
            url   = link.get("url", "") if isinstance(link, dict) else ""
            if title:
                news_items.append({"title": title, "date": str(pub)[:10], "source": src, "url": url})

        chart = []
        for dt, row in hist3m.iterrows():
            chart.append({
                "date": dt.strftime("%b %d"),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })

        insiders  = get_insider_trades(ticker)
        catalysts = detect_catalysts(news_items)

        mcap = info.get("marketCap", 0)
        if mcap < 300e6:   cap_tier = "Micro Cap"
        elif mcap < 2e9:   cap_tier = "Small Cap"
        elif mcap < 10e9:  cap_tier = "Mid Cap"
        else:              cap_tier = "Large Cap"

        d = {
            "success": True,
            "ticker": ticker.upper(),
            "name": info.get("longName", ticker.upper()),
            "price": round(price, 2),
            "change_pct": change_pct,
            "gap_pct": gap_pct,
            "open_price": round(open_price, 2),
            "prev_close": round(prev_close, 2),
            "market_cap": mcap,
            "cap_tier": cap_tier,
            "volume": info.get("volume") or int(hist1y["Volume"].iloc[-1]),
            "avg_volume": info.get("averageVolume", 0),
            "rvol": rvol,
            "rsi": rsi,
            "atr": atr,
            "ma50": ma50, "ma200": ma200,
            "above_50ma": a50, "above_200ma": a200,
            "week_high": round(week_high, 2),
            "week_low": round(week_low, 2),
            "week52_proximity_pct": prox52,
            "float_shares": float_sh,
            "short_pct_float": round(short_pct * 100, 1) if short_pct else None,
            "days_to_cover": round(short_rat, 1) if short_rat else None,
            "borrow_fee": None,
            "utilization": None,
            "pe_ratio": round(info.get("trailingPE", 0) or 0, 2),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "description": (info.get("longBusinessSummary", "") or "")[:400] + "...",
            "analyst_count": info.get("numberOfAnalystOpinions", 0),
            "recommendation": (info.get("recommendationKey", "N/A") or "N/A").upper(),
            "target_price": round(info.get("targetMeanPrice", 0) or 0, 2),
            "avg_up_vol": avg_up, "avg_dn_vol": avg_dn, "vol_ratio": vol_ratio,
            "news": news_items,
            "chart": chart,
            "insider_trades": insiders,
            "catalysts": catalysts,
        }
        d["score"] = score_stock(d)
        d["market"] = get_market_conditions()
        d["trade_plan"] = estimate_trade_plan(d, d["score"], d["market"])
        return d
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Watchlist ───────────────────────────────────────────────────────────────

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE) as f:
            return json.load(f)
    return []


def save_watchlist(wl):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(wl, f)


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data   = request.json
    ticker = data.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"success": False, "error": "Please enter a ticker symbol"})
    return jsonify(get_stock_data(ticker))


@app.route("/watchlist", methods=["GET"])
def get_watchlist():
    return jsonify(load_watchlist())


@app.route("/watchlist/add", methods=["POST"])
def add_to_watchlist():
    ticker = (request.json.get("ticker") or "").strip().upper()
    note = request.json.get("note", "")
    if not ticker:
        return jsonify({"success": False})
    wl = load_watchlist()
    if not any(w["ticker"] == ticker for w in wl):
        wl.append({"ticker": ticker, "note": note, "added": datetime.now().strftime("%Y-%m-%d")})
        save_watchlist(wl)
    return jsonify({"success": True, "watchlist": wl})


@app.route("/watchlist/remove", methods=["POST"])
def remove_from_watchlist():
    ticker = (request.json.get("ticker") or "").strip().upper()
    wl = [w for w in load_watchlist() if w["ticker"] != ticker]
    save_watchlist(wl)
    return jsonify({"success": True, "watchlist": wl})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
