import json
import os
from datetime import datetime, timedelta

import requests
import yfinance as yf

from analysis import (
    calc_atr, calc_rsi, calc_rvol, detect_catalysts,
    estimate_trade_plan, get_trend, get_vol_structure, score_stock,
)

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")


def get_market_conditions():
    try:
        spy_hist = yf.Ticker("SPY").history(period="1y")
        vix_hist = yf.Ticker("^VIX").history(period="5d")
        qqq_hist = yf.Ticker("QQQ").history(period="3mo")

        if spy_hist.empty:
            raise ValueError("SPY data unavailable")

        spy_closes = list(spy_hist["Close"])
        spy_price  = spy_closes[-1]
        spy_ma50   = round(sum(spy_closes[-50:])  / min(50,  len(spy_closes)), 2)
        spy_ma200  = round(sum(spy_closes[-200:]) / min(200, len(spy_closes)), 2)
        spy_rsi    = calc_rsi(spy_closes)
        spy_rvol   = calc_rvol(spy_hist)
        spy_chg    = round((spy_closes[-1] - spy_closes[-2]) / spy_closes[-2] * 100, 2) if len(spy_closes) > 1 else 0

        vix = round(float(vix_hist["Close"].iloc[-1]), 2) if not vix_hist.empty else 20.0

        qqq_closes  = list(qqq_hist["Close"]) if not qqq_hist.empty else []
        qqq_chg_1m  = round((qqq_closes[-1] - qqq_closes[0]) / qqq_closes[0] * 100, 1) if len(qqq_closes) > 1 else 0

        above_50  = spy_price > spy_ma50
        above_200 = spy_price > spy_ma200

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

        if vix >= 35:   vix_label, vix_mult = "Extreme Fear", 1.40
        elif vix >= 25: vix_label, vix_mult = "High Fear",    1.20
        elif vix >= 18: vix_label, vix_mult = "Elevated",     1.05
        elif vix <= 13: vix_label, vix_mult = "Complacent",   0.85
        else:           vix_label, vix_mult = "Normal",       1.00

        combined_mult = round(trend_mult * vix_mult, 3)

        parts = []
        if above_50 and above_200:
            parts.append(
                f"SPY is trading above both its 50-day (${spy_ma50:,.0f}) and 200-day (${spy_ma200:,.0f}) "
                f"moving averages, confirming a broad market uptrend that typically supports swing setups."
            )
        elif above_200:
            parts.append(
                f"SPY is above its 200-day MA (${spy_ma200:,.0f}) but has pulled back below the 50-day, "
                f"suggesting the longer-term trend is intact but short-term momentum is weakening."
            )
        elif above_50:
            parts.append(
                f"SPY is below its 200-day MA (${spy_ma200:,.0f}), signaling the broad market is in a "
                f"longer-term downtrend — swing trades carry extra risk in this environment."
            )
        else:
            parts.append(
                f"SPY is trading below both moving averages (50d: ${spy_ma50:,.0f}, 200d: ${spy_ma200:,.0f}), "
                f"indicating a confirmed bear market — most setups will face strong headwinds."
            )

        if vix >= 30:
            parts.append(
                f"The VIX at {vix} reflects extreme fear — volatility is elevated, creating larger move "
                f"potential in both directions but also sharper, faster reversals."
            )
        elif vix >= 20:
            parts.append(
                f"The VIX at {vix} is elevated above normal, meaning stocks are experiencing wider daily "
                f"swings — size positions accordingly to manage risk."
            )
        elif vix <= 14:
            parts.append(
                f"The VIX at {vix} is historically low, suggesting market complacency — low volatility "
                f"environments can compress swing trade returns until a catalyst breaks the range."
            )
        else:
            parts.append(
                f"The VIX at {vix} ({vix_label.lower()}) reflects balanced risk sentiment, "
                f"a reasonable environment for swing trades with defined stops."
            )

        if spy_rsi and spy_rsi > 70:
            parts.append(
                f"SPY's RSI of {spy_rsi} is overbought, which may limit near-term upside — "
                f"a market pullback could pressure even strong setups."
            )
        elif spy_rsi and spy_rsi < 40:
            parts.append(
                f"SPY's RSI of {spy_rsi} is oversold, suggesting a near-term bounce is possible "
                f"which could provide a tailwind for momentum setups."
            )
        elif qqq_chg_1m > 5:
            parts.append(
                f"QQQ has gained {qqq_chg_1m}% over the past month, showing strong growth and tech "
                f"momentum that often carries small and mid-cap stocks higher."
            )
        elif qqq_chg_1m < -5:
            parts.append(
                f"QQQ has fallen {abs(qqq_chg_1m)}% over the past month — growth stocks are under "
                f"pressure, which increases the probability of bear-case outcomes for swing setups."
            )

        return {
            "spy_price":         round(spy_price, 2),
            "spy_ma50":          spy_ma50,
            "spy_ma200":         spy_ma200,
            "spy_rsi":           spy_rsi,
            "spy_rvol":          spy_rvol,
            "spy_chg":           spy_chg,
            "qqq_chg_1m":        qqq_chg_1m,
            "vix":               vix,
            "vix_label":         vix_label,
            "trend":             trend,
            "trend_color":       trend_color,
            "above_50":          above_50,
            "above_200":         above_200,
            "return_multiplier": combined_mult,
            "summary":           " ".join(parts[:3]),
        }
    except Exception:
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
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
        out = []
        for h in hits[:8]:
            s     = h.get("_source", {})
            names = s.get("display_names", [])
            out.append({
                "date": s.get("file_date", "N/A"),
                "name": names[0] if names else "Unknown",
                "form": s.get("form_type", "4"),
            })
        return out
    except Exception:
        return []


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
        ma50, ma200, a50, a200       = get_trend(price, hist1y)
        avg_up, avg_dn, vol_ratio    = get_vol_structure(hist1y)

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
                "date":   dt.strftime("%b %d"),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })

        insiders  = get_insider_trades(ticker)
        catalysts = detect_catalysts(news_items)

        mcap = info.get("marketCap", 0)
        if mcap < 300e6:  cap_tier = "Micro Cap"
        elif mcap < 2e9:  cap_tier = "Small Cap"
        elif mcap < 10e9: cap_tier = "Mid Cap"
        else:             cap_tier = "Large Cap"

        d = {
            "success":    True,
            "ticker":     ticker.upper(),
            "name":       info.get("longName", ticker.upper()),
            "price":      round(price, 2),
            "change_pct": change_pct,
            "gap_pct":    gap_pct,
            "open_price": round(open_price, 2),
            "prev_close": round(prev_close, 2),
            "market_cap": mcap,
            "cap_tier":   cap_tier,
            "volume":     info.get("volume") or int(hist1y["Volume"].iloc[-1]),
            "avg_volume": info.get("averageVolume", 0),
            "rvol":       rvol,
            "rsi":        rsi,
            "atr":        atr,
            "ma50":  ma50,  "ma200":     ma200,
            "above_50ma": a50, "above_200ma": a200,
            "week_high":  round(week_high, 2),
            "week_low":   round(week_low, 2),
            "week52_proximity_pct": prox52,
            "float_shares":    float_sh,
            "short_pct_float": round(short_pct * 100, 1) if short_pct else None,
            "days_to_cover":   round(short_rat, 1) if short_rat else None,
            "borrow_fee":      None,
            "utilization":     None,
            "pe_ratio":        round(info.get("trailingPE", 0) or 0, 2),
            "sector":          info.get("sector", "N/A"),
            "industry":        info.get("industry", "N/A"),
            "description":     (info.get("longBusinessSummary", "") or "")[:400] + "...",
            "analyst_count":   info.get("numberOfAnalystOpinions", 0),
            "recommendation":  (info.get("recommendationKey", "N/A") or "N/A").upper(),
            "target_price":    round(info.get("targetMeanPrice", 0) or 0, 2),
            "avg_up_vol": avg_up, "avg_dn_vol": avg_dn, "vol_ratio": vol_ratio,
            "news":          news_items,
            "chart":         chart,
            "insider_trades": insiders,
            "catalysts":     catalysts,
        }
        d["score"]      = score_stock(d)
        d["market"]     = get_market_conditions()
        d["trade_plan"] = estimate_trade_plan(d, d["score"], d["market"])
        return d
    except Exception as e:
        return {"success": False, "error": str(e)}


def load_watchlist():
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_watchlist(wl):
    try:
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(wl, f)
    except Exception:
        pass
