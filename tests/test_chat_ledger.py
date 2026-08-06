"""S5.1c/1 · L'aggancio: la chat scrive nel registro a stream finito.

È l'unico pezzo di questo sprint che tocca il percorso della chat in produzione,
e le tre cose che prova sono quelle che, sbagliate, si vedrebbero soltanto in
bolletta o in un ticket:

  · **si scrive DOPO**, non durante: scrivere da dentro il generatore vorrebbe
    dire farlo mentre l'utente sta ancora leggendo;
  · **si scrive anche se lo stream si interrompe.** Quei token sono stati
    consumati davvero — il `finally` è l'unico posto che li vede in tutti e tre
    i casi (finito, interrotto, abbandonato);
  · **la contabilità non rompe la risposta.** Se il registro esplode, l'utente
    ha comunque letto quello che aveva chiesto.
"""
import pytest
from fastapi.testclient import TestClient

from app import ledger, main, rag, tenants, uso
from app.config import settings

client = TestClient(main.app)

FAKE_TENANT = {"name": "ATS", "allowed_scopes": ["ats"], "allowed_origins": [],
               "branding": {}, "quota_day": 0, "tenant_id": "uuid-ats",
               "org_code": "forma", "code": "ats"}


@pytest.fixture
def chat_finta(monkeypatch):
    """Una chat che risponde e un registro che registra — nessuno dei due vero."""
    scritte = []

    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: FAKE_TENANT if k == "K_ATS" else None)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(ledger, "addebita",
                        lambda tenant, op, u, **kw: scritte.append(
                            {"tenant": tenant.get("code"), "op": op, "uso": u, **kw}))
    return scritte


def _risposta(misura=None, pezzi=("ciao", " mondo"), rompi=False):
    """Un `answer_stream` finto che, se gli danno il misuratore, lo riempie."""
    def _finto(*a, **kw):
        m = kw.get("misura")
        if m is not None and misura is not None:
            for evento in misura:
                m.aggiungi(evento)
        yield 'event: sources\ndata: {"sources": []}\n\n'
        for p in pezzi:
            yield 'data: {"delta": "%s"}\n\n' % p
        if rompi:
            raise RuntimeError("provider caduto a metà")
        yield 'event: done\ndata: {}\n\n'
    return _finto


def _chiedi():
    r = client.post("/chat", json={"message": "ciao", "stream": True},
                    headers={"X-Tenant-Key": "K_ATS"})
    r.read()
    return r


def test_una_chat_misurata_finisce_nel_registro(monkeypatch, chat_finta):
    monkeypatch.setattr(rag, "answer_stream", _risposta(misura=[
        {"usage": {"prompt_tokens": 22, "completion_tokens": 8}}]))
    assert _chiedi().status_code == 200

    assert len(chat_finta) == 1
    riga = chat_finta[0]
    assert riga["tenant"] == "ats" and riga["op"] == "chat"
    assert (riga["uso"].input, riga["uso"].output) == (22, 8)


def test_si_scrive_DOPO_che_lo_stream_e_finito(monkeypatch, chat_finta):
    """Se si scrivesse durante, la riga esisterebbe prima che i token siano
    stati tutti consumati — e il conto sarebbe quello di mezza risposta."""
    ordine = []

    def _finto(*a, **kw):
        m = kw.get("misura")
        yield 'event: sources\ndata: {"sources": []}\n\n'
        ordine.append("primo-delta")
        yield 'data: {"delta": "ciao"}\n\n'
        m.aggiungi({"usage": {"prompt_tokens": 10, "completion_tokens": 4}})
        ordine.append("ultimo-delta")
        yield 'event: done\ndata: {}\n\n'

    monkeypatch.setattr(rag, "answer_stream", _finto)
    monkeypatch.setattr(ledger, "addebita",
                        lambda *a, **k: ordine.append("registro"))
    _chiedi()
    assert ordine == ["primo-delta", "ultimo-delta", "registro"]


def test_uno_stream_INTERROTTO_si_paga_lo_stesso(monkeypatch, chat_finta):
    """Quei token sono stati consumati davvero: il provider li ha generati e ce
    li ha fatturati, anche se l'utente ha visto mezza risposta."""
    monkeypatch.setattr(rag, "answer_stream", _risposta(
        misura=[{"type": "message_start", "message": {"usage": {"input_tokens": 90}}}],
        rompi=True))
    _chiedi()

    assert len(chat_finta) == 1
    assert chat_finta[0]["uso"].input == 90


def test_uno_stream_senza_usage_scrive_comunque_la_riga_IGNOTO(monkeypatch, chat_finta):
    """È il caso di oggi con `MISTRAL_STREAM_USAGE` spento: la riga esiste, e il
    suo conteggio è la prova continua che la misura funziona (o che si è rotta)."""
    monkeypatch.setattr(rag, "answer_stream", _risposta(misura=[]))
    _chiedi()

    assert len(chat_finta) == 1
    assert chat_finta[0]["uso"] is None, "None, non Uso(0,0): non è gratis, è ignoto"


def test_il_registro_che_esplode_NON_rompe_la_risposta(monkeypatch, chat_finta):
    def _rotto(*a, **k):
        raise RuntimeError("pooler giù")

    monkeypatch.setattr(rag, "answer_stream", _risposta(misura=[
        {"usage": {"prompt_tokens": 5, "completion_tokens": 1}}]))
    monkeypatch.setattr(ledger, "addebita", _rotto)

    r = client.post("/chat", json={"message": "ciao", "stream": True},
                    headers={"X-Tenant-Key": "K_ATS"})
    assert r.status_code == 200
    assert "ciao" in r.text, "l'utente legge la risposta anche se la contabilità cade"


def test_il_modello_del_misuratore_e_quello_configurato(monkeypatch, chat_finta):
    monkeypatch.setattr(settings, "llm_provider", "mistral")
    monkeypatch.setattr(settings, "mistral_llm_model", "mistral-small-latest")
    monkeypatch.setattr(rag, "answer_stream", _risposta(misura=[
        {"usage": {"prompt_tokens": 1, "completion_tokens": 1}}]))
    _chiedi()
    assert chat_finta[0]["uso"].modello == "mistral-small-latest"
