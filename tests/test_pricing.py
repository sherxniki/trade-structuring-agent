import math

from agent import pricing
from agent.market import sample_market_data
from agent.recommender import build_plan
from agent.view_parser import parse_with_rules


def test_known_black_scholes_value():
    # Textbook case: S=100, K=100, T=1, r=5%, vol=20% -> call ~10.45, put ~5.57
    assert abs(pricing.price(100, 100, 1, 0.05, 0, 0.2, "call") - 10.4506) < 1e-3
    assert abs(pricing.price(100, 100, 1, 0.05, 0, 0.2, "put") - 5.5735) < 1e-3


def test_put_call_parity():
    S, K, T, r, q, v = 230, 240, 0.5, 0.04, 0.01, 0.3
    c = pricing.price(S, K, T, r, q, v, "call")
    p = pricing.price(S, K, T, r, q, v, "put")
    assert abs((c - p) - (S * math.exp(-q * T) - K * math.exp(-r * T))) < 1e-8


def test_delta_matches_finite_difference():
    h = 0.01
    up = pricing.price(100 + h, 105, 0.25, 0.04, 0, 0.25, "call")
    dn = pricing.price(100 - h, 105, 0.25, 0.04, 0, 0.25, "call")
    g = pricing.greeks(100, 105, 0.25, 0.04, 0, 0.25, "call")
    assert abs((up - dn) / (2 * h) - g["delta"]) < 1e-4


def test_parser_reads_simple_views():
    v = parse_with_rules("I think Apple goes up a bit over 3 months, and I don't want to spend much")
    assert (v.ticker, v.direction, v.horizon_days, v.cost_preference) == ("AAPL", "bullish", 90, "low")
    assert parse_with_rules("Tesla drops 15% by year end").direction == "bearish"
    assert parse_with_rules("SPY stays flat").direction == "neutral"
    assert parse_with_rules("I own MSFT and want protection").direction == "hedge"


def test_bull_call_spread_metrics():
    v = parse_with_rules("AAPL up a bit in 3 months, cheap")
    plan = build_plan(v, sample_market_data("AAPL"))
    spread = next(s for s in plan.ranked if s.name == "Bull call spread")
    width = (spread.legs[1].strike - spread.legs[0].strike) * 100
    m = spread.metrics
    # max gain + max loss of a debit spread equals the strike width
    assert abs(m["max_gain"] - m["max_loss"] - width) < 1.0
    assert abs(-m["max_loss"] - m["net_premium"]) < 1.0


def test_every_direction_builds_three_structures():
    for text in ["NVDA up", "NVDA down", "NVDA flat", "NVDA big move either way", "I own NVDA, hedge"]:
        plan = build_plan(parse_with_rules(text), sample_market_data("NVDA"))
        assert len(plan.ranked) == 3
        assert plan.explanation
