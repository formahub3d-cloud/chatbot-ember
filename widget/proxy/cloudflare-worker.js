// Proxy Jarvis come Cloudflare Worker — universale, per QUALSIASI sito cliente.
// La CHIAVE TENANT resta un "secret" del Worker: non finisce mai nel browser.
//
// Deploy (dashboard Cloudflare → Workers):
//   1. Crea un Worker, incolla questo codice.
//   2. Settings → Variables: aggiungi
//        JARVIS_API        = https://jarvis-production-e680.up.railway.app   (Variable)
//        JARVIS_TENANT_KEY = CHIAVE_DEL_CLIENTE                              (Secret)
//        ALLOW_ORIGIN      = https://www.sitodelcliente.it                   (Variable, opzionale)
//   3. Punta il widget al Worker:  data-proxy="https://jarvis-hrh.tuosub.workers.dev"
//
// Un Worker per cliente (chiave diversa) = isolamento netto e niente chiave esposta.

export default {
  async fetch(request, env) {
    const origin = env.ALLOW_ORIGIN || "*";
    const cors = {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    if (request.method !== "POST") return json({ answer: "Metodo non consentito." }, 405, cors);
    if (!env.JARVIS_API || !env.JARVIS_TENANT_KEY) return json({ answer: "Proxy non configurato." }, 500, cors);

    let body;
    try { body = await request.json(); } catch { return json({ answer: "Richiesta non valida." }, 400, cors); }
    const message = (body && typeof body.message === "string") ? body.message.slice(0, 2000) : "";
    if (!message.trim()) return json({ answer: "Messaggio vuoto." }, 400, cors);

    try {
      const r = await fetch(env.JARVIS_API.replace(/\/$/, "") + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Tenant-Key": env.JARVIS_TENANT_KEY },
        body: JSON.stringify({ message }),
      });
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
