#!/usr/bin/env python3
"""
Transcript utilities: parse subtitles (json3 / vtt / srt / timestamped txt),
dedupe rolling auto-captions, merge into timestamped paragraphs, and write the
work-dir artefacts consumed by later steps.

CLI (local file mode, when the transcript is supplied by the user):
    python transcript_utils.py --file talk.vtt --out ./work --video-id dQw4w9WgXcQ
"""
import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- time helpers

def fmt_ts(sec):
    sec = int(max(0, round(float(sec))))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


_TS_RE = re.compile(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$")


def parse_ts(value):
    """Accept seconds (int/float/str) or 'mm:ss' / 'h:mm:ss' / 'hh:mm:ss.mmm'."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    v = str(value).strip().strip("[]()")
    if re.fullmatch(r"\d+(\.\d+)?s?", v):
        return float(v.rstrip("s"))
    m = _TS_RE.match(v)
    if not m:
        return None
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + (int(ms) / 1000 if ms else 0)


# ---------------------------------------------------------------- parsers

def _clean(text):
    text = re.sub(r"<[^>]+>", "", text)          # inline vtt tags / <c>
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")
    text = re.sub(r"\[(?:Music|Applause|Laughter|音乐|掌声|笑声)\]", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def parse_json3(data):
    if isinstance(data, str):
        data = json.loads(data)
    segs = []
    for ev in data.get("events", []):
        if "segs" not in ev:
            continue
        text = _clean("".join(s.get("utf8", "") for s in ev["segs"]))
        if not text:
            continue
        start = ev.get("tStartMs", 0) / 1000
        dur = ev.get("dDurationMs", 0) / 1000
        segs.append({"start": start, "end": start + dur, "text": text})
    return _dedupe(segs)


def _parse_cues(text, sep_re):
    segs = []
    blocks = re.split(r"\n\s*\n", text.replace("\r", ""))
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip()]
        idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if idx is None:
            continue
        a, _, rest = lines[idx].partition("-->")
        b_ = rest.strip().split(" ")[0]
        start, end = parse_ts(a.strip()), parse_ts(b_)
        body = _clean(" ".join(lines[idx + 1:]))
        if start is None or not body:
            continue
        segs.append({"start": start, "end": end or start, "text": body})
    return _dedupe(segs)


def parse_vtt(text):
    return _parse_cues(text, None)


def parse_srt(text):
    return _parse_cues(text, None)


_LINE_TS = re.compile(r"^\s*[\[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?\s*[-–—:]?\s*(.*)$")


def parse_timestamped_txt(text):
    """Lines like '[12:34] text', '12:34 text', or YouTube 'Show transcript' copy
    (a timestamp line followed by text lines)."""
    segs, cur = [], None
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = _LINE_TS.match(line)
        if m and parse_ts(m.group(1)) is not None:
            if cur:
                segs.append(cur)
            cur = {"start": parse_ts(m.group(1)), "end": None, "text": _clean(m.group(2))}
        elif cur is not None:
            cur["text"] = (cur["text"] + " " + _clean(line)).strip()
    if cur:
        segs.append(cur)
    for i, s in enumerate(segs):
        s["end"] = segs[i + 1]["start"] if i + 1 < len(segs) else s["start"] + 5
    return [s for s in segs if s["text"]]


def _dedupe(segs):
    """Remove rolling duplicates typical of auto-captions."""
    out = []
    for s in segs:
        if out:
            prev = out[-1]["text"]
            if s["text"] == prev:
                out[-1]["end"] = max(out[-1]["end"], s["end"])
                continue
            if s["text"].startswith(prev) and len(prev) > 3:
                s = dict(s, text=s["text"][len(prev):].strip())
                if not s["text"]:
                    continue
        out.append(s)
    return out


def parse_file(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    ext = os.path.splitext(path)[1].lower()
    if ext in (".json", ".json3"):
        data = json.loads(raw)
        if isinstance(data, list):  # [{start,end|duration,text}]
            return [{"start": float(d["start"]),
                     "end": float(d.get("end", d["start"] + d.get("duration", 0))),
                     "text": _clean(d["text"])} for d in data if d.get("text")]
        return parse_json3(data)
    if ext == ".vtt" or raw.lstrip().startswith("WEBVTT"):
        return parse_vtt(raw)
    if ext == ".srt" or re.search(r"\d\d:\d\d:\d\d,\d{3}\s*-->", raw):
        return parse_srt(raw)
    return parse_timestamped_txt(raw)


# ---------------------------------------------------------------- paragraphs

_SENT_END = re.compile(r"[.?!。？！…]['\"”’)]?$")


def merge_paragraphs(segs, target=40, hard_max=75):
    """Merge caption fragments into ~40s paragraphs, breaking on speaker changes
    ('>>' in YouTube captions, or a `speaker` field from diarised transcripts) and
    sentence ends. Each paragraph keeps its start timestamp (and speaker if known)."""
    paras, cur = [], None
    for s in segs:
        text = s["text"]
        spk = s.get("speaker")
        speaker_change = text.startswith(">>") or text.startswith("- ") or \
            (spk is not None and cur is not None and spk != cur.get("speaker"))
        text = text.lstrip(">").lstrip("- ").strip() if text.startswith((">>", "- ")) else text.strip()
        if not text:
            continue
        if cur is None:
            cur = {"start": s["start"], "end": s["end"], "text": text, "speaker_change": True, "speaker": spk}
            continue
        dur = s["end"] - cur["start"]
        should_break = (
            speaker_change
            or (dur > target and _SENT_END.search(cur["text"]))
            or dur > hard_max
        )
        if should_break:
            paras.append(cur)
            cur = {"start": s["start"], "end": s["end"], "text": text, "speaker_change": speaker_change,
                   "speaker": spk if spk is not None else None}
        else:
            cur["text"] += " " + text
            cur["end"] = s["end"]
    if cur:
        paras.append(cur)
    for i, p in enumerate(paras):
        p["id"] = i + 1
        p["ts"] = fmt_ts(p["start"])
        if p.get("speaker") is None:
            p.pop("speaker", None)
    return paras


def write_workdir(out, segs, video_id=None, part_minutes=10):
    os.makedirs(out, exist_ok=True)
    paras = merge_paragraphs(segs)
    with open(os.path.join(out, "transcript_raw.json"), "w", encoding="utf-8") as f:
        json.dump(segs, f, ensure_ascii=False)
    with open(os.path.join(out, "paragraphs.json"), "w", encoding="utf-8") as f:
        json.dump(paras, f, ensure_ascii=False, indent=1)

    # transcript.md split into parts of ~part_minutes for chunked translation
    lines, part, part_start = [], 0, None
    step = part_minutes * 60
    for p in paras:
        if part_start is None or p["start"] >= part_start + step:
            part += 1
            part_start = (p["start"] // step) * step
            lines.append(f"\n## Part {part} ({fmt_ts(part_start)}–{fmt_ts(part_start + step)})\n")
        if p.get("speaker"):
            mark = f"{p['speaker']}: " if p["speaker_change"] else ""
        else:
            mark = ">> " if p["speaker_change"] else ""
        lines.append(f"[{p['ts']}] {mark}{p['text']}")
    header = f"# Transcript{' — ' + video_id if video_id else ''}\n\n" \
             f"> {len(paras)} paragraphs · {part} parts · " + \
             ("'Name:' = speaker (diarised)" if any(p.get("speaker") for p in paras) else "'>>' = speaker change") + "\n"
    with open(os.path.join(out, "transcript.md"), "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")
    words = sum(len(p["text"].split()) for p in paras)
    return {"paragraphs": len(paras), "parts": part, "words": words,
            "duration": paras[-1]["end"] if paras else 0}


def main():
    ap = argparse.ArgumentParser(description="Parse a local transcript file into the work dir.")
    ap.add_argument("--file", required=True, help=".vtt/.srt/.json3/.json/.txt with timestamps")
    ap.add_argument("--out", required=True)
    ap.add_argument("--video-id", default=None, help="11-char YouTube id (for timestamp links)")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()
    segs = parse_file(args.file)
    if not segs:
        sys.exit("No timestamped segments parsed. Ensure the file contains timestamps.")
    stats = write_workdir(args.out, segs, args.video_id)
    meta_path = os.path.join(args.out, "meta.json")
    if not os.path.exists(meta_path):
        meta = {"id": args.video_id, "title": args.title or os.path.basename(args.file),
                "url": f"https://www.youtube.com/watch?v={args.video_id}" if args.video_id else None,
                "duration": stats["duration"], "subtitle_source": f"local:{os.path.basename(args.file)}"}
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
