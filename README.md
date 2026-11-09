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

<img width="767" height="729" alt="Civitai Grabber 052" src="https://github.com/user-attachments/assets/87e7db2b-5c97-464c-a19f-0d7b8d0b047b" />


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
2. Double-click `civitai_grabber.pyw`. Tick **Connect via Sign-in** and allow the access in the browser tab
  (or click the gear button, open the tab *Connection*, paste an API token and tick **Connect via API**).
3. Choose the output folder, paste Civitai links (model pages, `.../models/ID?modelVersionId=ID`, or single image
  pages `.../images/ID`) and press **START**.
4. For each model you get the file, `NN-example` images/videos with metadata, and the description file.

The window has tooltips for every option. Rarely changed options are in **Setup** (the gear button at the top
right). Settings can also be given in a plain text task file (see the comment at the top of `civitai_grabber.pyw`).

## The link table: every link is a job of its own

Each link you add becomes a row of the table, and **a row keeps its own settings**: output folder, prefix, number
of examples, number of gallery images and the *Model file* switch. When a link is added, it takes the values that the
fields above the table show at that moment. Change the fields later and only the links added *afterwards* are
affected, so you can paste a few links, set another folder and prefix, paste more, and press **START** once.

- **To change links that are already in the table**, select them (Ctrl or Shift for several): the header says
  *settings for: N selected*, and the fields above now show and change those rows only.
- The **Status** column shows what happens to each link: *checking*, *ok*, *warning*, *running*, *done*, *error*,
  *partial* (the model came, but some of the images did not), *hold*. Models are shown by name, not by address; once a
  link has been checked, the status shows what it is (*LoRA*, *Checkpoint*, *Embedding*...).
- A model and the single image links below it form a **pack** and share one colour (the colours alternate between
  packs; a lone link has no colour). The images of a pack **follow the folder of their model**. An image that you
  give a folder of its own is marked with *.
- **Hold** pauses the selected rows: **START** skips them until you press **Resume**. A model on hold holds its
  images too. Rows that ended with an error or *partial* come back after a restart marked *hold (error)* /
  *hold (partial)*, so a failed link is never started again by accident. If the examples of a model are incomplete and you keep it in the
  list, the gallery images below it wait for it, so the numbering always starts with the examples.
- Finished links disappear from the table, failed ones stay. **Undo / Redo** take back changes of the list. The table
  is remembered between runs.
- **START** and **STOP** are one button: STOP appears while a task runs.
- Setup lets you hide the *Examples* and *Gallery* columns to give more room to the others.

If a model is downloaded but some example or gallery images fail, Setup (tab *Downloads*) decides what happens: you
are asked, or the model is kept in the list with *Model file* switched off so the next run completes only the images,
or it is simply finished.

## What the program checks when you add a link

A moment after a model link appears in the list (pasted, typed, or sent by the browser extension), the program asks
Civitai about it and shows a window if something is wrong:

- the model is **paid** or in **early access** (the end date is shown) - unless your account has already bought it;
- the model or version was **deleted or hidden**, or is not published (a model published a moment ago may not be
  known to the Civitai API yet: check again in a minute);
- the model is **already downloaded** (also when the same file was saved earlier under another prefix, or the program's
  history knows the same version in another folder);
- a **folder with the same name already exists** and holds another model (or it is not known which one).

For each warning you remove the link or keep it (for an existing folder the buttons are "Exclude link" and
"Download to new folder": the model is then saved to a separate folder named *Name (model id)*). **START** stays
locked until all checks are done and all warnings are answered. If Civitai cannot be reached, the link simply stays in
the list. Free models get no extra requests; for paid and early-access models the program sends one tiny test request
to the file address to see whether your account already has the access. Nothing is created on disk for a model that
cannot be downloaded. The taskbar button turns yellow while some link in the list carries a warning.

## Setup and appearance

- **Setup** (the gear button, top right) has three tabs. *Downloads*: what to do with already downloaded items (ask,
  skip, download again), what to do when some example or gallery images fail, the description file name (and *Name as
  model*), the image subfolder, videos, original file names, WebP to JPG, naming of ID-like model files, and the
  experimental ComfyUI workflow `.json`. *Connection*: the API token (the key is shown while the field is unlocked and
  hidden when you press *Lock*). *Program*: how many recent folders and prefixes the lists remember (5 to 30), which
  table columns are shown, the dark theme (the small window of the browser extension has its own dark switch) and the
  update check.
- **Three check boxes** at the top show and switch the connections: *Connect via Sign-in*, *Connect via API* and
  *Browser bridge*. Hover a box for details (who is signed in, whether a token is entered, whether the browser extension
  is connected).
- **Dark theme.** On Windows 10 the title bar of the active window follows the system setting *Show accent color on
  title bars and window borders*: while it is on, Windows paints that title bar with the accent color whatever the
  program asks for. Turn it off in Windows Settings -> Personalization -> Colors to get dark title bars (Setup has a
  button for it). On Windows 11 the program sets the title bar colors itself.
- **Updates.** When the program starts (at most once in 12 hours) it asks github.com which release is the newest and shows
  an *Update X* link at the top right if it is newer than the one you run. Nothing is downloaded or installed by the
  program. Switch it off in Setup, tab *Program*.
- **Failure diagnostics.** When a request fails, the log gets a line like `DIAG: reset | files | ... | ...`: the kind of
  failure, the part of the service (`api`, `page` or `files`), the facts and a conclusion - whether it looks like your
  internet connection, a short outage of the file servers, rate limits, a Cloudflare check page, or a change in Civitai
  itself (`format changed?`). Please add such lines to bug reports.

## Folders, prefix and names

- **Output folder** keeps the folders used last (12 by default; Setup, tab *Program*: 5 to 30, the prefix list is as
  long); the first line of the list, *Add output folder...*, opens the folder chooser.
- **Prefix** is put in front of the model file name. The chain button next to the folder **links the prefix to that
  folder**: whenever you choose the folder again, its prefix is filled in (joined rings: linked; rings apart: not linked,
  or the prefix was changed after linking). Every folder has its own link; the prefix can always be edited.
- **Name ID-like model files by title** (optional): a model file whose name is only an ID (26 random characters, as the
  Civitai trainer makes them) is saved under the model's title - with the version name added when the model has several
  versions. The original name is written to the description file.
- Every model folder gets a small hidden file `.civitai-model.json` and the description file gets *Model ID* and *Version ID*
  lines, so the program can later tell which model a folder belongs to. The description file of another model that
  lies in the same folder is never overwritten; if the folder name is taken by another model, the new model gets its
  own folder named *Name (model id)*.

## How the downloads are organised

- **A model link** creates the model's own folder inside the row's output folder. It receives the model file, the
  example images/videos (`01-...`, `02-...`) with their metadata, and the description file. *Model file* can be
  switched off per row to get only the images and the description.
- **Gallery images** are the images other users uploaded to the model's gallery: the *Gallery* field says how many
  to take (a number or *all*; it needs the browser bridge).
- **Single image links** (`.../images/ID`) added right after a model link are downloaded into that model's folder
  together with its examples: the numbering simply continues, and their metadata is appended to the description file.
- **Images without a model link before them** go to the folder of their own row (optionally into an image subfolder,
  see Setup).
- If a model was downloaded before, the program asks what to do (skip it, or download it again; Setup can set the
  answer once for all).
- Folders the program created and that stayed empty (a failed run, a stop) are removed without asking. If a run is
  stopped or a download fails halfway, the program offers to delete the incomplete files (nothing else is ever
  touched). An incomplete file is resumed when you download the same link again.

## Two ways to authorize

The program needs your Civitai account for some models and for reading image pages. There are two ways, and both can be set up at the same time:

|     | Sign in with Civitai | API token |
| --- | --- | --- |
| How | Tick *Connect via Sign-in* and allow the access in the browser tab | Create a key in Civitai (account settings -> API keys), paste it in Setup (gear button), tab *Connection*, and tick *Connect via API* |
| Access | Read-only (profile, models, media), limited to this program | A personal key: treat it like a password |
| Revoking | One click in your Civitai account (*Connected Apps*) | Delete the key in Civitai |
| Renewal | Automatic (renewed in the background every hour) | Not needed |
| Stored in | `civitai_grabber_auth.json` | `civitai_grabber_settings.json` |
| Needs | A browser and the local port 8765 free for a moment | Nothing |

**Which one is used?** If you are signed in, the sign-in is used and the API token is ignored; after you sign out, the token is used again. The log of every run says which credentials were used and counts the requests, but never shows your user name. `civitai.red` and `civitai.com` are interchangeable: a sign-in on either site works for links of both.

## Privacy

Your settings stay on your computer (`civitai_grabber_settings.json`). The API token, or the sign-in
(`civitai_grabber_auth.json`), is sent only to Civitai, to authorize the program's requests and downloads; it is never
written to the log and never sent anywhere else. Both files keep the secret as plain text, like most small tools
do: do not share them. There is no analytics or telemetry. Two requests are not about your downloads: the update
check (to github.com, can be switched off) and, only after a failed request, a short network check (a bare connection
to 1.1.1.1 or 8.8.8.8 and one simple request to the Civitai site, to tell your internet connection from the service);
neither sends any data about you. The browser extension talks only to the program on your own computer (127.0.0.1) and
works with the Civitai pages in your browser (the optional Like and notification switches press buttons on the pages you add).

## Browser bridge (optional, recommended)

<img width="282" height="388" alt="Bridge 018" src="https://github.com/user-attachments/assets/01b3d8d5-121b-46f9-970b-beb6f4d3a824" />


Civitai image pages cannot be read by scripts without your browser session, so some metadata and the gallery images can
only be collected through your browser. The bridge does this reading with your own login. To add pages to the list it
provides:

- the right-click items "Add link to Civitai Grabber list" and "Add this page to Civitai Grabber list";
- a toolbar button (pin it through the browser's extensions menu) that sends the address of the current page to
  the list.

It can also close the browser tab of a finished link: *Never*, *Always*, or *Ask* (the extension window then shows a
list of the finished pages with check boxes, and you choose which to close and which to keep open). Pages where
something was not downloaded, or whose link carries a warning, stay open and appear in the extension's **Needs attention**
list; when you remove such a link in the program, it disappears from that list too.

**Like and notifications (optional).** The extension window has two small switches with icons, a thumb and a bell. Each has
three positions: grey = leave as it is (the default), green = switch on, orange = switch off (the thumb turns down, the bell
gets a minus). When you add a model page with the toolbar button or the right-click item *Add this page*, the extension sets
the like and the notification bell on that page the way you chose. It presses a button only if its state differs, once per
page, and pages added one after another are handled with a pause. Civitai switches the notifications on by itself when you
like a model, so a green thumb with an orange bell gives you a like without notifications. Links added any other way do
nothing, and you have to be signed in to Civitai in that browser. The switches work on Civitai pages only.

**Installation** (the code is in the `bridge` folder of this repository; the Chromium package and the signed Firefox
`.xpi` are attached to the [Releases](../../releases)). Current versions: Firefox Add-ons, the Chromium package
and the signed `.xpi` 0.18.0 (the same code; only the Firefox manifest differs).

- **Firefox 140 or newer (desktop), recommended:** install it from the Firefox Add-ons site:
  [Civitai Grabber Bridge](https://addons.mozilla.org/firefox/addon/civitai-grabber-bridge/) -> *Add to Firefox*.
  Firefox then updates it by itself.
- **Firefox, the other way:** open the latest Release and click the signed `.xpi`
  file in the Assets list; Firefox asks whether to install it - confirm with *Add*. It is signed by Mozilla, so it stays
  installed after Firefox is restarted, and Firefox updates it by itself (it checks once a day, or use `about:addons` -> gear
  icon -> *Check for Updates*). Please install it this way: an add-on installed through *Install Add-on From File* did not
  update in our tests. Use only one of the two Firefox ways.
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
expected to happen. A screenshot helps; so do the `DIAG:` lines of the log. The log contains no tokens and no user
name, but it does contain the paths of your folders: look through it before you post it. The pages saved in the
`debug` folder contain your browser session: never share them.

## Credits

Idea, specification, interface design and testing: the project author. Code written with the help of
Claude (Anthropic) under the author's direction.

## License

MIT - see `LICENSE`.
