# Changelog

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
