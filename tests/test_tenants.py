"""Test dello store tenant: fallback statico (Mongo off) e percorso Mongo (fake)."""
import sys
import types

from app.config import settings
from app import tenants as T
from app.security import hash_key


def test_fallback_mongo_off():
    settings.mongo_uri = ""
    assert T._mongo_enabled() is False
    assert T.get_tenant_by_key("") is None
    # quota illimitata quando Mongo è spento
    assert T.quota_ok({"quota_day": 5, "key_hash": "h"}) is True


class _FakeCol:
    def __init__(self):
        self.docs = []

    def create_index(self, *a, **k):
        pass

    def estimated_document_count(self):
        return len(self.docs)

    def insert_many(self, ds):
        self.docs.extend(ds)

    def find_one(self, q):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return d
        return None

    def update_one(self, q, upd):
        d = self.find_one(q)
        if d:
            d.update(upd.get("$set", {}))

    def find_one_and_update(self, q, upd, upsert=False, return_document=True):
        d = self.find_one(q)
        if not d and upsert:
            d = dict(q)
            d["count"] = 0
            self.docs.append(d)
        if d and "$inc" in upd:
            for k, v in upd["$inc"].items():
                d[k] = d.get(k, 0) + v
        return d


class _FakeDB:
    def __init__(self):
        self.c = {}

    def __getitem__(self, n):
        return self.c.setdefault(n, _FakeCol())


def test_mongo_path(monkeypatch):
    # stub 'pymongo' (l'ambiente sandbox non ha TLS ok; su Railway c'è quello vero)
    fake = types.ModuleType("pymongo")

    class ReturnDocument:
        AFTER = True

    fake.ReturnDocument = ReturnDocument
    monkeypatch.setitem(sys.modules, "pymongo", fake)

    settings.mongo_uri = "mongodb://mock"
    db = _FakeDB()
    monkeypatch.setattr(T, "_mdb", lambda: db)
    monkeypatch.setattr(T, "load_static", lambda: {
        "CHIAVE_X": {"name": "Cliente X", "allowed_scopes": ["x"],
                     "allowed_origins": ["https://x.it"], "branding": {}, "quota_day": 2},
    })

    assert T.mongo_seed() == 1
    t = T.get_tenant_by_key("CHIAVE_X")
    assert t and t["allowed_scopes"] == ["x"]
    assert T.get_tenant_by_key("SBAGLIATA") is None

    # quota 2/giorno → terza chiamata bloccata
    assert T.quota_ok(t) is True
    assert T.quota_ok(t) is True
    assert T.quota_ok(t) is False

    # revoca
    db[settings.tenants_collection].update_one({"key_hash": hash_key("CHIAVE_X")}, {"$set": {"active": False}})
    assert T.get_tenant_by_key("CHIAVE_X") is None

    settings.mongo_uri = ""  # ripristina
