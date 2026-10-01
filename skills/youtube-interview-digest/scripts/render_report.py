#!/usr/bin/env python3
"""
Render digest.json (+ meta / heatmap / signals / Chinese transcript) into:
  report.html  – interactive page: embedded YouTube player, every timestamp clickable (seekTo),
                 heat curve, searchable bilingual transcript that follows playback
  report.md    – portable Markdown; timestamps are youtube.com/watch?v=ID&t=Ns links

Also VALIDATES the digest:
  - every summary item carries a timestamp (spec requirement)
  - timestamps are inside the video duration
  - English quotes appear (near-)verbatim in the transcript and near the claimed time

Usage:
  python render_report.py --work ./work                       # uses work/digest.json, work/transcript_zh.md
  python render_report.py --work ./work --out ./out --strict  # non-zero exit on validation errors
"""
import argparse
import datetime
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from transcript_utils import fmt_ts, parse_ts  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "report_template.html")


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- transcript_zh

ZH_LINE = re.compile(r"^\s*\[((?:\d{1,2}:)?\d{1,2}:\d{2})\]\s*(?:(?:\*\*)?([^：:\]\*]{1,24})(?:\*\*)?[：:]\s*)?(.+)$")


def load_transcript_zh(path, paras):
    if not path or not os.path.exists(path):
        # no translation yet: show original paragraphs so the page is still useful
        return [{"t": p["start"], "en": p["text"]} for p in paras]
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = ZH_LINE.match(line)
            if not m:
                if rows and line.strip() and not line.startswith("#") and not line.startswith(">"):
                    rows[-1]["zh"] += re.sub(r"\s*⭐\s*", " ", line.strip())
                continue
            t, spk, txt = m.groups()
            # guard: speaker capture only if it looks like a name (no sentence punctuation)
            if spk and re.search(r"[，。,.!?？！]", spk):
                txt, spk = f"{spk}：{txt}", None
            txt = re.sub(r"\s*⭐\s*", " ", txt).strip()  # quote-candidate markers are internal only
            rows.append({"t": parse_ts(t), "speaker": (spk or "").strip() or None, "zh": txt})
    # attach English original by nearest paragraph start
    if paras:
        starts = [p["start"] for p in paras]
        for r in rows:
            i = min(range(len(starts)), key=lambda k: abs(starts[k] - r["t"]))
            if abs(starts[i] - r["t"]) <= 3:
                r["en"] = paras[i]["text"]
    return rows


# ---------------------------------------------------------------- validation

REQ = {  # section -> list of (label, getter returning list of (path, value))
    "tldr": lambda g: [(f"tldr[{i}]", x.get("t")) for i, x in enumerate(g.get("tldr", []))],
    "value.takeaways": lambda g: [(f"value.takeaways[{i}]", x.get("t"))
                                  for i, x in enumerate((g.get("value") or {}).get("takeaways", []))],
    "framework": lambda g: [(f"framework[{i}].start", x.get("start")) for i, x in enumerate(g.get("framework", []))]
    + [(f"framework[{i}].points[{j}]", p.get("t")) for i, x in enumerate(g.get("framework", []))
       for j, p in enumerate(x.get("points", []))],
    "viewpoints": lambda g: [(f"viewpoints[{i}]", x.get("t")) for i, x in enumerate(g.get("viewpoints", []))],
    "quotes": lambda g: [(f"quotes[{i}]", x.get("t")) for i, x in enumerate(g.get("quotes", []))],
    "conflicts": lambda g: [(f"conflicts[{i}].{s}", (x.get(s) or {}).get("t"))
                            for i, x in enumerate(g.get("conflicts", [])) for s in ("a", "b") if x.get(s)],
    "hotspots": lambda g: [(f"hotspots[{i}]", x.get("t")) for i, x in enumerate(g.get("hotspots", []))],
    "comment_insights": lambda g: [(f"comment_insights[{i}]", x.get("t"))
                                   for i, x in enumerate(g.get("comment_insights", []))],
    "resources": lambda g: [(f"resources[{i}]", x.get("t")) for i, x in enumerate(g.get("resources", []))],
}

SOFT = {"comment_insights", "resources"}  # missing ts here = warning only


def _norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split()


def check_quotes(g, paras, errors, warns):
    if not paras:
        return
    words, idx = [], []  # flattened transcript words with paragraph start
    for p in paras:
        for w in _norm(p["text"]):
            words.append(w)
            idx.append(p["start"])
    for i, q in enumerate(g.get("quotes", [])):
        en = q.get("en")
        if not en:
            warns.append(f"quotes[{i}] has no English original (en) — cannot verify")
            continue
        qw = _norm(en)
        if len(qw) < 3:
            continue
        n = len(qw)
        first = qw[0]
        cands = [k for k, w in enumerate(words) if w == first] or range(0, max(1, len(words) - n), max(1, n // 2))
        scored = []  # every occurrence — interviews often repeat a line (cold-open teaser, recap)
        for k in cands:
            r = difflib.SequenceMatcher(None, qw, words[k:k + n + 3]).ratio()
            scored.append((r, k))
        best = max((r for r, _ in scored), default=0.0)
        if best < 0.6:
            errors.append(f"quotes[{i}] not found in transcript (match {best:.2f}): \"{en[:70]}\"")
            continue
        hits = sorted({idx[k] for r, k in scored if r >= max(0.6, best - 0.08)})
        claimed = parse_ts(q.get("t"))
        if claimed is None:
            q["t"] = hits[-1]  # prefer the later (main-body) occurrence over a teaser
            continue
        nearest = min(hits, key=lambda t: abs(t - claimed))
        if abs(nearest - claimed) > 90:
            warns.append(f"quotes[{i}] timestamp {fmt_ts(claimed)} not near any occurrence "
                         f"({', '.join(fmt_ts(t) for t in hits)}) — moved to {fmt_ts(nearest)}")
            q["t"] = nearest


def validate(g, duration, paras):
    errors, warns = [], []
    for sec, getter in REQ.items():
        for path, v in getter(g):
            t = parse_ts(v)
            if t is None:
                (warns if sec in SOFT else errors).append(f"{path}: missing/invalid timestamp ({v!r})")
            elif duration and t > duration + 2:
                errors.append(f"{path}: timestamp {fmt_ts(t)} beyond video duration {fmt_ts(duration)}")
    for k in ("one_liner", "tldr", "framework", "viewpoints", "quotes", "hotspots"):
        if not g.get(k):
            warns.append(f"section '{k}' is empty")
    check_quotes(g, paras, errors, warns)
    return errors, warns


# ---------------------------------------------------------------- markdown

def md_ts(v, vid):
    t = parse_ts(v)
    if t is None:
        return ""
    return f"[`{fmt_ts(t)}`](https://www.youtube.com/watch?v={vid}&t={int(t)}s)" if vid else f"`{fmt_ts(t)}`"


def md_rich(text, vid):
    return re.sub(r"\[((?:\d{1,2}:)?\d{1,2}:\d{2})(?:\s*[-–~]\s*(?:\d{1,2}:)?\d{1,2}:\d{2})?\]",
                  lambda m: md_ts(m.group(1), vid), text or "")


def _sole_speaker(items):
    sp = {x.get("speaker") for x in items}
    return next(iter(sp)) if len(sp) == 1 and None not in sp else None


def _num_zh(n):
    if n is None:
        return None
    return f"{n / 1e4:.1f}".rstrip("0").rstrip(".") + " 万" if n >= 1e4 else str(n)


def to_markdown(meta, g, transcript, vid, extra=None):
    extra = extra or {}
    R = lambda s: md_rich(s, vid)  # noqa: E731
    T = lambda v: md_ts(v, vid)  # noqa: E731
    L = [f"# {g.get('title_zh') or meta.get('title')}", ""]
    if g.get("title_zh"):
        L.append(f"原标题：{meta.get('title')}  ")
    ud = meta.get("upload_date") or ""
    ud = f"{ud[:4]}-{ud[4:6]}-{ud[6:]}" if len(ud) == 8 and ud.isdigit() else ud
    info = [meta.get("channel"), ud, fmt_ts(meta.get("duration") or 0),
            f"{_num_zh(meta.get('view_count'))}次观看" if meta.get("view_count") else None,
            f"[原视频]({meta.get('url')})" if meta.get("url") else None]
    L.append(" · ".join(str(x) for x in info if x) + "  ")
    if g.get("guests"):
        L.append("嘉宾：" + "；".join(f"{x.get('name')}，{x.get('role', '')}".rstrip("，") for x in g["guests"])
                 + (f"　主持：{g['host']}" if g.get("host") else ""))
    L.append("")
    if g.get("one_liner"):
        L += [f"> {R(g['one_liner'])}", ""]
    v = g.get("value") or {}
    if v or g.get("tldr"):
        L.append("## 结论")
        if v.get("score") is not None:
            L.append(f"值得看的程度：{v['score']} / 5。适合：{'；'.join(v.get('for_whom', []))}")
            L.append("")
        if v.get("why"):
            L += [R(v["why"]), ""]
        if g.get("tldr"):
            L.append("**要点**\n")
            L += [f"- {T(x.get('t'))} {R(x.get('text'))}" for x in g["tldr"]]
            L.append("")
        if v.get("takeaways"):
            L.append("**可以直接拿去用的**\n")
            L += [f"- {T(x.get('t'))} {R(x.get('text'))}" for x in v["takeaways"]]
            L.append("")
        if v.get("caveats"):
            L += [f"读之前需要知道：{R(v['caveats'])}", ""]
    if g.get("framework"):
        L.append(f"## 内容结构\n\n按视频顺序分成 {len(g['framework'])} 段。\n")
        for f in g["framework"]:
            end = f"（至 {fmt_ts(parse_ts(f['end']))}）" if f.get("end") is not None else ""
            L.append(f"### {T(f.get('start'))} {f.get('title')}{end}")
            if f.get("summary"):
                L.append(R(f["summary"]) + "\n")
            L += [f"- {T(p.get('t'))} {R(p.get('text'))}" for p in f.get("points", [])]
            L.append("")
    if g.get("viewpoints"):
        one = _sole_speaker(g["viewpoints"])
        L.append("## 主要观点\n" + (f"\n以下都是 {one} 的观点。\n" if one else ""))
        for x in g["viewpoints"]:
            who = "" if one or not x.get("speaker") else f"（{x['speaker']}）"
            L.append(f"- **{x.get('title')}** {T(x.get('t'))}{who}")
            if x.get("detail"):
                L.append(f"  {R(x['detail'])}")
            if x.get("evidence"):
                L.append(f"  依据：{R(x['evidence'])}")
        L.append("")
    if g.get("quotes"):
        one = _sole_speaker(g["quotes"])
        L.append("## 金句\n\n" + (f"{one} 的原话，" if one else "") + "英文与字幕逐句核对过。\n")
        for q in g["quotes"]:
            L.append(f"> {q.get('zh')}  ")
            if q.get("en"):
                L.append(f"> *{q['en']}*  ")
            L.append(f"> {T(q.get('t'))}" + ("" if one else f" {q.get('speaker', '')}"))
            if q.get("why"):
                L.append(f"\n{R(q['why'])}")
            L.append("")
    if g.get("conflicts"):
        L.append(f"## 观点冲突\n")
        for c in g["conflicts"]:
            L.append(f"### {c.get('topic')}" + (f"（{c['type']}）" if c.get("type") else ""))
            for s in ("a", "b"):
                if c.get(s):
                    L.append(f"- {c[s].get('who')} {T(c[s].get('t'))}：{R(c[s].get('claim'))}")
            if c.get("analysis"):
                L.append(f"\n怎么看：{R(c['analysis'])}")
            L.append("")
    if g.get("hotspots"):
        basis = "和".join(x for x in ["重复观看曲线" if extra.get("has_heatmap") else "",
                                    f"评论里的 {extra['timestamp_mentions']} 处时间戳" if extra.get("timestamp_mentions") else ""] if x)
        L.append("## 讨论热点\n" + (f"\n根据{basis}找出观众最在意的片段。热度以全片最高点为 100。\n" if basis else ""))
        names = {"heatmap": "回看高峰", "comments": "评论提到", "content": "内容判断"}
        for i, h in enumerate(g["hotspots"], 1):
            srcs = h.get("source") if isinstance(h.get("source"), list) else [h.get("source")]
            src = " + ".join(names.get(s, s) for s in srcs if s)
            L.append(f"### {T(h.get('t'))} {h.get('title')}")
            L.append(f"热度 {round(float(h.get('heat') or 0) * 100)}，{src}\n")
            if h.get("why"):
                L.append(R(h["why"]) + "\n")
            if h.get("supplement"):
                L.append(f"补充：{R(h['supplement'])}\n")
            for c in h.get("comments", []):
                L.append(f"> {c.get('text_zh') or c.get('text')}" + (f"（{_num_zh(c['likes'])} 赞）" if c.get("likes") else ""))
            L.append("")
    if g.get("comment_insights"):
        n = extra.get("comments_analyzed")
        L.append("## 评论区\n" + (f"\n从 {n} 条热门评论里归纳。\n" if n else ""))
        for c in g["comment_insights"]:
            L.append(f"- **{c.get('theme')}**" + (f"（{c['stance']}）" if c.get("stance") else "") +
                     f" {T(c.get('t'))} {R(c.get('summary'))}")
        L.append("")
    if g.get("resources"):
        L.append("## 提到的书和资源\n")
        L += [f"- {T(r.get('t'))} {r.get('name')}" + (f"，{R(r['note'])}" if r.get("note") else "") for r in g["resources"]]
        L.append("")
    if g.get("glossary"):
        L.append("## 术语与更正\n")
        L += [f"- {x.get('term')}：{x.get('zh', '')}" + (f"。{R(x['note'])}" if x.get("note") else "") for x in g["glossary"]]
        L.append("")
    if transcript and any(r.get("zh") for r in transcript):
        L.append("## 全文译稿\n")
        for r in transcript:
            spk = f"**{r['speaker']}**：" if r.get("speaker") else ""
            L.append(f"{T(r['t'])} {spk}{r.get('zh') or r.get('en')}\n")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--digest", default=None, help="default: <work>/digest.json")
    ap.add_argument("--transcript-zh", default=None, help="default: <work>/transcript_zh.md")
    ap.add_argument("--out", default=None, help="output dir (default: work dir)")
    ap.add_argument("--name", default="report")
    ap.add_argument("--strict", action="store_true", help="exit 1 on validation errors")
    ap.add_argument("--no-transcript", action="store_true",
                    help="omit the full transcript section (for publicly shared reports / copyright)")
    args = ap.parse_args()
    w = args.work
    out = args.out or w
    os.makedirs(out, exist_ok=True)

    meta = load(os.path.join(w, "meta.json"), {})
    heat = load(os.path.join(w, "heatmap.json"), [])
    signals = load(os.path.join(w, "signals.json"), {})
    paras = load(os.path.join(w, "paragraphs.json"), [])
    digest = load(args.digest or os.path.join(w, "digest.json"))
    if digest is None:
        sys.exit("digest.json not found — write it first (see references/digest-schema.md)")
    duration = meta.get("duration") or (paras[-1]["end"] if paras else 0)

    errors, warns = validate(digest, duration, paras)
    transcript = [] if args.no_transcript else \
        load_transcript_zh(args.transcript_zh or os.path.join(w, "transcript_zh.md"), paras)

    payload = {
        "meta": meta, "digest": digest, "transcript": transcript,
        # only what the page draws: no raw comment text is embedded in the HTML
        "signals": {"heatmap": heat,
                    "comment_anchors": [{"t": a["t"], "mentions": a["mentions"]}
                                        for a in signals.get("comment_anchors", [])],
                    "peaks": [{k: p[k] for k in ("start", "end", "value") if k in p}
                              for p in signals.get("peaks", [])],
                    "comments_analyzed": signals.get("comments_analyzed"),
                    "timestamp_mentions": signals.get("timestamped_mentions")},
        "generated_at": datetime.date.today().isoformat(),
    }
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    title = (digest.get("title_zh") or meta.get("title") or "YouTube 访谈精读")
    html = tpl.replace("__TITLE__", title.replace("<", "&lt;")).replace("__DATA_JSON__", data)
    html_path = os.path.join(out, f"{args.name}.html")
    md_path = os.path.join(out, f"{args.name}.md")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(to_markdown(meta, digest, transcript, meta.get("id"),
                            {"has_heatmap": bool(heat), "comments_analyzed": signals.get("comments_analyzed"),
                             "timestamp_mentions": signals.get("timestamped_mentions")}))

    n_ts = sum(len(g(digest)) for g in REQ.values())
    print(json.dumps({"html": html_path, "md": md_path, "timestamps": n_ts,
                      "transcript_rows": len(transcript), "errors": errors, "warnings": warns},
                     ensure_ascii=False, indent=1))
    if errors and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
