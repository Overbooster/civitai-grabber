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
  st.textContent = i.status + (i.status.startsWith("connected") && i.grabberVersion ? " (Civitai Grabber v" + i.grabberVersion + ")" : "");
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
  addHint.textContent = ok ? "" : "Open a Civitai model or image page to add it.";
})();

browser.storage.local.get("closeMode").then((r) => { mode.value = r.closeMode || "never"; });
mode.addEventListener("change", () => browser.storage.local.set({ closeMode: mode.value }));
$("pendClose").addEventListener("click", async () => { await rpc({ cmd: "closeSelected", ids: checkedTabs() }); render(); });
$("pendKeep").addEventListener("click", async () => { await rpc({ cmd: "keepSelected", ids: checkedTabs() }); render(); });

render();
setInterval(render, 700);
