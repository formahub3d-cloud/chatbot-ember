"use strict";
const path=require("path"),fs=require("fs");
function trova(){const c=["/opt/pw-browsers/chromium-1194/chrome-linux/chrome","/usr/bin/chromium"];for(const p of c)if(fs.existsSync(p))return p;
 const b=process.env.PLAYWRIGHT_BROWSERS_PATH||"/opt/pw-browsers";for(const d of fs.readdirSync(b)){const p=path.join(b,d,"chrome-linux","chrome");if(fs.existsSync(p))return p;}return null;}
(async()=>{const {chromium}=require("playwright");const e=trova();
const b=await chromium.launch(e?{executablePath:e}:{});const pg=await b.newPage();
pg.on("pageerror",x=>console.log("PAGEERROR",x.message));
await pg.addInitScript(()=>{try{localStorage.setItem("dv_demo","1")}catch(e){}});
await pg.route(/^https?:\/\//,r=>r.abort());
await pg.goto("file://"+path.resolve(__dirname,"panel","index.html"));
await pg.waitForTimeout(900);
const o=await pg.evaluate(async()=>{
  const orig=window.demoData;
  window.demoData=(s,p,x)=>{const d=orig(s,p,x);
    if(s==="engine"&&p==="/admin/brain")return Object.assign({},d,{ingest_commit:{vault_commit:"0000deadbeef",at:d.ingest_commit.at},stats:Object.assign({},d.stats,{by_tenant:Object.assign({},d.stats.by_tenant,{hrh:2})})});
    return d;};
  const prova=await api("engine","/admin/brain");
  route("home");await new Promise(r=>setTimeout(r,1200));
  return {sostituito: prova.ingest_commit.vault_commit,
          righe: document.querySelectorAll("#homeOggi .imp-riga").length,
          bottoni: document.querySelectorAll("#homeOggi [data-oggi]").length,
          testo: (document.getElementById("homeOggi")||{textContent:""}).textContent.slice(0,240)};
});
console.log(JSON.stringify(o,null,1));await b.close();})();
