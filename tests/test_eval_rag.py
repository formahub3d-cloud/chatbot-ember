"""Logica di giudizio dell'eval RAG (scripts/eval_rag.py): keyword, min_hit,
expect_gap e falsi 'non lo so'. Offline — nessuna rete."""
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "eval_rag", Path(__file__).resolve().parents[1] / "scripts" / "eval_rag.py")
eval_rag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_rag)

GAP = ["non ho questa informazione", "non lo so"]


def test_keyword_sufficienti():
    ok, why = eval_rag.judge({"keywords": ["forma", "3d"], "min_hit": 2},
                             "FORMA Hub si occupa di stampa 3D.", GAP)
    assert ok and "forma" in why


def test_keyword_insufficienti():
    ok, _ = eval_rag.judge({"keywords": ["qdrant", "scope"], "min_hit": 2},
                           "Risposta generica che cita solo lo scope.", GAP)
    assert not ok


def test_gap_atteso_e_dichiarato():
    ok, _ = eval_rag.judge({"expect_gap": True}, "Mi spiace, non ho questa informazione.", GAP)
    assert ok


def test_gap_atteso_ma_ha_risposto():
    ok, why = eval_rag.judge({"expect_gap": True}, "La carbonara si fa con il guanciale.", GAP)
    assert not ok and "non lo so" in why


def test_falso_gap_su_domanda_in_scope():
    ok, why = eval_rag.judge({"keywords": ["forma"], "min_hit": 1},
                             "Non lo so, non ho questa informazione.", GAP)
    assert not ok and "in scope" in why


def test_eval_set_ben_formato():
    spec = json.loads((Path(__file__).resolve().parents[1] / "eval" / "eval_set.json")
                      .read_text("utf-8"))
    assert len(spec["cases"]) >= 8 and spec["gap_markers"]
    for c in spec["cases"]:
        assert c.get("q") and c.get("key_env")
        assert c.get("expect_gap") or c.get("keywords")
