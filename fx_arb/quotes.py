"""Quote records and CSV reading for FX top-of-book data."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import Iterable, Iterator


@dataclass(frozen=True)
class Quote:
    """Top-of-book quote for one currency pair.

    Prices are quote-currency per unit of base (EURUSD = 1.10 means 1 EUR = 1.10 USD).
    Sizes are in units of the base currency.
    """

    ts: float  # epoch seconds
    base: str
    quote: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float

    @property
    def pair(self) -> str:
        return f"{self.base}{self.quote}"


def read_quotes_csv(path: str) -> Iterator[Quote]:
    """Read quotes from a CSV with columns: ts,base,quote,bid,ask,bid_size,ask_size."""
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            yield Quote(
                ts=float(row["ts"]),
                base=row["base"].strip().upper(),
                quote=row["quote"].strip().upper(),
                bid=float(row["bid"]),
                ask=float(row["ask"]),
                bid_size=float(row["bid_size"]),
                ask_size=float(row["ask_size"]),
            )


def write_quotes_csv(path: str, quotes: Iterable[Quote]) -> None:
    fields = ["ts", "base", "quote", "bid", "ask", "bid_size", "ask_size"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for q in quotes:
            writer.writerow({k: getattr(q, k) for k in fields})
