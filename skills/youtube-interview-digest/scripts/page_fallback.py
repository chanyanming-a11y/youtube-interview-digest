#!/usr/bin/env python3
"""
Login-free fallback used when yt-dlp hits YouTube's "confirm you're not a bot" wall.

YouTube still serves the public watch page (ytInitialData) to flagged IPs, and the
InnerTube /next endpoint still pages comments. The player response (captions, streams)
is what gets blocked. So from the page we can recover:

  meta      title / channel / date / views / likes / comment count / description + links
  chapters  creator chapters (macroMarkers)
  heatmap   "Most replayed" markers (frameworkUpdates.macroMarkersListEntity)
  comments  top threads (+ first replies of the busiest threads) via /youtubei/v1/next

Transcript sources tried in order:
  1. InnerTube get_transcript (often FAILED_PRECONDITION without login)
  2. External transcript linked from the description:
     - Substack posts (/p/<slug>) → /api/v1/posts/<slug> → podcastUpload/videoUpload transcription.json
       (word-timed, speaker-diarised; used by Lenny's Podcast and many other podcasts)
If all fail the caller reports TRANSCRIPT_MISSING.
"""
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_DEC = json.JSONDecoder()


# --- SSRF guard: only fetch public hostnames, never IP literals / loopback / cloud metadata
def _host_safe(host):
    h = (host or "").lower().strip()
    if not h:
        return False
    # IPv6 literal in brackets: [::1] or [::1]:8080
    if h.startswith("["):
        rb = h.find("]")
        if rb == -1:
            return False
        h = h[1:rb]
    # Bare IP (v4 or v6) -> reject (blocks 127.0.0.1, 169.254.169.254, ::1, fe80::1, ...)
    try:
        ipaddress.ip_address(h)
        return False
    except ValueError:
        pass
    # Not a bare IP: it may carry a trailing :port (IPv4 / hostname). Strip and re-check.
    if ":" in h:
        h = h.rsplit(":", 1)[0]
        if not h:
            return False
        try:
            ipaddress.ip_address(h)       # e.g. 127.0.0.1 from 127.0.0.1:8080
            return False
        except ValueError:
            pass
    if h == "localhost" or h.endswith(".local") or h.endswith(".internal") \
       or h in ("metadata", "metadata.google.internal"):
        return False
    return True


def _url_safe(url):
    """Literal-name check: scheme + hostname only. Deterministic, no DNS."""
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    return _host_safe(p.hostname or "")


def _ip_public(ip):
    """True only for a globally routable address (no loopback/private/metadata)."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped          # ::ffff:127.0.0.1 must not slip through
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _resolve_safe(host):
    """Resolve `host` and reject if ANY answer is non-public.

    `_host_safe` only inspects the literal name, so an attacker-controlled
    domain could still resolve to 127.0.0.1 or the cloud metadata address.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    addrs = {info[4][0] for info in infos}
    if not addrs:
        return False
    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])   # strip IPv6 zone id
        except ValueError:
            return False
        if not _ip_public(ip):
            return False
    return True


def _url_fetchable(url):
    """Full pre-flight for an outbound fetch: literal check + DNS check."""
    if not _url_safe(url):
        return False
    host = urllib.parse.urlparse(url).hostname or ""
    return _resolve_safe(host)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect target.

    Without this a URL that passed the pre-flight could still bounce to an
    internal address (urllib follows redirects transparently).
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _url_fetchable(newurl):
            raise urllib.error.HTTPError(newurl, code, "blocked redirect", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(proxy=None):
    """urllib opener that re-checks every redirect target (SSRF hardening)."""
    handlers = [_SafeRedirectHandler()]
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)


def _http(url, data=None, headers=None, timeout=40, proxy=None):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", "Cookie": "CONSENT=YES+1; PREF=hl=en&gl=US"}
    if data is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, json.dumps(data).encode() if data is not None else None, h)
    with _opener(proxy).open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _extract_json(html, marker):
    i = html.find(marker)
    while i != -1:
        j = html.find("{", i)
        try:
            return _DEC.raw_decode(html[j:])[0]
        except ValueError:
            i = html.find(marker, i + 1)
    return None


def _walk(o, key):
    """Yield every value stored under `key` anywhere in a nested structure."""
    stack = [o]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            for k, v in x.items():
                if k == key:
                    yield v
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(x, list):
            stack.extend(x)


def _num(text):
    """'473,426 views' → 473426 ; '1.2K' → 1200 ; '3万' → 30000."""
    if text is None:
        return None
    t = str(text).strip().replace(",", "")
    m = re.search(r"([\d.]+)\s*([KMB万亿]?)", t, re.I)
    if not m:
        return None
    n = float(m.group(1))
    mult = {"k": 1e3, "m": 1e6, "b": 1e9, "万": 1e4, "亿": 1e8}.get(m.group(2).lower(), 1)
    return int(round(n * mult))


# ---------------------------------------------------------------- page

def fetch_page(vid, proxy=None):
    html = _http(f"https://www.youtube.com/watch?v={vid}&hl=en&gl=US", proxy=proxy)
    data = _extract_json(html, "ytInitialData")
    cfg = _extract_json(html, "ytcfg.set(") or {}
    player = _extract_json(html, "ytInitialPlayerResponse") or {}
    if not data:
        raise RuntimeError("ytInitialData not found in watch page")
    return {"data": data, "cfg": cfg, "player": player}


def heatmap_from_page(data):
    for ent in _walk(data, "macroMarkersListEntity"):
        ml = ent.get("markersList", {})
        if ml.get("markerType") == "MARKER_TYPE_HEATMAP":
            out = []
            for m in ml.get("markers", []):
                s = int(m["startMillis"]) / 1000
                d = int(m["durationMillis"]) / 1000
                out.append({"start": round(s, 2), "end": round(s + d, 2),
                            "value": round(float(m.get("intensityScoreNormalized", 0)), 4)})
            return out
    return []


def chapters_from_page(data):
    for mm in _walk(data, "markersMap"):
        for m in mm:
            chs = (m.get("value") or {}).get("chapters") or []
            if chs:
                out = []
                for c in chs:
                    r = c.get("chapterRenderer", {})
                    s = int(r.get("timeRangeStartMillis", 0)) / 1000
                    out.append({"start": s, "title": (r.get("title") or {}).get("simpleText", "")})
                for i, c in enumerate(out):
                    c["end"] = out[i + 1]["start"] if i + 1 < len(out) else None
                return out
    return []


def description_from_page(data):
    """Return (full_text, [urls]) — description text is truncated for links, so rebuild them
    from commandRuns (youtube.com/redirect?q=...)."""
    for ad in _walk(data, "attributedDescription"):
        text = ad.get("content", "")
        urls = []
        for run in ad.get("commandRuns", []):
            for ue in _walk(run, "urlEndpoint"):
                u = ue.get("url", "")
                if "youtube.com/redirect" in u:
                    q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("q", [""])[0]
                    u = q or u
                if u.startswith("http"):
                    urls.append(u)
        # also raw URLs that were not truncated
        urls += [u for u in re.findall(r"https?://[^\s)]+", text) if not u.endswith("...")]
        seen, uniq = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        return text, uniq
    return "", []


def meta_from_page(vid, page, heatmap, chapters):
    data, player = page["data"], page["player"]
    res = data.get("contents", {}).get("twoColumnWatchNextResults", {}).get("results", {}) \
        .get("results", {}).get("contents", [])
    pi = next((c["videoPrimaryInfoRenderer"] for c in res if "videoPrimaryInfoRenderer" in c), {})
    si = next((c["videoSecondaryInfoRenderer"] for c in res if "videoSecondaryInfoRenderer" in c), {})
    title = "".join(r.get("text", "") for r in (pi.get("title") or {}).get("runs", [])) or \
        (player.get("videoDetails") or {}).get("title")
    views = _num(((pi.get("viewCount") or {}).get("videoViewCountRenderer") or {})
                 .get("viewCount", {}).get("simpleText"))
    pis = json.dumps(pi)
    likes = None
    m = re.search(r"along with ([\d,]+) other", pis)
    if m:
        likes = _num(m.group(1)) + 1
    else:
        m = re.search(r'"likeCount(?:IfIndifferent)?(?:String)?": "([^"]+)"', json.dumps(data))
        likes = _num(m.group(1)) if m else None
    date_txt = (pi.get("dateText") or {}).get("simpleText", "")
    upload = None
    for fmt in ("%b %d, %Y", "Premiered %b %d, %Y", "Streamed live on %b %d, %Y"):
        try:
            upload = datetime.strptime(date_txt, fmt).strftime("%Y%m%d")
            break
        except ValueError:
            pass
    owner = (si.get("owner") or {}).get("videoOwnerRenderer", {})
    channel = "".join(r.get("text", "") for r in (owner.get("title") or {}).get("runs", []))
    handle = (owner.get("navigationEndpoint") or {}).get("browseEndpoint", {}).get("canonicalBaseUrl")
    comment_count = None
    for p in data.get("engagementPanels", []):
        r = p.get("engagementPanelSectionListRenderer", {})
        if r.get("panelIdentifier") == "engagement-panel-comments-section":
            ci = (r.get("header") or {}).get("engagementPanelTitleHeaderRenderer", {}).get("contextualInfo", {})
            comment_count = _num("".join(x.get("text", "") for x in ci.get("runs", [])))
    desc, urls = description_from_page(data)
    duration = heatmap[-1]["end"] if heatmap else (player.get("videoDetails") or {}).get("lengthSeconds")
    return {
        "id": vid, "url": f"https://www.youtube.com/watch?v={vid}", "title": title,
        "channel": channel, "channel_url": f"https://www.youtube.com{handle}" if handle else None,
        "upload_date": upload, "duration": float(duration) if duration else None,
        "view_count": views, "like_count": likes, "comment_count": comment_count,
        "language": None, "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        "tags": [], "description": desc[:4000], "description_urls": urls[:60],
        "chapters": chapters, "has_heatmap": bool(heatmap),
        "playability": (player.get("playabilityStatus") or {}).get("status"),
    }


# ---------------------------------------------------------------- comments

def _next(cfg, token, proxy=None):
    body = {"context": cfg.get("INNERTUBE_CONTEXT") or
            {"client": {"clientName": "WEB", "clientVersion": cfg.get("INNERTUBE_CLIENT_VERSION", "2.20260901.00.00"),
                        "hl": "en", "gl": "US"}},
            "continuation": token}
    return json.loads(_http("https://www.youtube.com/youtubei/v1/next?prettyPrint=false", body, proxy=proxy))


def _entities(resp):
    ents = {}
    for m in resp.get("frameworkUpdates", {}).get("entityBatchUpdate", {}).get("mutations", []):
        c = (m.get("payload") or {}).get("commentEntityPayload")
        if c:
            p, tb, au = c.get("properties", {}), c.get("toolbar", {}), c.get("author", {})
            ents[p.get("commentId")] = {
                "id": p.get("commentId"),
                "text": (p.get("content") or {}).get("content", "").strip(),
                "likes": _num(tb.get("likeCountNotliked") or tb.get("likeCountLiked")) or 0,
                "reply_count_hint": _num(tb.get("replyCount")) or 0,
                "author": au.get("displayName"),
                "is_uploader": bool(au.get("isCreator")),
                "time_text": p.get("publishedTime"),
                "level": p.get("replyLevel", 0),
            }
    return ents


def _items(resp):
    out = []
    for e in resp.get("onResponseReceivedEndpoints", []):
        for v in e.values():
            if isinstance(v, dict) and "continuationItems" in v:
                out += v["continuationItems"]
    return out


def _token(item):
    for cc in _walk(item, "continuationCommand"):
        return cc.get("token")
    return None


def comments_from_page(page, max_root=300, reply_threads=15, replies_per=5, proxy=None, log=None):
    data, cfg = page["data"], page["cfg"]
    token = None
    for p in data.get("engagementPanels", []):
        r = p.get("engagementPanelSectionListRenderer", {})
        if r.get("panelIdentifier") == "engagement-panel-comments-section":
            for sm in _walk(r, "sortFilterSubMenuRenderer"):
                items = sm.get("subMenuItems", [])
                if items:
                    token = _token(items[0])  # "Top comments"
            if not token:
                token = _token(r.get("content", {}))
    if not token:
        return []
    roots, order, reply_tokens = {}, [], {}
    pages = 0
    while token and len(order) < max_root and pages < 60:
        try:
            resp = _next(cfg, token, proxy)
        except Exception as e:  # noqa: BLE001
            if log:
                log(f"  ! comments page {pages} failed: {e}")
            break
        pages += 1
        ents = _entities(resp)
        token = None
        for it in _items(resp):
            if "commentThreadRenderer" in it:
                t = it["commentThreadRenderer"]
                cid = next(iter(_walk(t.get("commentViewModel", {}), "commentId")), None)
                if not cid or cid not in ents or cid in roots:
                    continue
                c = dict(ents[cid])
                c["pinned"] = "pinnedText" in json.dumps(t.get("commentViewModel", {}))
                c["replies"] = []
                roots[cid] = c
                order.append(cid)
                rep = (t.get("replies") or {}).get("commentRepliesRenderer")
                if rep:
                    tk = _token(rep.get("subThreads") or rep.get("contents") or rep)
                    if tk:
                        reply_tokens[cid] = tk
            elif "continuationItemRenderer" in it:
                token = _token(it)
        time.sleep(0.3)
    # replies for the busiest threads only (each is one extra request)
    def _busy(k):
        return -(roots[k]["likes"] + 50 * roots[k]["reply_count_hint"])

    busiest = sorted(reply_tokens, key=_busy)[:reply_threads]
    for cid in busiest:
        try:
            resp = _next(cfg, reply_tokens[cid], proxy)
            reps = [v for v in _entities(resp).values() if v["level"] >= 1]
            roots[cid]["replies"] = sorted(reps, key=lambda x: -x["likes"])[:replies_per]
        except Exception as e:  # noqa: BLE001
            if log:
                log(f"  ! replies for {cid} failed: {e}")
        time.sleep(0.2)
    out = []
    for cid in order:
        c = roots[cid]
        c["reply_count"] = max(c.pop("reply_count_hint", 0), len(c["replies"]))
        c.pop("level", None)
        for r in c["replies"]:
            r.pop("level", None)
            r.pop("reply_count_hint", None)
        out.append(c)
    return sorted(out, key=lambda x: (-int(x["pinned"]), -x["likes"]))


# ---------------------------------------------------------------- transcripts

def transcript_from_innertube(page, proxy=None):
    data, cfg = page["data"], page["cfg"]
    params = next(iter(_walk(data, "getTranscriptEndpoint")), {}).get("params")
    if not params:
        return None, "no transcript panel"
    try:
        body = {"context": cfg.get("INNERTUBE_CONTEXT"), "params": params}
        r = json.loads(_http("https://www.youtube.com/youtubei/v1/get_transcript?prettyPrint=false", body, proxy=proxy))
    except Exception as e:  # noqa: BLE001
        return None, f"get_transcript: {e}"
    segs = []
    for s in _walk(r, "transcriptSegmentRenderer"):
        txt = "".join(x.get("text", "") for x in (s.get("snippet") or {}).get("runs", []))
        if txt.strip():
            segs.append({"start": int(s["startMs"]) / 1000, "end": int(s["endMs"]) / 1000, "text": txt.strip()})
    return (segs, "innertube:get_transcript") if segs else (None, "get_transcript: empty")


def transcript_from_substack(urls, proxy=None, log=None):
    """Try every description URL that looks like a Substack post."""
    tried = set()
    for u in urls:
        m = re.match(r"https?://([^/]+)/p/([\w-]+)", u)
        if not m or m.group(0) in tried:
            continue
        tried.add(m.group(0))
        host, slug = m.groups()
        if not _host_safe(host):
            continue
        try:
            post = json.loads(_http(f"https://{host}/api/v1/posts/{slug}", proxy=proxy))
        except Exception as e:  # noqa: BLE001
            if log:
                log(f"  · {host}/p/{slug}: {e}")
            continue
        for key in ("videoUpload", "podcastUpload"):
            up = post.get(key) or {}
            tr = up.get("transcription") or {}
            cdn = tr.get("cdn_url")
            if not cdn or not _url_fetchable(cdn):
                continue
            try:
                raw = json.loads(_http(cdn, proxy=proxy, timeout=90))
            except Exception as e:  # noqa: BLE001
                if log:
                    log(f"  · transcription.json failed: {e}")
                continue
            spk = tr.get("speaker_map") or {}
            segs = [{"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip(),
                     "speaker": spk.get(s.get("speaker"), s.get("speaker"))}
                    for s in (raw if isinstance(raw, list) else raw.get("segments", [])) if s.get("text", "").strip()]
            if segs:
                return segs, {"source": f"substack:{host}/p/{slug}:{key}", "duration": up.get("duration"),
                              "speakers": sorted(set(spk.values()))}
    return None, None


def run(vid, max_comments=300, proxy=None, log=print):
    page = fetch_page(vid, proxy)
    heat = heatmap_from_page(page["data"])
    chapters = chapters_from_page(page["data"])
    meta = meta_from_page(vid, page, heat, chapters)
    log(f"  ✓ page: {meta['title']!r} · {len(chapters)} chapters · heatmap {len(heat)} pts")
    comments = comments_from_page(page, max_root=max_comments, proxy=proxy, log=log) if max_comments else []
    log(f"  ✓ comments: {len(comments)} threads")
    segs, src = transcript_from_innertube(page, proxy)
    info = {"source": src} if segs else None
    if not segs:
        log(f"  · {src}")
        segs, info = transcript_from_substack(meta["description_urls"], proxy, log)
    return meta, heat, comments, segs, info


if __name__ == "__main__":
    m, h, c, s, i = run(sys.argv[1], max_comments=40)
    print(json.dumps({"title": m["title"], "heat": len(h), "comments": len(c),
                      "segs": len(s or []), "info": i}, ensure_ascii=False, indent=1))
