from fx_arb.oanda import instruments_for, parse_pricing
from fx_arb.synth import CURRENCIES

# Shaped like OANDA's /v3/accounts/{id}/pricing response.
SAMPLE = {
    "prices": [
        {
            "instrument": "EUR_USD",
            "time": "2026-10-10T12:00:00.123456789Z",
            "tradeable": True,
            "bids": [{"price": "1.10000", "liquidity": 10000000}],
            "asks": [{"price": "1.10020", "liquidity": 10000000}],
        },
        {
            "instrument": "GBP_USD",
            "time": "2026-10-10T12:00:00Z",
            "tradeable": False,
            "bids": [{"price": "1.25000", "liquidity": 1000000}],
            "asks": [{"price": "1.25020", "liquidity": 1000000}],
        },
        {
            "instrument": "USD_JPY",
            "time": "2026-10-10T12:00:00Z",
            "tradeable": True,
            "bids": [],
            "asks": [],
        },
    ]
}


def test_parse_keeps_only_tradeable_priced_entries():
    quotes = parse_pricing(SAMPLE)
    assert [q.pair for q in quotes] == ["EURUSD"]
    q = quotes[0]
    assert (q.bid, q.ask) == (1.10000, 1.10020)
    assert (q.bid_size, q.ask_size) == (10000000, 10000000)


def test_parse_handles_nanosecond_timestamps():
    from datetime import datetime, timezone

    q = parse_pricing(SAMPLE)[0]
    expected = datetime(2026, 10, 10, 12, 0, 0, 123456, tzinfo=timezone.utc).timestamp()
    assert abs(q.ts - expected) < 1e-6


def test_instruments_keep_only_pairs_among_our_currencies():
    available = ["EUR_USD", "USD_INR", "XAU_USD", "EUR_SGD", "USD_EUR_X", "BTC_USD"]
    names = instruments_for(available, CURRENCIES)
    assert names == ["EUR_USD", "USD_INR", "EUR_SGD"]


def test_currency_universe_is_thirteen_with_78_pairs():
    assert len(CURRENCIES) == 13
    assert len(instruments_for(
        [f"{a}_{b}" for i, a in enumerate(CURRENCIES) for b in CURRENCIES[i + 1:]], CURRENCIES)) == 78
