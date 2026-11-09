#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Civitai Grabber v0.52 - batch downloader for Civitai LoRA models and their example
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
    RENAME_ID: 0           1 = a model file with an ID-like name (26 random characters, e.g. from the Civitai trainer) is saved under the
                           model title (plus the version name when the model has several versions); the original name goes to the description
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
import struct
import zlib
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
import base64
import hashlib
import secrets
import webbrowser
from html.parser import HTMLParser

VERSION = "0.52"

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

STATE = {"log": None, "bridge_failures": 0, "bridge_off": False, "stop": None, "blocked": 0, "page_blocked": False, "model_folder": None, "model_name": None, "model_failed": False, "pillow_warned": False, "net_fail": 0, "net_down": False,
         "made_dirs": [], "parts": set()}

DEFAULTS = {"BRIDGE": "1", "TOKEN": "", "PATH": "", "PREFIX": "", "PICS": "4", "VIDEO": "1", "ORIGINAL": "1",
            "COMFY": "0", "EXISTING": "ask", "IMGFOLDER": "", "USE_SUBFOLDER": "0", "DSCR": "dscr.txt", "DSCR_AS_MODEL": "0", "MODEL": "1", "GALLERY": "0",
            "WEBP2JPG": "0", "RENAME_ID": "0", "USE_API": "0", "DARK": "0", "CHECK_UPDATES": "1", "COL_PICS": "1", "COL_GALLERY": "1",
            "ON_PARTIAL": "ask", "PARTIAL_NOTICE": "each", "BRIDGE_DARK": "0"}


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


def history_add(key, url, folder, status, file=None, note=None):
    try:
        rec = {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "key": key, "url": url, "folder": folder, "status": status, "file": file}
        if note:
            rec["note"] = note
        with open(HISTORY, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
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

# --------------------------------------------------------------------- Sign in with Civitai (OAuth 2.0 + PKCE)
OAUTH_CLIENT_ID = "0ea2a070-d17a-45d9-a772-ba3938974d06"  # public client of this program (it has no secret: PKCE is used)
OAUTH_PORT = 8765
OAUTH_REDIRECT = "http://localhost:%d/oauth/callback" % OAUTH_PORT
OAUTH_SCOPE = 37  # UserRead + ModelsRead + MediaRead: read-only
AUTH_FILE = os.path.join(SCRIPT_DIR, "civitai_grabber_auth.json")
SITES = ("civitai.red", "civitai.com")


def site_of(url):
    m = re.match(r"^https?://(?:[^/]*\.)?(civitai\.(?:red|com))(?:[:/]|$)", url or "")
    return m.group(1) if m else None


class _OAuthHandler(http.server.BaseHTTPRequestHandler):
    result = {}
    next_url = "https://civitai.red/"  # where the tab goes if the browser does not let a page close itself

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path != "/oauth/callback":
            self.send_response(404)
            self.end_headers()
            return
        _OAuthHandler.result.update({k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()})
        body = ("<html><head><meta charset='utf-8'></head><body style='font-family:sans-serif'>"
                "<h3>Civitai Grabber</h3><p>Signed in. This tab closes itself or opens Civitai in a moment; "
                "you can return to the program.</p>"
                "<script>setTimeout(function(){window.close();},400);"
                "setTimeout(function(){location.href=%s;},1500);</script></body></html>" % json.dumps(_OAuthHandler.next_url)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST",
                                 headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode("utf-8"))
            raise RuntimeError("%s %s" % (j.get("error", e.code), j.get("error_description", "")))
        except ValueError:
            raise RuntimeError("HTTP %s" % e.code)


class Auth:
    """Keeps the OAuth sign-in (per site) and counts which credentials every request used, so the log can prove
    whether the sign-in was enough or the API key was needed."""

    def __init__(self):
        self.lock = threading.RLock()
        self.sites = {}    # "civitai.red" -> {"refresh", "access", "exp", "user"}
        self.issued = {}   # every access token handed out -> site (an old string still maps to the fresh one)
        self.ep_cache = {}
        self.running = False
        self.counts = {"oauth": 0, "apikey": 0, "none": 0}
        self.denied = []
        self.kind = ""
        self.load()

    # ---- storage
    def load(self):
        try:
            with open(AUTH_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        for site, d in (data.get("sites") or {}).items():
            if site in SITES and d.get("refresh"):
                self.sites[site] = {"refresh": d["refresh"], "access": "", "exp": 0, "user": d.get("user", "")}
                SECRETS.add(d["refresh"])

    def save(self):
        data = {"sites": {s_: {"refresh": d["refresh"], "user": d.get("user", "")} for s_, d in self.sites.items()}}
        try:
            with open(AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
        except OSError:
            pass

    def signed_in(self):
        return {s_: d.get("user", "") for s_, d in self.sites.items()}

    def sign_out(self):
        with self.lock:
            self.sites.clear()
            self.issued.clear()
            self.save()

    # ---- endpoints
    def endpoints(self, site):
        if site in self.ep_cache:
            return self.ep_cache[site]
        for base in ("https://auth.%s" % site, "https://%s" % site):
            try:
                j = json.loads(http_get(base + "/.well-known/openid-configuration", None, timeout=30, retries=1).decode("utf-8"))
                if j.get("authorization_endpoint") and j.get("token_endpoint"):
                    ep = {"authorize": j["authorization_endpoint"], "token": j["token_endpoint"], "userinfo": j.get("userinfo_endpoint")}
                    self.ep_cache[site] = ep
                    return ep
            except Exception:  # noqa
                pass
        base = "https://%s/api/auth/oauth" % site  # civitai.red serves the sign-in paths directly
        ep = {"authorize": base + "/authorize", "token": base + "/token", "userinfo": base + "/userinfo"}
        self.ep_cache[site] = ep
        return ep

    # ---- sign in / refresh
    def _store(self, site, j, user=None):
        access = j.get("access_token")
        if not access:
            raise RuntimeError("no access token in the answer")
        d = self.sites.setdefault(site, {"refresh": "", "access": "", "exp": 0, "user": ""})
        d["access"] = access
        d["exp"] = time.time() + float(j.get("expires_in") or 3600)
        if j.get("refresh_token"):
            d["refresh"] = j["refresh_token"]
            SECRETS.add(d["refresh"])
        if user:
            d["user"] = user
        SECRETS.add(access)
        self.issued[access] = site
        self.save()

    def sign_in(self, site, log=None, open_browser=None, endpoints=None, timeout=240):
        """Opens the Civitai consent page in the browser and waits for the answer. Returns the user name."""
        log = log or (lambda m: None)
        ep = endpoints or self.endpoints(site)
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        servers = []
        for host in ("127.0.0.1", "::1"):  # "localhost" can mean either
            try:
                if host == "::1":
                    class _S6(http.server.HTTPServer):
                        address_family = socket.AF_INET6
                    srv = _S6((host, OAUTH_PORT), _OAuthHandler)
                else:
                    srv = http.server.HTTPServer((host, OAUTH_PORT), _OAuthHandler)
                srv.timeout = 0.5
                servers.append(srv)
            except OSError:
                pass
        if not servers:
            raise RuntimeError("port %d is busy; close the program that uses it or use the API token" % OAUTH_PORT)
        _OAuthHandler.result.clear()
        _OAuthHandler.next_url = "https://%s/" % site
        url = ep["authorize"] + "?" + urllib.parse.urlencode({
            "response_type": "code", "client_id": OAUTH_CLIENT_ID, "redirect_uri": OAUTH_REDIRECT,
            "scope": OAUTH_SCOPE, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
        log("Sign-in: the browser opens the Civitai page - press Allow")
        (open_browser or webbrowser.open)(url)
        t0 = time.time()
        try:
            while time.time() - t0 < timeout and not _OAuthHandler.result:
                for srv in servers:
                    srv.handle_request()
        finally:
            for srv in servers:
                srv.server_close()
        res = dict(_OAuthHandler.result)
        if not res:
            raise RuntimeError("no answer from the browser within %d seconds" % timeout)
        if res.get("error"):
            raise RuntimeError("Civitai refused: %s %s" % (res.get("error"), res.get("error_description", "")))
        if res.get("state") != state or not res.get("code"):
            raise RuntimeError("the answer of the browser does not match the request")
        j = _post_form(ep["token"], {"grant_type": "authorization_code", "code": res["code"], "redirect_uri": OAUTH_REDIRECT,
                                     "client_id": OAUTH_CLIENT_ID, "code_verifier": verifier})
        user = ""
        with self.lock:
            self._store(site, j)
            self.ep_cache.setdefault(site, ep)
            try:
                req = urllib.request.Request(ep["userinfo"], headers={"User-Agent": UA, "Authorization": "Bearer " + j["access_token"]})
                with urllib.request.urlopen(req, timeout=30) as r:
                    info = json.loads(r.read().decode("utf-8"))
                user = info.get("preferred_username") or info.get("username") or info.get("name") or ""
            except Exception:  # noqa
                pass
            self.sites[site]["user"] = user
            self.save()
        return user

    def _refresh(self, site):
        d = self.sites[site]
        j = _post_form(self.endpoints(site)["token"], {"grant_type": "refresh_token", "refresh_token": d["refresh"],
                                                         "client_id": OAUTH_CLIENT_ID})
        self._store(site, j)

    def _ensure(self, site):
        d = self.sites[site]
        if not d.get("access") or time.time() > d["exp"] - 300:
            self._refresh(site)
        self.issued[d["access"]] = site
        return d["access"]

    # ---- one run
    def begin_run(self, urls, apikey, log):
        """Chooses the credentials of the run. Returns the token string that the rest of the program passes around."""
        with self.lock:
            self.running = True
            self.counts = {"oauth": 0, "apikey": 0, "none": 0}
            self.denied = []
            hosts = [h for h in (site_of(u) for u in urls) if h]
            site = next((h for h in hosts if h in self.sites), None)
            cross = None
            if site is None and self.sites:  # signed in on the other Civitai site: it is the same account - try it and log the result
                site = next(iter(self.sites))
                cross = hosts[0] if hosts else None
            if site:
                try:
                    token = self._ensure(site)
                    self.kind = "oauth"
                    # the Civitai user name is deliberately not written to the log (logs get posted in bug reports)
                    log("Credentials: Sign in with Civitai (on %s)%s. The API token is NOT used%s." % (
                        site, (", used for %s links - the same account; the summary below shows whether it was accepted" % cross)
                        if cross and cross != site else "", " (a token is saved but ignored)" if apikey else ""))
                    return token
                except Exception as e:  # noqa
                    log("Credentials: the sign-in could not be renewed (%s) - please sign in again; using the API token" % e)
            self.kind = "apikey" if apikey else "none"
            log("Credentials: %s" % ("API token" if apikey else "none (no API token, not signed in) - some data may be unavailable"))
            return apikey

    def peek(self, url, apikey):
        """The token for a request made outside a run (the link check): the sign-in of that site (or the other one - it is
        the same account), else the API token. Touches no run counters."""
        with self.lock:
            host = site_of(url)
            site = host if host in self.sites else next(iter(self.sites), None)
            if site:
                try:
                    return self._ensure(site)
                except Exception as e:  # noqa
                    file_log("check: the sign-in could not be renewed: %r" % (e,))
        return apikey

    def fresh(self, token):
        """Called for every request: swaps an OAuth token for the current one (it lives one hour) and counts the use."""
        with self.lock:
            site = self.issued.get(token) if token else None
            if site is None or site not in self.sites:
                if self.running:
                    self.counts["apikey" if token else "none"] += 1
                return token
            d = self.sites[site]
            if time.time() > d["exp"] - 300:
                try:
                    self._refresh(site)
                except Exception as e:  # noqa
                    file_log("OAuth refresh failed: %r" % (e,))
            if self.running:
                self.counts["oauth"] += 1
            return d["access"] or token

    def tag(self):
        return {"oauth": " [OAuth]", "apikey": " [API token]"}.get(self.kind, "") if self.running else ""

    def note_error(self, code, url):
        if self.running and self.kind == "oauth" and code in (401, 403):
            self.denied.append("HTTP %s  %s" % (code, urllib.parse.urlsplit(str(url)).path[:80]))

    def end_run(self, log):
        with self.lock:
            if not self.running:
                return
            c = self.counts
            log("Credentials used: OAuth %d request(s), API token %d, public files without credentials %d" % (c["oauth"], c["apikey"], c["none"]))
            if self.kind == "oauth":
                if self.denied:
                    log("Refused although signed in (HTTP 401/403): %d" % len(self.denied))
                    for line in self.denied[:8]:
                        log("   " + line)
                else:
                    log("The sign-in was enough: no request was refused for lack of rights.")
            self.running = False


AUTH = Auth()


# ---- failure diagnostics: a short assessment of WHY a request failed (a passing problem or a changed service?); log only
DIAG = {"active": False, "seen": set(), "probed": set(), "fmt": set()}
DIAG_TEXT = {  # class -> (what it means, is a probe of the network useful)
    "dns": ("name lookup (DNS) failed", True),
    "timeout": ("no answer in time", True),
    "reset": ("the connection was closed by the other side or by something on the way", True),
    "refused": ("the connection was refused", True),
    "tls": ("secure connection (TLS / certificate) problem", True),
    "unreachable": ("network or host unreachable", True),
    "dropped": ("the download was interrupted before the end", True),
    "server": ("server error", True),
    "rate_limit": ("too many requests (rate limit)", False),
    "cloudflare": ("a Cloudflare check page came instead of the data", False),
    "auth": ("access denied (sign-in, rights, paid or early-access content)", False),
    "not_found": ("not found (removed, hidden or a wrong address)", False),
    "bad_request": ("the server did not accept the request", False),
    "not_json": ("the answer is not JSON (a web page or an error page?)", False),
    "html_instead_of_file": ("a web page came instead of the file", False),
    "format": ("the answer has another structure than expected", False),
    "other": ("unclassified error", True),
}


def diag_reset():
    DIAG["seen"].clear()
    DIAG["probed"].clear()
    DIAG["fmt"].clear()


def diag_layer(url):
    """Which part of the service a request belongs to: api / page / files (storage and image servers)."""
    try:
        u = urllib.parse.urlparse(str(url))
    except ValueError:
        return "request"
    host = (u.hostname or "").lower()
    if "/api/download/" in u.path:
        return "files"
    if "/api/" in u.path:
        return "api"
    if host and host.split(".", 1)[0] not in ("civitai", "www") and not re.fullmatch(r"(www\.)?civitai\.(com|red)", host):
        return "files"
    return "page"


def classify_error(exc, body=b""):
    """-> {cls, detail}. Pure function: the exception (and, for an HTTP error, the start of the answer) decide."""
    import ssl
    code = exc.code if isinstance(exc, urllib.error.HTTPError) else None
    if code is not None:
        hdr = exc.headers if exc.headers is not None else {}
        low = (body or b"")[:4000].lower()
        server = str(hdr.get("Server") or "").lower()
        retry = str(hdr.get("Retry-After") or "")
        cf = (str(hdr.get("cf-mitigated") or "").lower() == "challenge" or b"just a moment" in low or b"cf-chl" in low
              or b"challenge-platform" in low or ("cloudflare" in server and code in (403, 429, 503) and b"<html" in low))
        if code == 429:
            return {"cls": "rate_limit", "detail": "HTTP 429" + (", Retry-After %s" % retry if retry else "")}
        if cf:
            return {"cls": "cloudflare", "detail": "HTTP %s" % code}
        if code in (401, 403):
            return {"cls": "auth", "detail": "HTTP %s" % code}
        if code in (404, 410):
            return {"cls": "not_found", "detail": "HTTP %s" % code}
        if code in (400, 422):
            return {"cls": "bad_request", "detail": "HTTP %s" % code}
        if code >= 500:
            more = ", maintenance?" if (code == 503 and (retry or b"maintenance" in low)) else ""
            return {"cls": "server", "detail": "HTTP %s%s%s" % (code, ", Retry-After %s" % retry if retry else "", more)}
        return {"cls": "other", "detail": "HTTP %s" % code}
    inner = exc
    for _ in range(4):  # URLError wraps the real error in .reason
        r = getattr(inner, "reason", None) if isinstance(inner, urllib.error.URLError) else None
        if isinstance(r, BaseException):
            inner = r
        else:
            break
    text = str(inner)
    win = getattr(inner, "winerror", None)
    if isinstance(exc, json.JSONDecodeError) or isinstance(inner, json.JSONDecodeError):
        return {"cls": "not_json", "detail": "invalid JSON"}
    if isinstance(inner, socket.gaierror) or win == 11001:
        return {"cls": "dns", "detail": text[:80]}
    if isinstance(inner, (socket.timeout, TimeoutError)) or win == 10060 or "timed out" in text:
        return {"cls": "timeout", "detail": "timed out"}
    if isinstance(inner, (ssl.SSLError, getattr(ssl, "CertificateError", ssl.SSLError))) or "CERTIFICATE_VERIFY_FAILED" in text:
        return {"cls": "tls", "detail": text[:80]}
    if isinstance(inner, ConnectionRefusedError) or win == 10061:
        return {"cls": "refused", "detail": "refused"}
    if isinstance(inner, (ConnectionResetError, ConnectionAbortedError, http.client.RemoteDisconnected)) or win in (10054, 10053) \
            or "forcibly closed" in text or "Connection reset" in text:
        return {"cls": "reset", "detail": ("WinError %s" % win) if win else type(inner).__name__}
    if isinstance(inner, (http.client.IncompleteRead, http.client.BadStatusLine)) or "connection dropped" in text:
        return {"cls": "dropped", "detail": type(inner).__name__}
    if win in (10051, 10065) or getattr(inner, "errno", None) in (101, 113):
        return {"cls": "unreachable", "detail": "WinError %s" % win if win else "unreachable"}
    return {"cls": "other", "detail": "%s: %s" % (type(inner).__name__, text[:80])}


def diag_tcp(host, port, timeout=4):
    """A bare TCP connection (no HTTP): -> (ok, reason)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except OSError as e:
        return False, classify_error(e)["cls"]


def diag_http(url, timeout=6):
    """One light request to the same host: -> (status or None, reason). Any answer, even 403/404, means the server is alive."""
    try:
        u = urllib.parse.urlparse(url)
        probe = "%s://%s/" % (u.scheme or "https", u.netloc)
        req = urllib.request.Request(probe, headers={"User-Agent": UA}, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return getattr(r, "status", 200), ""
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa
        return None, classify_error(e)["cls"]


def diag_probe(url, cls=""):
    """The network around the failure: -> (facts, verdict). Run once per layer per task. A bare request to a storage or image host
    proves nothing (they answer it badly), so the main site of the task is the yardstick for "is the service alive"."""
    u = urllib.parse.urlparse(str(url))
    host = u.hostname or ""
    port = u.port or (80 if u.scheme == "http" else 443)
    site = DIAG.get("site") or u.netloc
    net = diag_tcp("1.1.1.1", 443)[0] or diag_tcp("8.8.8.8", 53)[0]
    tcp = diag_tcp(host, port)
    status, why = diag_http("%s://%s/" % (u.scheme or "https", site))
    site_name = urllib.parse.urlparse("//" + site).hostname or site
    facts = "internet %s; %s tcp %s; %s http %s" % ("ok" if net else "NO", host, "ok" if tcp[0] else "NO (%s)" % tcp[1], site_name,
                                                    status if status else "none (%s)" % why)
    if not net:
        verdict = "the internet connection looks down - not a problem of the service"
    elif not tcp[0]:
        verdict = "the internet works but this host cannot be reached (network, a block, or the service is down)"
    elif status is not None and status >= 500:
        verdict = "the service answers with errors - an outage or maintenance; try later"
    elif status is None and why == "timeout":
        verdict = "the host accepts connections but does not answer a simple request - overloaded or throttling; try later"
    elif status is None and why == "reset":
        verdict = "even a simple request is cut - the service is overloaded or something on the way cuts connections (filter, VPN, antivirus)"
    elif cls in ("reset", "timeout", "dropped"):
        verdict = "the connection to the host works, but this transfer was cut - short hiccups of the file/image servers, server limits or a filter on the way; it usually passes"
    else:
        verdict = "the service answers normally - this request failed for its own reason"
    return facts, verdict


def diag_say(cls, layer, text, verdict="", final=False):
    msg = "DIAG: %s | %s | %s%s" % (cls, layer, text, (" | " + verdict) if verdict else "")
    file_log(msg)
    if DIAG["active"]:
        (STATE.get("log") or (lambda m: None))("  " + msg)


def diag_event(exc, url, final=False):
    """Called where a request failed. Prints one DIAG line for the first failure of a kind per task and a short one when the
    request finally fails; never raises."""
    try:
        body = b""
        if isinstance(exc, urllib.error.HTTPError):
            try:
                body = exc.read(4096)
            except Exception:  # noqa
                pass
        if getattr(exc, "_diag_done", False) and not final:
            return None
        info = classify_error(exc, body)
        layer = diag_layer(url)
        key = (info["cls"], layer)
        try:
            exc._diag_done = True
        except Exception:  # noqa
            pass
        first = key not in DIAG["seen"]
        DIAG["seen"].add(key)
        if not DIAG["active"] or not (first or final):
            return info
        what, probe = DIAG_TEXT.get(info["cls"], DIAG_TEXT["other"])
        text = "%s (%s)" % (what, info["detail"])
        verdict = ""
        if first and probe and layer not in DIAG["probed"]:
            DIAG["probed"].add(layer)
            facts, verdict = diag_probe(url, info["cls"])
            text += "; " + facts
        elif not first:
            text += "; again"
        diag_say(info["cls"], layer, text, verdict)
        return info
    except Exception:  # noqa
        return None


# what the Civitai API is expected to contain (checked after every model / version request; a missing key is reported once per task)
API_EXPECTED = {
    "model": (("id", "name", "type", "modelVersions"), "modelVersions", ("id", "name")),
    "version": (("id", "name", "files", "images", "modelId"), "files", ("name", "downloadUrl")),
}


def diag_format(data, kind, url=""):
    try:
        top, sub, subkeys = API_EXPECTED[kind]
        if not isinstance(data, dict):
            missing = ["(the answer is not an object)"]
        else:
            missing = [k for k in top if k not in data]
            items = data.get(sub)
            if isinstance(items, list) and items and isinstance(items[0], dict):
                missing += ["%s[].%s" % (sub, k) for k in subkeys if k not in items[0]]
        if not missing:
            return
        key = (kind, tuple(missing))
        if key in DIAG["fmt"]:
            return
        DIAG["fmt"].add(key)
        have = ", ".join(sorted(data.keys())[:25]) if isinstance(data, dict) else type(data).__name__
        diag_say("format", diag_layer(url) if url else "api", "%s: missing %s; the answer has: %s" % (kind, ", ".join(missing), have),
                 "the Civitai API may have changed - the program may not work correctly; tell the author")
    except Exception:  # noqa
        pass


def http_get(url, token=None, timeout=60, retries=3):
    token = AUTH.fresh(token)
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
            again = e.code in (429, 500, 502, 503, 504) and attempt < retries - 1
            diag_event(e, url, final=not again)
            if again:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            last = e
            diag_event(e, url, final=attempt >= retries - 1)
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
            self._send(200, json.dumps({"app": "civitai-grabber", "version": VERSION, "launcher": BRIDGE.launcher, "dark": BRIDGE.dark}).encode())
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
        self.dark = False  # the extension window is drawn dark (a setting of its own; told to the extension in the ping answer)
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
            STATE["page_route"] = "browser bridge (%s)" % (r.get("via") or "?")
            return r["text"]
        raise urllib.error.HTTPError(url, int(r.get("status") or 502), "via browser", None, None)
    return _fetch_page_direct(url, token)


def _fetch_page_direct(url, token=None):
    """Open an HTML page with browser-like headers. First without the API token, then with it."""
    token = AUTH.fresh(token)
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


def _png_rgba(w, h, rows):
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def chain_icon_png(linked, k=1.0, dark=False):
    """The 'link' icon: two rings; joined by a bar when linked, apart and paler when not. Drawn here (no image files),
    anti-aliased by supersampling. k scales it for high-resolution screens."""
    W, H, ss = int(round(30 * k)), int(round(16 * k)), 4
    color = ((60, 60, 60) if linked else (150, 150, 150)) if not dark else ((225, 225, 225) if linked else (120, 120, 120))

    def inside(x, y):
        x, y = x / k, y / k
        for cx in (8.0, 22.0):
            d2 = (x - cx) ** 2 + (y - 8.0) ** 2
            if 4.1 ** 2 <= d2 <= 6.0 ** 2:
                return True
        return linked and 8.0 <= x <= 22.0 and 7.05 <= y <= 8.95

    rows = []
    for y in range(H):
        row = bytearray()
        for x in range(W):
            n = sum(1 for sy in range(ss) for sx in range(ss) if inside(x + (sx + 0.5) / ss, y + (sy + 0.5) / ss))
            row += bytes((color[0], color[1], color[2], int(255 * n / (ss * ss))))
        rows.append(bytes(row))
    return _png_rgba(W, H, rows)



def gear_icon_png(k=1.0, dark=False):
    """The Setup gear: a ring with 8 teeth and a hole, drawn here (no font, no image file), anti-aliased by supersampling.
    Design box 24 x 24; k scales it for high-resolution screens."""
    import math
    N, ss = int(round(24 * k)), 4
    color = (225, 225, 225) if dark else (60, 60, 60)
    teeth = [(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in range(0, 360, 45)]

    def inside(x, y):
        x, y = x / k - 12.0, y / k - 12.0
        r2 = x * x + y * y
        if r2 <= 3.4 ** 2:
            return False  # the hole
        if r2 <= 7.6 ** 2:
            return True  # the body
        for c, s_ in teeth:
            along, perp = x * c + y * s_, -x * s_ + y * c
            if 0.0 <= along <= 10.8 and abs(perp) <= 2.1:
                return True
        return False

    rows = []
    for y in range(N):
        row = bytearray()
        for x in range(N):
            n = sum(1 for sy in range(ss) for sx in range(ss) if inside(x + (sx + 0.5) / ss, y + (sy + 0.5) / ss))
            row += bytes((color[0], color[1], color[2], int(255 * n / (ss * ss))))
        rows.append(bytes(row))
    return _png_rgba(N, N, rows)


def get_json(url, token=None):
    return json.loads(http_get(url, token).decode("utf-8"))



# ---- which model does a folder belong to? (a hidden marker file; old folders: the description file)
MARKER = ".civitai-model.json"


def _head(path, n=12000):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(n)
    except OSError:
        return ""


def dscr_owner(path):
    """The model id named in a description file written by this program (Model ID line, else the Page address), or None."""
    head = _head(path)
    if not re.search(r"^(?:- \*\*)?File:", head, re.M):
        return None
    m = (re.search(r"^(?:- \*\*)?Model ID:(?:\*\*)?\s*(\d+)", head, re.M)
         or re.search(r"^(?:- \*\*)?Page:(?:\*\*)?\s*\S*/models/(\d+)", head, re.M))
    return m.group(1) if m else None


def folder_model_ids(folder):
    """Ids of the models a folder is known to hold: the marker file, else the description files in it. Empty set = unknown."""
    ids = set()
    try:
        with open(os.path.join(folder, MARKER), encoding="utf-8") as f:
            data = json.load(f)
        ids.add(str(data.get("modelId")))
        ids.update(str(x.get("modelId")) for x in data.get("others", []) if isinstance(x, dict))
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    ids.discard("None")
    if ids:
        return ids
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return ids
    for n in names:
        if n.lower().endswith((".txt", ".md")):
            owner = dscr_owner(os.path.join(folder, n))
            if owner:
                ids.add(owner)
    return ids


def write_marker(folder, model_id, vid, name, url):
    """A small hidden file in the model folder: which model (and versions) it holds. Another model in the same folder is added to 'others'."""
    path = os.path.join(folder, MARKER)
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    mid = str(model_id)
    if data.get("modelId") in (None, mid):
        data["modelId"] = mid
        data["name"], data["page"] = name, url
        data["versionIds"] = sorted({str(x) for x in data.get("versionIds", [])} | {str(vid)})
    else:
        others = [o for o in data.get("others", []) if isinstance(o, dict)]
        rec = next((o for o in others if str(o.get("modelId")) == mid), None)
        if rec is None:
            rec = {"modelId": mid, "name": name, "page": url, "versionIds": []}
            others.append(rec)
        rec["versionIds"] = sorted({str(x) for x in rec.get("versionIds", [])} | {str(vid)})
        data["others"] = others
    try:
        if os.path.exists(path) and sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(path, 0)  # a hidden file cannot be opened for writing
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(path, 2)  # hidden
    except (OSError, AttributeError, ValueError):
        pass


# ---- link check: can this model be downloaded right now? (asked when a link is added to the list)
MODEL_LINK = re.compile(r"/models/(\d+)")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # a 3xx answer is reported as it is: we only want to know where the server sends us


def probe_download(url, token):
    """One-byte request to the file address (never reads the file). Returns (http code, note for the log).
    The token goes into ?token= like in the real download. A redirect to file storage means 'allowed'."""
    tok = AUTH.fresh(token)
    full = url + ("&" if "?" in url else "?") + "token=" + urllib.parse.quote(tok) if tok else url
    req = urllib.request.Request(full, headers={"User-Agent": UA, "Range": "bytes=0-0"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=20) as r:
            return getattr(r, "status", 200), "content-type=%s" % (r.headers.get("Content-Type") or "?")
    except urllib.error.HTTPError as e:
        loc = (e.headers.get("Location") if e.headers else "") or ""
        try:
            body = e.read(200).decode("utf-8", "replace").replace("\n", " ")
        except Exception:  # noqa
            body = ""
        note = "answer %s" % e.code
        if loc:
            note += ", sends to %s" % (urllib.parse.urlsplit(loc).netloc or loc[:40])
        if body:
            note += ", text: %r" % body[:120]
        return e.code, note + ("|" + loc if loc else "")


def _parse_utc(text):
    try:
        return datetime.datetime.strptime(str(text)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


KEPT_LINKS = set()   # links the user chose to keep in the link-check window: the run only warns about them


def access_state(ver, token, url=""):
    """Is this model version paid or in early access - and does THIS account have the access anyway?
    paidAccess does not say who bought it, so the file address is asked with a one-byte request (only for such versions).
    Returns {"kind": ok | paid | early, "text", "probe"}."""
    res = {"kind": "ok", "text": "", "probe": ""}
    pa = ver.get("paidAccess")
    if not pa:
        return res
    ends = _parse_utc(pa.get("endsAt")) if isinstance(pa, dict) else None
    now = datetime.datetime.now(datetime.timezone.utc)
    if isinstance(pa, dict) and not pa.get("permanent") and ends and ends <= now:
        return res  # early access is over
    if isinstance(pa, dict) and not pa.get("permanent") and ends:
        left = ends - now
        res["kind"] = "early"
        res["text"] = "Early access until %s UTC (in %d d %d h): it can be downloaded only after buying it, or when the period ends." % (
            ends.strftime("%Y-%m-%d %H:%M"), left.days, left.seconds // 3600)
    else:
        res["kind"] = "paid"
        res["text"] = "Paid model: the access has to be bought on Civitai."
    dl = ver.get("downloadUrl") or ""
    if dl:
        try:
            code, note = probe_download(dl, token)
        except Exception as e:  # noqa
            code, note = 0, "%s: %s" % (type(e).__name__, e)
        loc = note.split("|", 1)[1] if "|" in note else ""
        note = note.split("|", 1)[0]
        res["probe"] = "test request to the file address: %s" % note
        file_log("access check %s: %s" % (url or dl, res["probe"]))
        # allowed = the file itself, or a redirect to file storage (an absolute address outside Civitai).
        # A redirect to a Civitai page (/model-versions/ID, a login or purchase page) means "no access".
        page_hosts = ("civitai.com", "www.civitai.com", "civitai.red", "www.civitai.red")  # Civitai pages; b2.civitai.com and the like are storage
        to_storage = (code in (301, 302, 303, 307, 308) and loc.lower().startswith(("http://", "https://"))
                      and (urllib.parse.urlsplit(loc).hostname or "").lower() not in page_hosts)
        if code in (200, 206) or to_storage:
            res.update(kind="ok", text="Paid, but this account has access (a test request to the file address was accepted).")
        elif code not in (301, 302, 303, 307, 308, 401, 402, 403):
            res["text"] += " (Not confirmed: the test request answered %s.)" % (code or "no answer")
    return res


def check_availability(url, apikey):
    """Asks Civitai whether the model link can be downloaded now (one or two small requests; a test request to the file only
    for paid / early-access versions). Returns {"kind", "text", "name", "ver", "probe"}; kind is one of:
    skip (not a model link) / ok / paid / early / notfound / denied / unpublished / error (no answer - the check is silent)."""
    out = {"kind": "skip", "text": "", "name": "", "ver": "", "probe": ""}
    p = urllib.parse.urlparse(url)
    mm = MODEL_LINK.search(p.path)
    if not mm:
        return out
    host = p.netloc
    token = AUTH.peek(url, apikey)
    vid = urllib.parse.parse_qs(p.query).get("modelVersionId", [None])[0]
    out["model_id"] = mm.group(1)

    def get(u):
        return json.loads(http_get(u, token, timeout=25, retries=2).decode("utf-8"))

    try:
        if not vid:
            model = get("%s://%s/api/v1/models/%s" % (SCHEME, host, mm.group(1)))
            versions = model.get("modelVersions") or []
            if not versions:
                out.update(kind="unpublished", text="The model has no published versions.")
                return out
            vid = versions[0]["id"]
            out["name"] = model.get("name") or ""
        ver = get("%s://%s/api/v1/model-versions/%s" % (SCHEME, host, vid))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            out.update(kind="notfound", text="Not found on %s: the model or version was deleted or is hidden - or it was published a moment ago and the API does not know it yet (check again in a minute)." % host)
        elif e.code in (401, 403):
            out.update(kind="denied", text="Civitai refused access (HTTP %s): sign in, or the model is restricted." % e.code)
        else:
            out.update(kind="error", text="HTTP %s" % e.code)
        return out
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError, KeyError, IndexError, TypeError) as e:
        out.update(kind="error", text="%s: %s" % (type(e).__name__, e))
        return out

    out["name"] = out["name"] or (ver.get("model") or {}).get("name") or ""
    out["mtype"] = str((ver.get("model") or {}).get("type") or "")
    out["ver"] = ver.get("name") or ""
    out["vid"] = ver.get("id") or vid
    vfiles = ver.get("files") or []
    prim = next((f for f in vfiles if f.get("primary")), None) or next(
        (f for f in vfiles if str(f.get("name", "")).lower().endswith(".safetensors")), None) or (vfiles[0] if vfiles else None)
    out["primary"] = (prim or {}).get("name") or ""
    status = ver.get("status")
    if status and status != "Published":
        out.update(kind="unpublished", text="This version is not published (status: %s)." % status)
        return out
    out["kind"] = "ok"
    out.update(access_state(ver, token, url))
    return out


MODEL_TYPE_NAMES = {"lora": "LoRA", "locon": "LyCORIS", "dora": "DoRA", "textualinversion": "Embedding", "aestheticgradient": "Aesthetic",
                    "motionmodule": "Motion", "controlnet": "Controlnet", "checkpoint": "Checkpoint", "hypernetwork": "Hypernetwork",
                    "vae": "VAE", "upscaler": "Upscaler", "poses": "Poses", "wildcards": "Wildcards", "workflows": "Workflows",
                    "detection": "Detection", "other": "Other", "textencoder": "Text Encoder", "unet": "UNet", "clipvision": "CLIP Vision",
                    "comfyuiworkflows": "ComfyUI WF", "vlm": "VLM", "clip": "CLIP", "llm": "LLM"}


def model_type_label(t):
    """The type of a model as the Status column shows it: Civitai's own name, a few spelled the way the site spells them."""
    t = str(t or "").strip()
    if not t:
        return ""
    return MODEL_TYPE_NAMES.get(re.sub(r"[^a-z0-9]", "", t.lower()), re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t))


def check_link(url, apikey, extra=None):
    """The whole check of one link: is it available (Civitai), and is it already downloaded / does its folder exist (disk).
    extra = the current window settings (PATH, PREFIX, MODEL, EXISTING, RENAME_ID)."""
    res = check_availability(url, apikey)
    if res.get("kind") != "ok" or not extra or not res.get("name"):
        return res
    try:
        folder_note = local_check(res, extra)
    except OSError as e:
        file_log("local check failed: %r" % (e,))
        return res
    res.update(folder_note or {})
    return res


def resolve_model_folder(path, name, model_id):
    """Where a model goes: <path>/<name>. If that folder holds ANOTHER (or an unknown) model, the model goes into
    a new folder "<name> (<model id>)". Returns a dict: folder (the one to use), base, alt, base_state, alt_state,
    ids (models known in the base folder). A state is free (no folder / empty), same (holds this model),
    other (holds another model) or unknown (has files, nobody knows whose)."""
    base = os.path.join(path, safe_name(name))
    mid = str(model_id or "")

    def state(f):
        if not os.path.isdir(f) or not [n for n in os.listdir(f) if n != MARKER]:
            return "free", set()
        ids = folder_model_ids(f)
        if ids and mid in ids:
            return "same", ids
        return ("other" if ids else "unknown"), ids

    bst, ids = state(base)
    out = {"folder": base, "base": base, "alt": None, "base_state": bst, "alt_state": None, "ids": ids}
    if bst in ("other", "unknown") and mid:
        alt = "%s (%s)" % (base, mid)
        out.update(folder=alt, alt=alt, alt_state=state(alt)[0])
    return out


def local_check(res, extra):
    path = (extra.get("PATH") or "").strip()
    if not path:
        return None
    r = resolve_model_folder(path, res["name"], res.get("model_id"))
    folder = r["folder"]
    if r["alt"]:
        if r["alt_state"] == "free":  # the usual case: say so once, the model goes into a new folder
            if r["base_state"] == "other":
                why = "A folder with this name already exists, but it holds another model (id %s):" % ", ".join(sorted(r["ids"]))
            else:
                why = "A folder with this name already exists and has files in it; it is not known which model it holds:"
            return {"kind": "folder", "text": "%s\n%s\n\nThis model will be saved into a new folder:\n%s" % (why, r["base"], r["alt"])}
        if r["alt_state"] in ("other", "unknown"):  # even the new name is taken by something else
            return {"kind": "folder", "text": "A folder with this name already exists, and the new-folder name is taken as well:\n%s\n"
                                              "It holds another model or an unknown one." % r["alt"]}
    state = r["alt_state"] if r["alt"] else r["base_state"]
    if state == "free":
        # nothing in the folder this link is going to, but the history may remember the same version in ANOTHER folder
        rec = history_find("model:%s" % res.get("vid"))
        if rec and not rec.get("note") and flag(extra, "MODEL") and str(extra.get("EXISTING", "ask")).lower() != "overwrite":
            old = rec.get("folder") or ""
            if old and os.path.isdir(old) and _norm(old) != _norm(folder):
                return {"kind": "downloaded", "text": "This version was downloaded earlier (%s) into another folder:\n%s" % (rec["time"][:16], old)}
        return None
    if flag(extra, "MODEL") and str(extra.get("EXISTING", "ask")).lower() != "overwrite" and res.get("primary"):
        orig = safe_name(res["primary"], 200)
        pre = extra.get("PREFIX", "")
        names = {pre + orig}
        if flag(extra, "RENAME_ID"):
            for several in (False, True):
                nice = readable_file_name(orig, res["name"], res.get("ver"), several)
                if nice:
                    names.add(pre + nice)
        found = None
        for n in names:
            fp = os.path.join(folder, n)
            if os.path.exists(fp) and os.path.getsize(fp) > 0:
                found = fp
                break
        if not found:  # the same file saved earlier under another prefix (older versions, another prefix setting)
            try:
                for n in sorted(os.listdir(folder)):
                    fp = os.path.join(folder, n)
                    if n.endswith(orig) and os.path.isfile(fp) and os.path.getsize(fp) > 0:
                        found = fp
                        break
            except OSError:
                pass
        if found:
            rec = history_find("model:%s" % res.get("vid"))
            when = (" on %s" % rec["time"][:16]) if rec else ""
            return {"kind": "downloaded", "text": "This version is already downloaded%s:\n%s" % (when, found)}
    return None


class LinkChecker:
    """Watches the link list: every model link that stays unchanged for a moment is checked in a background thread.
    Links with a problem are handed out in batches for one dialog; START stays locked while anything is unsettled."""
    STABLE = 0.6        # seconds a new line must stay unchanged (typing or pasting may still be going on)
    BATCH_WAIT = 0.3    # seconds after the last problem when nothing else is being checked
    BATCH_MAX = 6.0

    def __init__(self, check_fn=None, log=None, notify=None):
        self.check_fn = check_fn or check_link
        self.log = log or (lambda m: None)
        self.notify = notify or (lambda *a: None)
        self.state = {}       # link -> queued / ok / problem / kept
        self.kinds = {}       # link -> kind of the problem it was given
        self.titles = {}      # link -> "Model name - version" (shown in the table)
        self.types = {}       # link -> the type of the model as Civitai names it (LORA, Checkpoint...), shown in the Status column
        self.seen = {}        # link -> when it appeared
        self.problems = []    # [(link, result)] waiting for the dialog
        self.last_problem = 0.0
        self.q_in, self.q_out = queue.Queue(), queue.Queue()
        self.thread = None

    def _worker(self):
        while True:
            u, apikey, extra = self.q_in.get()
            try:
                res = self.check_fn(u, apikey, extra)
            except Exception as e:  # noqa
                res = {"kind": "error", "text": "%s: %s" % (type(e).__name__, e), "name": "", "ver": "", "probe": ""}
            self.q_out.put((u, res))
            if not self.q_in.empty():
                time.sleep(0.4)  # a gentle pace only when several links are waiting

    def tick(self, links, apikey, extra_fn=None, now=None):
        """Call often from the window thread. Returns a batch [(link, result)] to show in the dialog, or None."""
        now = time.time() if now is None else now
        live = set(links)
        for d in (self.state, self.seen, self.kinds, self.titles, self.types):
            for u in [u for u in d if u not in live]:
                del d[u]
        self.problems = [(u, r) for (u, r) in self.problems if u in live]
        for u in links:
            if u in self.state:
                continue
            if not MODEL_LINK.search(u):
                self.state[u] = "ok"  # image links need no check
                continue
            if now - self.seen.setdefault(u, now) < self.STABLE:
                continue
            self.state[u] = "queued"
            if self.thread is None:
                self.thread = threading.Thread(target=self._worker, daemon=True)
                self.thread.start()
            self.q_in.put((u, apikey, extra_fn(u) if extra_fn else None))
        while True:
            try:
                u, res = self.q_out.get_nowait()
            except queue.Empty:
                break
            if self.state.get(u) != "queued":
                continue  # the link left the list meanwhile
            kind = res.get("kind")
            label = (res.get("name") or "model") + ((" (version: %s)" % res["ver"]) if res.get("ver") else "")
            if res.get("name"):
                self.titles[u] = res["name"] + ((" - " + res["ver"]) if res.get("ver") else "")
            if res.get("mtype"):
                self.types[u] = res["mtype"]
            if kind == "error":
                self.state[u] = "ok"
                self.log("Link check: could not check %s - %s. The link stays in the list." % (label, res.get("text")))
            elif kind in ("ok", "skip"):
                self.state[u] = "ok"
                self.log("Link check: %s - available%s" % (label, (" (" + res["text"] + ")") if res.get("text") else ""))
            else:
                self.state[u] = "problem"
                self.kinds[u] = kind
                self.log("Link check: %s - %s" % (label, res.get("text")))
                self.problems.append((u, res))
                self.last_problem = now
                self.notify("attention", u, (res.get("text") or "")[:90] + " Waiting for your decision in the grabber.")
            if res.get("probe"):
                self.log("   " + res["probe"])
        if self.problems:
            busy = any(s == "queued" for s in self.state.values())
            if (not busy and now - self.last_problem >= self.BATCH_WAIT) or now - self.last_problem >= self.BATCH_MAX:
                rows, self.problems = self.problems, []
                return rows
        return None

    def trust(self, links):
        """Links that arrive complete (from the browser extension) need no waiting for the typing to finish."""
        for u in links:
            self.seen[u] = 0

    def warned(self, links):
        """Links in the list that carry a warning (waiting for the answer, or kept after it)."""
        return sum(1 for u in links if self.state.get(u) in ("problem", "kept"))

    def settle(self, removed, kept):
        for u in kept:
            self.state[u] = "kept"
        for u in removed:
            self.state.pop(u, None)
            self.seen.pop(u, None)
            self.kinds.pop(u, None)

    def unsettled(self, links):
        return sum(1 for u in links if MODEL_LINK.search(u) and self.state.get(u) in (None, "queued", "problem"))

    def recheck_kept(self, links):
        """START: a link the user chose to keep is asked about again (nothing is remembered about 'keep')."""
        n = 0
        for u in links:
            if self.state.get(u) == "kept" and self.kinds.get(u) not in ("downloaded", "folder"):  # these answers stand
                del self.state[u]
                self.seen[u] = 0
                n += 1
        return n


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


def ensure_dir(path):
    """os.makedirs that remembers which folders this run has created (to offer removing them if they stay empty)."""
    path = os.path.normpath(path)
    new, p = [], path
    while p and not os.path.isdir(p):
        new.append(p)
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    os.makedirs(path, exist_ok=True)
    for d in new:
        if d not in STATE["made_dirs"]:
            STATE["made_dirs"].append(d)


def cleanup_after_run(log):
    """At the end of a run: folders this run created and left empty are removed without asking (nothing is lost);
    incomplete (.part) files are offered for deletion - together with the folders that would be empty without them."""
    emptied = 0
    for d in sorted(set(STATE["made_dirs"]), key=len, reverse=True):  # the deepest first: a parent may become empty
        try:
            if not os.listdir(d):
                os.rmdir(d)
                emptied += 1
        except OSError:
            continue
    if emptied:
        log("Removed %d empty folder(s) created by this run." % emptied)
    parts = sorted(p for p in STATE["parts"] if os.path.exists(p))
    gone = set(parts)
    dirs = []
    for d in sorted(set(STATE["made_dirs"]), key=len, reverse=True):
        try:
            items = os.listdir(d)
        except OSError:
            continue
        if items and all(os.path.join(d, x) in gone for x in items):
            dirs.append(d)
            gone.add(d)
    if not parts:
        return

    def short(path):
        return "\\".join(path.replace("/", "\\").split("\\")[-3:])
    lines = ["The run left incomplete files:", ""]
    for pth in parts[:6]:
        lines.append("   %s  (%.1f MB)" % (short(pth), os.path.getsize(pth) / 1048576))
    if len(parts) > 6:
        lines.append("   ... and %d more" % (len(parts) - 6))
    if dirs:
        lines += ["", "%d folder(s) created by this run would stay empty without them." % len(dirs)]
    lines += ["", "Delete them? (An incomplete file can be resumed by downloading the same link again.)"]
    fn = ASK_CLEANUP["fn"]
    if not fn:
        log("Leftovers: %d incomplete file(s) - not removed" % len(parts))
        return
    if not fn("\n".join(lines), "Delete", "Keep the files"):
        log("Leftovers kept: %d incomplete file(s)" % len(parts))
        return
    for pth in parts:
        try:
            os.remove(pth)
        except OSError as e:
            log("  could not delete %s: %s" % (pth, e))
    for d in dirs:
        try:
            os.rmdir(d)
        except OSError as e:
            log("  could not remove %s: %s" % (d, e))
    STATE["parts"].clear()
    log("Deleted: %d incomplete file(s), %d empty folder(s)" % (len(parts), len(dirs)))


def safe_cleanup(log):
    try:
        cleanup_after_run(log)
    except Exception as e:  # noqa
        file_log("cleanup error: %r" % (e,))
    AUTH.end_run(log)


def download_file(url, dest, log, stop, token=None, attempts=5, auto_ext=False, name_ext=""):
    """Download into .part with retries and resume after a dropped connection.
    auto_ext=True: dest is a path WITHOUT extension; the extension is taken from the file content.
    The token goes into ?token=, not into a header: the header breaks the redirect to file storage.
    Returns the path of the finished file."""
    shown_url = url
    base_url = url
    tmp = dest + ".part"
    STATE["parts"].add(tmp)
    ctype = ""

    def finish():
        final = dest
        if auto_ext:
            ext = sniff_ext(tmp, ctype)
            if ext == ".jpg" and name_ext.lower() in (".jpg", ".jpeg"):
                ext = name_ext
            final = dest + ext
        if ctype.lower().startswith("text/html") and os.path.getsize(tmp) < 2000000:  # a page instead of the file: say so (the file is kept as before)
            diag_say("html_instead_of_file", diag_layer(base_url), "content-type %s, %d bytes" % (ctype, os.path.getsize(tmp)),
                     "the server sent a web page instead of the file (sign-in needed, a protection page or an error page): check what was saved")
        os.replace(tmp, final)
        STATE["parts"].discard(tmp)
        TB["cur"] = 0.0
        file_log("download ok: %s  content-type=%s  size=%d  url=%s" %
                 (os.path.basename(final), ctype, os.path.getsize(final), shown_url))
        return final

    for attempt in range(1, attempts + 1):
        if stop.is_set():
            raise Stopped()
        tok = AUTH.fresh(token)  # an OAuth token lives one hour: take the current one for every attempt
        url = base_url + ("&" if "?" in base_url else "?") + "token=" + urllib.parse.quote(tok) if tok else base_url
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
            diag_event(e, base_url, final=not (e.code in (429, 500, 502, 503, 504) and attempt < attempts))
            if e.code in (429, 500, 502, 503, 504) and attempt < attempts:
                log("    server answered %s, retry %d/%d" % (e.code, attempt, attempts - 1))
                stop.wait(3 * attempt)
                continue
            raise
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            diag_event(e, base_url, final=attempt >= attempts or bool(STATE.get("net_down")))
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


CHOOSE_HOOK = {"fn": None}  # tests put a function here that answers the questions of the program instead of a window
ASK_CLEANUP = {"fn": None}  # set by the window: asks Yes/No even after Stop was pressed
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
            file_log("webp convert: %s, mode %s, %dx%d, exif %s bytes" % (os.path.basename(path), im.mode, im.size[0], im.size[1],
                                                                       len(exif) if exif else 0))
            try:
                rgb.save(out, "JPEG", **kw)
            except Exception as e:  # noqa  (a JPEG holds at most 64 KB of EXIF/ICC: the picture matters more than those blocks)
                log("  the first JPG attempt failed (%s): converting again without the metadata blocks of the WebP" % e)
                file_log("pillow %s; metadata keys of the webp: %s" % (getattr(__import__("PIL"), "__version__", "?"), sorted(im.info.keys())))
                clean = Image.new("RGB", rgb.size)
                clean.paste(rgb)
                clean.save(out, "JPEG", quality=95, subsampling=0, optimize=True)
        os.remove(path)
        log("  converted WebP -> JPG: %s" % os.path.basename(out))
        return out
    except Exception as e:  # noqa
        log("  WebP conversion failed (%s), file kept as WebP" % e)
        file_log("webp convert error: %r" % (e,))
        try:
            if os.path.exists(out) and os.path.exists(path):
                os.remove(out)  # no half-written JPG next to the WebP
        except (OSError, NameError):
            pass
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

def devalue_unflatten(values):
    """The image pages keep their data in a compact 'devalue' form: a flat list in which every number is the position
    of another item (objects, lists) - this turns it back into ordinary dicts and lists."""
    memo = {}
    special = {-1: None, -2: float("nan"), -3: float("inf"), -4: float("-inf"), -5: -0.0}

    def hydrate(i):
        if isinstance(i, int) and i < 0:
            return special.get(i)
        if i in memo:
            return memo[i]
        v = values[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str):  # a special value (date, set, ...): kept as it is
                memo[i] = v
                return v
            out = memo[i] = []
            for x in v:
                out.append(hydrate(x))
            return out
        if isinstance(v, dict):
            out = memo[i] = {}
            for k, x in v.items():
                out[k] = hydrate(x)
            return out
        memo[i] = v
        return v
    return hydrate(0)


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
    STATE["page_route"] = "direct request"
    raw = fetch_page("%s://%s/images/%s" % (SCHEME, host, image_id), token)
    data = None
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
        except ValueError:
            data = None
    try:  # since autumn 2026 the page data is a string in the "devalue" form
        ts = data["props"]["pageProps"].get("trpcState") if isinstance(data, dict) else None
        if isinstance(ts, str):
            data["props"]["pageProps"]["trpcState"] = devalue_unflatten(json.loads(ts))
    except Exception as e:  # noqa
        file_log("could not decode the page data: %r" % (e,))
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
    if meta is None or img_url is None:  # tell the window log how the page was read (the details go to the log file)
        (STATE.get("log") or file_log)("    image page %s: read by %s, %d KB; generation metadata: %s; image address: %s%s" % (
            image_id, STATE.get("page_route", "?"), len(raw) // 1024, "found" if meta else "not found",
            "found" if img_url else "not found",
            "  (the page does not look like a normal image page)" if (img_url is None and "__NEXT_DATA__" not in raw) else ""))
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

ID_NAME_RE = re.compile(r"^(?:.*[-_ ])?(?P<ulid>[0-9A-Z]{26})(?:\.[A-Za-z0-9]{6,10})?$")


def readable_file_name(orig, model_name, version_name, several_versions):
    """A model file whose name is only an ID (26 random characters, optionally with a short suffix) gets the model title.
    Returns the new file name, or None when the name is not ID-like."""
    stem, ext = os.path.splitext(orig)
    m = ID_NAME_RE.match(stem)
    if not m or not re.search(r"\d", m.group("ulid")) or not re.search(r"[A-Z]", m.group("ulid")):
        return None
    base = safe_name(model_name or "", 150)
    if base == "unnamed":
        return None
    if several_versions and version_name:
        base = safe_name("%s - %s" % (base, version_name), 190)
    return base + ext


def flag(cfg, key):
    return str(cfg.get(key, DEFAULTS.get(key, ""))).strip().lower() in ("1", "true", "yes", "y")


def decide_existing(cfg, ask, what):
    """True = download again, False = skip."""
    mode = str(cfg.get("EXISTING", "ask")).strip().lower()
    if mode in ("overwrite", "over", "redo"):
        return True
    if mode in ("skip",):
        return False
    return bool(ask("Already downloaded:\n%s\n\nDownload it again?" % what, "Download again", "Skip"))


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
        if isinstance(e, (urllib.error.URLError, OSError, http.client.HTTPException)):
            diag_event(e, urls[0], final=True)
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
    diag_format(model, "model", "%s://%s/api/v1/models/%s" % (SCHEME, host, model_id))
    if not vid:
        vid = model["modelVersions"][0]["id"]
    ver = get_json("%s://%s/api/v1/model-versions/%s" % (SCHEME, host, vid), token)
    diag_format(ver, "version", "%s://%s/api/v1/model-versions/%s" % (SCHEME, host, vid))

    name = model.get("name") or (ver.get("model") or {}).get("name") or ("model_%s" % model_id)
    rf = resolve_model_folder(cfg["PATH"], name, model_id)
    folder = rf["folder"]
    log("  Model: %s  (version: %s)" % (name, ver.get("name")))
    if rf["alt"]:
        log("  A folder named %s already holds %s - this model goes into a new folder" % (
            os.path.basename(rf["base"]), ("another model (id %s)" % ", ".join(sorted(rf["ids"]))) if rf["ids"] else "something not known to be this model"))
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
    skip_note = "NO MODEL FILE: Model file is unchecked - only the examples and the description are downloaded"
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
        orig = safe_name(f.get("name") or ("%s.safetensors" % vid), 200)
        fn = cfg.get("PREFIX", "") + orig
        job = {"name": fn, "url": f.get("downloadUrl") or ver.get("downloadUrl"), "info": describe_file(f)}
        if flag(cfg, "RENAME_ID"):
            nice = readable_file_name(orig, model.get("name") or name, ver.get("name"), len(model.get("modelVersions") or []) > 1)
            if nice:
                job["orig"], job["orig_dest"] = orig, os.path.join(folder, fn)  # the old name: files downloaded earlier still count
                job["name"] = fn = cfg.get("PREFIX", "") + nice
        job["dest"] = os.path.join(folder, fn)
        jobs.append(job)
    orig_note = ", ".join(j["orig"] for j in jobs if j.get("orig"))
    if orig_note and do_model:
        log("  The file name is only an ID (%s) - saved as: %s" % (orig_note, ", ".join(j["name"] for j in jobs)))
    if do_model and jobs:
        many = len(weights) >= 2
        fname_shown = ", ".join(("%s (%s, %s)" % (j["name"], j["info"]["info"], j["info"]["size"])) if many else j["name"] for j in jobs)
    else:
        fname_shown = "(not downloaded)"

    overwrite = False
    have_any = do_model and any(os.path.exists(pth) and os.path.getsize(pth) > 0
                                for j in jobs for pth in (j["dest"], j.get("orig_dest")) if pth)
    if do_model and jobs and not have_any and ver.get("paidAccess"):
        acc = access_state(ver, token, url)  # last line of defence: nothing is created for a model that cannot be downloaded
        if acc["kind"] in ("paid", "early"):
            log("  " + acc["text"])
            if acc.get("probe"):
                log("  " + acc["probe"])
            if url in KEPT_LINKS:  # the user was already told (twice) and chose to keep the link in the list
                if "Not confirmed" in acc["text"]:
                    log("  The access could not be confirmed - trying to download anyway")
                else:
                    log("  SKIPPED: this version cannot be downloaded now. The link stays in the list; no folder was created.")
                    return "kept"
            elif not ask("%s\n\n%s\n\nTry to download anyway? If you leave it, nothing is created and the link stays in the list." % (name, acc["text"]),
                         "Try anyway", "Leave in the list"):
                log("  SKIPPED: this version cannot be downloaded now. The link stays in the list; no folder was created.")
                return "kept"
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
    ensure_dir(folder)

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
               "- **Page:** %s" % url, "- **Model ID:** %s | **Version ID:** %s" % (model_id, vid), "- **File:** %s" % fname_shown] + (["- **Original file name:** %s" % orig_note] if orig_note else [])
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
               "Page: %s" % url, "Model ID: %s | Version ID: %s" % (model_id, vid), "File: %s" % fname_shown] + (["Original file name: %s" % orig_note] if orig_note else [])
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
        other = dscr_owner(os.path.join(folder, dname))
        if other and other != str(model_id):  # the description of ANOTHER model lies here: never overwrite it
            base_, ext_ = os.path.splitext(dname)
            dname = "%s (%s)%s" % (base_, model_id, ext_)
            log("  The description file of another model (id %s) is in this folder - writing %s instead" % (other, dname))
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
    if not do_model:
        log("  [NO MODEL FILE] this model was processed without its model file (the Model file option was off)")
    write_marker(folder, model_id, vid, name, url)
    history_add("model:%s" % vid, url, folder, "ok",
                note=None if do_model else "examples only - model file NOT downloaded (Model file option was off)")
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
    own = cfg.get("OWN_FOLDER") == "1"  # the image was given a folder of its own: it does not follow the model above it
    if cfg.get("DIR"):  # an image that waited on hold: the folder of its (already finished) model was kept
        folder = os.path.normpath(cfg["DIR"])
    elif STATE["model_folder"] and not own:  # scenario 1: images that follow a model link go to that model's folder
        folder = STATE["model_folder"]
    elif STATE["model_failed"] and not own:
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
    ensure_dir(folder)

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
            extra.append("Note: generation metadata could not be read from the image page" +
                         (" (the page is blocked for scripts)" if STATE["page_blocked"] else ""))
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
1. Connect: tick "Connect via Sign-in" (recommended; a browser window opens), or tick "Connect via API" and paste your Civitai API key (account settings -> API keys) in Setup, tab Connection. While you are signed in, the sign-in has priority over the API token. Hover over a box to see its state. Choose an "Output folder" (a category folder: one kind of models per folder).
2. Add links: press Paste or Ctrl+V (several links in one text are fine), or send them from the browser. Every link becomes a row of the table: model links (.../models/ID?modelVersionId=ID) and/or image links (.../images/ID).
3. Press START (it turns into STOP while a task runs). Finished links disappear from the table, failed ones stay.

THE LINK TABLE
One row per link: its status (checking, ok, warning, kept, hold; running, partial, error during and after a run), the link (the model name when known), the folder, the prefix, the number of examples and of gallery images (the last two columns can be hidden in Setup). A new link takes the values of the fields above the table (Output folder, Prefix, Model file, Examples, From gallery) and keeps them: changing the fields with nothing selected affects only the links added afterwards. To change links that are already in the table, select them (Ctrl or Shift for several): the header then says \"settings for: N selected\" and the fields work for the selected rows only (the box shows nothing where the selected rows differ). A model and the images below it form a pack and share one colour (the colours alternate between packs); the images follow the folder of their model. An image can be given a folder of its own by selecting it and changing the folder: it is then marked with *. Hold puts the selected rows on pause: START skips them until you press Resume; a model on hold holds its images too. A held image of a model that has been downloaded meanwhile still goes to that model's folder. Keys: Delete removes the selected rows, Ctrl+A selects all, Ctrl+V pastes links, Ctrl+C copies the links, Ctrl+Z / Ctrl+Y undo and redo changes of the list, Esc deselects; a double click opens the page in the browser. The table is kept between runs of the program. The options of Setup apply to all links.

WHERE THINGS GO
- Every model gets its own folder inside the Output folder, named after the model (characters that Windows does not allow are replaced).
- If a folder with that name already holds ANOTHER model (or one nobody can identify), the new model goes into a separate folder named "Model name (model id)". The same model later finds its own folder again.
- Image links that follow a model link in the table go into that model's folder, continue the numbering and add their metadata to the same description file. A new model link starts a new folder. The model folder is remembered only within one run.
- Image links with no model link before them go to the Output folder, or into the subfolder when "Image subfolder" is ticked (a name, a nested path a/b/c, or a full path).
- A model link is removed from the list only after the image links below it are finished, so after a Stop or an error the rest of the list still knows its folder.

OPTIONS
Model file: tick to download the model file; the prefix box is used only then. Examples: how many example images/videos of the model version to download (number, all, or 0/empty for none; videos count). From gallery: how many images that other users uploaded to the model's gallery to download (number or all; needs the browser bridge, so the box is greyed out without it). 
If a model or image was downloaded before, the program does what Setup says: asks (default), skips it, or downloads it again (a task file can set EXISTING too). Images already saved to a different folder are never treated as downloaded.
Add prefix: text put before the model file name. Description file: name of the description file (.txt or .md, no extension = .txt; empty = no description file is written). "Name as model" names that file after the model instead (the extension still comes from the box).
Original file names: try to read the original name from the image page. WebP to JPG needs the Pillow library (py -m pip install pillow).
ComfyUI workflow as .json: experimental, saves the workflow found in the metadata next to the image.

LINK CHECK
A moment after a model link appears in the list (pasted, typed, or sent by the browser extension) the program asks Civitai whether it can be downloaded now. A paid model, a model in early access (with its end date), a deleted or hidden model, or an unpublished version is reported in a window: you remove the link from the list or keep it. START stays locked until all checks are done and answered. Links that are already downloaded, or whose model folder already exists with another (or an unknown) model in it, are reported in the same way (for an existing folder the buttons are "Exclude link" / "Download to new folder"). A kept availability problem is checked again when you press START. If Civitai cannot be reached, the link simply stays in the list. Paid and early-access links get one extra one-byte test request to the file address (it shows whether your account already bought the access); free models get no test request.

SETUP
The gear button at the top right (left of the question mark) opens Setup: options that are rarely changed. Changes apply at once. Tab Downloads: what to do with already downloaded items (Ask / Skip / Download again), the description file name (and "Name as model"), the image subfolder, videos, original file names, WebP to JPG, naming of ID-like model files, the experimental ComfyUI workflow .json. Tab Connection: the API token. Tab Program: how many recent output folders and prefixes the lists remember (5 to 30), the dark theme, and the update check (at start, at most once in 12 hours, the program asks github.com which release is the newest; if it is newer than this one, a link "Update ..." appears at the top right; nothing is downloaded or installed by the program).

FAILURE DIAGNOSTICS
When a request fails, the log gets a line "DIAG: class | part of the service | facts | conclusion". Classes: dns, timeout, reset, refused, tls, unreachable, dropped, server, rate_limit, cloudflare, auth, not_found, bad_request, not_json, html_instead_of_file, format. Parts: api (the Civitai API), page (web pages), files (file and image servers). At the first failure in a part the program also looks at the network around it: a bare connection to a neutral address (1.1.1.1, else 8.8.8.8), a bare connection to the host, one simple request to the Civitai site; the conclusion says whether it looks like your internet connection, that host, or the service itself. "format" means that the Civitai API answers with another structure than expected: the program may stop working correctly, please tell the author. The lines only go to the log; no data about you is sent anywhere.

PREFIX LINK
The chain button after the prefix links the prefix typed now to the current output folder. Every folder has its own link; folders without a link keep working as before. When a linked folder is chosen (Browse, the drop-down list, typing), its prefix is filled in. Joined rings: linked (click to unlink); rings apart: not linked, or the prefix was changed after linking (click to link the prefix typed now). The prefix can always be edited.

NAME ID-LIKE MODEL FILES BY TITLE
With this box ticked, a model file that has only an ID for a name (26 random characters, as the Civitai trainer makes them) is saved as <prefix><model title>.safetensors; when the model has several versions the version name is added. The original name is written to the description file. A model downloaded earlier under its ID name still counts as already downloaded.

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


# ---- the task engine: a task is a list of jobs (one link = one job with its OWN settings)
class Job:
    """One link of a task. The settings belong to the job (a copy made when the job is queued), so that different links of one task can
    later have different folders, prefixes, numbers of examples and so on. parent: the model job that a single-image link follows
    (the image goes into that model's folder). status: pending / ok / skipped / partial / kept / error."""
    __slots__ = ("url", "cfg", "kind", "parent", "key", "status", "note")

    def __init__(self, url, cfg, kind, parent=None):
        self.url, self.cfg, self.kind, self.parent = url, cfg, kind, parent
        self.key = link_key(url)
        self.status, self.note = "pending", ""


def link_kind(url):
    return "model" if "/models/" in url else ("image" if "/images/" in url else "other")


def make_jobs(urls, cfg):
    """Jobs from a list of links; every job gets its own copy of the settings. A single-image link that follows a model link
    belongs to that model (it is downloaded into the model's folder with the examples)."""
    jobs, last_model = [], None
    for u in urls:
        kind = link_kind(u)
        job = Job(u, dict(cfg), kind, last_model if kind == "image" else None)
        if kind == "model":
            last_model = job
        jobs.append(job)
    return jobs


def check_job_cfg(cfg, log):
    """The checks that were made once 'on start': the settings of a job with the defaults filled in, or None (the reason is logged)."""
    cfg = {**DEFAULTS, **cfg}
    if cfg["TOKEN"]:
        SECRETS.add(cfg["TOKEN"])
    if not cfg["PATH"]:
        log("No output folder given (PATH).")
        return None
    try:
        os.makedirs(cfg["PATH"], exist_ok=True)
    except OSError as e:
        log("Cannot create the output folder: %s" % e)
        return None
    pics = str(cfg.get("PICS", "")).strip().lower()
    gal = str(cfg.get("GALLERY", "")).strip().lower()
    for label, val in (("Examples", pics), ("From gallery", gal)):
        if val and val not in ("all", "*") and not val.isdigit():
            log("%s must be a number, all, or empty (now: %r)." % (label, val))
            return None
    return cfg


def run_task(cfg, urls, log, stop, ask, done=None):
    """A task of links that all have the same settings (the window and task files work this way for now)."""
    return run_jobs(make_jobs(urls, cfg), log, stop, ask, done, fallback_cfg=cfg)


def run_jobs(jobs, log, stop, ask, done=None, fallback_cfg=None, on_job=None):
    diag_reset()
    try:
        DIAG["site"] = urllib.parse.urlparse(str(jobs[0].url)).netloc if jobs else ""
    except ValueError:
        DIAG["site"] = ""
    DIAG["active"] = True  # DIAG lines go to the log only while a task runs (not while links are merely being checked)
    try:
        return _run_jobs(jobs, log, stop, ask, done, fallback_cfg, on_job)
    finally:
        DIAG["active"] = False


def _run_jobs(jobs, log, stop, ask, done=None, fallback_cfg=None, on_job=None):
    """Processes the jobs in order. done(url) is called for every link that is finished, so the
    caller can remove it from its list. A model link is reported as finished only after all
    single-image links directly below it are finished too; if the run is stopped or an image fails,
    the model link stays in the list and re-establishes the folder on the next run."""
    done = done or (lambda u: None)
    on_job = on_job or (lambda u, status: None)  # on_job(url, "running" | final status): the window shows it in the table
    log("Civitai Grabber v%s" % VERSION)
    log("Log file: %s" % LOGFILE)
    STATE.update({"log": log, "bridge_failures": 0, "bridge_off": False, "stop": stop, "blocked": 0, "page_blocked": False, "model_folder": None,
                  "model_name": None, "model_failed": False, "pillow_warned": False, "net_fail": 0, "net_down": False,
                  "made_dirs": [], "parts": set()})
    checked = []  # the settings of the jobs are checked once per distinct set of settings
    for job in (jobs or [None]):
        base = job.cfg if job else (fallback_cfg or {})
        known = next((r for c, r in checked if c == base), None)
        if known is None:
            known = check_job_cfg(base, log)
            if known is None:
                return
            checked.append((base, known))
        if job:
            job.cfg = dict(known)  # every job keeps a settings dictionary of its own
    STATE["made_dirs"], STATE["parts"] = [], set()
    urls = [j.url for j in jobs]
    token = AUTH.begin_run(urls, (jobs[0].cfg if jobs else checked[0][1])["TOKEN"], log)  # the credentials belong to the run
    for job in jobs:
        job.cfg["TOKEN"] = token
    log("Links in the task: %d" % len(jobs))
    TB.update({"phase": "connecting", "failed": 0, "total": len(jobs), "idx": 0, "cur": 0.0})
    seen = {}  # link key -> finished OK?
    group = {"url": None, "ok": True, "wait": None, "block": False}
    waited = []  # images that wait for the examples of the model above
    pending = []  # models downloaded with some failed images that wait for the answer at the end of the list: (url, name, note)

    def partial_policy(c):
        mode = str(c.get("ON_PARTIAL", "ask")).strip().lower()
        mode = mode if mode in ("ask", "keep", "finish") else "ask"
        when = str(c.get("PARTIAL_NOTICE", "each")).strip().lower()
        when = when if when in ("each", "end", "none") else "each"
        return mode, ("each" if (mode == "ask" and when == "none") else when)  # a question cannot be skipped

    def decide(items, mode, when):
        """True = keep the models in the list with the Model file switched off, to complete them later; False = finish them as they are."""
        head = ("The model was downloaded, but some of its images were not:" if len(items) == 1
                else "%d models were downloaded, but some of their images were not:" % len(items))
        names = "\n".join("  %s - %s" % (nm, nt) for _u, nm, nt in items)
        if mode == "ask":
            return bool(ask("%s\n%s\n\nKeep %s in the list (Model file switched off) to complete %s later, or finish as it is?"
                            % (head, names, "it" if len(items) == 1 else "them", "it" if len(items) == 1 else "them"), "Keep in queue", "Finish as is"))
        keep = mode == "keep"
        if when != "none":
            on_job("", "notice:%s\n%s\n\n%s" % (head, names, "Kept in the list with the Model file switched off." if keep else "Finished as they are."))
        return keep

    def keep_model(u):
        ATTENTION.pop(u, None)
        on_job(u, "keep")
        log("  KEPT IN THE LIST: the model is downloaded; only its images will be completed on the next run (Model file is switched off for this row)")

    def close_group():
        if group["url"] and group["ok"]:
            if group["wait"]:
                pending.append(group["wait"])  # the answer comes at the end of the list
            else:
                done(group["url"])
        group["url"], group["ok"], group["wait"], group["block"] = None, True, None, False

    for i, job in enumerate(jobs, 1):
        u, cfg, k = job.url, job.cfg, job.key
        if stop.is_set():
            log("Stopped.")
            safe_cleanup(log)
            return
        log("[%d/%d] %s" % (i, len(jobs), u))
        if (job.kind != "model" and group["block"] and job.parent is not None and job.parent.url == group["url"]
                and cfg.get("OWN_FOLDER") != "1" and not cfg.get("DIR")):
            log("  WAITING: the examples of the model above are not complete, so this image waits (the numbering must start with the examples)")
            job.status = "waiting"
            on_job(u, "waiting")
            waited.append(u)
            continue
        TB["idx"], TB["cur"] = i - 1, 0.0
        on_job(u, "running")
        if k in seen:
            log("  SKIPPED: this link already appeared earlier in the list")
            job.status = "skipped"
            on_job(u, "skipped")
            if seen[k]:
                done(u)
            continue
        is_model = job.kind == "model"
        if is_model:
            close_group()
            STATE["model_folder"], STATE["model_failed"], STATE["model_name"] = None, False, None
        ok = False
        res = None
        try:
            if is_model:
                nxt = jobs[i].url if i < len(jobs) else ""
                res = process_model(u, cfg, log, stop, ask, next_is_image="/images/" in nxt)
            elif "/images/" in u:
                res = process_image(u, cfg, log, stop, ask)
            else:
                log("  Unrecognised link (expected /models/ or /images/)")
                res = "kept"
            ok = res in ("ok", "skipped", "partial")
            job.status = res or "error"
            if res == "partial":
                note = STATE.pop("partial_note", "some files were not downloaded")
                job.note = note
                ATTENTION[u] = note
                TB["failed"] += 1
                log("  ATTENTION: %s - the browser page of this link stays open and is marked in the extension window" % note)
        except Stopped:
            log("Stopped.")
            safe_cleanup(log)
            return
        except urllib.error.HTTPError as e:
            job.status = "error"
            hint = ""
            if e.code in (401, 403):
                hint = " - the model may be paid (buzz) or in early access, or the token is not accepted"
            elif e.code == 404:
                hint = " - page/model not found or hidden"
            AUTH.note_error(e.code, e.url)
            log("  HTTP ERROR %s: %s%s  (...%s)%s" % (e.code, e.reason, hint, str(e.url)[-70:], AUTH.tag()))
            file_log("HTTPError %s %s" % (e.code, e.url))
            if not getattr(e, "_diag_done", False):
                diag_event(e, e.url, final=True)
            history_add(k, u, cfg["PATH"], "error HTTP %s" % e.code)
        except Exception as e:  # noqa
            job.status = "error"
            log("  ERROR: %s: %s" % (type(e).__name__, e))
            file_log(traceback.format_exc())
            if isinstance(e, (urllib.error.URLError, OSError, http.client.HTTPException, json.JSONDecodeError)) \
                    and not getattr(e, "_diag_done", False):  # a failure already reported where it happened is not reported twice
                diag_event(e, u, final=True)
            history_add(k, u, cfg["PATH"], "error %s" % type(e).__name__)
        seen[k] = ok
        on_job(u, job.status)
        if not ok:
            TB["failed"] += 1
        if is_model:
            if not ok:
                STATE["model_failed"], STATE["model_folder"] = True, None
            group["url"], group["ok"] = u, ok
            if ok and res == "partial":
                mode_, when_ = partial_policy(cfg)
                info_ = (u, STATE.get("model_name") or u, job.note)
                if when_ == "end":
                    group["wait"], group["cfg"] = info_, cfg
                    group["block"] = True  # the answer comes later: the gallery images wait for it
                elif decide([info_], mode_, when_):
                    group["ok"] = False
                    group["block"] = True
                    keep_model(u)
        elif ok:
            done(u)
        elif group["url"]:
            group["ok"] = False
        time.sleep(0.7)
    close_group()
    if pending:
        mode_, when_ = partial_policy(group.get("cfg") or {})
        if decide(pending, mode_, when_):
            for u_, _nm, _nt in pending:
                keep_model(u_)
        else:
            for u_, _nm, _nt in pending:
                done(u_)
    if waited:
        log("%d image link(s) wait in the list for the examples of their model; they go on the next run." % len(waited))
    safe_cleanup(log)
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


UPDATE_REPO = "Overbooster/civitai-grabber"  # whose releases are checked for updates (a fork changes this)
TIP_COLORS = {"bg": "#ffffe0", "fg": "#000000"}  # hover hints; changed by the dark theme


def parse_version(text):
    """'v0.46' -> (0, 46); versions are compared as tuples of numbers."""
    return tuple(int(n) for n in re.findall(r"\d+", str(text or ""))[:4])


def latest_release(repo, timeout=10):
    """The newest release of a GitHub repository -> (tag, page address). First the address /releases/latest, which answers with a
    redirect to the page of the newest (not pre-)release (no API, no request limit); if that does not work (a blocked or slow
    github.com, a proxy), the API of GitHub is asked instead (it allows few requests per hour, enough for one check in 12 hours)."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    headers = {"User-Agent": "CivitaiGrabber/" + VERSION}
    problems = []
    for attempt in (1, 2):  # github.com answers with pauses now and then: a second try after a moment
        try:
            opener = urllib.request.build_opener(NoRedirect())
            try:
                opener.open(urllib.request.Request("https://github.com/%s/releases/latest" % repo, headers=headers), timeout=timeout)
                problems.append("unexpected answer")
            except urllib.error.HTTPError as e:
                m = re.search(r"/releases/tag/([^/?#]+)$", e.headers.get("Location") or "")
                if e.code in (301, 302, 303, 307, 308) and m:
                    tag = urllib.parse.unquote(m.group(1))
                    return tag, "https://github.com/%s/releases/tag/%s" % (repo, m.group(1))
                problems.append("no release found (HTTP %s)" % e.code)
                break  # a real answer without a release: asking again will not help
            break
        except Exception as e:  # noqa
            problems.append(str(e) or e.__class__.__name__)
            if attempt == 1:
                time.sleep(1.5)
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % repo,
                                                           headers=dict(headers, Accept="application/vnd.github+json")), timeout=timeout) as r:
            d = json.load(r)
        tag = str(d.get("tag_name") or "")
        if tag:
            return tag, d.get("html_url") or "https://github.com/%s/releases/tag/%s" % (repo, urllib.parse.quote(tag))
        problems.append("the API answer has no release")
    except Exception as e:  # noqa
        problems.append("API: " + (str(e) or e.__class__.__name__))
    raise RuntimeError("; ".join(problems))


def checkbox_png(px, checked, border, fill, mark, gap=0):
    """A check box for the dark theme, px pixels square: a rounded square with a thick border, a tick when checked.
    Anti-aliased by supersampling; colours are (r, g, b); gap = transparent columns on the right (space before the text)."""
    s_, ss = px / 16.0, 4
    R, W = 3.2 * s_, 2.0 * s_
    pts = [(3.9 * s_, 8.3 * s_), (6.8 * s_, 11.2 * s_), (12.2 * s_, 5.0 * s_)]

    def rr(x, y, inset, r):
        lo, hi = inset, px - inset
        if not (lo <= x <= hi and lo <= y <= hi):
            return False
        cx, cy = min(max(x, lo + r), hi - r), min(max(y, lo + r), hi - r)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r

    def on_tick(x, y):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            dx, dy = x2 - x1, y2 - y1
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / float(dx * dx + dy * dy)))
            if (x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2 <= (1.15 * s_) ** 2:
                return True
        return False

    rows = []
    for y in range(px):
        row = bytearray()
        for x in range(px):
            m, rs, gs, bs = 0, 0, 0, 0
            for sy in range(ss):
                for sx in range(ss):
                    fx, fy = x + (sx + 0.5) / ss, y + (sy + 0.5) / ss
                    if not rr(fx, fy, 0.5, R):
                        continue
                    if checked and on_tick(fx, fy):
                        c = mark
                    elif rr(fx, fy, 0.5 + W, max(R - W, 0.5)):
                        c = fill
                    else:
                        c = border
                    m += 1
                    rs, gs, bs = rs + c[0], gs + c[1], bs + c[2]
            if m:
                row += bytes((rs // m, gs // m, bs // m, int(255 * m / (ss * ss))))
            else:
                row += bytes((0, 0, 0, 0))
        row += bytes(4 * gap)
        rows.append(bytes(row))
    return _png_rgba(px + gap, px, rows)


class Tooltip:
    """Small hover hint for a Tk widget."""

    def __init__(self, widget, text, delay=600, wrap=380, when=None, pos=None):
        """when(event) -> bool: the hint belongs to a part of the widget only (checked while the pointer moves);
        pos() -> (x, y): where the hint appears (screen coordinates); wrap: line width in pixels (a number or a function)."""
        self.widget, self.text, self.delay, self.wrap, self.when, self.pos = widget, text, delay, wrap, when, pos
        self.tip = None
        self.job = None
        if when is None:
            widget.bind("<Enter>", self._schedule, "+")
        else:
            widget.bind("<Motion>", self._motion, "+")
        widget.bind("<Leave>", self._hide, "+")
        widget.bind("<ButtonPress>", self._hide, "+")

    def _motion(self, e):
        if self.when(e):
            if self.tip is None and self.job is None:
                self.job = self.widget.after(self.delay, self._show)
        else:
            self._hide()

    def _schedule(self, _e=None):
        self._hide()
        self.job = self.widget.after(self.delay, self._show)

    def _show(self):
        import tkinter as tk
        self.job = None
        if self.tip is not None:
            return
        text = self.text() if callable(self.text) else self.text
        if self.pos:
            x, y = self.pos()
        else:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        wrap = self.wrap() if callable(self.wrap) else self.wrap
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry("+%d+%d" % (x, y))
        tk.Label(self.tip, text=text, justify="left", background=TIP_COLORS["bg"], foreground=TIP_COLORS["fg"], relief="solid",
                 borderwidth=1, padx=6, pady=3, wraplength=wrap).pack()

    def _hide(self, _e=None):
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


EXISTING_LABELS = [("Ask", "ask"), ("Skip", "skip"), ("Download again", "overwrite")]
PARTIAL_LABELS = [("Ask", "ask"), ("Keep in queue", "keep"), ("Finish", "finish")]  # a model is downloaded, but some example/gallery images failed
NOTICE_LABELS = [("After each job", "each"), ("At the end of the list", "end"), ("Don't notify", "none")]


FLAG_KEYS = ("VIDEO", "ORIGINAL", "COMFY", "WEBP2JPG", "USE_SUBFOLDER", "BRIDGE", "DSCR_AS_MODEL", "MODEL", "RENAME_ID", "USE_API", "DARK", "CHECK_UPDATES", "COL_PICS", "COL_GALLERY", "BRIDGE_DARK")
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
    from tkinter import ttk, filedialog, messagebox
    from tkinter import font as tkfont

    class ScrollText(tk.Text):
        """Like scrolledtext.ScrolledText, but with a ttk scrollbar (a tk scrollbar cannot be recoloured for the dark theme)."""

        def __init__(self, master, **kw):
            self.frame = ttk.Frame(master)
            self.vbar = ttk.Scrollbar(self.frame, orient="vertical")
            self.vbar.pack(side="right", fill="y")
            kw["yscrollcommand"] = self.vbar.set
            tk.Text.__init__(self, self.frame, **kw)
            self.pack(side="left", fill="both", expand=True)
            self.vbar["command"] = self.yview
            for m in vars(tk.Pack).keys() | vars(tk.Grid).keys() | vars(tk.Place).keys():
                if m[0] != "_" and m not in ("config", "configure"):
                    setattr(self, m, getattr(self.frame, m))

    import tkinter.font as tkfont

    saved = load_settings()
    if "USE_API" not in saved:  # settings of an older version: a saved token means the API connection was in use
        saved["USE_API"] = "1" if str(saved.get("TOKEN") or "").strip() else "0"
    if str(saved.get("TOKEN") or "").strip():
        SECRETS.add(str(saved["TOKEN"]).strip())
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
    root.minsize(736, 580)
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
        w, h = max(736, min(w, sw)), max(580, min(h, sh))
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
    auth_q = queue.Queue()  # things the sign-in thread wants done in the window
    choose_q = queue.Queue()
    done_q = queue.Queue()
    job_q = queue.Queue()  # (link, status) from the engine: shown in the table
    stop = threading.Event()
    state = {"thread": None}
    tb = {"icon": "idle", "key": None, "key_t": 0.0, "attach_t": 0.0, "last_flash": 0.0, "blink": None, "hold": None, "hold_t": 0.0, "prog": TaskbarProgress()}
    gal_state = {"s": None}
    launch_state = {"asked": bool(saved.get("LAUNCH_ASKED"))}
    RECENT_LIMIT = {"PATH": 12, "PREFIX": 12, "IMGFOLDER": 10}
    recent = {"PATH": [], "PREFIX": [], "IMGFOLDER": []}  # newest first; RECENT_LIMIT for folders/prefixes, 10 for image subfolders
    combos = {}
    try:  # the number of remembered output folders (Setup); 5..30, default 12
        RECENT_LIMIT["PATH"] = max(5, min(30, int(saved.get("RECENT_PATHS_LIMIT", 12))))
        RECENT_LIMIT["PREFIX"] = RECENT_LIMIT["PATH"]  # the prefix list is always as long as the folder list
    except (TypeError, ValueError):
        pass

    v = {k: tk.StringVar() for k in TEXT_KEYS}
    b = {k: tk.BooleanVar() for k in FLAG_KEYS}
    b["BRIDGE_DARK"].trace_add("write", lambda *_: setattr(BRIDGE, "dark", bool(b["BRIDGE_DARK"].get())))  # the extension is told in the ping answer
    existing_var = tk.StringVar(value="Ask")
    partial_var = tk.StringVar(value="Ask")
    notice_var = tk.StringVar(value="After each job")

    # ---- settings
    frm = ttk.Frame(root, padding=(8, 8, 8, 4))
    frm.pack(fill="x")
    frm.columnconfigure(1, weight=1)

    ttk.Label(frm, text="Connect:").grid(row=0, column=0, sticky="w", pady=2)
    row_tk = ttk.Frame(frm)
    row_tk.grid(row=0, column=1, columnspan=2, sticky="we", padx=(6, 0), pady=2)
    signin_var = tk.BooleanVar(value=False)  # shows the real state: signed in or not
    cb_signin = ttk.Checkbutton(row_tk, text="Connect via Sign-in", variable=signin_var)
    cb_signin.pack(side="left")
    cb_api = ttk.Checkbutton(row_tk, text="Connect via API", variable=b["USE_API"])
    cb_api.pack(side="left", padx=(14, 0))
    cb_bridge = ttk.Checkbutton(row_tk, text="Browser bridge", variable=b["BRIDGE"])
    cb_bridge.pack(side="left", padx=(14, 0))

    ttk.Label(frm, text="Output folder:").grid(row=1, column=0, sticky="w", pady=2)
    row_path = ttk.Frame(frm)
    row_path.grid(row=1, column=1, columnspan=2, sticky="we", padx=(6, 0), pady=2)
    path_combo = ttk.Combobox(row_path, textvariable=v["PATH"], height=RECENT_LIMIT["PATH"] + 1)  # 12 recent folders + "Add output folder..." without a scroll bar
    path_combo.pack(side="left", fill="x", expand=True, ipady=2)
    combos["PATH"] = path_combo
    try:
        scale = min(3.0, max(1.0, root.winfo_fpixels("1i") / 96.0))
    except tk.TclError:
        scale = 1.0
    ICONS = {mode: {"on": tk.PhotoImage(data=base64.b64encode(chain_icon_png(True, scale / 1.5, mode == "dark"))),
                    "off": tk.PhotoImage(data=base64.b64encode(chain_icon_png(False, scale / 1.5, mode == "dark")))}
             for mode in ("light", "dark")}
    icon_mode = {"cur": "light"}
    link_btn = ttk.Label(row_path, image=ICONS["light"]["off"], cursor="hand2", padding=1, borderwidth=1, relief="flat", takefocus=True)  # no button outline: just the chain (a thin frame shows the keyboard focus)
    link_btn.pack(side="left", padx=(8, 4))
    lbl_prefix = ttk.Label(row_path, text="Prefix:")
    lbl_prefix.pack(side="left", padx=(4, 6))
    prefix_box = ttk.Frame(row_path, width=110, height=26)  # its width is set so that the field starts above "From gallery:"
    prefix_box.pack(side="left")
    prefix_box.pack_propagate(False)
    e_prefix = ttk.Combobox(prefix_box, textvariable=v["PREFIX"], height=RECENT_LIMIT["PREFIX"])
    e_prefix.pack(fill="both", expand=True, ipady=2)
    combos["PREFIX"] = e_prefix

    def align_prefix():
        """The left edge of the prefix field = the left edge of the "From gallery:" label in the Links row below."""
        root.update_idletasks()
        left = lbl_gallery.winfo_rootx()
        w = row_path.winfo_rootx() + row_path.winfo_width() - left
        if w > 60:
            prefix_box.configure(width=w, height=e_prefix.winfo_reqheight() + 4)
            try:  # the main button is as wide as the prefix field
                cur = start_btn.winfo_reqwidth()
                if abs(cur - w) > 2:
                    start_btn.configure(padx=max(6, int(float(start_btn.cget("padx"))) + (w - cur) // 2))
            except (tk.TclError, NameError, ValueError):
                pass

    align_state = {"after": None}

    def align_later(_e=None):
        if align_state["after"]:
            root.after_cancel(align_state["after"])
        align_state["after"] = root.after(60, lambda: (align_state.update(after=None), align_prefix()))

    frm.bind("<Configure>", align_later)
    root.after(150, align_later)

    setup_w = {}  # widgets of the Setup window that depend on other options (exist only while Setup is open)

    def sync_setup(*_):  # greyed-out boxes in Setup: subfolder unless its box is ticked, name box with Name-as-model
        try:
            if "e_img" in setup_w:
                setup_w["e_img"].configure(state="normal" if b["USE_SUBFOLDER"].get() else "disabled")
            if "e_dscr" in setup_w:
                setup_w["e_dscr"].configure(state="disabled" if b["DSCR_AS_MODEL"].get() else "normal")
        except tk.TclError:
            pass

    ui_state = {"only_img": False}  # only single-image rows are selected: they have a folder only, the other fields are greyed out

    def sync_fields(*_):  # prefix is greyed out without Model file
        e_prefix.configure(state="normal" if b["MODEL"].get() and not ui_state["only_img"] else "disabled")
        sync_setup()

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
    hdr.pack(fill="x", pady=(2, 0))
    hdr_var = tk.StringVar(value="Links (settings for: next links)")  # which links the fields below change: all, or the selected rows
    hdr_label = ttk.Label(hdr, textvariable=hdr_var)
    hdr_label.pack(side="left")
    cb_model = ttk.Checkbutton(hdr, text="Model file", variable=b["MODEL"])
    count_values = ["all"] + [str(n) for n in range(0, 21)]  # typing any number or "all" still works
    e_gal = ttk.Combobox(hdr, textvariable=v["GALLERY"], values=count_values, width=5, height=12)
    e_pics = ttk.Combobox(hdr, textvariable=v["PICS"], values=count_values, width=5, height=12)
    e_gal.pack(side="right", ipady=2)  # from the right: gallery, examples, model file (so they read left to right: Model file, Examples, From gallery)
    lbl_gallery = ttk.Label(hdr, text="From gallery:")
    lbl_gallery.pack(side="right", padx=(12, 6))
    hdr.bind("<Configure>", align_later)
    e_pics.pack(side="right", ipady=2)
    ttk.Label(hdr, text="Examples:").pack(side="right", padx=(16, 6))
    cb_model.pack(side="right")
    actions = ttk.Frame(top_pane, padding=(0, 10, 0, 6))
    actions.pack(side="bottom", fill="x")
    tbl_frame = ttk.Frame(top_pane)
    tbl_frame.pack(fill="both", expand=True, pady=(8, 0))
    TABLE_COLS = (("status", "Status", 98, "w"), ("link", "Link", 260, "w"), ("folder", "Folder", 170, "w"),
                  ("prefix", "Prefix", 80, "w"), ("pics", "Examples", 84, "center"), ("gallery", "Gallery", 68, "center"))
    tree = ttk.Treeview(tbl_frame, columns=[c[0] for c in TABLE_COLS], show="headings", selectmode="extended", height=6)
    for key_, title_, width_, anchor_ in TABLE_COLS:
        tree.heading(key_, text=title_, anchor="w" if anchor_ == "w" else "center")
        tree.column(key_, width=width_, minwidth=120 if key_ == "link" else 44, anchor=anchor_, stretch=(key_ == "link"))  # (the Folder column joins in when columns are hidden)
    tvbar = ttk.Scrollbar(tbl_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=tvbar.set)
    tvbar.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)

    paste_btn = ttk.Button(actions, text="Paste")
    undo_btn = ttk.Button(actions, text="Undo", takefocus=False)
    redo_btn = ttk.Button(actions, text="Redo", takefocus=False)
    sample_btn = ttk.Button(actions, text="Create sample txt")  # hidden unless SHOW_TXT_BUTTONS
    load_btn = ttk.Button(actions, text="Load from txt…")
    hold_btn = ttk.Button(actions, text="Hold")
    clear_btn = ttk.Button(actions, text="Clear all")
    shown = [paste_btn] + ([sample_btn, load_btn] if SHOW_TXT_BUTTONS else []) + [undo_btn, redo_btn, hold_btn, clear_btn]
    for w in shown:
        w.pack(side="left", padx=(0, 6))
    class StartButton(tk.Button):
        """The main button, one for both actions: START (blue, the same blue with white text as the buttons of the browser extension)
        while nothing runs, STOP (amber) while a task runs, "Stopping..." (pale amber, not pressable) until the task has ended, and the
        pale blue "locked" look while the links are being checked."""
        MODES = {"start": ("START", "#2162be", "#ffffff", "#1b4f99"), "locked": ("START", "#a9c1e6", "#ffffff", None),
                 "stop": ("STOP", "#f0a830", "#1b1b1b", "#e29a1c"), "stopping": ("Stopping\u2026", "#f3dca9", "#6b5a35", None)}

        def __init__(self, master, **kw):
            f = tkfont.nametofont("TkDefaultFont").copy()
            f.configure(weight="bold")
            bg = ttk.Style(master).lookup("TFrame", "background") or "#f0f0f0"
            self.mode = "start"
            tk.Button.__init__(self, master, font=f, relief="flat", bd=0, padx=16, pady=2, cursor="hand2", width=9,
                               activeforeground="#ffffff", highlightthickness=2, highlightbackground=bg, highlightcolor=bg, **kw)
            self.ring_hidden, self.ring_shown = bg, "#163f7a"
            self.set_mode("start")
            self.bind("<Enter>", lambda e: self._hover(True))
            self.bind("<Leave>", lambda e: self._hover(False))

        def set_mode(self, mode):
            self.mode = mode
            text, bg, fg, hover = self.MODES[mode]
            off = hover is None
            tk.Button.configure(self, text=text, bg=bg, fg=fg, activebackground=hover or bg, activeforeground=fg, disabledforeground=fg,
                                state="disabled" if off else "normal", cursor="arrow" if off else "hand2")

        def _hover(self, inside):
            text, bg, fg, hover = self.MODES[self.mode]
            if hover:
                tk.Button.configure(self, bg=hover if inside else bg)

        def configure(self, cnf=None, **kw):
            res = tk.Button.configure(self, cnf, **kw) if (cnf or kw) else tk.Button.configure(self)
            if "state" in kw and self.mode in ("start", "locked"):  # callers that only lock / unlock START
                self.set_mode("locked" if str(kw["state"]) == "disabled" else "start")
            return res

        config = configure

    start_btn = StartButton(actions, text="START")
    start_btn.pack(side="right")

    logbtns = ttk.Frame(bottom_pane, padding=(0, 4, 0, 0))
    logbtns.pack(side="bottom", fill="x")
    copylog_btn = ttk.Button(logbtns, text="Copy log")
    openlog_btn = ttk.Button(logbtns, text="Open log file")
    copylog_btn.pack(side="left", padx=(0, 6))
    openlog_btn.pack(side="left")
    icons_box = ttk.Frame(row_tk)  # the gear and the question mark always get cells of the same size
    icons_box.pack(side="right", before=cb_signin)  # packed before the left-hand boxes: when the window is narrow they keep their room
    icons_box.columnconfigure(0, uniform="ib")
    icons_box.columnconfigure(2, uniform="ib")
    icons_box.columnconfigure(1, minsize=6)
    help_btn = ttk.Button(icons_box, text="?", width=3)
    help_btn.grid(row=0, column=2, sticky="nsew")
    GEARS = {mode: tk.PhotoImage(data=base64.b64encode(gear_icon_png(scale / 1.5, mode == "dark"))) for mode in ("light", "dark")}
    setup_btn = ttk.Button(icons_box, image=GEARS["light"], width=3)  # the gear: Setup (a drawn picture, the same on every system)
    setup_btn.grid(row=0, column=0, sticky="nsew")
    upd_font = tkfont.nametofont("TkDefaultFont").copy()
    upd_font.configure(underline=True)
    upd_lbl = ttk.Label(row_tk, text="", cursor="hand2", font=upd_font, foreground="#0b57d0", padding=1, borderwidth=1, relief="flat",
                        takefocus=True)  # "New version ..." link; shown only when a newer release exists
    box = ScrollText(bottom_pane, wrap="word", state="disabled", font=mono)
    box.pack(fill="both", expand=True)

    # ---- keyboard: Tab / Shift+Tab leave the text boxes (no tab characters), Enter presses the focused button
    kbd = {"tab": 0.0}  # when Tab was last pressed: tells keyboard focus from focus given by a mouse click

    def note_tab(_e=None):
        kbd["tab"] = time.time()

    root.bind_all("<KeyPress-Tab>", note_tab, "+")
    root.bind_all("<ISO_Left_Tab>", note_tab, "+")

    def tab_out(widget):
        def go(_e, back=False):
            note_tab()
            nxt = widget.tk_focusPrev() if back else widget.tk_focusNext()
            if nxt:
                nxt.focus_set()
            return "break"
        widget.bind("<Tab>", go)
        widget.bind("<Shift-Tab>", lambda e: go(e, True))
        widget.bind("<ISO_Left_Tab>", lambda e: go(e, True))

    tab_out(box)
    for sb in (tvbar, box.vbar):
        sb.configure(takefocus=0)
    # Tab order follows the stacking order of the widgets, which is the order of creation: put it in the order of the screen
    for w in (setup_btn, help_btn, upd_lbl, icons_box, cb_model, e_pics, e_gal, actions):
        w.lift()
    for cls in ("TButton", "Button"):
        root.bind_class(cls, "<Return>", lambda e: (e.widget.invoke(), "break")[1])

    def strip_focus(layout):  # a ttk layout without its dotted focus rectangle
        out = []
        for name, opts in layout:
            opts = dict(opts or {})
            kids = strip_focus(opts["children"]) if opts.get("children") else []
            if name.endswith(".focus"):
                for kn, ko in kids:
                    ko = dict(ko)
                    for key in ("side", "sticky", "expand"):
                        if key in opts:
                            ko[key] = opts[key]
                    out.append((kn, ko))
                continue
            if kids:
                opts["children"] = kids
            out.append((name, opts))
        return out

    def calm_focus(w):
        """The focus rectangle of a button/box stays while the keyboard is used (Tab), but a rectangle left by a mouse click
        (or by returning to the window) fades after 3 seconds; the focus itself does not move."""
        if isinstance(w, StartButton):
            show = lambda: w.configure(highlightcolor=w.ring_shown)  # noqa: E731
            hide = lambda: w.configure(highlightcolor=w.ring_hidden)  # noqa: E731
        elif w.winfo_class() in ("TButton", "TCheckbutton"):
            orig = str(w.cget("style"))
            base = orig or w.winfo_class()
            quiet = "Quiet." + base
            st = ttk.Style(root)

            def ensure():  # layouts belong to a theme: make the "quiet" one for the theme that is on now
                key = (st.theme_use(), quiet)
                if key not in quiet_done:
                    st.layout(quiet, strip_focus(st.layout(base)))
                    quiet_done.add(key)

            try:
                ensure()
            except tk.TclError:
                return

            def hide():
                ensure()
                w.configure(style=quiet)
            show = lambda: w.configure(style=orig)  # noqa: E731
        else:
            return
        job = {"id": None}

        def cancel():
            if job["id"] is not None:
                w.after_cancel(job["id"])
                job["id"] = None

        def on_in(_e):
            cancel()
            try:
                show()
            except tk.TclError:
                return
            if time.time() - kbd["tab"] > 0.4:
                job["id"] = w.after(3000, fade)

        def fade():
            job["id"] = None
            try:
                if root.focus_get() is w:
                    hide()
            except (tk.TclError, KeyError):
                pass

        def on_out(_e):
            cancel()
            try:
                show()
            except tk.TclError:
                pass

        w.bind("<FocusIn>", on_in, "+")
        w.bind("<FocusOut>", on_out, "+")

    quiet_done = set()

    def apply_calm(parent):
        for child in parent.winfo_children():
            calm_focus(child)
            apply_calm(child)

    apply_calm(root)

    # ---- dark theme: the light look is the system theme untouched; dark = the "clam" theme with a palette, plus the plain tk widgets
    DARK = dict(bg="#2b2d30", field="#1e1f22", fg="#dfe1e5", border="#4e5157", btn="#3c3f41", btn_hi="#4c5052", sel="#2f65ca",
                dis="#7b7f87", link="#6ea8ff", tipbg="#3c3f41")
    style0 = ttk.Style(root)
    light_theme = style0.theme_use()
    _t, _l = tk.Text(root), tk.Listbox(root)
    LIGHT_TK = {"text": {o: _t.cget(o) for o in ("background", "foreground", "insertbackground", "selectbackground", "selectforeground")},
                "list": {o: _l.cget(o) for o in ("background", "foreground", "selectbackground", "selectforeground")},
                "top": root.cget("background")}
    _t.destroy()
    _l.destroy()
    theme_state = {"dark": False}
    dark_cb = {}  # check box pictures of the dark theme (made once)

    # ---- title bars (Windows). Windows 11: the dark-mode attribute plus caption colours, for every window. Windows 10: only the dark-mode
    # attribute, and only when "Show accent colour on title bars and window borders" is OFF: with it on, Windows paints the title bar of
    # the ACTIVE window with the accent colour whatever a program asks for (a user's log showed ColorPrevalence=1 and the accent #E0E8ED:
    # the "light active / dark inactive" mix). Then the program leaves the title bars to the system and says so in Setup.
    title_seen = set()

    def title_plan():
        """-> 'none' (not Windows), 'win11', 'dark10' (Windows 10, accent off) or 'system' (Windows 10, accent on: hands off)."""
        if sys.platform != "win32":
            return "none"
        build = getattr(sys.getwindowsversion(), "build", 0)
        if build >= 22000:
            return "win11"
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as k:
                if winreg.QueryValueEx(k, "ColorPrevalence")[0]:
                    return "system"
        except OSError:
            pass
        return "dark10"

    title_log = {"n": 0}

    def titlebar_now(win, on, plan):
        try:
            import ctypes
            from ctypes import wintypes as wt
            u, d = ctypes.windll.user32, ctypes.windll.dwmapi
            u.GetAncestor.argtypes, u.GetAncestor.restype = [wt.HWND, wt.UINT], wt.HWND
            u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
            u.RedrawWindow.argtypes = [wt.HWND, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
            d.DwmSetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
            hwnd = u.GetAncestor(win.winfo_id(), 2)  # the top-level window itself (not an owner)
            if not hwnd:
                return

            def put(attr, value, kind=ctypes.c_uint):
                val = kind(value)
                return d.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val))

            r = put(20, 1 if on else 0, ctypes.c_int)
            if r != 0:
                r = put(19, 1 if on else 0, ctypes.c_int)  # older Windows 10
            if plan == "win11":
                put(35, 0x00221F1E if on else 0xFFFFFFFF)  # caption colour #1e1f22 (the colour of the input fields)
                put(36, 0x00E5E1DF if on else 0xFFFFFFFF)  # title text colour #dfe1e5
            if title_log["n"] < 14:
                title_log["n"] += 1
                file_log("Title bar: window %r hwnd=%s plan=%s dark=%s result=%s" % (win.title(), hwnd, plan, on, r))
            u.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x27)  # frame changed
            u.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0400 | 0x0100)  # repaint the frame now
            if (plan, on) not in title_seen:
                title_seen.add((plan, on))
                file_log("Title bar (%s, %s): dark mode %s" % (plan, "dark" if on else "light", "ok" if r == 0 else "refused (0x%X)" % (r & 0xFFFFFFFF)))
        except Exception as e:  # noqa
            if "err" not in title_seen:
                title_seen.add("err")
                file_log("Title bar: could not be changed (%r)" % (e,))

    def dark_titlebar(win, on, delays=(0, 150)):
        """Title bar of this window in the colours of the theme, where Windows allows it (see above)."""
        plan = title_plan()
        if plan == "none":
            return
        if plan == "system":
            if "system" not in title_seen:
                title_seen.add("system")
                file_log("Title bar: Windows 10 with accent colour on title bars is on - title bars are left to the system")
            return
        try:
            win.update_idletasks()
        except tk.TclError:
            return
        for ms in delays:
            try:
                call = (lambda: titlebar_now(win, bool(on), plan))
                win.after(ms, call) if ms else call()
            except tk.TclError:
                pass

    def on_toplevel_map(e):
        w = e.widget
        try:
            if w.winfo_class() == "Toplevel" and not w.overrideredirect():  # not the hover hints
                dark_titlebar(w, theme_state["dark"], delays=(0, 150, 500))
        except tk.TclError:
            pass

    def refresh_titlebars():
        dark_titlebar(root, theme_state["dark"])
        for t in root.winfo_children():  # open Setup / dialogs
            if t.winfo_class() == "Toplevel" and not t.overrideredirect():
                dark_titlebar(t, theme_state["dark"], delays=(0, 150, 500))

    root.bind_class("Toplevel", "<Map>", on_toplevel_map, "+")
    root.bind("<Map>", lambda e: dark_titlebar(root, theme_state["dark"]) if e.widget is root else None, "+")

    def recolor(widget, tkc, lbc, topbg, ring_bg, ring_on):
        for c in widget.winfo_children():
            cls = c.winfo_class()
            try:
                if cls == "Text":
                    c.configure(**tkc)
                elif cls in ("Toplevel", "Canvas"):
                    c.configure(background=topbg)
                elif isinstance(c, StartButton):
                    c.ring_hidden, c.ring_shown = ring_bg, ring_on
                    c.configure(highlightbackground=ring_bg, highlightcolor=ring_bg)
                elif cls == "TCombobox":
                    pop = str(root.tk.eval("ttk::combobox::PopdownWindow %s" % c))
                    root.tk.call(pop + ".f.l", "configure", *sum((("-" + k, val) for k, val in lbc.items()), ()))
            except tk.TclError:
                pass
            recolor(c, tkc, lbc, topbg, ring_bg, ring_on)

    def apply_theme(dark):
        st = ttk.Style(root)
        theme_state["dark"] = bool(dark)
        if dark:
            p = DARK
            st.theme_use("clam")
            st.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"], troughcolor=p["field"],
                         bordercolor=p["border"], darkcolor=p["border"], lightcolor=p["border"], focuscolor=p["bg"],
                         selectbackground=p["sel"], selectforeground="#ffffff", insertcolor=p["fg"])
            st.map(".", foreground=[("disabled", p["dis"])])
            st.configure("TButton", background=p["btn"], padding=(8, 3))
            st.map("TButton", background=[("disabled", p["btn"]), ("pressed", p["btn_hi"]), ("active", p["btn_hi"])])
            if not dark_cb:
                px, gap = max(14, int(round(16 * scale))), max(4, int(round(5 * scale)))

                def pic(checked, border, fill, mark="#ffffff"):
                    rgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # noqa: E731
                    return tk.PhotoImage(data=base64.b64encode(checkbox_png(px, checked, rgb(border), rgb(fill), rgb(mark), gap)))

                dark_cb.update(off=pic(False, "#868b94", p["field"]), off_hot=pic(False, "#aab0ba", "#2a2c30"),
                               off_dis=pic(False, "#4a4d52", p["bg"]), on=pic(True, "#3574d4", "#3574d4"),
                               on_hot=pic(True, "#4a88ee", "#4a88ee"), on_dis=pic(True, "#44474c", "#44474c", "#8a8e96"))
                st.element_create("Dark.indicator", "image", dark_cb["off"],
                                  ("disabled", "selected", dark_cb["on_dis"]), ("disabled", dark_cb["off_dis"]),
                                  ("selected", "active", dark_cb["on_hot"]), ("selected", dark_cb["on"]),
                                  ("active", dark_cb["off_hot"]))
            st.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Dark.indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [("Checkbutton.label", {"sticky": "nswe"})]})]})])
            st.configure("TCheckbutton", background=p["bg"])
            st.map("TCheckbutton", background=[("active", p["bg"])])
            for name in ("TEntry", "TCombobox", "TSpinbox"):
                st.configure(name, fieldbackground=p["field"], foreground=p["fg"], insertcolor=p["fg"], bordercolor=p["border"],
                             arrowcolor=p["fg"], background=p["btn"])
                st.map(name, fieldbackground=[("disabled", p["bg"]), ("readonly", p["field"])],
                       foreground=[("disabled", p["dis"])], background=[("active", p["btn_hi"])],
                       selectbackground=[("!focus", p["field"])], selectforeground=[("!focus", p["fg"])])
            st.configure("TNotebook", background=p["bg"], bordercolor=p["border"])
            st.configure("TNotebook.Tab", background=p["btn"], foreground=p["fg"], padding=(10, 3), bordercolor=p["border"])
            st.map("TNotebook.Tab", background=[("selected", p["bg"]), ("active", p["btn_hi"])])
            st.configure("TScrollbar", background=p["btn"], troughcolor=p["field"], bordercolor=p["border"], arrowcolor=p["fg"],
                         darkcolor=p["btn"], lightcolor=p["btn"])
            st.map("TScrollbar", background=[("active", p["btn_hi"])])
            st.configure("TPanedwindow", background=p["bg"])
            tkc = dict(background=p["field"], foreground=p["fg"], insertbackground=p["fg"], selectbackground=p["sel"], selectforeground="#ffffff")
            lbc = dict(background=p["field"], foreground=p["fg"], selectbackground=p["sel"], selectforeground="#ffffff")
            topbg, ring_on = p["bg"], "#8ab4f8"
            TIP_COLORS.update(bg=p["tipbg"], fg=p["fg"])
            upd_lbl.configure(foreground=p["link"])
        else:
            st.theme_use(light_theme)
            tkc, lbc, topbg, ring_on = LIGHT_TK["text"], LIGHT_TK["list"], LIGHT_TK["top"], "#163f7a"
            TIP_COLORS.update(bg="#ffffe0", fg="#000000")
            upd_lbl.configure(foreground="#0b57d0")
        for opt, val in tkc.items():
            root.option_add("*Text." + opt, val)
        for opt, val in lbc.items():
            root.option_add("*TCombobox*Listbox." + opt, val)
            root.option_add("*Listbox." + opt, val)
        root.option_add("*Toplevel.background", topbg)
        root.option_add("*Canvas.background", topbg)
        root.configure(background=topbg)
        ring_bg = ttk.Style(root).lookup("TFrame", "background") or topbg
        recolor(root, tkc, lbc, topbg, ring_bg, ring_on)
        mode = "dark" if dark else "light"
        icon_mode["cur"] = mode
        setup_btn.configure(image=GEARS[mode])
        refresh_link()
        style_table(bool(dark))
        refresh_titlebars()
        align_later()

    # ---- update check: which release is the newest on GitHub (the program only tells; nothing is downloaded or installed)
    upd = {"found": "", "url": "", "busy": False, "last": 0.0}
    try:
        upd["last"] = float(saved.get("UPDATE_LAST") or 0)
    except (TypeError, ValueError):
        pass
    upd_status = tk.StringVar(value="")

    def show_update(tag, url):
        upd["found"], upd["url"] = str(tag or ""), str(url or "")
        if tag and parse_version(tag) > parse_version(VERSION):
            upd_lbl.configure(text="Update " + str(tag).lstrip("vV"))
            if not upd_lbl.winfo_manager():
                upd_lbl.pack(side="right", padx=(0, 10), before=cb_signin)
        else:
            upd_lbl.pack_forget()

    def open_update(_e=None):
        url = upd["url"]
        if url.startswith("https://github.com/%s/" % UPDATE_REPO):
            webbrowser.open(url)
        return "break"

    upd_lbl.bind("<Button-1>", open_update)
    for key in ("<space>", "<Return>"):
        upd_lbl.bind(key, open_update)
    upd_lbl.bind("<FocusIn>", lambda _e: upd_lbl.configure(relief="solid"), "+")
    upd_lbl.bind("<FocusOut>", lambda _e: upd_lbl.configure(relief="flat"), "+")

    def check_updates(report=None):
        if upd["busy"]:
            return
        upd["busy"] = True

        def work():
            try:
                tag, url = latest_release(UPDATE_REPO)
                err = ""
            except Exception as e:  # noqa
                tag, url, err = "", "", str(e) or e.__class__.__name__

            def done():
                upd["busy"] = False
                if tag:
                    upd["last"] = time.time()
                    show_update(tag, url)
                    if parse_version(tag) > parse_version(VERSION):
                        log("A new version of the Grabber is available: %s - %s" % (tag, url))
                else:
                    file_log("Update check failed: %s" % err)
                if report:
                    report(tag, err)
            auth_q.put(done)
        threading.Thread(target=work, daemon=True).start()

    def auto_update_check():
        if b["CHECK_UPDATES"].get() and time.time() - upd["last"] > 12 * 3600:
            check_updates()

    # ---- undo for entry fields, context menus, hover hints
    for ent, key in ((path_combo, "PATH"), (e_prefix, "PREFIX"),
                     (e_pics, "PICS"), (e_gal, "GALLERY")):
        UndoEntry(ent, v[key])
        attach_menu(ent)
    attach_menu(box, editable=False)

    for widget, text in (
            (upd_lbl, lambda: "Version %s is available (this is %s). Click to open its download page. The program installs nothing by itself." % (str(upd["found"]).lstrip("vV"), VERSION)),
            (cb_signin, lambda: signin_tip()),
            (cb_api, lambda: api_tip()),
            (path_combo, "Category folder: the place for one kind of models (characters, styles, poses ...). "
                         "Every model gets its own subfolder here, named after the model. "
                         "The drop-down list holds the most recently used folders (the number is set in Setup, 12 by default); its first line, \"Add output folder...\", "
                         "opens the folder chooser."),
            (cb_model, "Download the model file (LoRA, checkpoint ...). Untick to get only examples/gallery images and the description file."),
            (lbl_prefix, "Prefix: text put in front of the model file name (used only when Model file is ticked). "
                         "Handy for sorting models in a stack."),
            (e_gal, "How many images other users uploaded to the model's gallery to download: a number, all (can be thousands!), "
                    "or 0/empty for none. Needs the browser bridge, so this box is greyed out without it."),
            (e_prefix, "Text added to the start of the model file name, e.g. k2-pers-. Handy for sorting and grouping models "
                       "in file lists and in the model stacks of generation programs. The list holds the most recent prefixes (as many as folders; set in Setup)."),
            (e_pics, "How many example images/videos the model's author attached to the version: a number, all, or 0/empty for none."),
            (link_btn, "Link the prefix to the output folder. Rings joined: linked - the prefix is filled in whenever this folder is chosen; "
                       "click to unlink. Rings apart: not linked, or the prefix was changed - click to link the prefix typed now to this folder. "
                       "Editing the prefix is never blocked."),

            (undo_btn, "Undo the last change in the box you were working in (the link list by default). Ctrl+Z does the same."),
            (redo_btn, "Redo what was undone. Ctrl+Y does the same."),
            (hold_btn, "Hold: put the selected links on pause - START skips them until you press Resume. A model on hold holds its images too."),
            (sample_btn, "Save an empty task-file template (all keys, no data) and open it in your text editor."),
            (load_btn, "Load settings and links from a task txt file. Empty keys are ignored, so the file may hold only links."),
            (paste_btn, "Add the clipboard text to the end of the list."),
            (clear_btn, "Remove all links from the list."),
            (start_btn, lambda: {"start": "Start downloading all links in the list.", "locked": "Locked until the links are checked and decided.",
                                 "stop": "Stop after the current step.", "stopping": "Stopping after the current step ..."}[start_btn.mode]),
            (copylog_btn, "Copy the whole log to the clipboard."),
            (openlog_btn, "Open civitai_grabber.log in the default editor."),
            (cb_bridge, lambda: "Local port 127.0.0.1 for the browser extension, which fetches image pages with your logged-in browser.\nNow: %s." % bridge_status()),
            (setup_btn, "Setup: rarely changed options."),
            (help_btn, "Short help.")):
        Tooltip(widget, text)

    # the hint of the link table: only on the "Links" title and on the heading strip (Status ... Prefix), and inside the table
    TABLE_HELP = ("One row per link, with its own settings. A new link takes the values of the fields above and keeps them; to change links already "
                  "in the table, select them first (Ctrl or Shift for several). A model and the images below it share one colour; the images follow "
                  "the folder of their model (* = an image with a folder of its own). Finished links disappear, failed ones stay (after a restart "
                  "they come back on hold). Hold pauses the selected rows, a model holds its images. Delete removes, Ctrl+V pastes, Esc deselects, "
                  "a double click opens the page.")

    def over_heads(e):
        if tree.identify_region(e.x, e.y) != "heading":
            return False
        dc = tree["displaycolumns"]
        ids = [c[0] for c in TABLE_COLS] if dc in (("#all",), "#all") else list(dc)
        try:
            k = int(tree.identify_column(e.x)[1:]) - 1
        except ValueError:
            return False
        return 0 <= k < len(ids) and ids[k] in ("status", "link", "folder", "prefix")

    Tooltip(hdr_label, TABLE_HELP, wrap=560)
    Tooltip(tree, TABLE_HELP, when=over_heads, wrap=lambda: max(200, min(560, tree.winfo_width() - 30)),
            pos=lambda: (tree.winfo_rootx() + 8, tree.winfo_rooty() + 30))

    # ---- prefix linked to an output folder (every folder has its own link; the prefix stays editable)
    prefix_map = {}
    link_ctx = {"path_at": 0.0, "prefix_at": 0.0, "after": None}

    def norm_path(p):  # the same folder written with / or \\, with or without a trailing slash, in any letter case
        p = re.sub(r"/+", "/", (p or "").strip().replace("\\", "/")).rstrip("/")
        return p.lower()

    def link_state():
        key = norm_path(v["PATH"].get())
        if not key:
            return "off"
        if key not in prefix_map:
            return "free"
        return "linked" if prefix_map[key] == v["PREFIX"].get() else "changed"

    def refresh_link(*_):  # only the picture changes: joined rings = linked; apart (paler) = not linked or the prefix was changed
        st = link_state()
        link_btn.state(["disabled"] if st == "off" else ["!disabled"])
        link_btn.configure(image=ICONS[icon_mode["cur"]]["on" if st == "linked" else "off"], cursor="arrow" if st == "off" else "hand2")

    def toggle_link():
        key = norm_path(v["PATH"].get())
        if not key:
            return
        if link_state() == "linked":
            del prefix_map[key]
            log("The prefix is no longer linked to this folder.")
        else:
            prefix_map[key] = v["PREFIX"].get()
            log("The prefix \"%s\" is linked to this folder: it is filled in whenever the folder is chosen." % prefix_map[key])
        refresh_link()
        save_settings()

    def apply_link():
        link_ctx["after"] = None
        key = norm_path(v["PATH"].get())
        # a prefix set AFTER the folder (a task file, the user) wins over the link
        if key in prefix_map and link_ctx["prefix_at"] <= link_ctx["path_at"] and v["PREFIX"].get() != prefix_map[key]:
            v["PREFIX"].set(prefix_map[key])
        refresh_link()

    def on_path_change(*_):
        if ctx["loading"]:  # the field is only showing another row's value
            refresh_link()
            return
        link_ctx["path_at"] = time.time()
        if link_ctx["after"]:
            root.after_cancel(link_ctx["after"])
        link_ctx["after"] = root.after(300, apply_link)  # not while the path is still being typed
        refresh_link()

    def on_prefix_change(*_):
        link_ctx["prefix_at"] = time.time()
        refresh_link()

    link_btn.bind("<Button-1>", lambda _e: toggle_link() if link_state() != "off" else None)
    link_btn.bind("<FocusIn>", lambda _e: link_btn.configure(relief="solid"), "+")
    link_btn.bind("<FocusOut>", lambda _e: link_btn.configure(relief="flat"), "+")
    for key in ("<space>", "<Return>"):
        link_btn.bind(key, lambda _e: (toggle_link() if link_state() != "off" else None, "break")[1])

    # ---- logic
    lock_state = {"locked": False}

    def set_lock(lock):  # the token field (in Setup) is locked against accidental edits
        lock_state["locked"] = bool(lock)
        try:
            if "e_token" in setup_w:
                setup_w["e_token"].configure(state="readonly" if lock else "normal", show="\u2022" if lock else "")  # unlocked: the key is visible
                setup_w["lock_btn"].configure(text="Unlock" if lock else "Lock")
        except tk.TclError:
            pass

    def active_token():  # the API token counts only while "Connect via API" is ticked
        return v["TOKEN"].get().strip() if b["USE_API"].get() else ""

    def signin_tip():
        si = AUTH.signed_in()
        t = ("Sign in with your Civitai account (a browser window opens); untick to sign out. "
             "This connection has priority over the API token. Needs a free local port 8765.")
        return t + ("\nSigned in as %s." % ", ".join((u or "?") for u in si.values())) if si else t

    def api_tip():
        t = "Use your Civitai API key (Setup, tab Connection) when you are not signed in."
        return t if v["TOKEN"].get().strip() else t + "\nNo token entered yet."

    def refresh_signin_ui():
        signin_var.set(bool(AUTH.signed_in()))
        cb_signin.configure(state="normal", text="Connect via Sign-in")

    def on_signin_click():
        signin_var.set(bool(AUTH.signed_in()))  # the box shows the real state; it changes when the sign-in or sign-out really happens
        do_signin()

    def ask_site():
        """Small modal window: which Civitai site to sign in to. Returns 'civitai.red', 'civitai.com' or None."""
        win = tk.Toplevel(root)
        win.title("Sign in with Civitai")
        win.transient(root)
        first = next((site_of(x) for x in current_links() if site_of(x)), None)
        var = tk.StringVar(value=first or "civitai.red")
        ttk.Label(win, text="Which site do you use?").pack(anchor="w", padx=14, pady=(12, 4))
        for site in SITES:
            ttk.Radiobutton(win, text=site, value=site, variable=var).pack(anchor="w", padx=24)
        res = {"v": None}
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=14, pady=12)
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="Sign in", command=lambda: (res.update(v=var.get()), win.destroy())).pack(side="right", padx=6)
        win.grab_set()
        root.wait_window(win)
        return res["v"]

    def do_signin():
        if AUTH.signed_in():
            if choose("Sign out?\n\nThe program will use the API token again (if \"Connect via API\" is ticked) "
                      "(you can also revoke the access in your Civitai account: Connected Apps).", [("Sign out", True), ("Stay signed in", False)], escape=False):
                AUTH.sign_out()
                refresh_signin_ui()
                log("Signed out.")
            return
        site = ask_site()
        if not site:
            return
        cb_signin.configure(state="disabled", text="Waiting for the browser ...")

        def work():
            try:
                user = AUTH.sign_in(site, log=log)
            except Exception as e:  # noqa
                err = str(e)
                file_log("sign-in failed: %r" % (e,))
                auth_q.put(lambda: (refresh_signin_ui(), log("Sign-in failed: %s" % err),
                                    choose("Sign-in failed:\n%s" % err, [("OK", True)])))
            else:
                auth_q.put(lambda: (refresh_signin_ui(), log("Signed in on %s. From now on the sign-in is used "
                                                            "instead of the API token." % site)))
        threading.Thread(target=work, daemon=True).start()

    def push_recent(key, value):
        value = (value or "").strip()
        if not value:
            return
        lst = recent[key]
        lst[:] = [x for x in lst if os.path.normcase(x) != os.path.normcase(value)]
        lst.insert(0, value)
        del lst[RECENT_LIMIT.get(key, 10):]
        w = combos.get(key)
        if w is not None:  # the image subfolder box lives in Setup and exists only while it is open
            try:
                w.configure(values=([BROWSE_LABEL] + lst) if key == "PATH" else lst)
            except tk.TclError:
                pass

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
        if "ON_PARTIAL" in d:
            partial_var.set(next((lbl for lbl, code in PARTIAL_LABELS if code == str(d["ON_PARTIAL"]).lower()), "Ask"))
        if "PARTIAL_NOTICE" in d:
            notice_var.set(next((lbl for lbl, code in NOTICE_LABELS if code == str(d["PARTIAL_NOTICE"]).lower()), "After each job"))
        if d.get("TOKEN") and "USE_API" not in d:
            b["USE_API"].set(True)  # a task file with a token: the token is meant to be used
        set_lock(bool(v["TOKEN"].get().strip()))

    def collect_cfg():
        cfg = {k: v[k].get().strip() for k in TEXT_KEYS}
        for k in FLAG_KEYS:
            cfg[k] = "1" if b[k].get() else "0"
        cfg["TOKEN"] = active_token()
        for k in ROW_KEYS:
            if k in defaults:
                cfg[k] = defaults[k]
        cfg["EXISTING"] = next((code for lbl, code in EXISTING_LABELS if lbl == existing_var.get()), "ask")
        cfg["ON_PARTIAL"] = next((code for lbl, code in PARTIAL_LABELS if lbl == partial_var.get()), "ask")
        cfg["PARTIAL_NOTICE"] = next((code for lbl, code in NOTICE_LABELS if lbl == notice_var.get()), "each")
        return cfg

    # ---- the link table: a list of rows, a row = a link + ITS OWN settings. A link takes the values of the fields above the table
    # when it is added (the "next links" values) and keeps them, whatever the fields show later; selected rows are edited one by one.
    # A single image under a model has no folder of its own: it follows the model above it, until it is given a folder explicitly.
    ROW_KEYS = ("PATH", "PREFIX", "PICS", "GALLERY", "MODEL")  # the settings of one link ("MODEL" is "1" or "0")
    ROW_EXTRA = ("HOLD", "DIR", "WAS", "MODELDONE")  # HOLD "1" = on hold (WAS = the result it had when the program was closed: error/partial); DIR = the exact folder of an image whose model was finished while the image waited; MODELDONE "1" = the model is already downloaded, only images remain
    URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

    class Row:
        __slots__ = ("id", "url", "ov")  # ov: the values of this row (saved under the old name)

        def __init__(self, rid, url, ov=None):
            self.id, self.url = rid, url
            self.ov = {k: str(x) for k, x in (ov or {}).items() if k in ROW_KEYS or k in ROW_EXTRA}

    table = {"rows": [], "next": 1, "undo": [], "redo": [], "state": {}}  # state: link -> what the engine reports (running, error...)
    defaults = {}  # the values of the fields when nothing is selected: they are given to the links added NEXT
    ctx = {"loading": False}
    shown = {}  # row id of the tree -> (values, tag): what the table shows now

    def current_links():
        return [r.url for r in table["rows"]]

    def extract_urls(text):
        return [m.group(0).rstrip(".,;") for m in URL_RE.finditer(text or "")]

    def snapshot():
        return [(r.url, dict(r.ov)) for r in table["rows"]]

    def new_row(url, ov=None):
        r = Row(table["next"], url, ov)
        table["next"] += 1
        return r

    def push_undo():
        table["undo"].append(snapshot())
        del table["undo"][:-100]
        table["redo"].clear()

    def set_rows(snap):
        table["rows"] = [new_row(u, ov) for u, ov in snap]
        render_table(False)
        on_select()

    def undo_rows():
        if table["undo"]:
            table["redo"].append(snapshot())
            set_rows(table["undo"].pop())

    def redo_rows():
        if table["redo"]:
            table["undo"].append(snapshot())
            set_rows(table["redo"].pop())

    def field_default(key):
        if key == "MODEL":
            return "1" if b["MODEL"].get() else "0"
        return v[key].get().strip()

    def fresh_values(url, has_model):
        """What a new row takes from the fields. A single image under a model takes nothing: it follows the model."""
        if link_kind(url) == "image" and has_model:
            return {}
        return {k: defaults.get(k, field_default(k)) for k in ROW_KEYS}

    def layout():
        """(parent, pack): parent = row id of a single image -> the model row above it (the same rule the engine uses);
        pack = row id -> 0 or 1 for a model that has images and for those images (the colours alternate from pack to pack)."""
        parent, pack, last, n = {}, {}, None, -1
        for r in table["rows"]:
            kind = link_kind(r.url)
            if kind == "model":
                last = r
            elif kind == "image" and last is not None and not r.ov.get("DIR"):
                parent[r.id] = last
                if last.id not in pack:
                    n += 1
                    pack[last.id] = n % 2
                pack[r.id] = pack[last.id]
        return parent, pack

    def is_held(r, parent):
        if r.ov.get("HOLD") == "1":
            return True
        p = parent.get(r.id)
        return p is not None and p.ov.get("HOLD") == "1"  # the images of a model on hold wait with it

    def extra_for(u):
        """The settings a link is checked with: the common options plus the folder, prefix and Model file of ITS row."""
        cfg = collect_cfg()
        r = next((x for x in table["rows"] if x.url == u), None)
        if r is not None:
            e = effective(r)
            cfg.update({k: e[k] for k in ("PATH", "PREFIX", "MODEL")})
        return cfg

    def active_links():  # the links that will be downloaded: not on hold
        parent = layout()[0]
        return [r.url for r in table["rows"] if not is_held(r, parent)]

    def effective(r, parent=None):
        """The values of a row as the engine uses them; an image under a model has that model's folder unless it has its own."""
        if parent is None:
            parent = layout()[0]
        d = {k: defaults.get(k, field_default(k)) for k in ROW_KEYS}
        d.update({k: x for k, x in r.ov.items() if k in ROW_KEYS})
        p = parent.get(r.id)
        if p is not None:
            if "PATH" not in r.ov:
                d["PATH"] = effective(p, parent)["PATH"]
            d.update(PREFIX="", PICS="", GALLERY="", MODEL="")
        elif r.ov.get("DIR"):
            d.update(PATH=r.ov["DIR"], PREFIX="", PICS="", GALLERY="", MODEL="")
        return d

    def drop_same_as_parent():
        """An image whose own folder is the folder of its model is just following it (the * marks only a different folder)."""
        parent = layout()[0]
        for r in table["rows"]:
            p = parent.get(r.id)
            if p is not None and "PATH" in r.ov and norm_path(r.ov["PATH"]) == norm_path(effective(p, parent)["PATH"]):
                del r.ov["PATH"]

    def freeze_orphans():
        """An image that lost its model (the model row was removed and no model is above it) keeps the folder it has now."""
        parent = layout()[0]
        for r in table["rows"]:
            if link_kind(r.url) == "image" and r.id not in parent and "PATH" not in r.ov and not r.ov.get("DIR"):
                r.ov["PATH"] = defaults.get("PATH", field_default("PATH"))

    def add_urls(urls):
        """Adds new links (those not yet in the table) as one undo step; returns the added ones."""
        have = set(current_links())
        new = []
        for u in urls:
            if u not in have:
                have.add(u)
                new.append(u)
        if new:
            push_undo()
            has_model = any(link_kind(r.url) == "model" for r in table["rows"])
            for u in new:
                table["rows"].append(new_row(u, fresh_values(u, has_model)))
                has_model = has_model or link_kind(u) == "model"
            render_table()
            kids = tree.get_children()
            if kids:
                tree.see(kids[-1])
        return new

    def selected_rows():
        sel = set(tree.selection())
        return [r for r in table["rows"] if "r%d" % r.id in sel]

    def remove_rows(rows, remember=True):
        ids = {r.id for r in rows}
        if not ids:
            return
        if remember:
            push_undo()
        table["rows"] = [r for r in table["rows"] if r.id not in ids]
        for r in rows:
            table["state"].pop(r.url, None)
        freeze_orphans()
        render_table()
        on_select()

    def remove_selected(_e=None):
        remove_rows(selected_rows())
        return "break"

    def select_all(_e=None):
        tree.selection_set(tree.get_children())
        return "break"

    def clear_selection(_e=None):
        tree.selection_set(())

    def folder_chars():  # how many characters of a folder fit into the Folder column now
        try:
            w = int(tree.column("folder", "width"))
        except (tk.TclError, ValueError):
            w = 170
        return max(18, int((w - 14) / 6.5))

    def short_path(p, n=None):
        """The folder as far as it fits: without the closing backslash, and the cut falls between folder names, so all rows look alike."""
        p, n = (p or "").rstrip("\\/") or (p or ""), n or folder_chars()
        if len(p) <= n:
            return p
        cut = len(p) - (n - 1)
        m = re.search(r"[\\/]", p[cut - 1:])
        return "\u2026" + p[cut - 1 + m.start():] if m else "\u2026" + p[-(n - 1):]

    def status_of(r):
        st = table["state"].get(r.url)
        if st:
            return {"running": "running", "ok": "done"}.get(st, st)
        if not MODEL_LINK.search(r.url):
            return "image"
        cs = checker.state.get(r.url)
        if cs in (None, "queued"):
            return "checking"
        if cs == "ok":
            return model_type_label(checker.types.get(r.url)) or "ok"  # the link is fine: say what it is
        return {"problem": "warning", "kept": "kept"}.get(cs, "ok")

    def link_text(r, child, e):
        t = checker.titles.get(r.url)
        if not t:
            u = urllib.parse.urlparse(r.url)
            t = u.path + (("?" + u.query) if u.query else "")
        if link_kind(r.url) == "model" and e["MODEL"] != "1":
            t += "   [model downloaded]" if r.ov.get("MODELDONE") else "   [no model file]"
        return ("    " if child else "") + t

    def row_tag(r, status, held, pack):
        if status == "error":
            return "error"
        if status in ("warning", "partial", "kept"):
            return "warning"
        if held:
            return "hold"
        return "pack%d" % pack.get(r.id) if r.id in pack else ""

    def row_values(r, info, n=None):
        parent, pack = info
        child = r.id in parent
        e = effective(r, parent)
        held = is_held(r, parent)
        st = ("hold (%s)" % r.ov["WAS"] if r.ov.get("WAS") and r.ov.get("HOLD") == "1" else "hold") if held else status_of(r)
        star = " *" if child and "PATH" in r.ov else ""  # an image with a folder of its own, not the folder of its model
        return (st, link_text(r, child, e), short_path(e["PATH"], n) + star, e["PREFIX"], e["PICS"], e["GALLERY"]), row_tag(r, st, held, pack)

    def render_table(keep_selection=True):
        sel = set(tree.selection()) if keep_selection else set()
        tree.delete(*tree.get_children())
        shown.clear()
        info, n = layout(), folder_chars()
        for r in table["rows"]:
            vals, tag = row_values(r, info, n)
            iid = "r%d" % r.id
            tree.insert("", "end", iid=iid, values=vals, tags=(tag,) if tag else ())
            shown[iid] = (vals, tag)
        keep = [i for i in sel if tree.exists(i)]
        if keep:
            tree.selection_set(keep)

    def refresh_dynamic():  # statuses, titles and settings change by themselves (the link check, the run, the fields): update what differs
        info, n = layout(), folder_chars()
        for r in table["rows"]:
            iid = "r%d" % r.id
            old = shown.get(iid)
            if old is None or not tree.exists(iid):
                continue
            vals, tag = row_values(r, info, n)
            if vals != old[0]:
                tree.item(iid, values=vals)
            if tag != old[1]:
                tree.item(iid, tags=(tag,) if tag else ())
            shown[iid] = (vals, tag)

    def style_table(dark):
        st_ = ttk.Style(root)
        if dark:
            st_.configure("Treeview", background=DARK["field"], fieldbackground=DARK["field"], foreground=DARK["fg"], bordercolor=DARK["border"],
                          rowheight=22)
            st_.map("Treeview", background=[("selected", DARK["sel"])], foreground=[("selected", "#ffffff")])
            st_.configure("Treeview.Heading", background=DARK["btn"], foreground=DARK["fg"], bordercolor=DARK["border"], relief="flat")
            st_.map("Treeview.Heading", background=[("active", DARK["btn_hi"])])
            colors = ("#f2877d", "#f0a830", "#8ab4f8", "#c58af9", "#7d8590")
        else:
            st_.configure("Treeview", rowheight=22)
            colors = ("#b3261e", "#b45f06", "#0b57d0", "#8430ce", "#8a8f98")
        for tag_, col in zip(("error", "warning", "pack0", "pack1", "hold"), colors):
            tree.tag_configure(tag_, foreground=col)

    def apply_columns():  # the Examples and Gallery columns can be hidden (Setup): the room goes to the Link and Folder columns
        hide = {"pics": not b["COL_PICS"].get(), "gallery": not b["COL_GALLERY"].get()}
        tree.configure(displaycolumns=[c[0] for c in TABLE_COLS if not hide.get(c[0])])
        tree.column("folder", stretch=any(hide.values()))
        root.after(250, refresh_dynamic)

    resize_job = {"id": None}

    def on_tree_resize(_e=None):  # the Folder column shows as much of the path as fits
        if resize_job["id"]:
            root.after_cancel(resize_job["id"])
        resize_job["id"] = root.after(150, lambda: (resize_job.update(id=None), refresh_dynamic()))

    # ---- the fields above the table show the values for the NEXT links (nothing selected) or the values of the selected rows and change them
    def update_hold_btn():
        rows = selected_rows()
        parent = layout()[0]
        resume = bool(rows) and all(is_held(r, parent) for r in rows)
        hold_btn.configure(text="Resume" if resume else "Hold")
        hold_btn.state(["!disabled"] if rows else ["disabled"])

    def hold_toggle(_e=None):
        rows = selected_rows()
        if not rows:
            return
        parent = layout()[0]
        if all(is_held(r, parent) for r in rows):  # Resume (an image held only because of its model waits until the model is resumed)
            todo = [r for r in rows if r.ov.get("HOLD") == "1"]
            if todo:
                push_undo()
                for r in todo:
                    del r.ov["HOLD"]
                    r.ov.pop("WAS", None)
        else:
            push_undo()
            for r in rows:
                r.ov["HOLD"] = "1"
                r.ov.pop("WAS", None)
        refresh_dynamic()
        update_hold_btn()

    def hold_label():
        rows = selected_rows()
        parent = layout()[0]
        return "Resume" if rows and all(is_held(r, parent) for r in rows) else "Hold"

    def load_fields():
        """Shows the values for the next links, or the common values of the selected rows (nothing for values that differ)."""
        rows = selected_rows()
        parent = layout()[0]
        ctx["loading"] = True
        try:
            for k in ROW_KEYS:
                if rows:  # an image has only a folder; its other values mean nothing
                    vals = {effective(r, parent)[k] for r in rows if k == "PATH" or link_kind(r.url) != "image"}
                else:
                    vals = {defaults.get(k, field_default(k))}
                val = vals.pop() if len(vals) == 1 else None
                if k == "MODEL":
                    b["MODEL"].set(val == "1")
                    cb_model.state(["alternate"] if val is None else ["!alternate"])
                else:
                    v[k].set(val if val is not None else "")
        finally:
            ctx["loading"] = False
        n = len(rows)
        ui_state["only_img"] = bool(rows) and all(link_kind(r.url) == "image" for r in rows)
        for w in (e_pics,):
            w.configure(state="disabled" if ui_state["only_img"] else "normal")
        cb_model.state(["disabled"] if ui_state["only_img"] else ["!disabled"])
        hdr_var.set("Links (settings for: %s)" % ("next links" if not n else "%d selected" % n))
        refresh_link()
        sync_fields()
        update_hold_btn()

    def on_select(_e=None):
        load_fields()

    def on_field_change(key, *_):
        if ctx["loading"]:
            return
        val = ("1" if b["MODEL"].get() else "0") if key == "MODEL" else v[key].get().strip()
        rows = selected_rows()
        if key == "MODEL":
            cb_model.state(["!alternate"])
        if rows:
            parent = layout()[0]
            ids = {r.id for r in rows}
            for r in rows:
                if key == "PATH":
                    if r.id in parent and parent[r.id].id in ids:  # it follows its model, which changes too
                        r.ov.pop("PATH", None)
                    else:
                        r.ov["PATH"] = val
                        r.ov.pop("DIR", None)
                elif link_kind(r.url) != "image":
                    r.ov[key] = val
                    if key == "MODEL" and val == "1":
                        r.ov.pop("MODELDONE", None)
            drop_same_as_parent()
        else:
            defaults[key] = val
        refresh_dynamic()

    def push_defaults():
        for k in ROW_KEYS:
            defaults[k] = field_default(k)

    def migrate_rows():
        """Rows saved by v0.50 held only what differed from the common values: fill in the rest from the fields now."""
        parent = layout()[0]
        for r in table["rows"]:
            if r.id in parent:
                if saved.get("ROWS_VERSION", 1) < 2:
                    r.ov.pop("PATH", None)  # v0.50 ignored the folder of an image under a model
            else:
                for k in ROW_KEYS:
                    r.ov.setdefault(k, defaults.get(k, field_default(k)))

    def keep_for_later(u):
        """The engine finished a model but some images failed and the answer was 'keep': the row stays, the model is not downloaded again."""
        for r in table["rows"]:
            if r.url.strip() == u.strip():
                r.ov["MODEL"], r.ov["MODELDONE"] = "0", "1"
                table["state"][r.url] = "partial"
                break

    def freeze_held_children(u, folder):
        """A model is finished, but an image below it was put on hold and stays: it keeps the folder of that model."""
        model = next((r for r in table["rows"] if r.url.strip() == u.strip()), None)
        if model is None or link_kind(model.url) != "model":
            return
        parent = layout()[0]
        kids = [r for r in table["rows"] if parent.get(r.id) is model]
        for r in kids:
            if folder:
                r.ov["DIR"] = folder
                r.ov.pop("PATH", None)
            else:
                r.ov["PATH"] = effective(model, parent)["PATH"]

    def copy_links():
        rows = selected_rows() or table["rows"]
        root.clipboard_clear()
        root.clipboard_append("\n".join(r.url for r in rows))

    def open_row(_e=None):
        rows = selected_rows()
        if rows:
            webbrowser.open(rows[0].url)

    def log(msg):
        msg = scrub(msg)
        file_log(msg)
        q.put(msg)

    # ---- link check (a model link is checked a moment after it appears in the list, whatever way it got there)
    checker = LinkChecker(log=log, notify=BRIDGE.notify)
    start_ctx = {"pending": False, "force": False, "lock_since": None, "lock_told": False}

    BROWSE_LABEL = "Add output folder\u2026"
    path_prev = {"v": v["PATH"].get()}

    def browse_dir():
        cur = path_prev["v"]
        d = filedialog.askdirectory(title="Output folder", initialdir=cur if cur and os.path.isdir(cur) else None)
        if d:
            v["PATH"].set(os.path.normpath(d))

    def on_path_picked(_e=None):
        if v["PATH"].get() == BROWSE_LABEL:  # the first line of the list is not a folder: put the old value back and ask
            v["PATH"].set(path_prev["v"])
            browse_dir()

    def remember_path(*_):
        if v["PATH"].get() != BROWSE_LABEL:
            path_prev["v"] = v["PATH"].get()

    v["PATH"].trace_add("write", remember_path)
    path_combo.bind("<<ComboboxSelected>>", on_path_picked, "+")

    def create_sample():
        p = filedialog.asksaveasfilename(title="Save sample task file", initialfile="civitai_task.txt",
                                         defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(SAMPLE_TASK)
        except OSError as ex:
            choose("Cannot write the file:\n%s" % ex, [("OK", True)])
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
            choose("Cannot read the file:\n%s" % ex, [("OK", True)])
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
            use_file = choose("The task file and the window have different values:\n\n%s" % "\n".join(lines),
                              [("Use the file's values", True), ("Keep the window's values", False)], escape=False)
            if not use_file:
                for k in conflicts:
                    take.pop(k, None)
        clear_selection()
        load_fields()
        set_values(take)
        push_defaults()
        render_table()
        if urls:
            if current_links():
                ans = choose("The link list is not empty.\n\nReplace it with the links from the file, or add them to the end?",
                             [("Replace the list", True), ("Add to the end", False), ("Do not load the links", None)], escape=None)
                if ans is None:
                    urls = []
                elif ans:
                    push_undo()
                    table["rows"] = []
            if urls:
                add_urls(urls)
        log("Loaded task file: %s (%d links, %d settings)" % (p, len(urls), len(take)))

    focus_w = {"w": None}

    def remember_focus(e):
        w = e.widget
        if isinstance(w, (tk.Text, ttk.Entry)) and w is not box:
            focus_w["w"] = w
        elif w is tree:
            focus_w["w"] = None

    def target_widget():  # the box the user was working in; None = the link table
        w = focus_w["w"]
        try:
            if w is None or not w.winfo_exists() or str(w.cget("state")) != "normal":
                return None
        except tk.TclError:
            return None
        return w

    def do_undo():
        w = target_widget()
        undo_rows() if w is None else w.event_generate("<<Undo>>")

    def do_redo():
        w = target_widget()
        redo_rows() if w is None else w.event_generate("<<Redo>>")

    root.bind_all("<FocusIn>", remember_focus, "+")

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
        urls = extract_urls(text)
        if not urls:
            log("The clipboard holds no links.")
            return
        add_urls(urls)

    def add_links(links):
        new = add_urls(links)
        if new:
            checker.trust(new)
        log("Added %d link(s) from the browser%s" % (len(new), (" (%d already in the list)" % (len(links) - len(new))) if len(links) > len(new) else ""))

    def clear_urls():
        if table["rows"]:
            push_undo()
            table["rows"] = []
            table["state"].clear()
            render_table(False)
            on_select()

    def copy_log():
        root.clipboard_clear()
        root.clipboard_append(box.get("1.0", "end"))

    def open_log():
        if not open_path(LOGFILE):
            log("Cannot open the log file.")

    # ---- Setup window: rarely changed options (changes apply at once and are saved); more sections will join later
    setup_state = {"win": None}
    existing_var.trace_add("write", lambda *_: save_settings())
    b["COMFY"].trace_add("write", lambda *_: save_settings())

    def open_setup(tab=None):
        if setup_state["win"] is not None:
            try:
                setup_state["win"].deiconify()
                setup_state["win"].lift()
                setup_state["win"].focus_set()
                if tab in setup_state.get("tabs", {}):
                    setup_state["nb"].select(setup_state["tabs"][tab])
                return
            except tk.TclError:
                setup_state["win"] = None
        win = tk.Toplevel(root)
        setup_state["win"] = win
        win.title("Civitai Grabber - Setup")
        win.transient(root)
        try:
            if app_icon:
                win.iconphoto(False, app_icon)
        except tk.TclError:
            pass
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        dl = ttk.Frame(nb, padding=12)
        nb.add(dl, text="Downloads")
        con = ttk.Frame(nb, padding=12)
        nb.add(con, text="Connection")
        gen = ttk.Frame(nb, padding=12)
        nb.add(gen, text="Program")
        setup_state["nb"], setup_state["tabs"] = nb, {"Downloads": dl, "Connection": con, "Program": gen}
        if tab in setup_state["tabs"]:
            nb.select(setup_state["tabs"][tab])
        dl.columnconfigure(1, weight=1)
        tips = []

        ttk.Label(dl, text="If already downloaded:").grid(row=0, column=0, sticky="w", pady=4)
        cmb_ex = ttk.Combobox(dl, textvariable=existing_var, values=[lbl for lbl, _c in EXISTING_LABELS], state="readonly", width=16)
        cmb_ex.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=4)
        tips.append((cmb_ex, "What to do with a model or image that was downloaded before. Ask: a window asks every time (default). "
                             "Skip: it is passed by. Download again: it is downloaded again and overwritten."))

        ttk.Label(dl, text="If examples or gallery fail:").grid(row=1, column=0, sticky="w", pady=4)
        row_p = ttk.Frame(dl)
        row_p.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=4)
        cmb_pa = ttk.Combobox(row_p, textvariable=partial_var, values=[lbl for lbl, _c in PARTIAL_LABELS], state="readonly", width=16)
        cmb_pa.pack(side="left")
        ttk.Label(row_p, text="  Notify:").pack(side="left")
        cmb_no = ttk.Combobox(row_p, textvariable=notice_var, values=[lbl for lbl, _c in NOTICE_LABELS], state="readonly", width=20)
        cmb_no.pack(side="left", padx=(6, 0))

        def sync_notice(*_):  # a question cannot be left unasked: "Don't notify" is only for Keep in queue / Finish
            vals = [lbl for lbl, _c in NOTICE_LABELS]
            if partial_var.get() == "Ask":
                vals = vals[:2]
                if notice_var.get() not in vals:
                    notice_var.set(vals[0])
            cmb_no.configure(values=vals)
        cmb_pa.bind("<<ComboboxSelected>>", sync_notice, "+")
        sync_notice()
        tips.append((cmb_pa, "A model was downloaded but some of its example or gallery images were not (the log shows which). Ask: you decide for those models "
                             "(finish as it is, or keep them in the list with the Model file switched off, so the next run completes only the images). "
                             "Keep in queue / Finish: it is done without asking."))
        tips.append((cmb_no, "When to tell you about such models: after each job, or once at the end of the list. Don't notify is possible only for "
                             "Keep in queue and Finish (the log always has the details)."))

        ttk.Label(dl, text="Description file:").grid(row=2, column=0, sticky="w", pady=4)
        row_d = ttk.Frame(dl)
        row_d.grid(row=2, column=1, sticky="we", padx=(10, 0), pady=4)
        e_dscr = ttk.Entry(row_d, textvariable=v["DSCR"], width=16)
        e_dscr.pack(side="left", fill="x", expand=True, ipady=2)
        cb_dname = ttk.Checkbutton(row_d, text="Name as model", variable=b["DSCR_AS_MODEL"])
        cb_dname.pack(side="left", padx=(10, 0))

        cb_sub = ttk.Checkbutton(dl, text="Image subfolder:", variable=b["USE_SUBFOLDER"])
        cb_sub.grid(row=3, column=0, sticky="w", pady=4)
        e_img = ttk.Combobox(dl, textvariable=v["IMGFOLDER"], width=30, values=recent["IMGFOLDER"])
        e_img.grid(row=3, column=1, sticky="we", padx=(10, 0), pady=4, ipady=2)
        combos["IMGFOLDER"] = e_img
        for ent, key in ((e_dscr, "DSCR"), (e_img, "IMGFOLDER")):
            UndoEntry(ent, v[key])
            attach_menu(ent)
        setup_w.update(e_dscr=e_dscr, e_img=e_img)

        row_o = ttk.Frame(dl)
        row_o.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 3))
        cb_video = ttk.Checkbutton(row_o, text="Include videos", variable=b["VIDEO"])
        cb_orig = ttk.Checkbutton(row_o, text="Original file names", variable=b["ORIGINAL"])
        cb_webp = ttk.Checkbutton(row_o, text="Convert WebP to JPG", variable=b["WEBP2JPG"], command=on_webp)
        cb_video.pack(side="left")
        cb_orig.pack(side="left", padx=(16, 0))
        cb_webp.pack(side="left", padx=(16, 0))
        cb_rename = ttk.Checkbutton(dl, text="Name ID-like model files by title", variable=b["RENAME_ID"])
        cb_comfy = ttk.Checkbutton(dl, text="Save ComfyUI workflow as .json (experimental)", variable=b["COMFY"])
        for r, w in enumerate((cb_rename, cb_comfy), start=5):
            w.grid(row=r, column=0, columnspan=2, sticky="w", pady=3)
        tips.append((cb_comfy, "Experimental: if the image metadata holds a ComfyUI workflow, it is saved as a .json next to the image."))

        ttk.Label(con, text="API token:").grid(row=0, column=0, sticky="w", pady=4)
        e_token = ttk.Entry(con, textvariable=v["TOKEN"], show=("\u2022" if lock_state["locked"] else ""), width=38)
        e_token.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=4, ipady=2)
        lock_btn = ttk.Button(con, text="Unlock" if lock_state["locked"] else "Lock", width=9)
        lock_btn.grid(row=0, column=2, padx=(6, 0), pady=4)
        ttk.Label(con, wraplength=520, justify="left",
                  text="Your Civitai API key (account settings, API keys). It is used when \"Connect via API\" is ticked in the main "
                       "window and you are not signed in. It is saved in civitai_grabber_settings.json next to the script, in plain "
                       "text - do not share that file.").grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        UndoEntry(e_token, v["TOKEN"])
        attach_menu(e_token)
        e_token.configure(state="readonly" if lock_state["locked"] else "normal")
        setup_w.update(e_token=e_token, lock_btn=lock_btn)
        lock_btn.configure(command=lambda: set_lock(str(e_token.cget("state")) != "readonly"))
        tips.append((e_token, "Your Civitai API key (account settings, API keys). Saved in civitai_grabber_settings.json next to the script."))
        tips.append((lock_btn, "Lock the token field against accidental edits / unlock it to change the token."))

        ttk.Label(gen, text="Folder and prefix history:").grid(row=0, column=0, sticky="w", pady=4)
        lim_var = tk.StringVar(value=str(RECENT_LIMIT["PATH"]))
        spn = ttk.Spinbox(gen, from_=5, to=30, width=6, textvariable=lim_var)
        spn.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=4)
        tips.append((spn, "How many recently used output folders and prefixes the two drop-down lists keep (5 to 30). "
                          "Lowering the number cuts the oldest entries from the lists."))

        def apply_limit(*_):
            try:
                n = int(lim_var.get())
            except ValueError:
                return
            if not 5 <= n <= 30:
                return  # not applied while a wrong number is typed
            RECENT_LIMIT["PATH"] = RECENT_LIMIT["PREFIX"] = n
            del recent["PATH"][n:]
            del recent["PREFIX"][n:]
            path_combo.configure(values=[BROWSE_LABEL] + recent["PATH"], height=n + 1)
            e_prefix.configure(values=recent["PREFIX"], height=n)
            save_settings()

        lim_var.trace_add("write", apply_limit)
        row_t = ttk.Frame(gen)
        row_t.grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 4))
        cb_dark = ttk.Checkbutton(row_t, text="Dark theme", variable=b["DARK"],
                                  command=lambda: (apply_theme(bool(b["DARK"].get())), save_settings()))
        cb_dark.pack(side="left")
        cb_bdark = ttk.Checkbutton(row_t, text="Dark window of the browser extension", variable=b["BRIDGE_DARK"], command=save_settings)
        cb_bdark.pack(side="left", padx=(16, 0))
        row_c = ttk.Frame(gen)
        row_c.grid(row=2, column=0, columnspan=2, sticky="we", pady=4)
        ttk.Label(row_c, text="Table columns:").pack(side="left")

        def on_columns():
            apply_columns()
            save_settings()
        cb_cp = ttk.Checkbutton(row_c, text="Examples", variable=b["COL_PICS"], command=on_columns)
        cb_cg = ttk.Checkbutton(row_c, text="Gallery", variable=b["COL_GALLERY"], command=on_columns)
        cb_cp.pack(side="left", padx=(10, 0))
        cb_cg.pack(side="left", padx=(10, 0))
        row_u = ttk.Frame(gen)
        row_u.grid(row=3, column=0, columnspan=2, sticky="we", pady=4)
        cb_upd = ttk.Checkbutton(row_u, text="Check for updates on start", variable=b["CHECK_UPDATES"])
        cb_upd.pack(side="left")

        def report(tag, err):
            if not tag:
                upd_status.set("Could not check (%s)" % (str(err).split(";")[0][:70] if err else "no connection?"))
            elif parse_version(tag) > parse_version(VERSION):
                upd_status.set("New version available: %s" % str(tag).lstrip("vV"))
            else:
                upd_status.set("This is the latest version (%s)" % VERSION)

        def check_now():
            upd_status.set("Checking ...")
            check_updates(report)

        btn_upd = ttk.Button(row_u, text="Check now", command=check_now)
        btn_upd.pack(side="left", padx=(14, 0))
        ttk.Label(row_u, textvariable=upd_status).pack(side="left", padx=(10, 0))
        if title_plan() == "system":  # Windows 10 paints active title bars with the accent colour: say so, offer the setting
            row_h = ttk.Frame(gen)
            row_h.grid(row=4, column=0, columnspan=2, sticky="we", pady=(14, 2))
            ttk.Label(row_h, wraplength=520, justify="left",
                      text="Windows 10 paints the title bar of the active window with the accent colour (Windows Settings > Personalization "
                           "> Colors > \"Title bars and window borders\"), so title bars stay light with the dark theme. Turn that "
                           "setting off to get dark title bars.").pack(anchor="w")

            def open_colors():
                try:
                    os.startfile("ms-settings:colors")
                except OSError:
                    pass
            ttk.Button(row_h, text="Open Windows color settings", command=open_colors).pack(anchor="w", pady=(6, 0))
        tips.append((cb_cp, "Show the Examples column in the link table. Hidden columns give their room to the Link and Folder columns; "
                            "the values stay in the rows and the fields above the table still work."))
        tips.append((cb_cg, "Show the Gallery column in the link table. Hidden columns give their room to the Link and Folder columns; "
                            "the values stay in the rows and the fields above the table still work."))
        tips.append((cb_dark, "Dark colours for the whole program. Windows system message boxes stay light."))
        tips.append((cb_bdark, "Draws the small window of the browser extension in dark colours. It is a setting of its own: it does not have to match the "
                               "program's theme. The extension remembers it when the program is closed."))
        tips.append((cb_upd, "At start (not more than once in 12 hours) the program asks github.com which release is the newest "
                             "and shows a link at the top if it is newer than this one. Nothing is downloaded or installed by itself."))
        for widget, text in tips:
            Tooltip(widget, text)
        for widget, text in (
            (cb_sub, "Save single image links into the subfolder below. Only for a run that has NO model link before "
                     "the image links; images that follow a model link always go into that model's folder."),
            (cb_dname, "Name the description file after the model. Its extension (.txt / .md) is taken from the "
                       "Description file box; images saved without a model still use the name in that box."),
            (e_img, "Subfolder name or nested path (a/b/c) inside the category folder; a full path such as "
                    "d:\\AI\\pics = exactly that folder. Paste it, no Browse needed. The list holds recent entries."),
            (e_dscr, "Name of the description file written next to the model (.txt or .md; no extension = .txt). "
                     "Markdown is used for .md. EMPTY = no description file is written."),
            (cb_video, "Also download video examples. They count towards the number of examples."),
            (cb_rename, "A model file whose name is only an ID (26 random characters, e.g. from the Civitai trainer) is saved under the model "
                        "title (with the version name when the model has several versions). The original name is written to the description file."),
            (cb_orig, "Try to read the original file name from the image page. Pages are often blocked for scripts "
                      "(HTTP 403); then the name from the image address is used."),
            (cb_webp, "Convert downloaded WebP images to JPG (quality 95). Needs Pillow: py -m pip install pillow"),
        ):
            Tooltip(widget, text)
        sync_setup()

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=10)

        def close(_e=None):
            setup_state["win"] = None
            setup_w.clear()
            setup_state.pop("tabs", None)
            combos.pop("IMGFOLDER", None)
            win.destroy()

        ttk.Button(bar, text="Close", command=close).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Escape>", close)
        apply_calm(win)
        win.update_idletasks()
        w0, h0 = win.winfo_reqwidth(), win.winfo_reqheight()
        win.minsize(w0, h0)
        win.maxsize(int(w0 * 1.6), 4000)
        win.resizable(True, False)  # widened a bit if wanted; the height always follows the content
        x = root.winfo_rootx() + max(0, (root.winfo_width() - w0) // 2)
        y = root.winfo_rooty() + max(0, (root.winfo_height() - h0) // 3)
        win.geometry("+%d+%d" % (x, y))
        win.wait_visibility()  # focus only after the window is shown: set before, it leaves the title bar light until the next click
        win.focus_set()

    def show_help():
        win = tk.Toplevel(root)
        win.title("Civitai Grabber - help")
        win.geometry("760x640+%d+%d" % (root.winfo_rootx() + 30, root.winfo_rooty() + 30))
        if app_icon is not None:
            win.iconphoto(False, app_icon)
        bar = ttk.Frame(win, padding=6)
        bar.pack(side="bottom", fill="x")
        status = ttk.Label(bar, text="")
        txt = ScrollText(win, wrap="word", font=mono)
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
            if choose(CONSENT_TEXT, [("Allow", True), ("Do not allow", False)], parent=win, escape=False):
                err = register_launcher()
                if err:
                    choose(err, [("OK", True)], parent=win)
                launch_state["asked"] = True
                save_settings()
            refresh()

        def remove():
            err = unregister_launcher()
            if err:
                choose(err, [("OK", True)], parent=win)
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
        elif waiting and checker.warned(current_links()):  # a link with a warning is in the list: yellow, not the peaceful green
            icon, mode, frac = "idle", "paused", 1.0
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
        """Remove the first row of the table whose link is u (a finished link); what could be undone before is forgotten."""
        for r in table["rows"]:
            if r.url.strip() == u.strip():
                remove_rows([r], remember=False)
                table["undo"].clear()
                table["redo"].clear()
                return

    def ask(msg, yes="Yes", no="No"):
        ev, holder = threading.Event(), {}
        ask_q.put((msg, holder, ev, (yes, no)))
        while not ev.wait(0.3):
            if stop.is_set():
                return False
        return holder.get("ans", False)

    def ask_cleanup(msg, yes="Yes", no="No"):
        ev, holder = threading.Event(), {}
        ask_q.put((msg, holder, ev, (yes, no)))
        ev.wait(300)
        return holder.get("ans", False)

    ASK_CLEANUP["fn"] = ask_cleanup

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
                  wraplength=720, justify="left", foreground=("#a9b4c0" if b["DARK"].get() else "#555")).pack(anchor="w", padx=14, pady=(6, 0))

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

    def choose(text, buttons, title="Civitai Grabber", parent=None, escape=None):
        """A message box in the colours of the program, with buttons that say what they do (instead of Yes / No).
        buttons: [(label, value), ...] left to right; Esc and the close button give `escape`. No button has the focus at first
        (the window may open while you are typing); Tab and Enter work as everywhere in the program."""
        if CHOOSE_HOOK["fn"]:  # tests
            return CHOOSE_HOOK["fn"](text, buttons)
        owner = parent or root
        win = tk.Toplevel(owner)
        win.title(title)
        win.transient(owner)
        try:
            if app_icon:
                win.iconphoto(False, app_icon)
        except tk.TclError:
            pass
        result = {"v": escape}
        ttk.Label(win, text=text, wraplength=520, justify="left").pack(anchor="w", padx=16, pady=(14, 4))
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=16, pady=(8, 14))

        def done(val):
            result["v"] = val
            win.destroy()

        for label, val in reversed(buttons):
            ttk.Button(bar, text=label, command=lambda v=val: done(v)).pack(side="right", padx=(8, 0))
        win.protocol("WM_DELETE_WINDOW", lambda: done(escape))
        win.bind("<Escape>", lambda _e: done(escape))
        win.update_idletasks()
        x = owner.winfo_rootx() + max(0, (owner.winfo_width() - win.winfo_width()) // 2)
        y = owner.winfo_rooty() + max(0, (owner.winfo_height() - win.winfo_height()) // 3)
        win.geometry("+%d+%d" % (x, y))
        win.grab_set()
        win.focus_set()
        owner.wait_window(win)
        return result["v"]

    def ask_remove_links(rows, labels=("Remove link", "Keep link")):
        """Modal window about links that cannot be downloaded now; rows = [(link, title, reason)].
        Returns the links to remove from the list. Closing the window keeps everything (Enter does nothing on purpose:
        the window may open while you are typing somewhere else)."""
        win = tk.Toplevel(root)
        win.title("Civitai Grabber - link check")
        win.transient(root)
        try:
            if app_icon:
                win.iconphoto(False, app_icon)
        except tk.TclError:
            pass
        result = {"gone": []}
        ticks = []
        url_fg = "#a9b4c0" if b["DARK"].get() else "#555"
        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")
        if len(rows) == 1:
            u, title, reason = rows[0]
            ttk.Label(win, text=title, font=bold, wraplength=560, justify="left").pack(anchor="w", padx=14, pady=(12, 2))
            ttk.Label(win, text=reason, wraplength=560, justify="left").pack(anchor="w", padx=14, pady=(0, 6))
            ttk.Label(win, text=u, wraplength=560, justify="left", foreground=url_fg).pack(anchor="w", padx=14)
            yes_text, no_text = labels
        else:
            ttk.Label(win, text="%d links cannot be downloaded now. Ticked links will be removed from the list:" % len(rows),
                      wraplength=600, justify="left").pack(anchor="w", padx=14, pady=(12, 6))
            holder = ttk.Frame(win)
            holder.pack(fill="both", expand=True, padx=14)
            canvas = tk.Canvas(holder, height=min(360, 74 * len(rows)), width=620, highlightthickness=0)
            sb = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
            inner = ttk.Frame(canvas)
            inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=sb.set)
            canvas.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
            for u, title, reason in rows:
                var = tk.BooleanVar(value=True)
                ticks.append((u, var))
                ttk.Checkbutton(inner, text=title, variable=var).pack(anchor="w", pady=(6, 0))
                ttk.Label(inner, text=reason, wraplength=560, justify="left").pack(anchor="w", padx=(24, 0))
                ttk.Label(inner, text=u, wraplength=560, justify="left", foreground=url_fg).pack(anchor="w", padx=(24, 0))
            yes_text, no_text = "Remove ticked", "Keep all"
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=14, pady=12)

        def yes():
            result["gone"] = [rows[0][0]] if len(rows) == 1 else [u for u, var in ticks if var.get()]
            win.destroy()

        def no():
            win.destroy()

        ttk.Button(bar, text=no_text, command=no).pack(side="right")
        ttk.Button(bar, text=yes_text, command=yes).pack(side="right", padx=(0, 8))
        win.protocol("WM_DELETE_WINDOW", no)
        win.bind("<Escape>", lambda _e: no())
        win.update_idletasks()
        x = root.winfo_rootx() + max(0, (root.winfo_width() - win.winfo_width()) // 2)
        y = root.winfo_rooty() + max(0, (root.winfo_height() - win.winfo_height()) // 3)
        win.geometry("+%d+%d" % (x, y))
        win.grab_set()
        win.focus_set()
        root.wait_window(win)
        return result["gone"]

    def images_below(u, links):
        """Image links that follow a model link in the list (they are saved into that model's folder)."""
        if u not in links:
            return []
        out = []
        for nxt in links[links.index(u) + 1:]:
            if MODEL_LINK.search(nxt):
                break
            if re.search(r"/images/\d+", nxt):
                out.append(nxt)
        return out

    def handle_problems(rows):
        tb_flash(2)
        items = []
        for u, res in rows:
            title = (res.get("name") or "Model") + ((" - " + res["ver"]) if res.get("ver") else "")
            items.append((u, title, res.get("text") or "This link cannot be downloaded."))
        kind = rows[0][1].get("kind") if len(rows) == 1 else ""
        gone = list(ask_remove_links(items, ("Exclude link", "Download to new folder") if kind == "folder" else ("Remove link", "Keep link")))
        links = current_links()
        for u in list(gone):
            below = [x for x in images_below(u, links) if x not in gone]
            if below and choose(
                    "%d image link(s) follow the removed model link in the list and belong to it.\n\nRemove them too? "
                    "(If you keep them, they will be saved into the folder of the model above them, or into the output folder.)" % len(below),
                    [("Remove them too", True), ("Keep them", False)], escape=False):
                gone.extend(below)
        for u in gone:
            remove_line(u)
            BRIDGE.notify("dismiss", u)  # the browser extension (0.17+) takes the link off its "Needs attention" list
        kept = [u for u, _ in rows if u not in gone]
        checker.settle(gone, kept)
        log("Link check: %d link(s) removed from the list, %d kept." % (len(gone), len(kept)))

    def pump():
        try:
            while True:
                auth_q.get_nowait()()
        except queue.Empty:
            pass
        try:
            while True:
                msg = q.get_nowait()
                box.configure(state="normal")
                box.insert("end", msg + "\n")
                box.see("end")
                box.configure(state="disabled")
        except queue.Empty:
            pass
        notices = []
        try:
            while True:
                u_job, st_job = job_q.get_nowait()
                if st_job.startswith("notice:"):
                    notices.append(st_job[7:])
                elif st_job == "keep":
                    keep_for_later(u_job)
                else:
                    table["state"][u_job] = st_job
        except queue.Empty:
            pass
        for text_ in notices:
            choose(text_, [("OK", True)])
        try:
            while True:
                u_done, folder_done = done_q.get_nowait()
                freeze_held_children(u_done, folder_done)  # an image on hold keeps the folder of its finished model
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
            msg, holder, ev, names = ask_q.get_nowait()
            holder["ans"] = choose(msg, [(names[0], True), (names[1], False)], escape=False)
            ev.set()
        except queue.Empty:
            pass
        try:
            c_title, c_rows, c_default, c_holder, c_ev = choose_q.get_nowait()
            c_holder["ans"] = show_chooser(c_title, c_rows, c_default)
            c_ev.set()
        except queue.Empty:
            pass
        rows = checker.tick(current_links(), active_token(), extra_for)
        if rows:
            handle_problems(rows)
        refresh_dynamic()
        t = state["thread"]
        if t is not None and not t.is_alive():
            state["thread"] = None
            tb_finish()
            start_btn.set_mode("start")
        if state["thread"] is None:
            waiting = checker.unsettled(active_links())
            want = "disabled" if waiting else "normal"
            if str(start_btn.cget("state")) != want:
                start_btn.configure(state=want)
            if waiting:
                start_ctx["lock_since"] = start_ctx["lock_since"] or time.time()
                if time.time() - start_ctx["lock_since"] > 3 and not start_ctx["lock_told"]:
                    start_ctx["lock_told"] = True
                    log("START is locked until %d link(s) are checked and decided." % waiting)
            else:
                start_ctx["lock_since"], start_ctx["lock_told"] = None, False
                if start_ctx["pending"]:
                    start_ctx["pending"], start_ctx["force"] = False, True
                    try:
                        start()
                    finally:
                        start_ctx["force"] = False
        bt = "Browser bridge: ports busy" if bridge_status().startswith("could not") else "Browser bridge"
        if str(cb_bridge.cget("text")) != bt:  # a failure to start is the only status the box shows itself
            cb_bridge.configure(text=bt)
        tb_tick()
        if (not launch_state["asked"] and BRIDGE.connected() and sys.platform.startswith("win")
                and not launcher_registered()):
            launch_state["asked"] = True  # ask once, when the extension has connected for the first time
            if choose(CONSENT_TEXT, [("Allow", True), ("Do not allow", False)], escape=False):
                err = register_launcher()
                log("Launch from the browser allowed." if not err else "Could not write the registry entry: %s" % err)
            save_settings()
        want = "normal" if (b["BRIDGE"].get() and BRIDGE.connected() and not ui_state["only_img"]) else "disabled"
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
            if choose("WebP conversion needs the Pillow library, which is not installed for the Python "
                      "that runs this script:\n%s\n\nInstall it now (pip install pillow)?" % python_for_pip(),
                      [("Install now", True), ("Not now", False)], escape=False):
                threading.Thread(target=install_pillow, daemon=True).start()

    def worker(jobs, cfg, need_pillow=False):
        try:
            if need_pillow:
                install_pillow()
            run_jobs(jobs, log, stop, ask, lambda u: done_q.put((u, STATE.get("model_folder"))), fallback_cfg=cfg, on_job=lambda u, st: job_q.put((u, st)))
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
            d["TOKEN"] = v["TOKEN"].get().strip()  # the saved token stays even while "Connect via API" is off
            d["UPDATE_LAST"], d["UPDATE_FOUND"], d["UPDATE_URL"] = upd["last"], upd["found"], upd["url"]
            d["URLS"] = "\n".join(current_links())  # (older versions read the links from here)
            rows_ = []
            for r in table["rows"]:
                ov_ = dict(r.ov)
                last_ = table["state"].get(r.url)
                if last_ in ("error", "partial") and ov_.get("HOLD") != "1":  # after a restart it is history: on hold until the user decides
                    ov_["HOLD"], ov_["WAS"] = "1", last_
                rows_.append({"url": r.url, "ov": ov_})
            d["ROWS"] = rows_
            d["ROWS_VERSION"] = 2
            d["LAUNCH_ASKED"] = launch_state["asked"]
            d["RECENT"] = list(recent["PATH"])
            d["RECENT_PREFIX"] = list(recent["PREFIX"])
            d["RECENT_SUB"] = list(recent["IMGFOLDER"])
            d["RECENT_PATHS_LIMIT"] = RECENT_LIMIT["PATH"]
            d["PREFIX_BY_PATH"] = dict(prefix_map)
            d["WINDOW"] = window_state()
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def start():
        cfg = collect_cfg()
        parent = layout()[0]
        active = [r for r in table["rows"] if not is_held(r, parent)]
        urls = [r.url for r in active]
        if not urls:
            log("All links are on hold - select the ones to start, press Resume, then START." if table["rows"] else "The link list is empty.")
            return
        if checker.unsettled(urls):
            log("The link check is still running - START works when it is done.")
            return
        if not start_ctx["force"]:
            again = checker.recheck_kept(urls)
            if again:  # nothing is remembered about "keep": the links are asked about once more
                start_ctx["pending"] = True
                log("Checking again the %d link(s) you chose to keep ..." % again)
                return
        KEPT_LINKS.clear()
        KEPT_LINKS.update(u for u in urls if checker.state.get(u) == "kept")
        if not cfg["DSCR"] and cfg["DSCR_AS_MODEL"] != "1":
            if not choose("The description file name is empty: no description and no generation metadata will be written.\n\nContinue anyway?",
                          [("Continue", True), ("Cancel", False)], escape=False):
                return
        off = [r for r in active if re.search(r"/models/\d+", r.url) and effective(r, parent)["MODEL"] != "1" and not r.ov.get("MODELDONE")]
        if off:
            ans = choose("The \"Model file\" option is OFF.\n\n%d link(s) in the list lead to models: only their examples and "
                         "description will be downloaded, without the model files." % len(off),
                         [("Turn Model file ON and start", True), ("Start without model files", False), ("Go back", None)], escape=None)
            if ans is None:
                return
            if ans:
                defaults["MODEL"] = "1"
                for r in active:
                    if r.ov.get("MODEL") == "0":
                        r.ov["MODEL"] = "1"
                load_fields()
                refresh_dynamic()
                cfg = collect_cfg()
        need_pillow = False
        if cfg["WEBP2JPG"] == "1":
            try:
                import PIL  # noqa
            except ImportError:
                need_pillow = choose("WebP to JPG conversion needs the Pillow library, which is not installed for the "
                                     "Python that runs this script:\n%s\n\nInstall it now (pip install pillow)?" % python_for_pip(),
                                     [("Install now", True), ("Not now", False)], escape=False)
        jobs = make_jobs(urls, cfg)  # the parent of an image is found in the same order as in the table (held rows go with their model)
        for job, r in zip(jobs, active):
            e = effective(r, parent)
            if r.id in parent:  # an image under a model: the folder of the model, or a folder of its own
                job.cfg["PATH"] = e["PATH"]
                if "PATH" in r.ov:
                    job.cfg["OWN_FOLDER"] = "1"
            else:
                job.cfg.update({k: e[k] for k in ROW_KEYS})  # every job takes the values of its own row
                if r.ov.get("DIR"):
                    job.cfg["DIR"] = r.ov["DIR"]
        held_n = len(table["rows"]) - len(active)
        if held_n:
            log("%d link(s) on hold are skipped." % held_n)
        for key in ("PATH", "PREFIX", "IMGFOLDER"):
            push_recent(key, cfg[key])
        for r in active:
            e = effective(r, parent)
            for key in ("PATH", "PREFIX"):
                if e.get(key):
                    push_recent(key, e[key])
        table["state"].clear()
        save_settings()
        stop.clear()
        start_btn.set_mode("stop")
        start_ctx["t0"] = time.time()
        t = threading.Thread(target=worker, args=(jobs, cfg, need_pillow), daemon=True)
        state["thread"] = t
        t.start()

    def do_stop():
        stop.set()
        start_btn.set_mode("stopping")
        log("Stopping after the current step…")

    def main_button():  # one button: START, then STOP (a double click on START must not stop the task at once)
        if start_btn.mode == "start":
            start()
        elif start_btn.mode == "stop" and time.time() - start_ctx.get("t0", 0) > 1.0:
            do_stop()

    tmenu = tk.Menu(root, tearoff=0)
    tmenu.add_command(label="Paste links", command=lambda: paste_urls())
    tmenu.add_command(label="Select all", command=select_all)
    tmenu.add_command(label="Copy link", command=copy_links)
    tmenu.add_separator()
    tmenu.add_command(label="Hold", command=hold_toggle)
    tmenu.add_command(label="Remove", command=remove_selected)

    def table_menu(e):
        iid = tree.identify_row(e.y)
        if iid and iid not in tree.selection():
            tree.selection_set(iid)
        tmenu.entryconfigure(4, label=hold_label())
        tmenu.tk_popup(e.x_root, e.y_root)

    def table_click(e):  # a click on the empty part of the table deselects
        if tree.identify_row(e.y) == "" and tree.identify_region(e.x, e.y) != "heading":
            clear_selection()

    def table_ctrl(e):  # Ctrl+letter, whatever the keyboard layout is (on Windows the key code is the letter's code)
        code = e.keycode if sys.platform == "win32" else {"a": 65, "v": 86, "z": 90, "y": 89, "c": 67}.get(str(e.keysym).lower(), 0)
        action = {65: select_all, 86: lambda: paste_urls(), 90: undo_rows, 89: redo_rows, 67: copy_links}.get(code)
        if action:
            action()
            return "break"

    tree.bind("<Button-3>", table_menu)
    tree.bind("<Button-1>", table_click, "+")
    tree.bind("<Delete>", remove_selected)
    tree.bind("<Escape>", clear_selection)
    tree.bind("<Double-1>", lambda e: open_row() if tree.identify_row(e.y) else None)
    tree.bind("<Control-KeyPress>", table_ctrl)
    cb_signin.configure(command=on_signin_click)
    refresh_signin_ui()

    def on_api():
        if b["USE_API"].get() and not v["TOKEN"].get().strip():
            open_setup("Connection")  # nothing to use yet: show where the key goes

    cb_api.configure(command=on_api)
    sample_btn.configure(command=create_sample)
    load_btn.configure(command=load_txt)
    start_btn.configure(command=main_button)
    copylog_btn.configure(command=copy_log)
    openlog_btn.configure(command=open_log)
    paste_btn.configure(command=paste_urls)
    undo_btn.configure(command=do_undo)
    redo_btn.configure(command=do_redo)
    clear_btn.configure(command=clear_urls)
    hold_btn.configure(command=hold_toggle)
    help_btn.configure(command=show_help)
    setup_btn.configure(command=open_setup)
    cb_bridge.configure(command=set_bridge)

    # ---- restore previous settings
    for key, skey in (("PATH", "RECENT"), ("PREFIX", "RECENT_PREFIX"), ("IMGFOLDER", "RECENT_SUB")):
        for item in reversed(saved.get(skey) or []):
            push_recent(key, item)
    set_values({**DEFAULTS, **{k: x for k, x in saved.items() if k in DEFAULTS}})
    sync_fields()
    show_update(saved.get("UPDATE_FOUND"), saved.get("UPDATE_URL"))  # a known newer version is shown at once, without waiting for the network
    if b["DARK"].get():
        apply_theme(True)
    root.after(4000, auto_update_check)
    push_defaults()
    saved_rows = saved.get("ROWS")
    if isinstance(saved_rows, list):
        for item in saved_rows:
            if isinstance(item, dict) and str(item.get("url", "")).lower().startswith("http"):
                table["rows"].append(new_row(str(item["url"]).strip(), item.get("ov") if isinstance(item.get("ov"), dict) else {}))
    else:
        table["rows"] = [new_row(u) for u in extract_urls(saved.get("URLS", ""))]
    migrate_rows()
    style_table(bool(b["DARK"].get()))
    apply_columns()
    render_table(False)
    tree.bind("<Configure>", on_tree_resize, "+")
    tree.bind("<ButtonRelease-1>", on_tree_resize, "+")
    tree.bind("<<TreeviewSelect>>", on_select)
    for key_ in ROW_KEYS:
        (b[key_] if key_ == "MODEL" else v[key_]).trace_add("write", lambda *_a, k=key_: on_field_change(k))
    if isinstance(saved.get("PREFIX_BY_PATH"), dict):
        prefix_map.update({str(k): str(x) for k, x in saved["PREFIX_BY_PATH"].items()})
    refresh_link()
    v["PATH"].trace_add("write", on_path_change)
    v["PREFIX"].trace_add("write", on_prefix_change)
    for key in ("PATH", "PREFIX", "IMGFOLDER"):
        if not recent[key]:
            push_recent(key, v[key].get())
    path_combo.configure(values=[BROWSE_LABEL] + recent["PATH"])  # the first line is always there, even when the list is empty

    def restore_sash():
        frac = (saved.get("WINDOW") or {}).get("sash")
        try:
            if isinstance(frac, (int, float)) and 0.08 <= frac <= 0.92:
                paned.sashpos(0, int(frac * paned.winfo_height()))
        except Exception:  # noqa
            pass
        balance_actions()

    root.after(300, restore_sash)
    root.after(700, balance_actions)
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
        run_task(c, u, lambda m: (file_log(m), print(m)), threading.Event(), lambda m, *a: False)
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
