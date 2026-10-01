# youtube-interview-digest

> Turn a one-hour YouTube interview or podcast into a **10-minute Chinese digest where every claim links back to the exact second in the video**.

[中文](README.md) · [Example report](examples/netflix-elizabeth-stone/) · [Case study (中文)](docs/case-study.md)

[![CI](https://github.com/chanyanming-a11y/youtube-interview-digest/actions/workflows/ci.yml/badge.svg)](https://github.com/chanyanming-a11y/youtube-interview-digest/actions/workflows/ci.yml)

![Overview](docs/images/01-overview.jpg)

## What it does

An agent skill in the `SKILL.md` format. Given a YouTube link (or a transcript file), the agent:

1. **Fetches** the timestamped transcript, creator chapters, the "Most replayed" heatmap, and top comments with replies
2. **Translates** the transcript paragraph by paragraph into Chinese, keeping every timestamp
3. **Deconstructs** the content into a framework, falsifiable viewpoints, verbatim quotes, and **viewpoint conflicts** (guest vs host, vs consensus, vs comments, self-contradictions, implicit tensions)
4. **Enriches** it with audience signals: replay peaks, timestamps that viewers typed in comments, and comment themes. It also flags cold zones that viewers skip
5. **Compresses** everything into `digest.json`: a one-line verdict, a TL;DR, and a value score with pros, cons, the target audience, and caveats
6. **Renders** `report.html` (sticky embedded player and heat curve; click any timestamp to seek) and `report.md`

## Why trust the output

`render_report.py --strict` refuses to publish a report when:

- a summary item has no timestamp, or its timestamp is beyond the video length
- an English quote can't be found in the transcript (fuzzy match). Repeated lines, such as a cold-open teaser, resolve to the nearest occurrence

## Example

[Netflix CPTO Elizabeth Stone on Lenny's Podcast](https://www.youtube.com/watch?v=t0GiTyz4syY). The episode is 72 minutes long, with about 13k words and 218 comment threads. The resulting report has 113 clickable timestamps, 6 TL;DR items, 8 framework nodes, 10 verified quotes, 6 viewpoint conflicts, 6 hotspots, and 2 fact-checks. See [`examples/`](examples/netflix-elizabeth-stone/).

## Install

```bash
git clone https://github.com/chanyanming-a11y/youtube-interview-digest.git
cd youtube-interview-digest
./install.sh                         # → ~/.workbuddy/skills/
./install.sh ~/.your-agent/skills    # any agent that loads SKILL.md skills
python3 -m pip install -r skills/youtube-interview-digest/requirements.txt   # Python ≥ 3.10
```

Then ask the agent something like "summarize this YouTube interview with timestamps: <url>".

## Bot-check fallback chain

| Level | Source | Gets | Login |
|---|---|---|---|
| 1 | yt-dlp | everything | no |
| 2 | public watch page `ytInitialData` + InnerTube `/next` | meta, chapters, heatmap, comments | no |
| 3 | external transcript linked in the description (Substack podcasts) | diarised transcript with word-level timing | no |
| 4 | `--cookies-from-browser` / `--cookies` | captions | **yes, only with explicit user consent** |
| 5 | user-supplied `.srt` / `.vtt` / copied "Show transcript" text | captions | no |

## Notes

- For personal study and research. Respect YouTube's Terms of Service and content copyright. When sharing reports publicly, render with `--no-transcript` (YouTube captions are platform content; redistributing large chunks may breach ToS). This repo's `examples/` and the GitHub Pages demo keep the full transcript **for demonstrating the output format only** — not an endorsement to redistribute the video's captions.
- Never commit cookie files. They are excluded by `.gitignore`.
- Security (vulnerability reporting, SSRF / cookie notes): see [SECURITY.md](SECURITY.md).
- MIT licensed.
