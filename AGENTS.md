# 环境准备

## 在进行任何工作任务前，请确保已安装以下内容

1. hugo(v.157): 博客生成工具
2. node.js(>=22)
3. git
4. github cli
5. python

# 项目核心任务指导

## 生成日报

### Step1. 读取RSS资讯

**调用SKILL**
调用 `rss-daily-digest` 技能进行该子任务，完成读取后，统一保存到 `<项目根目录>/temp/<当前日期>/rss_articles.md`
**相关约束**
1. 只获取当日RSS资讯


### Step3. 综合 `rss_articles.md` 的内容，生成最终完整的日报md `content/post/<YYYY-MM-DD>.md`

**相关约束**

**输出格式**

严格按以下markdown模版输出：

1. 必须按概览中的文章顺序来输出  二级标题的 标题列表

-------------------------------------------------------------------
makerdown 模板
-------------------------------------------------------------------

```markdown
+++
date = '2026-04-20T08:30:00+08:00'
draft = true
title = 'AI早知道 【2026-04-20】刊'
+++

# AI早知道 【2026-04-20】刊

## 概览

### 类别名称(多种类别,每一个类别新闻不超过10条)

- <中文标题><a href="链接地址" target="_blank" rel="noopener noreferrer">↗</a>

----- （摘要内容列表，必须和概览中的顺序保持一致）
## <a href="链接地址" target="_blank" rel="noopener noreferrer">中文标题</a>

- 中文摘要

相关链接：
  `- <a href="https://example.com/path" target="_blank" rel="noopener noreferrer">https://example.com/path</a>`。
-----



---

**提示**：内容由AI辅助创作，可能存在**幻觉**和**错误**。

```
-------------------------------------------------------------------------


