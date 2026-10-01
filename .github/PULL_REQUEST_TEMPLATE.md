## 这个 PR 做了什么
<!-- 一句话说明动机，以及改了哪部分（脚本 / 文档 / 示例 / CI） -->

## 改动类型
- [ ] 功能（MINOR）
- [ ] 向后兼容修复 / 安全（PATCH）
- [ ] 文档 / 测试 / CI（无需升版本）

## 检查清单
- [ ] 本地跑过 `python3 -m unittest discover -s tests -v`
- [ ] 安全相关改动仍经过 `_host_safe` / `_url_safe` 校验（不访问内网 / 云元数据）
- [ ] 报告 HTML 里外部文本都做了转义
- [ ] 没有提交 cookies 或其他敏感信息
- [ ] 如涉及版本变化，`CHANGELOG.md` 与 `marketplace.json` 的版本号已同步

## 关联 issue
<!-- 例如 fixes #12 -->
