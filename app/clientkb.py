"""V8/B · Il pannello del cliente: la terza persona che non esisteva.

Nel sistema ci sono tre tipi di persone e ne erano implementate due:

    Andrea (owner)          vede tutto il cervello, scrive con approvazione
    Il cliente (ATS)        ⚠️ non esisteva
    I visitatori del sito   vedono solo risposte, non scrivono mai

Il cliente aveva le credenziali (`clientauth`) e una sola porta: la chat. Poteva
parlare col proprio cervello e non poteva GUARDARLO. Questo modulo è la stanza
che gli mancava, ed è fatta di tre cose sole:

1. **La propria knowledge base** — l'elenco delle note che lo riguardano, con
   quando sono state aggiornate. «Ecco le dodici cose che so di voi.» È la frase
   che vende il prodotto al primo incontro, e finora non si poteva dire.

2. **Segnalare un errore** — non correggerlo. Una segnalazione è una proposta
   che arriva nella coda dell'owner. La governance non cambia di una virgola:
   nel vault scrive una persona sola, dopo aver guardato. Il cliente ottiene
   quello che gli serve (essere ascoltato su ciò che lo riguarda) senza che
   nessuno gli dia una penna sul cervello di qualcun altro.

3. **I buchi** — le domande a cui il bot non ha saputo rispondere sui suoi dati.
   Qui c'è l'unico punto delicato del blocco, e vale la pena scriverlo: quelle
   domande le hanno fatte i SUOI utenti finali. Sono dati dei clienti del
   cliente, e il motore gira ancora in US West. Perciò la pagina esiste ma è
   dietro una spunta sul record (`flags.buchi`), spenta di default, e quando è
   spenta lo DICE — «è una decisione da prendere», non una lista vuota che
   sembra «nessun buco».

**Perché prima della raccolta automatica dalle conversazioni.** Le KB dei
clienti stanno fra le 61 e le 77 righe: scheletri, perché in modalità cliente il
pulsante «salva nel cervello» è nascosto (scelta giusta) e quindi crescono solo
se le scrive Andrea a mano. La tentazione è accendere la raccolta automatica.
Dieci minuti del cliente che guarda e corregge valgono più di cento
conversazioni raccolte da sole — e quando la raccolta si accenderà, sarà lui ad
approvare, sulla sua roba: il problema dei dati dei suoi utenti diventa un
accordo invece che una sorpresa.

**Il confine.** Niente qui prende lo scope dalla richiesta: arriva sempre dai
grant della sessione cliente, letti server-side dal cookie. Non si può
falsificare cambiando un campo nel browser — che è la stessa regola del filtro
Qdrant, applicata a una pagina invece che a una risposta.
"""
from __future__ import annotations

import logging
import time
import uuid
from threading import Lock

from . import brain, metrics, tenants
from .config import settings
from .security import cap_input, redact_pii

log = logging.getLogger("ember.clientkb")

STATI = ("aperta", "accolta", "respinta")
MAX_COSA = 800
MAX_APERTE = 50            # tetto per tenant: una coda, non una casella postale

_lock = Lock()
_mem: list[dict] = []      # fallback: si azzera al redeploy, e la console lo dice


def enabled() -> bool:
    """True se le segnalazioni sono PERSISTENTI (Supabase + db/client_report.sql)."""
    return (settings.grants_backend.strip().lower() == "supabase"
            and bool(settings.database_url.strip()))


def _ora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ══════════════════════════════════════════════════════════════════════════
# 1 · «Ecco le dodici cose che so di voi»
# ══════════════════════════════════════════════════════════════════════════
def kb(scopes) -> dict:
    """Le note che riguardano questo cliente, più recenti prima.

    Il filtro è sugli SCOPE della sessione, non su un parametro: è lo stesso
    confine del retrieval, applicato ai metadati invece che ai vettori. Una
    chiave master non arriva mai qui (clientauth la rifiuta alla creazione), ma
    se ci arrivasse per errore verrebbe trattata come nessuno scope: meglio una
    pagina vuota che la knowledge base di tutti dentro il pannello di uno."""
    ammessi = {str(s).strip() for s in (scopes or []) if str(s).strip() and s != "*"}
    if not ammessi:
        return {"note": [], "totale": 0, "scopes": [], "persist": brain.enabled(),
                "vuota_perche": "questo accesso non ha nessuna area assegnata"}
    tutte = brain.notes(limit=400)
    mie = [{"slug": n["slug"], "title": n["title"], "path": n["path"],
            "scope": n["tenant"], "updated_at": n["updated_at"], "tags": n.get("tags") or []}
           for n in tutte if n.get("tenant") in ammessi]
    return {"note": mie, "totale": len(mie), "scopes": sorted(ammessi),
            "persist": brain.enabled(),
            "vuota_perche": "" if mie else (
                "il cervello non ha ancora note nelle vostre aree"
                if brain.enabled() else
                "i metadati delle note non sono disponibili su questo motore")}


# ══════════════════════════════════════════════════════════════════════════
# 2 · «Questa cosa è sbagliata» — una proposta, non una modifica
# ══════════════════════════════════════════════════════════════════════════
def segnala(tenant_code: str, cosa: str, slug: str = "", titolo: str = "",
            da: str = "") -> dict | None:
    """Registra una segnalazione del cliente. NON tocca il vault.

    `tenant_code` arriva dalla sessione, mai dal corpo della richiesta.
    Il testo viene REDATTO (non scartato, a differenza delle proposte da
    conversazione): qui il cliente sta descrivendo un errore, e buttare via la
    segnalazione perché contiene il nome di un referente vorrebbe dire non
    ascoltarlo. Redigere conserva il senso e toglie il dato."""
    tenant_code = (tenant_code or "").strip()
    cosa = redact_pii(cap_input(cosa, MAX_COSA)).strip()
    if not tenant_code or not cosa:
        return None
    slug = cap_input(slug, 120).strip()
    titolo = redact_pii(cap_input(titolo, 200)).strip()
    da = redact_pii(cap_input(da, 120)).strip()
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "INSERT INTO client_report (tenant_code, slug, titolo, cosa, da) "
                        "VALUES (%s,%s,%s,%s,%s) RETURNING rep_id, created_at",
                        (tenant_code, slug, titolo, cosa, da))
                    row = cur.fetchone()
                c.commit()
            return {"id": str(row[0]), "tenant": tenant_code, "slug": slug,
                    "titolo": titolo, "cosa": cosa, "da": da, "stato": "aperta",
                    "created_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])}
        except Exception:
            log.warning("client_report: insert fallito, fallback memoria", exc_info=True)
    with _lock:
        aperte = [r for r in _mem if r["tenant"] == tenant_code and r["stato"] == "aperta"]
        if len(aperte) >= MAX_APERTE:
            return None
        r = {"id": uuid.uuid4().hex, "tenant": tenant_code, "slug": slug,
             "titolo": titolo, "cosa": cosa, "da": da, "stato": "aperta",
             "created_at": _ora(), "chiusa_at": "", "chiusa_da": "", "risposta": ""}
        _mem.append(r)
    return dict(r)


def segnalazioni(tenant_code: str = "", stato: str = "aperta", limit: int = 100) -> list[dict]:
    """Le segnalazioni. Senza `tenant_code` sono TUTTE — solo per la coda
    dell'owner; il pannello cliente passa sempre il proprio."""
    limit = max(1, min(int(limit or 100), 300))
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    sql = ("SELECT rep_id, tenant_code, slug, titolo, cosa, stato, da, "
                           "created_at, chiusa_at, chiusa_da, risposta FROM client_report WHERE 1=1")
                    par: list = []
                    if tenant_code:
                        sql += " AND tenant_code=%s"
                        par.append(tenant_code)
                    if stato:
                        sql += " AND stato=%s"
                        par.append(stato)
                    par.append(limit)
                    cur.execute(sql + " ORDER BY created_at DESC LIMIT %s", par)
                    return [{"id": str(r[0]), "tenant": r[1], "slug": r[2] or "",
                             "titolo": r[3] or "", "cosa": r[4], "stato": r[5],
                             "da": r[6] or "", "created_at": _i(r[7]), "chiusa_at": _i(r[8]),
                             "chiusa_da": r[9] or "", "risposta": r[10] or ""}
                            for r in cur.fetchall()]
        except Exception:
            log.warning("client_report: lettura fallita, fallback memoria", exc_info=True)
    with _lock:
        out = [dict(r) for r in reversed(_mem)
               if (not tenant_code or r["tenant"] == tenant_code)
               and (not stato or r["stato"] == stato)]
    return out[:limit]


def _i(v) -> str:
    if not v:
        return ""
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def chiudi(rep_id: str, stato: str, da: str, risposta: str = "") -> bool:
    """L'owner accoglie o respinge una segnalazione, COL SUO NOME.

    Non è burocrazia: una segnalazione che sparisce senza risposta insegna al
    cliente che non vale la pena segnalare, ed è il modo più veloce per
    spegnere l'unica funzione che fa crescere le sue note."""
    rep_id, da = (rep_id or "").strip(), (da or "").strip()[:80]
    if not rep_id or not da or stato not in ("accolta", "respinta"):
        return False
    risposta = redact_pii(cap_input(risposta, 400)).strip()
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute("UPDATE client_report SET stato=%s, chiusa_at=now(), "
                                "chiusa_da=%s, risposta=%s WHERE rep_id::text=%s "
                                "AND stato='aperta'", (stato, da, risposta, rep_id))
                    tocca = cur.rowcount
                c.commit()
            return bool(tocca)
        except Exception:
            log.warning("client_report: chiusura fallita", exc_info=True)
            return False
    with _lock:
        for r in _mem:
            if r["id"] == rep_id and r["stato"] == "aperta":
                r.update(stato=stato, chiusa_at=_ora(), chiusa_da=da, risposta=risposta)
                return True
    return False


# ══════════════════════════════════════════════════════════════════════════
# 3 · I buchi — dietro una decisione, non un default
# ══════════════════════════════════════════════════════════════════════════
def buchi(tenant_code: str, scopes, consentito: bool) -> dict:
    """Le domande rimaste senza risposta nelle aree del cliente.

    `consentito` NON si decide qui: arriva da `flags.buchi(tenant_code)`, cioè
    dal record del tenant, server-side. Quando è spento la risposta non è una
    lista vuota — è una lista vuota CHE DICE PERCHÉ. Una lista vuota muta
    direbbe «nessun buco», che è la cosa più sbagliata da far credere a un
    cliente il cui bot non sa rispondere."""
    ammessi = {str(s).strip() for s in (scopes or []) if str(s).strip() and s != "*"}
    if not consentito:
        return {"buchi": [], "consentito": False, "totale": 0,
                "perche": ("Le domande rimaste senza risposta le hanno scritte i vostri "
                           "utenti finali: mostrarle qui è una cosa che decidiamo insieme, "
                           "non un'impostazione predefinita. Chiedetelo a FORMA e si accende.")}
    voci = [g for g in metrics.insights()["gaps"] if g.get("scope") in ammessi]
    return {"buchi": voci[:60], "consentito": True, "totale": len(voci), "perche": ""}


def reset() -> None:
    """Solo per i test."""
    with _lock:
        _mem.clear()
