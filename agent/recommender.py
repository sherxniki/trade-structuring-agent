"""Pick candidate structures for a view, price them, score them and explain the choice."""

import math
from dataclasses import dataclass

from agent import strategies as st


@dataclass
class Plan:
    view: object
    market: object
    T: float                 # years to expiry
    expected_move: float     # 1 standard deviation move in $ over the horizon
    target_price: float      # price the view expects
    downside_price: float    # used for hedges
    ranked: list             # strategies, best first
    scores: dict             # name -> score
    explanation: str


def strike_step(spot):
    if spot < 20:
        return 0.5
    if spot < 100:
        return 1.0
    if spot < 500:
        return 5.0
    return 10.0


def round_strike(x, spot):
    step = strike_step(spot)
    return round(round(x / step) * step, 2)


def _apart(k_low, k_high, spot):
    """Make sure two strikes are at least one step apart."""
    step = strike_step(spot)
    if k_high - k_low < step:
        k_high = k_low + step
    return k_low, k_high


def zero_cost_strike(make, strikes, md, T):
    """Pick the strike from `strikes` that makes the structure cost closest to zero."""
    best, best_cost = None, None
    for k in strikes:
        cost = abs(make(k).net_premium(md, T))
        if best_cost is None or cost < best_cost:
            best, best_cost = k, cost
    return best


def strike_grid(spot, low, high):
    step = strike_step(spot)
    k = round_strike(low, spot)
    out = []
    while k <= high:
        out.append(round(k, 2))
        k += step
    return out


def move_fraction(view, md, T):
    """Size of the expected move as a fraction of spot."""
    if view.move_pct:
        return max(view.move_pct / 100, 0.01)
    one_sd = md.atm_vol * math.sqrt(T)
    if view.direction in ("neutral", "volatile", "hedge"):
        return max(one_sd, 0.02)
    factor = 1.0 if view.strength == "strong" else 0.5
    return max(one_sd * factor, 0.02)


def build_candidates(view, md, T):
    S = md.spot
    m = move_fraction(view, md, T)
    r = lambda x: round_strike(x, S)
    atm = r(S)

    if view.direction == "bullish":
        call_k = atm if view.strength == "mild" else r(S * (1 + m / 2))
        lo, hi = _apart(atm, r(S * (1 + m)), S)
        rr_call = r(S * (1 + m / 2))
        rr_put = zero_cost_strike(lambda k: st.risk_reversal_bullish(k, rr_call),
                                  strike_grid(S, S * 0.5, S * 0.99), md, T)
        return [
            st.long_call(call_k),
            st.bull_call_spread(lo, hi),
            st.risk_reversal_bullish(rr_put, rr_call),
        ]

    if view.direction == "bearish":
        put_k = atm if view.strength == "mild" else r(S * (1 - m / 2))
        lo, hi = _apart(r(S * (1 - m)), atm, S)
        rr_put = r(S * (1 - m / 2))
        rr_call = zero_cost_strike(lambda k: st.risk_reversal_bearish(k, rr_put),
                                   strike_grid(S, S * 1.01, S * 1.6), md, T)
        return [
            st.long_put(put_k),
            st.bear_put_spread(hi, lo),
            st.risk_reversal_bearish(rr_call, rr_put),
        ]

    if view.direction == "neutral":
        inner = m * 0.75
        p_sell, c_sell = r(S * (1 - inner)), r(S * (1 + inner))
        p_buy, c_buy = r(S * (1 - 2 * inner)), r(S * (1 + 2 * inner))
        p_buy, p_sell = _apart(p_buy, p_sell, S)
        c_sell, c_buy = _apart(c_sell, c_buy, S)
        b_lo, b_hi = r(S * (1 - inner)), r(S * (1 + inner))
        return [
            st.iron_condor(p_buy, p_sell, c_sell, c_buy),
            st.call_butterfly(b_lo, atm, b_hi),
            st.short_strangle(p_sell, c_sell),
        ]

    if view.direction == "volatile":
        half = m / 2
        p_in, c_in = r(S * (1 - half)), r(S * (1 + half))
        p_out, c_out = r(S * (1 - 1.5 * m)), r(S * (1 + 1.5 * m))
        reverse_condor = st.Strategy(
            "Reverse iron condor",
            [st.Leg("put", -1, p_out), st.Leg("put", 1, p_in),
             st.Leg("call", 1, c_in), st.Leg("call", -1, c_out)],
            "Buy a strangle and sell further-out options: cheaper big-move bet, gains are capped.",
        )
        return [st.long_straddle(atm), st.long_strangle(p_in, c_in), reverse_condor]

    # hedge: user owns 100 shares and wants protection
    put_k = r(S * 0.95)
    if view.cost_preference in ("zero", "low"):
        collar_call = zero_cost_strike(lambda k: st.collar(put_k, k),
                                       strike_grid(S, S * 1.01, S * 1.6), md, T)
    else:
        collar_call = r(S * (1 + m))
    return [
        st.protective_put(put_k),
        st.collar(put_k, collar_call),
        st.put_spread_hedge(put_k, r(S * (1 - 1.5 * m))),
    ]


# ---------------- scenarios ----------------

def scenario_prices(view, md, m, target):
    """Spot prices that represent 'being right' about the view."""
    S = md.spot
    if view.direction == "neutral":
        return [S * (1 + x * m / 2) for x in (-1, -0.5, 0, 0.5, 1)]   # stays inside the range
    if view.direction == "volatile":
        return [S * (1 - m), S * (1 + m)]                                # moves either way
    return [target]


def scenario_text(view, md, m, target):
    if view.direction == "neutral":
        lo, hi = md.spot * (1 - m / 2), md.spot * (1 + m / 2)
        return f"on average if {md.ticker} stays between ${lo:,.2f} and ${hi:,.2f}"
    if view.direction == "volatile":
        return f"on average if {md.ticker} moves {m:.0%} either way"
    return f"if {md.ticker} ends at ${target:,.2f}"


# ---------------- scoring ----------------

def _risk_capital(strategy, md, T, m):
    """Money at risk: max loss, or a stress loss (2x expected move against you) if unlimited."""
    max_loss = strategy.metrics["max_loss"]
    if max_loss != -math.inf:
        return max(abs(max_loss), 1.0)
    stress = min(strategy.pnl_at_expiry(md, T, md.spot * (1 - 2 * m)),
                 strategy.pnl_at_expiry(md, T, md.spot * (1 + 2 * m)))
    return max(abs(stress), 1.0)


def _cost_penalty(view, strategy, md):
    premium = strategy.metrics["net_premium"]
    notional = md.spot * st.MULTIPLIER
    penalty = 0.0
    if view.cost_preference == "low":
        penalty += max(premium, 0) / notional * 10
    elif view.cost_preference == "zero":
        penalty += abs(premium) / notional * 50
    if view.max_premium and premium > view.max_premium:
        penalty += 1.0
    if view.limited_risk and not strategy.metrics["limited_risk"]:
        penalty += 1.0
    return penalty


def score(view, strategy, md, T, target, downside, m):
    if view.direction == "hedge":
        stock_down = (downside - md.spot) * st.MULTIPLIER
        stock_up = (md.spot * (1 + m) - md.spot) * st.MULTIPLIER
        hedged_down = strategy.pnl_at_expiry(md, T, downside)
        hedged_up = strategy.pnl_at_expiry(md, T, md.spot * (1 + m))
        protection = (hedged_down - stock_down) / abs(stock_down)   # share of the loss saved
        upside_kept = hedged_up / stock_up
        base = 0.6 * protection + 0.4 * upside_kept
    else:
        ror = strategy.metrics["pnl_at_target"] / _risk_capital(strategy, md, T, m)
        base = 0.6 * min(ror, 3.0) + 1.0 * strategy.metrics["prob_profit"]
    return base - _cost_penalty(view, strategy, md)


# ---------------- explanation ----------------

def money(x):
    if x == math.inf:
        return "unlimited"
    if x == -math.inf:
        return "unlimited"
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.0f}"


def horizon_text(days):
    if days < 14:
        return f"{days} days"
    if days < 60:
        return f"{round(days / 7)} weeks"
    if days < 365:
        return f"{round(days / 30)} months"
    years = days / 365
    return "1 year" if round(years, 1) == 1 else f"{years:.1f} years"


def outcome(pnl):
    if pnl >= 0:
        return f"makes {money(pnl)}"
    return f"loses {money(-pnl)}"


def cost_text(premium):
    if abs(premium) < 5:
        return "costs about nothing upfront"
    if premium > 0:
        return f"costs {money(premium)} upfront"
    return f"pays you {money(-premium)} upfront"


def explain(view, md, best, others, target, downside, scenario):
    mt = best.metrics
    view_text = {
        "bullish": f"a {view.strength} bullish view",
        "bearish": f"a {view.strength} bearish view",
        "neutral": "a view that the stock stays in a range",
        "volatile": "a view that the stock makes a big move either way",
        "hedge": "protecting shares you already own",
    }[view.direction]

    lines = [f"**{best.name}** is the best fit for {view_text} on {md.ticker} over "
             f"{horizon_text(view.horizon_days)}. {best.summary}"]

    if view.direction == "hedge":
        hedged = best.pnl_at_expiry(md, best_T(view), downside)
        unhedged = (downside - md.spot) * st.MULTIPLIER
        lines.append(
            f"It {cost_text(mt['net_premium'])}. If {md.ticker} drops to ${downside:,.2f}, "
            f"100 shares alone lose {money(abs(unhedged))}; with this hedge you lose {money(abs(hedged))}."
        )
    else:
        loss = "unlimited" if mt["max_loss"] == -math.inf else money(-mt["max_loss"]) if mt["max_loss"] < 0 else "$0"
        lines.append(
            f"It {cost_text(mt['net_premium'])}, {outcome(mt['pnl_at_target'])} {scenario}, "
            f"and the most you can lose is {loss}. "
            f"Market-implied chance of profit: {mt['prob_profit']:.0%}."
        )

    if others:
        alt = others[0]
        reasons = []
        if mt["limited_risk"] and not alt.metrics["limited_risk"]:
            reasons.append("its loss is capped")
        if mt["net_premium"] < alt.metrics["net_premium"] - 5:
            reasons.append("it is cheaper")
        if view.direction != "hedge" and (mt["pnl_at_target"] or 0) > (alt.metrics["pnl_at_target"] or 0) + 5:
            reasons.append("it pays more if you are right")
        if mt["prob_profit"] > alt.metrics["prob_profit"] + 0.03:
            reasons.append("it has a higher chance of profit")
        if reasons:
            joined = reasons[0] if len(reasons) == 1 else ", ".join(reasons[:-1]) + " and " + reasons[-1]
            lines.append(f"Compared with the {alt.name.lower()}, {joined}.")
    return " ".join(lines)


def best_T(view):
    return view.horizon_days / 365


# ---------------- main entry ----------------

def build_plan(view, md):
    T = view.horizon_days / 365
    m = move_fraction(view, md, T)
    one_sd = md.atm_vol * math.sqrt(T) * md.spot

    if view.direction == "bullish":
        target = md.spot * (1 + m)
    elif view.direction == "bearish":
        target = md.spot * (1 - m)
    else:
        target = md.spot
    downside = md.spot * (1 - m)

    candidates = build_candidates(view, md, T)
    prices = scenario_prices(view, md, m, target)
    for s in candidates:
        s.compute_metrics(md, T, target)
        s.metrics["pnl_at_target"] = sum(s.pnl_at_expiry(md, T, p) for p in prices) / len(prices)

    scores = {s.name: score(view, s, md, T, target, downside, m) for s in candidates}
    ranked = sorted(candidates, key=lambda s: scores[s.name], reverse=True)
    text = explain(view, md, ranked[0], ranked[1:], target, downside, scenario_text(view, md, m, target))
    return Plan(view, md, T, one_sd, target, downside, ranked, scores, text)
