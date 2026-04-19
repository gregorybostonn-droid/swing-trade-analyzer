# SwingEdge — Swing Trade Analyzer

A Flask web app for analyzing small and mid-cap stocks for swing trading. All analysis is done in-house using raw price/volume data — no third-party ratings.

## What it does

- Calculates RSI, RVOL, ATR, 50/200-day MAs from raw Yahoo Finance data
- Scores stocks across 6 categories: Momentum, RVOL, Catalyst, Float, Trend, Short Squeeze
- Generates Bull / Base / Bear trade scenarios with ATR-based price targets
- Fetches insider trades directly from the SEC EDGAR API
- Pulls live SPY / VIX / QQQ market conditions and adjusts return forecasts
- Detects catalysts (earnings, FDA, merger, analyst, insider, contract) from news headlines
- Random TSX ticker button for exploring Canadian stocks

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser.

## Project structure

```
app.py          # Flask routes
analysis.py     # Scoring, RSI/RVOL/ATR calculations, trade plan logic
data.py         # yfinance + SEC EDGAR data fetching
static/main.js  # Frontend JavaScript
templates/      # HTML template
requirements.txt
```

## Notes

- Analysis results are cached for 15 minutes to avoid API rate limits
- Ticker input is sanitized — only alphanumeric, dots, and hyphens accepted
- Canadian stocks use the `.TO` suffix (e.g. `SHOP.TO`)
- Borrow fee and utilization data require a live broker feed — not available via Yahoo Finance
