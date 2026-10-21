"use strict";
// Civitai Grabber Bridge (Firefox: background page, Chromium: service worker; the code is the same)
//  1. asks the local Civitai Grabber script for jobs ("fetch this page") and answers with the page text,
//     fetched with the cookies of the logged-in browser;
//  2. sends Civitai page/link addresses to the script's download list (popup and right-click menu);
//  3. can close the tabs of finished links and start the program (native messaging).
if (typeof importScripts === "function") importScripts("common.js");   // service worker; Firefox loads common.js from the manifest

const PORTS = Array.from({ length: 10 }, (_, i) => 47653 + i);
const HDR = { "X-Grabber": "1" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const act = browser.action || browser.browserAction;          // toolbar button API

let base = null;
let fastUntil = 0;     // after "Start" is pressed: look for the program more often for a while
const info = { status: "looking for the script…", done: 0, last: "", news: "", grabberVersion: "" };
const ICONS_ON = { 16: "icon-16.png", 32: "icon-32.png", 48: "icon-48.png", 128: "icon.png" };
const ICONS_OFF = { 16: "icon-off-16.png", 32: "icon-off-32.png", 48: "icon-off-48.png", 128: "icon-off.png" };
let lastOn = null;

class NotRunning extends Error {}

// ---- state that must survive a restart of the background script (Chromium stops it when idle)
const area = browser.storage.session || browser.storage.local;
const sentTabs = new Map();   // normalized link -> id of the tab it was added from
const pendingClose = [];      // [{tabId, url}] waiting for the user's OK (mode "ask")
const attention = [];         // [{url, note}] finished links that need a look (some files were not downloaded)
let closeMode = "never";
let clientId = "";             // tells the program which browser added a link, so its "finished" news returns to that browser
const ready = (async () => {
  try {
    const ci = await browser.storage.local.get("clientId");
    clientId = ci.clientId || Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
    if (!ci.clientId) await browser.storage.local.set({ clientId });
    const r = await area.get(["sentTabs", "pendingClose"]);
    for (const [k, v] of Object.entries(r.sentTabs || {})) sentTabs.set(k, v);
    if (Array.isArray(r.pendingClose)) pendingClose.push(...r.pendingClose);
    const a = await area.get("attention");
    if (Array.isArray(a.attention)) attention.push(...a.attention);
    const c = await browser.storage.local.get("closeMode");
    if (c.closeMode) closeMode = c.closeMode;
  } catch (e) { /* start empty */ }
})();
const saveState = () => area.set({ sentTabs: Object.fromEntries(sentTabs), pendingClose, attention }).catch(() => {});
browser.storage.onChanged.addListener((ch) => { if (ch.closeMode) closeMode = ch.closeMode.newValue || "never"; });

// ---- toolbar icon: normal = connected to the program, pale = not connected; short badge flashes for results
function showBadge(text, color) {
  act.setBadgeText({ text });
  if (color) act.setBadgeBackgroundColor({ color });
}
function setConnected(on) {
  if (on === lastOn) return;
  lastOn = on;
  Promise.resolve(act.setIcon({ path: on ? ICONS_ON : ICONS_OFF })).catch(() => {});
  act.setTitle({
    title: on ? "Civitai Grabber Bridge: connected to the program"
              : "Civitai Grabber Bridge: the program is NOT running",
  });
}
// the badge is empty, except for a short flash after an action and an amber number while links need attention
function updateBadge() {
  if (attention.length) showBadge(String(attention.length), "#e6a700");
  else showBadge("", null);
}
function flash(text, color, ms = 2500) {
  showBadge(text, color);
  setTimeout(updateBadge, ms);
}
function notify(message) {
  browser.notifications.create({
    type: "basic", title: "Civitai Grabber", message, iconUrl: browser.runtime.getURL("icon.png"),
  }).catch(() => {});
}

async function timedFetch(url, opts = {}, ms = 2000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try { return await fetch(url, { ...opts, signal: ctl.signal }); } finally { clearTimeout(t); }
}

async function findServer() {
  // all ports at once: a closed local port may need a while to refuse
  const found = await Promise.all(PORTS.map(async (p) => {
    try {
      const r = await timedFetch(`http://127.0.0.1:${p}/ping`, { headers: HDR, cache: "no-store" }, 1500);
      const j = await r.json();
      return j && j.app === "civitai-grabber" ? { p, j } : null;
    } catch (e) { return null; }
  }));
  const hit = found.find(Boolean);
  if (!hit) return false;
  base = `http://127.0.0.1:${hit.p}`;
  info.grabberVersion = (hit.j && hit.j.version) || "";
  browser.storage.local.set({ seen: true, launcher: !!hit.j.launcher, version: hit.j.version, lastSeen: Date.now() }).catch(() => {});
  return true;
}

async function ensureServer() {
  if (base) {
    try {
      const r = await timedFetch(`${base}/ping`, { headers: HDR, cache: "no-store" }, 1500);
      if (r.ok) return true;
    } catch (e) { /* fall through */ }
    base = null;
  }
  return findServer();
}

// the text of a loaded tab: Chromium (and Firefox with the scripting API) / older Firefox
async function readPage(tabId) {
  if (browser.scripting && browser.scripting.executeScript) {
    const [r] = await browser.scripting.executeScript({
      target: { tabId }, func: () => ({ title: document.title, html: document.documentElement.outerHTML }),
    });
    return r && r.result;
  }
  const [res] = await browser.tabs.executeScript(tabId, {
    code: "({title: document.title, html: document.documentElement.outerHTML})",
  });
  return res;
}

// Fallback for pages that refuse a plain fetch: load the page in a background tab like a normal visit.
async function pageViaTab(url, timeoutMs = 60000) {
  const tab = await browser.tabs.create({ url, active: false });
  const t0 = Date.now();
  try {
    while (Date.now() - t0 < timeoutMs) {
      await sleep(700);
      const t = await browser.tabs.get(tab.id);
      if (t.status !== "complete") continue;
      const res = await readPage(tab.id);
      if (res && !/just a moment/i.test(res.title || "")) return res.html;
    }
    throw new Error("the page did not finish loading");
  } finally {
    browser.tabs.remove(tab.id).catch(() => {});
  }
}

async function doJob(job) {
  const out = { id: job.id, status: 0, text: "", via: "fetch" };
  try {
    const r = await fetch(job.url, { credentials: "include", cache: "no-store" });
    out.status = r.status;
    let needTab = false;
    if (r.ok) {
      out.text = await r.text();
      if (job.kind === "page" && !/__NEXT_DATA__|"meta":\{/.test(out.text)) needTab = true;
    } else if (job.kind === "page" && [401, 403, 429, 503].includes(r.status)) {
      needTab = true;
    }
    if (needTab) {
      out.text = await pageViaTab(job.url);
      out.status = 200;
      out.via = "tab";
    }
  } catch (e) {
    out.error = String(e);
  }
  info.done += 1;
  info.last = `${job.url} → ${out.error ? "error" : out.status} (${out.via})`;
  await fetch(`${base}/result`, {
    method: "POST",
    headers: { ...HDR, "Content-Type": "application/json" },
    body: JSON.stringify(out),
  });
}

// Chromium stops an idle service worker after about 30 seconds. Calls of extension APIs count as activity,
// so a harmless one is made regularly; an alarm wakes the worker up again if it has been stopped anyway.
const keepAlive = () => { try { browser.runtime.getPlatformInfo().catch(() => {}); } catch (e) { /* ignore */ } };
setInterval(keepAlive, 20000);
if (browser.alarms) {
  browser.alarms.create("civitai-grabber-tick", { periodInMinutes: 0.5 });
  browser.alarms.onAlarm.addListener(() => { keepAlive(); mainLoop(); });
}

let looping = false;
async function mainLoop() {
  if (looping) return;
  looping = true;
  for (;;) {
    keepAlive();
    if (!base) {
      info.status = "the script is not running (looking for it…)";
      setConnected(false);
      if (!(await findServer())) { await sleep(Date.now() < fastUntil ? 500 : 3000); continue; }
    }
    info.status = "connected to the script";
    setConnected(true);
    try {
      await ready;
      const r = await fetch(`${base}/job?c=${encodeURIComponent(clientId)}`, { headers: HDR, cache: "no-store" });
      if (r.status === 204) continue;           // nothing to do, ask again
      if (!r.ok) throw new Error("HTTP " + r.status);
      const job = await r.json();
      if (job.kind === "event") { await handleEvent(job); continue; }   // news from the program, nothing to fetch
      info.status = "working: " + job.url;
      await doJob(job);
    } catch (e) {
      base = null;
      info.status = "the script is not running (looking for it…)";
      setConnected(false);
      await sleep(1500);
    }
  }
}

// ---- adding links to the script's download list
async function addUrls(urls, tab) {
  await ready;
  const good = [...new Set(urls.map(normalize).filter(Boolean))];
  if (!good.length) return { sent: 0, skipped: urls.length };
  if (!(await ensureServer())) {
    setConnected(false);
    throw new NotRunning("The Civitai Grabber script is not running");
  }
  const r = await timedFetch(`${base}/add`, {
    method: "POST",
    headers: { ...HDR, "Content-Type": "application/json" },
    body: JSON.stringify({ urls: good, client: clientId }),
  }, 5000);
  if (!r.ok) throw new Error("HTTP " + r.status);
  if (tab && tab.url && tab.id !== undefined) {   // only the page itself is remembered, never a page that merely holds a link
    const here = normalize(tab.url);
    if (here && good.includes(here)) { sentTabs.set(here, tab.id); saveState(); }
  }
  return { sent: good.length, skipped: urls.length - good.length };
}

// the menu items appear only on / for Civitai model and image pages
const CIVITAI_URLS = ["https://*.civitai.red/models/*", "https://*.civitai.red/images/*",
                      "https://*.civitai.com/models/*", "https://*.civitai.com/images/*"];
Promise.resolve(browser.contextMenus.removeAll()).catch(() => {}).then(() => {
  browser.contextMenus.create({
    id: "add-link", title: "Add link to Civitai Grabber list", contexts: ["link"], targetUrlPatterns: CIVITAI_URLS,
  });
  browser.contextMenus.create({
    id: "add-page", title: "Add this page to Civitai Grabber list", contexts: ["page"],
    documentUrlPatterns: CIVITAI_URLS,
  });
});
browser.contextMenus.onClicked.addListener(async (menu, tab) => {
  const url = menu.menuItemId === "add-link" ? menu.linkUrl : menu.pageUrl;
  try {
    const r = await addUrls([url], menu.menuItemId === "add-page" ? tab : null);
    if (r.sent) {
      flash("+" + r.sent, "#1a7f37");
    } else {
      flash("×", "#9a6700");
      notify("This is not a Civitai model or image page - nothing was added.");
    }
  } catch (e) {
    flash("!", "#c62828");
    let hint = "Start the program and try again.";
    try {
      const li = await browser.storage.local.get(["launcher"]);
      if (li.launcher) hint = "Open the Bridge window (toolbar button) to start it.";
    } catch (x) { /* keep the default hint */ }
    notify(e instanceof NotRunning
      ? "The Civitai Grabber program is NOT running - the link was NOT added. " + hint
      : "Could not add the link: " + e.message);
  }
});

setConnected(false);
ready.then(updateBadge);   // clears a badge left over from an earlier version

// ---- closing the tabs of finished links (setting in the popup: never / always / ask)
let askTimer = null;

async function closeTabEntries(entries) {
  let closed = 0;
  for (const e of entries) {
    try {
      const t = await browser.tabs.get(e.tabId);
      if (pageKey(t.url) !== pageKey(e.url)) { info.news += " - tab shows another page"; continue; }   // a changed slug or query does not matter
      const sib = await browser.tabs.query({ windowId: t.windowId });
      if (sib.length < 2) { info.news += " - last tab of its window, kept"; continue; }               // never close the last tab of a window
      await browser.tabs.remove(t.id);
      closed++;
      info.news += " - tab closed";
    } catch (err) { info.news += " - tab already gone"; }
  }
  return closed;
}

function askNotify() {
  const n = pendingClose.length;
  if (!n) return;
  browser.notifications.create("close-tabs", {
    type: "basic", title: "Civitai Grabber", iconUrl: browser.runtime.getURL("icon.png"),
    message: `${n} browser tab(s) of finished links are waiting. Click here (or the toolbar button) to choose which to close and which to keep.`,
  }).catch(() => {});
}
// the tabs waiting for the user's decision, with their titles (the popup shows them as a list of check boxes)
async function pendingItems() {
  const out = [];
  for (const e of pendingClose.slice()) {
    let title = "";
    try { title = (await browser.tabs.get(e.tabId)).title || ""; } catch (err) { /* the tab is gone */ }
    out.push({ tabId: e.tabId, url: e.url, title });
  }
  return out;
}
// close (doClose) or just stop asking about (keep open) the chosen tabs
async function resolvePending(ids, doClose) {
  await ready;
  const set = new Set(ids);
  const take = pendingClose.filter((e) => set.has(e.tabId));
  for (let i = pendingClose.length - 1; i >= 0; i--) if (set.has(pendingClose[i].tabId)) pendingClose.splice(i, 1);
  saveState();
  const n = doClose ? await closeTabEntries(take) : take.length;
  if (!pendingClose.length) browser.notifications.clear("close-tabs").catch(() => {});
  return n;
}
async function closePending() {
  await ready;
  const list = pendingClose.splice(0);
  saveState();
  const n = await closeTabEntries(list);
  browser.notifications.clear("close-tabs").catch(() => {});
  return n;
}
browser.notifications.onClicked.addListener(async (id) => {
  if (id !== "close-tabs") return;
  try { await (browser.action || browser.browserAction).openPopup(); } catch (e) { /* the browser did not allow it: the toolbar button does the same */ }
});

function removeAttention(url) {
  const i = attention.findIndex((a) => a.url === url);
  if (i >= 0) attention.splice(i, 1);
}

async function openAttention(url) {
  try {
    const tabs = await browser.tabs.query({});
    const t = tabs.find((x) => x.url && normalize(x.url) === url);
    if (t) {
      await browser.tabs.update(t.id, { active: true });
      await browser.windows.update(t.windowId, { focused: true });
    } else {
      await browser.tabs.create({ url });
    }
  } catch (e) { /* ignore */ }
  removeAttention(url);
  saveState();
  updateBadge();
}

async function handleEvent(job) {
  await ready;
  const key = normalize(job.url);
  if (job.event === "attention") {          // the link is done, but something was not downloaded: keep its page, mark it
    if (!key) return;
    removeAttention(key);
    attention.push({ url: key, note: job.note || "needs a look" });
    saveState();
    updateBadge();
    notify(`${job.note || "Some files were not downloaded"} - the page stays open; see "Needs attention" in the extension window.`);
    return;
  }
  if (job.event !== "finished") return;
  if (key && attention.some((a) => a.url === key)) { removeAttention(key); updateBadge(); }
  let sk = key && sentTabs.has(key) ? key : undefined;      // the program may report the link a little differently than it was added
  if (key && sk === undefined) for (const k of sentTabs.keys()) if (pageKey(k) && pageKey(k) === pageKey(key)) { sk = k; break; }
  const tabId = sk !== undefined ? sentTabs.get(sk) : undefined;
  info.news = `finished ${pageKey(key) || key}: ` + (tabId === undefined ? "no remembered tab (the link was not added from its own page, or from another browser)" : `tab ${tabId}, mode ${closeMode}`);
  if (tabId === undefined) return;
  sentTabs.delete(sk);
  if (closeMode === "always") {
    saveState();
    closeTabEntries([{ tabId, url: key }]);
  } else if (closeMode === "ask") {
    pendingClose.push({ tabId, url: key });
    saveState();
    clearTimeout(askTimer);
    askTimer = setTimeout(askNotify, 4000);   // one question for a whole batch
  } else {
    saveState();
  }
}

// ---- starting the program: no tab involved. The browser runs a small helper (native messaging) that the
// program registers with its permission; the helper opens the script like a double click.
async function launchGrabber() {
  try {
    await browser.runtime.sendNativeMessage("civitai_grabber", { cmd: "start" });
  } catch (e) {
    if (/no such native application|not found|forbidden|permission denied/i.test(String((e && e.message) || e))) throw new Error("not-registered");
    // anything else: the helper starts the program and ends without an answer - that is normal
  }
  fastUntil = Date.now() + 25000;
}

// ---- the popup asks through messages (a service worker has no page that the popup could reach)
async function handleCommand(m) {
  await ready;
  switch (m && m.cmd) {
    case "state": {
      if (!base) await findServer();   // fresh answer right after the worker has been started
      const li = await browser.storage.local.get(["seen", "launcher"]);
      return { info: { ...info }, pending: pendingClose.length, pendingList: await pendingItems(), attention, seen: !!li.seen, launcher: !!li.launcher };
    }
    case "add":
      try { return await addUrls(m.urls || [], m.tab); }
      catch (e) { return { error: String((e && e.message) || e), notRunning: e instanceof NotRunning }; }
    case "launch":
      try { await launchGrabber(); return { ok: true }; } catch (e) { return { error: String(e.message || e) }; }
    case "closePending":
      return { closed: await closePending() };
    case "closeSelected":
      return { closed: await resolvePending(m.ids || [], true) };
    case "keepSelected":
      return { kept: await resolvePending(m.ids || [], false) };
    case "openAttention":
      await openAttention(m.url);
      return { ok: true };
    case "clearAttention":
      attention.length = 0;
      saveState();
      updateBadge();
      return { ok: true };
    default:
      return { error: "unknown command" };
  }
}
browser.runtime.onMessage.addListener((m, sender, sendResponse) => {
  handleCommand(m).then(sendResponse, (e) => sendResponse({ error: String(e) }));
  return true;   // the answer is sent later
});

mainLoop();
