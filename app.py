import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from flask import Flask, jsonify, render_template, request
from flask_caching import Cache

from data import get_stock_data, load_watchlist, save_watchlist

app = Flask(__name__)
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 900})

TSX_TICKERS = [
    # Banks & Insurance
    "RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO", "MFC.TO", "SLF.TO",
    "GWO.TO", "IFC.TO", "FFH.TO", "POW.TO",
    # Energy
    "ENB.TO", "TRP.TO", "SU.TO", "CVE.TO", "IMO.TO", "ARX.TO", "PEY.TO",
    "CPG.TO", "BTE.TO", "TVE.TO", "VET.TO", "PSK.TO", "ERF.TO", "MEG.TO",
    # Mining & Materials
    "ABX.TO", "AEM.TO", "AGI.TO", "K.TO", "WPM.TO", "FNV.TO", "OR.TO",
    "ERO.TO", "LUN.TO", "FM.TO", "HBM.TO", "TXG.TO", "CS.TO", "NGT.TO", "CG.TO",
    # Uranium
    "CCO.TO", "NXE.TO", "DML.TO", "FCU.TO", "URE.TO",
    # Rail & Transport
    "CNR.TO", "CP.TO", "TFII.TO", "AC.TO",
    # Tech
    "SHOP.TO", "CSU.TO", "OTEX.TO", "CGI.TO", "BB.TO", "KXS.TO",
    "TOI.TO", "ENGH.TO", "DCBO.TO", "DSG.TO", "MDA.TO", "CLS.TO",
    # Telecom
    "BCE.TO", "T.TO", "RCI-B.TO",
    # Cannabis
    "WEED.TO", "ACB.TO", "CRON.TO",
    # Infrastructure & Utilities
    "BAM.TO", "NPI.TO", "INE.TO", "BLX.TO", "RNW.TO",
    # REITs
    "CAR-UN.TO", "REI-UN.TO", "HR-UN.TO", "FCR-UN.TO",
    # Consumer & Retail
    "ATD.TO", "DOL.TO", "L.TO", "MRU.TO", "CTC-A.TO", "EMP-A.TO",
    # Industrials
    "WSP.TO", "STN.TO", "CAE.TO", "GFL.TO", "WCN.TO", "SJ.TO", "TIH.TO",
    # Agriculture
    "NTR.TO", "AGT.TO",
    # Media & Info
    "TRI.TO", "QBR-B.TO",
    # Diversified
    "RFP.TO", "CFP.TO", "WEF.TO", "IFP.TO", "GUD.TO", "WELL.TO",
]


def sanitize_ticker(raw):
    """Allow only alphanumeric, dots, and hyphens — the valid chars in a ticker."""
    return re.sub(r"[^A-Z0-9.\-]", "", (raw or "").upper())[:10]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    ticker = sanitize_ticker((request.json or {}).get("ticker", "").strip())
    if not ticker:
        return jsonify({"success": False, "error": "Please enter a ticker symbol"})

    cache_key = f"stock_{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)

    result = get_stock_data(ticker)
    if result.get("success"):
        cache.set(cache_key, result)
    return jsonify(result)


SCAN_UNIVERSE = [
    # US — high-momentum small/mid cap
    "NVDA", "AMD", "TSLA", "MSTR", "COIN", "PLTR", "SMCI", "IONQ", "RKLB",
    "HOOD", "SOFI", "UPST", "AFRM", "DKNG", "CRWD", "SNOW", "DDOG", "NET",
    "PANW", "ZS", "UBER", "DASH", "SQ", "PYPL", "ROKU", "SPOT", "TTD",
    "SHOP", "ABNB", "LYFT", "RIVN", "JOBY", "ACHR", "LUNR", "RDW",
    # TSX — most liquid momentum names
    "SHOP.TO", "CSU.TO", "AEM.TO", "WPM.TO", "FNV.TO", "CCO.TO", "NXE.TO",
    "ARX.TO", "TVE.TO", "MEG.TO", "FM.TO", "HBM.TO", "CLS.TO", "MDA.TO",
    "DCBO.TO", "WELL.TO", "GUD.TO", "BAM.TO", "ATD.TO", "DOL.TO",
    "WSP.TO", "GFL.TO", "CAE.TO", "AC.TO", "SU.TO", "CVE.TO",
]


@app.route("/scan")
def scan():
    min_score = int(request.args.get("min_score", 70))
    results = []

    def fetch(ticker):
        key = f"stock_{ticker}"
        cached = cache.get(key)
        if cached:
            return cached
        d = get_stock_data(ticker)
        if d.get("success"):
            cache.set(key, d)
        return d

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch, t): t for t in SCAN_UNIVERSE}
        for future in as_completed(futures):
            d = future.result()
            if d.get("success") and d.get("score", {}).get("total", 0) >= min_score:
                results.append({
                    "ticker":     d["ticker"],
                    "name":       d["name"],
                    "score":      d["score"]["total"],
                    "rating":     d["score"]["rating"],
                    "color":      d["score"]["color"],
                    "price":      d["price"],
                    "change_pct": d["change_pct"],
                    "rvol":       d["rvol"],
                    "rsi":        d["rsi"],
                    "sector":     d["sector"],
                    "cap_tier":   d["cap_tier"],
                })

    results.sort(key=lambda x: x["score"], reverse=True)
    return jsonify({"success": True, "results": results, "scanned": len(SCAN_UNIVERSE)})


@app.route("/random-tsx")
def random_tsx():
    return jsonify({"ticker": random.choice(TSX_TICKERS)})


@app.route("/watchlist", methods=["GET"])
def get_watchlist():
    return jsonify(load_watchlist())


@app.route("/watchlist/add", methods=["POST"])
def add_to_watchlist():
    ticker = sanitize_ticker((request.json or {}).get("ticker", ""))
    note   = (request.json or {}).get("note", "")
    if not ticker:
        return jsonify({"success": False, "error": "Invalid ticker"})
    wl = load_watchlist()
    if not any(w["ticker"] == ticker for w in wl):
        wl.append({"ticker": ticker, "note": note, "added": datetime.now().strftime("%Y-%m-%d")})
        save_watchlist(wl)
    return jsonify({"success": True, "watchlist": wl})


@app.route("/watchlist/remove", methods=["POST"])
def remove_from_watchlist():
    ticker = sanitize_ticker((request.json or {}).get("ticker", ""))
    wl = [w for w in load_watchlist() if w["ticker"] != ticker]
    save_watchlist(wl)
    return jsonify({"success": True, "watchlist": wl})


if __name__ == "__main__":
    app.run(debug=False, port=5000)
