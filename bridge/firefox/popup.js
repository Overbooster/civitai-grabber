"use strict";
const rpc = (msg) => browser.runtime.sendMessage(msg);
const $ = (id) => document.getElementById(id);

$("ver").textContent = "v" + browser.runtime.getManifest().version;
const msg = $("msg");
const addBtn = $("addPage");
const addHint = $("addHint");
const mode = $("closeMode");
const unchecked = new Set();   // tabs the user has unchecked in the "finished pages" list (all others are checked)

// finished links whose page must be looked at again (some files were not downloaded)
function labelOf(url) {
  const m = url.match(/\/(models|images)\/(\d+)/);
  return m ? (m[1] === "models" ? "Model " : "Image ") + m[2] : url;
}
function renderAttention(list) {
  const box = $("attention");
  box.style.display = list.length ? "block" : "none";
  const ul = $("attList");
  const key = JSON.stringify(list);
  if (ul.dataset.key === key) return;        // nothing changed: do not rebuild (keeps clicks working)
  ul.dataset.key = key;
  ul.textContent = "";
  for (const a of list) {
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.textContent = labelOf(a.url);
    link.title = a.url;
    link.addEventListener("click", () => rpc({ cmd: "openAttention", url: a.url }).then(render));
    const note = document.createElement("span");
    note.textContent = " - " + a.note;
    li.append(link, note);
    ul.append(li);
  }
}
$("attClear").addEventListener("click", () => rpc({ cmd: "clearAttention" }).then(render));

async function render() {
  const s = await rpc({ cmd: "state" });
  if (!s || !s.info) return;
  const i = s.info;
  const connected = i.status.startsWith("connected") || i.status.startsWith("working");
  // one message only: when the program is not running, the box below says so (no duplicate line here)
  const st = $("status");
  st.style.display = connected ? "block" : "none";
  st.textContent = i.status.startsWith("connected") && i.grabberVersion ? "connected to Civitai Grabber v" + i.grabberVersion : i.status;
  st.className = "ok";
  const cnt = $("count");
  cnt.style.display = connected ? "block" : "none";
  cnt.textContent = "Pages fetched: " + i.done;
  $("last").textContent = [i.last ? "Last: " + i.last : "", i.news ? "News: " + i.news : ""].filter(Boolean).join("  |  ");

  const box = $("launchBox");
  box.style.display = connected ? "none" : "block";
  if (!connected) {
    const lm = $("launchMsg");
    const btn = $("launch");
    btn.style.display = "none";
    if (s.seen && s.launcher) {
      if (!lm.dataset.busy) lm.textContent = "Civitai Grabber is not running.";
      btn.style.display = "block";
    } else if (s.seen) {
      lm.textContent = "Civitai Grabber is not running. Start it yourself (for a Start button here, allow \u201claunch from browser\u201d in its help window).";
    } else {
      lm.textContent = "No Civitai Grabber has been found by this extension yet. Start the program once; this window will remember it.";
    }
  } else {
    delete $("launchMsg").dataset.busy;
  }
  renderAttention(s.attention || []);
  renderPending(s.pendingList || []);
}

function renderPending(list) {
  const box = $("pendingBox");
  box.style.display = list.length ? "block" : "none";
  const ul = $("pendList");
  const key = JSON.stringify(list);
  if (ul.dataset.key === key) return;        // nothing changed: do not rebuild (keeps the check boxes as they are)
  ul.dataset.key = key;
  ul.textContent = "";
  for (const it of list) {
    const li = document.createElement("li");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !unchecked.has(it.tabId);
    cb.id = "pend" + it.tabId;
    cb.addEventListener("change", () => { if (cb.checked) unchecked.delete(it.tabId); else unchecked.add(it.tabId); });
    const lab = document.createElement("label");
    lab.htmlFor = cb.id;
    lab.textContent = " " + (it.title || labelOf(it.url));
    lab.title = it.url;
    li.append(cb, lab);
    ul.append(li);
  }
}
function checkedTabs() {
  return [...$("pendList").querySelectorAll("input")].filter((c) => c.checked).map((c) => Number(c.id.slice(4)));
}

$("launch").addEventListener("click", async () => {
  const lm = $("launchMsg");
  const r = await rpc({ cmd: "launch" });
  lm.dataset.busy = "1";
  lm.textContent = r && r.ok ? "Starting Civitai Grabber…"
    : "Starting from here is not set up. Start the program once by hand, open its help (?) window and press \u201cAllow launch from browser\u201d.";
});

addBtn.addEventListener("click", async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  const r = await rpc({ cmd: "add", urls: [tab.url], tab: { id: tab.id, url: tab.url } });
  if (r && r.error) {
    msg.className = "err";
    msg.textContent = r.notRunning
      ? "The Civitai Grabber script is NOT running. Nothing was added - start the script and try again."
      : "Could not add: " + r.error;
  } else {
    msg.className = "";
    msg.textContent = r.sent ? `Sent ${r.sent} link(s) to the list.` : "Nothing to add: this is not a Civitai model or image page.";
  }
});

// the button is live only on a Civitai model or image page
(async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  const ok = !!(tab && tab.url && normalize(tab.url));
  addBtn.disabled = !ok;
  $("addWrap").title = ok ? "" : NOT_CIVITAI;
  react.enabled = ok;
  paintTri();
  addHint.textContent = ok ? "" : "Open a Civitai model or image page to add it.";
})();

// three-way switches with icons (Tabler icons, as on the site): grey = leave as it is, green = switch on, orange = switch off
const TRI = ["neutral", "on", "off"];
const THUMB = ["M7 11v8a1 1 0 0 1 -1 1h-2a1 1 0 0 1 -1 -1v-7a1 1 0 0 1 1 -1h3a4 4 0 0 0 4 -4v-1a2 2 0 0 1 4 0v5h3a2 2 0 0 1 2 2l-1 5a2 3 0 0 1 -2 2h-7a3 3 0 0 1 -3 -3"];
const THUMB_FILLED = ["M13 3a3 3 0 0 1 2.995 2.824l.005 .176v4h2a3 3 0 0 1 2.98 2.65l.015 .174l.005 .176l-.02 .196l-1.006 5.032c-.381 1.626 -1.502 2.796 -2.81 2.78l-.164 -.008h-8a1 1 0 0 1 -.993 -.883l-.007 -.117l.001 -9.536a1 1 0 0 1 .5 -.865a2.998 2.998 0 0 0 1.492 -2.397l.007 -.202v-1a3 3 0 0 1 3 -3z", "M5 10a1 1 0 0 1 .993 .883l.007 .117v9a1 1 0 0 1 -.883 .993l-.117 .007h-1a2 2 0 0 1 -1.995 -1.85l-.005 -.15v-7a2 2 0 0 1 1.85 -1.995l.15 -.005h1z"];
const BELL = ["M10 5a2 2 0 1 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3h-16a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6", "M9 17v1a3 3 0 0 0 6 0v-1"];
const BELL_PLUS = ["M12.5 17h-8.5a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6a2 2 0 1 1 4 0a7 7 0 0 1 4 6v1", "M9 17v1a3 3 0 0 0 3.51 2.957", "M16 19h6", "M19 16v6"];
const BELL_MINUS = ["M12.5 17h-8.5a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6a2 2 0 1 1 4 0a7 7 0 0 1 4 6v1", "M9 17v1a3 3 0 0 0 3.51 2.957", "M16 19h6"];
const svg = (paths, o = {}) => {
  const NS = "http://www.w3.org/2000/svg";
  const el = document.createElementNS(NS, "svg");
  const set = (k, v) => el.setAttribute(k, v);
  set("width", "20"); set("height", "20"); set("viewBox", "0 0 24 24");
  set("fill", o.filled ? "currentColor" : "none"); set("stroke", o.filled ? "none" : "currentColor");
  set("stroke-width", "2"); set("stroke-linecap", "round"); set("stroke-linejoin", "round");
  if (o.flip) el.style.transform = "scaleY(-1)";
  for (const d of paths) { const p = document.createElementNS(NS, "path"); p.setAttribute("d", d); el.appendChild(p); }
  return el;
};
const TRI_VIEW = {
  likeMode: {
    neutral: { icon: () => svg(THUMB), tip: "Like: leave as it is" },
    on: { icon: () => svg(THUMB_FILLED, { filled: true }), tip: "Like: put a like" },
    off: { icon: () => svg(THUMB, { flip: true }), tip: "Like: take the like off" },
  },
  bellMode: {
    neutral: { icon: () => svg(BELL), tip: "Notifications: leave as they are" },
    on: { icon: () => svg(BELL_PLUS), tip: "Notifications: switch on" },
    off: { icon: () => svg(BELL_MINUS), tip: "Notifications: switch off" },
  },
};
const NOT_CIVITAI = "Works on Civitai pages only";
const react = { enabled: false, likeMode: "neutral", bellMode: "neutral" };
const TRI_BUTTONS = [["likeBtn", "likeWrap", "likeMode"], ["bellBtn", "bellWrap", "bellMode"]];
function paintTri() {
  for (const [id, wrapId, key] of TRI_BUTTONS) {
    const v = TRI_VIEW[key][react[key]];
    $(id).dataset.state = react[key];
    $(id).replaceChildren(v.icon());
    $(id).disabled = !react.enabled;
    $(wrapId).title = react.enabled ? v.tip : NOT_CIVITAI;    // the tooltip sits on the wrapper: a disabled button shows none of its own
  }
}
for (const [id, , key] of TRI_BUTTONS) {
  browser.storage.local.get(key).then((r) => { react[key] = TRI.includes(r[key]) ? r[key] : "neutral"; paintTri(); });
  $(id).addEventListener("click", () => {
    react[key] = TRI[(TRI.indexOf(react[key]) + 1) % TRI.length];
    paintTri();
    browser.storage.local.set({ [key]: react[key] });
  });
}
paintTri();

browser.storage.local.get("closeMode").then((r) => { mode.value = r.closeMode || "never"; });
mode.addEventListener("change", () => browser.storage.local.set({ closeMode: mode.value }));
$("pendClose").addEventListener("click", async () => { await rpc({ cmd: "closeSelected", ids: checkedTabs() }); render(); });
$("pendKeep").addEventListener("click", async () => { await rpc({ cmd: "keepSelected", ids: checkedTabs() }); render(); });

render();
setInterval(render, 700);

// dark window: the program tells it (Setup of the program); the last answer is remembered while the program is closed
const applyDark = (v) => document.body.classList.toggle("dark", !!v);
browser.storage.local.get("bridgeDark").then((r) => applyDark(r.bridgeDark));
browser.storage.onChanged.addListener((ch, area) => { if (area === "local" && ch.bridgeDark) applyDark(ch.bridgeDark.newValue); });
