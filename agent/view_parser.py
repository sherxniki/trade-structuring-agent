"""Turn a plain-English market view into structured fields.

Uses an LLM through the class app store's broker when available, and a simple keyword parser otherwise,
so the demo always works.
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import date

from agent import broker

DIRECTIONS = ["bullish", "bearish", "neutral", "volatile", "hedge"]

COMPANY_TICKERS = {
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "amazon": "AMZN",
    "google": "GOOGL", "alphabet": "GOOGL", "meta": "META", "facebook": "META",
    "tesla": "TSLA", "jpmorgan": "JPM", "jp morgan": "JPM", "morgan stanley": "MS",
    "goldman": "GS", "netflix": "NFLX", "amd": "AMD", "s&p": "SPY", "s&p 500": "SPY",
    "sp500": "SPY", "spx": "SPY", "the market": "SPY", "nasdaq": "QQQ",
}

# Uppercase words that look like tickers but are not.
NOT_TICKERS = {"I", "A", "AN", "THE", "AND", "OR", "BUT", "IF", "MY", "ME", "IT", "TO", "IN",
               "ON", "UP", "OF", "AT", "BY", "SO", "NO", "OK", "ETF", "USD", "CEO", "AI",
               "EPS", "Q1", "Q2", "Q3", "Q4", "IV", "VOL", "DON'T", "WANT"}


@dataclass
class View:
    ticker: str
    direction: str              # bullish, bearish, neutral, volatile, hedge
    strength: str = "mild"      # mild or strong
    move_pct: float = None      # expected move in %, if the user gave one
    horizon_days: int = 90
    cost_preference: str = "any"   # any, low, zero
    max_premium: float = None      # max $ to spend per structure, if given
    limited_risk: bool = True      # user wants losses capped
    parsed_by: str = "rules"

    def to_dict(self):
        return asdict(self)


# ---------------- rule-based parser ----------------

def _find_ticker(text, default):
    m = re.search(r"\$([A-Za-z]{1,5})\b", text)
    if m:
        return m.group(1).upper()
    lower = text.lower()
    for name in sorted(COMPANY_TICKERS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(name) + r"\b", lower):
            return COMPANY_TICKERS[name]
    for word in re.findall(r"\b[A-Z]{1,5}\b", text):
        if word not in NOT_TICKERS:
            return word
    return default


def _has(text, words):
    return any(re.search(r"\b" + w + r"\b", text) for w in words)


def _find_direction(text):
    if _has(text, ["hedge", "protect", "protection", "insure", "insurance", "i own", "i hold",
                   "my shares", "holding", "downside protection"]):
        return "hedge"
    if _has(text, ["big move", "volatile", "either way", "either direction", "not sure which way",
                   "don't know which way", "swing", "jump or drop", "move a lot", "explode"]):
        return "volatile"
    if _has(text, ["sideways", "flat", "range", "range-bound", "stay", "calm", "stable",
                   "not move", "won't move", "boring", "quiet", "pinned", "stuck"]):
        return "neutral"
    if _has(text, [r"(not|won't|wont|isn't|don't think it will) (go )?(down|fall|drop)"]):
        return "bullish"
    if _has(text, [r"(not|won't|wont) (go )?(up|rise|rally)"]):
        return "bearish"
    bull = ["bullish", "up", "rise", "rally", "higher", "climb", "beat", "grow", "gain",
            "increase", "moon", "rebound", "recover", "outperform", "rallies", "surge", "soar"]
    bear = ["bearish", "down", "fall", "drop", "decline", "lower", "crash", "miss", "sink",
            "tank", "slide", "underperform", "correction", "plunge", "collapse", "sell-off", "selloff"]
    ending = r"(s|es|ed|d|ing|ped|ping)?\b"   # drops, dropped, falling...
    bull_hits = sum(1 for w in bull if re.search(r"\b" + w + ending, text))
    bear_hits = sum(1 for w in bear if re.search(r"\b" + w + ending, text))
    if bear_hits > bull_hits:
        return "bearish"
    if bull_hits > 0:
        return "bullish"
    return "bullish"


def _find_strength(text):
    if _has(text, ["a lot", "sharply", "significantly", "strongly", "strong", "big", "huge",
                   "crash", "moon", "massive", "very", "much higher", "much lower", "explode", "soar",
                   "hard", "surge", "skyrocket", "rip", "plunge", "collapse", "tank", "big way"]):
        return "strong"
    return "mild"


def _find_horizon(text):
    m = re.search(r"(\d+)\s*(day|week|month|year|yr|mo)s?", text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        mult = {"day": 1, "week": 7, "month": 30, "mo": 30, "year": 365, "yr": 365}[unit]
        return max(7, min(n * mult, 730))
    words = {"a week": 7, "next week": 7, "a month": 30, "next month": 30, "a quarter": 90,
             "next quarter": 90, "a year": 365, "next year": 365, "six months": 180,
             "half a year": 180, "two months": 60, "three months": 90, "few weeks": 21,
             "few months": 90, "earnings": 30, "short term": 30, "long term": 365}
    for phrase, days in words.items():
        if phrase in text:
            return days
    if "end of the year" in text or "end of year" in text or "year end" in text:
        days = (date(date.today().year, 12, 31) - date.today()).days
        return max(days, 14)
    return 90


def _find_cost(text):
    max_premium = None
    m = re.search(r"\$\s?([\d,]+(?:\.\d+)?)\s*(k)?", text)
    if m and _has(text, ["spend", "budget", "pay", "cost", "premium", "max", "risk", "afford"]):
        max_premium = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)

    if _has(text, ["free", "zero cost", "zero-cost", "costless", "no cost", "no upfront",
                   "nothing upfront", "don't want to pay", "self-financing", "self financing"]):
        return "zero", max_premium
    if _has(text, ["cheap", "low cost", "low-cost", "inexpensive", "not spend much",
                   "don't want to spend", "dont want to spend", "spend much", "small budget",
                   "budget", "affordable", "too much"]) or max_premium:
        return "low", max_premium
    return "any", max_premium


def _find_limited_risk(text):
    if _has(text, ["unlimited risk is fine", "ok with risk", "okay with risk", "comfortable with risk",
                   "happy to take risk", "don't mind risk", "aggressive"]):
        return False
    return True


def parse_with_rules(text, default_ticker="AAPL"):
    lower = text.lower()
    move = re.search(r"(\d+(?:\.\d+)?)\s*%", lower)
    cost_pref, max_premium = _find_cost(lower)
    return View(
        ticker=_find_ticker(text, default_ticker),
        direction=_find_direction(lower),
        strength=_find_strength(lower),
        move_pct=float(move.group(1)) if move else None,
        horizon_days=_find_horizon(lower),
        cost_preference=cost_pref,
        max_premium=max_premium,
        limited_risk=_find_limited_risk(lower),
        parsed_by="rules",
    )


# ---------------- LLM parser ----------------

VIEW_TOOL = {
    "type": "function",
    "function": {
        "name": "record_view",
        "description": "Record the user's market view as structured fields.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock or ETF ticker, e.g. AAPL. Map company names to tickers. Use SPY for 'the market'."},
                "direction": {"type": "string", "enum": DIRECTIONS,
                              "description": "bullish/bearish = expects up/down; neutral = expects little movement; volatile = big move but unsure of direction; hedge = owns the stock and wants protection."},
                "strength": {"type": "string", "enum": ["mild", "strong"]},
                "move_pct": {"type": ["number", "null"], "description": "Size of expected move in percent if stated, else null."},
                "horizon_days": {"type": "integer", "description": "Time horizon in calendar days. Default 90 if not stated."},
                "cost_preference": {"type": "string", "enum": ["any", "low", "zero"],
                                    "description": "low = wants it cheap; zero = wants zero upfront cost; any = not mentioned."},
                "max_premium": {"type": ["number", "null"], "description": "Max dollars they will spend, if stated."},
                "limited_risk": {"type": "boolean", "description": "False only if the user says they accept unlimited or large risk."},
            },
            "required": ["ticker", "direction", "strength", "horizon_days", "cost_preference", "limited_risk"],
        },
    },
}


def llm_available():
    return broker.available()


def _view_from_fields(data, default_ticker):
    direction = data.get("direction") if data.get("direction") in DIRECTIONS else "bullish"
    cost = data.get("cost_preference") if data.get("cost_preference") in ("any", "low", "zero") else "any"
    return View(
        ticker=str(data.get("ticker") or default_ticker).upper().lstrip("$"),
        direction=direction,
        strength="strong" if data.get("strength") == "strong" else "mild",
        move_pct=data.get("move_pct"),
        horizon_days=int(max(7, min(int(data.get("horizon_days") or 90), 730))),
        cost_preference=cost,
        max_premium=data.get("max_premium"),
        limited_risk=bool(data.get("limited_risk", True)),
        parsed_by="llm",
    )


def parse_with_llm(text, default_ticker="AAPL"):
    messages = [
        {"role": "system", "content": (
            "You turn a person's market view into structured fields. Always answer by calling "
            f"record_view exactly once. Today is {date.today().isoformat()}. "
            f"If no ticker is mentioned, use {default_ticker}.")},
        {"role": "user", "content": text},
    ]
    message = broker.chat(messages, tools=[VIEW_TOOL], max_tokens=400)
    calls = message.get("tool_calls") or []
    if calls and calls[0]["function"]["name"] == "record_view":
        data = json.loads(calls[0]["function"]["arguments"])
    else:
        # Some models answer with JSON text instead of a tool call.
        content = message.get("content") or ""
        data = json.loads(content[content.index("{"): content.rindex("}") + 1])
    return _view_from_fields(data, default_ticker)


def parse_view(text, default_ticker="AAPL", use_llm=True):
    """Parse with the LLM if possible, otherwise fall back to rules."""
    if use_llm and llm_available():
        try:
            return parse_with_llm(text, default_ticker)
        except Exception:
            pass
    return parse_with_rules(text, default_ticker)


def explain_with_llm(view, md, best, others):
    """Optional: a short natural-language explanation written by the LLM."""
    payload = {
        "view": view.to_dict(),
        "market": {"ticker": md.ticker, "spot": round(md.spot, 2), "atm_vol": round(md.atm_vol, 3)},
        "recommended": {"name": best.name, "legs": [l.label() for l in best.legs], "metrics": _clean(best.metrics)},
        "alternatives": [{"name": s.name, "metrics": _clean(s.metrics)} for s in others],
    }
    messages = [{
        "role": "user",
        "content": (
            "You are a derivatives structurer. In 3 short sentences of plain English, explain why "
            "the recommended structure fits this view better than the alternatives, and name its "
            "main risk. No jargon without explaining it. Numbers are per 1 contract. "
            "Reply with plain text only.\n\n" + json.dumps(payload, default=str)
        ),
    }]
    text = (broker.chat(messages, max_tokens=300).get("content") or "").strip()
    if not text:
        raise ValueError("The model returned no explanation.")
    return text


def _clean(metrics):
    out = {}
    for k, v in metrics.items():
        if isinstance(v, float):
            out[k] = "unlimited" if v in (float("inf"), float("-inf")) else round(v, 2)
        else:
            out[k] = v
    return out
