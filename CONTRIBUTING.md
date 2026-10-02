# 贡献指南 · Contributing

感谢你考虑为 `youtube-interview-digest` 做出贡献。这个 skill 的目标是把 YouTube 长访谈变成可信、可溯源的中文精读报告——任何改动都应守住两条底线：**结论可溯源**（金句逐字比对原文）、**默认安全**（不泄露凭据、不主动访问内网）。

## 提 issue / 反馈安全漏洞

- **功能 / Bug**：开一个普通 issue，尽量附上视频链接、复现步骤和 `report.html` 里出问题的板块。
- **安全问题（私有反馈，不要开公开 issue）**：见 [SECURITY.md](SECURITY.md)。可通过 GitHub 的 **Security → Report a vulnerability**，或邮件 `chanyanming-a11y@users.noreply.github.com`。

## 本地开发

```bash
git clone https://github.com/chanyanming-a11y/youtube-interview-digest.git
cd youtube-interview-digest

# 可选：建一个隔离环境
python3 -m venv .venv && source .venv/bin/activate

# 跑通抓取所需的第三方依赖（yt-dlp / youtube-transcript-api）
pip install -r skills/youtube-interview-digest/requirements.txt
```

脚本只负责确定性工作（抓取、解析、信号计算、渲染、校验）；需要判断的部分（翻译、解构、归纳）由 agent 完成。改脚本时请保持这种分工。

## 运行测试、lint 与覆盖率

测试只依赖 Python 标准库，不需要联网或装第三方包：

```bash
python3 -m unittest discover -s tests -v
```

提交前请再跑一遍 lint 与覆盖率门禁（配置都在 `pyproject.toml`）：

```bash
pip install ruff==0.16.10 coverage
ruff check .                                    # 规则集 E,F,W,I,B,UP
coverage run -m unittest discover -s tests -q   # 计量范围见 [tool.coverage.run]
coverage report                                 # 阈值见 [tool.coverage.report] fail_under
```

CI（`.github/workflows/ci.yml`）在 push / PR 到 `main` 时会跑三件事：`ruff check`、Python 3.10–3.12 的 `py_compile` + 测试、以及覆盖率门禁。三者任一失败，徽章就会变红。

覆盖率只在**离线可测**的脚本上计量——`fetch_youtube.py`（yt-dlp）、`fetch_transcript_browser.py`（登录态浏览器）、`analyze_signals.py`（远程模型）需要联网与凭据，已在 `[tool.coverage.run] omit` 中排除，改由人工冒烟验证。

## 从哪开始：good first issue

不确定能改什么时，可以从这些入门任务里挑一个（对应 issue 会带 `good first issue` 标签）：

- **补测试**：给 `page_fallback.py` 的抓取 / 重定向分支加离线用例（用 `http.server` 起一个本地假站即可，参考 `tests/test_security.py` 里的 `ServeReportServerTest`）。
- **补文档**：把 README 的常见卡点补成「现象 → 原因 → 一句可照抄的命令」三段式。
- **报错更友好**：挑一处 `sys.exit(...)` 或异常分支，把消息改写成「哪里出错了 + 下一步该做什么」。
- **改一版措辞**：报告模板里的板块说明文字（`assets/report_template.html`）读起来是否还顺，改文案不影响逻辑，风险最低。

挑选前请先开 issue 说一句你打算怎么做，避免撞车。较大的方向见 [ROADMAP.md](ROADMAP.md)。

## 改动约定

- **安全相关**：任何会发起网络请求的代码都要经过 `page_fallback._host_safe` / `_url_safe` 的校验（只放行公网域名，拒绝 IP 字面量、`localhost`、`.local`/`.internal`、云元数据 `169.254.169.254`）。新增转写来源时照此办理。
- **渲染**：报告 HTML 里所有外部/用户可控文本都要转义（标题走 `render_report._escape_title`）。不要去掉已有的 `</` → `<\/` 防护。
- **金句校验**：`render_report.py --strict` 要求英文原句能在字幕里找到，改动不要削弱这条校验。
- **cookies 敏感**：`fetch_youtube.py` 可通过 `--cookies` / `--cookies-from-browser` 读登录信息，**绝不**写入磁盘或提交仓库。`.gitignore` 已排除 `cookies.txt`。

## 提交与 PR

- 分支从 `main` 切出，PR 合回 `main`。
- 提交信息用中文或英文短句，说明「为什么」而非「改了什么」。
- 版本号在 `.claude-plugin/marketplace.json` 的 `metadata.version` 与 [CHANGELOG.md](CHANGELOG.md) 同步更新（遵循语义化版本：功能变更升 MINOR，向后兼容修复升 PATCH）。
- 新增示例报告请放进 `examples/`，并确保不泄露任何私人信息。

## 行为准则

参与本项目即表示你同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)（改编自 Contributor Covenant 2.1）。

## 许可

本仓库以 [MIT](LICENSE) 许可发布。提交即表示你同意你的贡献在同等许可下被采用。
