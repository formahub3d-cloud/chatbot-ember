"""A0 — il vault stantio (29-07): rendere IMPOSSIBILE indicizzare un vault
vecchio senza saperlo.

Il bug in produzione: pull --ff-only fallisce sugli shallow → si proseguiva in
silenzio con la fotografia del primo clone, per sempre, con workflow verde.
Ora: fetch+reset deterministico; se fallisce → UN clone pulito con trasloco del
contenuto solo-locale (contratti/, write-back: dati del cliente); se fallisce
anche quello → errore. Più: guard sull'età del commit, e commit+data del vault
SEMPRE visibili nella risposta di /ingest e in /admin/brain."""
import subprocess
from pathlib import Path

import pytest

from app import ingest
from app.config import settings


def _fail(*a, **k):
    raise subprocess.CalledProcessError(1, a[0])


# ── il pull fallito NON prosegue mai più in silenzio ─────────────────────────
def test_fetch_fallito_riprova_con_clone_pulito_o_esplode(tmp_path, monkeypatch):
    vp = tmp_path / "vault"
    (vp / ".git").mkdir(parents=True)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[:3])
        raise subprocess.CalledProcessError(1, cmd)          # fallisce TUTTO
    monkeypatch.setattr(ingest.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="né fetch\\+reset né un clone pulito"):
        ingest.sync_vault(str(vp), "https://github.com/x/y.git", "tok")
    # ha tentato fetch E POI il clone pulito: mai «proseguo con la copia locale»
    flat = [" ".join(c) for c in calls]
    assert any("fetch" in c for c in flat)
    assert any("clone" in c for c in flat)


def test_clone_pulito_trasloca_il_contenuto_solo_locale(tmp_path, monkeypatch):
    """I gitignorati (contratti/ ANNIDATI, note private del write-back) sono dati
    del cliente: il clone pulito non deve MAI perderli."""
    vp = tmp_path / "vault"
    (vp / ".git").mkdir(parents=True)
    privato = vp / "forma" / "clienti" / "ats" / "contratti"
    privato.mkdir(parents=True)
    (privato / "unilav-rossi.md").write_text("dati personali", encoding="utf-8")
    (vp / "forma" / "nota-tracciata.md").write_text("vecchia", encoding="utf-8")

    def fake_run(cmd, **kw):
        if "fetch" in cmd or "reset" in cmd:
            raise subprocess.CalledProcessError(1, cmd)       # fetch+reset giù
        if "clone" in cmd:                                    # il clone «riesce»
            dest = Path(cmd[-1])
            (dest / ".git").mkdir(parents=True)
            (dest / "forma").mkdir(parents=True)
            (dest / "forma" / "nota-tracciata.md").write_text("nuova", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(ingest.subprocess, "run", fake_run)
    assert ingest.sync_vault(str(vp), "https://github.com/x/y.git", "tok") is True
    # il vault è la copia NUOVA…
    assert (vp / "forma" / "nota-tracciata.md").read_text(encoding="utf-8") == "nuova"
    # …ma il contenuto solo-locale annidato è stato TRASLOCATO, non perso
    assert (vp / "forma" / "clienti" / "ats" / "contratti" / "unilav-rossi.md").exists()
    # e la copia vecchia non resta in giro
    assert not (tmp_path / "vault.stale").exists()


# ── guard anti-stantio ───────────────────────────────────────────────────────
def _vault_ok(tmp_path):
    d = tmp_path / "v"
    (d / "forma").mkdir(parents=True)
    (d / "forma" / "a.md").write_text("x", encoding="utf-8")
    return d


def test_vault_troppo_vecchio_interrompe(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "vault_path", str(_vault_ok(tmp_path)))
    monkeypatch.setattr(settings, "vault_git_url", "")
    monkeypatch.setattr(settings, "ingest_min_notes", 1)
    monkeypatch.setattr(settings, "ingest_max_vault_age_h", 48)
    monkeypatch.setattr(ingest, "vault_info", lambda *a, **k: {
        "vault_commit": "abc123def456",
        "vault_commit_date": "2026-07-14T10:00:00+02:00"})    # settimane fa
    monkeypatch.setattr(ingest, "client", lambda: (_ for _ in ()).throw(
        AssertionError("con vault stantio NON si arriva a Qdrant")))
    with pytest.raises(RuntimeError, match="fermo al commit abc123def456"):
        ingest.run()


def test_soglia_zero_disattiva_il_guard_eta(tmp_path, monkeypatch):
    from tests.test_p0bis import FakeQdrant
    fake = FakeQdrant()
    monkeypatch.setattr(settings, "vault_path", str(_vault_ok(tmp_path)))
    monkeypatch.setattr(settings, "vault_git_url", "")
    monkeypatch.setattr(settings, "ingest_min_notes", 1)
    monkeypatch.setattr(settings, "ingest_max_vault_age_h", 0)     # disattivato
    monkeypatch.setattr(ingest, "vault_info", lambda *a, **k: {
        "vault_commit": "abc123def456",
        "vault_commit_date": "2026-07-14T10:00:00+02:00"})
    monkeypatch.setattr(ingest, "client", lambda: fake)
    monkeypatch.setattr(ingest, "embed", lambda texts: [[0.0] * 8 for _ in texts])
    out = ingest.run()
    assert out["notes"] == 1


# ── la spia: commit e data del vault nella risposta ──────────────────────────
def test_risposta_ingest_contiene_commit_e_data(tmp_path, monkeypatch):
    from tests.test_p0bis import FakeQdrant
    fake = FakeQdrant()
    monkeypatch.setattr(settings, "vault_path", str(_vault_ok(tmp_path)))
    monkeypatch.setattr(settings, "vault_git_url", "")
    monkeypatch.setattr(settings, "ingest_min_notes", 1)
    monkeypatch.setattr(settings, "ingest_max_vault_age_h", 48)
    from datetime import datetime, timezone
    fresco = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(ingest, "vault_info", lambda *a, **k: {
        "vault_commit": "feed12345678", "vault_commit_date": fresco})
    monkeypatch.setattr(ingest, "client", lambda: fake)
    monkeypatch.setattr(ingest, "embed", lambda texts: [[0.0] * 8 for _ in texts])
    out = ingest.run()
    assert out["vault_commit"] == "feed12345678"
    assert out["vault_commit_date"] == fresco


def test_vault_info_su_repo_vero(tmp_path):
    """vault_info legge commit e data da un repo git reale (formato %H|%cI)."""
    vp = tmp_path / "repo"
    vp.mkdir()
    subprocess.run(["git", "init", "-q", str(vp)], check=True)
    subprocess.run(["git", "-C", str(vp), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-q", "-m", "x"], check=True)
    info = ingest.vault_info(str(vp))
    assert len(info["vault_commit"]) == 12
    assert "T" in info["vault_commit_date"]
