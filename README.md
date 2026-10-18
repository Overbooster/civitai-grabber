# Civitai Grabber

A small program that downloads Civitai models (LoRA, checkpoints) together with their example
images/videos and the generation metadata (prompt, seed, sampler...), and writes a description file
(`dscr.txt`) next to the model. It comes with an optional browser extension ("bridge") that adds pages to the
program's download list in a couple of clicks and lets the program read pages that need your login.

Made first of all for the author's own workflow and shared as-is: you are welcome to test and use it freely.

> **Unofficial.** This project is not affiliated with, endorsed by or connected to Civitai. Please use it
> moderately and respect the site's terms and the rights of model authors.
>

**Status: public beta (v0.28).** It works for the author, but it has been tested on very few
machines. Bug reports are welcome (see below).

<img width="962" height="772" alt="Civitai Grabber2" src="https://github.com/user-attachments/assets/d539b058-5a72-431f-a121-4077510800bc" />

## What you need

- Windows 10/11. This is where the program is developed and tested (see "Known limits" for Linux and macOS).
- [Python](https://www.python.org/downloads/) 3.8 or newer (the standard installer from python.org already
  includes Tkinter, which is used for the window). Nothing else has to be installed.
  Optional: `py -m pip install pillow` to convert WebP images to JPG.
- A Civitai **API token** (Civitai: account settings -> API keys).

## Quick start

1. Download this repository (green **Code** button -> **Download ZIP**) and unpack it anywhere.
2. Double-click `civitai_grabber.pyw`. Paste your token, choose the output folder, paste Civitai links
   (model pages, `.../models/ID?modelVersionId=ID`, or single image pages `.../images/ID`) and press **START**.
3. For each model you get the file, `NN-example` images/videos with metadata, and the description file.

The window has tooltips for every option. Settings can also be given in a plain text task file
(see the comment at the top of `civitai_grabber.pyw`).

## Privacy

Your token and settings stay on your computer (`civitai_grabber_settings.json`). The token is sent only to
Civitai, to authorize the program's requests and downloads; it is never written to the log and never sent
anywhere else. There is no analytics or telemetry. The browser extension talks only to the program on your own
computer (127.0.0.1) and works with the Civitai pages in your browser.

## How the downloads are organised

- **A model link** creates the model's own folder inside the output folder. It receives the model file, the
  example images/videos (`01-...`, `02-...`) with their metadata, and the description file.
- **Gallery images** (links to single image pages, `.../images/ID`) that are added to the list right after a
  model link are downloaded into that model's folder together with its examples: they inherit the folder, the
  numbering simply continues, and their metadata is appended to the description file.
- **Images without a model link before them** go to the output folder itself (optionally into an
  image subfolder, see the option in the window). So to download gallery images separately, set the folder you
  want before pressing **START**.
- At the moment the output folder and the other options apply to the whole current list; per-link folders are
  planned.

## Browser bridge (optional, recommended)

Civitai image pages cannot be read by scripts without your browser session, so some metadata can only be
collected through your browser. The bridge does this reading with your own login. To add pages to the list it
provides:

- the right-click items "Add link to Civitai Grabber list" and "Add this page to Civitai Grabber list";
- a toolbar button (pin it through the browser's extensions menu) that sends the address of the current page to
  the list.
  
**Installation** (the files are in the latest [Release](../../releases); the same code is in the `bridge` folder of this repository):

- **Firefox, recommended:** download the signed `.xpi` file from the Release and open it in Firefox
  (or `about:addons` -> gear icon -> *Install Add-on From File*). It is signed by Mozilla, so the
  installation is permanent and survives restarts.
- **Firefox, temporary / for trying the newest code:** open `about:debugging#/runtime/this-firefox` ->
  *Load Temporary Add-on* -> pick `bridge/firefox/manifest.json` from this repository (or from an
  unpacked zip). A temporary add-on disappears when Firefox is restarted.
- **Chrome / Edge / Brave / Chromium:** unpack the Chromium zip from the Release (or use the folder
  `bridge/chromium` of this repository), open `chrome://extensions`, turn on *Developer mode*,
  *Load unpacked* and select that folder. The extension keeps a fixed ID, so the program recognises it
  automatically. Do not delete or move the folder afterwards.

When the program is closed, the extension window offers a **Start Civitai Grabber** button; for this the
program asks your permission once and adds a small entry for each browser it can launch from
(this uses the browser's "native messaging" feature and writes only into your own user registry).

## Known limits

- Paid (Buzz-only) and login-protected models cannot be downloaded.
- Very long Windows paths (over 260 characters) are not handled.
- Opera, Vivaldi and Yandex Browser are not covered by the start-from-browser button yet.
- Linux and macOS have not been tested. The downloader is plain Python and may work there, but the
  start-from-browser feature and the taskbar indicators are written for Windows. Test reports are welcome.

## Bug reports

Open an **Issue** and attach `civitai_grabber.log` (it contains no token), the program version
(shown in the window title) and what you expected to happen. A screenshot helps.

## Credits

Idea, specification, interface design and testing: the project author. Code written with the help of
Claude (Anthropic) under the author's direction.

## License

MIT - see `LICENSE`.
