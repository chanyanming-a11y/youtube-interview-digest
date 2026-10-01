---
name: youtube-interview-digest
description: 油管内容总结 / YouTube interview & podcast digest. This skill should be used when the user shares a YouTube link (or a YouTube transcript file) and asks to summarize, translate, 总结, 精读, 拆解, 提炼 a video, interview, podcast or talk. It fetches the timestamped transcript, heatmap ("most replayed") and top comments, translates to Chinese, deconstructs framework / quotes / viewpoint conflicts, enriches with traffic peaks and comment hotspots, then outputs an interactive HTML report (embedded player, every summary item has a clickable timestamp that seeks the video) plus Markdown.
---

# YouTube 访谈精读（youtube-interview-digest）

把一个 YouTube 视频（访谈、播客、演讲）处理成**带时间戳、可点击跳转**的中文精读报告。流水线如下：

```
YouTube 链接 ─▶ ① 抓取：字幕 + 回看热度 + 评论
             ─▶ ② 翻译：逐段中文译稿（时间戳不变）
             ─▶ ③ 解构：框架 / 观点 / 金句 / 观点冲突
             ─▶ ④ 补充：回看高峰 + 评论焦点 → 讨论热点、评论洞察
             ─▶ ⑤ 压缩：一句话结论、TL;DR、访谈价值 → digest.json
             ─▶ ⑥ 渲染：report.html（内嵌播放器，点时间点跳转）+ report.md
```

## 环境

```bash
# PY：任意 Python ≥ 3.10。有隔离 venv 就用 venv；在 WorkBuddy 里用 managed runtime 下的 venv
PY=${PY:-python3}
S=<本 skill 目录>/scripts          # 例如 ~/.workbuddy/skills/youtube-interview-digest/scripts
$PY -c "import yt_dlp, youtube_transcript_api" 2>/dev/null || $PY -m pip install -q -r $S/../requirements.txt
```

Python 版本低于 3.10 时（比如 macOS 自带的 3.9），先装一个新版本或换用 managed runtime，再执行后续步骤。

工作目录约定：`W=<workspace>/yt_<videoId>/`，所有中间产物和最终报告都放在这里。

## ① 抓取

```bash
$PY $S/fetch_youtube.py "<URL>" --out $W --max-comments 300
```

产物：`meta.json`（标题、频道、时长、章节、统计、描述区链接）、`heatmap.json`、`comments.json`、`transcript.md`（按约 10 分钟切成 Part，每段 `[mm:ss]` 开头；带 `Name:` 说明是有说话人分离的转写，只有 `>>` 则表示换人说话）、`paragraphs.json`。

**抓取链路（自动完成，无需干预）**：
1. 先用 yt-dlp 抓全部数据。
2. 如果触发 BOT_CHECK（本机代理出口 IP 被风控，多数访谈视频都会触发），**自动切换到页面降级模式**，`fetch_mode=page-fallback`。这时仍能从公开网页拿到元数据、章节、热度和评论（通过 InnerTube `/next` 分页），不需要登录。
3. 拿不到字幕时，去视频描述里的链接找外部转写。目前支持 **Substack 播客文章**（`/p/<slug>` → `/api/v1/posts/<slug>` → transcription.json），Lenny's Podcast 等大量播客都用这种方式，转写自带说话人和词级时间戳。
   - 核对 `meta.external_transcript.duration_diff_s`：绝对值 ≤ 5 秒才能直接用；超过时会给出 warning，可能是剪辑版本不同或插了广告。这时用章节标题抽查几处，确认对齐或算出偏移后再用。

**退出码**：0 成功 · 2 URL 或网络错误 · 3 BOT_CHECK 且页面降级也失败 · **4 除字幕外的数据都已保存**。遇到 4 时按顺序处理：
1. **先征得用户同意**，再加 `--cookies-from-browser chrome` 重跑（也可用 safari / edge / firefox）。macOS 会弹出钥匙串授权，需要用户点「允许」。也可以让用户导出 cookies.txt，然后加 `--cookies <path>`。
2. 用户不同意或仍然失败：请用户在 YouTube 页面「…更多 → 显示文字记录」里复制全文（或提供 .srt/.vtt 文件），然后执行：
   `$PY $S/transcript_utils.py --file <文件> --out $W --video-id <ID>`（已有的 meta、热度、评论会保留）

检查抓取结果：`subtitle_source` 带 `auto` 表示自动字幕，专有名词错误较多，翻译时要纠错；带 `substack:` 表示外部播客转写，需在报告的 `value.caveats` 里注明来源；`heatmap_points=0` 表示该视频没有热度数据。

## 分析信号

```bash
$PY $S/analyze_signals.py --work $W
```

读取 `$W/signals.md`，内容包括：回看高峰（已去掉开场高峰，附对应原文片段）、评论时间戳锚点（按点赞加权，⚡ 表示与回看高峰重合）、高赞评论线程和评论关键词。

## ② 翻译

按 `references/translation-guide.md` 执行：逐个 Part 读取 `transcript.md`，翻译后**追加写入** `$W/transcript_zh.md`，格式为 `[mm:ss] 说话人：译文`，时间戳不能改动。可能成为金句的句子，在行末加 ⭐。长视频（> 60 分钟）按指南里的压缩策略处理。

## ③④ 解构 + 热度补充

按 `references/analysis-framework.md` 执行，边读边在 `$W/analysis_notes.md` 里记笔记：
- ③ 基于译稿提取框架节点、观点（必须是可以被反驳的主张）、金句（`en` 从原文复制）、观点冲突（五类逐一排查，至少 1 条）。
- ④ 结合 `signals.md`：⚡ 项必须进热点；给每个回看高峰判断成因；把评论区的反驳回填到冲突里；把原片没讲透的内容写进 `supplement`；高赞评论归纳为 4–8 个主题。

## ⑤ 压缩 → digest.json

按 `references/digest-schema.md` 写 `$W/digest.json`。硬性要求：
- **每个总结项都要带时间戳**，时间点取自译稿中真实存在的段落，指向话题开始讨论的位置，禁止估算。
- 结论先行：`one_liner` 写成判断句；`tldr` 3–6 条；`value` 要包含评分、适合人群、可直接用的收获和局限。
- 同一内容只在一个板块展开，其他板块用文本内的 `[mm:ss]` 引用。

## ⑥ 渲染与校验

```bash
$PY $S/render_report.py --work $W --strict
```

- 输出 `report.html` 和 `report.md`。`errors` 不为空时（缺时间戳、时间超出视频时长、金句在原文中找不到），修正 digest.json 后重新运行，直到 errors 为空。金句时间戳偏差超过 90 秒会自动修正并给出 warning。
- 内嵌播放器：YouTube 在 `file://` 页面下可能拒绝内嵌（错误 153）。页面会自动降级：点击时间点时在新标签页打开 `youtube.com/watch?v=ID&t=Ns`。想在页面内直接跳转，就启动本地服务后预览：
  `$PY -m http.server 8765 --bind 127.0.0.1 -d $W`（后台运行），然后打开 `http://127.0.0.1:8765/report.html`。
- 用 present_files 交付：先放 HTTP 预览链接（或 report.html），再放 report.md。

## 最终回复

回复要结论先行，包括：一句话结论、价值评分和适合人群、3 条最值得看的片段（带时间戳）、数据降级说明（是否有热度和评论数据、字幕是否为自动字幕）。不要把整份报告复述一遍。

## 资源

| 文件 | 用途 |
|---|---|
| `scripts/fetch_youtube.py` | 抓取入口：先用 yt-dlp，遇到 BOT_CHECK 自动走页面降级，再按描述链接找外部转写；退出码见上文 |
| `scripts/page_fallback.py` | 免登录降级：解析 ytInitialData（元数据、章节、热度），通过 InnerTube 拉评论和回复，读取 Substack 转写 |
| `scripts/transcript_utils.py` | 解析 json3/vtt/srt/带时间戳的 txt，去除滚动重复，合并段落，切分 Part；也可作为 CLI 导入本地字幕 |
| `scripts/analyze_signals.py` | 检测回看高峰、聚类评论时间戳、提取高赞线程和关键词，生成 signals.md |
| `scripts/render_report.py` | 校验 digest 并渲染 HTML 和 Markdown；`--no-transcript` 可去掉全文译稿（公开分享时用） |
| `requirements.txt` | Python 依赖（yt-dlp、youtube-transcript-api） |
| `assets/report_template.html` | 报告模板：左侧吸顶播放器、热度曲线和目录，右侧十个部分 |
| `references/translation-guide.md` | 译稿格式、说话人识别、术语、长视频策略 |
| `references/analysis-framework.md` | 解构、热度补充、压缩的方法论和自检清单 |
| `references/digest-schema.md` | digest.json 字段说明和示例 |
