---
name: rss-daily-digest
description: >-
  抓取主流科技/媒体 RSS 源，按目标自然日筛选条目，并在项目根目录 temp 下写入按日期命名的 markdown
  文件；**须为中文表述**（条目标题、摘要等译成通顺中文，链接与专有名词可保留原文）。适用于
  每日资讯摘要或从订阅源同步当日 md 文件。
---

# RSS 当日资讯 → `temp/rss_YYYY-MM-DD.md`

## 目标

从已配置的 RSS/Atom 源汇总**当日**条目，输出**一篇**按日期命名的 markdown 到 `temp/` 目录。输出为分条块状结构（`【序号】` + 标题/来源/日期/链接/摘要），便于后续二次处理。**资讯条目中的标题、摘要等须译为通顺的中文**；产品名、公司名、技术缩写等可保留英文或中英并用，以可读为准。

**输出目录**：`temp/`。

## 何时运行

- 用户要求「今日 RSS / 抓取资讯 / 生成当日 md」等。
- 编辑 `feeds.json` 之后，可重新运行以刷新内容。

## 流程

step1. 核心内容生成

1. **目标日期**：默认使用 **`Asia/Shanghai` 时区下的「今天」**。若用户指定日期，则使用该日期（ISO `YYYY-MM-DD`）。
2. **执行抓取脚本**（见下文），在仓库根目录运行。脚本会按条目抓取并去重，优先运行脚本以保证输出可复现；仅在脚本无法运行（如网络被拦等）时再手写文件。
3. **条数与质量**：`rss_articles.md` 里输出的「类型」与条目标题一致（仅对标题做关键词判定）。**合并去重后，每个数据源（订阅源）最多保留 5 条**当日条目（可用 `--max-per-feed M` 调整；同源内按质量分与发布时间择优）。**默认不对「类型」做条数上限**；若需截断，可用 `--max-per-category N`（N>0 时每类最多 N 条）。启用截断时，在同类内先按订阅源 **`priority`（越大越优先，见 `feeds.json`）**，再按时间排序输出；无需为落选条目强写摘要。
4. **检查**生成文件：去重、按需删掉跑题条目，确认输出字段完整（标题/**类型**/来源/日期/链接/摘要/**图片**/**视频**）。脚本会打开每条「链接」抓取正文（优先 `<article>`/`<main>` 区域），各条**最多 2 张图、2 个视频**（正文中出现顺序）；无需逐条打开网页时可加 `--skip-body-media`。

step2. 内容翻译和中文润色（不要询问用户，直接开始）

1. **中文表述**：将**每条标题、摘要** 都通过 翻译为自然、准确的 中文（链接 URL 不变；无摘要可省略「摘要」行）。

step3. 输出 `articles` 和 `发布公告`

step4. 综合 `rss_articles.md` 的内容，生成最终完整的日报md `content/post/<YYYY-MM-DD>.md`

1. 如果遇到多条表达的是 同一件事情，或者相同的资讯内容的，根据数据源的优先级，选取一条即可
2. 每种类型最多取10条高价值的新闻，如果不足10条，则全用，你要有点判断能力哦，没什么价值的新闻不要取
3. 严格按以下类型列表顺序生成类型标题, 类型下的文章必须和 `rss_articles.md` 中表达的类型保持一致：
```text
"模型发布",
"设计生态",
"开发生态",
"产品应用",
"技术与洞察",
"行业生态",
"前瞻与传闻",
"要闻"
```

## 命令

在仓库根目录执行：

```bash
python .cursor/skills/rss-daily-digest/scripts/fetch_rss_digest.py
```

可选参数：

```bash
python .cursor/skills/rss-daily-digest/scripts/fetch_rss_digest.py --date 2026-04-20
python .cursor/skills/rss-daily-digest/scripts/fetch_rss_digest.py --feeds .cursor/skills/rss-daily-digest/scripts/feeds.json
python .cursor/skills/rss-daily-digest/scripts/fetch_rss_digest.py --max-per-feed 5
python .cursor/skills/rss-daily-digest/scripts/fetch_rss_digest.py --max-per-category 10
python .cursor/skills/rss-daily-digest/scripts/fetch_rss_digest.py --skip-body-media
```

依赖：**Python 3.10+**，**仅标准库**（无需 `pip install`）。

## 输出 articles 结构

严格按下列块状 Markdown 骨架输出：

```text
【1】
标题: 这届10后AI原住民,把小红书变成了“地下硅谷”
类型: 产品应用
来源: 干饭吃肉喝汤
优先级:2
日期: 2026-04-21 11:53:22
链接: https://mp.weixin.qq.com/s?...
摘要: AI的巨轮滚滚碾过,人们都在满头大汗地玩着一场名为不被淘汰的生存游戏...
--------------------------------------------------------------
【2】
...
```

**类型**（单独一行）：仅根据**标题**自动判定，必为以下之一——  
`模型发布` | `开发生态` | `技术与洞察` | `产品应用` | `行业生态` | `前瞻与传闻` | `要闻`  
（脚本对标题做关键词打分；无法归类时默认为 **要闻**。）

要求：
- 每条在摘要之后有 **图片**、**视频** 两行；各含最多 2 个 URL（`；` 分隔），无则 `（无）`；其余为标题/类型/来源/日期/链接/摘要 + 1 行分隔线。
- 为空时使用占位：`（无标题）`、`（未知来源）`、`（无链接）`、`（无摘要）`；图片/视频行无资源时为 `（无）`。
- 生成文件名统一为：`temp/<YYYY-MM-DD>/rss_articles.md`。
- 根据优先级排列

## 输出 发布公告 结构


1. 必须生成发布公告，保存为：`temp/<YYYY-MM-DD>/message.md`，严格按模板生成，保持结构一致，如下：

```markdown

📰 IUX AI Daily 
| AI早报速递 | 2026-04-20 |
| 今日金价 |
| xxx 元/克 |
| 今日油价 |
| 92#汽油：xxx 元/升 |
| ... 元/升 |
============================
🌷 <简短的充满诗意的开场白>。
🥰 大家好，我是你们的助理哥，今天是<日期><星期>，<农历xxx>。
🌥️ <杭州天气预报(必须简短)>,为您带来今日AI报道。

2026年4月16日

<最多7条比较重要的新闻标题>
1.  Google发布Gemini 3.1 Flash TTS模型，优化文本转语音性能。
2.  xxx
...
7.  xxx


============================
🔗 原文链接：https://ypvichi.github.io/iux-daily-blog//post/2026-04-20/

```
2. 杭州天气预报数据 调用`weather-query`查询

## 订阅源列表

默认精选列表见 [scripts/feeds.json](scripts/feeds.json)。编辑者可增删源（名称 + url，可选 **`priority`**：非负整数，**数值越大越优先**——同类截断时优先保留高 priority 源的条目；重复链接去重时保留 priority 更高的一条）。若某源返回 403 或为空，可换该站其他官方 RSS 地址，或从列表中移除。

更多来源与排错说明见 [reference.md](reference.md)。

