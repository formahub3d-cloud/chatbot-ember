"""Auto-compilazione contratti (Fase 3): template per tipologia + merge dati persona
+ generazione PDF.

Flusso: i dati della persona arrivano dall'estrazione UniLav (extract.py) o
dall'applicazione, si fondono nel template della tipologia scelta e producono la
lettera di assunzione — prima come TESTO da rivedere (conferma umana, regola 5),
poi come PDF da inviare alla firma (provider e-sign: fuori da questo modulo).

Nessun dato viene salvato qui: il modulo è puro (input → documento).
"""
from datetime import date

from fpdf import FPDF

# Campi comuni a tutti i template. `required`: senza quel campo il PDF non si genera.
_PERSONA = [
    ("nome", "Nome", True),
    ("cognome", "Cognome", True),
    ("codice_fiscale", "Codice fiscale", True),
    ("luogo_nascita", "Luogo di nascita", False),
    ("data_nascita", "Data di nascita", False),
    ("residenza", "Indirizzo di residenza", False),
]
_AZIENDA = [
    ("datore", "Datore di lavoro (denominazione)", True),
    ("datore_cf", "P.IVA / CF datore", False),
    ("sede_lavoro", "Sede di lavoro", True),
]
_RAPPORTO = [
    ("mansione", "Mansione", True),
    ("livello", "Livello / inquadramento", False),
    ("ccnl", "CCNL applicato", True),
    ("orario", "Orario settimanale", True),
    ("retribuzione", "Retribuzione lorda", True),
    ("data_inizio", "Data inizio", True),
]

_INTESTAZIONE = """LETTERA DI ASSUNZIONE — {titolo}

{datore}{datore_cf_riga}
Sede di lavoro: {sede_lavoro}

Alla c.a. di {nome} {cognome}
Codice fiscale: {codice_fiscale}{anagrafica_riga}

Oggetto: proposta di assunzione con contratto {titolo_minuscolo}.
"""

_CORPO_COMUNE = """
Con la presente Le comunichiamo la nostra volontà di assumerLa alle seguenti condizioni:

  - Mansione: {mansione}{livello_riga}
  - CCNL applicato: {ccnl}
  - Orario di lavoro: {orario}
  - Retribuzione lorda: {retribuzione}
  - Data di inizio del rapporto: {data_inizio}
{durata_blocco}
Il periodo di prova e ogni ulteriore condizione sono regolati dal CCNL applicato.
La comunicazione obbligatoria (UniLav) sarà trasmessa nei termini di legge.

Data: {oggi}

Firma del datore di lavoro: ______________________

Firma per accettazione del lavoratore: ______________________
"""

TEMPLATES = {
    "determinato": {
        "titolo": "Tempo determinato",
        "fields": _PERSONA + _AZIENDA + _RAPPORTO + [("data_fine", "Data fine", True)],
        "durata": "  - Durata: dal {data_inizio} al {data_fine} (tempo determinato)\n",
    },
    "indeterminato": {
        "titolo": "Tempo indeterminato",
        "fields": _PERSONA + _AZIENDA + _RAPPORTO,
        "durata": "  - Durata: a tempo indeterminato\n",
    },
    "apprendistato": {
        "titolo": "Apprendistato professionalizzante",
        "fields": _PERSONA + _AZIENDA + _RAPPORTO + [
            ("data_fine", "Fine periodo formativo", True),
            ("qualifica_obiettivo", "Qualifica da conseguire", True),
        ],
        "durata": ("  - Periodo formativo: dal {data_inizio} al {data_fine}\n"
                   "  - Qualifica da conseguire: {qualifica_obiettivo}\n"),
    },
    "stagionale": {
        "titolo": "Lavoro stagionale",
        "fields": _PERSONA + _AZIENDA + _RAPPORTO + [("data_fine", "Data fine", True)],
        "durata": "  - Durata: dal {data_inizio} al {data_fine} (attività stagionale)\n",
    },
}


def list_templates() -> list[dict]:
    """Catalogo dei template: id, titolo e campi (con obbligatorietà) per la UI."""
    return [{"id": tid,
             "titolo": t["titolo"],
             "fields": [{"name": n, "label": lb, "required": rq} for n, lb, rq in t["fields"]]}
            for tid, t in TEMPLATES.items()]


def fill(template_id: str, data: dict) -> dict:
    """Merge dei dati persona/azienda nel template. Ritorna {text, missing, template}.
    `missing` = campi obbligatori vuoti: se non è vuota, il testo è una BOZZA
    incompleta (i buchi appaiono come «___») e il PDF non va generato."""
    t = TEMPLATES.get(template_id)
    if not t:
        raise KeyError(f"template sconosciuto: {template_id}")
    d = {k: str(v).strip() for k, v in (data or {}).items() if str(v or "").strip()}
    missing = [n for n, _lb, rq in t["fields"] if rq and not d.get(n)]

    def g(k):  # valore o segnaposto visibile
        return d.get(k, "___")

    fmt = {n: g(n) for n, _lb, _rq in t["fields"]}
    fmt.update({
        "titolo": t["titolo"],
        "titolo_minuscolo": t["titolo"].lower(),
        "oggi": date.today().strftime("%d/%m/%Y"),
        "datore_cf_riga": f"\nP.IVA/CF: {d['datore_cf']}" if d.get("datore_cf") else "",
        "livello_riga": f" — livello {d['livello']}" if d.get("livello") else "",
        "anagrafica_riga": (f"\nNato/a a {g('luogo_nascita')} il {g('data_nascita')}"
                            f" — residente in {g('residenza')}"
                            if any(d.get(k) for k in ("luogo_nascita", "data_nascita", "residenza"))
                            else ""),
        "durata_blocco": t["durata"].format_map({n: g(n) for n, _lb, _rq in t["fields"]}),
    })
    text = (_INTESTAZIONE + _CORPO_COMUNE).format_map(fmt)
    return {"template": template_id, "titolo": t["titolo"], "text": text, "missing": missing}


def to_pdf(text: str, titolo: str = "Contratto") -> bytes:
    """Rende il testo del contratto in un PDF A4 semplice e pulito (helvetica)."""
    pdf = FPDF(format="A4")
    pdf.set_margins(20, 18, 20)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font("helvetica", size=10.5)
    safe = text.encode("latin-1", "replace").decode("latin-1")
    for line in safe.splitlines():
        if line.isupper() and len(line) > 10:          # riga di intestazione
            pdf.set_font("helvetica", "B", 12)
            pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", size=10.5)
        else:
            pdf.multi_cell(0, 5.4, line if line else " ", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
