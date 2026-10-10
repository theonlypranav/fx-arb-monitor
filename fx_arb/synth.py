"""Generate synthetic, internally consistent FX quotes with injected mispricings.

Used to test the detector end to end without a live feed.

Usage:
    python -m fx_arb.synth out.csv --ticks 5000 --seed 1
"""
from __future__ import annotations

import argparse
import random

from .quotes import Quote, write_quotes_csv

# USD value of one unit of each currency, also the starting point of each random walk.
START_VALUE = {
    "USD": 1.0, "EUR": 1.10, "GBP": 1.27, "JPY": 0.0067, "CHF": 1.12, "AUD": 0.65,
    "CAD": 0.73, "NZD": 0.61, "SGD": 0.74, "INR": 0.012, "NOK": 0.094, "SEK": 0.095, "ZAR": 0.053,
}
# Pairs quoted by the generator: every cross among these currencies.
CURRENCIES = list(START_VALUE)
PAIRS = [(a, b) for i, a in enumerate(CURRENCIES) for b in CURRENCIES[i + 1 :]]


def generate(ticks: int, seed: int = 0, spread_bps: float = 0.5, inject_every: int = 400,
             inject_bps: float = 12.0) -> list[Quote]:
    rng = random.Random(seed)
    # USD value of one unit of each currency (USD = 1). Random walk on each.
    value = dict(START_VALUE)
    quotes: list[Quote] = []
    ts = 1_700_000_000.0

    for tick in range(ticks):
        ts += rng.uniform(0.01, 0.2)
        for c in CURRENCIES:
            if c != "USD":
                value[c] *= 1 + rng.gauss(0, 0.0002)

        # Occasionally break one pair so a cycle becomes profitable.
        broken = None
        if inject_every and tick % inject_every == inject_every - 1:
            broken = rng.choice(PAIRS)

        for base, quote in PAIRS:
            mid = value[base] / value[quote]
            if (base, quote) == broken:
                mid *= 1 + inject_bps / 1e4 * rng.choice([-1, 1])
            half = mid * spread_bps / 2e4
            size = rng.choice([1e6, 2e6, 5e6])
            quotes.append(Quote(ts, base, quote, mid - half, mid + half, size, size))
    return quotes


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic FX quotes.")
    parser.add_argument("out_path")
    parser.add_argument("--ticks", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    quotes = generate(args.ticks, seed=args.seed)
    write_quotes_csv(args.out_path, quotes)
    print(f"Wrote {len(quotes)} quotes to {args.out_path}")


if __name__ == "__main__":
    main()
