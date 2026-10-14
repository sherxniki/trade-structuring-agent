"""Option strategies: legs, pricing, payoffs and summary metrics.

Everything is quoted per 1 unit of the structure, i.e. 1 contract per option
leg (100 shares) and 100 shares for a stock leg.
"""

import math
from dataclasses import dataclass, field

import numpy as np

from agent import pricing

MULTIPLIER = 100


@dataclass
class MarketData:
    ticker: str
    spot: float
    atm_vol: float          # e.g. 0.28 for 28%
    rate: float = 0.04      # risk-free rate
    div_yield: float = 0.0
    skew: float = 2.0       # extra vol points for every 10% the strike is below spot
    source: str = "sample"  # "live" or "sample"
    note: str = ""

    def vol_for_strike(self, strike):
        """Simple linear skew: lower strikes get higher vol (typical for equities)."""
        moneyness = math.log(strike / self.spot)
        vol = self.atm_vol - (self.skew / 100) * (moneyness / 0.10)
        return max(vol, 0.05)


@dataclass
class Leg:
    kind: str       # "call", "put" or "stock"
    qty: int        # +1 long, -1 short
    strike: float = 0.0

    def label(self):
        side = "Buy" if self.qty > 0 else "Sell"
        if self.kind == "stock":
            return f"{side} 100 shares"
        n = abs(self.qty)
        count = f"{n}x " if n > 1 else ""
        return f"{side} {count}{self.strike:g} {self.kind}"


@dataclass
class Strategy:
    name: str
    legs: list
    summary: str = ""            # one-line plain-English idea
    holds_stock: bool = False    # True for hedges on stock you already own
    metrics: dict = field(default_factory=dict)

    # ---------- pricing ----------

    def leg_value(self, leg, md, S, T, vol_shift=0.0):
        """Value of one leg per share at spot S with T years left."""
        if leg.kind == "stock":
            return S
        vol = md.vol_for_strike(leg.strike) + vol_shift
        vol = max(vol, 0.01)
        return pricing.price(S, leg.strike, T, md.rate, md.div_yield, vol, leg.kind)

    def entry_values(self, md, T):
        return [self.leg_value(leg, md, md.spot, T) for leg in self.legs]

    def net_premium(self, md, T):
        """Upfront option premium in $ (positive = you pay, negative = you receive)."""
        total = 0.0
        for leg, value in zip(self.legs, self.entry_values(md, T)):
            if leg.kind != "stock":
                total += leg.qty * value
        return total * MULTIPLIER

    def pnl(self, md, T, S, days_forward=0, vol_shift=0.0):
        """P&L in $ if spot moves to S after `days_forward` days (and vol shifts)."""
        T_left = max(T - days_forward / 365, 0.0)
        total = 0.0
        for leg, entry in zip(self.legs, self.entry_values(md, T)):
            now = self.leg_value(leg, md, S, T_left, vol_shift)
            total += leg.qty * (now - entry)
        return total * MULTIPLIER

    def pnl_at_expiry(self, md, T, S):
        return self.pnl(md, T, S, days_forward=T * 365)

    def greeks(self, md, T):
        """Position greeks in $ terms for one unit of the structure."""
        out = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
        for leg in self.legs:
            if leg.kind == "stock":
                out["delta"] += leg.qty
                continue
            vol = md.vol_for_strike(leg.strike)
            g = pricing.greeks(md.spot, leg.strike, T, md.rate, md.div_yield, vol, leg.kind)
            for key in out:
                out[key] += leg.qty * g[key]
        return {
            "delta_shares": out["delta"] * MULTIPLIER,                       # share-equivalent
            "delta_dollars": out["delta"] * MULTIPLIER * md.spot,            # $ exposure
            "gamma_shares": out["gamma"] * MULTIPLIER * md.spot / 100,      # delta change per 1% move
            "vega": out["vega"] * MULTIPLIER,                                # $ per vol point
            "theta": out["theta"] * MULTIPLIER,                              # $ per day
        }

    # ---------- summary numbers ----------

    def compute_metrics(self, md, T, target_price=None):
        spots = np.linspace(md.spot * 0.01, md.spot * 3.0, 3000)
        pnls = np.array([self.pnl_at_expiry(md, T, s) for s in spots])

        # If P&L still rises (or falls) at the far right, gain (or loss) is unlimited.
        slope_right = pnls[-1] - pnls[-2]
        unlimited_gain = slope_right > 1e-6
        unlimited_loss = slope_right < -1e-6

        max_gain = math.inf if unlimited_gain else float(pnls.max())
        max_loss = -math.inf if unlimited_loss else float(pnls.min())

        breakevens = []
        for i in range(len(spots) - 1):
            a, b = pnls[i], pnls[i + 1]
            if a == 0 or (a < 0) != (b < 0):
                if b != a:
                    x = spots[i] + (spots[i + 1] - spots[i]) * (-a) / (b - a)
                else:
                    x = spots[i]
                breakevens.append(round(float(x), 2))

        prob_profit = self._prob_profit(md, T, spots, pnls)

        self.metrics = {
            "net_premium": self.net_premium(md, T),
            "max_gain": max_gain,
            "max_loss": max_loss,
            "breakevens": breakevens,
            "prob_profit": prob_profit,
            "pnl_at_target": self.pnl_at_expiry(md, T, target_price) if target_price else None,
            "limited_risk": not unlimited_loss and max_loss > -math.inf,
        }
        return self.metrics

    @staticmethod
    def _prob_profit(md, T, spots, pnls):
        """Chance of making money at expiry, using a lognormal model with ATM vol.

        Uses the risk-neutral drift, so it is a market-implied estimate, not a forecast.
        """
        sigma = md.atm_vol
        mu = math.log(md.spot) + (md.rate - md.div_yield - 0.5 * sigma**2) * T
        sd = sigma * math.sqrt(max(T, 1e-6))
        log_s = np.log(spots)
        density = np.exp(-((log_s - mu) ** 2) / (2 * sd**2)) / (spots * sd * math.sqrt(2 * math.pi))
        weights = density * np.gradient(spots)
        weights = weights / weights.sum()
        return float(weights[pnls > 0].sum())


# ---------- strategy builders ----------

def long_call(k):
    return Strategy("Long call", [Leg("call", 1, k)],
                    "Buy a call: pay a premium for unlimited upside.")


def bull_call_spread(k_low, k_high):
    return Strategy("Bull call spread", [Leg("call", 1, k_low), Leg("call", -1, k_high)],
                    "Buy a call and sell a higher one: cheaper, but gains are capped.")


def risk_reversal_bullish(k_put, k_call):
    return Strategy("Risk reversal", [Leg("put", -1, k_put), Leg("call", 1, k_call)],
                    "Sell a put to pay for a call: near zero cost, but you take downside risk.")


def long_put(k):
    return Strategy("Long put", [Leg("put", 1, k)],
                    "Buy a put: pay a premium to profit if the stock falls.")


def bear_put_spread(k_high, k_low):
    return Strategy("Bear put spread", [Leg("put", 1, k_high), Leg("put", -1, k_low)],
                    "Buy a put and sell a lower one: cheaper, but gains are capped.")


def risk_reversal_bearish(k_call, k_put):
    return Strategy("Bearish risk reversal", [Leg("call", -1, k_call), Leg("put", 1, k_put)],
                    "Sell a call to pay for a put: near zero cost, but you take upside risk.")


def long_straddle(k):
    return Strategy("Long straddle", [Leg("call", 1, k), Leg("put", 1, k)],
                    "Buy a call and a put at the same strike: profit from a big move either way.")


def long_strangle(k_put, k_call):
    return Strategy("Long strangle", [Leg("put", 1, k_put), Leg("call", 1, k_call)],
                    "Buy an out-of-the-money put and call: cheaper than a straddle, needs a bigger move.")


def iron_condor(k_put_buy, k_put_sell, k_call_sell, k_call_buy):
    return Strategy("Iron condor", [
        Leg("put", 1, k_put_buy), Leg("put", -1, k_put_sell),
        Leg("call", -1, k_call_sell), Leg("call", 1, k_call_buy),
    ], "Sell a put spread and a call spread: collect premium if the stock stays in a range.")


def call_butterfly(k_low, k_mid, k_high):
    return Strategy("Call butterfly", [
        Leg("call", 1, k_low), Leg("call", -2, k_mid), Leg("call", 1, k_high),
    ], "Low-cost bet that the stock ends near one price.")


def short_strangle(k_put, k_call):
    return Strategy("Short strangle", [Leg("put", -1, k_put), Leg("call", -1, k_call)],
                    "Sell a put and a call: collect premium if the stock stays calm, unlimited risk.")


def protective_put(k):
    return Strategy("Protective put", [Leg("stock", 1), Leg("put", 1, k)],
                    "Keep your shares and buy a put as insurance.", holds_stock=True)


def collar(k_put, k_call):
    return Strategy("Collar", [Leg("stock", 1), Leg("put", 1, k_put), Leg("call", -1, k_call)],
                    "Buy a put and sell a call against your shares: cheap protection, capped upside.",
                    holds_stock=True)


def put_spread_hedge(k_high, k_low):
    return Strategy("Put spread hedge", [Leg("stock", 1), Leg("put", 1, k_high), Leg("put", -1, k_low)],
                    "Buy a put spread against your shares: protects against a moderate drop for less.",
                    holds_stock=True)
