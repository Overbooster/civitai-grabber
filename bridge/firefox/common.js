"use strict";
// Shared by the background script and the popup.
// Chromium calls the extension API "chrome", Firefox "browser" (both return promises in the places used here).
var browser = globalThis.browser || globalThis.chrome;

// "models/123" or "images/456" of a Civitai page address (slug, query and hash ignored); null = not such a page
function pageKey(u) {
  try {
    const x = new URL(u);
    if (!/(^|\.)civitai\.(red|com)$/.test(x.hostname)) return null;
    const m = x.pathname.match(/^\/(models|images)\/(\d+)/);
    return m ? m[1] + "/" + m[2] : null;
  } catch (e) { return null; }
}

// Civitai model / image page address -> the address that is sent to the program (null = not such a page)
function normalize(u) {
  try {
    const x = new URL(u);
    if (!/(^|\.)civitai\.(red|com)$/.test(x.hostname)) return null;
    const m = x.pathname.match(/^\/(models|images)\/\d+/);
    if (!m) return null;
    x.hash = "";
    if (m[1] === "images") x.search = "";   // image links need no query
    return x.toString();
  } catch (e) { return null; }
}
