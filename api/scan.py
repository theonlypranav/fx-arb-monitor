"""Vercel Python function: scan the latest FX snapshot and return opportunities as JSON.

Uses OANDA when OANDA_TOKEN and OANDA_ACCOUNT_ID are set. Otherwise it returns
simulated quotes, labelled as such, so the site still works without a feed.
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_arb.detector import ArbDetector  # noqa: E402
from fx_arb.oanda import fetch_quotes_from_env  # noqa: E402
from fx_arb.synth import CURRENCIES, generate  # noqa: E402


def snapshot():
    """Return (mode, quotes, now). Quotes are one per pair, taken at one moment."""
    live = fetch_quotes_from_env()
    if live is not None:
        return "live", live, time.time()

    # Simulated: a fresh 5-tick walk every 30 s, with one mispricing on tick 5.
    quotes = generate(5, seed=int(time.time()) // 30, inject_every=5)
    last = max(q.ts for q in quotes)
    return "simulated", [q for q in quotes if q.ts == last], last


def run_scan(currency=None):
    """Scan one snapshot. If currency is set, keep only cycles that pass through it."""
    mode, quotes, now = snapshot()
    book = {q.pair: q for q in quotes}
    detector = ArbDetector(
        fee_bps=float(os.environ.get("FEE_BPS", "0.5")),
        min_profit_bps=0.5,
        max_age_s=float(os.environ.get("MAX_AGE_S", "5")),
    )
    opps = detector.scan(book, now)
    if currency:
        opps = [o for o in opps if currency in o.path.split(" -> ")]
    return {
        "mode": mode,
        "as_of": now,
        "pairs": len(book),
        "currency": currency,
        "fee_bps_per_leg": detector.fee_bps,
        "opportunities": [
            {
                "path": o.path,
                "profit_bps": round(o.profit_bps, 3),
                "max_notional": round(o.max_notional, 2),
                "currency": o.legs[0].src,
                "legs": [
                    {
                        "src": leg.src,
                        "dst": leg.dst,
                        "pair": leg.pair,
                        "side": leg.side,
                        "price": leg.price,
                        "rate": leg.rate,
                        "max_src": leg.max_src,
                    }
                    for leg in o.legs
                ],
            }
            for o in opps[:20]
        ],
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        currency = (parse_qs(urlsplit(self.path).query).get("currency") or [""])[0].upper() or None
        if currency and currency not in CURRENCIES:
            status, body = 400, {"error": f"unknown currency; use one of {', '.join(CURRENCIES)}"}
        else:
            try:
                status, body = 200, run_scan(currency)
            except Exception:
                # Log the detail server-side only, so URLs or tokens never reach the client.
                import traceback

                traceback.print_exc()
                status, body = 502, {"error": "feed unavailable"}

        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
