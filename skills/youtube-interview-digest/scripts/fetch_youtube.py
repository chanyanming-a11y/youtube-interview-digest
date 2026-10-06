#!/usr/bin/env python3
"""
Fetch everything needed for a YouTube interview digest in one pass:
  meta.json          title / channel / duration / chapters / stats / description
  heatmap.json       "Most replayed" traffic curve (if YouTube exposes it)
  comments.json      top comments (+ replies) sorted by likes
  transcript_raw.json / paragraphs.json / transcript.md   timestamped transcript

Usage:
  python fetch_youtube.py "https://www.youtube.com/watch?v=ID" --out ./work
  python fetch_youtube.py URL --out ./work --lang en --max-comments 500
  python fetch_youtube.py URL --out ./work --cookies-from-browser chrome   # if bot-check / age-gate

On BOT_CHECK the script automatically switches to a login-free page fallback
(meta, chapters, heatmap, comments from the public watch page; transcript from
InnerTube or a Substack post linked in the description).

Exit codes: 0 ok · 2 extract failed · 3 BOT_CHECK and page fallback failed ·
            4 everything except the transcript was saved (needs cookies or a transcript file)

Requires: yt-dlp  (fallback: youtube-transcript-api for captions)
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_transcript_browser as ftb  # noqa: E402
import page_fallback  # noqa: E402
from transcript_utils import fmt_ts, parse_json3, parse_vtt, write_workdir  # noqa: E402

try:
    import yt_dlp
except ImportError:
    sys.exit("yt-dlp missing. Install: <venv>/bin/pip install yt-dlp youtube-transcript-api")


def pick_track(info, prefer):
    """Return (lang, kind, formats). Manual subs in original language first,
    then original-language auto captions, then any English, then anything."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    orig = (info.get("language") or "").split("-")[0]
    cands = []
    for p in prefer:
        cands += [(manual, p, "manual"), (auto, f"{p}-orig", "auto"), (auto, p, "auto")]
    if orig:
        cands += [(manual, orig, "manual"), (auto, f"{orig}-orig", "auto"), (auto, orig, "auto")]
    cands += [(manual, "en", "manual"), (manual, "en-US", "manual"), (manual, "en-GB", "manual"),
              (auto, "en-orig", "auto"), (auto, "en", "auto")]
    for pool, lang, kind in cands:
        if lang in pool and pool[lang]:
            return lang, kind, pool[lang]
    for lang, fm in manual.items():
        if lang != "live_chat" and fm:
            return lang, "manual", fm
    for lang, fm in auto.items():
        if lang.endswith("-orig") and fm:
            return lang, "auto", fm
    return None, None, None


def download_subs(ydl, formats):
    by_ext = {f.get("ext"): f for f in formats}
    for ext in ("json3", "vtt", "srv3"):
        f = by_ext.get(ext)
        if not f:
            continue
        try:
            raw = ydl.urlopen(f["url"]).read().decode("utf-8", "ignore")
            if not raw.strip():
                continue
            segs = parse_json3(raw) if ext == "json3" else parse_vtt(raw) if ext == "vtt" else []
            if segs:
                return segs, ext
        except Exception as e:  # noqa: BLE001
            print(f"  ! subtitle {ext} failed: {e}", file=sys.stderr)
    return None, None


def fallback_transcript_api(video_id, prefer):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None, None
    try:
        api = YouTubeTranscriptApi()
        tl = api.list(video_id)
        langs = prefer + ["en", "en-US", "en-GB"]
        try:
            tr = tl.find_manually_created_transcript(langs)
        except Exception:  # noqa: BLE001
            tr = tl.find_transcript(langs + [t.language_code for t in tl])
        data = tr.fetch()
        segs = [{"start": s.start, "end": s.start + s.duration, "text": s.text.replace("\n", " ")}
                for s in data if s.text.strip()]
        return segs, f"transcript-api:{tr.language_code}{'(auto)' if tr.is_generated else ''}"
    except Exception as e:  # noqa: BLE001
        print(f"  ! youtube-transcript-api failed: {e}", file=sys.stderr)
        return None, None


def shape_comments(raw, duration):
    roots, replies = {}, {}
    for c in raw or []:
        item = {
            "id": c.get("id"),
            "text": (c.get("text") or "").strip(),
            "likes": c.get("like_count") or 0,
            "author": c.get("author"),
            "is_uploader": bool(c.get("author_is_uploader")),
            "pinned": bool(c.get("is_pinned")),
            "time_text": c.get("_time_text"),
        }
        parent = c.get("parent", "root")
        if parent == "root":
            item["replies"] = []
            roots[item["id"]] = item
        else:
            replies.setdefault(parent, []).append(item)
    for pid, rs in replies.items():
        if pid in roots:
            roots[pid]["replies"] = sorted(rs, key=lambda x: -x["likes"])[:10]
    out = sorted(roots.values(), key=lambda x: (-int(x["pinned"]), -x["likes"]))
    for c in out:
        c["reply_count"] = len(c["replies"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="", help="preferred caption langs, comma separated (default: original)")
    ap.add_argument("--max-comments", type=int, default=300, help="target number of top-level comments")
    ap.add_argument("--no-comments", action="store_true")
    ap.add_argument("--cookies-from-browser", default=None, help="chrome / safari / edge / firefox")
    ap.add_argument("--cookies", default=None, help="Netscape cookies.txt exported from a logged-in browser")
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--no-browser", action="store_true",
                    help="skip the automatic browser 'Show transcript' export")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    prefer = [x.strip() for x in args.lang.split(",") if x.strip()]

    opts = {
        "skip_download": True, "quiet": True, "no_warnings": True, "noplaylist": True,
        "getcomments": not args.no_comments,
        "extractor_args": {"youtube": {
            # total, parents(root), replies(total), replies-per-thread  -> --max-comments = root target
            "max_comments": [str(args.max_comments * 2), str(args.max_comments), str(args.max_comments), "5"],
            "comment_sort": ["top"]}},
    }
    if args.cookies:
        opts["cookiefile"] = args.cookies
    if args.cookies_from_browser:
        opts["cookiesfrombrowser"] = (args.cookies_from_browser,)
    if args.proxy:
        opts["proxy"] = args.proxy

    log = lambda m: print(m, file=sys.stderr)  # noqa: E731
    vid_guess = extract_video_id(args.url)
    platform = detect_platform(args.url, None)
    tail = "" if args.no_comments else f" + up to {args.max_comments} comments"
    print(f"→ [yt-dlp] extracting metadata{tail} ...", file=sys.stderr)
    mode, info, segs, src, ext_info, bot_msg = "yt-dlp", None, None, None, None, None
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(args.url, download=False)
        except yt_dlp.utils.DownloadError as e:
            msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
            if not any(k in msg for k in ("not a bot", "Sign in to confirm", "cookies", "429",
                                          "needs to be reloaded", "reloaded", "Failed to extract",
                                          "confirm you", "unavailable", "This video is unavailable")):
                print(json.dumps({"error": "EXTRACT_FAILED", "message": msg[:300],
                                  "next": "Check URL / network / proxy"}, ensure_ascii=False, indent=1))
                sys.exit(2)
            bot_msg = msg[:200]
        if info is not None:
            vid = info["id"]
            lang, kind, formats = pick_track(info, prefer)
            if formats:
                segs, ext = download_subs(ydl, formats)
                if segs:
                    src = f"yt-dlp:{lang}:{kind}:{ext}"
            if not segs and is_youtube(args.url):
                log("→ falling back to youtube-transcript-api ...")
                segs, src = fallback_transcript_api(vid, prefer)

    if info is not None:
        duration = info.get("duration") or 0
        meta = {
            "id": vid, "url": info.get("webpage_url") or args.url, "platform": platform,
            "title": info.get("title"), "channel": info.get("channel") or info.get("uploader"),
            "channel_url": info.get("channel_url"), "upload_date": info.get("upload_date"),
            "duration": duration, "view_count": info.get("view_count"), "like_count": info.get("like_count"),
            "comment_count": info.get("comment_count"), "language": info.get("language"),
            "thumbnail": info.get("thumbnail"), "tags": (info.get("tags") or [])[:20],
            "description": (info.get("description") or "")[:4000],
            "description_urls": re.findall(r"https?://[^\s)]+", info.get("description") or "")[:60],
            "chapters": [{"start": c.get("start_time"), "end": c.get("end_time"), "title": c.get("title")}
                         for c in (info.get("chapters") or [])],
            "has_heatmap": bool(info.get("heatmap")),
        }
        heatmap = [{"start": h["start_time"], "end": h["end_time"], "value": round(h["value"], 4)}
                   for h in (info.get("heatmap") or [])]
        comments = shape_comments(info.get("comments"), duration)
    else:
        # ---- BOT_CHECK: login-free page fallback (meta + chapters + heatmap + comments)
        if not is_youtube(args.url):
            print(json.dumps({"error": "EXTRACT_FAILED",
                              "message": "non-YouTube source: automatic page fallback is YouTube-only; "
                                         "provide a transcript file or use a yt-dlp-supported platform",
                              "next": "transcript_utils.py --file <f> --out <dir>"}, ensure_ascii=False, indent=1))
            sys.exit(2)
        if not vid_guess:
            sys.exit("BOT_CHECK and could not parse a video id from the URL")
        vid, mode = vid_guess, "page-fallback"
        log(f"→ [yt-dlp] BOT_CHECK ({bot_msg[:60]}…) → page fallback (no login needed)")
        try:
            meta, heatmap, comments, pf_segs, ext_info = page_fallback.run(
                vid, max_comments=0 if args.no_comments else args.max_comments, proxy=args.proxy, log=log)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"error": "BOT_CHECK", "message": bot_msg, "page_fallback_error": str(e)[:200],
                              "next": NEXT_BOT}, ensure_ascii=False, indent=1))
            sys.exit(3)
        duration = meta.get("duration") or 0
        if pf_segs:
            segs, src = pf_segs, ext_info["source"]

    # external transcript from description links, when YouTube captions are unavailable
    if not segs and meta.get("description_urls"):
        log("→ looking for an external transcript linked in the description ...")
        segs, ext_info = page_fallback.transcript_from_substack(meta["description_urls"], args.proxy, log)
        if segs:
            src = ext_info["source"]

    # automatic browser export of YouTube's built-in "Show transcript" — runs
    # whenever no transcript was obtained by any previous method, BEFORE falling
    # back to asking the user to paste it by hand.
    if not segs and not args.no_browser and is_youtube(args.url):
        log("→ trying automatic browser transcript export (YouTube 'Show transcript') ...")
        try:
            bsegs, bsrc = ftb.run(vid, args.out, cookies_file=args.cookies,
                                 browser_name=args.cookies_from_browser or "chrome",
                                 proxy=args.proxy, log=log)
            if bsegs:
                segs, src = bsegs, bsrc
        except ImportError:
            log("  ! playwright not installed — skipping (install: <venv>/bin/pip install playwright)")
        except Exception as e:  # noqa: BLE001
            log(f"  ! browser transcript export failed: {e}")

    for c in meta.get("chapters", []):
        c["ts"] = fmt_ts(c.get("start") or 0)
    meta["duration_text"] = fmt_ts(duration)
    meta["fetch_mode"] = mode
    meta["subtitle_source"] = src
    warnings = []
    if ext_info and ext_info.get("duration") and duration:
        diff = float(ext_info["duration"]) - float(duration)
        meta["external_transcript"] = {**ext_info, "duration_diff_s": round(diff, 1)}
        if abs(diff) > 5:
            warnings.append(f"external transcript is {diff:+.0f}s vs video — timestamps may be offset "
                            "(different edit / ads). Verify against chapters before using.")
    if segs and not any(s.get("speaker") for s in segs) and src and "auto" in src:
        warnings.append("auto captions: no speaker labels, proper nouns may be misheard")

    def dump(name, obj):
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    dump("meta.json", meta)
    dump("heatmap.json", heatmap)
    dump("comments.json", comments)

    stats = {"video_id": vid, "title": meta["title"], "fetch_mode": mode, "video_duration": meta["duration_text"],
             "subtitle_source": src, "heatmap_points": len(heatmap),
             "comments_root": len(comments), "chapters": len(meta["chapters"])}
    if segs:
        stats.update(write_workdir(args.out, segs, vid))
    else:
        stats["transcript"] = "MISSING"
        stats["next"] = (NEXT_BOT if mode == "page-fallback" else
            ("Automatic browser 'Show transcript' export was attempted but failed. "
             "Re-run with --cookies cookies.txt, or paste the transcript and run "
             "transcript_utils.py --file <f> --out <same dir> (meta/heatmap/comments are kept).")) + LOCAL_HINT
        log("! transcript missing — " + LOCAL_HINT.splitlines()[0])
    if warnings:
        stats["warnings"] = warnings
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    if not segs:
        sys.exit(4)


NEXT_BOT = ("Automatic browser 'Show transcript' export was attempted but could not retrieve it. "
            "Try one of: (1) re-run with --cookies cookies.txt (export once from a logged-in browser: "
            "Chrome menu → Settings → ... → export, or `yt-dlp --cookies-from-browser chrome -o cookies.txt URL`); "
            "or (2) paste the transcript from YouTube '… → Show transcript' and run "
            "transcript_utils.py --file <f> --out <same dir> (meta/heatmap/comments are kept).")

# Appended to `next` when the transcript could not be fetched because the running
# environment's egress IP is blocked by YouTube (common with cloud/sandbox agents).
# The fix is to run local_fetch.sh on the user's OWN machine (normal IP + logged-in
# Chrome), which fetches the transcript in one shot; then hand the folder back.
LOCAL_HINT = ("\n\nIf this ran inside an agent/sandbox whose egress IP is blocked by YouTube "
              "('RequestBlocked' / 'page needs to be reloaded'), DON'T retry here — run "
              "local_fetch.sh on your OWN machine instead: it uses your local logged-in Chrome "
              "and a normal IP, so it fetches the transcript in one shot. Then hand the output "
              "folder back to the agent to continue (translate / deconstruct / render).")


def extract_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([\w-]{11})", url)
    if m:
        return m.group(1)
    return url if re.fullmatch(r"[\w-]{11}", url) else None


def is_youtube(url):
    return bool(re.search(r"youtube\.com|youtu\.be", url or ""))


def detect_platform(url, info):
    u = (url or "")
    if re.search(r"youtube\.com|youtu\.be", u):
        return "youtube"
    if "bilibili" in u:
        return "bilibili"
    if "vimeo.com" in u:
        return "vimeo"
    ext = (info or {}).get("extractor") or ""
    if "Bilibili" in ext:
        return "bilibili"
    if "Vimeo" in ext:
        return "vimeo"
    if "YouTube" in ext:
        return "youtube"
    return "generic"


if __name__ == "__main__":
    main()
