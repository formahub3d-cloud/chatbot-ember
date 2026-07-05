"""Rate limiter a finestra scorrevole: sotto/oltre soglia, scadenza della finestra,
limite disabilitato, chiavi indipendenti. Clock iniettato (niente sleep)."""
from app.ratelimit import SlidingWindowLimiter


def test_sotto_e_oltre_soglia():
    rl = SlidingWindowLimiter(window_s=60)
    assert rl.allow("k", 2, now=1000) is True
    assert rl.allow("k", 2, now=1001) is True
    assert rl.allow("k", 2, now=1002) is False        # terza in finestra → bloccata


def test_finestra_scorre():
    rl = SlidingWindowLimiter(window_s=60)
    assert rl.allow("k", 1, now=1000) is True
    assert rl.allow("k", 1, now=1030) is False        # ancora dentro i 60s
    assert rl.allow("k", 1, now=1061) is True         # vecchia uscita dalla finestra


def test_limite_zero_illimitato():
    rl = SlidingWindowLimiter()
    assert all(rl.allow("k", 0, now=t) for t in range(1000, 1100))


def test_chiavi_indipendenti():
    rl = SlidingWindowLimiter(window_s=60)
    assert rl.allow("a", 1, now=1000) is True
    assert rl.allow("b", 1, now=1000) is True         # chiave diversa, contatore separato
    assert rl.allow("a", 1, now=1001) is False
