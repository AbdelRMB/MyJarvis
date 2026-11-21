// node rendu.mjs apercu 5 9.5 ...   → apercu-<t>.png
// node rendu.mjs video out.mp4      → vidéo 1920x1080 30 i/s
import puppeteer from "puppeteer-core";
import { spawn } from "child_process";
import path from "path";
import { fileURLToPath, pathToFileURL } from "url";
import { createRequire } from "module";
const ici = path.dirname(fileURLToPath(import.meta.url));
const ffmpeg = createRequire(import.meta.url)("ffmpeg-static");
const [mode, ...args] = process.argv.slice(2);
const FPS = 30;

const nav = await puppeteer.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
  args: ["--hide-scrollbars", "--force-color-profile=srgb", "--font-render-hinting=none"],
});
const page = await nav.newPage();
await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1.2 });
await page.goto(pathToFileURL(path.join(ici, "demo.html")).href, { waitUntil: "networkidle0" });
await page.evaluate(async () => { await document.fonts.ready; });
const DUREE = await page.evaluate(() => window.DUREE);

if (mode === "apercu") {
  // on rejoue la séquence depuis 0 pour que les états cumulés (rotation, défilement) soient justes
  const cibles = args.map(Number).sort((a, b) => a - b);
  let k = 0;
  for (let i = 0; k < cibles.length; i++) {
    const t = i / FPS;
    await page.evaluate((t) => window.render(t), t);
    if (t >= cibles[k] - 1e-6) {
      await page.screenshot({ path: path.join(ici, `apercu-${cibles[k]}.png`) });
      k++;
    }
  }
} else {
  const sortie = path.resolve(args[0] || "jarvis-demo.mp4");
  const ff = spawn(ffmpeg, ["-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", sortie],
    { stdio: ["pipe", "inherit", "inherit"] });
  const n = Math.round(DUREE * FPS);
  for (let i = 0; i < n; i++) {
    await page.evaluate((t) => window.render(t), i / FPS);
    const img = await page.screenshot({ type: "jpeg", quality: 95, optimizeForSpeed: true });
    if (!ff.stdin.write(img)) await new Promise((r) => ff.stdin.once("drain", r));
    if (i % 150 === 0) console.log(`image ${i}/${n}`);
  }
  ff.stdin.end();
  await new Promise((r) => ff.on("close", r));
  console.log("ok", sortie);
}
await nav.close();
