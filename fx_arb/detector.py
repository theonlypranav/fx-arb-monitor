"""Multi-leg FX arbitrage detection on a bid/ask quote book.

Each currency is a node. Converting one currency into another is an edge whose
rate is the price you actually get: the bid when selling base, or 1/ask when
buying base with quote. A cycle whose rates multiply to more than 1 (after fees)
is a risk-free profit if all legs fill at top of book.

Bellman-Ford on weights -log(rate) finds negative cycles, i.e. profitable loops.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .quotes import Quote


@dataclass(frozen=True)
class Leg:
    src: str
    dst: str
    rate: float  # units of dst received per unit of src, after fees
    max_src: float  # most units of src this leg can absorb at top of book
    pair: str
    side: str  # "sell" (hit the bid) or "buy" (lift the ask)
    price: float  # the quoted bid or ask, before fees, in quote currency per unit of base


@dataclass(frozen=True)
class Opportunity:
    ts: float
    legs: tuple[Leg, ...]
    profit_bps: float  # net of fees, per unit of starting currency
    max_notional: float  # largest starting amount that fits top-of-book depth

    @property
    def path(self) -> str:
        nodes = [self.legs[0].src] + [leg.dst for leg in self.legs]
        return " -> ".join(nodes)


def build_edges(quotes: list[Quote], fee_bps: float = 0.0) -> dict[tuple[str, str], Leg]:
    """Best top-of-book edge for each (src, dst) currency pair."""
    keep = 1.0 - fee_bps / 1e4
    best: dict[tuple[str, str], Leg] = {}

    def offer(leg: Leg) -> None:
        key = (leg.src, leg.dst)
        current = best.get(key)
        if current is None or leg.rate > current.rate:
            best[key] = leg

    for q in quotes:
        if q.bid > 0 and q.bid_size > 0:
            offer(Leg(q.base, q.quote, q.bid * keep, q.bid_size, q.pair, "sell", q.bid))
        if q.ask > 0 and q.ask_size > 0:
            # Spend quote currency to buy base. Depth in quote units is ask_size * ask.
            offer(Leg(q.quote, q.base, keep / q.ask, q.ask_size * q.ask, q.pair, "buy", q.ask))
    return best


def _canonical(cycle: list[str]) -> tuple[str, ...]:
    i = cycle.index(min(cycle))
    return tuple(cycle[i:] + cycle[:i])


def find_negative_cycles(edges: dict[tuple[str, str], Leg]) -> list[list[str]]:
    """Return distinct cycles (node lists, forward order) with rate product > 1."""
    nodes = sorted({n for pair in edges for n in pair})
    weighted = [(u, v, -math.log(leg.rate)) for (u, v), leg in edges.items()]

    dist = {n: 0.0 for n in nodes}  # virtual source connected to every node
    pred: dict[str, str | None] = {n: None for n in nodes}
    updated: list[str] = []
    for _ in range(len(nodes)):
        updated = []
        for u, v, w in weighted:
            if dist[u] + w < dist[v] - 1e-12:
                dist[v] = dist[u] + w
                pred[v] = u
                updated.append(v)
        if not updated:
            return []

    cycles: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for v in updated:
        # Walk back far enough to be guaranteed to be inside a cycle.
        x = v
        for _ in range(len(nodes)):
            x = pred[x]
        cycle = [x]
        y = pred[x]
        while y != x:
            cycle.append(y)
            y = pred[y]
        cycle.reverse()
        key = _canonical(cycle)
        if key not in seen:
            seen.add(key)
            cycles.append(cycle)
    return cycles


def evaluate_cycle(cycle: list[str], edges: dict[tuple[str, str], Leg], ts: float) -> Opportunity:
    """Price a cycle: profit in bps and the largest starting notional the depth supports."""
    legs = tuple(edges[(cycle[i], cycle[(i + 1) % len(cycle)])] for i in range(len(cycle)))
    prefix = 1.0  # units of the current holding per unit of starting currency
    max_notional = math.inf
    for leg in legs:
        # Holding before this leg is notional * prefix, which must fit within leg.max_src.
        max_notional = min(max_notional, leg.max_src / prefix)
        prefix *= leg.rate
    return Opportunity(ts=ts, legs=legs, profit_bps=(prefix - 1.0) * 1e4, max_notional=max_notional)


class ArbDetector:
    def __init__(self, fee_bps: float = 0.0, min_profit_bps: float = 0.5, max_age_s: float = 2.0):
        self.fee_bps = fee_bps
        self.min_profit_bps = min_profit_bps
        self.max_age_s = max_age_s

    def scan(self, book: dict[str, Quote], now: float) -> list[Opportunity]:
        """Scan the latest quote per pair. Stale quotes (older than max_age_s) are ignored."""
        fresh = [q for q in book.values() if now - q.ts <= self.max_age_s]
        edges = build_edges(fresh, self.fee_bps)
        opps = [evaluate_cycle(c, edges, now) for c in find_negative_cycles(edges)]
        found = [o for o in opps if o.profit_bps >= self.min_profit_bps]
        return sorted(found, key=lambda o: -o.profit_bps)
