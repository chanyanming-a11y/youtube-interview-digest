"""Tests for the skill's security-relevant helpers (stdlib only, no network).

These pin down the SSRF guard in page_fallback.py, the same-origin check on the
local TTS proxy in serve_report.py, and the HTML title escaping in
render_report.py so a regression can't silently reopen an injection vector.
"""
import functools
import importlib.util
import ipaddress
import json
import os
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "skills", "youtube-interview-digest", "scripts")


def _load(name):
    """Load a skill script by file path (its parent dir has a hyphen, so it is
    not a normal importable package)."""
    path = os.path.join(SCRIPTS, name)
    spec = importlib.util.spec_from_file_location("yid_" + name[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


page_fallback = _load("page_fallback.py")
render_report = _load("render_report.py")
serve_report = _load("serve_report.py")


class SsrfGuardHostTest(unittest.TestCase):
    def test_blocks_ip_literals(self):
        for ip in ("127.0.0.1", "169.254.169.254", "::1", "10.0.0.5",
                   "192.168.1.1", "0.0.0.0", "fe80::1", "[::1]:8080",
                   "fd00::1", "[fe80::1]:9999"):
            self.assertFalse(page_fallback._host_safe(ip), f"should block {ip}")

    def test_blocks_loopback_and_internal_names(self):
        for h in ("localhost", "foo.local", "bar.internal", "metadata",
                  "metadata.google.internal"):
            self.assertFalse(page_fallback._host_safe(h), f"should block {h}")

    def test_allows_public_hosts(self):
        for h in ("example.com", "sub.stack.com", "www.youtube.com",
                  "lenny.substack.com", "a.b.c.example.org"):
            self.assertTrue(page_fallback._host_safe(h), f"should allow {h}")


class SsrfGuardUrlTest(unittest.TestCase):
    def test_scheme_restricted(self):
        self.assertTrue(page_fallback._url_safe("https://sub.stack.com/api/posts/x"))
        self.assertTrue(page_fallback._url_safe("http://example.com/x"))
        # non-http(s) schemes are rejected outright
        self.assertFalse(page_fallback._url_safe("ftp://example.com/x"))
        self.assertFalse(page_fallback._url_safe("file:///etc/passwd"))
        self.assertFalse(page_fallback._url_safe("javascript:alert(1)"))

    def test_blocks_internal_hosts_in_url(self):
        self.assertFalse(page_fallback._url_safe("http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(page_fallback._url_safe("http://localhost:8080/"))
        self.assertFalse(page_fallback._url_safe("http://10.0.0.1/secret"))
        self.assertFalse(page_fallback._url_safe("http://127.0.0.1:8080/"))

    def test_rejects_urls_without_host(self):
        self.assertFalse(page_fallback._url_safe("not a url"))
        self.assertFalse(page_fallback._url_safe(""))


class SsrfResolvedIpTest(unittest.TestCase):
    """The literal check can be bypassed by a hostname that resolves inward, so
    every resolved address must also be public."""

    def test_rejects_non_public_addresses(self):
        for s in ("127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1",
                  "169.254.169.254", "0.0.0.0", "::1", "fe80::1", "fd00::1",
                  "::ffff:127.0.0.1", "::ffff:10.0.0.1"):
            self.assertFalse(
                page_fallback._ip_public(ipaddress.ip_address(s)),
                f"should treat {s} as non-public")

    def test_allows_public_addresses(self):
        for s in ("1.1.1.1", "93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"):
            self.assertTrue(
                page_fallback._ip_public(ipaddress.ip_address(s)),
                f"should treat {s} as public")

    def test_localhost_resolution_is_rejected(self):
        # resolves via /etc/hosts, so this works offline
        self.assertFalse(page_fallback._resolve_safe("localhost"))

    def test_url_fetchable_still_blocks_literals(self):
        self.assertFalse(page_fallback._url_fetchable("http://127.0.0.1:8080/"))
        self.assertFalse(page_fallback._url_fetchable("http://localhost/"))


class SafeRedirectTest(unittest.TestCase):
    """urllib follows redirects transparently, so the target must be re-checked."""

    def setUp(self):
        self.handler = page_fallback._SafeRedirectHandler()
        self.req = urllib.request.Request("https://example.com/start")

    def test_blocks_redirect_to_internal_addresses(self):
        for target in ("http://127.0.0.1:8080/x",
                       "http://169.254.169.254/latest/meta-data/",
                       "http://10.0.0.1/secret",
                       "file:///etc/passwd"):
            with self.assertRaises(urllib.error.HTTPError, msg=target):
                self.handler.redirect_request(self.req, None, 302, "Found", {}, target)

    def test_allows_redirect_to_public_host(self):
        got = self.handler.redirect_request(
            self.req, None, 302, "Found", {}, "https://example.com/next")
        self.assertEqual(got.get_full_url(), "https://example.com/next")


class TtsProxyOriginTest(unittest.TestCase):
    """The local TTS proxy must not be reachable from an arbitrary web page."""

    class _Fake:
        def __init__(self, headers):
            self.headers = headers

    def _allowed(self, headers):
        return serve_report.Handler._origin_allowed(TtsProxyOriginTest._Fake(headers))

    def test_allows_same_loopback_origin(self):
        for origin in ("http://127.0.0.1:8765",
                       "http://localhost:8765",
                       "http://127.0.0.1:8765/report.html",
                       "http://[::1]:8765"):
            self.assertTrue(self._allowed({"Origin": origin}), origin)

    def test_allows_missing_origin(self):
        # curl / top-level navigation send no Origin or Referer
        self.assertTrue(self._allowed({}))
        self.assertTrue(self._allowed({"Referer": "http://127.0.0.1:8765/report.html"}))

    def test_blocks_remote_origins(self):
        for origin in ("https://evil.example",
                       "http://192.168.1.50:8765",
                       "http://127.0.0.1.evil.example",
                       "null"):
            self.assertFalse(self._allowed({"Origin": origin}), origin)

    def test_prefers_origin_over_referer(self):
        # a forged loopback Referer must not override a remote Origin
        self.assertFalse(self._allowed({"Origin": "https://evil.example",
                                        "Referer": "http://127.0.0.1:8765/"}))

    def test_tts_responses_do_not_send_wildcard_cors(self):
        with open(os.path.join(SCRIPTS, "serve_report.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn('Access-Control-Allow-Origin", "*"', src)


class ServeReportServerTest(unittest.TestCase):
    """End-to-end checks on the tiny localhost server that serves report.html."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        pathlib.Path(self._tmp.name, "report.html").write_text(
            "<h1>demo</h1>", encoding="utf-8")
        handler = functools.partial(serve_report.Handler, directory=self._tmp.name)
        # port 0 => the OS picks a free one, so tests never collide
        self.httpd = serve_report._Server(("127.0.0.1", 0), handler)
        self.httpd.tts_cfg = None
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def _url(self, path="/report.html"):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_reuse_address_is_set_before_bind(self):
        # Assigning it on the instance after construction is a no-op, which used
        # to make a quick restart hop to the next port instead of reusing this one.
        self.assertTrue(serve_report._Server.allow_reuse_address)

    def test_binds_loopback_only(self):
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")

    def test_serves_the_report(self):
        with urllib.request.urlopen(self._url(), timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("demo", resp.read().decode())

    def test_unknown_post_route_is_rejected(self):
        req = urllib.request.Request(self._url("/nope"), data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 405)

    def test_tts_blocked_for_remote_origin(self):
        req = urllib.request.Request(
            self._url("/tts"), data=b"{}", method="POST",
            headers={"Origin": "https://evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)

    def test_tts_rejects_empty_text(self):
        req = urllib.request.Request(self._url("/tts"), data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_tts_without_config_reports_not_implemented(self):
        # no Origin header => allowed, but there is no appid/token configured
        req = urllib.request.Request(
            self._url("/tts"),
            data=json.dumps({"text": "你好", "source": "doubao"}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 501)
        body = ctx.exception.read()
        # a hand-written Content-Length that disagrees with the body makes the
        # browser hang waiting for bytes that never arrive
        self.assertEqual(len(body), int(ctx.exception.headers["Content-Length"]))


class TitleEscapeTest(unittest.TestCase):
    def test_escapes_angle_brackets_and_amp(self):
        self.assertEqual(render_report._escape_title("<b>&'x'"), "&lt;b&gt;&amp;'x'")

    def test_double_quote_not_escaped(self):
        # quote=False: only <, >, & are escaped
        self.assertEqual(render_report._escape_title('a "b"'), 'a "b"')

    def test_none_is_safe(self):
        self.assertEqual(render_report._escape_title(None), "")

    def test_injection_cannot_break_out_of_title(self):
        evil = "</title><script>alert(1)</script>"
        escaped = render_report._escape_title(evil)
        self.assertNotIn("</title>", escaped)
        self.assertNotIn("<script>", escaped)
        self.assertIn("&lt;", escaped)


if __name__ == "__main__":
    unittest.main()
