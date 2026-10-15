"""Market data: live from Yahoo Finance, with sample data as a fallback.

The fallback means the demo still works with no internet or if Yahoo is down.
"""

import logging
import math
from datetime import date, datetime

from agent.strategies import MarketData

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Approximate reference values used when live data is unavailable.
SAMPLE_DATA = {
    "AAPL": (230.0, 0.26, 0.004),
    "MSFT": (510.0, 0.24, 0.007),
    "NVDA": (180.0, 0.45, 0.0002),
    "AMZN": (225.0, 0.32, 0.0),
    "GOOGL": (200.0, 0.30, 0.004),
    "META": (720.0, 0.36, 0.003),
    "TSLA": (420.0, 0.58, 0.0),
    "JPM": (300.0, 0.24, 0.019),
    "MS": (150.0, 0.27, 0.025),
    "GS": (750.0, 0.28, 0.017),
    "NFLX": (1200.0, 0.38, 0.0),
    "AMD": (160.0, 0.50, 0.0),
    "SPY": (660.0, 0.16, 0.012),
    "QQQ": (590.0, 0.20, 0.006),
}

DEFAULT_SAMPLE = (100.0, 0.30, 0.0)


def sample_market_data(ticker, rate=0.04, skew=2.0):
    spot, vol, div = SAMPLE_DATA.get(ticker.upper(), DEFAULT_SAMPLE)
    note = "Sample data (approximate values)."
    if ticker.upper() not in SAMPLE_DATA:
        note = f"No sample data for {ticker}; using a generic $100 stock with 30% vol."
    return MarketData(ticker.upper(), spot, vol, rate, div, skew, "sample", note)


def _realized_vol(closes):
    import numpy as np

    returns = np.diff(np.log(closes))
    return float(np.std(returns) * math.sqrt(252))


def _atm_implied_vol(tk, spot, horizon_days):
    """ATM implied vol from the listed expiry closest to the horizon, or None."""
    import numpy as np

    expiries = tk.options
    if not expiries:
        return None, None
    today = date.today()

    def days_to(exp):
        return (datetime.strptime(exp, "%Y-%m-%d").date() - today).days

    usable = [e for e in expiries if days_to(e) >= 7]
    if not usable:
        return None, None
    expiry = min(usable, key=lambda e: abs(days_to(e) - horizon_days))
    chain = tk.option_chain(expiry)

    vols = []
    for table in (chain.calls, chain.puts):
        if table is None or table.empty:
            continue
        table = table.assign(dist=(table["strike"] - spot).abs()).sort_values("dist").head(2)
        for v in table["impliedVolatility"]:
            # Yahoo returns junk IVs outside market hours; keep sensible values only.
            if 0.05 < v < 2.5:
                vols.append(float(v))
    if not vols:
        return None, expiry
    return float(np.mean(vols)), expiry


def live_market_data(ticker, horizon_days=90, rate=0.04, skew=2.0):
    import yfinance as yf

    tk = yf.Ticker(ticker)
    hist = tk.history(period="1y")
    if hist is None or hist.empty:
        raise ValueError(f"No price history for {ticker}")
    closes = hist["Close"].dropna().values
    spot = float(closes[-1])
    realized = _realized_vol(closes[-63:]) if len(closes) > 63 else _realized_vol(closes)

    div = 0.0
    try:
        info_div = tk.info.get("dividendYield") or 0.0
        # Yahoo has switched between 0.5 and 0.005 formats over time.
        div = info_div / 100 if info_div > 0.2 else info_div
    except Exception:
        pass

    implied, expiry = None, None
    try:
        implied, expiry = _atm_implied_vol(tk, spot, horizon_days)
    except Exception:
        pass

    if implied:
        vol, note = implied, f"Live price; ATM implied vol from the {expiry} expiry."
    else:
        vol, note = realized, "Live price; 3-month realized vol (implied vol not available right now)."

    return MarketData(ticker.upper(), spot, vol, rate, div, skew, "live", note)


def get_market_data(ticker, horizon_days=90, rate=0.04, skew=2.0, use_live=True):
    if use_live:
        try:
            return live_market_data(ticker, horizon_days, rate, skew)
        except Exception as exc:
            md = sample_market_data(ticker, rate, skew)
            md.note = f"Live data unavailable ({type(exc).__name__}); using sample data."
            return md
    return sample_market_data(ticker, rate, skew)
