"""V10/C · Le cinque prove della conversazione vera.

In quattro giri sono state aggiunte sei cose — il tono per tutti, il muro che
diventa porta, il filo che espande la domanda di seguito, la memoria delle
preferenze, i riassunti compressi, le capacità raggiungibili parlando — tutte
fatte bene, e l'area «conversazione» è passata da 4 a 6. Il problema è che sono
**sei funzioni, e una conversazione non è una somma di funzioni**.

Il criterio, al posto dell'elenco: *una conversazione funziona quando chi parla
non deve pensare a come parlare.* Oggi Divina risponde bene se le fai la domanda
giusta nel modo giusto. Queste sono le cinque prove che contano, e prima di
questo modulo non ne passava nessuna:

    «Aspetta, non intendevo quello»   torna indietro di un turno, non ricomincia
    «E l'altro?» (dopo due clienti)   chiede QUALE, invece di indovinare
    «Lascia stare, dimmi invece…»     abbandona il filo senza rispondere lo stesso
    «Ma sei sicura?»                  riapre la fonte, non ripete con altre parole
    silenzio, poi «allora?»           riprende dal punto dove si era fermata

**La scelta di fondo.** Una mossa di conversazione non cambia il TONO della
risposta: cambia **cosa si va a cercare**. È questa la differenza fra sei
funzioni e una conversazione, ed è anche l'unica versione testabile senza
chiamare il modello. «Aspetta, non intendevo quello» seguito dall'espansione
lessicale del filo rimette nella query *proprio la frase che la persona ha appena
ritirato*: più contesto, più sbagliato. Qui la mossa decide la query PRIMA, e il
filo espande solo quando ha senso.

**Il caso ambiguo non arriva nemmeno al modello.** Con due soggetti in ballo e un
«e l'altro?», la risposta giusta è una domanda, e una domanda non ha bisogno di
un LLM né di un retrieval: si compone dai due nomi che sono già nel filo. Costa
zero, arriva subito (conta a voce) e soprattutto **non può indovinare**, che è il
comportamento che si vuole escludere.

Il limite di sempre: niente qui allarga i permessi. Le mosse cambiano la query e
il modo di rispondere; lo scope si ricalcola dai grant, come prima e come sempre.
"""
from __future__ import annotations

import re

from . import filo

MOSSE = ("correzione", "ambiguo", "abbandono", "dubbio", "ripresa", "normale")

# Una mossa si riconosce da come si apre il turno, non da una parola persa in
# mezzo: «non intendevo» all'inizio è una correzione, la stessa dentro una frase
# lunga è cronaca. Prudenza deliberata — un falso negativo lascia il
# comportamento di prima (che funziona), un falso positivo cambia la query.
_CORREZIONE = re.compile(
    r"(?i)^\W*(?:aspetta|no[,!.]|nì|non\s+intendevo|non\s+volevo\s+dire|"
    r"mi\s+sono\s+spiegat[oa]\s+male|non\s+è\s+quello|intendevo|volevo\s+dire|"
    r"scusa[,]?\s+intendevo|forse\s+mi\s+sono\s+spiegat)")
_ABBANDONO = re.compile(
    r"(?i)^\W*(?:lascia\s+(?:stare|perdere)|non\s+importa|fa\s+niente|"
    r"vabb[eè]|niente|cambiamo\s+discorso|passiamo\s+ad\s+altro)\b")
_DUBBIO = re.compile(
    r"(?i)^\W*(?:ma\s+)?(?:sei\s+sicur[oa]|sicur[oa]\?|davvero\?|"
    r"non\s+mi\s+convince|sei\s+certa?|è\s+proprio\s+così|"
    r"da\s+dove\s+(?:lo\s+)?(?:l')?hai\s+pres|ne\s+sei\s+sicur[oa])")
_RIPRESA = re.compile(
    r"(?i)^\W*(?:allora|e\s+quindi|quindi|dunque|dimmi|continua|vai|"
    r"e\s+poi|dicevi)\W*$")
# L'anafora NUDA: «e l'altro?», «e quello?», «e lui?». Corta per definizione —
# se la persona ha aggiunto di che cosa parla, non è più ambigua.
_ANAFORA_NUDA = re.compile(
    r"(?i)^\W*(?:e\s+)?(?:l'altr[oa]|gli\s+altri|le\s+altre|quell[oa]|quest[oa]|"
    r"lui|lei|loro|il\s+secondo|l'altro\s+invece)\W*\??\W*$")
# Dopo «lascia stare» spesso arriva subito la domanda nuova.
_INVECE = re.compile(r"(?i)\b(?:invece|piuttosto|semmai)\b[,:]?\s*(.+)$")

MAX_NUDA = 32          # oltre, la domanda porta già il suo soggetto


def _ultima_utente(turni: list[dict]) -> str:
    for t in reversed(turni or []):
        if t.get("role") == "user":
            return (t.get("content") or "").strip()
    return ""


# Un «soggetto candidato» è un nome proprio: maiuscola non a inizio frase, o una
# sigla tutta maiuscola (ATS, FORMA). Volutamente grezzo: serve a capire se in
# ballo ce n'è UNO o DUE, non a fare analisi linguistica.
_PAROLA = re.compile(r"\b([A-ZÀ-Þ][\wÀ-ÿ'’]{1,}|[A-Z]{2,})\b")
_INIZIALI = {"Ciao", "Salve", "Grazie", "Divina", "Se", "Il", "La", "Lo", "Gli",
             "Le", "Un", "Una", "Che", "Come", "Cosa", "Quale", "Quali", "Dove",
             "Quando", "Perché", "Mi", "Ti", "Ci", "Non", "Aspetta", "No", "E",
             "Ma", "Poi", "Allora", "Quindi", "Sono", "Ho", "Vorrei", "Puoi",
             "Dimmi", "Parlami", "Fammi", "Sì", "Ok", "Va", "Adesso", "Oggi"}


def candidati(turni: list[dict]) -> list[str]:
    """I soggetti in ballo nel filo, dal più recente. Si guardano SOLO i turni
    dell'utente: i nomi che compaiono nelle risposte di Divina sono spesso
    ripetizioni o contorno, e contarli farebbe sembrare ambiguo un filo che non
    lo è."""
    visti: list[str] = []
    for t in reversed(turni or []):
        if t.get("role") != "user":
            continue
        testo = t.get("content") or ""
        for i, m in enumerate(_PAROLA.finditer(testo)):
            p = m.group(1)
            if p in _INIZIALI or (i == 0 and m.start() == 0 and p not in ("ATS", "FORMA")):
                continue
            if p not in visti:
                visti.append(p)
        if len(visti) >= 4:
            break
    return visti


def mossa(domanda: str, turni: list[dict] | None = None) -> str:
    """Che mossa di conversazione è questo turno. Senza filo è sempre `normale`:
    tutte e cinque le mosse si appoggiano a ciò che è stato detto prima, e senza
    un prima non esistono."""
    d = (domanda or "").strip()
    turni = turni or []
    if not d or not turni:
        return "normale"
    if _ABBANDONO.search(d):
        return "abbandono"
    if _CORREZIONE.search(d):
        return "correzione"
    if _DUBBIO.search(d):
        return "dubbio"
    if len(d) <= MAX_NUDA and _ANAFORA_NUDA.search(d) and len(candidati(turni)) >= 2:
        return "ambiguo"
    if len(d) <= MAX_NUDA and _RIPRESA.search(d):
        return "ripresa"
    return "normale"


def query(domanda: str, turni: list[dict] | None = None, m: str | None = None) -> str:
    """Il testo con cui CERCARE, deciso dalla mossa. Mai quello che si mostra.

    Le tre righe che contano davvero:

    - **correzione**: il turno appena ritirato ESCE dall'espansione. Il filo, da
      solo, rimetterebbe nella query proprio la frase che la persona ha detto di
      non aver inteso — più contesto e più sbagliato.
    - **abbandono**: il filo si taglia. Se dopo «lascia stare» c'è un «invece…»,
      si cerca quello e basta; se non c'è niente, non si cerca niente.
    - **dubbio** e **ripresa**: non sono domande nuove. Si cerca la DOMANDA DI
      PRIMA, che è ciò di cui si sta parlando — cercare «ma sei sicura?» nel
      vault non trova niente, e infatti finiva nel muro.
    """
    d = (domanda or "").strip()
    turni = turni or []
    m = m or mossa(d, turni)
    if m == "abbandono":
        nuovo = _INVECE.search(d)
        return (nuovo.group(1).strip() if nuovo else "")
    if m == "correzione":
        # Solo i turni utente PRECEDENTI a quello ritirato, più ciò che la
        # correzione stessa porta di nuovo.
        utente = [t["content"] for t in turni if t["role"] == "user"]
        prima = utente[:-1][-1:] if len(utente) >= 2 else []
        return " ".join(prima + [d]).strip()[:filo.MAX_CHARS_TURNO]
    if m in ("dubbio", "ripresa"):
        return _ultima_utente(turni) or d
    if m == "ambiguo":
        return d            # non si cerca: si chiede. Qui per completezza.
    return filo.query_retrieval(d, turni)


def chiarimento(domanda: str, turni: list[dict] | None = None) -> dict | None:
    """La domanda di ritorno per il caso ambiguo — senza modello e senza retrieval.

    «E l'altro?» con due soggetti in ballo ha esattamente una risposta corretta, e
    non è una risposta: è «quale dei due?». Comporla dai nomi che sono già nel
    filo costa zero, arriva subito (a voce conta) e **non può indovinare** — che è
    il comportamento che si vuole rendere impossibile, non solo improbabile."""
    c = candidati(turni or [])
    if len(c) < 2:
        return None
    due = c[:2]
    return {"answer": f"Quale dei due, {due[1]} o {due[0]}? "
                      "Così non tiro a indovinare.",
            "candidati": due}


# ── Cosa dire al modello, quando la mossa non si risolve da sola ─────────────
_ISTRUZIONI_IT = {
    "correzione": " MOSSA: la persona ti sta CORREGGENDO. Torna indietro di UN turno e"
                  " riparti da lì: non ricominciare da capo, non ripetere quello che hai"
                  " già detto e non scusarti più di mezza riga. Se ha detto cosa"
                  " intendeva davvero, rispondi a quello.",
    "abbandono": " MOSSA: la persona ha ABBANDONATO l'argomento di prima. Non rispondere"
                 " lo stesso alla domanda vecchia e non riassumerla: se ne ha posta una"
                 " nuova rispondi solo a quella, altrimenti chiudi in una riga.",
    "dubbio": " MOSSA: la persona DUBITA della risposta che hai appena dato. Non"
              " riformularla con altre parole: torna alla fonte, di' cosa c'è scritto"
              " esattamente e cosa invece NON c'è, e se il CONTENUTO non basta a"
              " sostenerla dillo apertamente. Cambiare parole per sembrare più"
              " convincenti è la cosa peggiore che puoi fare qui.",
    "ripresa": " MOSSA: la persona ti sta chiedendo di RIPRENDERE il discorso rimasto in"
               " sospeso. Ripartia dal punto dove eri arrivata, senza reintrodurre"
               " l'argomento da capo e senza ripetere ciò che hai già detto.",
}
_ISTRUZIONI_EN = {
    "correzione": " MOVE: they are CORRECTING you. Go back ONE turn and restart from"
                  " there: do not start over, do not repeat yourself, keep the apology"
                  " under half a line.",
    "abbandono": " MOVE: they DROPPED the previous topic. Do not answer the old question"
                 " anyway and do not summarise it: answer only the new one, or close in"
                 " one line.",
    "dubbio": " MOVE: they DOUBT the answer you just gave. Do not rephrase it: go back to"
              " the source, say what it actually states and what it does NOT, and admit"
              " it if the CONTENT does not support the claim.",
    "ripresa": " MOVE: they are asking you to RESUME the unfinished thread. Continue from"
               " where you stopped, without reintroducing the topic.",
}


def istruzione(m: str, lang: str = "it") -> str:
    """La riga che si aggiunge al system prompt per questa mossa ('' se nessuna)."""
    tab = _ISTRUZIONI_EN if str(lang or "").lower().startswith("en") else _ISTRUZIONI_IT
    return tab.get(m or "", "")


# ── C2 · Le domande che non riguardano il cervello ───────────────────────────
# «Che ore sono a New York», «come si scrive un'email di sollecito». Il cervello
# non c'entra, e la risposta giusta non è né il muro né la porta: è rispondere —
# per l'owner e per il tenant con `libera`. Il vincolo di C3 resta intero: senza
# quel permesso il muro non si tocca, perché il widget sul sito di un cliente non
# può inventare sul cliente.
#
# Quello che cambia qui è UNA cosa e piccola: non si offre di scrivere una nota
# nel vault. Offrire di annotare l'ora di New York è la porta aperta sul niente,
# e riempirebbe il cervello di spazzatura con la nostra firma sopra.
_GENERICA = re.compile(
    r"(?i)^\W*(?:che\s+ore\s+sono|che\s+giorno\s+è|quanto\s+fa\b|"
    r"come\s+si\s+(?:scrive|dice|fa\s+a|calcola|traduce)\b|"
    r"cosa\s+(?:significa|vuol\s+dire)\b|che\s+differenza\s+c'è\s+tra\b|"
    r"traduci\b|scrivimi\s+un(?:'|a\s+)?(?:email|mail|lettera|testo)\b|"
    r"dammi\s+un(?:'|a\s+)?idea\b|spiegami\s+(?:in\s+parole\s+semplici|il\s+concetto)\b)")


def generica(domanda: str, nomi=()) -> bool:
    """La domanda riguarda il mondo, non il cervello di FORMA?

    Prudente in un verso solo, e il verso conta. «Come si fa a fatturare ad ATS»
    ha la FORMA di una domanda generale ed è una domanda sul cervello:
    sopprimerle l'offerta di colmare il buco sarebbe il danno vero, perché il
    buco esiste e nessuno lo saprebbe.

    Il discrimine non può essere «c'è un nome proprio» — «New York» ne ha due e
    non c'entra niente col cervello. È **il mondo del tenant**: `nomi` sono i
    suoi scope (ats, forma-core, andrea…), cioè esattamente ciò di cui il
    cervello potrebbe sapere qualcosa. Se la domanda ne nomina uno, non è
    generica, punto. Chiamata senza `nomi` resta prudente e dice di sì solo
    sulla forma."""
    d = (domanda or "").strip()
    if not d or not _GENERICA.search(d):
        return False
    basso = d.lower()
    parole = set(re.findall(r"[\wÀ-ÿ']+", basso))
    for n in list(nomi or []) + ["forma", "divina", "ovyon"]:
        for pezzo in re.split(r"[-_/\s]+", str(n or "").lower()):
            if len(pezzo) >= 3 and pezzo in parole:
                return False
    return True
