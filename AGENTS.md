# 环境准备

## 在进行任何工作任务前，请确保已安装以下内容

1. hugo(v.157): 博客生成工具
2. node.js(>=22)
3. git
4. github cli
5. python

## **配置 Git Hook（Hiklink通知）**

本仓已在 **`.git/hooks/pre-push`** 配置推送前 Hiklink 通知（`#!/bin/sh`，通过 `$(git rev-parse --show-toplevel)/hiklink.js` 调用，无需手填路径）：

- **Skill 路径**：会匹配 **`.cursor/skills/`** 或 `skills/`
- **通知失败**（网络、环境变量等）**不会阻止** `git push`（`node … || true`）
- 首次克隆后若无该文件，可从本仓库复制一份到 `.git/hooks/pre-push`，并确保可执行：`chmod +x .git/hooks/pre-push`（Windows 用 Git 自带的 `chmod` 或 Git Bash 执行一次）

Hiklink 所需环境变量见根目录 **`hiklink.js`** 文件头注释；未配置时脚本会输出跳过提示，推送照常进行。

# 项目核心任务指导

## 生成日报

### Step1. 读取RSS资讯

**调用SKILL**
调用 `rss-daily-digest` 技能进行该子任务，完成读取后，统一保存到 `<项目根目录>/temp/<当前日期>/rss_articles.md`
**相关约束**
1. 只获取当日 RSS 资讯；按 `fetch_rss_digest.py` 规则，**合并去重后每个数据源最多 5 条**、**每个类型（与 `rss_articles.md` 中「类型」一致）最多 15 条**，由脚本按 priority 与质量分择优，落选条目不必写入 `content/post`。
2. `rss_articles.md` 中每条可含从原文页抓取的 **「图片:」「视频:」** 行；生成 `content/post/<日期>.md` 时，若该条在 `rss_articles` 中**不是** `（无）`，须把相应图片/视频**写入**该条对应的「摘要分块」中（见 Step3 模板与格式说明）。

### Step2. 综合 `rss_articles.md` 的内容，生成最终完整的日报md `content/post/<YYYY-MM-DD>.md`


**输出格式**

严格按以下 markdown 模版输出：

1. 必须按概览中的文章顺序来输出  二级标题的 标题列表
2. **图片与视频**（与 `rss_articles.md` 中每条一一对应）：若该条的「图片:」「视频:」后**有 URL**（不是 `（无）`），在**该条**的摘要分块中追加展示：
   - **图片**：在「相关链接」**之前**，用 markdown 行内图语法逐张输出，**顺序与 `rss_articles` 中 URL 一致**，例如 `![配图](https://...)`，最多 2 张。
   - **视频**：在「相关链接」**之前**（有图片时放在「图片」之后），嵌入类 URL 可用「视频链接」加 `<a href="..." target="_blank" rel="noopener noreferrer">` 的可点击行；**普通视频直链**同样用可点击链接列出即可，最多 2 个。
3. 若 `rss_articles` 中该条图片与视频均为 `（无）`，**不要**在对应分块输出

-------------------------------------------------------------------
markdown 模板
-------------------------------------------------------------------

```markdown
+++
date = '2026-04-20T08:30:00+08:00'
draft = true
title = '【2026-04-20】刊'

+++

# AI早报【2026-04-20】刊

## 概览

### 类别名称(多种类别,每一个类别新闻不超过10条)

- <中文标题><a href="链接地址" target="_blank" rel="noopener noreferrer">↗</a>

----- （摘要内容列表，必须和概览中的顺序保持一致,概览中的标题必须和下列中的标题是一一对应的，不能出错）
## <a href="链接地址" target="_blank" rel="noopener noreferrer">中文标题</a>

- 中文摘要


![简短短述或「配图 1」](https://从rss_articles原样复制的图片URL1)
![简短短述或「配图 2」](https://从rss_articles原样复制的图片URL2)


<a href="https://从rss_articles复制的视频或嵌入地址" target="_blank" rel="noopener noreferrer">视频链接</a>

相关链接：

- <a href="https://example.com/path" target="_blank" rel="noopener noreferrer">https://example.com/path</a>
- xxx
- xxx
-----



---

**提示**：内容由AI辅助创作，可能存在**幻觉**和**错误**。

```
-------------------------------------------------------------------------