# Trade Structuring Agent

Describe a market view in plain English, and the agent designs, prices and compares option trades for it.

> "I think Apple goes up a bit over the next 3 months, and I don't want to spend much"
>
> → **Bull call spread** (buy 230 call, sell 245 call). Costs $655, makes $830 if AAPL reaches $245, max loss $655, 42% market-implied chance of profit. Compared with the risk reversal, it pays more if you are right.

## What it does

The agent runs four steps:

1. **Reads the view.** An LLM through the class app store (or a built-in keyword parser when no model is connected) turns the sentence into structured fields: ticker, direction (bullish, bearish, neutral, volatile, hedge), strength, horizon, budget and risk appetite.
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

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv run --locked python run.py
```

Open `http://localhost:8080`. Without a model connection, the app uses a built-in keyword parser and template explanations, so everything still works.

To use the class model locally, copy `.env.example` to `.env`, paste a development token from the class app store (**Account → Local development token**), and start with:

```bash
uv run --locked --env-file .env python run.py
```

## Publish on the class app store

1. In **My app**, claim the address `trade-structuring-agent` (it must match `slug` in `workshop-app.json`).
2. Build the ZIP:

   ```bash
   uv run --locked python package.py --slug trade-structuring-agent --output ~/Downloads/trade-structuring-agent.zip
   ```

3. Upload the ZIP in **My app** and publish it.

On the store, model usage comes from each visitor's class allowance, and the app uses sample market data (no public internet there).

## Demo script (2 minutes)

1. Switch **Market data** to *Sample (offline)* if the Wi-Fi is unreliable.
2. Click the Apple example → walk through "What the agent understood", then the recommendation.
3. Open **Payoff charts** → show the trade-off between capped gains and lower cost.
4. Ask the audience for a view (any stock, any direction) and type it in.
5. For technical audiences, open **Advanced** → greeks and the scenario grid.

## Project layout

```
app.py                  Streamlit UI
run.py                  Starts the app on the platform's port
agent/broker.py         Model calls through the class app store
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
