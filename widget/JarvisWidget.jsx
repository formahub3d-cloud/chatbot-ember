"use client";
/* Jarvis — widget di chat per Next.js / React (App Router).
 *
 * DUE MODALITÀ:
 *   1) PROXY (consigliato): la chiave resta sul server, NON nel browser.
 *      <JarvisWidget proxy="/api/jarvis" title="Assistente HRH" />
 *      (vedi widget/proxy/nextjs-route.js → app/api/jarvis/route.js)
 *   2) DIRETTA (solo pilota): chiave nell'HTML.
 *      <JarvisWidget api="https://jarvis...railway.app" tenantKey="CHIAVE_HRH" />
 */
import { useState, useRef, useEffect } from "react";

export default function JarvisWidget({
  proxy = "",
  api = "http://localhost:8000",
  tenantKey = "CHIAVE_FORMA_INTERNO",
  title = "Jarvis · Assistente",
  accent = "#0ED4E4",
}) {
  const base = api.replace(/\/$/, "");
  const endpoint = proxy ? proxy.replace(/\/$/, "") : base + "/chat";
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState([]); // {role:'u'|'a', text, sources?}
  const [val, setVal] = useState("");
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    if (open && msgs.length === 0) {
      setMsgs([{ role: "a", text: `Ciao! Sono ${title}. Rispondo solo sulle aree a cui ho accesso. Come posso aiutarti?` }]);
    }
  }, [open]); // eslint-disable-line

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [msgs, busy]);

  async function ask() {
    const q = val.trim();
    if (!q || busy) return;
    setVal("");
    setMsgs((m) => [...m, { role: "u", text: q }]);
    setBusy(true);
    try {
      const headers = { "Content-Type": "application/json" };
      if (!proxy) headers["X-Tenant-Key"] = tenantKey; // in proxy mode la chiave la mette il server
      const r = await fetch(endpoint, {
        method: "POST",
        headers,
        body: JSON.stringify({ message: q }),
      });
      if (!r.ok) {
        setMsgs((m) => [...m, { role: "a", text: `⚠️ Errore ${r.status}. Riprova tra poco.` }]);
      } else {
        const d = await r.json();
        setMsgs((m) => [...m, { role: "a", text: d.answer || "(nessuna risposta)", sources: d.sources }]);
      }
    } catch {
      setMsgs((m) => [...m, { role: "a", text: "⚠️ Connessione non riuscita. Verifica che il servizio sia attivo." }]);
    } finally {
      setBusy(false);
    }
  }

  const C = {
    dark: "#0e0e10", line: "#26262e", txt: "#f4f4f6", mut: "#9a9aa6",
    fontFamily: "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial,sans-serif",
  };

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Apri chat"
        style={{
          position: "fixed", right: 22, bottom: 22, width: 58, height: 58, borderRadius: "50%",
          background: accent, color: "#06262b", border: "none", cursor: "pointer", zIndex: 2147483000,
          boxShadow: "0 8px 28px rgba(0,0,0,.35)", fontSize: 26,
        }}
      >💬</button>

      {open && (
        <div style={{
          position: "fixed", right: 22, bottom: 92, width: 360, maxWidth: "calc(100vw - 32px)",
          height: 520, maxHeight: "calc(100vh - 130px)", background: C.dark, border: `1px solid ${C.line}`,
          borderRadius: 16, zIndex: 2147483000, display: "flex", flexDirection: "column", overflow: "hidden",
          boxShadow: "0 18px 50px rgba(0,0,0,.5)", fontFamily: C.fontFamily,
        }}>
          <div style={{ padding: "14px 16px", borderBottom: `1px solid ${C.line}`, color: C.txt, fontWeight: 700,
            fontSize: 15, display: "flex", justifyContent: "space-between", alignItems: "center",
            background: `linear-gradient(135deg, ${accent}22, transparent)` }}>
            <span>{title}</span>
            <button onClick={() => setOpen(false)} aria-label="Chiudi"
              style={{ background: "none", border: "none", color: C.mut, fontSize: 20, cursor: "pointer" }}>×</button>
          </div>

          <div ref={bodyRef} style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
            {msgs.map((m, i) => (
              <div key={i} style={{
                maxWidth: "85%", padding: "9px 12px", borderRadius: 12, fontSize: 14, lineHeight: 1.45, whiteSpace: "pre-wrap",
                alignSelf: m.role === "u" ? "flex-end" : "flex-start",
                background: m.role === "u" ? accent : "#1b1b22",
                color: m.role === "u" ? "#06262b" : C.txt,
                border: m.role === "u" ? "none" : `1px solid ${C.line}`,
              }}>
                {m.text}
                {m.sources?.length ? <div style={{ fontSize: 11, color: C.mut, marginTop: 4 }}>Fonti: {m.sources.join(", ")}</div> : null}
              </div>
            ))}
            {busy && <div style={{ alignSelf: "flex-start", color: C.mut, fontSize: 13 }}>…sto pensando</div>}
          </div>

          <div style={{ borderTop: `1px solid ${C.line}`, padding: 10, display: "flex", gap: 8 }}>
            <input
              value={val} onChange={(e) => setVal(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()}
              placeholder="Scrivi una domanda..."
              style={{ flex: 1, background: "#15151a", border: `1px solid ${C.line}`, color: C.txt, borderRadius: 10, padding: "10px 12px", fontSize: 14, outline: "none" }}
            />
            <button onClick={ask} disabled={busy}
              style={{ background: accent, color: "#06262b", border: "none", borderRadius: 10, padding: "0 14px", fontWeight: 700, cursor: busy ? "default" : "pointer", opacity: busy ? 0.5 : 1 }}>Invia</button>
          </div>
        </div>
      )}
    </>
  );
}
