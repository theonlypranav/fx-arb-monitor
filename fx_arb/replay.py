"""Replay recorded quotes through the detector and report new opportunities.

Usage:
    python -m fx_arb.replay quotes.csv --fee-bps 0.5 --min-bps 0.5
"""
from __future__ import annotations

import argparse
import itertools
import statistics
import time
from typing import Callable

from .detector import ArbDetector, Opportunity
from .quotes import Quote, read_quotes_csv


def replay(
    quotes: list[Quote],
    detector: ArbDetector,
    on_opportunity: Callable[[Opportunity], None] | None = None,
) -> dict[str, float]:
    """Feed quotes in time order. Report an opportunity when its path first appears.

    The book is scanned once per timestamp, after every quote sharing that
    timestamp has been applied. Scanning after each individual quote would
    compare pairs from different moments and report phantom arbitrage.

    An opportunity stays "active" while its path keeps showing up on consecutive
    ticks, so one mispricing that lasts many ticks is reported once.
    Returns timing stats for the scans.
    """
    book: dict[str, Quote] = {}
    active: set[str] = set()
    timings_us: list[float] = []
    reported = 0

    ordered = sorted(quotes, key=lambda x: x.ts)
    for ts, group in itertools.groupby(ordered, key=lambda x: x.ts):
        for q in group:
            book[q.pair] = q
        t0 = time.perf_counter()
        opps = detector.scan(book, ts)
        timings_us.append((time.perf_counter() - t0) * 1e6)

        current = {o.path for o in opps}
        for o in opps:
            if o.path not in active:
                reported += 1
                if on_opportunity:
                    on_opportunity(o)
        active = current

    return {
        "ticks": len(quotes),
        "opportunities": reported,
        "scan_us_median": statistics.median(timings_us) if timings_us else 0.0,
        "scan_us_max": max(timings_us) if timings_us else 0.0,
    }


def _print_opp(o: Opportunity) -> None:
    print(
        f"{o.ts:.3f}  {o.path:<24} profit={o.profit_bps:7.2f} bps  "
        f"max_notional={o.max_notional:,.0f} {o.legs[0].src}  "
        f"legs={[leg.pair + ':' + leg.side for leg in o.legs]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay FX quotes and report arbitrage cycles.")
    parser.add_argument("csv_path")
    parser.add_argument("--fee-bps", type=float, default=0.0, help="fee per leg, in bps")
    parser.add_argument("--min-bps", type=float, default=0.5, help="minimum net profit to report")
    parser.add_argument("--max-age", type=float, default=2.0, help="ignore quotes older than this (s)")
    args = parser.parse_args()

    detector = ArbDetector(fee_bps=args.fee_bps, min_profit_bps=args.min_bps, max_age_s=args.max_age)
    stats = replay(list(read_quotes_csv(args.csv_path)), detector, on_opportunity=_print_opp)
    print(
        f"\n{stats['ticks']} ticks, {stats['opportunities']} opportunities. "
        f"scan median {stats['scan_us_median']:.0f} us, max {stats['scan_us_max']:.0f} us"
    )


if __name__ == "__main__":
    main()
