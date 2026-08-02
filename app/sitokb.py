"""V9/B · La knowledge base di un cliente nasce dal suo sito, come PROPOSTA.

Il problema, coi numeri: le KB dei cinque clienti stanno fra le 61 e le 77 righe.
Scheletri. E il motivo non è tecnico — **riempirle è lavoro manuale che dipende
dal cliente**, e i clienti non sono ancora stati interpellati. Il risultato è che
per far vedere Divina ad ATS bisognerebbe prima chiedere ad ATS del materiale:
si chiede un favore prima di aver mostrato il valore.

Il ribaltamento è tutto qui. Divina prende **l'indirizzo del sito** e ne ricava
una bozza: chi sono, cosa fanno, servizi, contatti, orari, le domande che un
visitatore farebbe. Poi si apre il pannello del cliente e gli si dice:

    «Guarda: questo è quello che il bot sa già di voi.
     Cosa manca, e cosa è sbagliato?»

**Correggere è cento volte più facile che compilare**, e la conversazione parte
da qualcosa di fatto invece che da un questionario.

## Le tre regole non negoziabili, in codice e non per convenzione

1. **Ogni pezzo porta la sua fonte** — quale URL e quale frase. La citazione si
   verifica LETTERALMENTE contro il testo scaricato: se non si ritrova, la
   proposta cade (`learned._cita_vera`, stessa funzione, non una copia). Una KB
   cliente senza provenienza è peggio di una vuota, perché sembra verificata.
2. **Niente dati personali.** Nomi di dipendenti, email individuali, telefoni
   privati: si SCARTANO, non si redigono — stessa scelta di `learned.py`. Con
   una deroga dichiarata: i recapiti PUBBLICI di un'azienda (l'email `info@`, il
   telefono della sede, l'indirizzo) sono il motivo per cui esiste una sezione
   «Contatti», e un bot che non sa dire dove sei non serve a niente. Quindi la
   voce di tipo `contatti` ammette un recapito **aziendale** e continua a
   rifiutare tutto ciò che sembra una persona.
3. **Nessuna scrittura automatica.** Questo modulo NON scrive: ritorna candidati
   che finiscono nella coda `/admin/proposals`. Vale anche — soprattutto —
   quando le proposte sono trenta e approvarle a mano è noioso.

## Cosa NON fa, e perché

Non naviga il sito da sé. Un motore che scarica un URL deciso da chi fa la
richiesta è un ponte verso la rete interna (SSRF): le pagine le scopre e le
scarica Tavily, e qui entra solo testo. Senza `TAVILY_API_KEY` è inerte e
`degrado.per("kb-da-sito")` lo dichiara nella schermata dove si usa.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse

from . import websearch
from .learned import _cita_vera
from .providers import chat
from .security import cap_input, redact_pii

log = logging.getLogger("ember.sitokb")

MAX_PAGINE = 6           # quante pagine del sito si leggono
MAX_VOCI = 12            # tetto per giro: una coda dove si decide, non un archivio
MIN_TESTO = 400          # sotto questa soglia non c'è un sito, c'è una pagina vuota

# Le sezioni che una scheda cliente ha davvero, nell'ordine in cui servono a un
# bot che risponde. Non è una tassonomia: è l'elenco delle domande che arrivano.
SEZIONI = ("identita", "servizi", "contatti", "orari", "domande")
SEZIONI_IT = {
    "identita": "Chi sono",
    "servizi": "Cosa fanno",
    "contatti": "Contatti",
    "orari": "Orari e sede",
    "domande": "Domande frequenti",
}

# Le pagine che vale la pena cercare dentro un sito: sono le stesse cinque su
# qualunque sito aziendale italiano, e cercarle per nome costa una query sola.
_QUERY = "chi siamo azienda servizi prodotti contatti dove siamo orari"


def _dominio(url: str) -> str:
    try:
        netloc = urlparse(url if "//" in url else "https://" + url).netloc
    except Exception:
        return ""
    return netloc.lower().removeprefix("www.")


def normalizza_url(url: str) -> str:
    """`ats.it` → `https://ats.it`. Vuoto se non sembra un indirizzo."""
    u = (url or "").strip()
    if not u:
        return ""
    if "//" not in u:
        u = "https://" + u
    p = urlparse(u)
    if p.scheme not in ("http", "https") or "." not in p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}"


def leggi(url: str) -> list[dict]:
    """Le pagine del sito → [{url, titolo, testo}]. [] se non si può leggere.

    Due passaggi, entrambi delegati al provider: si SCOPRONO le pagine interne
    con una ricerca ristretta al dominio, poi si ESTRAE il testo. Se l'estrazione
    non è disponibile si ripiega sugli snippet della ricerca: più corti, ma veri
    e con il loro URL — e la citazione si verifica lo stesso, contro quello che
    si è davvero letto."""
    url = normalizza_url(url)
    dom = _dominio(url)
    if not url or not dom or not websearch.enabled():
        return []
    trovate = websearch.search(f"{dom} {_QUERY}", max_results=MAX_PAGINE, domini=[dom])
    # l'home page va sempre inclusa: è quella che dice chi sono, ed è anche
    # quella che una ricerca per parole chiave a volte non restituisce.
    urls, viste = [url], {url}
    for t in trovate:
        u = normalizza_url(t.get("url", ""))
        if u and u not in viste and _dominio(u) == dom:
            viste.add(u)
            urls.append(u)
    urls = urls[:MAX_PAGINE]

    testi = websearch.estrai(urls)
    snippet = {normalizza_url(t.get("url", "")): (t.get("snippet") or "") for t in trovate}
    titoli = {normalizza_url(t.get("url", "")): (t.get("title") or "") for t in trovate}
    pagine = []
    for u in urls:
        testo = (testi.get(u) or snippet.get(u) or "").strip()
        if len(testo) < 80:
            continue
        pagine.append({"url": u, "titolo": titoli.get(u, "") or u, "testo": testo})
    return pagine


_PROMPT = """Sei l'archivista del cervello di FORMA. Qui sotto ci sono le pagine del sito
di un'azienda cliente. Ricavane una BOZZA di scheda: quello che un assistente dovrebbe
sapere per rispondere a chi scrive a quell'azienda.

Regole, tassative:
- da ZERO a {max} voci. Meglio poche e solide che tante e vaghe.
- ogni voce ha una SEZIONE fra: {sezioni}.
- ogni voce ha una CITAZIONE: un frammento COPIATO ALLA LETTERA dalle pagine, fra 15 e
  200 caratteri, e l'URL della pagina da cui viene. Se non puoi copiare una frase che
  lo dimostri, NON scrivere la voce.
- NIENTE persone fisiche: nomi e cognomi di dipendenti, email personali, cellulari
  privati. I recapiti AZIENDALI (info@, telefono della sede, indirizzo) vanno bene e
  stanno nella sezione contatti.
- NON inventare orari, prezzi o servizi che non sono scritti. Se il sito non lo dice,
  la voce non esiste: il buco è un'informazione utile, l'invenzione no.
- la sezione «domande» contiene le domande che un visitatore farebbe DAVVERO, con la
  risposta ricavata dal sito.

Rispondi SOLO con JSON valido, senza testo attorno:
{{"voci": [{{"sezione": "...", "titolo": "...", "contenuto": "...", "citazione": "...", "url": "..."}}]}}

PAGINE:
{pagine}
"""

# Una persona fisica in una scheda aziendale: nome e cognome accanto a un ruolo,
# email personali (nome.cognome@), cellulari. `redact_pii` copre già molto; questo
# aggiunge il caso specifico che su un sito «chi siamo» capita sempre.
_PERSONA = re.compile(
    r"\b[A-Z][a-zà-ù]{2,}\s+[A-Z][a-zà-ù]{2,}\s*[—–\-,(]\s*(?:CEO|founder|fondat|titolar|"
    r"direttor|responsabil|amministrator|social media|marketing manager)", re.I)
_MAIL_PERSONALE = re.compile(r"\b[a-z]+\.[a-z]+@", re.I)


def _senza_persone(*parti: str) -> bool:
    for p in parti:
        t = str(p or "")
        if t and (_PERSONA.search(t) or _MAIL_PERSONALE.search(t)):
            return False
    return True


def _senza_pii(testo: str, sezione: str) -> bool:
    """Regola 2, con la deroga dichiarata per i recapiti AZIENDALI.

    Il controllo sulle PERSONE vale SEMPRE, in ogni sezione: `redact_pii` copre
    email, telefoni e IBAN ma non un nome e cognome accanto a un ruolo, che è
    esattamente quello che c'è su ogni pagina «chi siamo». Metterlo solo nei
    contatti sarebbe stato il buco più grande del blocco.

    La deroga riguarda solo i RECAPITI: fuori dai contatti vale la regola secca
    di `learned.py` (se `redact_pii` cambia il testo, si scarta); nei contatti un
    recapito aziendale è il motivo per cui la sezione esiste — un bot che non sa
    dire dove sei non serve a niente."""
    t = str(testo or "")
    if not t:
        return True
    if not _senza_persone(t):
        return False
    return True if sezione == "contatti" else redact_pii(t) == t


def _parse(raw: str) -> list[dict]:
    testo = str(raw or "").strip()
    if not testo:
        return []
    if not testo.startswith("{"):
        i, j = testo.find("{"), testo.rfind("}")
        if i < 0 or j <= i:
            return []
        testo = testo[i:j + 1]
    try:
        dati = json.loads(testo)
    except Exception:
        log.info("sitokb: risposta non JSON, nessuna proposta")
        return []
    voci = dati.get("voci") if isinstance(dati, dict) else dati
    return [v for v in (voci or []) if isinstance(v, dict)]


def filtra(voci, pagine: list[dict], scope: str) -> list[dict]:
    """Applica le tre regole ai candidati grezzi. Funzione PURA e testabile: è
    qui che si guarda se il disegno regge, non dentro una chiamata LLM."""
    scope = (scope or "").strip().lower()
    if not scope:
        return []
    per_url = {p["url"]: p["testo"] for p in pagine}
    tutto = "\n".join(per_url.values())
    out, visti = [], set()
    for v in voci or []:
        sezione = str(v.get("sezione") or "").strip().lower()
        if sezione not in SEZIONI:
            continue
        titolo = cap_input(str(v.get("titolo") or "").strip(), 160)
        contenuto = cap_input(str(v.get("contenuto") or "").strip(), 1200)
        citazione = str(v.get("citazione") or "").strip()[:300]
        url = normalizza_url(str(v.get("url") or ""))
        if not titolo or not contenuto:
            continue
        # Regola 1 · la citazione deve ritrovarsi DAVVERO. Prima nella pagina
        # dichiarata (così l'URL non è decorativo), poi in tutto il materiale:
        # un modello che sbaglia pagina ma cita bene ha detto una cosa vera con
        # l'indirizzo sbagliato — si tiene la frase, non l'indirizzo.
        fonte = url if (url in per_url and _cita_vera(citazione, per_url[url])) else ""
        if not fonte:
            if not _cita_vera(citazione, tutto):
                log.info("sitokb: scartata (citazione non ritrovata) · %r", titolo[:60])
                continue
            fonte = next((u for u, t in per_url.items() if _cita_vera(citazione, t)), "")
        if not fonte:
            continue
        if not (_senza_pii(titolo, sezione) and _senza_pii(contenuto, sezione)
                and _senza_pii(citazione, sezione)):
            log.info("sitokb: scartata (dati personali) · %r", titolo[:60])
            continue
        chiave = (sezione, titolo.lower())
        if chiave in visti:
            continue
        visti.add(chiave)
        out.append({"sezione": sezione, "titolo": titolo, "contenuto": contenuto,
                    "citazione": citazione, "url": fonte, "scope": scope})
        if len(out) >= MAX_VOCI:
            break
    return out


def proponi(scope: str, url: str) -> dict:
    """Dal sito di un cliente a una bozza di scheda. NON scrive nulla.

    Ritorna {voci, pagine, url, perche} — `perche` è vuoto quando è andata, e
    altrimenti dice in una frase cosa è mancato: senza chiave, sito non
    leggibile, testo troppo poco. Una lista vuota senza spiegazione farebbe
    concludere che il cliente non ha un sito."""
    url = normalizza_url(url)
    if not url:
        return {"voci": [], "pagine": [], "url": "", "perche": "L'indirizzo non è valido."}
    if not websearch.enabled():
        return {"voci": [], "pagine": [], "url": url,
                "perche": "Il sito non si può leggere: manca TAVILY_API_KEY."}
    pagine = leggi(url)
    if not pagine:
        return {"voci": [], "pagine": [], "url": url,
                "perche": "Non è stato possibile leggere nessuna pagina di questo sito."}
    testo_totale = sum(len(p["testo"]) for p in pagine)
    if testo_totale < MIN_TESTO:
        return {"voci": [], "pagine": [p["url"] for p in pagine], "url": url,
                "perche": f"Il sito ha pochissimo testo ({testo_totale} caratteri): "
                          "non c'è abbastanza per ricavarne una scheda."}
    blocco = "\n\n".join(f"--- {p['url']}\n{p['testo'][:6000]}" for p in pagine)
    prompt = _PROMPT.format(max=MAX_VOCI, sezioni=", ".join(SEZIONI), pagine=blocco)
    try:
        raw = chat("Rispondi solo con JSON valido.", prompt)
    except Exception:
        log.warning("sitokb: il modello non ha risposto", exc_info=True)
        return {"voci": [], "pagine": [p["url"] for p in pagine], "url": url,
                "perche": "Il modello non ha risposto: riprova fra poco."}
    voci = filtra(_parse(raw), pagine, scope)
    perche = ""
    if not voci:
        perche = ("Le pagine sono state lette, ma nessuna voce ha superato i controlli: "
                  "o le frasi citate non si ritrovavano nel testo, o contenevano dati "
                  "di persone. Meglio zero voci che una scheda che sembra verificata.")
    return {"voci": voci, "pagine": [p["url"] for p in pagine], "url": url, "perche": perche}
