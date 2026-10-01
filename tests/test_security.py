"""Tests for the skill's security-relevant helpers (stdlib only, no network).

These pin down the SSRF guard in page_fallback.py and the HTML title escaping in
render_report.py so a regression can't silently reintroduce an injection vector.
"""
import importlib.util
import os
import unittest

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
