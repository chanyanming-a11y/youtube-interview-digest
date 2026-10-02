"""Tests for transcript parsing / segmentation (stdlib only, no network).

These cover the path the README now points users at: bringing your own captions
(".srt" / ".vtt" / json3 / timestamped txt / text copied from YouTube's
"Show transcript" panel).
"""
import importlib.util
import json
import os
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "skills", "youtube-interview-digest", "scripts")


def _load(name):
    path = os.path.join(SCRIPTS, name)
    spec = importlib.util.spec_from_file_location("yid_" + name[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tu = _load("transcript_utils.py")


class ParseTsTest(unittest.TestCase):
    def test_accepts_seconds_and_clock_forms(self):
        self.assertEqual(tu.parse_ts(90), 90.0)
        self.assertEqual(tu.parse_ts("90"), 90.0)
        self.assertEqual(tu.parse_ts("90s"), 90.0)
        self.assertEqual(tu.parse_ts("12:34"), 754.0)
        self.assertEqual(tu.parse_ts("1:02:03"), 3723.0)
        self.assertEqual(tu.parse_ts("[12:34]"), 754.0)
        self.assertAlmostEqual(tu.parse_ts("00:00:01.500"), 1.5)

    def test_rejects_junk(self):
        for bad in (None, "", "abc", "12:7"):
            with self.subTest(bad=bad):
                self.assertIsNone(tu.parse_ts(bad))

    def test_fmt_ts(self):
        self.assertEqual(tu.fmt_ts(0), "00:00")
        self.assertEqual(tu.fmt_ts(754), "12:34")
        self.assertEqual(tu.fmt_ts(3723), "1:02:03")


class TimestampedTxtTest(unittest.TestCase):
    def test_bracket_and_bare_forms(self):
        segs = tu.parse_timestamped_txt("[00:01] hello\n[00:04] world")
        self.assertEqual([s["text"] for s in segs], ["hello", "world"])
        self.assertEqual(segs[0]["start"], 1.0)
        self.assertEqual(segs[0]["end"], 4.0)

    def test_youtube_show_transcript_copy(self):
        # what you get when you select-all in YouTube's transcript panel
        text = "0:00\nhello and welcome\n0:05\ntoday we're talking about startups\n"
        segs = tu.parse_timestamped_txt(text)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0]["text"], "hello and welcome")
        self.assertEqual(segs[1]["start"], 5.0)

    def test_multiline_body_is_joined(self):
        segs = tu.parse_timestamped_txt("00:02\nfirst line\nsecond line")
        self.assertEqual(segs[0]["text"], "first line second line")

    def test_ignores_empty_and_untimed_text(self):
        self.assertEqual(tu.parse_timestamped_txt("just prose, no timestamps"), [])


class CueFormatTest(unittest.TestCase):
    SRT = ("1\n00:00:01,000 --> 00:00:03,000\nHello there\n\n"
           "2\n00:00:04,500 --> 00:00:06,000\nGeneral Kenobi\n")
    VTT = ("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<c>Hello there</c>\n\n"
           "00:00:04.500 --> 00:00:06.000\nGeneral Kenobi\n")

    def test_srt(self):
        segs = tu.parse_srt(self.SRT)
        self.assertEqual([s["text"] for s in segs], ["Hello there", "General Kenobi"])
        self.assertAlmostEqual(segs[0]["start"], 1.0)

    def test_vtt_strips_inline_tags(self):
        segs = tu.parse_vtt(self.VTT)
        self.assertEqual(segs[0]["text"], "Hello there")

    def test_rolling_duplicates_are_merged(self):
        rolling = ("00:00:01 --> 00:00:03\nhello\n\n"
                   "00:00:03 --> 00:00:05\nhello\n\n"
                   "00:00:05 --> 00:00:07\nhello world\n")
        segs = tu.parse_vtt(rolling)
        self.assertEqual([s["text"] for s in segs], ["hello", "world"])
        self.assertEqual(segs[0]["end"], 5.0)

    def test_music_markers_stripped(self):
        segs = tu.parse_vtt("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n[Music] hi\n")
        self.assertEqual(segs[0]["text"], "hi")


class Json3Test(unittest.TestCase):
    def test_json3_events(self):
        data = {"events": [
            {"tStartMs": 1000, "dDurationMs": 2000,
             "segs": [{"utf8": "hello "}, {"utf8": "world"}]},
            {"tStartMs": 4000, "dDurationMs": 1000, "segs": [{"utf8": "bye"}]},
        ]}
        segs = tu.parse_json3(data)
        self.assertEqual(segs[0]["text"], "hello world")
        self.assertEqual(segs[0]["start"], 1.0)

    def test_plain_list_json(self):
        data = [{"start": 0, "duration": 2, "text": "a"}, {"start": 2, "end": 4, "text": "b"}]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f)
            segs = tu.parse_file(p)
        self.assertEqual([s["text"] for s in segs], ["a", "b"])
        self.assertEqual(segs[0]["end"], 2.0)


class ParseFileDispatchTest(unittest.TestCase):
    def _write(self, name, text):
        d = tempfile.mkdtemp()
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_dispatch_by_extension(self):
        self.assertEqual(len(tu.parse_file(self._write("a.srt", CueFormatTest.SRT))), 2)
        self.assertEqual(len(tu.parse_file(self._write("a.vtt", CueFormatTest.VTT))), 2)

    def test_dispatch_by_content_when_extension_unknown(self):
        # .vtt detected from the WEBVTT header, .srt from the "... -->" pattern
        self.assertEqual(len(tu.parse_file(self._write("a.txt", CueFormatTest.VTT))), 2)
        self.assertEqual(len(tu.parse_file(self._write("b.txt", CueFormatTest.SRT))), 2)

    def test_dispatch_to_timestamped_txt(self):
        p = self._write("c.txt", "[00:01] hi\n[00:03] there")
        self.assertEqual(len(tu.parse_file(p)), 2)


class MergeParagraphsTest(unittest.TestCase):
    def test_splits_on_speaker_change(self):
        # only a ">>" prefix marks a new speaker; lines without it continue the
        # current paragraph even when target/hard_max would otherwise allow a break
        segs = [{"start": 0, "end": 2, "text": ">> hello"},
                {"start": 2, "end": 4, "text": "answer"},
                {"start": 4, "end": 6, "text": ">> next question"}]
        paras = tu.merge_paragraphs(segs, target=999)
        self.assertEqual([p["text"] for p in paras], ["hello answer", "next question"])
        self.assertEqual(paras[0]["ts"], "00:00")
        self.assertTrue(paras[0]["speaker_change"])
        self.assertEqual(paras[1]["ts"], "00:04")

    def test_merges_into_target_paragraphs_at_sentence_end(self):
        segs = [{"start": 0, "end": 5, "text": "One."},
                {"start": 50, "end": 55, "text": "Two."}]
        paras = tu.merge_paragraphs(segs, target=40, hard_max=75)
        self.assertEqual([p["text"] for p in paras], ["One.", "Two."])

    def test_keeps_diarised_speaker(self):
        segs = [{"start": 0, "end": 2, "text": "hi", "speaker": "Host"},
                {"start": 2, "end": 4, "text": "yo", "speaker": "Guest"}]
        paras = tu.merge_paragraphs(segs, target=999)
        self.assertEqual([p.get("speaker") for p in paras], ["Host", "Guest"])


class WriteWorkdirTest(unittest.TestCase):
    def test_writes_artifacts_and_stats(self):
        segs = [{"start": 0, "end": 80, "text": "a"}, {"start": 80, "end": 160, "text": "b"}]
        with tempfile.TemporaryDirectory() as d:
            stats = tu.write_workdir(d, segs, video_id="abcdefghijk", part_minutes=1)
            for name in ("transcript_raw.json", "paragraphs.json", "transcript.md"):
                self.assertTrue(os.path.exists(os.path.join(d, name)), name)
            with open(os.path.join(d, "transcript.md"), encoding="utf-8") as f:
                md = f.read()
        self.assertIn("abcdefghijk", md)
        self.assertIn("Part 1", md)
        self.assertIn("'>>' = speaker change", md)
        self.assertGreater(stats["words"], 0)
        self.assertEqual(stats["duration"], 160)


class LocalFileCliTest(unittest.TestCase):
    def test_cli_creates_meta_with_local_source(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "talk.vtt")
            with open(src, "w", encoding="utf-8") as f:
                f.write(CueFormatTest.VTT)
            out = os.path.join(d, "work")
            import contextlib
            import io
            import sys
            argv = sys.argv
            sys.argv = ["transcript_utils.py", "--file", src, "--out", out,
                        "--video-id", "abcdefghijk", "--title", "T"]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    tu.main()
            finally:
                sys.argv = argv
            with open(os.path.join(out, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
        self.assertEqual(meta["subtitle_source"], "local:talk.vtt")
        self.assertEqual(meta["url"], "https://www.youtube.com/watch?v=abcdefghijk")

    def test_cli_rejects_file_without_timestamps(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "plain.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("no timestamps anywhere")
            import sys
            argv = sys.argv
            sys.argv = ["transcript_utils.py", "--file", src, "--out", os.path.join(d, "w")]
            try:
                with self.assertRaises(SystemExit):
                    tu.main()
            finally:
                sys.argv = argv


if __name__ == "__main__":
    unittest.main()
