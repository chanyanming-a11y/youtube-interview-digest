#!/usr/bin/env python3
"""
Turn raw audience signals into a compact brief the agent can reason over.

Inputs  (work dir): meta.json, heatmap.json, comments.json, paragraphs.json
Outputs (work dir): signals.json  (machine)  +  signals.md  (read this one)

Signals:
  1. Traffic peaks   – local maxima of YouTube "Most replayed" curve (intro spike removed)
  2. Comment anchors – timestamps viewers typed in comments (e.g. "23:15 this!"), like-weighted
  3. Top comments    – highest-liked threads with reply counts (discussion focus)
  4. Keywords        – frequent terms / bigrams across comments
Each peak / anchor is paired with the transcript paragraph(s) it covers.

Usage: python analyze_signals.py --work ./work [--peaks 8] [--top 40]
"""
import argparse
import json
import math
import os
import re
from collections import Counter

from transcript_utils import fmt_ts

STOP = set("""a an the and or but if of to in on at for with from by is are was were be been being it its this that
these those i you he she we they me him her us them my your his our their what which who whom whose when where why how
not no yes so just very really too also can could would should will shall may might must do does did done have has had
than then there here about into out up down over under again more most much many some any all each every such only own
same other s t don doesn didn isn aren wasn weren ve ll re d m im it's i'm that's he's she's they're you're like get got
one two lot thing things know think video guy people say said even well going gonna want make way good great love thank
thanks watch watching episode podcast interview lenny lol 😂""".split())


def load(work, name, default):
    p = os.path.join(work, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def para_at(paras, t, span=0):
    """Paragraphs overlapping [t, t+span]."""
    hits = [p for p in paras if p["start"] <= t + span and p["end"] >= t]
    if not hits:
        before = [p for p in paras if p["start"] <= t]
        hits = before[-1:] if before else paras[:1]
    return hits


def excerpt(paras, t, span=0, n=260):
    txt = " ".join(p["text"] for p in para_at(paras, t, span))
    return txt[:n] + ("…" if len(txt) > n else "")


# ---------------------------------------------------------------- 1. heatmap peaks

def heatmap_peaks(heat, duration, k):
    if not heat:
        return []
    vals = [h["value"] for h in heat]
    n = len(vals)
    # smooth (window 3) to avoid jagged single-bucket spikes
    sm = [sum(vals[max(0, i - 1):i + 2]) / len(vals[max(0, i - 1):i + 2]) for i in range(n)]
    mean = sum(sm) / n
    std = math.sqrt(sum((v - mean) ** 2 for v in sm) / n) or 1e-9
    skip_until = max(0.03 * (duration or heat[-1]["end"]), 30)  # opening spike is noise
    cands = []
    for i in range(n):
        if heat[i]["start"] < skip_until:
            continue
        left = sm[i - 1] if i else -1
        right = sm[i + 1] if i + 1 < n else -1
        if sm[i] >= left and sm[i] >= right and sm[i] > mean:
            cands.append(i)
    cands.sort(key=lambda i: -sm[i])
    picked = []
    min_gap = max(n // 25, 2)
    for i in cands:
        if all(abs(i - j) >= min_gap for j in picked):
            picked.append(i)
        if len(picked) >= k:
            break
    peaks = []
    for i in sorted(picked):
        # expand to contiguous region above (mean + 0.5 std)
        # expand to the contiguous "shoulder" of the peak, but keep it tight:
        # above max(mean+0.5σ, 70% of the peak) and at most 3 buckets each side
        thr = max(mean + 0.5 * std, 0.7 * sm[i])
        lo = i
        while lo > 0 and i - lo < 3 and sm[lo - 1] >= thr and sm[lo - 1] <= sm[lo] + 0.05:
            lo -= 1
        hi = i
        while hi + 1 < n and hi - i < 3 and sm[hi + 1] >= thr and sm[hi + 1] <= sm[hi] + 0.05:
            hi += 1
        peaks.append({
            "start": heat[lo]["start"], "end": heat[hi]["end"], "peak_at": heat[i]["start"],
            "ts": fmt_ts(heat[lo]["start"]),
            "value": round(sm[i], 3), "z": round((sm[i] - mean) / std, 2),
        })
    return peaks


# ---------------------------------------------------------------- 2. comment anchors

TS_IN_TEXT = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):([0-5]\d)(?![\d:])")


def comment_anchors(comments, duration, gap=20, top=12):
    """Cluster timestamps viewers typed; mentions within `gap` seconds of each other
    form one anchor. Weight = sum(1 + ln(1+likes))."""
    hits = []
    for c in comments:
        for item in [c] + c.get("replies", []):
            secs = []
            for m in TS_IN_TEXT.finditer(item["text"]):
                h, mi, s = m.groups()
                sec = int(h or 0) * 3600 + int(mi) * 60 + int(s)
                if (duration and sec > duration + 5) or sec in secs:
                    continue
                secs.append(sec)
            # a comment listing many timestamps is a viewer-made index: spread its weight
            index_like = len(secs) >= 3
            w = (1 + math.log1p(item["likes"])) / (len(secs) if index_like else 1)
            for sec in secs:
                hits.append({"t": sec, "ts": fmt_ts(sec), "likes": item["likes"], "text": item["text"][:300],
                             "w": w, "cid": item.get("id") or item["text"][:60], "index": index_like})
    hits.sort(key=lambda x: x["t"])
    clusters = []
    for h in hits:
        if clusters and h["t"] - clusters[-1][-1]["t"] <= gap:
            clusters[-1].append(h)
        else:
            clusters.append([h])
    # one comment counts once per cluster (e.g. "42:40 - 42:50" is a range, not 2 votes)
    dedup = []
    for cl in clusters:
        seen, keep = set(), []
        for x in cl:
            if x["cid"] not in seen:
                seen.add(x["cid"])
                keep.append(x)
        dedup.append(keep)
    ranked = sorted(dedup, key=lambda cl: -sum(x["w"] for x in cl))[:top]
    out = []
    for cl in sorted(ranked, key=lambda cl: cl[0]["t"]):
        cs = sorted(cl, key=lambda x: (x["index"], -x["likes"]))
        out.append({"start": cl[0]["t"], "ts": fmt_ts(cs[0]["t"]), "t": cs[0]["t"], "mentions": len(cl),
                    "weight": round(sum(x["w"] for x in cl), 1),
                    "index_only": all(x["index"] for x in cl),
                    "samples": [{k: v for k, v in x.items() if k not in ("w", "cid")} for x in cs[:4]]})
    return out, len(hits)


# ---------------------------------------------------------------- 3/4. comments

def top_threads(comments, top):
    out = []
    for c in comments[:top]:
        out.append({"likes": c["likes"], "reply_count": c.get("reply_count", 0), "pinned": c.get("pinned"),
                    "is_uploader": c.get("is_uploader"), "text": c["text"][:500],
                    "top_replies": [{"likes": r["likes"], "text": r["text"][:240]} for r in c.get("replies", [])[:3]]})
    return out


def keywords(comments, k=30):
    uni, bi = Counter(), Counter()
    for c in comments:
        for item in [c] + c.get("replies", []):
            w = 1 + math.log1p(item["likes"])
            toks = [t for t in re.findall(r"[a-zA-Z][a-zA-Z'\-]{2,}|[\u4e00-\u9fff]{2,}", item["text"].lower())]
            toks = [t for t in toks if t not in STOP]
            for t in set(toks):
                uni[t] += w
            for a, b in set(zip(toks, toks[1:], strict=False)):
                bi[f"{a} {b}"] += w
    return ([{"term": t, "score": round(s, 1)} for t, s in uni.most_common(k)],
            [{"term": t, "score": round(s, 1)} for t, s in bi.most_common(k // 2)])


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--peaks", type=int, default=8)
    ap.add_argument("--top", type=int, default=40, help="top comment threads to keep")
    args = ap.parse_args()
    w = args.work
    meta = load(w, "meta.json", {})
    heat = load(w, "heatmap.json", [])
    comments = load(w, "comments.json", [])
    paras = load(w, "paragraphs.json", [])
    duration = meta.get("duration") or (paras[-1]["end"] if paras else 0)

    peaks = heatmap_peaks(heat, duration, args.peaks)
    for p in peaks:
        p["excerpt"] = excerpt(paras, p["start"], p["end"] - p["start"]) if paras else ""
    anchors, n_ts = comment_anchors(comments, duration)
    for a in anchors:
        a["excerpt"] = excerpt(paras, a["t"], 20) if paras else ""
    # overlap: a comment anchor inside / near a traffic peak = strongest signal
    for a in anchors:
        a["near_peak"] = any(p["start"] - 30 <= a["t"] <= p["end"] + 30 for p in peaks)
    for p in peaks:
        p["comment_mentions"] = sum(a["mentions"] for a in anchors if p["start"] - 30 <= a["t"] <= p["end"] + 30)
    threads = top_threads(comments, args.top)
    kw_uni, kw_bi = keywords(comments)

    signals = {"has_heatmap": bool(heat), "comments_analyzed": len(comments),
               "timestamped_mentions": n_ts, "peaks": peaks, "comment_anchors": anchors,
               "top_threads": threads, "keywords": kw_uni, "bigrams": kw_bi,
               "chapters": meta.get("chapters", [])}
    with open(os.path.join(w, "signals.json"), "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=1)

    # human/agent-readable brief
    L = [f"# Audience signals — {meta.get('title', '')}",
         f"- duration {fmt_ts(duration)} · views {meta.get('view_count')} · likes {meta.get('like_count')} · "
         f"comments {meta.get('comment_count')} (analyzed {len(comments)} threads, {n_ts} timestamp mentions)",
         f"- heatmap: {'yes' if heat else 'NOT AVAILABLE (low views or new video) — rely on comments'}", ""]
    if meta.get("chapters"):
        L.append("## Creator chapters")
        L += [f"- [{c['ts']}] {c['title']}" for c in meta["chapters"]]
        L.append("")
    L.append("## 1. Traffic peaks (Most replayed, intro removed)")
    if not peaks:
        L.append("_none_")
    for i, p in enumerate(peaks, 1):
        L.append(f"**P{i} [{p['ts']}–{fmt_ts(p['end'])}]** value {p['value']} (z={p['z']}) · "
                 f"comment mentions nearby: {p['comment_mentions']}")
        L.append(f"> {p['excerpt']}")
    L.append("\n## 2. Comment timestamp anchors (like-weighted)")
    if not anchors:
        L.append("_none_")
    for a in anchors:
        L.append(f"**[{a['ts']}]** mentions {a['mentions']} · weight {a['weight']}"
                 f"{' · ⚡near traffic peak' if a['near_peak'] else ''}"
                 f"{' · (only from viewer-made timestamp index — weak signal)' if a.get('index_only') else ''}")
        for s in a["samples"][:2]:
            L.append(f"  - ({s['likes']}👍) {s['text'][:180]}")
        L.append(f"  > transcript: {a['excerpt'][:200]}")
    L.append("\n## 3. Top comment threads")
    for i, c in enumerate(threads[:25], 1):
        tag = "📌" if c["pinned"] else ""
        tag += "🎙️uploader " if c["is_uploader"] else ""
        L.append(f"{i}. {tag}({c['likes']}👍 · {c['reply_count']} replies) {c['text'][:260]}")
        for r in c["top_replies"][:2]:
            L.append(f"   ↳ ({r['likes']}👍) {r['text'][:160]}")
    L.append("\n## 4. Comment keywords")
    L.append(", ".join(f"{k['term']}({k['score']})" for k in kw_uni[:25]))
    L.append("\nBigrams: " + ", ".join(f"{k['term']}({k['score']})" for k in kw_bi[:12]))
    with open(os.path.join(w, "signals.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(json.dumps({"peaks": len(peaks), "comment_anchors": len(anchors), "threads": len(threads),
                      "timestamp_mentions": n_ts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
