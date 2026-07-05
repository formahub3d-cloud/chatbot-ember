"""RedisLimiter con un client Redis FINTO (niente server): stessa semantica a
finestra scorrevole del limiter in-memory. Clock iniettato."""
from app.ratelimit import RedisLimiter


class _FakeRedis:
    """Simula il minimo indispensabile: sorted-set per chiave."""
    def __init__(self):
        self.z: dict = {}

    def zremrangebyscore(self, key, mn, mx):
        d = self.z.get(key, {})
        rm = [m for m, s in d.items() if mn <= s <= mx]
        for m in rm:
            del d[m]
        return len(rm)

    def zcard(self, key):
        return len(self.z.get(key, {}))

    def zadd(self, key, mapping):
        self.z.setdefault(key, {}).update(mapping)
        return len(mapping)

    def expire(self, key, ttl):
        return True


def test_redis_sotto_e_oltre_soglia():
    rl = RedisLimiter(client=_FakeRedis(), window_s=60)
    assert rl.allow("k", 2, now=1000) is True
    assert rl.allow("k", 2, now=1001) is True
    assert rl.allow("k", 2, now=1002) is False


def test_redis_finestra_scorre():
    rl = RedisLimiter(client=_FakeRedis(), window_s=60)
    assert rl.allow("k", 1, now=1000) is True
    assert rl.allow("k", 1, now=1030) is False
    assert rl.allow("k", 1, now=1061) is True


def test_redis_illimitato():
    rl = RedisLimiter(client=_FakeRedis())
    assert all(rl.allow("k", 0, now=t) for t in range(1000, 1010))


def test_redis_chiavi_indipendenti():
    rl = RedisLimiter(client=_FakeRedis(), window_s=60)
    assert rl.allow("a", 1, now=1000) is True
    assert rl.allow("b", 1, now=1000) is True
    assert rl.allow("a", 1, now=1001) is False
