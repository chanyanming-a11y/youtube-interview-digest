# 示例：Netflix CPTO Elizabeth Stone @ Lenny's Podcast

- 原视频：https://www.youtube.com/watch?v=t0GiTyz4syY（72 分钟，2026-07-19 发布）
- 数据快照：2026-09-30，播放量和评论数以当天为准
- 抓取方式：`page-fallback`（yt-dlp 被 YouTube 拦截，改从公开网页获取数据）；字幕取自 Lenny Newsletter 的播客转写
- 价值解读：[`docs/case-study.md`](../../docs/case-study.md)

| 文件 | 说明 |
|---|---|
| `report.html` | 交互报告。**下载后用浏览器打开**，或通过 GitHub Pages 访问（见下文） |
| `report.md` | Markdown 版，时间点是标准 YouTube 链接，在 GitHub 上可以直接阅读 |
| `digest.json` | 结构化结果，agent 按 `references/digest-schema.md` 写出，渲染器读取它生成报告 |
| `analysis_notes.md` | agent 的中间笔记：数据质量核对、叙事结构、事实核查、冲突和热度解读 |
| `meta.json` | 视频元数据快照（标题、章节、统计数据） |

**版权说明**：公开示例用 `--no-transcript` 渲染，不包含全文译稿；也没有提交原始字幕和评论数据（`transcript*.json`、`comments.json`、`signals.md`）。报告里只保留摘要、短引用和译成中文的评论摘录，不含评论者用户名。

## 在线查看

GitHub 不会直接渲染 HTML 文件。可以任选一种方式：

1. **GitHub Pages**（推荐）：仓库 Settings → Pages → Source 选 `main` 分支的 `/ (root)`，之后访问
   `https://<your-name>.github.io/youtube-interview-digest/examples/netflix-elizabeth-stone/report.html`。
   通过 https 访问时，内嵌播放器通常可以正常播放和跳转。
2. 下载 `report.html`，在本地浏览器打开。如果播放器报错 153，改用 `python3 -m http.server` 本地起服务预览。
