# Trade Structuring Agent

Describe a market view in plain English, and the agent designs, prices and compares option trades for it.

> "I think Apple goes up a bit over the next 3 months, and I don't want to spend much"
>
> → **Bull call spread** (buy 230 call, sell 245 call). Costs $655, makes $830 if AAPL reaches $245, max loss $655, 42% market-implied chance of profit. Compared with the risk reversal, it pays more if you are right.

## What it does

The agent runs four steps:

1. **Reads the view.** An LLM via the Anthropic API (or a built-in keyword parser if no API key is set) turns the sentence into structured fields: ticker, direction (bullish, bearish, neutral, volatile, hedge), strength, horizon, budget and risk appetite.
2. **Gets market data.** Live price and at-the-money implied vol from Yahoo Finance. Falls back to realized vol, then to sample data, so a demo never breaks.
3. **Designs candidates.** Picks three structures that fit the view, with strikes set from the expected move (implied vol × √time). Risk reversals and collars are solved for close to zero cost.
4. **Prices, scores and explains.** Black-Scholes prices and greeks for each leg, payoff and breakevens at expiry, market-implied chance of profit, and a fit score that balances payoff if you're right, chance of profit, cost and risk.

| View | Structures compared |
|---|---|
| Bullish | Long call, bull call spread, risk reversal |
| Bearish | Long put, bear put spread, bearish risk reversal |
| Range-bound | Iron condor, call butterfly, short strangle |
| Big move either way | Long straddle, long strangle, reverse iron condor |
| Hedge shares you own | Protective put, collar, put spread hedge |

The **Advanced** tab shows position greeks (delta, gamma, vega, theta), a spot × implied vol scenario grid with a days-forward slider, and per-leg strikes, vols and prices.

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Optional: set an Anthropic API key so the LLM reads the view and writes the explanation.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Without a key, everything still works using the keyword parser and template explanations.

## Deploy (shareable link)

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Create an app from this repo, branch `main`, file `app.py`.
3. Optional: in the app's **Secrets**, add `ANTHROPIC_API_KEY = "sk-ant-..."`.

## Demo script (2 minutes)

1. Switch **Market data** to *Sample (offline)* if the Wi-Fi is unreliable.
2. Click the Apple example → walk through "What the agent understood", then the recommendation.
3. Open **Payoff charts** → show the trade-off between capped gains and lower cost.
4. Ask the audience for a view (any stock, any direction) and type it in.
5. For technical audiences, open **Advanced** → greeks and the scenario grid.

## Project layout

```
app.py                  Streamlit UI
agent/view_parser.py    Plain English → structured view (LLM or keyword rules)
agent/market.py         Live data from Yahoo Finance, sample-data fallback
agent/pricing.py        Black-Scholes prices and greeks
agent/strategies.py     Legs, structures, payoffs, breakevens, chance of profit
agent/recommender.py    Strike selection, scoring and explanation
tests/                  Pricing and parser tests (pytest)
```

## Assumptions

European options, Black-Scholes with a simple linear put skew, flat rates, no fees or bid/ask spread, 1 contract = 100 shares. Chance of profit uses the risk-neutral lognormal distribution, so it is market-implied, not a forecast.

Built for learning and demos. Not investment advice.
