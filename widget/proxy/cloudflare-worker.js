// Proxy Divina come Cloudflare Worker — universale, per QUALSIASI sito cliente.
// La CHIAVE TENANT resta un "secret" del Worker: non finisce mai nel browser.
//
// Deploy (dashboard Cloudflare → Workers):
//   1. Crea un Worker, incolla questo codice.
//   2. Settings → Variables: aggiungi
//        EMBER_API        = https://divina.formahub.it   (Variable)
//        EMBER_TENANT_KEY = CHIAVE_DEL_CLIENTE                              (Secret)
//        ALLOW_ORIGIN      = https://www.sitodelcliente.it                   (Variable, opzionale)
//   3. Punta il widget al Worker:  data-proxy="https://ember-hrh.tuosub.workers.dev"
//
// Un Worker per cliente (chiave diversa) = isolamento netto e niente chiave esposta.

export default {
  async fetch(request, env) {
    const origin = env.ALLOW_ORIGIN || "*";
    const cors = {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    const API_BASE = env.EMBER_API || env.JARVIS_API;            // JARVIS_*: retro-compat
    const TENANT_KEY = env.EMBER_TENANT_KEY || env.JARVIS_TENANT_KEY;
    if (!API_BASE || !TENANT_KEY) return json({ answer: "Proxy non configurato." }, 500, cors);
    const BASE = API_BASE.replace(/\/$/, "");

    // GET /config → branding + capacità voce (per l'auto-config del widget).
    if (request.method === "GET" && new URL(request.url).pathname.endsWith("/config")) {
      try {
        const up = await fetch(BASE + "/config", { headers: { "X-Tenant-Key": TENANT_KEY } });
        return json(await up.json().catch(() => ({})), up.status, cors);
      } catch { return json({}, 502, cors); }
    }
    if (request.method !== "POST") return json({ answer: "Metodo non consentito." }, 405, cors);

    // Voce PRO: se il path finisce con /voice/stt o /voice/tts, inoltra così com'è
    // (audio o JSON) aggiungendo la chiave lato server. Serve VOICE_PROVIDER su Divina.
    const path = new URL(request.url).pathname;
    if (path.endsWith("/voice/stt") || path.endsWith("/voice/tts")) {
      const sub = path.endsWith("/voice/stt") ? "/voice/stt" : "/voice/tts";
      try {
        const up = await fetch(API_BASE.replace(/\/$/, "") + sub, {
          method: "POST",
          headers: { "X-Tenant-Key": TENANT_KEY,
                     "Content-Type": request.headers.get("content-type") || "application/octet-stream" },
          body: request.body,
        });
        return new Response(up.body, {
          status: up.status,
          headers: { ...cors, "Content-Type": up.headers.get("content-type") || "application/json" },
        });
      } catch { return json({ error: "Voce non raggiungibile." }, 502, cors); }
    }

    // Feedback 👍/👎: inoltra a /feedback con la chiave lato server.
    if (path.endsWith("/feedback")) {
      try {
        const fb = await request.json().catch(() => ({}));
        const up = await fetch(API_BASE.replace(/\/$/, "") + "/feedback", {
          method: "POST",
          headers: { "X-Tenant-Key": TENANT_KEY, "Content-Type": "application/json" },
          body: JSON.stringify(fb),
        });
        return json(await up.json().catch(() => ({ ok: true })), up.status, cors);
      } catch { return json({ ok: false }, 502, cors); }
    }

    let body;
    try { body = await request.json(); } catch { return json({ answer: "Richiesta non valida." }, 400, cors); }
    const message = (body && typeof body.message === "string") ? body.message.slice(0, 2000) : "";
    if (!message.trim()) return json({ answer: "Messaggio vuoto." }, 400, cors);

    const stream = body && body.stream === true; // il widget chiede lo streaming SSE
    const history = Array.isArray(body && body.history) ? body.history.slice(-6) : [];

    try {
      const r = await fetch(API_BASE.replace(/\/$/, "") + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Tenant-Key": TENANT_KEY },
        body: JSON.stringify({ message, stream, history }),
      });
      // SSE pass-through: se Divina risponde in streaming, lo inoltriamo così com'è.
      const ct = r.headers.get("content-type") || "";
      if (ct.includes("text/event-stream") && r.body) {
        return new Response(r.body, {
          status: r.status,
          headers: { ...cors, "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        });
      }
      const data = await r.json().catch(() => ({ answer: "Risposta non valida dal servizio." }));
      return json(data, r.status, cors);
    } catch {
      return json({ answer: "Servizio non raggiungibile." }, 502, cors);
    }
  },
};

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...cors },
  });
}
