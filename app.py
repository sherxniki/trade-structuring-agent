"""Trade Structuring Agent — describe a market view, get option structures designed, priced and compared.

Run locally:  streamlit run app.py
"""

import math
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from agent import view_parser
from agent.market import SAMPLE_DATA, get_market_data
from agent.recommender import build_plan, horizon_text, money

st.set_page_config(page_title="Trade Structuring Agent", page_icon="📈", layout="wide")

def esc(text):
    """Escape $ so Streamlit markdown doesn't treat it as LaTeX."""
    return str(text).replace("$", "\\$")


COLORS = ["#2563eb", "#d97706", "#7c3aed"]
PROFIT, LOSS = "#16a34a", "#dc2626"

EXAMPLES = [
    "I think Apple goes up a bit over the next 3 months, and I don't want to spend much",
    "NVDA will rally hard after earnings next month",
    "I think the S&P stays flat for the next 6 weeks",
    "Netflix will make a big move after earnings but I'm not sure which way",
    "I own Microsoft shares and want protection for 2 months at zero cost",
    "Tesla drops 15% by the end of the year",
]

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      .step {font-size: 0.9rem; color: #555;}
      .pill {display:inline-block; padding:4px 12px; margin:2px 6px 2px 0; border-radius:999px;
             background:#eef2ff; color:#1e3a8a; font-size:0.9rem;}
      .tag-best {background:#dcfce7; color:#166534; padding:2px 8px; border-radius:6px; font-size:0.8rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------- sidebar ----------------

with st.sidebar:
    st.header("Settings")
    # The class app store has no public internet, so default to sample data there.
    hosted = bool(os.environ.get("WORKSHOP_RUN_TOKEN"))
    data_mode = st.radio("Market data", ["Live (Yahoo Finance)", "Sample (offline)"], index=1 if hosted else 0,
                         help="Sample mode never needs the internet, so it is safest for live demos.")
    use_live = data_mode.startswith("Live")

    has_llm = view_parser.llm_available()
    use_llm = st.toggle("Use AI to read the view", value=has_llm, disabled=not has_llm,
                        help="Uses the class app store's model when available. Otherwise a keyword parser is used.")
    if not has_llm:
        st.caption("AI model not connected: using the built-in keyword parser.")

    default_ticker = st.selectbox("Default ticker (if none mentioned)", list(SAMPLE_DATA), index=0)
    rate = st.slider("Risk-free rate (%)", 0.0, 8.0, 4.0, 0.25) / 100
    skew = st.slider("Put skew (vol pts per 10% lower strike)", 0.0, 6.0, 2.0, 0.5,
                     help="Lower strikes get higher implied vol, as is typical in equity markets.")
    st.divider()
    st.caption("Prices use Black-Scholes with European exercise, no fees. "
               "For education and demos, not investment advice.")

# ---------------- header and input ----------------

st.title("📈 Trade Structuring Agent")
st.write("Describe what you think a stock will do, in plain English. The agent reads your view, "
         "pulls market data, designs option structures, prices them and recommends the best fit.")

if "view_text" not in st.session_state:
    st.session_state.view_text = EXAMPLES[0]

st.caption("Try an example:")
cols = st.columns(3)
for i, ex in enumerate(EXAMPLES):
    if cols[i % 3].button(ex, key=f"ex{i}", width="stretch"):
        st.session_state.view_text = ex
        st.session_state.run = True

text = st.text_area("Your market view", key="view_text", height=80)
if st.button("Build my trade", type="primary"):
    st.session_state.run = True

# ---------------- run the agent ----------------

if st.session_state.get("run"):
    st.session_state.run = False
    with st.status("Agent working…", expanded=True) as status:
        st.write("**1. Reading your view**")
        view = view_parser.parse_view(text, default_ticker, use_llm=use_llm)
        st.markdown(
            f"<span class='step'>Parsed by {'AI' if view.parsed_by == 'llm' else 'keyword rules'}: "
            f"{view.ticker}, {view.direction}"
            f"{' (' + view.strength + ')' if view.direction in ('bullish', 'bearish') else ''}, "
            f"{horizon_text(view.horizon_days)}</span>", unsafe_allow_html=True)

        st.write("**2. Fetching market data**")
        md = get_market_data(view.ticker, view.horizon_days, rate, skew, use_live=use_live)
        st.markdown(esc(f"<span class='step'>{md.ticker} at ${md.spot:,.2f}, vol {md.atm_vol:.0%}. {md.note}</span>"),
                    unsafe_allow_html=True)

        st.write("**3. Designing and pricing candidate structures**")
        plan = build_plan(view, md)
        st.markdown("<span class='step'>" + " · ".join(s.name for s in plan.ranked) + "</span>",
                    unsafe_allow_html=True)

        st.write("**4. Comparing and writing the recommendation**")
        if use_llm and view_parser.llm_available():
            try:
                plan.explanation = view_parser.explain_with_llm(view, md, plan.ranked[0], plan.ranked[1:])
            except Exception:
                pass
        status.update(label="Done", state="complete", expanded=False)
    st.session_state.plan = plan

plan = st.session_state.get("plan")
if not plan:
    st.stop()

view, md, T = plan.view, plan.market, plan.T
best = plan.ranked[0]

# ---------------- what the agent understood ----------------

st.subheader("What the agent understood")
budget = {"any": "No limit", "low": "Keep it cheap", "zero": "Zero cost"}[view.cost_preference]
if view.max_premium:
    budget += f" (≤ ${view.max_premium:,.0f})"
pills = [
    f"Ticker: {view.ticker}",
    f"View: {view.direction}" + (f" ({view.strength})" if view.direction in ("bullish", "bearish") else ""),
    f"Horizon: {horizon_text(view.horizon_days)}",
    f"Budget: {budget}",
    f"Risk: {'Capped losses' if view.limited_risk else 'OK with large risk'}",
]
if view.move_pct:
    pills.insert(2, f"Move: {view.move_pct:g}%")
st.markdown("".join(f"<span class='pill'>{esc(p)}</span>" for p in pills), unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"{md.ticker} price", f"${md.spot:,.2f}", help=md.note)
c2.metric("Implied vol (ATM)", f"{md.atm_vol:.1%}")
c3.metric("Expected move (1 sd)", f"±${plan.expected_move:,.2f}",
          help="One standard deviation move over the horizon, from implied vol.")
if view.direction in ("bullish", "bearish"):
    c4.metric("Target price", f"${plan.target_price:,.2f}",
              f"{plan.target_price / md.spot - 1:+.1%}")
elif view.direction == "hedge":
    c4.metric("Downside scenario", f"${plan.downside_price:,.2f}",
              f"{plan.downside_price / md.spot - 1:+.1%}")
else:
    c4.metric("Data", "Live" if md.source == "live" else "Sample")
if md.source != "live":
    st.caption(f"ℹ️ {md.note}")

# ---------------- recommendation ----------------

st.subheader("Recommendation")
st.success(esc(plan.explanation))
st.markdown("**Legs:** " + " · ".join(l.label() for l in best.legs) +
            f"  —  expiry in {horizon_text(view.horizon_days)}")


# ---------------- helpers ----------------

def signed(x, suffix=""):
    """+$1,234 / -$56 style."""
    sign = "+" if x >= 0 else "-"
    return f"{sign}${abs(x):,.0f}{suffix}"


def fmt_loss(x):
    if x == -math.inf:
        return "Unlimited"
    return money(-x) if x < 0 else "$0"


def fmt_gain(x):
    return "Unlimited" if x == math.inf else money(x)


def fmt_cost(p):
    if abs(p) < 5:
        return "≈ $0"
    return f"{money(p)} paid" if p > 0 else f"{money(-p)} received"


def price_grid(md, plan):
    width = max(2.5 * plan.expected_move, abs(plan.target_price - md.spot) * 1.8, md.spot * 0.08)
    lo = md.spot - width
    hi = md.spot + width
    return np.linspace(max(lo, md.spot * 0.2), hi, 300)


def add_markers(fig, md, plan):
    fig.add_vline(x=md.spot, line_dash="dot", line_color="#6b7280",
                  annotation_text=f"Now ${md.spot:,.0f}", annotation_position="top left")
    if plan.view.direction in ("bullish", "bearish"):
        fig.add_vline(x=plan.target_price, line_dash="dash", line_color="#0ea5e9",
                      annotation_text=f"Target ${plan.target_price:,.0f}", annotation_position="bottom right")
    fig.add_hline(y=0, line_color="#9ca3af", line_width=1)


def style(fig, height=420, legend_below=False):
    legend = (dict(orientation="h", yanchor="top", y=-0.3, x=0) if legend_below
              else dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=90 if legend_below else 10),
                      legend=legend,
                      xaxis_title=f"{md.ticker} price at expiry", yaxis_title="Profit / loss ($)",
                      yaxis_tickprefix="$", yaxis_tickformat=",.0f", xaxis_tickprefix="$",
                      hovermode="x unified", plot_bgcolor="white")
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")
    return fig


# ---------------- tabs ----------------

tab_compare, tab_payoff, tab_adv, tab_how = st.tabs(
    ["Compare", "Payoff charts", "Advanced: greeks & scenarios", "How it works"])

with tab_compare:
    rows = []
    for i, s in enumerate(plan.ranked):
        m = s.metrics
        rows.append({
            "Structure": ("⭐ " if i == 0 else "") + s.name,
            "Legs": " · ".join(l.label() for l in s.legs),
            "Upfront": fmt_cost(m["net_premium"]),
            "Max gain": fmt_gain(m["max_gain"]),
            "Max loss": fmt_loss(m["max_loss"]),
            "Breakeven": ", ".join(f"${b:,.2f}" for b in m["breakevens"][:2]) or "—",
            "If you're right": money(m["pnl_at_target"]) if view.direction != "hedge" else "—",
            "Chance of profit": f"{m['prob_profit']:.0%}",
            "Fit score": round(plan.scores[s.name], 2),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Per 1 contract (100 shares). Chance of profit is market-implied (risk-neutral lognormal), "
               "not a forecast. Fit score balances payoff if you're right, chance of profit, cost and risk.")

    grid = price_grid(md, plan)
    fig = go.Figure()
    for i, s in enumerate(plan.ranked):
        fig.add_trace(go.Scatter(
            x=grid, y=[s.pnl_at_expiry(md, T, x) for x in grid], name=s.name,
            line=dict(color=COLORS[i], width=4 if i == 0 else 2, dash=None if i == 0 else "dash")))
    if view.direction == "hedge":
        fig.add_trace(go.Scatter(x=grid, y=(grid - md.spot) * 100, name="Shares only (no hedge)",
                                 line=dict(color="#9ca3af", width=2, dash="dot")))
    add_markers(fig, md, plan)
    st.markdown("**Profit / loss at expiry**")
    st.plotly_chart(style(fig), width="stretch")

with tab_payoff:
    grid = price_grid(md, plan)
    cols = st.columns(len(plan.ranked))
    for i, (col, s) in enumerate(zip(cols, plan.ranked)):
        expiry = np.array([s.pnl_at_expiry(md, T, x) for x in grid])
        today = np.array([s.pnl(md, T, x) for x in grid])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=grid, y=np.where(expiry > 0, expiry, 0), fill="tozeroy",
                                 line=dict(width=0), fillcolor="rgba(22,163,74,0.15)",
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=grid, y=np.where(expiry < 0, expiry, 0), fill="tozeroy",
                                 line=dict(width=0), fillcolor="rgba(220,38,38,0.15)",
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=grid, y=expiry, name="At expiry", line=dict(color=COLORS[i], width=3)))
        fig.add_trace(go.Scatter(x=grid, y=today, name="If it moves today",
                                 line=dict(color=COLORS[i], width=1.5, dash="dot")))
        add_markers(fig, md, plan)
        fig.update_layout(title=("⭐ " if i == 0 else "") + s.name)
        with col:
            st.plotly_chart(style(fig, 420, legend_below=True), width="stretch")
            st.caption(s.summary)

with tab_adv:
    names = [s.name for s in plan.ranked]
    pick = st.selectbox("Structure", names, index=0)
    s = plan.ranked[names.index(pick)]
    g = s.greeks(md, T)

    a, b, c, d = st.columns(4)
    a.metric("Delta", f"{g['delta_shares']:+,.0f} shares", signed(g['delta_dollars'], " exposure"), delta_color="off",
             help="Share-equivalent exposure: how many shares this behaves like right now.")
    b.metric("Gamma (shares per 1%)", f"{g['gamma_shares']:+,.2f}",
             help="How much delta changes for a 1% move in the stock.")
    c.metric("Vega (per vol pt)", signed(g['vega']), help="P&L for a 1 point rise in implied vol.")
    d.metric("Theta (per day)", signed(g['theta']), help="P&L from one day passing, all else equal.")

    st.markdown("**Scenario grid** — P&L ($) for a move in spot and implied vol")
    days = st.slider("Days from today", 0, max(view.horizon_days - 1, 1), 0,
                     help="0 = an instant move today. Later dates include time decay.")
    spot_moves = [-0.20, -0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10, 0.20]
    vol_moves = [-10, -5, 0, 5, 10]
    z = [[s.pnl(md, T, md.spot * (1 + sm), days_forward=days, vol_shift=vm / 100) for sm in spot_moves]
         for vm in vol_moves]
    zmax = max(abs(v) for row in z for v in row) or 1
    heat = go.Figure(go.Heatmap(
        z=z, x=[f"{sm:+.0%}" for sm in spot_moves], y=[f"{vm:+d} vol" for vm in vol_moves],
        colorscale=[[0, LOSS], [0.5, "#ffffff"], [1, PROFIT]], zmin=-zmax, zmax=zmax,
        text=[[f"{v:+,.0f}" for v in row] for row in z], texttemplate="%{text}",
        hovertemplate="Spot %{x}, %{y}: $%{z:,.0f}<extra></extra>", showscale=False))
    heat.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                       xaxis_title="Spot move", yaxis_title="Implied vol change",
                       xaxis_type="category", yaxis_type="category")
    st.plotly_chart(heat, width="stretch")

    st.markdown("**Leg detail**")
    leg_rows = []
    for leg in s.legs:
        if leg.kind == "stock":
            leg_rows.append({"Leg": leg.label(), "Strike": "—", "Vol": "—", "Price / share": f"${md.spot:,.2f}"})
            continue
        vol = md.vol_for_strike(leg.strike)
        leg_rows.append({"Leg": leg.label(), "Strike": f"${leg.strike:,.2f}", "Vol": f"{vol:.1%}",
                         "Price / share": f"${s.leg_value(leg, md, md.spot, T):,.2f}"})
    st.dataframe(pd.DataFrame(leg_rows), hide_index=True, width="stretch")

with tab_how:
    st.markdown(
        f"""
**The agent runs four steps:**

1. **Read the view** — {'An LLM' if view.parsed_by == 'llm' else 'A keyword parser'} turns your sentence into
   structured fields: ticker, direction, strength, horizon, budget and risk appetite.
2. **Get market data** — live price and at-the-money implied vol from Yahoo Finance (falls back to realized vol,
   then to sample data, so the demo never breaks). A simple put skew is added on top.
3. **Design candidates** — picks three structures that fit the direction, with strikes set from the expected move
   (implied vol × √time). Risk reversals and collars are solved for close to zero cost.
4. **Price, score, explain** — Black-Scholes prices and greeks for each leg, payoff and breakevens at expiry,
   market-implied chance of profit, then a fit score that rewards payoff if you're right and chance of profit,
   and penalises cost (if you want it cheap) and unlimited risk (if you want losses capped).

**Assumptions:** European options, Black-Scholes with a linear skew, flat rates, no fees or bid/ask spread,
1 contract = 100 shares. Built for learning and demos, not trading advice.
"""
    )
