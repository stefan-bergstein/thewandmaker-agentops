#!/usr/bin/env node
// Capture a real product page from the cluster, for the deck.
//
//   node scripts/capture-ui.mjs <name> <url> [--wait 5000] [--width 1400] [--height 664]
//                               [--click "text"]... [--hide "css selector"]... [--full] [--login]
//
// --click takes the exact text of a link, tab or row; "~text" clicks the first one that contains
// it. A URL of "-" is read from the environment variable CAPTURE_URL instead, for links that
// must not show up in a process list (the one-time pairing link of the apprentice's console).
//
// The deck shows such a capture where it can't show the page live in a frame (products that
// refuse to be framed, or the scripted deck without a cluster). It lands in
// deck/assets/img/captures/<name>.png, and deck/js/captures.js records when it was taken, so
// the slide can say "captured from this cluster · <date>". Nothing is drawn or retouched.
//
// Login: the page is loaded with the bearer token of the current oc context.
// The token is read at run time, sent only to hosts under the cluster's own apps domain, and
// never printed or stored. OpenShift AI and MLflow accept that. The OpenShift console does not:
// it wants its own login. For such a page pass --login: a Chrome window opens, you log in there
// yourself (the script types nothing), and the capture is taken once the page is there. The
// window's profile is kept in local/capture-profile, so the next capture needs no new login.
//
// Needs a Chrome on this Mac and puppeteer-core, which "npx hyperframes" already brought along
// (looked up in ~/.npm/_npx). Nothing is downloaded.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const OUT = path.join(ROOT, "deck", "assets", "img", "captures");
const INDEX = path.join(ROOT, "deck", "js", "captures.js");

function args() {
  const a = process.argv.slice(2), o = { click: [], hide: [], wait: 5000, width: 1400, height: 664, full: false };
  const pos = [];
  for (let i = 0; i < a.length; i++) {
    if (a[i] === "--click") o.click.push(a[++i]);
    else if (a[i] === "--hide") o.hide.push(a[++i]);
    else if (a[i] === "--wait") o.wait = +a[++i];
    else if (a[i] === "--width") o.width = +a[++i];
    else if (a[i] === "--height") o.height = +a[++i];
    else if (a[i] === "--full") o.full = true;
    else if (a[i] === "--login") o.login = true;
    else pos.push(a[i]);
  }
  if (pos.length < 2) { console.error("usage: capture-ui.mjs <name> <url> [options]"); process.exit(2); }
  o.name = pos[0]; o.url = pos[1] === "-" ? process.env.CAPTURE_URL : pos[1];
  if (!o.url) { console.error("no URL (CAPTURE_URL is empty)"); process.exit(2); }
  return o;
}

function findPuppeteer() {
  const base = path.join(os.homedir(), ".npm", "_npx");
  const hits = fs.existsSync(base) ? fs.readdirSync(base)
    .map((d) => path.join(base, d, "node_modules", "puppeteer-core"))
    .filter((p) => fs.existsSync(path.join(p, "package.json"))) : [];
  if (!hits.length) throw new Error("puppeteer-core not found under ~/.npm/_npx (run the film's 'npx hyperframes check' once)");
  // newest copy wins
  hits.sort((x, y) => fs.statSync(y).mtimeMs - fs.statSync(x).mtimeMs);
  return createRequire(import.meta.url)(hits[0]);
}

function findChrome() {
  const c = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "/Applications/Chromium.app/Contents/MacOS/Chromium"];
  const hit = c.find((p) => fs.existsSync(p));
  if (!hit) throw new Error("no Chrome found in /Applications");
  return hit;
}

function oc(...a) {
  return execFileSync("oc", a, { env: { ...process.env }, encoding: "utf8" }).trim();
}

const o = args();
const token = oc("whoami", "-t");
const apps = oc("get", "ingresses.config.openshift.io", "cluster", "-o", "jsonpath={.spec.domain}");
const puppeteer = findPuppeteer();
const browser = await puppeteer.launch(o.login
  ? { executablePath: findChrome(), headless: false, userDataDir: path.join(ROOT, "local", "capture-profile"),
      defaultViewport: null, args: ["--window-size=" + o.width + "," + (o.height + 90)] }
  : { executablePath: findChrome(), headless: true, args: ["--hide-scrollbars"] });
try {
  const page = await browser.newPage();
  // The panel in the deck is about 2.1 times as wide as high. A smaller window drawn at double
  // density gives larger type on the projector and stays sharp.
  await page.setViewport({ width: o.width, height: o.height, deviceScaleFactor: 2 });
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    let host = "";
    try { host = new URL(req.url()).hostname; } catch (e) { /* data: and the like */ }
    // The token goes to the cluster's own pages only, never to a third party the page may load from.
    if (host === apps || host.endsWith("." + apps)) req.continue({ headers: { ...req.headers(), authorization: "Bearer " + token } });
    else req.continue();
  });
  const want = new URL(o.url);
  const atLogin = () => { const u = new URL(page.url()); return u.hostname !== want.hostname || /\/(auth|oauth|login)\b/i.test(u.pathname); };
  let res = await page.goto(o.url, { waitUntil: "networkidle2", timeout: 90000 });
  if (atLogin()) {
    if (!o.login) throw new Error("the page asked for a login (landed on " + new URL(page.url()).hostname + "). Run it again with --login and log in yourself.");
    console.log("Log in in the Chrome window that just opened. Waiting up to five minutes …");
    const until = Date.now() + 300000;
    while (atLogin() && Date.now() < until) await new Promise((r) => setTimeout(r, 1000));
    if (atLogin()) throw new Error("no login within five minutes");
    res = await page.goto(o.url, { waitUntil: "networkidle2", timeout: 90000 });
  }
  const landed = new URL(page.url());
  for (const text of o.click) {
    const hit = await page.evaluateHandle((t) => {
      // Open shadow roots count too: some consoles are built from web components.
      const all = [];
      const walk = (root) => root.querySelectorAll("*").forEach((e) => { all.push(e); if (e.shadowRoot) walk(e.shadowRoot); });
      walk(document);
      const own = (e) => Array.from(e.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
      if (t.startsWith("~")) { const part = t.slice(1); return all.find((e) => own(e).includes(part)) || null; }
      return all.find((e) => own(e) === t) || all.find((e) => e.textContent.trim() === t && e.children.length === 0) || null;
    }, text);
    const el = hit.asElement();
    if (!el) throw new Error('nothing to click with the text "' + text + '"');
    await el.click();
    await new Promise((r) => setTimeout(r, 2500));
  }
  await new Promise((r) => setTimeout(r, o.wait));
  if (o.hide.length) await page.addStyleTag({ content: o.hide.map((s) => s + " { display: none !important; }").join("\n") });
  fs.mkdirSync(OUT, { recursive: true });
  const file = path.join(OUT, o.name + ".png");
  await page.screenshot({ path: file, fullPage: o.full });
  const title = await page.title();

  // The deck reads this file; keep what other captures wrote.
  let all = {};
  if (fs.existsSync(INDEX)) {
    const m = fs.readFileSync(INDEX, "utf8").match(/window\.OLLI_CAPTURES = (\{[\s\S]*\});/);
    if (m) all = JSON.parse(m[1]);
  }
  const taken = new Date().toLocaleString("en-GB", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
  all[o.name] = { src: "assets/img/captures/" + o.name + ".png?t=" + Date.now(), taken, page: landed.hostname.split(".")[0] + landed.pathname };
  fs.writeFileSync(INDEX, "// Captures of real product pages, taken from the cluster by scripts/capture-ui.mjs. Do not edit.\n" +
    "window.OLLI_CAPTURES = " + JSON.stringify(all, null, 2) + ";\n");
  console.log(`${o.name}: HTTP ${res ? res.status() : "?"}, "${title}", ${path.relative(ROOT, file)}, taken ${taken}`);
} finally {
  await browser.close();
}
