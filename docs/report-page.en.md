# The report page

[中文](report-page.md) · [Back to README](../README.en.md)

`report.html` is a **self-contained static file**: CSS, JS and data are all inlined. Double-click it and it works — no server, no Node.

## In-page playback with clickable timestamps

A sticky player sits on the left with a custom minimal bar (progress / time / fullscreen). **Every timestamp is clickable** — click to seek to that second, and the current paragraph highlights as playback advances.

Timestamps come from real caption paragraphs, not from the model: `render_report.py --strict` rejects any timestamp beyond the video length and refuses to publish the report.

## Distraction-free playback (the shield)

YouTube's embed pops its own title bar, channel row and "more videos" shelf on pause / end. Those elements live in a cross-origin iframe, so **CSS can't remove them**.

The report lays a **permanent transparent shield** over the player that swallows every pointer event, so YouTube never receives hover and never shows its chrome — **even while playing**. On pause / end the shield becomes a cover (thumbnail + play button); a toggle in the corner restores the raw player.

## Full-article read-aloud

The "Read aloud" button under the title reads every section **block by block** (verdict / framework / viewpoints / quotes / conflicts / hotspots / comments / transcript) with highlighting and auto-scroll. **Double-click any paragraph to start reading from there.**

Three voices, auto-selected by availability:

| Voice | Requires | Notes |
|---|---|---|
| **Microsoft Edge Xiaoxiao Neural** | `pip install edge-tts` on the machine serving the report | Free, no key, most natural — **the default** |
| **Doubao** (Volcano Engine) | copy `scripts/tts_config.example.json` to `tts_config.json` and fill in `appid` / `token` | Good quality, needs your own key |
| **browser-native TTS** | nothing | Offline fallback; robotic Chinese |

Chinese timestamps are spoken as "X分Y秒" — e.g. `07:20` becomes "零七分二十秒".

## Automatic playback and the local server

When rendering finishes, `render_report.py` **starts a local preview server** (`serve_report.py`, bound to `127.0.0.1` only) and prints a `preview_url`. Open the report through that URL and the video plays **inline** with working seeks, because the page then has a valid origin and escapes the `file://` restriction.

That same server is the **local TTS proxy**:

- Doubao keys are only forwarded through it — they never enter `report.html` or the repo;
- it listens on loopback only, and `/tts` enforces a same-origin check, so other web pages can't call it cross-origin.

## Offline single file

`report.html` is self-contained (only the video and thumbnails hit YouTube's CDN). Send it to anyone — no server needed.

Opened over `file://` it degrades gracefully:

- it shows a cover, with a "local preview" link that switches to the in-page playable mode;
- read-aloud falls back to the browser-native voice, since there is no local proxy.

## Player errors 150 / 101 / 153?

| Error | Cause | Fix |
|---|---|---|
| 150 / 101 | the creator forbade embedding | timestamps automatically open `youtube.com/watch?v=…&t=…s` in a new tab, at the exact second |
| 153 | you opened the file over `file://` | open the local preview URL printed during rendering to play in-page |

None of these affect the report content — only whether playback happens in-page or in a new tab.

## No sound, or robotic Chinese?

Work down the table above: install `edge-tts` first for the most natural voice. Without a local server (i.e. opened over `file://`) only the browser-native voice is available, and its Chinese does sound robotic.
