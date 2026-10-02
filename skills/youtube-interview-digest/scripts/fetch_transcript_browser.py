#!/usr/bin/env python3
"""
fetch_transcript_browser.py — automatically export YouTube's built-in
"Show transcript" text via a real browser, so the user never has to copy it
by hand.

Why this exists
---------------
When yt-dlp is bot-checked, the only reliable way to get the transcript YouTube
shows in its UI is to open the page in a *logged-in* browser and click
"… → Show transcript". This script automates exactly that, which removes the
tedious manual copy-paste the skill previously fell back to.

Pipeline
--------
  1. Obtain YouTube session cookies:
       - from --cookies <file> (Netscape, exported once), or
       - auto-exported from a local browser via yt-dlp --cookies-from-browser.
  2. Launch the installed Chrome (Playwright channel="chrome") with a fresh
     profile and inject the cookies -> YouTube treats it as a logged-in session,
     so the bot wall does not trigger.
  3. Open the watch page, click "Show transcript", wait for the panel.
  4. Scroll to lazy-load every segment, then read [mm:ss] + text.
  5. Return segments; the caller (or the CLI) writes them via
     transcript_utils.write_workdir.

Graceful degradation
--------------------
If Playwright or cookies are unavailable it prints a clear next step instead of
failing silently. The module import itself never requires Playwright (it is
imported lazily inside run()), so fetch_youtube.py can import this module safely
even when Playwright is not installed.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from transcript_utils import parse_ts, write_workdir  # noqa: E402

VID_RE = re.compile(r"[\w-]{11}")


def extract_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([\w-]{11})", url or "")
    if m:
        return m.group(1)
    return url if VID_RE.fullmatch(url or "") else None


# ------------------------------------------------------------ cookies

def export_cookies_from_browser(browser_name, tmp_path):
    """Use yt-dlp (already a dependency) to dump Netscape cookies from a local
    browser. Returns tmp_path on success, None on failure. yt-dlp writes the
    cookie file while loading the browser jar, so we ignore its exit code and
    just check the file afterwards."""
    try:
        import yt_dlp  # noqa: F401  (ensures yt-dlp is present)
    except ImportError:
        return None
    try:
        subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--cookies-from-browser", browser_name,
             "--cookies", tmp_path, "--skip-download", "--no-warnings",
             "https://www.youtube.com/"],
            check=False, capture_output=True, timeout=120,
        )
    except Exception:  # noqa: BLE001
        return None
    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
        return tmp_path
    return None


def parse_netscape(path):
    cookies = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            http_only = False
            if line.startswith("#HttpOnly_"):
                # Netscape variant: the whole token is "#HttpOnly_.domain"
                http_only = True
                line = line[len("#HttpOnly_"):]
            elif line.startswith("#"):
                continue  # real comment line
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _flag, path_, secure, expiry, name, value = parts[:7]
            cookies.append({
                "name": name, "value": value, "domain": domain, "path": path_,
                "secure": secure.upper() == "TRUE",
                "httpOnly": http_only,
                "expires": int(expiry) if expiry and expiry.isdigit() else None,
            })
    return cookies


def load_cookies(cookies_file, browser_name, log):
    """Return a list of Playwright cookie dicts (youtube/google scoped), or []."""
    path = None
    if cookies_file:
        path = cookies_file
    elif browser_name:
        fd, tmp = tempfile.mkstemp(suffix=".txt", prefix="ytcookies_")
        os.close(fd)
        log(f"  · exporting cookies from {browser_name} browser ...")
        path = export_cookies_from_browser(browser_name, tmp)
        if not path:
            log("  ! cookie export failed (is the browser installed / unlocked by another process?)")
    if not path or not os.path.exists(path):
        return []
    cookies = parse_netscape(path)
    if not cookies_file and path.startswith(tempfile.gettempdir()):
        try:
            os.remove(path)
        except OSError:
            pass
    scoped = [c for c in cookies if "youtube.com" in c["domain"] or "google.com" in c["domain"]]
    log(f"  · {len(cookies)} cookies ({len(scoped)} scoped to youtube/google)")
    return scoped or cookies


# ------------------------------------------------------------ browser

def _js_click(page, pred_js):
    """Click an element chosen by an in-page JS predicate. Returns True if clicked."""
    try:
        return bool(page.evaluate(pred_js))
    except Exception:  # noqa: BLE001
        return False


def _open_video_more_menu(page, log):
    """Open the video's '… / More' actions menu. Scoped to ytd-watch-metadata so we
    never trigger a *comment's* '…' menu. Robust to locale: the button's aria-label is
    often empty in zh-CN, with the label only in the visible text (更多 / 更多操作), so
    we match by text and require it to live inside a ytd-menu-renderer."""
    pred = r"""() => {
        const meta = document.querySelector('ytd-watch-metadata');
        if (!meta) return false;
        const inMenu = (b) => !!b.closest('ytd-menu-renderer');
        const match = (b) => {
            const t = (b.textContent || '').replace(/\s+/g, '');
            const al = (b.getAttribute('aria-label') || '');
            return inMenu(b) && /更多|更多操作|操作菜单|more|show/i.test(t + al);
        };
        let cand = Array.from(meta.querySelectorAll('button')).find(match);
        if (cand) { cand.click(); return true; }
        // fallback: any 更多/More button that is not inside a comment thread
        cand = Array.from(meta.querySelectorAll('button')).find(b =>
            !b.closest('ytd-comment-thread-renderer') &&
            /更多|更多操作|操作菜单|more|show/i.test((b.textContent||'').replace(/\s+/g,'') + (b.getAttribute('aria-label')||'')));
        if (cand) { cand.click(); return true; }
        return false;
    }"""
    if _js_click(page, pred):
        page.wait_for_timeout(1000)
        return True
    return False


def _click_transcript_item(page, log):
    """Click the 'Show transcript' / '显示文字记录' item inside the open popup menu."""
    pred = r"""() => {
        const kws = ['显示文字记录','文字记录','transcript','transcrip','字幕','untertitel',
                     'transcription','show transcript','转写文稿','content to text'];
        const items = Array.from(document.querySelectorAll(
            'ytd-menu-service-item-renderer, tp-yt-paper-item, ytd-menu-navigation-item-renderer, tp-yt-paper-listbox > *'));
        const m = items.find(it => kws.some(k => (it.textContent || '').toLowerCase().includes(k.toLowerCase())));
        if (m) { m.click(); return true; }
        return false;
    }"""
    return _js_click(page, pred)


def _click_transcript_panel_header(page, log):
    """Some layouts expose the transcript as an engagement panel ('转写文稿' / 'Transcript').
    Click its header to expand it."""
    pred = r"""() => {
        const panels = Array.from(document.querySelectorAll('ytd-engagement-panel-section-list-renderer'));
        const p = panels.find(ep => /转写文稿|transcript|文字记录/i.test(ep.textContent || ''));
        if (!p) return false;
        const titleEl = Array.from(p.querySelectorAll('*')).find(
            e => /转写文稿|transcript|文字记录/i.test(e.textContent || '') && e.childElementCount <= 2);
        (titleEl || p.querySelector('ytd-engagement-panel-title-renderer, #header, h2, h3, button') || p).click();
        return true;
    }"""
    return _js_click(page, pred)


def _panel_ready(page, timeout=15000):
    try:
        page.wait_for_selector("ytd-transcript-segment-renderer", timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def _click_show_transcript(page, log):
    """Open the transcript panel. Returns True if transcript rows appeared.

    Three strategies, tried in order:
      A) video '… / More' menu  → 'Show transcript' item
      B) click the 'Transcript' engagement-panel header to expand it
      C) click a '内容转文字 / transcript' toggle button directly (some locales)
    """
    # Strategy A
    if _open_video_more_menu(page, log):
        if _click_transcript_item(page, log):
            if _panel_ready(page):
                return True
            log("  ! transcript panel did not appear after menu click")
    # Strategy B
    if _click_transcript_panel_header(page, log) and _panel_ready(page, timeout=20000):
        return True
    # Strategy C
    pred_c = r"""() => {
        const b = Array.from(document.querySelectorAll('button')).find(e =>
            /内容转文字|transcript|transcribe|文字记录|show transcript/i.test(
                (e.textContent||'') + (e.getAttribute('aria-label')||'')));
        if (b) { b.click(); return true; } return false;
    }"""
    if _js_click(page, pred_c) and _panel_ready(page, timeout=20000):
        return True
    log("  ! could not open the built-in transcript panel")
    return False


def _collect_segments(page, log):
    # scroll the transcript panel so every (possibly lazy) segment renders
    try:
        page.evaluate("""() => {
            const el = document.querySelector('#transcript')
                    || document.querySelector('ytd-transcript-renderer')
                    || document.querySelector('[class*=transcript]');
            if (el) { for (let i = 0; i < 30; i++) el.scrollTop = el.scrollHeight; }
        }""")
        page.wait_for_timeout(700)
        page.mouse.wheel(0, 9000)
        page.wait_for_timeout(700)
    except Exception:  # noqa: BLE001
        pass
    # primary selector (stable across YouTube versions)
    raw = page.eval_on_selector_all(
        "ytd-transcript-segment-renderer",
        """els => els.map(e => {
            const ts = e.querySelector('.segment-timestamp');
            const tx = e.querySelector('.segment-text');
            return {ts: ts ? ts.textContent.trim() : '', tx: tx ? tx.textContent.trim() : ''};
        })""",
    )
    if raw:
        return raw
    # generic fallback: scan for rows shaped like "[mm:ss] <sentence>"
    # (handles layouts where the segment renderer tag/class differs)
    return page.evaluate("""() => {
        const re = /^\\s*\\d{1,2}:\\d{2}(?::\\d{2})?\\s*$/;
        const out = [];
        document.querySelectorAll('*').forEach(el => {
            const d = Array.from(el.childNodes).filter(n => n.nodeType === 3)
                        .map(n => n.textContent).join('').trim();
            if (!re.test(d)) return;
            const parent = el.parentElement;
            if (!parent) return;
            const tx = parent.textContent.replace(d, '').trim();
            // require a real sentence (skip the player scrubbing bar etc.)
            if (tx.length > 4) out.push({ts: d, tx});
        });
        return out;
    }""")


def run(video_id, out, cookies_file=None, browser_name="chrome", proxy=None, log=print):
    """Launch a browser, pull the built-in transcript, return (segs, source).
    segs is a list of {start, end, text}; source is a descriptive string.
    Returns (None, reason) when nothing was retrieved."""
    from playwright.sync_api import sync_playwright  # lazy: clear error if missing

    cookies = load_cookies(cookies_file, browser_name, log)
    url = f"https://www.youtube.com/watch?v={video_id}"

    with sync_playwright() as p:
        launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
        if proxy:
            launch_args.append(f"--proxy-server={proxy}")
        # Prefer an explicit Chrome path if the user sets YT_CHROME_PATH
        # (channel= and executable_path= are mutually exclusive in Playwright).
        chrome_path = os.environ.get("YT_CHROME_PATH")
        if chrome_path:
            browser = p.chromium.launch(executable_path=chrome_path, headless=True, args=launch_args)
        else:
            browser = p.chromium.launch(channel="chrome", headless=True, args=launch_args)
        context = browser.new_context()
        if cookies:
            context.add_cookies(cookies)
        page = context.new_page()
        log(f"  · opening {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        ok = _click_show_transcript(page, log)
        segs = []
        if ok:
            raw = _collect_segments(page, log)
            for r in raw:
                sec = parse_ts(r.get("ts"))
                text = (r.get("tx") or "").strip()
                if sec is None or not text:
                    continue
                segs.append({"start": float(sec), "end": float(sec), "text": text})
        browser.close()

    if not segs:
        return None, "browser:no-segments"
    segs.sort(key=lambda s: s["start"])
    for i, s in enumerate(segs):
        s["end"] = segs[i + 1]["start"] if i + 1 < len(segs) else s["start"] + 6
    return segs, f"browser:show-transcript:{video_id}"


def main():
    ap = argparse.ArgumentParser(description="Auto-export YouTube's built-in transcript via a browser.")
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cookies", default=None, help="Netscape cookies.txt (exported once)")
    ap.add_argument("--cookies-from-browser", default="chrome",
                    help="chrome / safari / edge / firefox (default chrome)")
    ap.add_argument("--no-browser-cookies", action="store_true",
                    help="do not auto-export cookies from a local browser")
    args = ap.parse_args()
    vid = extract_video_id(args.url)
    if not vid:
        sys.exit("Could not parse an 11-char video id from the URL.")
    os.makedirs(args.out, exist_ok=True)
    browser_name = None if args.no_browser_cookies else (args.cookies_from_browser or "chrome")
    try:
        segs, src = run(vid, args.out, cookies_file=args.cookies,
                        browser_name=browser_name, log=print)
    except ImportError:
        print("PLAYWRIGHT_MISSING: install with: <venv>/bin/pip install playwright\n"
              "(channel='chrome' reuses your installed Chrome — no browser download needed)")
        sys.exit(10)
    except Exception as e:  # noqa: BLE001
        print(f"BROWSER_FAILED: {e}")
        sys.exit(11)
    if not segs:
        print("NO_TRANSCRIPT: browser could not retrieve the transcript. "
              "Export cookies.txt (--cookies) or paste the transcript and run "
              "transcript_utils.py --file.")
        sys.exit(4)
    stats = write_workdir(args.out, segs, vid)
    print(json.dumps({"source": src, **stats}, ensure_ascii=False))


if __name__ == "__main__":
    main()
