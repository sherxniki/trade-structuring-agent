"""Black-Scholes pricing and greeks for European options.

All functions take:
    S     spot price
    K     strike
    T     time to expiry in years
    r     risk-free rate (continuous, e.g. 0.04)
    q     dividend yield (continuous, e.g. 0.005)
    sigma volatility (e.g. 0.25)
    kind  "call" or "put"
"""

import math


class _Normal:
    """Standard normal distribution using only the math module."""

    @staticmethod
    def cdf(x):
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    @staticmethod
    def pdf(x):
        return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


norm = _Normal()

MIN_T = 1e-6  # avoid dividing by zero at expiry


def _d1_d2(S, K, T, r, q, sigma):
    T = max(T, MIN_T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def intrinsic(S, K, kind):
    if kind == "call":
        return max(S - K, 0.0)
    return max(K - S, 0.0)


def price(S, K, T, r, q, sigma, kind):
    """Black-Scholes price of one option (per share)."""
    if T <= MIN_T:
        return intrinsic(S, K, kind)
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    if kind == "call":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def greeks(S, K, T, r, q, sigma, kind):
    """Greeks of one option (per share).

    delta  change in price per $1 move in spot
    gamma  change in delta per $1 move in spot
    vega   change in price per 1 vol point (1%)
    theta  change in price per calendar day
    """
    if T <= MIN_T:
        itm = intrinsic(S, K, kind) > 0
        delta = (1.0 if itm else 0.0) if kind == "call" else (-1.0 if itm else 0.0)
        return {"delta": delta, "gamma": 0.0, "vega": 0.0, "theta": 0.0}

    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    sqrt_t = math.sqrt(T)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)

    gamma = disc_q * norm.pdf(d1) / (S * sigma * sqrt_t)
    vega = S * disc_q * norm.pdf(d1) * sqrt_t / 100

    if kind == "call":
        delta = disc_q * norm.cdf(d1)
        theta = (
            -S * disc_q * norm.pdf(d1) * sigma / (2 * sqrt_t)
            - r * K * disc_r * norm.cdf(d2)
            + q * S * disc_q * norm.cdf(d1)
        )
    else:
        delta = -disc_q * norm.cdf(-d1)
        theta = (
            -S * disc_q * norm.pdf(d1) * sigma / (2 * sqrt_t)
            + r * K * disc_r * norm.cdf(-d2)
            - q * S * disc_q * norm.cdf(-d1)
        )

    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta / 365}
