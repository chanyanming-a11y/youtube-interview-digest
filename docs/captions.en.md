# When you can't get the captions

[中文](captions.md) · [Back to README](../README.en.md)

`fetch_youtube.py` degrades through several sources automatically, so in most cases you don't have to do anything. Only when every fallback fails (exit code 4) do you need to supply the captions yourself — this page is the full walkthrough for that step.

## Start here

| Your situation | What to do |
|---|---|
| The agent's egress IP is a cloud IP (sandbox / datacenter) | Skip the rest and run `local_fetch.sh` once on **your own machine** ([see below](#cloud-egress-ip-fetch-once-on-your-own-machine)) |
| Normal home network, but no captions | Export them once from YouTube's built-in "Show transcript" ([Option A](#option-a--youtubes-built-in-show-transcript-recommended-nothing-to-install), nothing to install, most reliable) |
| You want precise timing, or an archive copy | Download a caption file with yt-dlp ([Option B](#option-b--download-a-caption-file-precise-timing-or-you-want-to-keep-it)) |
| You also want the replay heatmap and comments | Use `local_fetch.sh` ([Option C](#option-c--fetch-everything-on-your-own-machine)) |

**One hard requirement: whatever you hand the agent must have timestamps.** Every clickable jump in the report depends on them.

## The automatic fallback chain

Many network environments — proxies and datacenter IPs especially — get a "sign in to confirm you're not a bot" gate from YouTube. The script tries these sources in order:

| Level | Source | Gets | Login |
|---|---|---|---|
| 1 | yt-dlp | everything | no |
| 2 | public watch page `ytInitialData` + InnerTube `/next` | meta, chapters, heatmap, comments and replies | no |
| 3 | external transcript linked in the description (Substack podcasts for now) | diarised transcript with word-level timing | no |
| 4 | **automatic browser export** of "Show transcript" (`fetch_transcript_browser.py`, Playwright driving your local logged-in Chrome) | captions | no (reuses your local session) |
| 5 | `--cookies-from-browser chrome` / `--cookies cookies.txt` | captions | **yes, only with explicit user consent** |
| 6 | **user-supplied**: full text copied from "Show transcript", or a `.srt` / `.vtt` / `.json3` file | captions | no |

Level 5 is the only path that touches your browser login, and the skill requires the agent to **ask for consent first**. Level 6 is the most common — and least error-prone — fallback; see below.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | success |
| `2` | URL or network error |
| `3` | blocked, and the page fallback failed too |
| `4` | everything except the captions was saved; supply captions via levels 4–6 |

External transcripts are compared against the video duration: a difference over 5 seconds raises a warning so the timeline doesn't drift silently. Spot-check a few chapter titles, confirm alignment or work out the offset, then proceed.

## Cloud egress IP: fetch once on your own machine

If the environment's **egress IP belongs to a cloud provider**, YouTube blocks the caption API wholesale (`RequestBlocked` / `page needs to be reloaded`), and login cookies don't help. **This is an environment limit, not a skill bug — don't retry.**

Fetch once on **your own machine** (normal IP, logged-in Chrome); every other step still happens inside the agent:

```bash
# macOS Terminal (run from the cloned repo)
./skills/youtube-interview-digest/local_fetch.sh "https://www.youtube.com/watch?v=<ID>"
# or, if the skill is already installed, run local_fetch.sh inside that skills dir
```

It reuses your local Chrome cookies (`--cookies-from-browser chrome`, no manual export) and gets meta / heatmap / comments / transcript in one go. The default output is `~/yt_<ID>` — hand that folder back to the agent.

**Only the fetch step needs network access.** Translation, signal analysis, deconstruction and rendering all run offline.

## Exporting the captions manually

YouTube blocks the caption API wholesale for datacenter / proxy IPs, and some videos simply have no captions at all. The reliable path is to export the transcript once yourself; the agent handles translation, deconstruction and rendering.

### Option A — YouTube's built-in "Show transcript" (recommended, nothing to install)

1. Open the video in a **desktop browser** (sign in first, so you don't hit the "confirm you're not a bot" gate).
2. Expand the description ("**...more**") and click **Show transcript** at the very bottom.
3. **Scroll the transcript panel to the bottom first** so the whole transcript loads — important for long videos, otherwise you only copy half of it.
4. **Keep timestamps on** (the ⋯ menu at the top-right of the panel toggles them). **Every clickable timestamp in the report depends on them** — with timestamps off, all jumps break.
5. Click inside the panel, select all (<kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>A</kbd>), copy (<kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>C</kbd>).
6. Paste it straight into the chat together with the video URL.

> The copy usually comes out as alternating "timestamp line + text line" — the agent parses that directly, **you don't need to tidy it up**.
>
> On mobile: the YouTube app also exposes "Show transcript" under "...more", but selecting and copying a long transcript there is painful — use a desktop for long videos.

### Option B — download a caption file (precise timing, or you want to keep it)

The skill already depends on yt-dlp, so one command is enough:

```bash
# captions only, no video
yt-dlp --skip-download --write-subs --write-auto-subs \
       --sub-langs "en.*,zh-Hans,zh" \
       -o "%(id)s.%(ext)s" "https://www.youtube.com/watch?v=<ID>"
# yields <ID>.en.vtt — .vtt is parsed directly, no ffmpeg conversion needed
```

**For your own videos**, YouTube Studio gives you cleaner official captions: Subtitles → pick the video → ⋯ next to the language → Download → `.srt`.

### Option C — fetch everything on your own machine

See [cloud egress IP](#cloud-egress-ip-fetch-once-on-your-own-machine) above: on a normal IP with a logged-in Chrome, one command gets captions + heatmap + comments.

## Supported formats

| What you have | Works? | Note |
|---|---|---|
| text copied from "Show transcript" | ✅ | "timestamp line + text line"; duplicates are fine |
| `.srt` / `.vtt` / `.json3` | ✅ | auto-detected, **no** conversion needed |
| timestamped `.txt` (`[12:34] text` or `12:34 text`) | ✅ | |
| plain text with **no timestamps at all** | ❌ | every jump in the report needs a timestamp |

## What to say to the agent (copy-paste)

> I can't get the captions automatically. Here is the full transcript I exported from YouTube's "Show transcript" (with timestamps).
> Video: https://www.youtube.com/watch?v=&lt;ID&gt;
> Please run the youtube-interview-digest pipeline on this transcript (translate → deconstruct → render).
> If the replay heatmap and comments aren't available this time, still render the report and note it under caveats.

Command-line equivalent (when `yt_<ID>/` already has meta / heatmap / comments):

```bash
python3 skills/youtube-interview-digest/scripts/transcript_utils.py \
  --file ./transcript.vtt --out ./yt_<ID> --video-id <ID>
```

It writes `transcript.md` / `paragraphs.json`, keeps any existing `meta.json` / heatmap / comments, and records `meta.subtitle_source` as `local:<filename>` so the report can state its provenance.

## Common snags

| Symptom | Cause / fix |
|---|---|
| No "Show transcript" in the description | The creator disabled captions, the video is too new, there is no speech, or the language isn't supported. Use Option B, or retry in a few hours |
| The copied text has no timestamps | "Toggle timestamps" is off in the panel — turn it on and copy again |
| The agent says it can't parse any timestamps | Same as above, or you pasted plain text from a third-party tool |
| Caption language doesn't match the video | Switch the caption track at the bottom of the panel and pick the original (usually marked "auto-generated") |
| Captions work but there's no heatmap / comments | Normal — those are fetched separately. The report still renders; "hotspots" just falls back to content judgement |
| Captions arrived but the timeline is shifted | An external transcript can be a few seconds off (different cut, or ads inserted). Spot-check against chapter titles and work out the offset first |
