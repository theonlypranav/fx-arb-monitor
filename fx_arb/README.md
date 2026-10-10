# fx_arb

Detects multi-leg FX arbitrage (triangular and longer loops) on a bid/ask quote book.

## How it works

- Each currency is a node. Converting between currencies uses the price you actually get: the **bid** when selling the base, or **1/ask** when buying the base.
- Bellman-Ford on `-log(rate)` finds loops whose rates multiply to more than 1 after fees.
- Each opportunity reports net profit in bps and `max_notional`, the largest starting amount that fits top-of-book depth on every leg.

## Usage

```bash
python3 -m fx_arb.synth quotes.csv --ticks 5000 --seed 1   # synthetic data
python3 -m fx_arb.replay quotes.csv --fee-bps 0.25 --min-bps 1
python3 -m pytest fx_arb/tests
```

CSV columns: `ts,base,quote,bid,ask,bid_size,ask_size`. Prices are quote per unit of base (EURUSD = 1.10). Sizes are in base units. `ts` is epoch seconds.

## Using it live

`ArbDetector.scan(book, now)` takes the latest quote per pair and returns opportunities. To go live, write a feed that keeps `book` updated and calls `scan` on each snapshot. No live provider is wired in yet.

## Things to know

- **Scan per snapshot, not per message.** Scanning after each update compares pairs from different moments and reports phantom arbitrage. The replay groups quotes by timestamp for this reason. A live feed needs an equivalent window.
- **Fees and spread matter.** Each leg crosses the spread. Small loops are usually eaten by costs.
- **Top of book only.** `max_notional` is a depth estimate. Real fills, latency, and rejects are not modeled.
- **Competition.** Cross-rate arbitrage among major pairs is quickly closed by HFT firms. Expect few real opportunities after costs.
