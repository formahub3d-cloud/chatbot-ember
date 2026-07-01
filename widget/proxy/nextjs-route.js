// Proxy Jarvis per siti Next.js (App Router).
// Posiziona questo file in:  app/api/jarvis/route.js
//
// Tiene la CHIAVE TENANT lato server (variabile d'ambiente), così NON finisce mai
// nell'HTML/browser. Il widget chiama "/api/jarvis" (stesso dominio), questo route
// aggiunge la chiave e inoltra a Jarvis.
//
// Variabili d'ambiente da impostare sul sito (es. su Vercel/Railway):
//   JARVIS_API         = https://jarvis-production-e680.up.railway.app
//   JARVIS_TENANT_KEY  = CHIAVE_DEL_CLIENTE   (es. CHIAVE_HRH)

export const runtime = "edge"; // veloce ed economico; rimuovi se preferisci Node

export async function POST(req) {
  const api = process.env.JARVIS_API;
  const key = process.env.JARVIS_TENANT_KEY;
  if (!api || !key) {
    return Response.json({ answer: "Proxy non configurato (JARVIS_API/JARVIS_TENANT_KEY)." }, { status: 500 });
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

  try {
    const r = await fetch(api.replace(/\/$/, "") + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Tenant-Key": key },
      body: JSON.stringify({ message }),
    });
    const data = await r.json().catch(() => ({ answer: "Risposta non valida dal servizio." }));
    return Response.json(data, { status: r.status });
  } catch {
    return Response.json({ answer: "Servizio non raggiungibile. Riprova tra poco." }, { status: 502 });
  }
}
