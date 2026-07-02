"""RAG: recupero filtrato per scope + risposta vincolata al contenuto.

Il filtro per scope È la limitazione per settore: un tenant vede solo i chunk
il cui `scope` è tra i suoi `allowed_scopes`.
"""
from qdrant_client.models import Filter, FieldCondition, MatchAny

from .config import settings
from .providers import embed, chat
from .ingest import client

SYSTEM = (
    "Sei Ember, l'assistente del cervello OVY di Andrea Aloia / FORMA. "
    "Rispondi SOLO usando il CONTENUTO fornito sotto. "
    "Se la risposta non è nel contenuto, scrivi esattamente: "
    "'Non ho questa informazione nelle aree a cui ho accesso.' "
    "Non inventare nulla. Rispondi in italiano, in modo conciso. "
    "Alla fine elenca gli slug delle note che hai usato."
)


def answer(question: str, allowed_scopes: list[str], k: int = 6) -> dict:
    qvec = embed([question])[0]
    c = client()
    # Chiave master: se tra gli scope c'è "*" la ricerca NON è filtrata (vede tutto).
    # Da usare SOLO con una chiave segreta forte, in un contesto admin privato (mai in un
    # widget pubblico): vede i dati di tutti i clienti.
    if "*" in allowed_scopes:
        flt = None
    else:
        flt = Filter(must=[FieldCondition(key="scope", match=MatchAny(any=allowed_scopes))])
    hits = c.query_points(
        collection_name=settings.qdrant_collection,
        query=qvec,
        query_filter=flt,
        limit=k,
    ).points
    if not hits:
        return {"answer": "Non ho questa informazione nelle aree a cui ho accesso.",
                "sources": [], "scopes": allowed_scopes}

    context = "\n\n".join(f"[{h.payload['slug']}] {h.payload['text']}" for h in hits)
    user = f"CONTENUTO:\n{context}\n\nDOMANDA: {question}"
    out = chat(SYSTEM, user)
    sources = sorted({h.payload["slug"] for h in hits})
    return {"answer": out, "sources": sources, "scopes": allowed_scopes}
