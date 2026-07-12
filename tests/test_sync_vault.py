"""Auto-ingest: aggiornamento del vault da git prima dell'indicizzazione.

Tutto offline: subprocess è mockato, nessun comando git reale viene eseguito.
Verifica: clone quando manca .git, pull quando c'è, no-op se url vuoto, iniezione
sicura del token (mai nei log), e la politica di gestione errori (pull best-effort,
clone fatale)."""
import logging
import subprocess

import pytest

from app import ingest


def _fake_run(calls):
    """Ritorna un finto subprocess.run che registra gli argv e simula successo."""
    def run(cmd, **kw):
        calls.append((list(cmd), kw))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return run


# ── no-op: url vuoto → nessuna chiamata git, comportamento storico ────────────
def test_url_vuoto_nessuna_chiamata(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ingest.subprocess, "run", _fake_run(calls))
    assert ingest.sync_vault(str(tmp_path), "", "") is False
    assert calls == []                       # subprocess NON invocato


# ── clone: cartella senza .git → git clone --depth 1 ──────────────────────────
def test_clone_quando_manca_git(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ingest.subprocess, "run", _fake_run(calls))
    dest = tmp_path / "vault"          # non esiste ancora, niente .git
    assert ingest.sync_vault(str(dest), "https://github.com/acme/ovy-cervello.git", "") is True
    assert len(calls) == 1
    argv = calls[0][0]
    assert argv[:4] == ["git", "clone", "--depth", "1"]
    assert argv[-1] == str(dest)
    assert calls[0][1].get("shell") is not True   # mai shell=True


# ── pull: cartella con .git → git pull --ff-only ──────────────────────────────
def test_pull_quando_git_esiste(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    calls = []
    monkeypatch.setattr(ingest.subprocess, "run", _fake_run(calls))
    assert ingest.sync_vault(str(tmp_path), "https://github.com/acme/ovy-cervello.git", "") is True
    assert len(calls) == 1
    argv = calls[0][0]
    assert argv == ["git", "-C", str(tmp_path), "pull", "--ff-only"]
    assert calls[0][1].get("shell") is not True


# ── token: iniettato nell'URL del clone ma MAI nei log ────────────────────────
def test_token_iniettato_nell_url_del_clone(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ingest.subprocess, "run", _fake_run(calls))
    dest = tmp_path / "vault"
    ingest.sync_vault(str(dest), "https://github.com/acme/cervello.git", "SECRETTOKEN")
    argv = calls[0][0]
    clone_url = argv[4]
    assert clone_url == "https://x-access-token:SECRETTOKEN@github.com/acme/cervello.git"


def test_token_non_compare_nei_log_su_errore(monkeypatch, tmp_path, caplog):
    """Se git fallisce, l'errore (che può riecheggiare l'URL con token) va redatto."""
    def boom(cmd, **kw):
        # git riecheggia l'URL con credenziali nel messaggio d'errore: deve sparire dai log.
        raise subprocess.CalledProcessError(
            128, cmd,
            stderr="fatal: could not read from https://x-access-token:SECRETTOKEN@github.com/acme/cervello.git",
        )
    monkeypatch.setattr(ingest.subprocess, "run", boom)
    dest = tmp_path / "vault"
    with caplog.at_level(logging.ERROR, logger="ember.ingest"):
        with pytest.raises(RuntimeError):
            ingest.sync_vault(str(dest), "https://github.com/acme/cervello.git", "SECRETTOKEN")
    assert "SECRETTOKEN" not in caplog.text            # token redatto ovunque nei log
    assert "***@github.com" in caplog.text             # URL redatto presente


# ── politica errori: pull best-effort (prosegue), clone fatale (solleva) ──────
def test_pull_fallito_prosegue_senza_sollevare(monkeypatch, tmp_path, caplog):
    (tmp_path / ".git").mkdir()

    def boom(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd, stderr="network blip")
    monkeypatch.setattr(ingest.subprocess, "run", boom)
    with caplog.at_level(logging.WARNING, logger="ember.ingest"):
        # NON solleva: c'è già una copia locale, si prosegue con quella.
        assert ingest.sync_vault(str(tmp_path), "https://github.com/acme/c.git", "") is True
    assert "proseguo con la copia locale" in caplog.text


def test_clone_fallito_solleva_runtimeerror(monkeypatch, tmp_path):
    def boom(cmd, **kw):
        raise subprocess.CalledProcessError(128, cmd, stderr="repo not found")
    monkeypatch.setattr(ingest.subprocess, "run", boom)
    dest = tmp_path / "vault"
    with pytest.raises(RuntimeError):
        ingest.sync_vault(str(dest), "https://github.com/acme/missing.git", "")


# ── redazione URL: helper puro ────────────────────────────────────────────────
def test_redact_url_toglie_le_credenziali():
    red = ingest._redact_url("https://x-access-token:abc123@github.com/acme/c.git")
    assert "abc123" not in red and red == "https://***@github.com/acme/c.git"
    # URL senza credenziali resta invariato
    assert ingest._redact_url("https://github.com/acme/c.git") == "https://github.com/acme/c.git"
