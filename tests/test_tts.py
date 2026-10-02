"""Regression guard for the in-page voice-reading (TTS) feature.

Pure static checks on assets/report_template.html — no browser needed.
If the TTS controls or the SpeechSynthesis wiring are accidentally removed,
this test fails before the report page ships half-broken.
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
CANDIDATES = [
    os.path.join(ROOT, "skills", "youtube-interview-digest", "assets", "report_template.html"),
    os.path.join(ROOT, "assets", "report_template.html"),
]
TEMPLATE = next((p for p in CANDIDATES if os.path.isfile(p)), CANDIDATES[0])


class TestTtsControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(TEMPLATE, encoding="utf-8") as f:
            cls.html = f.read()

    def test_template_exists(self):
        self.assertTrue(os.path.isfile(TEMPLATE), "report_template.html missing")

    def test_control_ids_present(self):
        # The read-aloud toolbar ids (renamed from tts/ttsStop/ttsLang/ttsRate when the
        # toolbar was rebuilt; the button now toggles play/stop instead of a separate #ttsStop).
        for cid in ("readAll", "rdLang", "rdRate", "rdSrc"):
            self.assertIn(f'id="{cid}"', self.html,
                          f"TTS control #{cid} not found in template")

    def test_speech_synthesis_api_used(self):
        self.assertIn("speechSynthesis", self.html, "window.speechSynthesis not referenced")
        self.assertIn("SpeechSynthesisUtterance", self.html,
                      "SpeechSynthesisUtterance not used")

    def test_language_options_cover_zh_and_en(self):
        # bilingual + English options only render when English exists, but 中文 must always be there
        self.assertRegex(self.html, r'<option value="zh"[^>]*>中文</option>',
                         "中文 (zh) voice option missing")
        self.assertIn('<option value="en">English</option>', self.html,
                      "English (en) voice option missing")

    def test_rate_options_present(self):
        for rate in ("0.85", "0.95", "1.1", "1.25", "1.5"):
            self.assertIn(f'value="{rate}"', self.html,
                          f"TTS rate option {rate}× missing")

    def test_speaking_highlight_class_defined(self):
        self.assertIn(".tr .row.speaking", self.html,
                      "missing .speaking highlight style for the read-aloud row")

    def test_no_placeholder_leftovers(self):
        # make sure the toolbar string is a normal template literal, not a leftover token
        self.assertNotIn("__TTS__", self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
