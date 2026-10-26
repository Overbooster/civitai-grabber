# Civitai Grabber

A small program that downloads Civitai models (LoRA, checkpoints) together with their example
images/videos and the generation metadata (prompt, seed, sampler...), and writes a description file
(`dscr.txt`) next to the model. It comes with an optional browser extension ("bridge") that adds pages to the
program's download list in a couple of clicks and lets the program read pages that need your login.

Made first of all for the author's own workflow and shared as-is: you are welcome to test and use it freely.

> **Unofficial.** This project is not affiliated with, endorsed by or connected to Civitai. Please use it
> moderately and respect the site's terms and the rights of model authors.

**Status: public beta.** The latest version is on the [Releases](../../releases) page. It works for the author,
but it has been tested on very few machines. Bug reports are welcome (see below).

<img width="922" height="745" alt="Civitai Grabber" src="https://github.com/user-attachments/assets/b8d0f6b2-c699-41d9-b874-731a1a573073" />


## What you need

- Windows 10/11. This is where the program is developed and tested (see "Known limits" for Linux and macOS).
- [Python](https://www.python.org/downloads/) 3.8 or newer (the standard installer from python.org already
  includes Tkinter, which is used for the window). Nothing else has to be installed.
  Optional: `py -m pip install pillow` to convert WebP images to JPG.
- A Civitai account: either **sign in with it** (recommended) or paste an **API token**
  (Civitai: account settings -> API keys).

## Quick start

1. Download `civitai_grabber.pyw` from the latest [Release](../../releases) (or the whole repository:
  green **Code** button -> **Download ZIP**) and put it in a folder of its own: the program keeps its settings and
  log next to itself.
2. Double-click `civitai_grabber.pyw`. Press **Sign in with Civitai** and allow the access in the browser tab
  (or paste an API token instead). Choose the output folder, paste Civitai links
  (model pages, `.../models/ID?modelVersionId=ID`, or single image pages `.../images/ID`) and press **START**.
3. For each model you get the file, `NN-example` images/videos with metadata, and the description file.

The window has tooltips for every option. Settings can also be given in a plain text task file
(see the comment at the top of `civitai_grabber.pyw`).

## What the program checks when you add a link

A moment after a model link appears in the list (pasted, typed, or sent by the browser extension), the program asks
Civitai about it and shows a window if something is wrong:

- the model is **paid** or in **early access** (the end date is shown) - unless your account has already bought it;
- the model or version was **deleted or hidden**, or is not published;
- the model is **already downloaded**;
- a **folder with the same name already exists** and holds another model (or it is not known which one).

For each warning you remove the link or keep it (for an existing folder the buttons are "Exclude link" and
"Download anyway"). **START** stays locked until all checks are done and all warnings are answered; a link you kept
because of a paid or missing model is checked again when you press START. If Civitai cannot be reached, the link
simply stays in the list. Free models get no extra requests; for paid and early-access models the program sends one
tiny test request to the file address to see whether your account already has the access. Nothing is created on
disk for a model that cannot be downloaded. The taskbar button turns yellow while some link in the list carries a
warning.

## Folders, prefix and names

- **Output folder** keeps the 12 folders used last; the first line of the list, *Add output folder...*, opens the
  folder chooser.
- **Prefix** is put in front of the model file name. The chain button next to the folder **links the prefix to that
  folder**: whenever you choose the folder again, its prefix is filled in (joined rings: linked; rings apart: not linked,
  or the prefix was changed after linking). Every folder has its own link; the prefix can always be edited.
- **Name ID-like model files by title** (optional): a model file whose name is only an ID (26 random characters, as the
  Civitai trainer makes them) is saved under the model's title - with the version name added when the model has several
  versions. The original name is written to the description file.
- Every model folder gets a small hidden file `.civitai-model.json` and the description file gets *Model ID* and *Version ID*
  lines, so the program can later tell which model a folder belongs to. The description file of another model that
  lies in the same folder is never overwritten.

## Two ways to authorize

The program needs your Civitai account for some models and for reading image pages. There are two ways, and both can be set up at the same time:

|     | Sign in with Civitai | API token |
| --- | --- | --- |
| How | Press the button and allow the access in the browser tab | Create a key in Civitai (account settings -> API keys) and paste it |
| Access | Read-only (profile, models, media), limited to this program | A personal key: treat it like a password |
| Revoking | One click in your Civitai account (*Connected Apps*) | Delete the key in Civitai |
| Renewal | Automatic (the access is renewed in the background every hour) | Not needed |
| Stored in | `civitai_grabber_auth.json` | `civitai_grabber_settings.json` |
| Log of a run | Does not show your user name | Does not show your user name |
| Needs | A browser and the local port 8765 free for a moment | Nothing |

**Which one is used?** If you are signed in, the sign-in is used and the API token is ignored; after you sign out, the token is used again. The log of every run says which credentials were used and counts the requests (for example "Credentials used: OAuth 120 request(s), API token 0"), and lists any request that was refused although you were signed in. `civitai.red` and `civitai.com` are interchangeable: a sign-in on either site works for links of both.

## Privacy

Your settings stay on your computer (`civitai_grabber_settings.json`). The API token, or the sign-in
(`civitai_grabber_auth.json`), is sent only to Civitai, to authorize the program's requests and downloads; it is never
written to the log and never sent anywhere else. Both files keep the secret as plain text, like most small tools
do: do not share them. There is no analytics or telemetry. The browser extension talks only to the program on your
own computer (127.0.0.1) and works with the Civitai pages in your browser.

## How the downloads are organised

- **A model link** creates the model's own folder inside the output folder. It receives the model file, the
  example images/videos (`01-...`, `02-...`) with their metadata, and the description file.
- **Gallery images** (links to single image pages, `.../images/ID`) that are added to the list right after a
  model link are downloaded into that model's folder together with its examples: they inherit the folder, the
  numbering simply continues, and their metadata is appended to the description file.
- **Images without a model link before them** go to the output folder itself (optionally into an
  image subfolder, see the option in the window). So to download gallery images separately, set the folder you
  want before pressing **START**.
- If a model was downloaded before, the program asks what to do (skip it, or download it again).
- At the moment the output folder and the other options apply to the whole current list; per-link folders are
  planned.
- Folders the program created and that stayed empty (a failed run, a stop) are removed without asking. If a run is
  stopped or a download fails halfway, the program offers to delete the incomplete files (nothing else is ever
  touched). An incomplete file is resumed when you download the same link again.

## Browser bridge (optional, recommended)

Civitai image pages cannot be read by scripts without your browser session, so some metadata can only be
collected through your browser. The bridge does this reading with your own login. To add pages to the list it
provides:

- the right-click items "Add link to Civitai Grabber list" and "Add this page to Civitai Grabber list";
- a toolbar button (pin it through the browser's extensions menu) that sends the address of the current page to
  the list.

It can also close the browser tab of a finished link: *Never*, *Always*, or *Ask* (the extension window then shows a
list of the finished pages with check boxes, and you choose which to close and which to keep open). Pages where
something was not downloaded, or whose link carries a warning, stay open and appear in the extension's **Needs attention**
list; when you remove such a link in the program, it disappears from that list too.

**Installation** (the files are in the latest [Release](../../releases); the same code is in the `bridge` folder of this repository):

- **Firefox 140 or newer** (Firefox for Android: 142): download the signed `.xpi` from the Release and open it in Firefox
  (or go to `about:addons` -> gear icon -> *Install Add-on From File* and select the `.xpi`). It is signed by Mozilla,
  so it stays installed after Firefox is restarted, and Firefox updates it by itself.
- **Chrome / Edge / Brave / Chromium:** unpack the Chromium zip from the Release (or use the folder
  `bridge/chromium` of this repository), open `chrome://extensions`, turn on *Developer mode*,
  *Load unpacked* and select that folder. The extension keeps a fixed ID, so the program recognises it
  automatically. Do not delete or move the folder afterwards. To update, replace the files in that folder and press
  the reload button on the extension's card.

When the program is closed, the extension window offers a **Start Civitai Grabber** button; for this the
program asks your permission once and adds a small entry for each browser it can launch from
(this uses the browser's "native messaging" feature and writes only into your own user registry).

## Known limits

- Paid models you have not bought cannot be downloaded (the program warns beforehand).
- Very long Windows paths (over 260 characters) are not handled.
- Opera, Vivaldi and Yandex Browser are not covered by the start-from-browser button yet.
- Linux and macOS have not been tested. The downloader is plain Python and may work there, but the
  start-from-browser feature and the taskbar indicators are written for Windows. Test reports are welcome.

## Bug reports

Open an **Issue** and attach `civitai_grabber.log`, the program version (shown in the window title) and what you
expected to happen. A screenshot helps. The log contains no tokens and no user name, but it does contain the paths of your
folders: look through it before you post it. The pages saved in the `debug` folder contain
your browser session: never share them.

## Credits

Idea, specification, interface design and testing: the project author. Code written with the help of
Claude (Anthropic) under the author's direction.

## License

MIT - see `LICENSE`.
