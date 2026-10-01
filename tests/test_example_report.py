"""Smoke test for the committed example / demo report (stdlib only, no network).

The repo ships a rendered example so newcomers can see the output format. This
test makes sure that demo asset doesn't silently go missing or stop being a real
rendered report (it should reference the demo video and contain real text).
"""
import html
import os
import unittest
from html.parser import HTMLParser

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE_HTML = os.path.join(REPO_ROOT, "docs", "example-report.html")
EXAMPLE_DIR = os.path.join(REPO_ROOT, "examples", "netflix-elizabeth-stone")
VIDEO_ID = "t0GiTyz4syY"


class _TextCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)


class ExampleReportTest(unittest.TestCase):
    def test_example_html_exists_and_is_rendered(self):
        self.assertTrue(os.path.isfile(EXAMPLE_HTML), "docs/example-report.html missing")
        with open(EXAMPLE_HTML, encoding="utf-8") as fh:
            raw = fh.read()
        self.assertIn("<html", raw.lower())
        self.assertIn(VIDEO_ID, raw, "example report should reference the demo video id")
        # Parse without error and collect substantial text content.
        parser = _TextCollector()
        parser.feed(raw)
        joined = "".join(parser.text)
        self.assertTrue(len(joined) > 200, "report should contain substantial text")
        self.assertIn("Netflix", joined)

    def test_example_artifact_trio_present(self):
        for name in ("report.html", "report.md", "digest.json"):
            path = os.path.join(EXAMPLE_DIR, name)
            self.assertTrue(os.path.isfile(path), f"missing example artifact: {name}")
            self.assertTrue(os.path.getsize(path) > 0, f"empty example artifact: {name}")


if __name__ == "__main__":
    unittest.main()
