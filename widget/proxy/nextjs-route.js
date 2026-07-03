// Proxy Ember per siti Next.js (App Router) — chat + voce PRO.
// Posiziona questo file in:  app/api/ember/[[...path]]/route.js
//   (catch-all: gestisce /api/ember  →  chat  e  /api/ember/voice/stt|tts  →  voce)
//
// Tiene la CHIAVE TENANT lato server (variabile d'ambiente), così NON finisce mai
// nell'HTML/browser. Il widget chiama "/api/ember" (stesso dominio), questo route
// aggiunge la chiave e inoltra a Ember.
//
// Variabili d'ambiente da impostare sul sito (es. su Vercel/Railway):
//   EMBER_API         = https://ember.formahub.it
//   EMBER_TENANT_KEY  = CHIAVE_DEL_CLIENTE   (es. CHIAVE_HRH)

export const runtime = "edge"; // veloce ed economico; rimuovi se preferisci Node

// GET /api/ember/config → branding + capacità voce (per l'auto-config del widget).
export async function GET(req) {
  const api = process.env.EMBER_API || process.env.JARVIS_API;
  const key = process.env.EMBER_TENANT_KEY || process.env.JARVIS_TENANT_KEY;
  if (!api || !key) return Response.json({}, { status: 500 });
  if (!new URL(req.url).pathname.endsWith("/config")) return Response.json({}, { status: 404 });
  try {
    const up = await fetch(api.replace(/\/$/, "") + "/config", { headers: { "X-Tenant-Key": key } });
    return Response.json(await up.json().catch(() => ({})), { status: up.status });
  } catch {
    return Response.json({}, { status: 502 });
  }
}

export async function POST(req) {
  const api = process.env.EMBER_API || process.env.JARVIS_API;            // JARVIS_*: retro-compat
  const key = process.env.EMBER_TENANT_KEY || process.env.JARVIS_TENANT_KEY;
  if (!api || !key) {
    return Response.json({ answer: "Proxy non configurato (EMBER_API/EMBER_TENANT_KEY)." }, { status: 500 });
  }
  const base = api.replace(/\/$/, "");
  const path = new URL(req.url).pathname;

  // ── Voce PRO: inoltra audio↔testo a /voice/* (serve VOICE_PROVIDER su Ember) ──
  if (path.endsWith("/voice/stt") || path.endsWith("/voice/tts")) {
    const sub = path.endsWith("/voice/stt") ? "/voice/stt" : "/voice/tts";
    try {
      const up = await fetch(base + sub, {
        method: "POST",
        headers: { "X-Tenant-Key": key,
                   "Content-Type": req.headers.get("content-type") || "application/octet-stream" },
        body: req.body,
        duplex: "half",
      });
      return new Response(up.body, {
        status: up.status,
        headers: { "Content-Type": up.headers.get("content-type") || "application/json" },
      });
    } catch {
      return Response.json({ error: "Voce non raggiungibile." }, { status: 502 });
    }
  }

  // ── Chat (JSON o SSE) ──
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
    const r = await fetch(base + "/chat", {
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
