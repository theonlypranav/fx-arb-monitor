from fx_arb.detector import ArbDetector, build_edges, find_negative_cycles
from fx_arb.quotes import Quote


def q(base, quote, bid, ask, ts=100.0, size=1e6):
    return Quote(ts, base, quote, bid, ask, size, size)


def consistent_book(ts=100.0):
    # EURUSD = 1.10, GBPUSD = 1.25, so EURGBP should be 0.88.
    return {
        "EURUSD": q("EUR", "USD", 1.10, 1.10, ts),
        "GBPUSD": q("GBP", "USD", 1.25, 1.25, ts),
        "EURGBP": q("EUR", "GBP", 0.88, 0.88, ts),
    }


def test_consistent_quotes_have_no_arbitrage():
    det = ArbDetector(min_profit_bps=0.1)
    assert det.scan(consistent_book(), now=100.0) == []


def test_mispriced_cross_is_detected_and_priced():
    book = consistent_book()
    # EURGBP offered at 0.80: buy EUR cheaply with GBP.
    book["EURGBP"] = q("EUR", "GBP", 0.80, 0.80)
    det = ArbDetector(min_profit_bps=0.1)
    opps = det.scan(book, now=100.0)
    assert opps, "expected a triangular opportunity"
    best = opps[0]
    # Product of rates around the loop is 1.10 * 0.80 * 1.25 = 1.10 -> 1000 bps.
    assert abs(best.profit_bps - 1000.0) < 1e-6
    assert set(best.path.split(" -> ")) == {"EUR", "USD", "GBP"}
    assert 0 < best.max_notional <= 1e6


def test_fees_can_eliminate_opportunity():
    book = consistent_book()
    book["EURGBP"] = q("EUR", "GBP", 0.80, 0.80)
    det = ArbDetector(fee_bps=400.0, min_profit_bps=0.1)  # 4% per leg swamps 10%
    assert det.scan(book, now=100.0) == []


def test_stale_quotes_are_ignored():
    book = consistent_book(ts=100.0)
    book["EURGBP"] = q("EUR", "GBP", 0.80, 0.80, ts=50.0)  # 50 s old
    det = ArbDetector(min_profit_bps=0.1, max_age_s=2.0)
    assert det.scan(book, now=100.0) == []


def test_depth_limits_notional():
    book = consistent_book()
    book["EURGBP"] = q("EUR", "GBP", 0.80, 0.80, size=1e3)  # thin ask
    det = ArbDetector(min_profit_bps=0.1)
    opps = det.scan(book, now=100.0)
    assert opps
    assert opps[0].max_notional <= 1e3 / 0.88 + 1e-6


def test_cycles_are_deduplicated():
    book = consistent_book()
    book["EURGBP"] = q("EUR", "GBP", 0.80, 0.80)
    edges = build_edges(list(book.values()))
    cycles = find_negative_cycles(edges)
    canon = {tuple(sorted(c)) for c in cycles}
    assert len(cycles) == len(canon)
