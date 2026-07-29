"""Parità del perimetro: il motore e i generatori del vault devono contare le
STESSE note (rilievo revisione A1, 29-07 — divergevano di 2 per i file nella
radice del vault, intercettati per nome dal generatore e non dal motore).

Confronta due implementazioni indipendenti della stessa regola:
  - quella del motore (app.ingest.is_note_included — LA regola, usata da
    ingest completo e incrementale);
  - la trascrizione letterale della regola dei generatori del vault
    (ovy-cervello/build.py + quality_gate.py, aggiornati dalla PR gemella).
Se una delle due parti cambia da sola, questo script (e il test in CI che lo
usa su un albero-fixture) se ne accorge.

Uso:  python scripts/count_notes.py /percorso/del/vault
Exit: 0 = stessi insiemi · 1 = divergono (stampa le differenze)
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.ingest import is_note_included  # noqa: E402

# Trascrizione LETTERALE della regola dei generatori del vault (build.py:
# iter_md salta le parti che iniziano con '.', is_skipped salta le cartelle in
# SKIP_NAMES e le note in RADICE; _index esclusi nel loop). Se ovy-cervello
# cambia la regola, va cambiata anche qui — è il punto del confronto.
VAULT_SKIP_NAMES = {"_showcase", "_templates", "_bozze",
                    "contratti", "chatbot-jarvis", "chatbot-ember"}


def vault_rule(rel: Path) -> bool:
    if any(p.startswith(".") for p in rel.parts):
        return False
    if rel.suffix != ".md" or rel.stem == "_index":
        return False
    if len(rel.parts) < 2:                    # note in radice: fuori
        return False
    return not any(p in VAULT_SKIP_NAMES for p in rel.parts[:-1])


def count(vault: Path):
    engine, generator = set(), set()
    for md in sorted(vault.rglob("*.md")):
        rel = md.relative_to(vault)
        if is_note_included(rel):
            engine.add(str(rel))
        if vault_rule(rel):
            generator.add(str(rel))
    return engine, generator


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    vault = Path(sys.argv[1])
    if not vault.is_dir():
        print(f"vault non trovato: {vault}")
        return 2
    engine, gen = count(vault)
    print(f"motore:     {len(engine)} note")
    print(f"generatori: {len(gen)} note")
    if engine == gen:
        print("PARITÀ ✓ — stessi insiemi")
        return 0
    for extra in sorted(engine - gen):
        print(f"  solo motore:     {extra}")
    for extra in sorted(gen - engine):
        print(f"  solo generatori: {extra}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
