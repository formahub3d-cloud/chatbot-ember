#!/usr/bin/env python3
"""eval_rag.py — Collaudo automatico della QUALITÀ delle risposte (eval RAG).

Esegue il set di domande di eval/eval_set.json contro un Divina vivo e assegna
un punteggio: ogni caso passa se la risposta contiene le keyword attese
(min_hit tra quelle elencate) oppure — per i casi expect_gap — se il motore
ammette correttamente di non sapere (i "gap marker"). Copre anche l'isolamento
cross-tenant (una chiave ATS non deve leggere il core FORMA).

Uso:
  EVAL_KEY_FORMA=<chiave forma> EVAL_KEY_ATS=<chiave ats> \
  python scripts/eval_rag.py [--base https://divina.formahub.it] [--min 0.8]

I casi la cui chiave (key_env) non è nell'ambiente vengono SALTATI, così si può
lanciare anche con una sola chiave. Exit code 0 se score >= --min, altrimenti 1
(usabile in CI con i secret). Solo stdlib.
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

EVAL_SET = Path(__file__).resolve().parents[1] / "eval" / "eval_set.json"


def ask(base: str, key: str, question: str, timeout: int = 60) -> str:
    req = urllib.request.Request(
        base.rstrip("/") + "/chat",
        data=json.dumps({"message": question, "stream": False}).encode(),
        headers={"Content-Type": "application/json", "X-Tenant-Key": key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return (json.loads(r.read().decode()).get("answer") or "")


def judge(case: dict, answer: str, gap_markers: list) -> tuple[bool, str]:
    """(passato, motivo). Logica pura e testabile offline."""
    low = (answer or "").lower()
    is_gap = any(m in low for m in gap_markers)
    if case.get("expect_gap"):
        return (True, "gap correttamente dichiarato") if is_gap else \
               (False, f"doveva dire 'non lo so', ha risposto: {answer[:80]!r}")
    if is_gap:
        return False, "ha risposto 'non lo so' a una domanda in scope"
    hits = [k for k in case.get("keywords", []) if k.lower() in low]
    need = int(case.get("min_hit", 1))
    if len(hits) >= need:
        return True, f"keyword trovate: {hits}"
    return False, f"keyword insufficienti ({len(hits)}/{need}): trovate {hits}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("EVAL_BASE", "https://divina.formahub.it"))
    ap.add_argument("--min", type=float, default=0.8, help="score minimo per passare (0-1)")
    args = ap.parse_args()

    spec = json.loads(EVAL_SET.read_text("utf-8"))
    gap_markers = spec["gap_markers"]
    run = skipped = passed = 0
    for case in spec["cases"]:
        key = os.environ.get(case["key_env"], "")
        if not key:
            skipped += 1
            print(f"· SKIP  {case['id']} ({case['key_env']} non impostata)")
            continue
        run += 1
        try:
            answer = ask(args.base, key, case["q"])
        except Exception as e:
            print(f"✗ FAIL  {case['id']} — errore di rete: {e}")
            continue
        ok, why = judge(case, answer, gap_markers)
        passed += ok
        print(f"{'✓ PASS' if ok else '✗ FAIL'}  {case['id']} — {why}")
    if not run:
        print("Nessun caso eseguito: imposta EVAL_KEY_FORMA / EVAL_KEY_ATS.")
        return 1
    score = passed / run
    print(f"\nScore: {passed}/{run} = {score:.0%} (soglia {args.min:.0%}; saltati {skipped})")
    return 0 if score >= args.min else 1


if __name__ == "__main__":
    raise SystemExit(main())
