import fs from "fs"; import path from "path"; import { pathToFileURL } from "url";
const dir = process.argv[2]; const out = {};
const noms = ["message-square","list-checks","rotate-ccw-clock","brain","list-todo","zap","globe","plug","laptop","cpu","activity","wrench","settings","download","life-buoy","chevron-down","mic","mic-off","volume-2","bell","arrow-up","check","loader-circle","shield-exclamation-point","sparkles","star","monitor","terminal","send","camera","calendar","search","user","chevrons-left","check-check","info","chart-column-big"];
for (const n of noms) {
  const f = path.join(dir, n + ".mjs"); if (!fs.existsSync(f)) { console.error("absent", n); continue; }
  const m = await import(pathToFileURL(f).href).catch(e => null);
  if (!m) { console.error("import", n); continue; }
  if (!m.__iconData) { console.error("alias", n, Object.keys(m)); continue; }
  out[n] = m.__iconData.node.map(([tag, a]) => `<${tag} ${Object.entries(a).filter(([k])=>k!=="key").map(([k,v])=>`${k}="${v}"`).join(" ")}/>`).join("");
}
fs.writeFileSync(process.argv[3], "window.ICONES=" + JSON.stringify(out) + ";");
console.log(Object.keys(out).length);
