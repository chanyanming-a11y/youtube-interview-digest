# digest.json 字段规范

`render_report.py` 读取的结构化结果。所有字段都可省略，省略后对应板块不渲染；但 `*` 标记的字段属于交付要求，必须写。

时间字段（`t` / `start` / `end`）可以写 `"12:34"`、`"1:02:03"` 或秒数 `754`。
任何文本字段里的 `[12:34]` 都会被渲染成可点击时间点。`**加粗**` 虽然能渲染，但不要用（见 `analysis-framework.md` 5.4 文风）。

```jsonc
{
  "title_zh": "为什么大多数路线图都是虚构的",            // 中文标题（意译，不必直译）
  "one_liner": "* 一句话结论，≤40 字，判断句",
  "keywords": ["路线图", "北极星指标", "AI 炒作"],        // 3–6 个标签
  "host": "Lenny Rachitsky",
  "guests": [{"name": "Maya Chen", "role": "前某音乐流媒体产品负责人"}],

  "value": {                                           // * 访谈价值
    "score": 4.5,                                      // 1–5
    "for_whom": ["订阅制产品负责人", "刚转岗的 PM"],
    "why": "加分项…；扣分项…，可以用 [03:12] 引用",
    "takeaways": [{"text": "按问题而不是功能做季度规划", "t": "00:45"}],
    "caveats": "嘉宾只有订阅业务经验，结论不一定适用于广告型产品"
  },

  "tldr": [{"text": "* 核心结论 1", "t": "00:31"}],       // * 3–6 条

  "framework": [{                                      // * 内容框架
    "title": "路线图是伪计划",
    "start": "00:20", "end": "01:58",
    "summary": "…",
    "points": [{"text": "写下日期就停止学习", "t": "00:31"}]
  }],

  "viewpoints": [{                                     // * 主要观点
    "title": "DAU 是订阅业务的虚荣指标",
    "detail": "展开说明…",
    "evidence": "亲身经历：从 DAU 切到每付费用户周收听时长 [02:25]",
    "speaker": "Maya Chen",
    "t": "03:12"
  }],

  "quotes": [{                                         // * 金句，en 必须从原文复制
    "zh": "你选择的指标，决定了你做出的产品。",
    "en": "the metric you choose decides the product you build",
    "speaker": "Maya Chen",
    "t": "02:48",
    "why": "一句话讲清指标和产品形态的因果关系"
  }],

  "conflicts": [{                                      // * ≥1
    "topic": "DAU 还能不能当北极星",
    "type": "嘉宾 vs 主持人",                           // 嘉宾 vs 主持人 / 嘉宾 vs 行业共识 / 前后矛盾 / 嘉宾 vs 评论区 / 嘉宾 vs 其他权威 / 隐含张力
    "a": {"who": "主持人（转述常见观点）", "claim": "DAU 仍是消费类 App 最好的北极星", "t": "03:02"},
    "b": {"who": "Maya Chen", "claim": "订阅业务应该看习惯深度", "t": "03:12"},
    "analysis": "分歧在于商业模式：广告型产品按次变现，DAU 与收入直接相关；订阅型产品按月变现…"
  }],

  "hotspots": [{                                       // * 讨论热点
    "title": "「DAU 是虚荣指标」引发共鸣与反驳",
    "t": "03:03", "end": "03:31",
    "source": ["heatmap", "comments"],                 // heatmap / comments / content
    "heat": 0.92,                                      // 0–1，取 heatmap 峰值，或按评论权重归一化
    "why": "全片回看最多的一段，有两条高赞评论直接写了 3:12 和 3:15，多数人是回来确认她是不是真这么说。",
    "supplement": "评论区有人提出广告型产品的反例 [03:12]；嘉宾未回应",
    "comments": [{"text_zh": "作为社交 App 的 PM，这句话我感同身受", "likes": 2400}]
  }],

  "comment_insights": [{
    "theme": "对「按问题做规划」的落地疑虑",
    "stance": "质疑",                                   // 赞同 / 质疑 / 补充 / 求资源 / 共鸣 / 玩梗
    "summary": "约 15% 的高赞评论认为 CEO 不会接受没有日期的路线图",
    "likes": 200,
    "t": "01:12"
  }],

  "resources": [{"name": "《Inspired》", "t": "04:10", "note": "嘉宾推荐的产品入门书"}],
  "glossary": [{"term": "North Star Metric", "zh": "北极星指标", "note": "字幕误识别为 north store，已更正"}]
}
```

## 渲染映射

| 字段 | HTML 板块 | 校验级别 |
|---|---|---|
| one_liner / keywords / guests | 页首 | 缺少时给 warning |
| value + tldr | 结论 | 缺时间戳报 error |
| framework | 内容结构（时间线） | 缺时间戳报 error |
| viewpoints | 主要观点 | 缺时间戳报 error |
| quotes | 金句（中英对照） | 缺时间戳报 error，原文匹配不上也报 error |
| conflicts | 观点冲突（双方并排） | 缺时间戳报 error |
| hotspots | 讨论热点（在热度曲线上标号） | 缺时间戳报 error |
| comment_insights | 评论区 | 缺时间戳给 warning |
| resources | 提到的书和资源 | 缺时间戳给 warning |
| glossary | 术语与更正 | — |
| transcript_zh.md | 全文译稿（可搜索、可显示英文、跟随播放） | — |
