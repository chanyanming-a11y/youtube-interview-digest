#!/usr/bin/env python3
"""
Serve a report work-dir over localhost so the embedded YouTube player can play
in-page, and (optionally) act as a local proxy for 字节火山引擎「语音合成」
(豆包音色) TTS and 微软在线语音 (Edge TTS / 晓晓 Neural 音色) — keeping any
API secret on the server instead of in the page. Edge TTS is free, needs no
key, and is auto-preferred when `edge-tts` is installed; 豆包 needs appid/token.

Why: YouTube rejects embedding from a `file://` page (player error 153). Opening
the same report.html over http://127.0.0.1 gives the iframe API a proper origin
so the video plays inline and timecode clicks seek instead of opening a tab.

The TTS proxy (`POST /tts`, `GET /tts/status`) only responds on 127.0.0.1, so the
appid/token never leaves this machine and is never embedded in the HTML.

Usage:
  python serve_report.py --work ./yt_VIDEOID            # prints the URL and serves
  python serve_report.py --work ./yt_VIDEOID --open     # also opens the browser
  python serve_report.py --work ./yt_VIDEOID --port 9000
  python serve_report.py --work ./yt_VIDEOID --tts-config /path/to/tts_config.json

TTS config (JSON) is searched in this order: --tts-config, $YTD_TTS_CONFIG, then
<this script dir>/tts_config.json. With no config, /tts returns 501 and the
report page silently keeps using the browser's native speech synthesis.
"""
import argparse
import asyncio
import base64
import functools
import http.server
import json
import os
import socketserver
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

REQUIRED = "report.html"
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def load_tts_config(explicit=None):
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("YTD_TTS_CONFIG"):
        candidates.append(os.environ["YTD_TTS_CONFIG"])
    candidates.append(os.path.join(SCRIPTS_DIR, "tts_config.json"))
    for path in candidates:
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    cfg = json.load(f)
                if cfg.get("appid") and cfg.get("token"):
                    return cfg
            except Exception:
                return None
    return None


# ---------------------------------------------------------------- Edge TTS (微软 在线语音, 免费无需密钥)
# 这是目前最热门、最自然的免费中文 TTS（晓晓 / XiaoxiaoNeural 等 Neural 语音）。
# 需要本地装了 edge-tts 库（`pip install edge-tts`）且可联网；否则自动降级。
EDGE_VOICES = {"zh": "zh-CN-XiaoxiaoNeural", "en": "en-US-AriaNeural"}


def _edge_available():
    try:
        import edge_tts  # noqa: F401
        return True
    except Exception:
        return False


def _edge_tts_bytes(text, lang, rate):
    import edge_tts
    voice = EDGE_VOICES.get("en" if str(lang).lower().startswith("en") else "zh", EDGE_VOICES["zh"])
    pct = int(round((float(rate) - 1.0) * 100))
    rate_str = ("+" if pct >= 0 else "") + str(pct) + "%"
    async def _run():
        comm = edge_tts.Communicate(text, voice, rate=rate_str)
        buf = b""
        async for chunk in comm.stream():
            if chunk.get("type") == "audio":
                buf += chunk["data"]
        return buf
    return asyncio.run(_run())


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # The report body is rendered client-side from embedded JSON, so a cached
        # old report.html would keep running stale JS (e.g. an older read-aloud).
        # Never let the browser / preview panel serve a stale copy.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _deny(self, code=405):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"error":"method not allowed"}')

    def _tts_status(self):
        cfg = getattr(self.server, "tts_cfg", None)
        doubao = bool(cfg and cfg.get("appid") and cfg.get("token"))
        edge = _edge_available()
        available = doubao or edge
        voices = {
            "doubao_zh": cfg.get("voice_zh") if doubao else None,
            "doubao_en": cfg.get("voice_en") if doubao else None,
            "edge": EDGE_VOICES if edge else None,
        }
        body = json.dumps({"available": available, "doubao": doubao, "edge": edge, "voices": voices}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _tts_synth(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            payload = {}
        source = (payload.get("source") or "doubao").strip().lower()
        text = (payload.get("text") or "").strip()
        lang = (payload.get("lang") or "zh-CN")
        try:
            rate = float(payload.get("rate") or 1.0)
        except Exception:
            rate = 1.0
        # guard: avoid absurd requests / abuse of the local proxy
        if not text or len(text) > 600:
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"error":"bad request text"}')
            return

        if source == "edge":
            self._edge_synth(text, lang, rate)
            return

        # default: 豆包 (火山引擎) via config
        cfg = getattr(self.server, "tts_cfg", None)
        if not (cfg and cfg.get("appid") and cfg.get("token")):
            self.send_response(501)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", "43")
            self.end_headers()
            self.wfile.write(b'{"error":"doubao tts not configured"}')
            return

        voice = cfg.get("voice_en") if str(lang).lower().startswith("en") else cfg.get("voice_zh")
        body = {
            "app": {
                "appid": cfg["appid"],
                "token": cfg["token"],
                "cluster": cfg.get("cluster", "volcano_tts"),
            },
            "user": {"uid": "ytd-report"},
            "audio": {
                "voice_type": voice or cfg.get("voice_zh"),
                "encoding": cfg.get("encoding", "mp3"),
                "speed_ratio": max(0.5, min(2.0, rate)),
            },
            "request": {
                "reqid": os.urandom(8).hex(),
                "text": text,
                "operation": "query",
            },
        }
        endpoint = cfg.get("endpoint", "https://openspeech.bytedance.com/api/v1/tts")
        auth_tpl = cfg.get("auth_header_template", "Bearer; {token}")
        headers = {
            "Content-Type": "application/json",
            "Authorization": auth_tpl.replace("{token}", cfg["token"]),
        }
        req = urllib.request.Request(
            endpoint, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "upstream", "status": e.code}).encode("utf-8"))
            return
        except Exception as e:  # network / DNS / timeout
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "upstream", "detail": str(e)}).encode("utf-8"))
            return

        try:
            j = json.loads(raw)
            if j.get("code") != 3000 or not j.get("data"):
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(
                    {"error": "upstream", "message": j.get("message")}).encode("utf-8"))
                return
            audio = base64.b64decode(j["data"])
        except Exception:
            audio = raw  # some deployments return raw audio bytes directly

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(audio)

    def _edge_synth(self, text, lang, rate):
        if not _edge_available():
            self.send_response(501)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"error":"edge tts not installed (pip install edge-tts)"}')
            return
        try:
            audio = _edge_tts_bytes(text, lang, rate)
        except Exception as e:  # network / DNS / auth
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "edge upstream", "detail": str(e)}).encode("utf-8"))
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(audio)

    def do_GET(self):
        if self.path == "/tts/status":
            self._tts_status()
            return
        if self.path == "/tts":
            self._deny(405)
            return
        super().do_GET()

    def do_POST(self):
        if self.path == "/tts":
            self._tts_synth()
            return
        if self.path == "/tts/status":
            self._tts_status()
            return
        self._deny(405)

    def log_message(self, *args):
        pass  # keep the server quiet


def main():
    ap = argparse.ArgumentParser(description="Serve a report over localhost for inline playback + optional 豆包 TTS proxy.")
    ap.add_argument("--work", required=True, help="work dir containing report.html")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the URL in the default browser")
    ap.add_argument("--tts-config", default=None, help="path to tts_config.json (appid/token)")
    args = ap.parse_args()

    work = os.path.abspath(args.work)
    target = os.path.join(work, REQUIRED)
    if not os.path.exists(target):
        sys.exit(f"{REQUIRED} not found in {work} — run render_report.py first.")

    handler = functools.partial(Handler, directory=work)

    httpd = None
    for port in range(args.port, args.port + 20):          # find a free port
        try:
            httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler)
            break
        except OSError:
            continue
    if httpd is None:
        sys.exit(f"no free port in {args.port}-{args.port + 19}")

    httpd.allow_reuse_address = True
    httpd.tts_cfg = load_tts_config(args.tts_config)

    url = f"http://127.0.0.1:{port}/{REQUIRED}"
    print(url, flush=True)
    if args.open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
