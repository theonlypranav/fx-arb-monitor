"""OANDA v20 REST pricing feed: real bid/ask prices with liquidity depth.

Needs a free OANDA practice account. Set OANDA_TOKEN and OANDA_ACCOUNT_ID.
Liquidity is read as units of the base currency (EUR for EUR_USD). Check this
against a live response before trusting max_notional.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .quotes import Quote
from .synth import CURRENCIES

HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

# Cache of the account's instrument names. OANDA's list changes rarely.
_instrument_cache: dict = {"at": 0.0, "names": None}
INSTRUMENT_TTL_S = 3600


def available_instruments(token: str, account_id: str, env: str = "practice", timeout: float = 5.0) -> list[str]:
    """Names of the currency pairs this account can price, e.g. ["EUR_USD", "USD_JPY", ...]."""
    now = time.time()
    if _instrument_cache["names"] is not None and now - _instrument_cache["at"] < INSTRUMENT_TTL_S:
        return _instrument_cache["names"]
    url = f"{HOSTS[env]}/v3/accounts/{account_id}/instruments"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    names = [i["name"] for i in payload.get("instruments", []) if i.get("type") == "CURRENCY"]
    _instrument_cache.update(at=now, names=names)
    return names


def instruments_for(available: list[str], currencies: list[str]) -> list[str]:
    """Keep the pairs where both currencies are in our list. Pairs OANDA doesn't offer drop out."""
    wanted = set(currencies)
    return [name for name in available if len(name.split("_")) == 2 and set(name.split("_")) <= wanted]


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
    names = instruments_for(available_instruments(token, account_id, env, timeout), CURRENCIES)
    if not names:
        raise RuntimeError("account offers no pairs among the configured currencies")
    params = urllib.parse.urlencode({"instruments": ",".join(names)})
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
