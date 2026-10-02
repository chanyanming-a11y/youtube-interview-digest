---
name: youtube-interview-digest
description: 油管内容总结 / YouTube interview & podcast digest. This skill should be used when the user shares a YouTube link (or a YouTube transcript file) and asks to summarize, translate, 总结, 精读, 拆解, 提炼 a video, interview, podcast or talk. It fetches the timestamped transcript, heatmap ("most replayed") and top comments, translates to Chinese, deconstructs framework / quotes / viewpoint conflicts, enriches with traffic peaks and comment hotspots, then outputs an interactive HTML report (embedded player with a no-distraction shield; every summary item has a clickable timestamp that seeks the video; a full-article read-aloud that supports natural voices — Microsoft Edge 晓晓 Neural / 豆包 / browser native — and double-click-to-start-from-any-paragraph) plus Markdown. Not for: general web articles or blog posts, non-YouTube video platforms, or a one-off plain translation without digest/deconstruction.
---

# YouTube 访谈精读（youtube-interview-digest）

把一个 YouTube 视频（访谈、播客、演讲）处理成**带时间戳、可点击跳转**的中文精读报告。流水线如下：

```
YouTube 链接 ─▶ ① 抓取：字幕(含自动浏览器导出内置文字稿) + 回看热度 + 评论
             ─▶ ② 翻译：逐段中文译稿（时间戳不变）
             ─▶ ③ 解构：框架 / 观点 / 金句 / 观点冲突
             ─▶ ④ 补充：回看高峰 + 评论焦点 → 讨论热点、评论洞察
             ─▶ ⑤ 压缩：一句话结论、TL;DR、访谈价值 → digest.json
             ─▶ ⑥ 渲染：report.html（优先本地服务页内播放；file:// 显示精致封面，时间码均可跳转）+ report.md
```

## 环境

```bash
# PY：任意 Python ≥ 3.10。有隔离 venv 就用 venv；在 WorkBuddy 里用 managed runtime 下的 venv
PY=${PY:-python3}
S=<本 skill 目录>/scripts          # 例如 ~/.workbuddy/skills/youtube-interview-digest/scripts
$PY -c "import yt_dlp, youtube_transcript_api" 2>/dev/null || $PY -m pip install -q -r $S/../requirements.txt

# 可选：自动浏览器导出 YouTube 自带文字稿需要 Playwright（仅当 yt-dlp / 页面降级都拿不到字幕时）
# 用 channel="chrome" 复用本机已装 Chrome，不需要下载浏览器二进制
$PY -c "import playwright" 2>/dev/null || $PY -m pip install -q playwright

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
4. **自动浏览器导出 YouTube 自带文字稿（新增）**：以上都拿不到字幕时，自动用 Playwright 驱动你已安装的 Chrome（复用登录态 cookie，绕开 bot-check），打开视频页点开「… → 显示文字记录」，滚动加载全部段落并抽取 `[mm:ss]` + 文本，产物格式与别的来源完全一致。`subtitle_source` 会标成 `browser:show-transcript:<ID>`。这一步把原来「用户手动复制全文」的降级路径自动化了——绝大多数被拦截的访谈视频到这里就能拿到字幕。

**退出码**：0 成功 · 2 URL 或网络错误 · 3 BOT_CHECK 且页面降级也失败 · **4 除字幕外的数据都已保存**。注意：进入 4 之前，抓取链路第 4 步（自动浏览器导出）已经自动跑过一次；退出码 4 只在该步也失败时出现。此时按顺序处理：
1. 先确认是否装了 Playwright（`pip install playwright`，用 `channel="chrome"` 复用本机 Chrome，无需下载浏览器）；若已装但仍失败，多半是 cookie 没注入成功——用 `--cookies cookies.txt` 显式指定（Chrome 导出或 `yt-dlp --cookies-from-browser chrome -o cookies.txt <URL>` 生成）。
2. 仍不行：请用户在 YouTube 页面「…更多 → 显示文字记录」里复制全文（或提供 .srt/.vtt 文件），然后执行：
   `$PY $S/transcript_utils.py --file <文件> --out $W --video-id <ID>`（已有的 meta、热度、评论会保留）。也可跳过浏览器自动步，直接在 fetch 时加 `--no-browser`。

**云 IP 被封（agent 沙箱）专用：本机一键抓取**。如果第 4 步自动浏览器导出仍失败，且你确认本机 Mac 是正常 IP + 已登录 Chrome（云沙箱出口 IP 会被 YouTube 整体封锁，属于环境限制而非 skill 问题），可以直接在本机跑 skill 根目录的 `local_fetch.sh` 一次性抓取全部数据：
   `./local_fetch.sh "<YouTube URL>"`    # 默认输出 ~/yt_<videoId>，自动用本机 Chrome cookie，一次拿到 meta / heatmap / comments / transcript
跑完把输出目录路径发回 agent，即可继续 ②翻译 → ③解构 → ④补充 → ⑤压缩 → ⑥渲染——**翻译及之后的步骤都不需要联网**，你本机只跑这一条命令即可。详见 README「本地抓取（避开云 IP 封锁）」一节。

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
- 内嵌播放器与降级封面：YouTube 在 `file://` 下拒绝内嵌（错误 153）。页面会**立即**显示一张精致封面（缩略图打底 + 渐变 + 居中播放按钮 + 底部操作条），而不是过去那块挡满播放器的深色报错遮罩。点封面/播放按钮会在 YouTube 打开并跳到当前进度；点时间码同样跳转。封面底部还有「复制预览命令」按钮——命令由 `render_report.py` 注入到 `meta.serve_cmd`，复制到终端运行即可切到可页内播放的模式。
- **页内播放是默认交付（已自动化）**：`render_report.py` 渲染后会**自动拉起本地服务**（除非加 `--no-serve`），并在输出 JSON 里给出 `preview_url`（形如 `http://127.0.0.1:PORT/report.html`）。该 URL 在浏览器里有合法 origin，视频页内直接播放、点时间码是 seek 而非开新标签。即便用户直接用 `file://` 打开 `report.html`，封面也会显示这条已启动的本地预览链接，点一下即可在本页播放。**注意缓存**：报告正文是客户端由内嵌 JSON **运行时渲染**的，改了模板 JS 后，旧的报表页仍会跑旧代码——`serve_report.py` 已对所有响应加 `Cache-Control: no-store, no-cache, must-revalidate`；交付时若用户反馈"改了没生效 / 还是旧行为"，多半是缓存，改用带 query 的 URL（如 `?v=r3`）或让用户硬刷新（Cmd+Shift+R）即可。
- **交付顺序**：用 `present_files` 时**优先放渲染输出的 `preview_url`**（localhost HTTP 预览，可在内置浏览器面板里直接播），再放 `report.md`；`report.html` 本身退而求其次（file:// 下只能看封面）。**离线单文件分享**：`report.html` 本身是自包含的（CSS/JS/数据全部内联，仅视频/封面缩略图走 YouTube CDN，需联网）——直接双击或发给别人即可，无需本地服务。打开方式决定朗读音源：①从 `localhost`/`127.0.0.1` 打开（即本机 `serve_report.py` 服务）→ 自动探测并首选微软晓晓 Neural（需本机 `pip install edge-tts` 且联网）；②以 `file://` 或直接发到别处打开 → 自动判定无 `/tts` 代理，仅保留**浏览器原生朗读**、隐藏云端选项，无需任何服务器。YouTube 内嵌只在有合法 origin（localhost/在线）时页内播放，file:// 下显示封面、点封面/时间码跳到 YouTube 观看。
- **无干扰画面（常驻护盾，已内置）**：YouTube 自带内嵌会在**暂停 / 结束 / 未开始**时弹出它自己的标题栏、频道行、"更多视频"推荐架、结束页推荐与分享按钮——这些来自**跨域 iframe，CSS 无法移除**。关键约束：即便播放中，只要 YouTube 收到 hover 就会弹出它的 chrome。因此模板在 `.player .clean` 上放一层**常驻透明护盾**（`visibility:visible; pointer-events:auto`），开启时**始终**盖在 iframe 上方、吞掉所有指针事件，使 YouTube 永远收不到 hover、自然也就不弹任何 chrome——**播放中也是干净的透明护盾**（不遮挡画面，但挡住交互）。护盾在**初始 / 暂停 / 结束**时变为不透明封面（`maxresdefault.jpg` 打底 + 渐变 + 居中播放键 + 文案：播放 / 已暂停·点击继续 / 播放结束·点击重播）；状态由 IFrame API 的 `onStateChange` 驱动（PLAYING→透明护盾，PAUSED/ENDED→封面）。护盾下方另有**自建极简控制条** `.cbar`（进度条可点击 seek、时间 `MM:SS / MM:SS`、全屏按钮），hover 显形。右上角悬停出现「无干扰 ✓ / 原画面」小开关（记 `localStorage['yt-clean']`，默认开），可一键切回 YouTube 原始画面。若用户反馈"播放时画面乱 / 有推荐和标题"，说明护盾未开或被关，重新打开「无干扰」即可，无需改代码。
- **朗读全文（覆盖全文各栏目）**：标题下方「朗读全文」按钮（语音图标）逐块朗读结论/框架/观点/金句/冲突/热点/评论/资源/术语/全文译稿，当前块高亮并自动滚动；语言（中文 / 中英双语 / English）与语速（0.85×–1.5×）可选。**音源三种（按可用度自动优选）**：①**微软语音 / Edge TTS（默认首选，免费、无需密钥）**——最自然的中文 Neural 音色（晓晓 `zh-CN-XiaoxiaoNeural`）；在跑 `serve_report.py` 的机器上 `pip install edge-tts` 即可启用，页面会自动出现「微软语音」并默认选中；②**豆包（字节火山引擎语音合成）**——把 `scripts/tts_config.example.json` 复制为 `tts_config.json`（或设 `YTD_TTS_CONFIG` / `render_report.py --tts-config`）填入 `appid/token/cluster/voice_zh/voice_en`，密钥**只经本地 `/tts` 代理**、不进浏览器/仓库；③**浏览器原生 TTS**（兜底，离线但中文音色偏机械）。无云端音源时页面自动隐藏对应选项、降级为浏览器原生。**双击正文任意段落可从该处起读**（工具条有「双击正文可从该处起读」提示）。**时间戳读法修正**：朗读前把中文文本里的 `MM:SS`（及 `H:MM:SS`，半/全角冒号均可）转成口语「X分Y秒」（如 `07:20`→「零七分二十秒」），避免被读成"零七点二十"。
- 手动起服务（备用 / 想换端口或自动开浏览器）：
  `$PY $S/serve_report.py --work $W --open`（打印 URL 后阻塞服务，需后台运行）

## 最终回复

回复要结论先行，包括：一句话结论、价值评分和适合人群、3 条最值得看的片段（带时间戳）、数据降级说明（是否有热度和评论数据、字幕是否为自动字幕）。不要把整份报告复述一遍。

交付时，用 `present_files` 优先附上 `render_report.py` 输出的 `preview_url`（localhost 链接，已自动起服务、可页内播放）；同时给出 `report.md` 与 `report.html`。说明：直接双击 `report.html`（file://）会显示封面，点封面上的本地预览链接即可在本页播放，无需手动起服务。

## 资源

| 文件 | 用途 |
|---|---|
| `scripts/fetch_youtube.py` | 抓取入口：先用 yt-dlp，遇到 BOT_CHECK 自动走页面降级，再按描述链接找外部转写；退出码见上文 |
| `scripts/page_fallback.py` | 免登录降级：解析 ytInitialData（元数据、章节、热度），通过 InnerTube 拉评论和回复，读取 Substack 转写 |
| `scripts/transcript_utils.py` | 解析 json3/vtt/srt/带时间戳的 txt，去除滚动重复，合并段落，切分 Part；也可作为 CLI 导入本地字幕 |
| `scripts/fetch_transcript_browser.py` | 自动浏览器导出：Playwright 驱动本机 Chrome（注入登录 cookie），点开「显示文字记录」，抽取 YouTube 自带时间戳文字稿；CLI 也可单独使用 |
| `scripts/analyze_signals.py` | 检测回看高峰、聚类评论时间戳、提取高赞线程和关键词，生成 signals.md |
| `scripts/render_report.py` | 校验 digest 并渲染 HTML 和 Markdown；`--no-transcript` 可去掉全文译稿（公开分享时用）；注入 `meta.serve_cmd` 供封面按钮复制 |
| `scripts/serve_report.py` | 在 `127.0.0.1` 起本地服务并打印 URL（绕开 `file://` 错误 153，让 YouTube 页内播放）；同时作为朗读 TTS 的**本地代理**（微软 Edge / 豆包），密钥只留本机、不进浏览器/仓库；对所有响应加 `Cache-Control: no-store`，避免改模板后缓存旧页面 |
| `scripts/tts_config.example.json` | 豆包（火山引擎）TTS 配置样例：`appid/token/cluster/voice_zh/voice_en/endpoint/auth_header_template`；复制为 `tts_config.json` 填入真实密钥（**切勿提交含密钥文件**到仓库） |
| `requirements.txt` | Python 依赖（yt-dlp、youtube-transcript-api；自动浏览器导出另需 playwright，见「环境」段） |
| `assets/report_template.html` | 报告模板：左侧吸顶播放器（**常驻无干扰护盾**——始终盖在 iframe 上吞掉指针事件，播放中也干净、不弹 YouTube 自带标题栏/推荐；暂停/结束时显形为封面），热度曲线和目录，右侧十个部分；标题下方有「朗读全文」按钮（语音图标 + 语言/语速选择，覆盖全文各栏目，逐块高亮并自动滚动），音源按可用度自动优选**微软 Edge 晓晓 Neural（免费最自然）→ 豆包 → 浏览器原生**，时间戳按「分/秒」读（如 `07:20`→「零七分二十秒」）；**双击正文任意段落即从该处起读** |
| `references/translation-guide.md` | 译稿格式、说话人识别、术语、长视频策略 |
| `references/analysis-framework.md` | 解构、热度补充、压缩的方法论和自检清单 |
| `references/digest-schema.md` | digest.json 字段说明和示例 |
