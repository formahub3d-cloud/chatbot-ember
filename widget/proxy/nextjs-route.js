// Proxy Ember per siti Next.js (App Router).
// Posiziona questo file in:  app/api/ember/route.js
//
// Tiene la CHIAVE TENANT lato server (variabile d'ambiente), così NON finisce mai
// nell'HTML/browser. Il widget chiama "/api/ember" (stesso dominio), questo route
// aggiunge la chiave e inoltra a Ember.
//
// Variabili d'ambiente da impostare sul sito (es. su Vercel/Railway):
//   EMBER_API         = https://jarvis-production-e680.up.railway.app
//   EMBER_TENANT_KEY  = CHIAVE_DEL_CLIENTE   (es. CHIAVE_HRH)

export const runtime = "edge"; // veloce ed economico; rimuovi se preferisci Node

export async function POST(req) {
  const api = process.env.EMBER_API || process.env.JARVIS_API;            // JARVIS_*: retro-compat
  const key = process.env.EMBER_TENANT_KEY || process.env.JARVIS_TENANT_KEY;
  if (!api || !key) {
    return Response.json({ answer: "Proxy non configurato (EMBER_API/EMBER_TENANT_KEY)." }, { status: 500 });
  }

  let body;
  try {
    body = await req.json();
  } catch {
    return Response.json({ answer: "Richiesta non valida." }, { status: 400 });
  }
  const message = (body && typeof body.message === "string") ? body.message.slice(0, 2000) : "";
  if (!message.trim()) {
    return Response.json({ answer: "Messaggio vuoto." }, { status: 400 });
  }

  const stream = body && body.stream === true; // il widget chiede lo streaming SSE

  try {
    const r = await fetch(api.replace(/\/$/, "") + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Tenant-Key": key },
      body: JSON.stringify({ message, stream }),
    });
    // SSE pass-through: se Ember risponde in streaming, lo inoltriamo così com'è.
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("text/event-stream") && r.body) {
      return new Response(r.body, {
        status: r.status,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
      });
    }
    const data = await r.json().catch(() => ({ answer: "Risposta non valida dal servizio." }));
    return Response.json(data, { status: r.status });
  } catch {
    return Response.json({ answer: "Servizio non raggiungibile. Riprova tra poco." }, { status: 502 });
  }
}
