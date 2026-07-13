#!/usr/bin/env python3
"""reingest.py — ri-indicizza il cervello su Ember chiamando POST /ingest.

Tiene il cervello fresco dopo che le note cambiano, senza re-deploy. Pensato per
essere lanciato:
  - a mano  →  python scripts/reingest.py
  - dalla CI (GitHub Actions, vedi .github/workflows/reingest.yml): nightly, on-demand,
    o via repository_dispatch quando il repo del vault viene aggiornato.

Legge la configurazione dall'ambiente (nessun segreto nel codice):
  EMBER_URL     base URL del servizio (default https://ember.formahub.it)
  ADMIN_TOKEN   token admin di Ember (Bearer) — obbligatorio

Solo libreria standard (urllib): nessuna dipendenza da installare in CI.
Exit code: 0 = ingest ok · 1 = errore HTTP/token · 2 = configurazione mancante.
"""
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "https://ember.formahub.it"


def load_paths(raw: str | None) -> list[str] | None:
    """Interpreta INGEST_PATHS: JSON array o lista separata da virgole → lista di path.
    Vuoto/'null' → None (ingest COMPLETO). Isolata per essere testabile."""
    raw = (raw or "").strip()
    if not raw or raw.lower() == "null":
        return None
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            paths = [str(x).strip() for x in v if str(x).strip()]
            return paths or None
    except json.JSONDecodeError:
        pass
    paths = [p.strip() for p in raw.split(",") if p.strip()]
    return paths or None


def build_request(base_url: str, token: str, paths: list[str] | None = None) -> urllib.request.Request:
    """Costruisce la POST /ingest autenticata. Con `paths` → body incrementale
    {"paths":[...]}; senza → nessun body (ingest completo). Isolata per essere testabile."""
    url = base_url.rstrip("/") + "/ingest"
    data = json.dumps({"paths": paths}).encode("utf-8") if paths else None
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    return req


def main() -> int:
    base_url = os.environ.get("EMBER_URL", DEFAULT_URL).strip() or DEFAULT_URL
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        print("⚠️  ADMIN_TOKEN mancante: impostalo nell'ambiente (GitHub secret in CI).")
        return 2

    paths = load_paths(os.environ.get("INGEST_PATHS"))
    req = build_request(base_url, token, paths)
    mode = f"incrementale ({len(paths)} note)" if paths else "completo"
    print(f"Re-ingest {mode} → {req.full_url}")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = resp.read().decode("utf-8", "replace")
        try:
            data = json.loads(body)
            print("✅ ingest ok:", json.dumps(data, ensure_ascii=False))
        except json.JSONDecodeError:
            print("✅ ingest ok:", body[:500])
        return 0
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        print(f"❌ HTTP {e.code}: {detail}")
        if e.code == 401:
            print("   Token admin non valido: controlla ADMIN_TOKEN.")
        return 1
    except urllib.error.URLError as e:
        print(f"❌ Servizio non raggiungibile: {e.reason}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
