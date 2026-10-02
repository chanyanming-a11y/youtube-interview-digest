"""Tests for digest validation and Markdown rendering (stdlib only, no network).

`render_report.py --strict` is the guard that stops an unsourced report from
shipping, so its checks get pinned down here.
"""
import importlib.util
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "skills", "youtube-interview-digest", "scripts")


def _load(name):
    path = os.path.join(SCRIPTS, name)
    spec = importlib.util.spec_from_file_location("yid_" + name[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rr = _load("render_report.py")

PARAS = [
    {"start": 0, "text": "the metric you choose decides the product you build"},
    {"start": 60, "text": "we switched from daily actives to hours per payer"},
]


def _digest(**over):
    g = {
        "title_zh": "标题",
        "one_liner": "一句话结论",
        "tldr": [{"text": "要点", "t": "00:30"}],
        "value": {"score": 4, "takeaways": [{"text": "收获", "t": "01:00"}]},
        "framework": [{"title": "段", "start": "00:10", "end": "01:00",
                       "points": [{"text": "点", "t": "00:30"}]}],
        "viewpoints": [{"title": "观点", "t": "01:00"}],
        "quotes": [{"zh": "译文", "en": "the metric you choose decides the product you build",
                    "t": "00:00"}],
        "conflicts": [{"topic": "题", "a": {"who": "A", "claim": "c", "t": "00:30"},
                       "b": {"who": "B", "claim": "c", "t": "01:00"}}],
        "hotspots": [{"title": "热点", "t": "00:30", "heat": 0.9}],
    }
    g.update(over)
    return g


class NormTest(unittest.TestCase):
    def test_lowercases_and_strips_punctuation(self):
        self.assertEqual(rr._norm("Hello, World!"), ["hello", "world"])

    def test_empty(self):
        self.assertEqual(rr._norm(""), [])


class TimestampRenderingTest(unittest.TestCase):
    def test_md_ts_makes_youtube_link(self):
        self.assertIn("&t=754s", rr.md_ts("12:34", "ABCDEFGHIJK"))

    def test_md_ts_without_video_id(self):
        self.assertEqual(rr.md_ts("12:34", None), "`12:34`")

    def test_md_ts_invalid(self):
        self.assertEqual(rr.md_ts("nope", "ABCDEFGHIJK"), "")

    def test_md_rich_converts_inline_timestamps(self):
        out = rr.md_rich("见 [12:34] 和 [01:00-02:00]", "ABCDEFGHIJK")
        self.assertIn("&t=754s", out)
        self.assertNotIn("[12:34]", out)

    def test_md_rich_handles_none(self):
        self.assertEqual(rr.md_rich(None, "X"), "")


class HelperTest(unittest.TestCase):
    def test_num_zh(self):
        self.assertEqual(rr._num_zh(999), "999")
        self.assertEqual(rr._num_zh(325227), "32.5 万")
        self.assertIsNone(rr._num_zh(None))

    def test_sole_speaker(self):
        self.assertEqual(rr._sole_speaker([{"speaker": "A"}, {"speaker": "A"}]), "A")
        self.assertIsNone(rr._sole_speaker([{"speaker": "A"}, {"speaker": "B"}]))
        self.assertIsNone(rr._sole_speaker([{"speaker": "A"}, {}]))


class ValidateTest(unittest.TestCase):
    def test_clean_digest_has_no_errors(self):
        errors, warns = rr.validate(_digest(), 120, PARAS)
        self.assertEqual(errors, [])
        self.assertEqual(warns, [])

    def test_missing_timestamp_is_an_error(self):
        g = _digest(framework=[{"title": "段", "start": None, "points": []}])
        errors, _ = rr.validate(g, 120, PARAS)
        self.assertTrue(any("framework[0].start" in e for e in errors), errors)

    def test_timestamp_beyond_duration_is_an_error(self):
        g = _digest(viewpoints=[{"title": "观点", "t": "99:00"}])
        errors, _ = rr.validate(g, 120, PARAS)
        self.assertTrue(any("beyond video duration" in e for e in errors), errors)

    def test_comment_insights_missing_ts_is_only_a_warning(self):
        g = _digest(comment_insights=[{"theme": "主题", "summary": "s"}])
        errors, warns = rr.validate(g, 120, PARAS)
        self.assertEqual(errors, [])
        self.assertTrue(any("comment_insights[0]" in w for w in warns), warns)

    def test_empty_required_section_warns(self):
        g = _digest(quotes=[])
        _, warns = rr.validate(g, 120, PARAS)
        self.assertTrue(any("'quotes' is empty" in w for w in warns), warns)


class QuoteVerificationTest(unittest.TestCase):
    def test_unfindable_quote_is_an_error(self):
        g = _digest(quotes=[{"zh": "x", "en": "totally fabricated sentence here", "t": "00:00"}])
        errors, _ = rr.validate(g, 120, PARAS)
        self.assertTrue(any("not found in transcript" in e for e in errors), errors)

    def test_drifting_timestamp_is_corrected_with_a_warning(self):
        # claim 10:00 for a line that is actually at 00:00 -> moved to 0
        g = _digest(quotes=[{"zh": "x",
                             "en": "the metric you choose decides the product you build",
                             "t": "10:00"}])
        errors, warns = rr.validate(g, 3600, PARAS)
        self.assertEqual(errors, [])
        self.assertTrue(any("not near any occurrence" in w for w in warns), warns)
        self.assertEqual(g["quotes"][0]["t"], 0)

    def test_quote_without_english_is_only_a_warning(self):
        g = _digest(quotes=[{"zh": "x", "t": "00:00"}])
        errors, warns = rr.validate(g, 120, PARAS)
        self.assertEqual(errors, [])
        self.assertTrue(any("no English original" in w for w in warns), warns)


class MarkdownTest(unittest.TestCase):
    META = {"title": "Original Title", "channel": "Chan", "duration": 120,
            "url": "https://www.youtube.com/watch?v=ABCDEFGHIJK",
            "upload_date": "20261002", "view_count": 12345, "id": "ABCDEFGHIJK"}

    def test_renders_core_sections(self):
        md = rr.to_markdown(self.META, _digest(), [], "ABCDEFGHIJK", {})
        for heading in ("## 结论", "## 内容结构", "## 主要观点", "## 金句", "## 观点冲突", "## 讨论热点"):
            self.assertIn(heading, md)
        self.assertIn("原标题：Original Title", md)
        self.assertIn("2026-10-02", md)

    def test_timestamps_become_links(self):
        md = rr.to_markdown(self.META, _digest(), [], "ABCDEFGHIJK", {})
        self.assertIn("https://www.youtube.com/watch?v=ABCDEFGHIJK&t=30s", md)

    def test_hotspot_basis_mentions_heatmap_when_present(self):
        g = _digest(hotspots=[{"title": "h", "t": "00:30", "heat": 0.5,
                              "source": ["heatmap", "comments"]}])
        md = rr.to_markdown(self.META, g, [], "ABCDEFGHIJK",
                            {"has_heatmap": True, "timestamp_mentions": 6})
        self.assertIn("重复观看曲线", md)
        self.assertIn("评论提到", md)

    def test_transcript_section_appended(self):
        rows = [{"t": 0, "speaker": "Host", "zh": "你好", "en": "hi"}]
        md = rr.to_markdown(self.META, _digest(), rows, "ABCDEFGHIJK", {})
        self.assertIn("## 全文译稿", md)
        self.assertIn("**Host**：你好", md)

    def test_no_transcript_rows_means_no_section(self):
        md = rr.to_markdown(self.META, _digest(), [], "ABCDEFGHIJK", {})
        self.assertNotIn("## 全文译稿", md)


if __name__ == "__main__":
    unittest.main()
