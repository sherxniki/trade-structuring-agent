"""Trade Structuring Agent — web server with no outside packages.

Serves the page in web/ and one JSON endpoint that runs the agent:
read the view → get market data → design and price trades → explain.

Run locally:  python3 server.py   (then open http://localhost:8080)
"""

import json
import math
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # find agent/ however the server is started

from agent import view_parser  # noqa: E402
from agent.market import SAMPLE_DATA, get_market_data  # noqa: E402
from agent.recommender import build_plan, horizon_text  # noqa: E402

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
HOSTED = bool(os.environ.get("WORKSHOP_RUN_TOKEN"))   # running on the class app store

FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/charts.js": ("charts.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}

EXAMPLES = [
    "I think Apple goes up a bit over the next 3 months, and I don't want to spend much",
    "NVDA will rally hard after earnings next month",
    "I think the S&P stays flat for the next 6 weeks",
    "Netflix will make a big move after earnings but I'm not sure which way",
    "I own Microsoft shares and want protection for 2 months at zero cost",
    "Tesla drops 15% by the end of the year",
]

SPOT_MOVES = [-0.20, -0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10, 0.20]
VOL_MOVES = [10, 5, 0, -5, -10]   # vol points, top row first


def live_data_possible():
    """Live prices need yfinance and the internet, so only offer them locally."""
    if HOSTED:
        return False
    try:
        import yfinance  # noqa: F401
        return True
    except ImportError:
        return False


def finite(x, digits=2):
    if x is None or (isinstance(x, float) and math.isinf(x)):
        return None
    return round(float(x), digits)


def clamp(value, low, high, default):
    try:
        return min(max(float(value), low), high)
    except (TypeError, ValueError):
        return default


# ---------------- run the agent ----------------

def build(payload):
    text = str(payload.get("text", "")).strip()
    if not text:
        raise ValueError("Type a market view first.")
    if len(text) > 1000:
        raise ValueError("Keep the view under 1,000 characters.")

    default_ticker = payload.get("defaultTicker")
    if default_ticker not in SAMPLE_DATA:
        default_ticker = "AAPL"
    rate = clamp(payload.get("rate"), 0.0, 8.0, 4.0) / 100
    skew = clamp(payload.get("skew"), 0.0, 6.0, 2.0)
    use_ai = bool(payload.get("useAI", True))
    use_live = bool(payload.get("live")) and live_data_possible()

    view = view_parser.parse_view(text, default_ticker, use_llm=use_ai)
    md = get_market_data(view.ticker, view.horizon_days, rate, skew, use_live=use_live)
    plan = build_plan(view, md)

    explained_by = "template"
    if use_ai and view_parser.llm_available():
        try:
            plan.explanation = view_parser.explain_with_llm(view, md, plan.ranked[0], plan.ranked[1:])
            explained_by = "ai"
        except Exception:
            pass   # keep the template explanation
    return plan_to_json(plan, explained_by)


def plan_to_json(plan, explained_by):
    view, md, T = plan.view, plan.market, plan.T

    # price range for the payoff charts
    width = max(2.5 * plan.expected_move, abs(plan.target_price - md.spot) * 1.8, md.spot * 0.08)
    lo, hi = max(md.spot - width, md.spot * 0.2), md.spot + width
    xs = [lo + (hi - lo) * i / 160 for i in range(161)]

    # days-forward choices for the scenario grid
    h = view.horizon_days
    days = sorted({0, round(h * 0.25), round(h * 0.5), round(h * 0.75), max(h - 1, 0)})

    strategies = []
    for i, s in enumerate(plan.ranked):
        m = s.metrics
        legs = []
        for leg in s.legs:
            if leg.kind == "stock":
                legs.append({"label": leg.label(), "strike": None, "vol": None, "price": round(md.spot, 2)})
            else:
                legs.append({
                    "label": leg.label(),
                    "strike": leg.strike,
                    "vol": round(md.vol_for_strike(leg.strike), 4),
                    "price": round(s.leg_value(leg, md, md.spot, T), 2),
                })
        strategies.append({
            "name": s.name,
            "summary": s.summary,
            "best": i == 0,
            "score": round(plan.scores[s.name], 2),
            "legs": legs,
            "metrics": {
                "netPremium": finite(m["net_premium"]),
                "maxGain": finite(m["max_gain"]),
                "maxLoss": finite(m["max_loss"]),
                "breakevens": m["breakevens"][:2],
                "probProfit": round(m["prob_profit"], 4),
                "pnlIfRight": finite(m["pnl_at_target"]),
                "limitedRisk": m["limited_risk"],
            },
            "greeks": {k: round(v, 2) for k, v in s.greeks(md, T).items()},
            "expiry": [round(s.pnl_at_expiry(md, T, x), 2) for x in xs],
            "today": [round(s.pnl(md, T, x), 2) for x in xs],
            "grids": {
                str(d): [[round(s.pnl(md, T, md.spot * (1 + sm), days_forward=d, vol_shift=vm / 100))
                          for sm in SPOT_MOVES] for vm in VOL_MOVES]
                for d in days
            },
        })

    return {
        "view": {**view.to_dict(), "horizonText": horizon_text(view.horizon_days)},
        "market": {"ticker": md.ticker, "spot": round(md.spot, 2), "atmVol": round(md.atm_vol, 4),
                   "source": md.source, "note": md.note},
        "expectedMove": round(plan.expected_move, 2),
        "targetPrice": round(plan.target_price, 2),
        "downsidePrice": round(plan.downside_price, 2),
        "explanation": plan.explanation,
        "explainedBy": explained_by,
        "x": [round(x, 2) for x in xs],
        "stockOnly": [round((x - md.spot) * 100, 2) for x in xs] if view.direction == "hedge" else None,
        "spotMoves": SPOT_MOVES,
        "volMoves": VOL_MOVES,
        "days": days,
        "strategies": strategies,
    }


# ---------------- HTTP ----------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass   # keep logs quiet

    def reply(self, body, content_type="application/json", status=200):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self.reply(b"ok", "text/plain")
        if path == "/api/meta":
            return self.reply({
                "ai": view_parser.llm_available(),
                "live": live_data_possible(),
                "hosted": HOSTED,
                "tickers": list(SAMPLE_DATA),
                "examples": EXAMPLES,
            })
        if path not in FILES:
            return self.send_error(404)
        name, content_type = FILES[path]
        self.reply((WEB / name).read_bytes(), content_type)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/build":
            return self.send_error(404)
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 8000:
                raise ValueError("Request too large.")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Bad request.")
            return self.reply(build(payload))
        except ValueError as exc:
            return self.reply({"error": str(exc)}, status=400)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return self.reply({"error": "Something went wrong building the trade. Try again."}, status=500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"Trade Structuring Agent on http://localhost:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
