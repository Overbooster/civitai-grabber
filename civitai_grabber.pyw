#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Civitai Grabber v0.28 - batch downloader for Civitai LoRA models and their example
images/videos with generation metadata. Python 3.8+, standard library only
(Tkinter is included in the Windows installer from python.org).

Run with a window:   python civitai_grabber.pyw
Run without window:  python civitai_grabber.pyw task.txt

Settings can be entered in the window or given in a txt task file:
    TOKEN: your_api_token
    PATH: d:\\AI\\LoRA\\
    PREFIX: k2-pers-
    MODEL: 1               1 = download the model file, 0 = skip it
    PICS: 4                example images/videos of the model version: a number, all, or 0/empty for none
    GALLERY: 0             gallery images (uploaded by users) per model: a number, all, or 0 (needs the browser bridge)
    VIDEO: 1               1 = also download video examples (they count towards PICS), 0 = skip them
    ORIGINAL: 1            1 = try to use the original file name from the image page
    COMFY: 0               1 = (experimental) save the ComfyUI workflow found in the metadata as a .json
                           next to each image, named like the image
    DSCR: dscr.txt         description file name (.txt or .md; no extension = .txt)
    DSCR_AS_MODEL: 0       1 = name the description file after the model (extension taken from DSCR)
    WEBP2JPG: 0            1 = convert downloaded WebP images to JPG (needs: py -m pip install pillow)
    EXISTING: ask          ask / skip / overwrite - what to do if already downloaded
    USE_SUBFOLDER: 0       1 = save single images (/images/ID) into IMGFOLDER (only when no model link
                           came before them in the same run; otherwise they go to that model's folder)
    IMGFOLDER:             subfolder name or nested path inside PATH (a/b/c), or a full path
    https://civitai.red/models/1800132/kayla?modelVersionId=3282255
    https://civitai.red/images/141345317
Lines starting with # are ignored. Empty values are ignored too (the program window supplies them).
    BRIDGE: 1              1 = accept pages from the Firefox bridge extension (local server on 127.0.0.1)

This is a .pyw file: double-click it to start without a black console window.
"""
import os
import re
import socket
import sys
import json
import time
import html
import queue
import threading
import traceback
import http.client
import http.server
import socketserver
import subprocess
import datetime
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser

VERSION = "0.28"

# ======================================================================================================
# SWITCHES - change True/False here, nothing else needs editing
SHOW_TXT_BUTTONS = False   # True: show the "Create sample txt" and "Load from txt" buttons again
TASKBAR_SIGNALS = True     # False: no signals on the taskbar button at all (Windows only)
TASKBAR_FLASH = "icon"     # blink when a link arrives / a run ends: "icon" = the icon blinks with a white plate, "system" = Windows blinks the whole button (orange), "off"
TASKBAR_WAITING = "green"  # links waiting in the list: "green" = whole button green, "yellow" = whole button yellow, "plate" = white plate around the icon, "none"
# ======================================================================================================
CHECK_INDENT = 0  # px from the left edge of a check box widget to its square (used to line up rows of the window)
SCHEME = "https"  # change only for local tests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

KNOWN_META = ["prompt", "negativePrompt", "cfgScale", "steps", "sampler", "scheduler",
              "seed", "Model", "Size", "clipSkip", "denoise", "Model hash"]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGFILE = os.path.join(SCRIPT_DIR, "civitai_grabber.log")
HISTORY = os.path.join(SCRIPT_DIR, "civitai_grabber_history.jsonl")
SETTINGS = os.path.join(SCRIPT_DIR, "civitai_grabber_settings.json")

BRIDGE_TIMEOUT = 90  # seconds to wait for one page from the browser

STATE = {"log": None, "bridge_failures": 0, "bridge_off": False, "stop": None, "blocked": 0, "page_blocked": False, "model_folder": None, "model_name": None, "model_failed": False, "pillow_warned": False, "net_fail": 0, "net_down": False}

DEFAULTS = {"BRIDGE": "1", "TOKEN": "", "PATH": "", "PREFIX": "", "PICS": "4", "VIDEO": "1", "ORIGINAL": "1",
            "COMFY": "0", "EXISTING": "ask", "IMGFOLDER": "", "USE_SUBFOLDER": "0", "DSCR": "dscr.txt", "DSCR_AS_MODEL": "0", "MODEL": "1", "GALLERY": "0",
            "WEBP2JPG": "0"}


SECRETS = set()  # strings (the API token) that must never appear in a log


def scrub(text):
    """Hides the API token in a text: both ?token=... parameters and the token itself."""
    text = re.sub(r"([?&]token=)[^&\s)\"']+", r"\1***", str(text))
    for sec in SECRETS:
        if sec and len(sec) >= 6:
            text = text.replace(sec, "***")
    return text


def file_log(msg):
    """Append a line to civitai_grabber.log next to the script."""
    msg = scrub(msg)
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def open_path(path):
    """Open a file in the default program (Windows / macOS / Linux)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:  # noqa
        file_log("open_path failed: %r" % (e,))
        return False


ICON_PNG_B64 = (
    "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"
)

# Taskbar icon states (64 px): white plate = links waiting (TASKBAR_WAITING = "plate"), red plate = errors, check mark = finished
ICON_STATES = {
    "pending": (
        "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"
    ),
    "error": (
        "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"
        "RK5CYII="
    ),
    "done": (
        "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"
    ),
}

NATIVE_NAME = "civitai_grabber"
EXTENSION_ID = "civitai-grabber-bridge@local"
# one entry per browser family (HKEY_CURRENT_USER): Firefox and the Chromium-based browsers
NATIVE_KEY = r"Software\Mozilla\NativeMessagingHosts\civitai_grabber"
CHROMIUM_KEYS = [r"Software\Google\Chrome\NativeMessagingHosts\civitai_grabber",
                 r"Software\Microsoft\Edge\NativeMessagingHosts\civitai_grabber",
                 r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\civitai_grabber",
                 r"Software\Chromium\NativeMessagingHosts\civitai_grabber"]
CHROMIUM_EXTENSION_IDS = ["ffefpfokecbbmifgnhmiedebmgoofhgc"]  # fixed by the key inside the Chromium package of the extension
OLD_LAUNCH_KEY = r"Software\Classes\civitai-grabber"  # v0.16-0.17: link type that needed a browser tab
HOST_JSON = os.path.join(SCRIPT_DIR, "civitai_grabber_host.json")
HOST_JSON_CHROMIUM = os.path.join(SCRIPT_DIR, "civitai_grabber_host_chromium.json")
HOST_BAT = os.path.join(SCRIPT_DIR, "civitai_grabber_launch.bat")
CONSENT_TEXT = ("To start Civitai Grabber from the browser extension, your permission is needed.\n\n"
                "This adds a small entry for each supported browser (Firefox, Chrome, Edge, Brave) in the registry, under\n"
                "HKEY_CURRENT_USER\\Software\\<browser>\\NativeMessagingHosts\\civitai_grabber\n"
                "and three small files next to this script (civitai_grabber_host.json, civitai_grabber_host_chromium.json, "
                "civitai_grabber_launch.bat). The entries can start only this script. No administrator rights are needed "
                "and nothing else on the computer is changed. You can remove it at any time in the help (?) window.\n\nAllow?")


def launcher_registered():
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg
    except ImportError:
        return False
    for key in [NATIVE_KEY] + CHROMIUM_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                path = winreg.QueryValue(k, "")
            if path and os.path.exists(path) and os.path.exists(HOST_BAT):
                return True
        except OSError:
            continue
    return False


def register_launcher():
    """(Re)writes the native-messaging entries so that the extension starts THIS script. Returns an error text or ''.
    The helper .bat asks Explorer to open the script, exactly like a double click; the program then is not a child of
    the browser and keeps running when the browser is closed."""
    if not sys.platform.startswith("win"):
        return "Launching from the browser is implemented for Windows only."
    try:
        import winreg
        with open(HOST_BAT, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("@echo off\nchcp 65001 >nul\nrem Written by Civitai Grabber: the browser extension runs this file to start the program.\n"
                    "explorer.exe \"%s\"\n" % os.path.abspath(__file__))
        with open(HOST_JSON, "w", encoding="utf-8") as f:
            json.dump({"name": NATIVE_NAME, "description": "Starts Civitai Grabber", "path": HOST_BAT,
                       "type": "stdio", "allowed_extensions": [EXTENSION_ID]}, f, indent=1)
        with open(HOST_JSON_CHROMIUM, "w", encoding="utf-8") as f:
            json.dump({"name": NATIVE_NAME, "description": "Starts Civitai Grabber", "path": HOST_BAT,
                       "type": "stdio", "allowed_origins": ["chrome-extension://%s/" % i for i in CHROMIUM_EXTENSION_IDS]}, f, indent=1)
        for key, manifest in [(NATIVE_KEY, HOST_JSON)] + [(k, HOST_JSON_CHROMIUM) for k in CHROMIUM_KEYS]:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
                winreg.SetValue(k, "", winreg.REG_SZ, manifest)
        BRIDGE.launcher = True
        return ""
    except OSError as e:
        return str(e)


def unregister_launcher():
    if not sys.platform.startswith("win"):
        return ""
    try:
        import winreg
        for key in [NATIVE_KEY] + CHROMIUM_KEYS:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
            except FileNotFoundError:
                pass
        for fn in (HOST_JSON, HOST_JSON_CHROMIUM, HOST_BAT):
            try:
                os.remove(fn)
            except FileNotFoundError:
                pass
        BRIDGE.launcher = False
        return ""
    except OSError as e:
        return str(e)


def old_launcher_present():
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, OLD_LAUNCH_KEY + r"\shell\open\command"):
            return True
    except OSError:
        return False


def remove_old_launcher():
    try:
        import winreg
        for sub in (r"\shell\open\command", r"\shell\open", r"\shell", ""):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, OLD_LAUNCH_KEY + sub)
            except FileNotFoundError:
                pass
    except OSError:
        pass


def another_instance_running():
    """True if a Civitai Grabber answers on one of the bridge ports (one window is enough).
    All ports are probed at the same time (a closed local port can take a long time to refuse on Windows),
    and the system proxy is bypassed on purpose."""
    found = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def probe(port):
        try:
            req = urllib.request.Request("http://127.0.0.1:%d/ping" % port, headers={"X-Grabber": "1"})
            with opener.open(req, timeout=0.6) as r:
                if json.loads(r.read().decode()).get("app") == "civitai-grabber":
                    found.append(port)
        except Exception:  # noqa
            pass

    threads = [threading.Thread(target=probe, args=(port,), daemon=True) for port in Bridge.PORTS]
    for t in threads:
        t.start()
    end = time.time() + 1.0
    for t in threads:
        t.join(max(0.0, end - time.time()))
    return bool(found)


class Stopped(Exception):
    pass


# ------------------------------------------------------------- history

def _norm(path):
    return os.path.normcase(os.path.normpath(path)) if path else ""


def history_add(key, url, folder, status, file=None):
    try:
        with open(HISTORY, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "key": key, "url": url, "folder": folder, "status": status, "file": file},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def history_find(key, folder=None):
    """Latest successful record for the key (and folder, if given)."""
    try:
        with open(HISTORY, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("key") == key and r.get("status") == "ok" and (folder is None or _norm(r.get("folder")) == _norm(folder)):
            return r
    return None


# ----------------------------------------------------------------- network

def http_get(url, token=None, timeout=60, retries=3):
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if token:
        headers["Authorization"] = "Bearer " + token
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            last = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise last


class _Server(http.server.ThreadingHTTPServer):
    """HTTPServer without the slow socket.getfqdn() lookup of the standard class; on Windows the port is
    not shared with another process (SO_REUSEADDR means something else there)."""
    allow_reuse_address = not sys.platform.startswith("win")

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class _BridgeHandler(http.server.BaseHTTPRequestHandler):
    """Local endpoint for the browser extension. Only requests that carry the X-Grabber header and,
    if an Origin is present, come from an extension are served (ordinary web pages cannot use it)."""

    def _send(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _client_gone(self):
        try:
            import select
            readable, _, _ = select.select([self.connection], [], [], 0)
            if readable:
                return self.connection.recv(1, socket.MSG_PEEK) == b""
        except (OSError, ValueError):
            return True
        return False

    def _allowed(self):
        origin = self.headers.get("Origin")
        if origin and not origin.startswith(("moz-extension://", "chrome-extension://")):
            self._send(403, b'{"error":"forbidden"}')
            return False
        if self.headers.get("X-Grabber") != "1":
            self._send(403, b'{"error":"forbidden"}')
            return False
        return True

    def do_OPTIONS(self):  # preflight (only extensions get a positive answer)
        origin = self.headers.get("Origin") or ""
        self.send_response(204)
        if origin.startswith(("moz-extension://", "chrome-extension://")):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "X-Grabber, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._allowed():
            return
        path = self.path.split("?")[0]
        if path == "/ping":
            BRIDGE.last_poll = time.time()
            self._send(200, json.dumps({"app": "civitai-grabber", "version": VERSION, "launcher": BRIDGE.launcher}).encode())
        elif path == "/job":
            BRIDGE.last_poll = time.time()
            cid = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("c") or [""])[0][:64]
            job, own = None, False
            for _ in range(20):  # up to ~20 s, in one-second slices
                ev = BRIDGE.pop_event(cid)  # news for THIS browser (its link is finished / needs attention)
                if ev:
                    job, own = ev, True
                    break
                try:
                    job = BRIDGE.jobs.get(timeout=1)
                    break
                except queue.Empty:
                    if self._client_gone():  # the browser was closed while waiting: do not take jobs for it
                        return
                    BRIDGE.last_poll = time.time()
            BRIDGE.last_poll = time.time()
            if job is None:
                self._send(204)
                return
            try:
                self._send(200, json.dumps(job).encode())
            except OSError:
                if job.get("id"):
                    BRIDGE.jobs.put(job)  # the browser has gone away: the job goes back to the queue
                elif own:
                    BRIDGE.events_of(cid).put(job)
                return
            if job.get("id"):
                BRIDGE.taken[job["id"]] = time.time()
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if not self._allowed():
            return
        if self.path.split("?")[0] == "/add":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(n).decode("utf-8"))
                urls = data.get("urls") or []
                client = str(data.get("client") or "")[:64]
                good = [u for u in urls if isinstance(u, str) and
                        re.match(r"^https?://[^/]*civitai\.[a-z]+/(models|images)/\d+", u)]
                for u in good:
                    if client:
                        BRIDGE.owner[page_key(u)] = client
                    BRIDGE.added.put(u)
                self._send(200, json.dumps({"ok": True, "queued": len(good)}).encode())
            except Exception as e:  # noqa
                file_log("bridge bad /add: %r" % (e,))
                self._send(400, b'{"error":"bad request"}')
            return
        if self.path.split("?")[0] != "/result":
            self._send(404, b'{"error":"not found"}')
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            with BRIDGE.cond:
                BRIDGE.results[data["id"]] = data
                BRIDGE.cond.notify_all()
            self._send(200, b'{"ok":true}')
        except Exception as e:  # noqa
            file_log("bridge bad result: %r" % (e,))
            self._send(400, b'{"error":"bad request"}')

    def log_message(self, *args):
        pass


def page_key(url):
    """"models/123" or "images/456" - the part of a Civitai address that identifies the page."""
    m = re.search(r"/(models|images)/(\d+)", url or "")
    return "%s/%s" % (m.group(1), m.group(2)) if m else ""


class Bridge:
    """Lets the browser extension fetch pages with the logged-in browser session on behalf of the script."""
    PORTS = list(range(47653, 47663))

    def __init__(self):
        self.jobs = queue.Queue()
        self.results = {}
        self.cond = threading.Condition()
        self.last_poll = 0.0
        self.next_id = 1
        self.taken = {}  # job id -> time it was handed to a browser
        self.launcher = False  # is the launch entry registered (reported to the extension)
        self.added = queue.Queue()  # links sent from the browser
        self.owner = {}  # "models/123" -> id of the browser that added the link (its news goes back to it)
        self.events = {}  # browser id -> queue of news for that browser
        self.server = None
        self.port = None

    def start(self):
        if self.server:
            return self.port
        for port in self.PORTS:
            try:
                srv = _Server(("127.0.0.1", port), _BridgeHandler)
            except OSError:
                continue
            srv.daemon_threads = True
            self.server, self.port = srv, port
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            file_log("bridge listening on 127.0.0.1:%d" % port)
            return port
        file_log("bridge: no free port")
        return None

    def stop(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:  # noqa
                pass
        self.server, self.port, self.last_poll = None, None, 0.0

    def connected(self):
        return bool(self.server) and time.time() - self.last_poll < 30

    def events_of(self, cid):
        return self.events.setdefault(cid, queue.Queue())

    def pop_event(self, cid):
        if not cid or cid not in self.events:
            return None
        try:
            return self.events[cid].get_nowait()
        except queue.Empty:
            return None

    def notify(self, event, url, note=""):
        """News for the extension: "finished" (it may close the tab of that link) or "attention" (something needs a look).
        It goes to the browser that added the link; if that is unknown (an older extension), to whichever browser asks first."""
        if self.connected():
            msg = {"id": 0, "kind": "event", "event": event, "url": url, "note": note}
            owner = self.owner.get(page_key(url))
            if owner:
                self.events_of(owner).put(msg)
            else:
                self.jobs.put(msg)

    def notify_finished(self, url):
        self.notify("finished", url)

    def request(self, url, kind="page", timeout=120):
        ids = []

        def enqueue():
            with self.cond:
                jid = self.next_id
                self.next_id += 1
            ids.append(jid)
            self.jobs.put({"id": jid, "url": url, "kind": kind})

        note = STATE.get("log") or file_log
        enqueue()
        t0 = last_note = time.time()
        retried = False
        try:
            with self.cond:
                while True:
                    got = next((j for j in ids if j in self.results), None)
                    if got is not None:
                        return self.results.pop(got)
                    stop = STATE.get("stop")
                    if stop is not None and stop.is_set():
                        raise Stopped()
                    now = time.time()
                    if now - t0 > timeout:
                        raise IOError("the browser did not answer in %d s" % timeout)
                    taken_at = self.taken.get(ids[-1])
                    if not retried and taken_at and now - taken_at > 30:  # taken, but never answered (browser closed?)
                        retried = True
                        note("    no answer for 30 s - asking the browser again")
                        enqueue()
                    TB["wait_browser"] = now - t0 > 8
                    if now - last_note > 10:
                        last_note = now
                        if not self.connected():
                            note("    waiting for the browser: it is not connected to this program - is it open? (%d s)…" % (now - t0))
                        else:
                            note("    still waiting for the browser (%d s)…" % (now - t0))
                    self.cond.wait(1.0)
        finally:
            TB["wait_browser"] = False
            with self.cond:
                for j in ids:
                    self.results.pop(j, None)
                    self.taken.pop(j, None)


BRIDGE = Bridge()


def fetch_page(url, token=None):
    if BRIDGE.connected() and not STATE["bridge_off"]:
        note = STATE.get("log") or file_log
        try:
            r = BRIDGE.request(url, "page", timeout=BRIDGE_TIMEOUT)
            if r.get("error"):
                raise IOError("browser bridge: %s" % r["error"])
        except Stopped:
            raise
        except IOError as e:
            STATE["bridge_failures"] += 1
            note("    the browser did not deliver the page (%s)" % e)
            if STATE["bridge_failures"] >= 2:
                STATE["bridge_off"] = True
                note("  Browser bridge switched off for the rest of this run: direct requests are used instead")
                return _fetch_page_direct(url, token)
            raise  # this link fails (it stays in the list) instead of silently losing the metadata
        STATE["bridge_failures"] = 0
        if r.get("status") == 200 and r.get("text"):
            file_log("page via browser bridge (%s): %s" % (r.get("via"), url))
            return r["text"]
        raise urllib.error.HTTPError(url, int(r.get("status") or 502), "via browser", None, None)
    return _fetch_page_direct(url, token)


def _fetch_page_direct(url, token=None):
    """Open an HTML page with browser-like headers. First without the API token, then with it."""
    base = {"User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9", "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1"}
    last = None
    for use_token in ([False, True] if token else [False]):
        headers = dict(base)
        if use_token:
            headers["Authorization"] = "Bearer " + token
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403):
                continue
            raise
    raise last


def get_json(url, token=None):
    return json.loads(http_get(url, token).decode("utf-8"))


def sniff_ext(path, ctype=""):
    """Real file format from the first bytes (fallback: Content-Type)."""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        head = b""
    if head.startswith(b"\x89PNG"):
        return ".png"
    if head[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[4:8] == b"ftyp":
        return ".mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    ctype = (ctype or "").split(";")[0].strip().lower()
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
            "video/mp4": ".mp4", "video/webm": ".webm"}.get(ctype, ".jpg")


def download_file(url, dest, log, stop, token=None, attempts=5, auto_ext=False, name_ext=""):
    """Download into .part with retries and resume after a dropped connection.
    auto_ext=True: dest is a path WITHOUT extension; the extension is taken from the file content.
    The token goes into ?token=, not into a header: the header breaks the redirect to file storage.
    Returns the path of the finished file."""
    shown_url = url
    if token:
        url = url + ("&" if "?" in url else "?") + "token=" + urllib.parse.quote(token)
    tmp = dest + ".part"
    ctype = ""

    def finish():
        final = dest
        if auto_ext:
            ext = sniff_ext(tmp, ctype)
            if ext == ".jpg" and name_ext.lower() in (".jpg", ".jpeg"):
                ext = name_ext
            final = dest + ext
        os.replace(tmp, final)
        TB["cur"] = 0.0
        file_log("download ok: %s  content-type=%s  size=%d  url=%s" %
                 (os.path.basename(final), ctype, os.path.getsize(final), shown_url))
        return final

    for attempt in range(1, attempts + 1):
        if stop.is_set():
            raise Stopped()
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        headers = {"User-Agent": UA}
        if have:
            headers["Range"] = "bytes=%d-" % have
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                status = getattr(r, "status", 200)
                ctype = r.headers.get("Content-Type") or ctype
                if have and status != 206:  # server did not honour Range - start over
                    have = 0
                length = int(r.headers.get("Content-Length") or 0)
                total = have + length if length else 0
                done = have
                TB["phase"] = "download"
                next_mark = (done * 100 // total // 10 * 10 + 10) if total else 10
                if have:
                    log("    resuming from %.1f MB" % (have / 1048576))
                with open(tmp, "ab" if have else "wb") as f:
                    while True:
                        if stop.is_set():
                            raise Stopped()
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            TB["cur"] = done / total
                        if total and total > 3 * 1048576:
                            pct = done * 100 // total
                            if pct >= next_mark:
                                log("    %d%%  (%.1f of %.1f MB)" % (pct, done / 1048576, total / 1048576))
                                next_mark = pct // 10 * 10 + 10
            if total and done < total:
                raise IOError("connection dropped before the end of the file")
            return finish()
        except Stopped:
            raise
        except urllib.error.HTTPError as e:
            if e.code == 416 and have:  # nothing left to resume - the file is complete
                return finish()
            if e.code in (429, 500, 502, 503, 504) and attempt < attempts:
                log("    server answered %s, retry %d/%d" % (e.code, attempt, attempts - 1))
                stop.wait(3 * attempt)
                continue
            raise
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            if attempt >= attempts or STATE.get("net_down"):
                raise
            wait = 3 * attempt
            log("    connection problem (%s), retry %d/%d in %d s" % (type(e).__name__, attempt, attempts - 1, wait))
            file_log("download retry: %r" % (e,))
            stop.wait(wait)


# what the taskbar button shows (written by the worker thread, read by the window)
TB = {"phase": "idle", "failed": 0, "total": 0, "idx": 0, "cur": 0.0, "wait_browser": False}
ATTENTION = {}  # link -> note: finished links that need a look (some files were not downloaded)


class TaskbarProgress:
    """Standard Windows taskbar signals for the program's button, through ctypes: progress bar over the whole button
    (ITaskbarList3) and blinking (FlashWindowEx). Does nothing on other systems and switches itself off on any error."""

    def __init__(self):
        self.p = None
        self.hwnd = 0
        self.fail = 0
        self._val = self._state = None

    def attach(self, root):
        if not sys.platform.startswith("win"):
            return False
        try:
            import ctypes
            import uuid
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.GetParent.restype = wintypes.HWND
            user32.GetParent.argtypes = [wintypes.HWND]
            self.hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()

            class GUID(ctypes.Structure):
                _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

            def guid(text):
                return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)

            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)
            ptr = ctypes.c_void_p()
            hr = ole32.CoCreateInstance(ctypes.byref(guid("56FDF344-FD6D-11D0-958A-006097C9A090")), None, 1,
                                        ctypes.byref(guid("EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF")), ctypes.byref(ptr))
            if hr != 0 or not ptr.value:
                return False
            vt = ctypes.cast(ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
            init = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vt[3])
            self._val = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.c_ulonglong,
                                           ctypes.c_ulonglong)(vt[9])      # SetProgressValue
            self._state = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.c_int)(vt[10])  # SetProgressState
            if init(ptr) != 0:
                return False
            self.p = ptr
            return True
        except Exception as e:  # noqa
            file_log("taskbar progress not available: %r" % (e,))
            self.p = None
            return False

    def set(self, mode, frac=0.0):
        """mode: none | indeterminate | normal (green) | paused (yellow) | error (red)"""
        if not self.p:
            return
        try:
            if mode == "indeterminate":
                self._state(self.p, self.hwnd, 1)
            elif mode in ("normal", "paused", "error"):
                self._state(self.p, self.hwnd, {"normal": 2, "paused": 8, "error": 4}[mode])
                self._val(self.p, self.hwnd, int(max(0.0, min(1.0, frac)) * 1000), 1000)
            else:
                self._state(self.p, self.hwnd, 0)
            self.fail = 0
        except Exception as e:  # noqa
            self.fail += 1
            file_log("taskbar progress error %d: %r" % (self.fail, e))
            if self.fail >= 3:  # switched off; tb_tick tries to attach again later
                self.p = None

    def flash(self, count):
        """Blinks the whole taskbar button `count` times (Windows shows it only while the window is not in front)."""
        self._flash(2, count)

    def stop_flash(self):
        self._flash(0, 0)

    def _flash(self, flags, count):
        if not self.hwnd or not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            from ctypes import wintypes

            class FLASHWINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", wintypes.HWND), ("dwFlags", ctypes.c_uint),
                            ("uCount", ctypes.c_uint), ("dwTimeout", ctypes.c_uint)]

            info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), self.hwnd, flags, count, 200)
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception as e:  # noqa
            file_log("taskbar flash failed: %r" % (e,))
            self.hwnd = 0


# ------------------------------------------------------------ text / formats

class _TextExtractor(HTMLParser):
    BLOCK = ("p", "div", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote")

    def __init__(self):
        super().__init__()
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.out.append("\n")
        elif tag in self.BLOCK:
            self.out.append("\n")
            if tag == "li":
                self.out.append("- ")

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        self.out.append(data)


def html_to_text(s):
    if not s:
        return ""
    p = _TextExtractor()
    p.feed(s)
    text = "".join(p.out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_REPL = {"/": "-", "\\": "-", "|": "-", ":": " -", "*": "", "?": "", '"': "'", "<": "(", ">": ")"}
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


CHOOSER = {"fn": None}  # set by the window: asks the user which model files of a version to download
WEIGHT_EXT = (".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".bin", ".sft")


def is_weight_file(f):
    return str(f.get("name", "")).lower().endswith(WEIGHT_EXT) and str(f.get("type", "")) not in ("Training Data", "Config")


def describe_file(f):
    """One line of information about a file of a model version for the choice window."""
    md = f.get("metadata") or {}
    kb = float(f.get("sizeKB") or 0)
    gb = kb / 1024 / 1024
    size = ("%.2f GB" % gb) if gb >= 0.1 else ("%.0f MB" % (kb / 1024))
    fmt = md.get("format") or os.path.splitext(str(f.get("name", "")))[1].lstrip(".").upper()
    bits = [str(md.get("fp") or ""), str(fmt or ""), str(f.get("type") or "")]
    return {"name": str(f.get("name", "")), "size": size, "gb": gb, "primary": bool(f.get("primary")),
            "info": ", ".join(x for x in bits if x)}


def safe_name(s, maxlen=100):
    """Windows-safe folder/file name: slashes and | -> dash, : -> ' -', * and ? removed."""
    s = str(s)
    for a, b in _REPL.items():
        s = s.replace(a, b)
    s = re.sub(r"[\x00-\x1f]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    if s.split(".")[0].upper() in _RESERVED:
        s = "_" + s
    return s[:maxlen].rstrip(" .") or "unnamed"


TEXT_EXTS = (".txt", ".md", ".markdown", ".rst", ".text", ".nfo")


def dscr_name(cfg, model_name=None):
    """Description file name; only plain-text extensions are accepted, otherwise .txt is added.
    With DSCR_AS_MODEL the file is named after the model (the extension still comes from DSCR)."""
    raw = cfg.get("DSCR", "dscr.txt")
    raw = "dscr.txt" if raw is None else str(raw)
    if model_name and flag(cfg, "DSCR_AS_MODEL"):
        ext = os.path.splitext(raw)[1].lower()
        return safe_name(model_name, 100) + (ext if ext in TEXT_EXTS else ".txt")
    if not raw.strip():
        return ""  # empty name = no description file
    name = safe_name(raw, 100)
    if os.path.splitext(name)[1].lower() not in TEXT_EXTS:
        name += ".txt"
    return name


def is_md(name):
    return name.lower().endswith((".md", ".markdown"))


def fmt_kv(k, v):
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    v = str(v)
    if "\n" in v:
        return "%s:\n%s" % (k, v)
    return "%s: %s" % (k, v)


def format_meta(meta, include_comfy=False):
    if not meta:
        return "(no generation metadata)"
    lines, used = [], set()
    for k in KNOWN_META:
        if k in meta and meta[k] not in (None, ""):
            lines.append(fmt_kv(k, meta[k]))
            used.add(k)
    for k, v in meta.items():
        if k in used or v in (None, ""):
            continue
        if k in ("comfy", "workflow"):  # the big workflow is saved as a separate .json instead
            continue
        lines.append(fmt_kv(k, v))
    return "\n".join(lines)


def meta_block(title, n, meta, include_comfy, md, extra=None):
    """Description-file block for one example/image."""
    body = format_meta(meta, include_comfy)
    extra = extra or []
    if md:
        out = ["## %s %02d" % (title, n), ""] + ["- %s" % x for x in extra] + ([""] if extra else []) + ["```", body, "```"]
    else:
        out = ["=== %s %02d ===" % (title.upper(), n)] + extra + [body]
    return "\n".join(out)


def image_id_from_item(item):
    if item.get("id"):
        return str(item["id"])
    m = re.search(r"/(\d+)\.(?:jpe?g|png|webp|gif|mp4|webm)$", urllib.parse.urlparse(item.get("url", "")).path)
    return m.group(1) if m else None


def last_segment(url):
    return urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])


def with_name(url, name):
    """Put the original file name into the last segment of the image URL."""
    if not url or not name:
        return url
    pu = urllib.parse.urlparse(url)
    parts = pu.path.split("/")
    parts[-1] = urllib.parse.quote(name)
    return pu._replace(path="/".join(parts)).geturl()


def save_workflow(meta, image_path, cfg, log):
    """Experimental: save the ComfyUI workflow from the metadata as <image name>.json."""
    if not flag(cfg, "COMFY") or not isinstance(meta, dict) or not meta.get("comfy"):
        return
    target = os.path.splitext(image_path)[0] + ".json"
    if os.path.exists(target):
        return
    try:
        comfy = meta["comfy"]
        if isinstance(comfy, str):
            comfy = json.loads(comfy)
        data, kind = None, "workflow"
        if isinstance(comfy, dict):
            wf = comfy.get("workflow")
            if isinstance(wf, str):
                wf = json.loads(wf)
            if isinstance(wf, dict) and wf.get("nodes"):
                data = wf
            else:
                pr = comfy.get("prompt")
                if isinstance(pr, str):
                    pr = json.loads(pr)
                data, kind = pr, "API prompt"
        if not isinstance(data, dict) or not data:
            log("  no ComfyUI workflow data in the metadata")
            return
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        log("  ComfyUI %s saved: %s" % (kind, os.path.basename(target)))
    except Exception as e:  # noqa
        log("  could not save the workflow: %s" % e)
        file_log("workflow error: %r" % (e,))


def python_for_pip():
    """The interpreter that runs this script (python.exe instead of pythonw.exe), for pip."""
    exe = sys.executable or "python"
    if exe.lower().endswith("pythonw.exe"):
        cand = exe[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(cand):
            exe = cand
    return exe


def convert_webp(path, cfg, log):
    """Optional WebP -> JPG conversion (needs the Pillow library). Returns the final path."""
    if not flag(cfg, "WEBP2JPG") or not path.lower().endswith(".webp"):
        return path
    try:
        from PIL import Image
    except ImportError:
        if not STATE["pillow_warned"]:
            STATE["pillow_warned"] = True
            log("  WebP conversion needs the Pillow library. Tick the WebP box again to install it, or run once:  "
                '"%s" -m pip install pillow  (WebP files are kept as they are for now)' % python_for_pip())
        return path
    try:
        out = os.path.splitext(path)[0] + ".jpg"
        with Image.open(path) as im:
            if getattr(im, "is_animated", False):
                log("  animated WebP kept as is: %s" % os.path.basename(path))
                return path
            exif = im.info.get("exif")
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, (255, 255, 255))
                rgb.paste(rgba, mask=rgba.split()[3])
            else:
                rgb = im.convert("RGB")
            kw = {"quality": 95, "subsampling": 0, "optimize": True}
            if exif:
                kw["exif"] = exif
            rgb.save(out, "JPEG", **kw)
        os.remove(path)
        log("  converted WebP -> JPG: %s" % os.path.basename(out))
        return out
    except Exception as e:  # noqa
        log("  WebP conversion failed (%s), file kept as WebP" % e)
        file_log("webp convert error: %r" % (e,))
        return path


def resolve_subfolder(root_path, value):
    """Folder for single images: empty = root, a full path is used as is, a name/nested path goes inside root."""
    value = (value or "").strip()
    if not value:
        return os.path.normpath(root_path)
    if os.path.isabs(value):
        return os.path.normpath(value)
    parts = [safe_name(x) for x in re.split(r"[\\/]+", value) if x.strip()]
    return os.path.join(root_path, *parts) if parts else os.path.normpath(root_path)


def api_image_info(host, image_id, token):
    """Public API lookup of one image (gives the file address, usually no generation metadata).
    Tries a few parameter variants because mature images may be hidden from the plain query."""
    for extra in ("", "&nsfw=X", "&nsfw=X&browsingLevel=31&period=AllTime&sort=Newest"):
        try:
            data = get_json("%s://%s/api/v1/images?imageId=%s%s" % (SCHEME, host, image_id, extra), token)
        except urllib.error.HTTPError as e:
            file_log("api image %s variant %r -> HTTP %s" % (image_id, extra, e.code))
            continue
        for it in data.get("items") or []:
            if str(it.get("id")) == str(image_id):
                file_log("api image %s found with variant %r" % (image_id, extra))
                return it
        file_log("api image %s variant %r -> not listed" % (image_id, extra))
    return None


def numbered_files(folder, n):
    pat = re.compile(r"^%s[._]" % ("%02d" % n))
    try:
        return [fn for fn in os.listdir(folder) if pat.match(fn) and not fn.endswith(".part")]
    except OSError:
        return []


def next_index(folder):
    top = 0
    for fn in os.listdir(folder):
        m = re.match(r"^(\d+)[._]", fn)
        if m and not fn.endswith(".part"):
            top = max(top, int(m.group(1)))
    return top + 1


# ---------------------------------------------- metadata from the image page

def find_meta(o):
    if isinstance(o, dict):
        m = o.get("meta")
        if isinstance(m, dict) and ("prompt" in m or "seed" in m or "steps" in m):
            return m
        for v in o.values():
            r = find_meta(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find_meta(v)
            if r:
                return r
    return None


def find_image_rec(o, image_id):
    if isinstance(o, dict):
        if str(o.get("id")) == str(image_id) and isinstance(o.get("url"), str):
            return o
        for v in o.values():
            r = find_image_rec(v, image_id)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find_image_rec(v, image_id)
            if r:
                return r
    return None


def find_name(o, image_id):
    """Original file name: a dict with the image id and a string field "name"."""
    if isinstance(o, dict):
        if str(o.get("id")) == str(image_id) and isinstance(o.get("name"), str) and o["name"].strip():
            return o["name"].strip()
        for v in o.values():
            r = find_name(v, image_id)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find_name(v, image_id)
            if r:
                return r
    return None


def build_image_urls(raw, rec, image_id):
    """Candidate CDN addresses of the original file, best first. The CDN ignores the last path
    segment, so the addresses are built from the account key and the image uuid."""
    cdn = r"image\.civitai\.com/([A-Za-z0-9_\-]+)/([0-9a-fA-F\-]{36})"
    text = raw.replace("\\/", "/")
    key = uuid = None
    if rec and isinstance(rec.get("url"), str):
        m = re.search(cdn, rec["url"])
        if m:
            key, uuid = m.group(1), m.group(2)
        elif re.fullmatch(r"[0-9a-fA-F\-]{36}", rec["url"]):
            uuid = rec["url"]
    og = (re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', raw)
          or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', raw))
    og_url = html.unescape(og.group(1)) if og else None
    og_cdn = None
    if og_url:
        m = re.search(cdn, og_url)
        if m and urllib.parse.urlparse(og_url).netloc == "image.civitai.com":
            og_cdn = (m.group(1), m.group(2))
            if not uuid:
                key, uuid = og_cdn
    if uuid and not key:
        pairs = re.findall(cdn, text)
        key = next((k for k, u in pairs if u == uuid), None) or (pairs[0][0] if pairs else None)
    cands = []
    if key and uuid:
        ext = ".mp4" if rec and rec.get("type") == "video" else ".jpeg"
        base = "https://image.civitai.com/%s/%s/original=true/" % (key, uuid)
        cands += [base + uuid + ext, base + str(image_id) + ext]
    if og_url and og_cdn:  # last resort: the og:image address turned into the original
        pu = urllib.parse.urlparse(og_url)
        parts = ["original=true" if re.search(r"(width|anim|quality|optimized)=", x) else x
                 for x in pu.path.split("/")]
        cands.append(pu._replace(path="/".join(parts), query="").geturl())
    return list(dict.fromkeys(cands))


def find_resources(o):
    """Models/LoRAs used for the image, as listed on the page ('resources' of the generation data)."""
    if isinstance(o, dict):
        res = o.get("resources")
        if o.get("type") in ("image", "video") and isinstance(res, list) and res:
            out = []
            for r in res:
                if isinstance(r, dict) and r.get("modelName"):
                    out.append("%s (%s) %s" % (r.get("modelName"), r.get("modelType", "?"), r.get("versionName", "")))
            if out:
                return "; ".join(x.strip() for x in out)
        for v in o.values():
            r = find_resources(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find_resources(v)
            if r:
                return r
    return None


def scrape_image_page(host, image_id, token, debug_dir=None):
    """Returns (meta | None, image_url | None, original_name | None, other_candidate_urls) from /images/ID."""
    raw = fetch_page("%s://%s/images/%s" % (SCHEME, host, image_id), token)
    data = None
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
        except ValueError:
            data = None
    meta = find_meta(data) if data is not None else None
    rec = find_image_rec(data, image_id) if data is not None else None
    name = find_name(data, image_id) if data is not None else None
    if meta is None:  # fallback: pull "meta":{...} straight out of the page text
        dec = json.JSONDecoder()
        for mm in re.finditer(r'"meta":\{', raw):
            try:
                obj, _ = dec.raw_decode(raw[mm.end() - 1:])
            except ValueError:
                continue
            if isinstance(obj, dict) and ("prompt" in obj or "seed" in obj):
                meta = obj
                break
    res = find_resources(data) if data is not None else None
    if res:
        meta = dict(meta) if meta else {}
        meta.setdefault("Resources", res)
    cands = build_image_urls(raw, rec, image_id)
    img_url = cands[0] if cands else None
    file_log("page %s: meta=%s name=%s candidates=%s og=%s" % (
        image_id, "yes" if meta else "no", name, cands,
        (re.search(r'og:image["\'][^>]*content=["\']([^"\']{0,200})', raw) or [None, None])[1]))
    if img_url is None:  # keep the page for diagnosis (missing metadata is normal: many images have none)
        try:
            ddir = os.path.join(SCRIPT_DIR, "debug")
            os.makedirs(ddir, exist_ok=True)
            for old in sorted(os.listdir(ddir))[:-19]:  # keep at most 20 files
                os.remove(os.path.join(ddir, old))
            with open(os.path.join(ddir, "page_%s.html" % image_id), "w", encoding="utf-8") as f:
                f.write(raw)
            file_log("page %s saved for diagnosis: debug/page_%s.html" % (image_id, image_id))
        except OSError:
            pass
    return meta, img_url, name, cands[1:]


# ------------------------------------------------------------- main scenarios

def flag(cfg, key):
    return str(cfg.get(key, DEFAULTS.get(key, ""))).strip().lower() in ("1", "true", "yes", "y")


def decide_existing(cfg, ask, what):
    """True = download again, False = skip."""
    mode = str(cfg.get("EXISTING", "ask")).strip().lower()
    if mode in ("overwrite", "over", "redo"):
        return True
    if mode in ("skip",):
        return False
    return bool(ask("Already downloaded:\n%s\n\nDownload again?" % what))


def download_first_ok(urls, dest, log, stop, token=None, name_ext=""):
    last = None
    for u in urls:
        try:
            return download_file(u, dest, log, stop, token, auto_ext=True, name_ext=name_ext)
        except Stopped:
            raise
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (400, 403, 404) and u is not urls[-1]:
                log("    HTTP %s for ...%s - trying the next address" % (e.code, u[-60:]))
                file_log("address failed HTTP %s: %s" % (e.code, u))
                continue
            raise
    raise last


def grab_example(n, item, host, token, folder, cfg, log, stop, overwrite):
    """Download one example. Returns (meta | None, saved file name | None)."""
    iid = image_id_from_item(item)
    api_url = item.get("url")
    meta = item.get("meta") if isinstance(item.get("meta"), dict) and item.get("meta") else None
    existing = numbered_files(folder, n)
    need_download = overwrite or not existing
    if need_download and STATE.get("net_down"):  # the network was found to be down a moment ago: do not wait for retries
        log("  [%02d] skipped (no network connection)" % n)
        return meta, None
    page_meta = page_img = name = None
    alts = []
    if iid and not STATE["page_blocked"] and ((need_download and flag(cfg, "ORIGINAL")) or not meta):
        try:
            page_meta, page_img, name, alts = scrape_image_page(host, iid, token, folder)
            if not meta and page_meta:
                meta = page_meta
                log("  [%02d] metadata taken from the image page" % n)
        except urllib.error.HTTPError as e:
            file_log("scrape error %s: %r" % (iid, e))
            if e.code in (401, 403):
                STATE["blocked"] += 1
                if STATE["blocked"] >= 2:
                    STATE["page_blocked"] = True
                    log("  Image pages answer HTTP %s to scripts: using API data only for the rest of this run" % e.code)
                else:
                    log("  [%02d] image page not available (HTTP %s), using API data" % (n, e.code))
            else:
                log("  [%02d] could not read the image page (%s) - continuing with the API data" % (n, e))
        except Exception as e:  # noqa
            log("  [%02d] could not read the image page (%s) - continuing with the API data" % (n, e))
            file_log("scrape error %s: %r" % (iid, e))
    if existing and not overwrite:
        log("  [%02d] already exists: %s" % (n, existing[0]))
        save_workflow(meta, os.path.join(folder, existing[0]), cfg, log)
        return meta, existing[0]
    for fn in existing:
        try:
            os.remove(os.path.join(folder, fn))
        except OSError:
            pass
    urls = [u for u in [api_url, page_img] + list(alts) if u]
    if flag(cfg, "ORIGINAL") and name:  # the CDN normally ignores the file name; kept as a last resort
        urls += [with_name(u, name) for u in list(urls)]
    urls = list(dict.fromkeys(urls))
    if not urls:
        log("  [%02d] no file address" % n)
        return meta, None
    src_name = name if (name and flag(cfg, "ORIGINAL")) else last_segment(urls[-1] if not name else urls[0])
    stem, name_ext = os.path.splitext(src_name)
    base = os.path.join(folder, "%02d_%s" % (n, safe_name(stem, 80)))
    try:
        final = download_first_ok(urls, base, log, stop, name_ext=name_ext)
    except Stopped:
        raise
    except Exception as e:  # noqa
        log("  [%02d] DOWNLOAD ERROR: %s" % (n, e))
        file_log("example error: %r" % (e,))
        if isinstance(e, (urllib.error.URLError, OSError, http.client.HTTPException)) and not isinstance(e, urllib.error.HTTPError):
            STATE["net_fail"] += 1
            if STATE["net_fail"] >= 2 and not STATE["net_down"]:
                STATE["net_down"] = True
                log("  No network connection: the remaining examples of this model are skipped (they stay marked for attention)")
        return meta, None
    STATE["net_fail"] = 0
    final = convert_webp(final, cfg, log)
    save_workflow(meta, final, cfg, log)
    log("  [%02d] saved: %s" % (n, os.path.basename(final)))
    return meta, os.path.basename(final)


def api_gallery_ids(host, vid, token, want, skip, log, stop):
    """Image ids of the gallery (images uploaded by users) of a model version, via the public API."""
    ids, cursor, extra = [], None, ""
    base = "%s://%s/api/v1/images?modelVersionId=%s&limit=100&sort=Most%%20Reactions&period=AllTime" % (SCHEME, host, vid)
    while True:
        if stop.is_set():
            raise Stopped()
        url = base + extra + (("&cursor=" + urllib.parse.quote(str(cursor))) if cursor else "")
        try:
            data = get_json(url, token)
        except urllib.error.HTTPError as e:
            log("  gallery list: HTTP %s" % e.code)
            break
        items = data.get("items") or []
        if not items and cursor is None and not extra:
            extra = "&nsfw=X"  # mature images may need the explicit flag
            continue
        for it in items:
            iid = it.get("id")
            if iid and str(iid) not in skip and iid not in ids:
                ids.append(iid)
        if want is not None and len(ids) >= want:
            break
        md = data.get("metadata") or {}
        cursor = md.get("nextCursor")
        if not cursor and md.get("nextPage"):
            m = re.search(r"[?&]cursor=([^&]+)", str(md["nextPage"]))
            cursor = urllib.parse.unquote(m.group(1)) if m else None
        if not cursor or len(ids) >= 5000:
            break
    return ids if want is None else ids[:want]


def run_gallery(host, vid, token, want_raw, skip_ids, cfg, log, stop, ask):
    if not (BRIDGE.connected() and not STATE["bridge_off"]):
        log("  Gallery skipped: the browser bridge is not connected (generation metadata needs it)")
        return
    want = None if want_raw in ("all", "*") else int(want_raw)
    ids = api_gallery_ids(host, vid, token, want, set(str(x) for x in skip_ids), log, stop)
    log("  Gallery images to download: %d" % len(ids))
    gcfg = dict(cfg)
    if str(gcfg.get("EXISTING", "ask")).strip().lower() == "ask":
        gcfg["EXISTING"] = "skip"  # no dialog for every already known gallery image
    glog = lambda m: None if m.startswith("  Folder:") else log(m)  # noqa
    ok = bad = 0
    for i, iid in enumerate(ids, 1):
        if stop.is_set():
            raise Stopped()
        u = "%s://%s/images/%s" % (SCHEME, host, iid)
        log("  [gallery %d/%d] %s" % (i, len(ids), u))
        try:
            res = process_image(u, gcfg, glog, stop, ask)
            if res in ("ok", "skipped"):
                ok += 1
            else:
                bad += 1
        except Stopped:
            raise
        except Exception as e:  # noqa
            bad += 1
            log("    ERROR: %s: %s" % (type(e).__name__, e))
            file_log(traceback.format_exc())
        time.sleep(0.3)
    log("  Gallery finished: %d done, %d failed" % (ok, bad))
    return bad


def process_model(url, cfg, log, stop, ask, next_is_image=False):
    p = urllib.parse.urlparse(url)
    host = p.netloc
    token = cfg["TOKEN"]
    include_comfy = flag(cfg, "COMFY")
    STATE["net_fail"], STATE["net_down"] = 0, False
    pics_raw = str(cfg.get("PICS", "4")).strip().lower()
    pics = None if pics_raw in ("all", "*") else int(pics_raw or 0)
    mm = re.search(r"/models/(\d+)", p.path)
    if not mm:
        raise ValueError("model id not found in the URL")
    model_id = mm.group(1)
    vid = urllib.parse.parse_qs(p.query).get("modelVersionId", [None])[0]

    model = get_json("%s://%s/api/v1/models/%s" % (SCHEME, host, model_id), token)
    if not vid:
        vid = model["modelVersions"][0]["id"]
    ver = get_json("%s://%s/api/v1/model-versions/%s" % (SCHEME, host, vid), token)

    name = model.get("name") or (ver.get("model") or {}).get("name") or ("model_%s" % model_id)
    folder = os.path.join(cfg["PATH"], safe_name(name))
    log("  Model: %s  (version: %s)" % (name, ver.get("name")))
    log("  Folder: %s" % folder)
    STATE["model_folder"] = folder  # images that follow in the list go here
    STATE["model_name"] = name

    # --- model file(s)
    do_model = flag(cfg, "MODEL")
    files = ver.get("files") or []
    primary = next((f for f in files if f.get("primary")), None)
    if not primary:
        primary = next((f for f in files if str(f.get("name", "")).lower().endswith(".safetensors")), None)
    if not primary and files:
        primary = files[0]
    if not primary and do_model:
        raise ValueError("this version has no files to download")
    picked = [primary] if primary else []
    skip_note = "Model file skipped (Model file is unchecked)"
    weights = [f for f in files if is_weight_file(f)]
    if do_model and len(weights) >= 2:
        if CHOOSER["fn"]:
            ans = CHOOSER["fn"]("%s  -  %s" % (name, ver.get("name")), [describe_file(f) for f in weights],
                                [i for i, f in enumerate(weights) if f is primary] or [0])
            if stop.is_set():
                raise Stopped()
            if not ans:  # Stop in the window: the whole run ends, the link stays in the list
                log("  Stopped at the choice of the model files; the link stays in the list")
                stop.set()
                raise Stopped()
            picked = [weights[i] for i in ans]
        else:
            log("  This version has %d model files; downloading the main one (%s)" % (len(weights), (primary or {}).get("name", "")))
    jobs = []
    for f in picked:
        fn = cfg.get("PREFIX", "") + safe_name(f.get("name") or ("%s.safetensors" % vid), 200)
        jobs.append({"name": fn, "dest": os.path.join(folder, fn), "url": f.get("downloadUrl") or ver.get("downloadUrl"),
                     "info": describe_file(f)})
    if do_model and jobs:
        many = len(weights) >= 2
        fname_shown = ", ".join(("%s (%s, %s)" % (j["name"], j["info"]["info"], j["info"]["size"])) if many else j["name"] for j in jobs)
    else:
        fname_shown = "(not downloaded)"

    overwrite = False
    have_any = do_model and any(os.path.exists(j["dest"]) and os.path.getsize(j["dest"]) > 0 for j in jobs)
    if have_any:
        rec = history_find("model:%s" % vid)
        when = (" (downloaded %s)" % rec["time"]) if rec else ""
        if next_is_image and str(cfg.get("EXISTING", "ask")).strip().lower() == "ask":
            log("  Model already downloaded%s - continuing in its folder with the images below" % when)
            return "skipped"
        if not decide_existing(cfg, ask, "%s%s\n%s" % (name, when, folder)):
            log("  SKIPPED: model already downloaded%s" % when)
            return "skipped"
        overwrite = True
    elif not do_model and str(cfg.get("EXISTING", "ask")).strip().lower() == "overwrite":
        overwrite = True
    os.makedirs(folder, exist_ok=True)

    if not do_model:
        log("  " + skip_note)
    else:
        for j in jobs:
            if os.path.exists(j["dest"]) and os.path.getsize(j["dest"]) > 0 and not overwrite:
                log("  File already exists: %s" % j["name"])
                continue
            log("  Downloading model: %s  (%s)" % (j["name"], j["info"]["size"]) if len(weights) >= 2 else "  Downloading model: %s" % j["name"])
            download_file(j["url"], j["dest"], log, stop, token)
            log("  Done: %s" % j["name"])

    # --- examples (images and videos)
    items = ver.get("images") or []
    if not flag(cfg, "VIDEO"):
        items = [i for i in items if i.get("type", "image") == "image"]
    if pics is not None:
        items = items[:pics]
    log("  Examples to download: %d" % len(items))
    entries = []
    bad = 0
    for n, item in enumerate(items, 1):
        if stop.is_set():
            raise Stopped()
        meta, saved = grab_example(n, item, host, token, folder, cfg, log, stop, overwrite)
        if not saved:
            bad += 1
        if meta:  # no description entry for items without metadata (e.g. most videos)
            entries.append((n, meta))
        time.sleep(0.4)

    # --- description file (rewritten completely)
    dname = dscr_name(cfg, name)
    md = is_md(dname)
    tw = ver.get("trainedWords") or []
    tags = model.get("tags") or []
    tags_txt = ", ".join(str(t) if not isinstance(t, dict) else t.get("name", "") for t in tags)
    mdesc = html_to_text(model.get("description")) or "(empty)"
    vdesc = html_to_text(ver.get("description"))
    if md:
        out = ["# %s" % name, "", "- **Version:** %s" % ver.get("name", ""),
               "- **Type:** %s | **Base model:** %s" % (model.get("type", ""), ver.get("baseModel", "")),
               "- **Page:** %s" % url, "- **File:** %s" % fname_shown]
        if tw:
            out.append("- **Trigger words:** %s" % ", ".join(tw))
        if tags_txt:
            out.append("- **Tags:** %s" % tags_txt)
        out += ["", "## Model description", "", mdesc]
        if vdesc:
            out += ["", "## Version description", "", vdesc]
    else:
        out = ["MODEL: %s" % name, "Version: %s" % ver.get("name", ""),
               "Type: %s | Base model: %s" % (model.get("type", ""), ver.get("baseModel", "")),
               "Page: %s" % url, "File: %s" % fname_shown]
        if tw:
            out.append("Trigger words: %s" % ", ".join(tw))
        if tags_txt:
            out.append("Tags: %s" % tags_txt)
        out += ["", "=== MODEL DESCRIPTION ===", mdesc]
        if vdesc:
            out += ["", "=== VERSION DESCRIPTION ===", vdesc]
    for n, meta in entries:
        out += ["", meta_block("Example", n, meta, False, md)]
    if dname:
        dpath = os.path.join(folder, dname)
        keep = ""
        try:  # keep blocks of single images that were appended to the old description file earlier
            with open(dpath, encoding="utf-8") as f:
                old = f.read()
            m = re.search(r"^(?:=== (?:IMAGE )?\d+ ===|## Image \d+)\s*$", old, re.M)
            if m:
                keep = "\n" + old[m.start():].rstrip("\n") + "\n"
        except OSError:
            pass
        with open(dpath, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n" + keep)
        log("  %s written (examples described: %d%s)" % (dname, len(entries), ", earlier image blocks kept" if keep else ""))
    else:
        log("  Description file skipped (its name is empty)")
    history_add("model:%s" % vid, url, folder, "ok")
    gal_raw = str(cfg.get("GALLERY", "0")).strip().lower()
    gal_bad = 0
    if gal_raw not in ("", "0"):
        gal_bad = run_gallery(host, vid, token, gal_raw, [image_id_from_item(i) for i in items], cfg, log, stop, ask) or 0
    if bad or gal_bad:
        STATE["partial_note"] = "%d file(s) were not downloaded" % (bad + gal_bad)
        return "partial"
    return "ok"


def process_image(url, cfg, log, stop, ask):
    p = urllib.parse.urlparse(url)
    host = p.netloc
    token = cfg["TOKEN"]
    mm = re.search(r"/images/(\d+)", p.path)
    if not mm:
        raise ValueError("image id not found in the URL")
    iid = mm.group(1)
    if STATE["model_folder"]:  # scenario 1: images that follow a model link go to that model's folder
        folder = STATE["model_folder"]
    elif STATE["model_failed"]:
        log("  KEPT IN THE LIST: the model above was not downloaded, so the folder for this image is unknown")
        return "kept"
    elif flag(cfg, "USE_SUBFOLDER"):  # scenario 2: no model before - output folder (+ optional subfolder)
        folder = resolve_subfolder(cfg["PATH"], cfg.get("IMGFOLDER"))
    else:
        folder = os.path.normpath(cfg["PATH"])
    log("  Folder: %s" % folder)
    key = "image:%s" % iid
    rec = history_find(key, folder)
    if rec and rec.get("file") and not os.path.exists(rec["file"]):
        rec = None  # the file was deleted since: download again without asking
    if rec and not decide_existing(cfg, ask, "Image %s (downloaded %s)\n%s\n(downloading again saves it once more "
                                              "under a new number)" % (iid, rec["time"], folder)):
        log("  SKIPPED: image already downloaded %s" % rec["time"])
        return "skipped"
    os.makedirs(folder, exist_ok=True)

    meta = img_url = name = info = None
    alts = []
    if not STATE["page_blocked"]:
        try:
            meta, img_url, name, alts = scrape_image_page(host, iid, token, folder)
        except urllib.error.HTTPError as e:
            if e.code not in (401, 403):
                raise
            STATE["page_blocked"] = True
            log("  Image pages answer HTTP %s to scripts: using the public API (no generation metadata)" % e.code)
    if not img_url:
        info = api_image_info(host, iid, token)
        if not info or not info.get("url"):
            raise ValueError("image %s was not found: the page is blocked for scripts and the API does not list it "
                             "(the image may be hidden, deleted or restricted)" % iid)
        img_url = info["url"]
        if isinstance(info.get("meta"), dict) and info["meta"]:
            meta = info["meta"]
    idx = next_index(folder)
    src_name = name or last_segment(img_url)
    stem, name_ext = os.path.splitext(src_name)
    urls = list(dict.fromkeys([img_url] + list(alts) + [with_name(img_url, name)]))
    base = os.path.join(folder, "%02d_%s" % (idx, safe_name(stem, 80)))
    try:
        final = download_first_ok(urls, base, log, stop, name_ext=name_ext)
    except urllib.error.HTTPError as e:
        if info is not None or e.code not in (400, 403, 404):
            raise
        log("  The addresses taken from the page failed, asking the public API for the file address")
        info = api_image_info(host, iid, token)
        if not info or not info.get("url") or info["url"] in urls:
            raise
        final = download_first_ok([info["url"]], base, log, stop, name_ext=name_ext)
    final = convert_webp(final, cfg, log)
    save_workflow(meta, final, cfg, log)
    log("  Image saved: %s" % os.path.basename(final))
    extra = ["Page: %s" % url]
    if info:
        if info.get("username"):
            extra.append("Author: %s" % info["username"])
        if info.get("width") and info.get("height"):
            extra.append("Size: %sx%s" % (info["width"], info["height"]))
        if info.get("createdAt"):
            extra.append("Created: %s" % info["createdAt"])
    if not meta:
        if info:
            extra.append("Note: the image page is blocked for scripts, generation metadata could not be read")
        log("  WARNING: no generation metadata for this image")
    dname = dscr_name(cfg, STATE["model_name"] if STATE["model_folder"] else None)
    if dname:
        dpath = os.path.join(folder, dname)
        lead = "\n" if os.path.exists(dpath) and os.path.getsize(dpath) > 0 else ""
        with open(dpath, "a", encoding="utf-8") as f:
            f.write(lead + meta_block("Image", idx, meta, False, is_md(dname), extra) + "\n")
    history_add(key, url, folder, "ok", file=final)
    return "ok"


# ------------------------------------------------------------------ task

def read_task_file(path):
    """Returns (explicit values from the file, links). Empty values are not 'given' and are ignored."""
    explicit, urls = {}, []
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("http"):
                urls.append(line)
                continue
            m = re.match(r"^([A-Za-z_]+)\s*:\s*(.*)$", line)
            if m and m.group(2).strip().strip('"'):
                explicit[m.group(1).upper()] = m.group(2).strip().strip('"')
    if "IMGFOLDER" in explicit and "USE_SUBFOLDER" not in explicit:
        explicit["USE_SUBFOLDER"] = "1"  # giving a subfolder implies using it
    return explicit, urls


def parse_task_file(path):
    explicit, urls = read_task_file(path)
    return {**DEFAULTS, **explicit}, urls


SAMPLE_TASK = """# Civitai Grabber task file
# Lines starting with # are ignored. Keys with an empty value are ignored too:
# whatever you leave empty here is taken from the program window.
# A value written here replaces the window value (the program warns when they differ).

# Civitai API key (account settings -> API keys)
TOKEN:
# Output folder; every model gets its own subfolder there
PATH:
# Text put in front of every model file name, e.g. k2-pers-
PREFIX:
# 1 = download the model file (0 = skip it)
MODEL:
# Example images/videos per model: a number, all, or 0 for none
PICS:
# Gallery images (uploaded by users) per model: a number, all, or 0 for none. Needs the browser bridge.
GALLERY:
# 1 = download video examples too, 0 = skip them
VIDEO:
# 1 = try to take original file names from the image page
ORIGINAL:
# What to do with already downloaded items: ask / skip / overwrite
EXISTING:
# Description file name (.txt or .md)
DSCR:
# 1 = name the description file after the model (the extension is taken from DSCR)
DSCR_AS_MODEL:
# Single image links with no model link before them: 1 = use IMGFOLDER (a name, a/b/c, or a full path)
USE_SUBFOLDER:
IMGFOLDER:
# 1 = convert WebP to JPG (needs: pip install pillow)
WEBP2JPG:
# 1 = save the ComfyUI workflow as a .json next to the image
COMFY:

# Links, one per line (model pages and/or single image pages). Remove the # in front:
# https://civitai.red/models/1800132/kayla?modelVersionId=3282255
# https://civitai.red/images/141345317
"""

HELP_TEXT = """Civitai Grabber v%s

WHAT IT DOES
Downloads LoRA/model files from Civitai model links together with their example images and videos, and writes the generation metadata (prompt, sampler, seed ...) into a description file next to the model. Links to single images work too.

QUICK START
1. Paste your Civitai API key (account settings -> API keys) into "API token" and press Lock to protect it. Choose an "Output folder" (a category folder: one kind of models per folder).
2. Put links into the list, one per line: model links (.../models/ID?modelVersionId=ID) and/or image links (.../images/ID).
3. Press START. Finished links disappear from the list, failed ones stay.

WHERE THINGS GO
- Every model gets its own folder inside the Output folder, named after the model (characters that Windows does not allow are replaced).
- Image links that follow a model link in the list go into that model's folder, continue the numbering and add their metadata to the same description file. A new model link starts a new folder. The model folder is remembered only within one run.
- Image links with no model link before them go to the Output folder, or into the subfolder when "Image subfolder" is ticked (a name, a nested path a/b/c, or a full path).
- A model link is removed from the list only after the image links below it are finished, so after a Stop or an error the rest of the list still knows its folder.

OPTIONS
Model file: tick to download the model file; the prefix box is used only then. Examples: how many example images/videos of the model version to download (number, all, or 0/empty for none; videos count). From gallery: how many images that other users uploaded to the model's gallery to download (number or all; needs the browser bridge, so the box is greyed out without it). 
If already downloaded: ask, skip, or download again (images already saved to a different folder are never treated as downloaded).
Add prefix: text put before the model file name. Description file: name of the description file (.txt or .md, no extension = .txt; empty = no description file is written). "Name as model" names that file after the model instead (the extension still comes from the box).
Original file names: try to read the original name from the image page. WebP to JPG needs the Pillow library (py -m pip install pillow).
ComfyUI workflow as .json: experimental, saves the workflow found in the metadata next to the image.

TASK FILES
The buttons "Create sample txt" and "Load from txt" are hidden for now (set SHOW_TXT_BUTTONS = True at the top of the script to bring them back); a task file can also be given on the command line. A task file holds TOKEN, PATH, PREFIX, PICS ... and the links. Empty keys are ignored, so a file can contain only links. If a value in the file differs from the window, you are asked which one to use.

BROWSER BRIDGE (optional)
Image pages are closed to scripts, so generation metadata of gallery images is not available directly. The browser extension "Civitai Grabber Bridge" fetches those pages with your logged-in browser and hands them to this program through a local port on 127.0.0.1. Keep Firefox open and logged in (the Civitai tabs themselves need not be open, loaded or active); the status shows "connected" when the extension is working. The extension's toolbar button and its right-click menu can also add the current page, a link, or all open Civitai tabs to the link list. Untick "Browser bridge" to turn the local port off.

LAUNCH FROM THE BROWSER (Windows, optional)
When the program is closed, the extension window offers a "Start Civitai Grabber" button. For this the program needs your permission: it adds a small entry for each supported browser (Firefox, Chrome, Edge, Brave) under HKEY_CURRENT_USER\\Software\\<browser>\\NativeMessagingHosts in the registry and three small files next to the script (civitai_grabber_host.json, civitai_grabber_host_chromium.json, civitai_grabber_launch.bat). The entries can start nothing but this script. The program asks before doing so and keeps them up to date when you move or update the script; the buttons at the bottom of this window allow or remove them (removal also deletes the files). The launch needs .pyw files to open with Python on double click. Other Chromium-based browsers (Opera, Vivaldi, Yandex) are not covered yet - there the program has to be started by hand.\nMODELS WITH SEVERAL FILES: when a model version offers more than one model file (other precision or format - checkpoints, LoRA, ...), a window lists the files with type and size; tick what to download. Stop ends the whole run and leaves the link in the list.\nCLOSING BROWSER TABS: in the extension window you can choose to close the browser tabs of links that were added from them and are finished (Never / Always / Ask).\nTASKBAR: the icon blinks when a link has arrived; a full green button = links are waiting; moving bar = connecting; growing green bar = downloading; red = there were errors; full green button with a check mark = finished. The check and the red mark go away when you return to the window. The switches at the top of the script (TASKBAR_SIGNALS, TASKBAR_FLASH, TASKBAR_WAITING) change or switch this off.

FILES NEXT TO THE SCRIPT
civitai_grabber.log (what happened), civitai_grabber_history.jsonl (downloaded items), civitai_grabber_settings.json (window settings and recent folders; it also contains your API token in plain text - do not share it).

SHORTCUTS
Ctrl+C / V / X / A / Z / Y work in all fields on any keyboard layout; right-click opens a context menu.
"""


def link_key(u):
    m = re.search(r"/models/(\d+)", u)
    if m:
        v = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("modelVersionId", ["latest"])[0]
        return "m:%s:%s" % (m.group(1), v)
    m = re.search(r"/images/(\d+)", u)
    return "i:%s" % m.group(1) if m else u


def run_task(cfg, urls, log, stop, ask, done=None):
    """Processes the links in order. done(url) is called for every link that is finished, so the
    caller can remove it from its list. A model link is reported as finished only after all
    single-image links directly below it are finished too; if the run is stopped or an image fails,
    the model link stays in the list and re-establishes the folder on the next run."""
    done = done or (lambda u: None)
    log("Civitai Grabber v%s" % VERSION)
    log("Log file: %s" % LOGFILE)
    STATE.update({"log": log, "bridge_failures": 0, "bridge_off": False, "stop": stop, "blocked": 0, "page_blocked": False, "model_folder": None,
                  "model_name": None, "model_failed": False, "pillow_warned": False, "net_fail": 0, "net_down": False})
    cfg = {**DEFAULTS, **cfg}
    if cfg["TOKEN"]:
        SECRETS.add(cfg["TOKEN"])
    if not cfg["PATH"]:
        log("No output folder given (PATH).")
        return
    if not cfg["TOKEN"]:
        log("WARNING: no TOKEN given, some data/files may be unavailable.")
    try:
        os.makedirs(cfg["PATH"], exist_ok=True)
    except OSError as e:
        log("Cannot create the output folder: %s" % e)
        return
    pics = str(cfg.get("PICS", "")).strip().lower()
    gal = str(cfg.get("GALLERY", "")).strip().lower()
    for label, val in (("Examples", pics), ("From gallery", gal)):
        if val and val not in ("all", "*") and not val.isdigit():
            log("%s must be a number, all, or empty (now: %r)." % (label, val))
            return
    log("Links in the task: %d" % len(urls))
    TB.update({"phase": "connecting", "failed": 0, "total": len(urls), "idx": 0, "cur": 0.0})
    seen = {}  # link key -> finished OK?
    group = {"url": None, "ok": True}

    def close_group():
        if group["url"] and group["ok"]:
            done(group["url"])
        group["url"], group["ok"] = None, True

    for i, u in enumerate(urls, 1):
        if stop.is_set():
            log("Stopped.")
            return
        log("[%d/%d] %s" % (i, len(urls), u))
        TB["idx"], TB["cur"] = i - 1, 0.0
        k = link_key(u)
        if k in seen:
            log("  SKIPPED: this link already appeared earlier in the list")
            if seen[k]:
                done(u)
            continue
        is_model = "/models/" in u
        if is_model:
            close_group()
            STATE["model_folder"], STATE["model_failed"], STATE["model_name"] = None, False, None
        ok = False
        res = None
        try:
            if is_model:
                nxt = urls[i] if i < len(urls) else ""
                res = process_model(u, cfg, log, stop, ask, next_is_image="/images/" in nxt)
            elif "/images/" in u:
                res = process_image(u, cfg, log, stop, ask)
            else:
                log("  Unrecognised link (expected /models/ or /images/)")
                res = "kept"
            ok = res in ("ok", "skipped", "partial")
            if res == "partial":
                note = STATE.pop("partial_note", "some files were not downloaded")
                ATTENTION[u] = note
                TB["failed"] += 1
                log("  ATTENTION: %s - the browser page of this link stays open and is marked in the extension window" % note)
        except Stopped:
            log("Stopped.")
            return
        except urllib.error.HTTPError as e:
            hint = ""
            if e.code in (401, 403):
                hint = " - the model may be paid (buzz) or in early access, or the token is not accepted"
            elif e.code == 404:
                hint = " - page/model not found or hidden"
            log("  HTTP ERROR %s: %s%s  (...%s)" % (e.code, e.reason, hint, str(e.url)[-70:]))
            file_log("HTTPError %s %s" % (e.code, e.url))
            history_add(k, u, cfg["PATH"], "error HTTP %s" % e.code)
        except Exception as e:  # noqa
            log("  ERROR: %s: %s" % (type(e).__name__, e))
            file_log(traceback.format_exc())
            history_add(k, u, cfg["PATH"], "error %s" % type(e).__name__)
        seen[k] = ok
        if not ok:
            TB["failed"] += 1
        if is_model:
            if not ok:
                STATE["model_failed"], STATE["model_folder"] = True, None
            group["url"], group["ok"] = u, ok
        elif ok:
            done(u)
        elif group["url"]:
            group["ok"] = False
        time.sleep(0.7)
    close_group()
    log("Done.")


# --------------------------------------------------------------------- GUI

class UndoEntry:
    """Ctrl+Z / Ctrl+Y for a ttk.Entry or ttk.Combobox (they have no undo of their own)."""

    def __init__(self, widget, var):
        self.widget, self.var = widget, var
        self.stack, self.pos, self.last, self.busy = [var.get()], 0, 0.0, False
        var.trace_add("write", self._changed)
        widget.bind("<<Undo>>", self.undo, "+")
        widget.bind("<<Redo>>", self.redo, "+")

    def _changed(self, *_):
        if self.busy:
            return
        val = self.var.get()
        if val == self.stack[self.pos]:
            return
        del self.stack[self.pos + 1:]
        now = time.time()
        if now - self.last < 0.8 and self.pos > 0:  # typing burst = one undo step
            self.stack[self.pos] = val
        else:
            self.stack.append(val)
            self.pos += 1
        self.last = now

    def _apply(self):
        self.busy = True
        self.var.set(self.stack[self.pos])
        self.busy = False
        try:
            self.widget.icursor("end")
        except Exception:  # noqa
            pass

    def undo(self, _e=None):
        if self.pos > 0:
            self.pos -= 1
            self._apply()
        self.last = 0.0
        return "break"

    def redo(self, _e=None):
        if self.pos < len(self.stack) - 1:
            self.pos += 1
            self._apply()
        self.last = 0.0
        return "break"


class Tooltip:
    """Small hover hint for a Tk widget."""

    def __init__(self, widget, text, delay=600):
        self.widget, self.text, self.delay = widget, text, delay
        self.tip = None
        self.job = None
        widget.bind("<Enter>", self._schedule, "+")
        widget.bind("<Leave>", self._hide, "+")
        widget.bind("<ButtonPress>", self._hide, "+")

    def _schedule(self, _e=None):
        self._hide()
        self.job = self.widget.after(self.delay, self._show)

    def _show(self):
        import tkinter as tk
        self.job = None
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry("+%d+%d" % (x, y))
        tk.Label(self.tip, text=self.text, justify="left", background="#ffffe0", relief="solid",
                 borderwidth=1, padx=6, pady=3, wraplength=380).pack()

    def _hide(self, _e=None):
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


EXISTING_LABELS = [("Ask", "ask"), ("Skip", "skip"), ("Download again", "overwrite")]


FLAG_KEYS = ("VIDEO", "ORIGINAL", "COMFY", "WEBP2JPG", "USE_SUBFOLDER", "BRIDGE", "DSCR_AS_MODEL", "MODEL")
TEXT_KEYS = ("TOKEN", "PATH", "PREFIX", "PICS", "IMGFOLDER", "DSCR", "GALLERY")


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def main_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, scrolledtext, messagebox
    import tkinter.font as tkfont

    saved = load_settings()
    if sys.platform.startswith("win"):  # own identity in the taskbar (instead of "Python")
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CivitaiGrabber.App")
        except Exception:  # noqa
            pass
    root = tk.Tk()
    app_icon = None
    icon_imgs = {}
    try:
        app_icon = tk.PhotoImage(data="".join(ICON_PNG_B64))
        root.iconphoto(True, app_icon)
        icon_imgs["idle"] = app_icon
        for key, data in ICON_STATES.items():
            icon_imgs[key] = tk.PhotoImage(data="".join(data))
    except tk.TclError:
        pass
    root.title("Civitai Grabber v%s" % VERSION)
    root.minsize(920, 580)
    mono = tkfont.nametofont("TkFixedFont").copy()
    mono.configure(size=9)

    # ---- window position/size: restore the last one if it still makes sense
    def start_geometry():
        win = saved.get("WINDOW") or {}
        m = re.match(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$", str(win.get("geometry") or ""))
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        if not m:
            return "960x740+40+20"
        w, h, x, y = (int(m.group(i)) for i in range(1, 5))
        w, h = max(920, min(w, sw)), max(580, min(h, sh))
        if x < -sw or x > 2 * sw - 100:
            x = 40
        if y < 0 or y > sh - 100:
            y = 20
        return "%dx%d%+d%+d" % (w, h, x, y)

    root.geometry(start_geometry())
    normal_geo = {"g": root.geometry()}
    if (saved.get("WINDOW") or {}).get("zoomed"):
        try:
            root.state("zoomed")
        except Exception:  # noqa
            pass

    def track_geometry(event):
        if event.widget is root:
            try:
                if root.state() == "normal":
                    normal_geo["g"] = root.geometry()
            except Exception:  # noqa
                pass

    root.bind("<Configure>", track_geometry, "+")

    # Ctrl+C/V/X/A/Z/Y must also work on non-Latin keyboard layouts (e.g. Russian);
    # Tk on Windows ignores them there, so they are mapped by hardware key code.
    def layout_independent_keys(event):
        if not sys.platform.startswith("win") or not (event.state & 0x4):
            return None
        seq = {86: ("<<Paste>>", "v"), 67: ("<<Copy>>", "c"), 88: ("<<Cut>>", "x"), 65: ("<<SelectAll>>", "a"),
               90: ("<<Undo>>", "z"), 89: ("<<Redo>>", "y")}.get(event.keycode)
        if seq and event.keysym.lower() != seq[1]:
            event.widget.event_generate(seq[0])
            return "break"
        return None

    root.bind_all("<Key>", layout_independent_keys, "+")

    def attach_menu(widget, editable=True):
        m = tk.Menu(root, tearoff=0)
        if editable:
            m.add_command(label="Undo", command=lambda: widget.event_generate("<<Undo>>"))
            m.add_separator()
            m.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
        m.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
        if editable:
            m.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
        m.add_command(label="Select all", command=lambda: widget.event_generate("<<SelectAll>>"))

        def show(e):
            widget.focus_set()
            m.tk_popup(e.x_root, e.y_root)

        widget.bind("<Button-3>", show)
        if sys.platform == "darwin":
            widget.bind("<Button-2>", show)
            widget.bind("<Control-Button-1>", show)

    q = queue.Queue()
    ask_q = queue.Queue()
    choose_q = queue.Queue()
    done_q = queue.Queue()
    stop = threading.Event()
    state = {"thread": None}
    tb = {"icon": "idle", "key": None, "key_t": 0.0, "attach_t": 0.0, "last_flash": 0.0, "blink": None, "hold": None, "hold_t": 0.0, "prog": TaskbarProgress()}
    gal_state = {"s": None}
    launch_state = {"asked": bool(saved.get("LAUNCH_ASKED"))}
    RECENT_LIMIT = {"PATH": 12, "PREFIX": 12, "IMGFOLDER": 10}
    recent = {"PATH": [], "PREFIX": [], "IMGFOLDER": []}  # newest first; RECENT_LIMIT for folders/prefixes, 10 for image subfolders
    combos = {}

    v = {k: tk.StringVar() for k in TEXT_KEYS}
    b = {k: tk.BooleanVar() for k in FLAG_KEYS}
    existing_var = tk.StringVar()

    # ---- settings
    frm = ttk.Frame(root, padding=(8, 8, 8, 4))
    frm.pack(fill="x")
    frm.columnconfigure(1, weight=1)

    ttk.Label(frm, text="API token:").grid(row=0, column=0, sticky="w", pady=2)
    row_tk = ttk.Frame(frm)
    row_tk.grid(row=0, column=1, columnspan=2, sticky="we", padx=(6, 0), pady=2)
    e_token = ttk.Entry(row_tk, textvariable=v["TOKEN"], show="•", width=44)
    e_token.pack(side="left", ipady=2)
    lock_btn = ttk.Button(row_tk, text="Lock", width=9)
    lock_btn.pack(side="left", padx=(6, 0))
    cb_bridge = ttk.Checkbutton(row_tk, text="Browser bridge", variable=b["BRIDGE"])
    cb_bridge.pack(side="right")
    bridge_lbl = ttk.Label(row_tk, text="", width=26, anchor="e")
    bridge_lbl.pack(side="right", padx=(0, 6))

    ttk.Label(frm, text="Output folder:").grid(row=1, column=0, sticky="w", pady=2)
    path_combo = ttk.Combobox(frm, textvariable=v["PATH"], height=12)
    path_combo.grid(row=1, column=1, sticky="nswe", padx=(6, 0), pady=2, ipady=2)
    combos["PATH"] = path_combo
    browse_btn = ttk.Button(frm, text="Browse…", width=9)
    browse_btn.grid(row=1, column=2, sticky="nswe", padx=(6, 0), pady=2)

    # row 3: what to download (left) and the single-image subfolder (right)
    row_dl = ttk.Frame(frm)
    row_dl.grid(row=2, column=0, columnspan=3, sticky="we", pady=2)
    cb_model = ttk.Checkbutton(row_dl, text="Model file", variable=b["MODEL"])
    cb_model.pack(side="left")
    lbl_prefix = ttk.Label(row_dl, text="Add prefix:")
    lbl_prefix.pack(side="left", padx=(12, 6))
    e_prefix = ttk.Combobox(row_dl, textvariable=v["PREFIX"], width=12, height=12)
    e_prefix.pack(side="left", ipady=2)
    combos["PREFIX"] = e_prefix
    ttk.Label(row_dl, text="Examples:").pack(side="left", padx=(12, 6))
    e_pics = ttk.Entry(row_dl, textvariable=v["PICS"], width=6)
    e_pics.pack(side="left", ipady=2)
    ttk.Label(row_dl, text="From gallery:").pack(side="left", padx=(12, 6))
    e_gal = ttk.Entry(row_dl, textvariable=v["GALLERY"], width=6)
    e_gal.pack(side="left", ipady=2)
    cb_sub = ttk.Checkbutton(row_dl, text="Image subfolder:", variable=b["USE_SUBFOLDER"])
    cb_sub.pack(side="left", padx=(16, 6))
    e_img = ttk.Combobox(row_dl, textvariable=v["IMGFOLDER"], width=12)
    e_img.pack(side="left", fill="x", expand=True, ipady=2)  # grows with the window
    combos["IMGFOLDER"] = e_img

    # row 4: what to do with known items (left), description file (right)
    row_ex = ttk.Frame(frm)
    row_ex.grid(row=3, column=0, columnspan=3, sticky="we", pady=2)
    # everything sits at the right edge; free space stays on the left
    cb_dname = ttk.Checkbutton(row_ex, text="Name as model", variable=b["DSCR_AS_MODEL"])
    cb_dname.pack(side="right", padx=(10, 0))
    dscr_box = ttk.Frame(row_ex)  # its width is set by align_rows() so that this row lines up with the check boxes above
    dscr_box.pack(side="right")
    e_dscr = ttk.Entry(dscr_box, textvariable=v["DSCR"], width=14)
    e_dscr.pack(fill="both", expand=True, ipady=2)
    ttk.Label(row_ex, text="Description file:").pack(side="right", padx=(16, 6))
    combo = ttk.Combobox(row_ex, textvariable=existing_var, state="readonly", width=14,
                         values=[lbl for lbl, _ in EXISTING_LABELS])
    combo.pack(side="right")
    ttk.Label(row_ex, text="If already downloaded:").pack(side="right", padx=(0, 6))

    def sync_fields(*_):  # greyed-out boxes: subfolder unless its box is ticked, prefix without Model file, name box with Name-as-model
        e_img.configure(state="normal" if b["USE_SUBFOLDER"].get() else "disabled")
        e_dscr.configure(state="disabled" if b["DSCR_AS_MODEL"].get() else "normal")
        e_prefix.configure(state="normal" if b["MODEL"].get() else "disabled")

    for key in ("USE_SUBFOLDER", "DSCR_AS_MODEL", "MODEL"):
        b[key].trace_add("write", sync_fields)


    # ---- resizable split: links on top, log below (drag the divider)
    paned = ttk.PanedWindow(root, orient="vertical")
    paned.pack(fill="both", expand=True, padx=8, pady=(0, 4))
    top_pane = ttk.Frame(paned)
    bottom_pane = ttk.Frame(paned)
    paned.add(top_pane, weight=1)
    paned.add(bottom_pane, weight=3)

    hdr = ttk.Frame(top_pane)  # "Links" title on the left, option checkboxes on the right
    hdr.pack(fill="x")
    ttk.Label(hdr, text="Links (one per line):").pack(side="left")
    cb_comfy = ttk.Checkbutton(hdr, text="ComfyUI workflow as .json", variable=b["COMFY"])
    cb_webp = ttk.Checkbutton(hdr, text="Convert WebP to JPG", variable=b["WEBP2JPG"])
    cb_orig = ttk.Checkbutton(hdr, text="Original file names", variable=b["ORIGINAL"])
    cb_video = ttk.Checkbutton(hdr, text="Include videos", variable=b["VIDEO"])
    cb_comfy.pack(side="right")
    for w in (cb_webp, cb_orig, cb_video):
        w.pack(side="right", padx=(0, 14))
    actions = ttk.Frame(top_pane, padding=(0, 10, 0, 6))
    actions.pack(side="bottom", fill="x")
    urlbox = scrolledtext.ScrolledText(top_pane, height=6, wrap="none", font=mono, undo=True)
    urlbox.pack(fill="both", expand=True, pady=(2, 0))

    paste_btn = ttk.Button(actions, text="Paste")
    undo_btn = ttk.Button(actions, text="Undo", takefocus=False)
    redo_btn = ttk.Button(actions, text="Redo", takefocus=False)
    sample_btn = ttk.Button(actions, text="Create sample txt")  # hidden unless SHOW_TXT_BUTTONS
    load_btn = ttk.Button(actions, text="Load from txt…")
    clear_btn = ttk.Button(actions, text="Clear all")
    shown = [paste_btn] + ([sample_btn, load_btn] if SHOW_TXT_BUTTONS else []) + [undo_btn, redo_btn, clear_btn]
    for w in shown:
        w.pack(side="left", padx=(0, 6))
    stop_btn = ttk.Button(actions, text="Stop", state="disabled")
    class StartButton(tk.Button):
        """The main button: the same blue with white text as the buttons of the browser extension."""
        COLORS = {"normal": ("#2162be", "#ffffff"), "disabled": ("#a9c1e6", "#ffffff")}

        def __init__(self, master, **kw):
            f = tkfont.nametofont("TkDefaultFont").copy()
            f.configure(weight="bold")
            tk.Button.__init__(self, master, font=f, relief="flat", bd=0, padx=18, pady=4, cursor="hand2",
                               activebackground="#163f7a", activeforeground="#ffffff", disabledforeground="#ffffff",
                               highlightthickness=0, **kw)
            self._paint("normal")
            self.bind("<Enter>", lambda e: self._hover(True))
            self.bind("<Leave>", lambda e: self._hover(False))

        def _paint(self, state):
            bg, fg = self.COLORS[state]
            tk.Button.configure(self, bg=bg, fg=fg)

        def _hover(self, inside):
            if str(self.cget("state")) != "disabled":
                tk.Button.configure(self, bg="#1b4f99" if inside else self.COLORS["normal"][0])

        def configure(self, cnf=None, **kw):
            res = tk.Button.configure(self, cnf, **kw) if (cnf or kw) else tk.Button.configure(self)
            if "state" in kw:
                st = str(kw["state"])
                self._paint("disabled" if st == "disabled" else "normal")
                tk.Button.configure(self, cursor="arrow" if st == "disabled" else "hand2")
            return res

        config = configure

    start_btn = StartButton(actions, text="START")
    stop_btn.pack(side="right")
    start_btn.pack(side="right", padx=(0, 6))

    logbtns = ttk.Frame(bottom_pane, padding=(0, 4, 0, 0))
    logbtns.pack(side="bottom", fill="x")
    copylog_btn = ttk.Button(logbtns, text="Copy log")
    openlog_btn = ttk.Button(logbtns, text="Open log file")
    copylog_btn.pack(side="left", padx=(0, 6))
    openlog_btn.pack(side="left")
    help_btn = ttk.Button(logbtns, text="?", width=3)
    help_btn.pack(side="right")
    box = scrolledtext.ScrolledText(bottom_pane, wrap="word", state="disabled", font=mono)
    box.pack(fill="both", expand=True)

    # ---- undo for entry fields, context menus, hover hints
    for ent, key in ((e_token, "TOKEN"), (path_combo, "PATH"), (e_img, "IMGFOLDER"), (e_prefix, "PREFIX"),
                     (e_dscr, "DSCR"), (e_pics, "PICS"), (e_gal, "GALLERY")):
        UndoEntry(ent, v[key])
        attach_menu(ent)
    attach_menu(urlbox)
    attach_menu(box, editable=False)

    for widget, text in (
            (e_token, "Your Civitai API key (account settings, API keys). Saved in civitai_grabber_settings.json next to the script."),
            (lock_btn, "Lock the token field against accidental edits / unlock it to change the token."),
            (path_combo, "Category folder: the place for one kind of models (characters, styles, poses ...). "
                         "Every model gets its own subfolder here, named after the model. "
                         "The drop-down list holds the 12 most recently used folders."),
            (browse_btn, "Choose the category folder."),
            (cb_model, "Download the model file (LoRA, checkpoint ...). Untick to get only examples/gallery images and the description file."),
            (lbl_prefix, "Text put in front of the model file name (used only when Model file is ticked). "
                         "Handy for sorting models in a stack."),
            (e_gal, "How many images other users uploaded to the model's gallery to download: a number, all (can be thousands!), "
                    "or 0/empty for none. Needs the browser bridge, so this box is greyed out without it."),
            (cb_sub, "Save single image links into the subfolder below. Only for a run that has NO model link before "
                     "the image links; images that follow a model link always go into that model's folder."),
            (cb_dname, "Name the description file after the model. Its extension (.txt / .md) is taken from the "
                       "Description file box; images saved without a model still use the name in that box."),
            (e_img, "Subfolder name or nested path (a/b/c) inside the category folder; a full path such as "
                    "d:\\AI\\pics = exactly that folder. Paste it, no Browse needed. The list holds recent entries."),
            (e_prefix, "Text added to the start of the model file name, e.g. k2-pers-. Handy for sorting and grouping models "
                       "in file lists and in the model stacks of generation programs. The list holds the 12 most recent prefixes."),
            (e_dscr, "Name of the description file written next to the model (.txt or .md; no extension = .txt). "
                     "Markdown is used for .md. EMPTY = no description file is written."),
            (e_pics, "How many example images/videos the model's author attached to the version: a number, all, or 0/empty for none."),
            (combo, "What to do when a model or single image was downloaded before: ask each time, skip, or download again."),
            (cb_video, "Also download video examples. They count towards the number of examples."),
            (cb_orig, "Try to read the original file name from the image page. Pages are often blocked for scripts "
                      "(HTTP 403); then the name from the image address is used."),
            (cb_webp, "Convert downloaded WebP images to JPG (quality 95). Needs Pillow: py -m pip install pillow"),
            (cb_comfy, "EXPERIMENTAL. If the metadata contains a ComfyUI workflow, save it as a .json file next to the "
                       "image (same name), loadable in ComfyUI."),
            (urlbox, "Model links (…/models/ID) and single image links (…/images/ID), one per line. "
                     "Finished links disappear from the list; failed ones stay."),
            (undo_btn, "Undo the last change in the box you were working in (the link list by default). Ctrl+Z does the same."),
            (redo_btn, "Redo what was undone. Ctrl+Y does the same."),
            (sample_btn, "Save an empty task-file template (all keys, no data) and open it in your text editor."),
            (load_btn, "Load settings and links from a task txt file. Empty keys are ignored, so the file may hold only links."),
            (paste_btn, "Add the clipboard text to the end of the list."),
            (clear_btn, "Remove all links from the list."),
            (start_btn, "Start downloading all links in the list."),
            (stop_btn, "Stop after the current step."),
            (copylog_btn, "Copy the whole log to the clipboard."),
            (openlog_btn, "Open civitai_grabber.log in the default editor."),
            (cb_bridge, "Local port 127.0.0.1 for the browser extension, which fetches image pages with your logged-in browser."),
            (help_btn, "Short help.")):
        Tooltip(widget, text)

    # ---- logic
    def set_lock(lock):
        e_token.configure(state="readonly" if lock else "normal")
        lock_btn.configure(text="Unlock" if lock else "Lock")

    def push_recent(key, value):
        value = (value or "").strip()
        if not value:
            return
        lst = recent[key]
        lst[:] = [x for x in lst if os.path.normcase(x) != os.path.normcase(value)]
        lst.insert(0, value)
        del lst[RECENT_LIMIT.get(key, 10):]
        combos[key].configure(values=lst)

    def set_values(d):
        """Apply a (partial) settings dict to the window."""
        for k in TEXT_KEYS:
            if k in d:
                v[k].set(str(d[k]))
        for k in FLAG_KEYS:
            if k in d:
                b[k].set(flag(d, k))
        if "EXISTING" in d:
            ex = str(d["EXISTING"]).lower()
            existing_var.set(next((lbl for lbl, code in EXISTING_LABELS if code == ex), "Ask"))
        set_lock(bool(v["TOKEN"].get().strip()))

    def collect_cfg():
        cfg = {k: v[k].get().strip() for k in TEXT_KEYS}
        for k in FLAG_KEYS:
            cfg[k] = "1" if b[k].get() else "0"
        cfg["EXISTING"] = next((code for lbl, code in EXISTING_LABELS if lbl == existing_var.get()), "ask")
        return cfg

    def current_links():
        return [ln.strip() for ln in urlbox.get("1.0", "end").splitlines() if ln.strip().lower().startswith("http")]

    def log(msg):
        msg = scrub(msg)
        file_log(msg)
        q.put(msg)

    def browse_dir():
        d = filedialog.askdirectory(title="Output folder")
        if d:
            v["PATH"].set(os.path.normpath(d))

    def create_sample():
        p = filedialog.asksaveasfilename(title="Save sample task file", initialfile="civitai_task.txt",
                                         defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(SAMPLE_TASK)
        except OSError as ex:
            messagebox.showerror("Civitai Grabber", "Cannot write the file:\n%s" % ex)
            return
        log("Sample task file saved: %s" % p)
        if not open_path(p):
            log("Could not open it automatically - open the file in any text editor.")

    def load_txt():
        p = filedialog.askopenfilename(title="Task file", filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if not p:
            return
        try:
            explicit, urls = read_task_file(p)
        except OSError as ex:
            messagebox.showerror("Civitai Grabber", "Cannot read the file:\n%s" % ex)
            return
        cur = collect_cfg()
        conflicts = []
        for k, val in explicit.items():
            if k not in cur:
                continue
            old = str(cur[k]).strip()
            if k in FLAG_KEYS:
                same = flag(cur, k) == flag(explicit, k)
            elif k == "EXISTING":
                same = old.lower() == str(val).lower()
            else:
                same = (old == str(val).strip()) or not old
            if not same:
                conflicts.append(k)
        take = dict(explicit)
        if conflicts:
            lines = []
            for k in conflicts:
                if k == "TOKEN":
                    lines.append("TOKEN (values hidden)")
                else:
                    lines.append("%s:  window = %r,  file = %r" % (k, cur[k], explicit[k]))
            use_file = messagebox.askyesno(
                "Civitai Grabber",
                "The task file and the window have different values:\n\n%s\n\n"
                "Yes = use the values from the file\nNo = keep the window values" % "\n".join(lines))
            if not use_file:
                for k in conflicts:
                    take.pop(k, None)
        set_values(take)
        if urls:
            if current_links():
                ans = messagebox.askyesnocancel(
                    "Civitai Grabber", "The link list is not empty.\n\nYes = replace it with the links from the file\n"
                                       "No = add them to the end\nCancel = do not load the links")
                if ans is None:
                    urls = []
                elif ans:
                    urlbox.delete("1.0", "end")
            cur_text = urlbox.get("1.0", "end-1c")
            if urls and cur_text and not cur_text.endswith("\n"):
                urlbox.insert("end", "\n")
            if urls:
                urlbox.insert("end", "\n".join(urls) + "\n")
        log("Loaded task file: %s (%d links, %d settings)" % (p, len(urls), len(take)))

    focus_w = {"w": None}

    def remember_focus(e):
        w = e.widget
        if isinstance(w, (tk.Text, ttk.Entry)) and w is not box:
            focus_w["w"] = w

    def target_widget():
        w = focus_w["w"]
        try:
            if w is None or not w.winfo_exists() or str(w.cget("state")) != "normal":
                return urlbox
        except tk.TclError:
            return urlbox
        return w

    def do_undo():
        target_widget().event_generate("<<Undo>>")

    def do_redo():
        target_widget().event_generate("<<Redo>>")

    root.bind_all("<FocusIn>", remember_focus, "+")

    def align_rows():
        """The left edge of the "If already downloaded" box lines up with the "Original file names" check box above it
        (the Description file box takes up the difference)."""
        try:
            root.update_idletasks()
            w0, h0 = e_dscr.winfo_reqwidth(), e_dscr.winfo_reqheight() + 4  # + the ipady of the entry
            dscr_box.pack_propagate(False)
            dscr_box.configure(width=w0, height=h0)
            root.update_idletasks()
            delta = combo.winfo_rootx() - (cb_orig.winfo_rootx() + CHECK_INDENT)
            dscr_box.configure(width=max(70, w0 + delta))
        except Exception:  # noqa
            pass

    def balance_actions():
        """Same space above the button row (to the link list) and below it (to the log), the divider included."""
        try:
            root.update_idletasks()
            sash = bottom_pane.winfo_rooty() - (top_pane.winfo_rooty() + top_pane.winfo_height())
            sash = max(0, min(sash, 30))
            top = max(10, sash + 2)
            actions.configure(padding=(0, top, 0, top - sash))
        except Exception:  # noqa
            pass

    def paste_urls():
        try:
            text = root.clipboard_get()
        except tk.TclError:
            log("The clipboard is empty or does not contain text.")
            return
        cur = urlbox.get("1.0", "end-1c")
        if cur and not cur.endswith("\n"):
            urlbox.insert("end", "\n")
        urlbox.insert("end", text.strip("\r\n") + "\n")
        urlbox.see("end")

    def add_links(links):
        have = set(current_links())
        new = []
        for u in links:
            if u not in have:
                have.add(u)
                new.append(u)
        if new:
            cur = urlbox.get("1.0", "end-1c")
            if cur and not cur.endswith("\n"):
                urlbox.insert("end", "\n")
            urlbox.insert("end", "\n".join(new) + "\n")
            urlbox.see("end")
        log("Added %d link(s) from the browser%s" % (len(new), (" (%d already in the list)" % (len(links) - len(new))) if len(links) > len(new) else ""))

    def clear_urls():
        urlbox.delete("1.0", "end")

    def copy_log():
        root.clipboard_clear()
        root.clipboard_append(box.get("1.0", "end"))

    def open_log():
        if not open_path(LOGFILE):
            log("Cannot open the log file.")

    def show_help():
        win = tk.Toplevel(root)
        win.title("Civitai Grabber - help")
        win.geometry("760x640+%d+%d" % (root.winfo_rootx() + 30, root.winfo_rooty() + 30))
        if app_icon is not None:
            win.iconphoto(False, app_icon)
        bar = ttk.Frame(win, padding=6)
        bar.pack(side="bottom", fill="x")
        status = ttk.Label(bar, text="")
        txt = scrolledtext.ScrolledText(win, wrap="word", font=mono)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", HELP_TEXT % VERSION)
        txt.configure(state="disabled")
        attach_menu(txt, editable=False)

        def refresh():
            if not sys.platform.startswith("win"):
                status.configure(text="Launch from the browser: Windows only")
            else:
                status.configure(text="Launch from the browser: " + ("allowed" if launcher_registered() else "not allowed"))

        def allow():
            if messagebox.askyesno("Civitai Grabber", CONSENT_TEXT, parent=win):
                err = register_launcher()
                if err:
                    messagebox.showerror("Civitai Grabber", err, parent=win)
                launch_state["asked"] = True
                save_settings()
            refresh()

        def remove():
            err = unregister_launcher()
            if err:
                messagebox.showerror("Civitai Grabber", err, parent=win)
            refresh()

        status.pack(side="left")
        ttk.Button(bar, text="Remove launch entry", command=remove).pack(side="right")
        ttk.Button(bar, text="Allow launch from browser", command=allow).pack(side="right", padx=(0, 6))
        refresh()
        win.transient(root)

    def tb_flash(count, icon="pending"):
        """Attention signal: the icon blinks `count` times with a white plate ("icon"), or Windows blinks the whole button ("system")."""
        if not TASKBAR_SIGNALS or TASKBAR_FLASH in (False, None, "off"):
            return
        if time.time() - tb["last_flash"] < 3:  # not more often than every 3 s
            return
        tb["last_flash"] = time.time()
        if TASKBAR_FLASH == "system":
            tb["prog"].flash(count)
            return
        tb["blink"] = {"t0": time.time(), "n": count, "icon": icon}
        blink_loop()

    def blink_loop():
        tb_tick()
        bl = tb["blink"]
        if bl and time.time() - bl["t0"] < bl["n"] * 0.32:
            root.after(40, blink_loop)
        elif bl:
            tb["blink"] = None
            tb_tick()

    def tb_tick():
        """Taskbar button: blink = a link has arrived / a run has ended; whole button green = links are waiting;
        moving bar = connecting; green bar = downloading; red = there were errors; full green + check = finished.
        The finished / error mark is cleared when you return to the window."""
        if not TASKBAR_SIGNALS:
            return
        waiting = bool(current_links())
        if state["thread"] is not None:
            icon = "idle"
            if TB["phase"] == "connecting":
                mode, frac = "indeterminate", 0.0
            elif TB.get("wait_browser"):  # the browser is needed but does not answer: yellow
                mode, frac = "paused", (TB["idx"] + TB["cur"]) / max(1, TB["total"])
            else:
                mode, frac = "normal", (TB["idx"] + TB["cur"]) / max(1, TB["total"])
        elif tb["hold"] == "error":
            icon, mode, frac = "error", "error", 1.0
        elif tb["hold"] == "done":
            icon, mode, frac = "done", "normal", 1.0
        elif waiting and TASKBAR_WAITING == "green":
            icon, mode, frac = "idle", "normal", 1.0
        elif waiting and TASKBAR_WAITING in ("yellow", "bar"):
            icon, mode, frac = "idle", "paused", 1.0
        elif waiting and TASKBAR_WAITING == "plate":
            icon, mode, frac = "pending", "none", 0.0
        else:
            icon, mode, frac = "idle", "none", 0.0
        bl = tb["blink"]
        if bl:
            phase = int((time.time() - bl["t0"]) / 0.16)
            if phase < 2 * bl["n"]:
                icon = bl["icon"] if phase % 2 == 0 else "idle"
        if icon != tb["icon"] and icon in icon_imgs:
            tb["icon"] = icon
            try:
                root.iconphoto(False, icon_imgs[icon])
            except tk.TclError:
                pass
        key = (mode, round(frac, 3))
        now = time.time()
        if key != tb["key"] or now - tb["key_t"] > 2:  # the state is sent again every 2 s: Windows may drop it (taskbar rebuilt)
            tb["key"], tb["key_t"] = key, now
            tb["prog"].set(mode, frac)
        if tb["prog"].p is None and sys.platform.startswith("win") and now - tb["attach_t"] > 30:
            tb["attach_t"] = now
            tb["prog"].attach(root)

    def tb_finish():
        tb["hold"] = None if stop.is_set() else ("error" if TB["failed"] else "done")
        tb["hold_t"] = time.time()
        if tb["hold"]:
            tb["last_flash"] = 0.0
            tb_flash(3, tb["hold"])

    def tb_seen(_e=None):  # the user is back at the window: the "finished" / "error" mark has done its job
        if tb["hold"] and time.time() - tb["hold_t"] > 1.5:
            tb["hold"] = None

    root.bind("<FocusIn>", tb_seen, "+")
    root.bind("<Enter>", tb_seen, "+")
    if TASKBAR_SIGNALS:
        root.after(600, lambda: tb["prog"].attach(root))

    def remove_line(u):
        """Remove the first line of the link list that equals u (a finished link)."""
        for i, ln in enumerate(urlbox.get("1.0", "end-1c").splitlines(), 1):
            if ln.strip() == u.strip():
                urlbox.delete("%d.0" % i, "%d.0 lineend+1c" % i)
                urlbox.edit_reset()
                return

    def ask(msg):
        ev, holder = threading.Event(), {}
        ask_q.put((msg, holder, ev))
        while not ev.wait(0.3):
            if stop.is_set():
                return False
        return holder.get("ans", False)

    def show_chooser(title, rows, default):
        """Modal list with the files of one model version; returns the indices of the ticked files (may be empty)."""
        win = tk.Toplevel(root)
        win.title("Choose model files")
        win.transient(root)
        try:
            if app_icon:
                win.iconphoto(False, app_icon)
        except tk.TclError:
            pass
        result = {"ans": None}
        ttk.Label(win, text=title, wraplength=720, justify="left").pack(anchor="w", padx=14, pady=(12, 2))
        ttk.Label(win, text="This version has several model files. Tick the ones to download:").pack(anchor="w", padx=14, pady=(0, 6))
        grid = ttk.Frame(win)
        grid.pack(fill="x", padx=14)
        vars_ = []
        for i, r in enumerate(rows):
            var = tk.BooleanVar(value=i in default)
            vars_.append(var)
            ttk.Checkbutton(grid, text=r["name"], variable=var).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(grid, text=r["info"]).grid(row=i, column=1, sticky="w", padx=(20, 0))
            ttk.Label(grid, text=r["size"]).grid(row=i, column=2, sticky="e", padx=(20, 0))
            ttk.Label(grid, text="main file" if r["primary"] else "").grid(row=i, column=3, sticky="w", padx=(12, 0))
        grid.columnconfigure(0, weight=1)
        total = ttk.Label(win, text="")
        total.pack(anchor="w", padx=14, pady=(8, 0))
        ttk.Label(win, text="Stop ends the whole run and keeps this link in the list - use it if you need to look into the choice first.",
                  wraplength=720, justify="left", foreground="#555").pack(anchor="w", padx=14, pady=(6, 0))

        def update_total(*_):
            sel = [rows[i] for i, v in enumerate(vars_) if v.get()]
            total.configure(text="Selected: %d file(s), %.2f GB" % (len(sel), sum(r["gb"] for r in sel)))
            try:
                ok_btn.configure(state="normal" if sel else "disabled")
            except (NameError, tk.TclError):
                pass

        for var in vars_:
            var.trace_add("write", update_total)
        update_total()
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=14, pady=12)

        def ok():
            result["ans"] = [i for i, v in enumerate(vars_) if v.get()]
            win.destroy()

        def cancel():
            result["ans"] = None
            win.destroy()

        ttk.Button(bar, text="Stop", command=cancel).pack(side="right")
        ok_btn = ttk.Button(bar, text="Download selected", command=ok)
        ok_btn.pack(side="right", padx=(0, 8))
        update_total()
        win.protocol("WM_DELETE_WINDOW", cancel)
        win.bind("<Escape>", lambda _e: cancel())
        win.bind("<Return>", lambda _e: ok() if any(v.get() for v in vars_) else None)
        win.update_idletasks()
        x = root.winfo_rootx() + max(0, (root.winfo_width() - win.winfo_width()) // 2)
        y = root.winfo_rooty() + max(0, (root.winfo_height() - win.winfo_height()) // 3)
        win.geometry("+%d+%d" % (x, y))
        win.grab_set()
        win.focus_set()
        root.wait_window(win)
        return result["ans"]

    def choose_files(title, rows, default):
        ev, holder = threading.Event(), {}
        choose_q.put((title, rows, default, holder, ev))
        while not ev.wait(0.3):
            if stop.is_set():
                return None
        return holder.get("ans")

    CHOOSER["fn"] = choose_files

    def set_bridge():
        if b["BRIDGE"].get():
            BRIDGE.start()
        else:
            BRIDGE.stop()

    def bridge_status():
        if not b["BRIDGE"].get():
            return "off"
        if not BRIDGE.server:
            return "could not start (ports busy)"
        return "connected" if BRIDGE.connected() else "waiting for the extension"

    def pump():
        try:
            while True:
                msg = q.get_nowait()
                box.configure(state="normal")
                box.insert("end", msg + "\n")
                box.see("end")
                box.configure(state="disabled")
        except queue.Empty:
            pass
        try:
            while True:
                u_done = done_q.get_nowait()
                remove_line(u_done)
                note = ATTENTION.pop(u_done, None)
                if note:
                    BRIDGE.notify("attention", u_done, note)
                else:
                    BRIDGE.notify_finished(u_done)
        except queue.Empty:
            pass
        incoming = []
        try:
            while True:
                incoming.append(BRIDGE.added.get_nowait())
        except queue.Empty:
            pass
        if incoming:
            add_links(incoming)
            tb_flash(2)
        try:
            msg, holder, ev = ask_q.get_nowait()
            holder["ans"] = messagebox.askyesno("Civitai Grabber", msg)
            ev.set()
        except queue.Empty:
            pass
        try:
            c_title, c_rows, c_default, c_holder, c_ev = choose_q.get_nowait()
            c_holder["ans"] = show_chooser(c_title, c_rows, c_default)
            c_ev.set()
        except queue.Empty:
            pass
        t = state["thread"]
        if t is not None and not t.is_alive():
            state["thread"] = None
            tb_finish()
            start_btn.configure(state="normal")
            stop_btn.configure(state="disabled")
        bridge_lbl.configure(text=bridge_status())
        tb_tick()
        if (not launch_state["asked"] and BRIDGE.connected() and sys.platform.startswith("win")
                and not launcher_registered()):
            launch_state["asked"] = True  # ask once, when the extension has connected for the first time
            if messagebox.askyesno("Civitai Grabber", CONSENT_TEXT):
                err = register_launcher()
                log("Launch from the browser allowed." if not err else "Could not write the registry entry: %s" % err)
            save_settings()
        want = "normal" if (b["BRIDGE"].get() and BRIDGE.connected()) else "disabled"
        if gal_state["s"] != want:
            gal_state["s"] = want
            e_gal.configure(state=want)
        root.after(150, pump)

    def install_pillow():
        exe = python_for_pip()
        log("Installing Pillow: %s -m pip install pillow" % exe)
        try:
            kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform.startswith("win") else {}
            r = subprocess.run([exe, "-m", "pip", "install", "pillow"], capture_output=True, text=True,
                               timeout=300, **kw)
            for ln in (r.stdout + r.stderr).strip().splitlines()[-3:]:
                log("  pip: " + ln)
            if r.returncode == 0:
                import importlib
                importlib.invalidate_caches()
                STATE["pillow_warned"] = False
                log("Pillow installed - WebP conversion is ready.")
            else:
                log("pip failed (exit code %d). Command to run by hand:  \"%s\" -m pip install pillow" % (r.returncode, exe))
        except Exception as ex:  # noqa
            log("Could not run pip: %s" % ex)

    def on_webp():
        if not b["WEBP2JPG"].get():
            return
        try:
            import PIL  # noqa
        except ImportError:
            if messagebox.askyesno("Civitai Grabber",
                                   "WebP conversion needs the Pillow library, which is not installed for the Python "
                                   "that runs this script:\n%s\n\nInstall it now (pip install pillow)?" % python_for_pip()):
                threading.Thread(target=install_pillow, daemon=True).start()

    def worker(cfg, urls, need_pillow=False):
        try:
            if need_pillow:
                install_pillow()
            run_task(cfg, urls, log, stop, ask, done_q.put)
        except Exception as ex:  # noqa
            log("Critical error: %s" % ex)
            file_log(traceback.format_exc())

    def window_state():
        try:
            frac = paned.sashpos(0) / max(1, paned.winfo_height())
        except Exception:  # noqa
            frac = 0.25
        zoomed = False
        try:
            zoomed = root.state() == "zoomed"
        except Exception:  # noqa
            pass
        return {"geometry": normal_geo["g"], "zoomed": zoomed, "sash": round(frac, 4)}

    def save_settings():
        try:
            d = collect_cfg()
            d["URLS"] = urlbox.get("1.0", "end").strip()
            d["LAUNCH_ASKED"] = launch_state["asked"]
            d["RECENT"] = list(recent["PATH"])
            d["RECENT_PREFIX"] = list(recent["PREFIX"])
            d["RECENT_SUB"] = list(recent["IMGFOLDER"])
            d["WINDOW"] = window_state()
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def start():
        cfg = collect_cfg()
        urls = current_links()
        if not urls:
            log("The link list is empty.")
            return
        if not cfg["DSCR"] and cfg["DSCR_AS_MODEL"] != "1":
            if not messagebox.askyesno("Civitai Grabber", "The description file name is empty: no description and no "
                                                          "generation metadata will be written.\n\nContinue anyway?"):
                return
        need_pillow = False
        if cfg["WEBP2JPG"] == "1":
            try:
                import PIL  # noqa
            except ImportError:
                need_pillow = messagebox.askyesno(
                    "Civitai Grabber", "WebP to JPG conversion needs the Pillow library, which is not installed for the "
                                       "Python that runs this script:\n%s\n\nInstall it now (pip install pillow)?" % python_for_pip())
        for key in ("PATH", "PREFIX", "IMGFOLDER"):
            push_recent(key, cfg[key])
        save_settings()
        stop.clear()
        start_btn.configure(state="disabled")
        stop_btn.configure(state="normal")
        t = threading.Thread(target=worker, args=(cfg, urls, need_pillow), daemon=True)
        state["thread"] = t
        t.start()

    def do_stop():
        stop.set()
        log("Stopping after the current step…")

    lock_btn.configure(command=lambda: set_lock(str(e_token.cget("state")) != "readonly"))
    browse_btn.configure(command=browse_dir)
    sample_btn.configure(command=create_sample)
    load_btn.configure(command=load_txt)
    start_btn.configure(command=start)
    stop_btn.configure(command=do_stop)
    copylog_btn.configure(command=copy_log)
    openlog_btn.configure(command=open_log)
    paste_btn.configure(command=paste_urls)
    undo_btn.configure(command=do_undo)
    redo_btn.configure(command=do_redo)
    clear_btn.configure(command=clear_urls)
    help_btn.configure(command=show_help)
    cb_bridge.configure(command=set_bridge)
    cb_webp.configure(command=on_webp)

    # ---- restore previous settings
    for key, skey in (("PATH", "RECENT"), ("PREFIX", "RECENT_PREFIX"), ("IMGFOLDER", "RECENT_SUB")):
        for item in reversed(saved.get(skey) or []):
            push_recent(key, item)
    set_values({**DEFAULTS, **{k: x for k, x in saved.items() if k in DEFAULTS}})
    sync_fields()
    urlbox.insert("1.0", saved.get("URLS", ""))
    urlbox.edit_reset()
    for key in ("PATH", "PREFIX", "IMGFOLDER"):
        if not recent[key]:
            push_recent(key, v[key].get())

    def restore_sash():
        frac = (saved.get("WINDOW") or {}).get("sash")
        try:
            if isinstance(frac, (int, float)) and 0.08 <= frac <= 0.92:
                paned.sashpos(0, int(frac * paned.winfo_height()))
        except Exception:  # noqa
            pass
        balance_actions()
        align_rows()

    root.after(300, restore_sash)
    root.after(700, balance_actions)
    root.after(800, align_rows)
    if launcher_registered():  # keep the entry pointing at the script that runs now (moved / updated file)
        register_launcher()
    BRIDGE.launcher = launcher_registered()

    if old_launcher_present():  # an entry of an earlier test build: remove it; the normal question comes again
        remove_old_launcher()
        launch_state["asked"] = False
    set_bridge()

    def on_close():
        save_settings()
        BRIDGE.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    pump()
    root.mainloop()


if __name__ == "__main__":
    if sys.stdout is None:  # started via pythonw / .pyw
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    from_browser = len(sys.argv) > 1 and sys.argv[1].lower().startswith("civitai-grabber:")
    if len(sys.argv) > 1 and not from_browser:
        c, u = parse_task_file(sys.argv[1])
        if flag(c, "BRIDGE"):
            BRIDGE.start()
        run_task(c, u, lambda m: (file_log(m), print(m)), threading.Event(), lambda m: False)
    elif another_instance_running():
        if not from_browser:
            try:
                import tkinter as _tk
                from tkinter import messagebox as _mb
                _r = _tk.Tk()
                _r.withdraw()
                _mb.showinfo("Civitai Grabber", "Civitai Grabber is already running (look at the taskbar).")
            except Exception:  # noqa
                pass
    else:
        try:
            main_gui()
        except Exception:
            file_log("GUI crashed:\n" + traceback.format_exc())
            try:
                from tkinter import messagebox
                messagebox.showerror("Civitai Grabber", "The program crashed, see civitai_grabber.log")
            except Exception:  # noqa
                pass
