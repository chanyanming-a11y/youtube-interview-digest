# 隐私与数据流向

本技能（agent skill）在本地运行，**不部署任何服务器，也不收集遥测 / 行为数据**。以下是数据从你机器流向外部的明确说明，方便你自行评估风险。

## 会对外发送什么

- **视频地址**：`fetch_youtube.py` 会把 YouTube 视频 URL 发给 YouTube 公开页面 / InnerTube 接口，用于获取字幕、章节、回看热度与评论。
- **描述里的外部转写链接**：当视频无字幕时，脚本会读取视频描述中出现的 Substack 文章链接（形如 `https://<host>/p/<slug>`），并向该公网域名请求转写。主机名经过 SSRF 校验，**只允许公网域名**，拒绝 IP 字面量、`localhost`、`.local`/`.internal` 与云元数据（`169.254.169.254`）。该域名由视频上传者填写，请只对信任的视频运行。
- **翻译 / 解构 / 归纳**：由你使用的 agent 自身的模型完成，请求发往该 agent 的后端，**不经过本仓库或任何中间服务器**。

## 留在本地什么

- 中间产物：`digest.json`、`meta.json`、字幕文件等，全部保存在你指定的工作目录。
- 成品：`report.html` 与 `report.md`，保存在本地。
- **cookies**：`fetch_youtube.py` 可通过 `--cookies <file>` 或 `--cookies-from-browser` 读取浏览器登录信息以突破 YouTube 限制；这些凭据**只在本地读取，从不写入磁盘文件或提交到仓库**（`.gitignore` 已排除 `cookies.txt`）。请勿把 cookies 文件提交或分享给他人。

## 不会做什么

- 不上传你的数据到本仓库作者的任何服务器。
- 不内嵌追踪脚本、不发起遥测请求。
- 不在报告里写入 cookies 或密钥。

## 共享报告时的注意

生成的报告嵌入了 YouTube 字幕与评论（第三方内容）。公开再分发大段字幕可能有 YouTube 服务条款 / 版权风险；公开分享请用 `render_report.py --no-transcript` 去掉全文译稿。本仓库 `examples/` 与 GitHub Pages 上的示例报告保留完整字幕，仅用于展示成品格式，不代表默认允许对外再分发该视频字幕。

## 相关

- 安全漏洞反馈与 SSRF / cookies 注意事项见 [SECURITY.md](SECURITY.md)。
- 合规与使用条款见 [README](README.md#合规与隐私)。
