# Changelog

## v1.2.2 — 2026-10-02

文档完善（无代码 / 功能变动），把 v1.2.1 的新能力写进 README。

- README（中 / 英）新增「报告页的交互」/「The report page」小节：无干扰常驻护盾、全文朗读三音源（微软 Edge 晓晓 Neural / 豆包 / 浏览器原生）+ 双击正文起读 + 时间戳「分 / 秒」读法、页内播放自动化、离线单文件分享
- 抓取链路表新增「自动浏览器导出『显示文字记录』」层（共 6 层），并补充「出口 IP 是云 IP（agent / 沙箱）时：本机一键抓取」小节（`local_fetch.sh`）
- 目录结构补全 `fetch_transcript_browser.py` / `serve_report.py` / `tts_config.example.json` / `local_fetch.sh`
- 使用段说明渲染会自动拉起本地预览服务、直接双击 `report.html` 的降级行为

## v1.2.1 — 2026-10-02

服务端 TTS 音源、自动浏览器导出字幕、本机一键抓取（无功能/数据回归，skill 子目录整体更新）。

- 云端 TTS 音源与本地代理：新增 `scripts/serve_report.py`，支持微软 Edge 晓晓 Neural（免费最自然）与豆包（火山引擎）服务端合成；密钥仅经本地 `/tts` 代理、不进报告 HTML / 仓库；朗读音源按可用度自动优选「Edge 晓晓 → 豆包 → 浏览器原生」
- 自动浏览器导出字幕：新增 `scripts/fetch_transcript_browser.py`，Playwright 驱动本机已登录 Chrome 点开「显示文字记录」抽取自带时间戳文字稿，补全多层字幕兜底链路（yt-dlp → 页面降级 → 外部转写 → 浏览器导出 → 粘贴）
- 本机一键抓取：新增 `local_fetch.sh`，在本地正常 IP + 已登录 Chrome 一次性抓取全部数据，专用于绕过云沙箱出口 IP 被 YouTube 风控（仅「抓取」需联网，翻译/解构/渲染在 agent 内）
- 配置样例：新增 `scripts/tts_config.example.json`（豆包 appid/token 占位，切勿提交真实密钥）
- 安全：根 `.gitignore` 增加 `tts_config.json`，避免真实 TTS 密钥误提交

## v1.2.0 — 2026-10-01

报告页新增浏览器原生语音朗读（零依赖、离线可用）。

- 全文译稿逐段朗读：工具栏新增 `朗读 / 停止` 按钮、语言下拉（中文 / English / 中英双语）、语速下拉（0.85×–1.5×）
- 朗读时当前段高亮（左侧红条）并自动滚动到视野；中文走 `zh-CN` 语音、英文走 `en-US` 语音，双语模式先读中文再读英文原文
- 健壮性：`epoch` 令牌防止切语言 / 停止时的竞态重读；每 5s 一次 `resume()` 心跳规避 Chrome 长句截断；浏览器不支持 Web Speech API 时自动移除按钮并提示
- 测试：新增 `tests/test_tts.py`（7 项静态断言，校验控件 / API / 语言语速选项 / 高亮样式）

## v1.1.4 — 2026-10-01

隐私透明化与上手优化（无功能 / 数据变动）。

- 隐私：新增 `PRIVACY.md`，明确数据流向（视频 URL 发往 YouTube/InnerTube、描述里的 Substack 链接经 SSRF 校验、翻译走 agent 自身模型、cookies 仅本地读取、无服务器 / 遥测）
- 上手：README 增加「让 agent 帮你装」复制即用提示（无需命令行），中英文同步
- 演示：README 效果区增加在线交互版说明，并预留演示 GIF 占位（`docs/images/demo.gif` 录制后取消注释即生效）

## v1.1.3 — 2026-10-01

进阶成熟度（无功能 / 数据变动）。

- Release 自动化：新增 `.github/workflows/release.yml`，推送 `v*` 标签即由 CI 从 CHANGELOG.md 抽取对应段落自动发 GitHub Release 并标记为 Latest（不再需要手动 UI；git push 无法建 Release 的痛点已解决）
- 测试：新增 `tests/test_example_report.py`，冒烟校验 `docs/example-report.html` 与 `examples/netflix-elizabeth-stone/` 的 report.html/report.md/digest.json 为有效渲染产物
- 依赖与安全：新增 `.github/dependabot.yml`（pip + github-actions 月度更新，保持 yt-dlp / youtube-transcript-api 与 Action 不过期）
- 协作模板：新增 PR 模板与 Issue 模板（bug / feature YAML 表单）

## v1.1.2 — 2026-10-01

成熟度与测试（无功能 / 数据变动）。

- 测试：新增 `tests/test_security.py`（标准库，无需联网），覆盖 Substack 抓取的 SSRF 防护与报告标题转义
- CI：新增 `.github/workflows/ci.yml`，push/PR 到 main 时用 Python 3.10–3.12 跑 `py_compile` + 测试
- 安全修复：SSRF 防护 `_host_safe` 修正对 IPv6 字面量（`::1` / `fe80::1`）和 `host:port` 形式的误放行
- 贡献：`CONTRIBUTING.md`；README 增加 CI 状态徽章；报告标题转义抽出 `_escape_title` 便于测试
- 文档：README 现有 7 张截图（`docs/images/*.jpg`）已覆盖效果预览

## v1.1.1 — 2026-10-01

隐私、安全与发布完善（无功能 / 数据变动）。

- 隐私：全部提交作者署名改为 `chanyanming-a11y`（去除真实姓名）；`marketplace.json` owner 元数据同步
- 发布：新增 GitHub Pages 在线示例（`docs/index.html` + `docs/example-report.html`）、Claude Code 插件市场清单（`.claude-plugin/marketplace.json`）、SKILL.md description 补充 negative triggers
- 安全：限制 Substack 外部转写抓取仅允许公网域名（阻断内网 / 元数据 SSRF）；报告 HTML 标题改用 `html.escape` 转义
- 依赖与文档：锁定核心依赖版本、新增 `SECURITY.md`、README 补充版权与公开分享提示

## v1.0.0 — 2026-09-30

首个公开版本。

- 六步流水线：抓取 → 翻译 → 解构 → 热度补充 → 压缩 → 渲染，最后做校验
- 报告包含 10 个部分，内嵌播放器，所有时间点都能点击跳转，并附 Markdown 版
- 抓取遇到 YouTube 拦截时自动降级：先从公开网页拿数据、用 InnerTube 拉评论，再找 Substack 外部转写；退出码 `4` 表示只缺字幕
- 信号分析：检测回看高峰（过滤开场高峰、收紧扩展范围），评论时间戳按间隔聚类，同一条评论只计一次，观众自制的时间戳目录降权
- 校验：检查每个总结项的时间戳；金句逐字比对原文，同一句话出现多次时取离标注最近的一处
- 新增 `render_report.py --no-transcript`，公开分享报告时可以去掉全文译稿
- 支持的字幕格式：json3、vtt、srt、带时间戳的 txt、带说话人分离的 JSON
- 示例：Netflix CPTO Elizabeth Stone @ Lenny's Podcast（113 个时间点，校验 0 error）

## v1.1.0 — 2026-09-30

报告页改版，去掉模板感。功能、数据和布局不变。

- 视觉：主栏从一叠圆角卡片改成连续的文档，章节之间用细线分隔；只保留一种强调色（时间码），去掉渐变、环形进度、彩色胶囊标签和大引号装饰；标题和金句改用衬线字体
- 文案：去掉页面里的 emoji 和星级评分；板块说明从固定套话改成根据数据生成（例如「共 6 组，其中 2 组是嘉宾自己说法之间的张力」）；同一位嘉宾的名字只写一次；字幕来源显示为可读的名称
- 示例报告的正文按新的文风重写，并修正一处数字错误：快问快答的回看峰值比第二高的片段高出约 70%，不是「一倍多」
- `references/analysis-framework.md` 新增 5.4「文风」一节，约束以后生成的报告
- 修复：讨论热点的说明文字读错了 `signals.json` 的字段名，导致不显示评论时间戳数量
- 页面里嵌入的数据只保留画图需要的字段（时间和提及次数），不再带评论原文
