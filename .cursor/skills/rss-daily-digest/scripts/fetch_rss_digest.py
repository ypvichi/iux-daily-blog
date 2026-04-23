#!/usr/bin/env python3
"""
Fetch multiple RSS/Atom feeds, keep entries whose published time falls on the
target calendar day (Asia/Shanghai), write markdown to temp/YYYY-MM-DD/rss_articles.md.

Per display type (classify_by_title, same as the written 类型 field), keep at
most N entries; within each type, pick by quality_score then sort by time.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

try:
    TZ_SH = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001 — Windows without tzdata
    TZ_SH = timezone(timedelta(hours=8))
USER_AGENT = (
    "Mozilla/5.0 (compatible; iux-daily-blog/rss-daily-digest; +https://github.com/ypvichi/iux-daily-blog)"
)
FEED_TIMEOUT_SECONDS = 12.0
FETCH_TIMEOUT_SECONDS = 18.0

# 八类归纳：要闻、模型发布、开发生态、产品应用、技术与洞察、行业生态、前瞻与传闻、其他。
# 展示顺序；分类冲突时用 _CAT_PRIORITY 决胜（特异性优先）。
CATEGORIES: tuple[str, ...] = (
    "要闻",
    "模型发布",
    "开发生态",
    "产品应用",
    "技术与洞察",
    "行业生态",
    "前瞻与传闻",
    "其他",
)

# 输出「类型」字段仅限以下七类（无「其他」）；仅依据标题归类，无明确信号时默认「要闻」。
# 顺序与技能说明一致：模型发布 → … → 要闻。
DISPLAY_TYPES: tuple[str, ...] = (
    "模型发布",
    "开发生态",
    "技术与洞察",
    "产品应用",
    "行业生态",
    "前瞻与传闻",
    "要闻",
)
# 同分时优先归入更具体的类（与 DISPLAY_TYPES 列举顺序无关）。
_DISPLAY_TYPE_PRIORITY: tuple[str, ...] = (
    "模型发布",
    "要闻",
    "开发生态",
    "产品应用",
    "技术与洞察",
    "行业生态",
    "前瞻与传闻",
)
MAX_ITEMS_PER_CATEGORY = 10
# 同分时优先归入更「具体」的类（与 CATEGORIES 顺序无关）。
_CAT_PRIORITY: tuple[str, ...] = (
    "模型发布",
    "要闻",
    "开发生态",
    "产品应用",
    "技术与洞察",
    "行业生态",
    "前瞻与传闻",
    "其他",
)

# 小写匹配；多字词尽量带边界空格避免误伤（如 "go "）。
_DEV_KEYWORDS: tuple[str, ...] = (
    "java",
    "jdk",
    "python",
    "rust",
    "golang",
    " spring",
    "spring ",
    "kubernetes",
    "docker",
    "redis",
    "database",
    "cache",
    "distributed",
    "framework",
    "library",
    "sdk",
    "graphql",
    "devops",
    "typescript",
    "javascript",
    "react",
    "vue",
    "node.js",
    "node ",
    "backend",
    "frontend",
    "fullstack",
    "langchain",
    "hibernate",
    "keycloak",
    "helidon",
    " spring boot",
    "spring boot",
    "rag",
    "engineering",
    "compiler",
    "jvm",
    "llvm",
    "wasm",
    "postgres",
    "mysql",
    "mongodb",
    "elasticsearch",
    "kafka",
    "terraform",
    "ansible",
    "cli",
    "ide",
    "vscode",
    "jetbrains",
    "build",
    "deploy",
    "infra",
    "sre",
    "observability",
    "prometheus",
    "opentelemetry",
    "git",
    "github",
    "gitlab",
    "opensource",
    "open source",
    "oss",
    "npm",
    "maven",
    "gradle",
    "infoq",
    "工程化",
    "分布式",
    "缓存",
    "数据库",
    "开源",
    "框架",
    "后端",
    "前端",
    "开发",
    "构建",
    "部署",
)

# 要闻：政策、监管、要闻简报/早报等。
_HEADLINE_KEYWORDS: tuple[str, ...] = (
    "policy",
    "regulation",
    "regulatory",
    "antitrust",
    "lawsuit",
    "congress",
    "senate",
    "government",
    "commission",
    "briefing",
    "派早报",
    "早报",
    "简报",
    "国常",
    "监管",
    "政策",
)

# 模型发布：新模型、基座、权重与版本等。
_MODEL_KEYWORDS: tuple[str, ...] = (
    "gpt",
    "claude",
    "gemini",
    "llama",
    "mistral",
    "deepseek",
    "large language",
    "foundation model",
    "tokenizer",
    "billion parameter",
    " open weights",
    "open weights",
    "weights release",
    "model release",
    "new model",
    "大模型",
    "基础模型",
    "模型发布",
    "opus",
    " opus ",
)

# 产品应用：面向用户/客户的产品、功能与端体验（含平台型产品、机器人产品化等）。
_PRODUCT_KEYWORDS: tuple[str, ...] = (
    "product",
    "launch",
    " feature",
    "features",
    "consumer",
    "subscription",
    "app store",
    "mobile",
    "saas",
    "platform",
    "ship",
    "ships",
    "出货",
    "新品",
    "robot",
    "humanoid",
    "marathon",
    "hardware",
)

# 技术与洞察：架构、方法论、趋势分析与工程实践类深度内容。
_TECH_INSIGHT_KEYWORDS: tuple[str, ...] = (
    "architecture",
    "pattern",
    "analysis",
    "research paper",
    "engineering",
    "practice",
    "insight",
    "beyond rag",
    "distributed",
    "evolution",
    "methodology",
    "趋势",
    "洞察",
    "实践",
    "工程化",
)

# 行业生态：市场、出行/垂直赛道、融资与创业公司、商业格局与公司动态。
_INDUSTRY_KEYWORDS: tuple[str, ...] = (
    "industry",
    "ecosystem",
    "market",
    "funding",
    "venture",
    "mobility",
    "competition",
    "landscape",
    "startup",
    "unicorn",
    "acquisition",
    "merger",
    "ipo",
    "uber",
    "lawsuit",
    "ceo",
    "interview",
    "赛道",
    "生态",
    "格局",
    "收购",
    "并购",
)

# 前瞻与传闻：安全事件、并购传闻、预测、播客/舆论、争议性公司动态等。
_NEWS_KEYWORDS: tuple[str, ...] = (
    "hack",
    "hacked",
    "hacking",
    "breach",
    "ransomware",
    "leak",
    "rumor",
    "rumour",
    "existential",
    "prediction",
    "forecast",
    "layoff",
    "layoffs",
    "manifesto",
    "denouncing",
    "podcast",
    "palantir",
    "融资",
    "传闻",
    "黑客",
    "入侵",
    "爆料",
    "裁员",
)

# 航天/科普等偏「非开发」题材，默认归入「其他」；若同时命中强开发词则仍以开发为准。
_SPACE_KEYWORDS: tuple[str, ...] = (
    "blue origin",
    "spacex",
    " rocket",
    " satellite",
    " orbit",
    "lunar",
    "moon ",
    "nasa",
    "new glenn",
    "launch vehicle",
    "arstechnica.com/space",
)


def local_tag(elem: ET.Element) -> str:
    t = elem.tag
    if t.startswith("{"):
        return t.rsplit("}", 1)[-1]
    return t


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = unescape(s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_rfc2822(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError, OverflowError):
        return None


def parse_iso_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def pick_child_text(parent: ET.Element, name: str) -> str | None:
    for ch in parent:
        if local_tag(ch) == name and ch.text:
            return ch.text.strip()
        if local_tag(ch) == name:
            parts = [ch.text or ""]
            for sub in ch:
                parts.append(ET.tostring(sub, encoding="unicode"))
            joined = "".join(parts).strip()
            if joined:
                return strip_html(joined) or joined
    return None


def fetch_xml(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=FEED_TIMEOUT_SECONDS) as resp:
        return resp.read()


def fetch_html_text(url: str, max_bytes: int = 2 * 1024 * 1024) -> str | None:
    """GET HTML page; return decoded text or None on failure. Stdlib only."""
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
            raw = resp.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
        # charset: prefer UTF-8; sites vary
        return raw.decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, ValueError):
        return None


class _StripScriptsStyles(HTMLParser):
    """Collect visible text; skip script/style/noscript/svg/template."""

    _SKIP = frozenset({"script", "style", "noscript", "svg", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag.lower() in self._SKIP:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIP and self._depth > 0:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._chunks)).strip()


def html_to_visible_text(html: str) -> str:
    """Strip tags roughly; keep readable body text for excerpt/summary."""
    if not html:
        return ""
    # Remove common boilerplate blocks (best-effort, regex)
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", html)
    # Prefer <article> or <main> if present
    art = re.search(r"(?is)<article[^>]*>(.*?)</article>", html)
    if art:
        html = art.group(1)
    else:
        main = re.search(r"(?is)<main[^>]*>(.*?)</main>", html)
        if main:
            html = main.group(1)
    p = _StripScriptsStyles()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 — lenient parse
        return strip_html(html)[:12000]
    t = p.text()
    if len(t) < 80:
        t = strip_html(html)
    return t[:12000]


def extractive_core_summary(text: str, max_sentences: int = 5, max_chars: int = 650) -> str:
    """
    Extractive 'summary': first substantive sentences (not semantic AI).
    Keeps output short for copyright / fair use as excerpt.
    """
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    parts = re.split(r"(?<=[.!?。！？])\s*", text)
    parts = [p.strip() for p in parts if p and len(p.strip()) > 12]
    if not parts:
        return text[:max_chars].rstrip() + "…"
    out: list[str] = []
    acc = 0
    for p in parts:
        if acc + len(p) > max_chars and out:
            break
        out.append(p)
        acc += len(p) + 1
        if len(out) >= max_sentences:
            break
    s = " ".join(out)
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"
    return s


_IMG_SRC_RE = re.compile(
    r"""<img[^>]+src\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)


def extract_inline_images(html: str, base_url: str, max_n: int = 2) -> list[str]:
    """Resolve up to max_n http(s) image URLs from HTML; skip data/blob/tracking heuristics."""
    if not html or not base_url:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _IMG_SRC_RE.finditer(html):
        src = (m.group(1) or "").strip()
        if not src or src.startswith(("data:", "blob:")):
            continue
        abs_u = urljoin(base_url, src)
        if not abs_u.startswith(("http://", "https://")):
            continue
        low = abs_u.lower()
        if any(x in low for x in ("pixel", "tracking", "spacer", "1x1", "beacon", "analytics")):
            continue
        if abs_u in seen:
            continue
        seen.add(abs_u)
        out.append(abs_u)
        if len(out) >= max_n:
            break
    return out


def enrich_entry_with_body(entry: dict) -> dict:
    """Fetch link HTML, add body_text, core_summary, core_images (best-effort)."""
    link = (entry.get("link") or "").strip()
    out = dict(entry)
    out["body_error"] = None
    html = fetch_html_text(link)
    if html is None:
        out["body_error"] = "fetch_failed"
        return out
    body_text = html_to_visible_text(html)
    out["body_text"] = body_text
    out["core_summary"] = extractive_core_summary(body_text)
    out["core_images"] = extract_inline_images(html, link, max_n=2)
    if not out["core_summary"]:
        out["body_error"] = "empty_text"
    return out


def parse_feed_items(xml_bytes: bytes, source_name: str) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    lt = local_tag(root)
    items: list[dict] = []

    if lt == "rss":
        channel = next((c for c in root if local_tag(c) == "channel"), None)
        if channel is None:
            return items
        for node in channel:
            if local_tag(node) != "item":
                continue
            title = pick_child_text(node, "title") or "(无标题)"
            link_el = next((c for c in node if local_tag(c) == "link"), None)
            link = ""
            if link_el is not None:
                link = (link_el.text or "").strip()
                if not link:
                    link = (link_el.get("href") or "").strip()
            pub = pick_child_text(node, "pubDate")
            dt = parse_rfc2822(pub)
            if dt is None:
                # dc:date
                for ch in node:
                    if local_tag(ch) == "date" or ch.tag.endswith("}date"):
                        dt = parse_iso_datetime(ch.text)
                        break
            desc = pick_child_text(node, "description")
            summary = strip_html(desc)[:500] if desc else ""
            items.append(
                {
                    "source": source_name,
                    "title": strip_html(title) or title,
                    "link": link,
                    "published": dt,
                    "summary": summary,
                }
            )
        return items

    if lt == "feed":  # Atom
        for node in root:
            if local_tag(node) != "entry":
                continue
            title = pick_child_text(node, "title") or "(无标题)"
            link = ""
            for ch in node:
                if local_tag(ch) == "link":
                    rel = (ch.get("rel") or "alternate").lower()
                    if rel == "alternate" or not link:
                        href = ch.get("href") or ""
                        if href:
                            link = href.strip()
            updated = pick_child_text(node, "updated") or pick_child_text(node, "published")
            dt = parse_iso_datetime(updated)
            summary = pick_child_text(node, "summary") or pick_child_text(node, "content")
            summary = strip_html(summary)[:500] if summary else ""
            items.append(
                {
                    "source": source_name,
                    "title": strip_html(title) or title,
                    "link": link,
                    "published": dt,
                    "summary": summary,
                }
            )
        return items

    return items


def date_in_shanghai(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    return dt.astimezone(TZ_SH).date()


def dedupe(entries: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for e in entries:
        key = (e["link"] or "", e["title"] or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _safe_text(s: str | None) -> str:
    """Collapse line breaks/extra spaces so each field stays one line."""
    return re.sub(r"\s+", " ", (s or "")).strip()


def _keyword_hits(blob: str, keywords: tuple[str, ...]) -> int:
    """
    统计关键词命中；英文/ASCII 词用词边界，避免 infra/git/rag 等短词误伤。
    含空格短语与非 ASCII（中文等）仍用子串匹配。
    """
    n = 0
    for kw in keywords:
        k = kw.strip()
        if not k:
            continue
        if " " in k or any(ord(c) > 127 for c in k):
            if k.lower() in blob:
                n += 1
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", blob):
            n += 1
    return n


def _best_category(scores: dict[str, int]) -> str:
    """分最高者胜出；同分保留 _CAT_PRIORITY 中较先出现的类（更具体）。"""
    best = "其他"
    best_v = -1
    for cat in _CAT_PRIORITY:
        v = scores.get(cat, 0)
        if v > best_v:
            best = cat
            best_v = v
    if best_v <= 0:
        return "其他"
    return best


def classify_entry(entry: dict) -> str:
    """
    将条目归入 CATEGORIES 之一；基于标题/摘要/来源/URL 的多组关键词打分，
    并辅以安全航天等规则；定稿时可人工微调分类。
    """
    title = (entry.get("title") or "").lower()
    summary = (entry.get("summary") or "").lower()
    source = (entry.get("source") or "").lower()
    link = (entry.get("link") or "").lower()
    blob = f"{title} {summary} {source} {link}"

    scores: dict[str, int] = {c: 0 for c in CATEGORIES}
    scores["要闻"] = _keyword_hits(blob, _HEADLINE_KEYWORDS)
    scores["模型发布"] = _keyword_hits(blob, _MODEL_KEYWORDS)
    scores["开发生态"] = _keyword_hits(blob, _DEV_KEYWORDS)
    scores["产品应用"] = _keyword_hits(blob, _PRODUCT_KEYWORDS)
    scores["技术与洞察"] = _keyword_hits(blob, _TECH_INSIGHT_KEYWORDS)
    scores["行业生态"] = _keyword_hits(blob, _INDUSTRY_KEYWORDS)
    scores["前瞻与传闻"] = _keyword_hits(blob, _NEWS_KEYWORDS)

    # 安全/重大传闻加权
    if re.search(r"(?<![a-z0-9])(?:hack|hacked|hacking|breach)(?![a-z0-9])", blob):
        scores["前瞻与传闻"] += 4
    if "existential" in blob:
        scores["前瞻与传闻"] += 3
    if "vercel" in blob and ("hack" in blob or "hacked" in blob or "breach" in blob):
        scores["前瞻与传闻"] += 2

    space = _keyword_hits(blob, _SPACE_KEYWORDS)
    strong_tech = (
        scores["模型发布"]
        + scores["开发生态"]
        + scores["技术与洞察"]
        + scores["产品应用"]
        + scores["行业生态"]
        + scores["前瞻与传闻"]
        + scores["要闻"]
    )
    # 航天/太空为主且整体科技信号弱 → 其他
    if space >= 1 and strong_tech < 4:
        return "其他"

    return _best_category(scores)


def classify_by_title(title: str | None) -> str:
    """
    仅根据标题归入 DISPLAY_TYPES 之一；与正文/摘要/链接无关。
    无匹配关键词时默认为「要闻」。
    """
    raw = (title or "").strip()
    if not raw or raw == "(无标题)":
        return "要闻"
    blob = raw.lower()

    scores: dict[str, int] = {c: 0 for c in DISPLAY_TYPES}
    scores["要闻"] = _keyword_hits(blob, _HEADLINE_KEYWORDS)
    scores["模型发布"] = _keyword_hits(blob, _MODEL_KEYWORDS)
    scores["开发生态"] = _keyword_hits(blob, _DEV_KEYWORDS)
    scores["产品应用"] = _keyword_hits(blob, _PRODUCT_KEYWORDS)
    scores["技术与洞察"] = _keyword_hits(blob, _TECH_INSIGHT_KEYWORDS)
    scores["行业生态"] = _keyword_hits(blob, _INDUSTRY_KEYWORDS)
    scores["前瞻与传闻"] = _keyword_hits(blob, _NEWS_KEYWORDS)

    if re.search(r"(?<![a-z0-9])(?:hack|hacked|hacking|breach)(?![a-z0-9])", blob):
        scores["前瞻与传闻"] += 4
    if "existential" in blob:
        scores["前瞻与传闻"] += 3
    if "vercel" in blob and ("hack" in blob or "hacked" in blob or "breach" in blob):
        scores["前瞻与传闻"] += 2

    space = _keyword_hits(blob, _SPACE_KEYWORDS)
    strong_tech = (
        scores["模型发布"]
        + scores["开发生态"]
        + scores["技术与洞察"]
        + scores["产品应用"]
        + scores["行业生态"]
        + scores["前瞻与传闻"]
        + scores["要闻"]
    )
    if space >= 1 and strong_tech < 4:
        return "要闻"

    best = "要闻"
    best_v = -1
    for cat in _DISPLAY_TYPE_PRIORITY:
        v = scores.get(cat, 0)
        if v > best_v:
            best = cat
            best_v = v
    if best_v <= 0:
        return "要闻"
    return best


def bucket_by_category(entries: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for e in entries:
        cat = classify_entry(e)
        buckets[cat].append(e)
    return buckets


def quality_score_entry(entry: dict) -> float:
    """
    粗粒度质量分：优先长标题、有信息量的摘要、权威媒体来源；
    压低纯短链标题、空泛的「Read more」、过短噪声等。与具体业务可再调权重。
    """
    title = (entry.get("title") or "").strip()
    summary = (entry.get("summary") or "").strip()
    source = (entry.get("source") or "").lower()
    link = (entry.get("link") or "").lower()
    tl = title.lower()

    s = 0.0
    s += min(len(title), 220) * 0.1
    s += min(len(summary), 1200) * 0.015

    if title.startswith("http://") or title.startswith("https://"):
        s -= 85.0
    if re.match(r"^https?://t\.co/\S+\Z", title.strip(), re.I):
        s -= 120.0
    if len(title) < 8 and not any(ord(c) > 127 for c in title):
        s -= 45.0
    if re.match(r"^read more\b", tl) or tl in ("read more", "read more."):
        s -= 40.0
    if tl.startswith("read more about the model"):
        s -= 35.0

    # 摘要过短或典型推广尾迹
    if len(summary) < 18:
        s -= 15.0
    if "powered by xgo" in summary.lower() and len(summary) < 160:
        s -= 12.0

    for hint in (
        "量子位",
        "爱范儿",
        "ifanr",
        "qbitai",
        "阮一峰",
        "infoq",
        "宝玉",
        "theverge",
        "techcrunch",
        "wired",
        "openai",
        "google",
        "github",
    ):
        if hint in source or hint in link:
            s += 6.0
            break

    return s


def select_top_per_display_type(entries: list[dict], max_per: int) -> list[dict]:
    """
    与输出字段「类型」一致（仅 `classify_by_title`），每类最多保留 max_per 条；
    同类内按 quality_score_entry 降序择优，再按发布时间升序输出整篇列表。
    """
    if max_per <= 0:
        return []
    buckets: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        cat = classify_by_title(e.get("title"))
        buckets[cat].append(e)

    selected: list[dict] = []
    for cat in DISPLAY_TYPES:
        group = buckets.get(cat, [])
        group.sort(
            key=lambda e: (
                -quality_score_entry(e),
                -(e.get("published") or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
            )
        )
        selected.extend(group[:max_per])

    selected.sort(
        key=lambda e: e.get("published") or datetime.min.replace(tzinfo=timezone.utc)
    )
    return selected


def write_markdown(
    out_path: Path,
    entries: list[dict],
) -> None:
    lines: list[str] = []
    for i, e in enumerate(entries, start=1):
        title = _safe_text(e.get("title")) or "(无标题)"
        source = _safe_text(e.get("source")) or "(未知来源)"
        link = _safe_text(e.get("link")) or "（无链接）"
        published = e.get("published")
        if isinstance(published, datetime):
            published_str = published.astimezone(TZ_SH).strftime("%Y-%m-%d %H:%M:%S")
        else:
            published_str = ""
        summary = _safe_text(e.get("summary")) or "（无摘要）"

        lines.append(f"【{i}】")
        lines.append(f"标题: {title}")
        lines.append(f"类型: {classify_by_title(e.get('title'))}")
        lines.append(f"来源: {source}")
        lines.append(f"日期: {published_str}")
        lines.append(f"链接: {link}")
        lines.append(f"摘要: {summary}")
        lines.append("--------------------------------------------------------------")

    if lines:
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def flatten_feeds_config(feeds_data: list) -> list[dict[str, str]]:
    """
    支持两种 feeds.json 形态：
    - 嵌套：顶层为各类别 { "name", "feeds": [ { "name", "url" }, ... ] }，展平为单列表拉取。
    - 旧版：顶层直接为 { "name", "url" }。
    """
    out: list[dict[str, str]] = []
    for item in feeds_data:
        if not isinstance(item, dict):
            continue
        if item.get("url"):
            n = (item.get("name") or urlparse(str(item.get("url", ""))).netloc or "unknown").strip()
            out.append({"name": n, "url": str(item["url"]).strip()})
            continue
        for sub in item.get("feeds") or []:
            if not isinstance(sub, dict):
                continue
            u = sub.get("url")
            if not u:
                continue
            n = (sub.get("name") or item.get("name") or urlparse(str(u)).netloc or "unknown").strip()
            out.append({"name": n, "url": str(u).strip()})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="RSS/Atom daily digest")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target calendar day YYYY-MM-DD (default: today in Asia/Shanghai)",
    )
    parser.add_argument(
        "--feeds",
        type=Path,
        default=None,
        help="Path to feeds.json",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: cwd)",
    )
    parser.add_argument(
        "--max-per-category",
        type=int,
        default=MAX_ITEMS_PER_CATEGORY,
        metavar="N",
        help=f"每类「类型」最多保留条数，同类内按质量分择优（默认 {MAX_ITEMS_PER_CATEGORY}）",
    )
    args = parser.parse_args()

    repo_root = (args.repo_root or Path.cwd()).resolve()
    script_dir = Path(__file__).resolve().parent
    feeds_path = args.feeds or (script_dir / "feeds.json")

    if args.date:
        target = date.fromisoformat(args.date)
    else:
        target = datetime.now(TZ_SH).date()

    feeds_raw = json.loads(feeds_path.read_text(encoding="utf-8"))
    if not isinstance(feeds_raw, list):
        print("Error: feeds.json must be a JSON array.", file=sys.stderr)
        return 1
    feed_list = flatten_feeds_config(feeds_raw)
    all_entries: list[dict] = []
    errors: list[str] = []
    usable_sources: list[str] = []
    unusable_sources: list[str] = []

    for feed in feed_list:
        name = feed.get("name") or urlparse(feed.get("url", "")).netloc or "unknown"
        url = feed.get("url")
        if not url:
            unusable_sources.append(f"{name}: missing_url")
            continue
        try:
            data = fetch_xml(url)
            parsed_items = parse_feed_items(data, name)
            matched_items = 0
            for item in parsed_items:
                d = date_in_shanghai(item.get("published"))
                if d == target:
                    all_entries.append(item)
                    matched_items += 1
            usable_sources.append(f"{name}: ok (parsed={len(parsed_items)}, matched={matched_items})")
        except TimeoutError as ex:
            unusable_sources.append(f"{name}: timeout ({ex})")
            errors.append(f"{name} ({url}): {ex}")
        except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError, OSError, ValueError) as ex:
            unusable_sources.append(f"{name}: failed ({type(ex).__name__}: {ex})")
            errors.append(f"{name} ({url}): {ex}")

    all_entries = dedupe(all_entries)
    all_entries.sort(key=lambda e: (e.get("published") or datetime.min.replace(tzinfo=timezone.utc)))
    cap = max(0, int(args.max_per_category))
    all_entries = select_top_per_display_type(all_entries, cap)

    out_file = repo_root / "temp" / target.isoformat() / "rss_articles.md"
    write_markdown(out_file, all_entries)

    print(
        f"Wrote {out_file} ({len(all_entries)} items, "
        f"max {cap} per display type, ranked by quality_score)."
    )
    print(
        "Source summary:"
        f" usable={len(usable_sources)}"
        f", unusable={len(unusable_sources)}"
    )
    print("Usable sources:")
    for item in usable_sources:
        print(f"  - {item}")
    print("Unusable sources:")
    for item in unusable_sources:
        print(f"  - {item}")
    if errors:
        print("Warnings:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
