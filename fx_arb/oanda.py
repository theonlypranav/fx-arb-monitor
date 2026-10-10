"""OANDA v20 REST pricing feed: real bid/ask prices with liquidity depth.

Needs a free OANDA practice account. Set OANDA_TOKEN and OANDA_ACCOUNT_ID.
Liquidity is read as units of the base currency (EUR for EUR_USD). Check this
against a live response before trusting max_notional.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .quotes import Quote

HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

# Every cross among the majors, in market-convention order. OANDA rejects names like USD_EUR,
# so this list can't be built from synth.CURRENCIES, which puts USD first.
INSTRUMENTS = [
    "EUR_USD", "GBP_USD", "AUD_USD", "USD_JPY", "USD_CHF",
    "EUR_GBP", "EUR_JPY", "EUR_CHF", "EUR_AUD",
    "GBP_JPY", "GBP_CHF", "GBP_AUD",
    "AUD_JPY", "AUD_CHF",
    "CHF_JPY",
]


def _parse_time(value: str) -> float:
    """OANDA times are RFC 3339 with nanoseconds. Python only reads microseconds."""
    value = value.rstrip("Z")
    if "." in value:
        head, frac = value.split(".", 1)
        value = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


def parse_pricing(payload: dict) -> list[Quote]:
    """Convert an OANDA /pricing response into Quote records. Skips unusable entries."""
    quotes: list[Quote] = []
    for price in payload.get("prices", []):
        if not price.get("tradeable", False):
            continue
        bids, asks = price.get("bids") or [], price.get("asks") or []
        if not bids or not asks:
            continue
        base, quote = price["instrument"].split("_")
        quotes.append(
            Quote(
                ts=_parse_time(price["time"]),
                base=base,
                quote=quote,
                bid=float(bids[0]["price"]),
                ask=float(asks[0]["price"]),
                bid_size=float(bids[0].get("liquidity", 0)),
                ask_size=float(asks[0].get("liquidity", 0)),
            )
        )
    return quotes


def fetch_quotes(token: str, account_id: str, env: str = "practice", timeout: float = 5.0) -> list[Quote]:
    params = urllib.parse.urlencode({"instruments": ",".join(INSTRUMENTS)})
    url = f"{HOSTS[env]}/v3/accounts/{account_id}/pricing?{params}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_pricing(json.load(response))


def fetch_quotes_from_env() -> list[Quote] | None:
    """Return quotes if OANDA is configured in the environment, otherwise None."""
    token, account_id = os.environ.get("OANDA_TOKEN"), os.environ.get("OANDA_ACCOUNT_ID")
    if not token or not account_id:
        return None
    return fetch_quotes(token, account_id, env=os.environ.get("OANDA_ENV", "practice"))
