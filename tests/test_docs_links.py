"""离线校验仓库内 Markdown 的相对链接与页内锚点。

改 README / 改文档标题最容易留下死链——这个测试保证「链接指向的文件存在」
以及「锚点能对上某个标题」。纯标准库、不联网，可直接进 CI。
"""

import os
import re
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SKIP_DIRS = {".git", "__pycache__", ".ruff_cache", ".venv", "node_modules"}
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_IMG_SRC = re.compile(r'<img[^>]+src="([^"]+)"')
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.M)
_HTML_TAG = re.compile(r"<[!/a-zA-Z].*?>")
# GitHub slugger 去掉的标点（含通用标点区 U+2000-206F / U+2E00-2E7F）
_PUNCT = re.compile(r"[\u2000-\u206F\u2E00-\u2E7F\\'!\"#$%&()*+,./:;<=>?@\[\]^`{|}~]")


def github_slug(text: str) -> str:
    """按 GitHub 的规则把标题转成锚点。"""
    text = _MD_LINK.sub(r"\1", text)
    text = _HTML_TAG.sub("", text)
    text = _PUNCT.sub("", text.strip().lower())
    return re.sub(r"\s", "-", text)


def markdown_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in sorted(filenames):
            if name.endswith(".md"):
                yield os.path.join(dirpath, name)


def slugs_in(path) -> set:
    body = Path(path).read_text(encoding="utf-8")
    counts, slugs = {}, set()
    for _, raw in _HEADING.findall(body):
        base = github_slug(raw)
        seen = counts.get(base, 0)
        counts[base] = seen + 1
        slugs.add(base if seen == 0 else f"{base}-{seen}")
    return slugs


class MarkdownLinksTest(unittest.TestCase):
    def _iter_links(self):
        for path in markdown_files():
            body = Path(path).read_text(encoding="utf-8")
            for match in list(_MD_LINK.finditer(body)) + list(_IMG_SRC.finditer(body)):
                target = match.group(2 if match.re is _MD_LINK else 1).split()[0].strip("<>")
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if target.startswith("#"):
                    # 同文件锚点：目标就是本文件自己
                    yield path, path, target[1:]
                    continue
                file_part, _, frag = target.partition("#")
                yield path, os.path.normpath(os.path.join(os.path.dirname(path), file_part)), frag

    def test_relative_links_resolve(self):
        missing = [f"{p} -> {t}" for p, t, _ in self._iter_links() if t and not os.path.exists(t)]
        self.assertEqual([], missing, "存在指向不存在文件的相对链接")

    def test_anchor_links_resolve(self):
        broken = []
        for path, target, frag in self._iter_links():
            if not frag or not target.endswith(".md") or not os.path.exists(target):
                continue
            if frag not in slugs_in(target):
                broken.append(f"{path} -> {os.path.relpath(target, ROOT)}#{frag}")
        self.assertEqual([], broken, "存在对不上任何标题的锚点")


if __name__ == "__main__":
    unittest.main()
