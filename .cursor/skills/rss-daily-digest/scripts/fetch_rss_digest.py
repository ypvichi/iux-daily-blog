#!/usr/bin/env python3
"""
Fetch multiple RSS/Atom feeds, keep entries whose published time falls on the
target calendar day (Asia/Shanghai), write markdown to temp/YYYY-MM-DD/rss_articles.md.

Per display type (classify_by_title, same as the written 类型 field), keep at
most N entries; within each type, pick by feed priority (feeds.json `priority`,
higher first), then quality_score, then sort by time.

Optionally fetches each article URL and extracts up to two images and two
videos from the main article content (see ARTICLE_MAX_IMAGES/ARTICLE_MAX_VIDEOS;
use --skip-body-media to disable). When body media is on, each URL is probed
with a short HTTP GET (Range first; image magic / Content-Type) and unreachable
or HTML-error responses are dropped from rss_articles.md. Use
--skip-media-url-check to keep legacy behavior (faster, may include dead links).

feeds.json 可为某项设置 "render": "ModuleBaseName"，对应本脚本同目录下
render/ModuleBaseName.py：须实现 parse_feed(listing_html, *, source_name,
listing_url="") -> list[dict]（字段与 RSS 条目一致）。可选在同名类 ModuleBaseName
上实现 enrich(html, link, entry) -> dict，对单页再提取 title/summary/
html_fragment_for_media；条目可设 feed_render 以启用该类。条目可含 body_fetch_url：
正文配图抓取使用该 URL 而非 link。
"""

from __future__ import annotations

import argparse
import importlib.util
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
# 正文内媒体：自每个文章页各取最多 N 个（优先 <article>/<main> 内顺序）。
ARTICLE_MAX_IMAGES = 2
ARTICLE_MAX_VIDEOS = 2
# 写入前探测图片/直链视频是否可拉取；与爬文章页超时分立，避免单条过慢。
MEDIA_CHECK_TIMEOUT = 6.0
MEDIA_SNIFF_BYTES = 2048

# 八类归纳：要闻、模型发布、开发生态、产品应用、技术与洞察、行业生态、前瞻与传闻、其他。
# 展示顺序；分类冲突时用 _CAT_PRIORITY 决胜（特异性优先）。
CATEGORIES: tuple[str, ...] = (
    "要闻",
    "模型发布",
    "设计生态",
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
    "设计生态",
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
    "设计生态",
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
    "设计生态",
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


def extract_article_html_fragment(full_html: str) -> str:
    """
    优先截取正文区域 HTML，用于在正文中取图/视频（避免导航栏等无关图）。
    顺序：article 内 > main 内 > body 内 > 去掉 head 后的全文。
    """
    if not full_html:
        return ""
    h = re.sub(r"(?is)<head[^>]*>.*?</head>", " ", full_html)
    m = re.search(r"(?is)<article[^>]*>(.*)</article>", h, re.DOTALL)
    if m:
        return m.group(1) or ""
    m = re.search(r"(?is)<main[^>]*>(.*)</main>", h, re.DOTALL)
    if m:
        return m.group(1) or ""
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", h, re.DOTALL)
    if m:
        return m.group(1) or ""
    return h


def html_to_visible_text(html: str) -> str:
    """Strip tags roughly; keep readable body text for excerpt/summary."""
    if not html:
        return ""
    # Remove common boilerplate blocks (best-effort, regex)
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", html)
    # Prefer <article> or <main> if present
    art = re.search(r"(?is)<article[^>]*>(.*?)</article>", html, re.DOTALL)
    if art:
        html = art.group(1)
    else:
        main = re.search(r"(?is)<main[^>]*>(.*?)</main>", html, re.DOTALL)
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


def _first_url_from_srcset(srcset: str | None) -> str | None:
    if not srcset or not srcset.strip():
        return None
    part = srcset.split(",")[0].strip().split()
    if part:
        return part[0].strip() or None
    return None


def _img_url_from_attrs(attrs: dict[str, str]) -> str | None:
    """Prefer real image URL; many站点用 data-src / srcset 懒加载。"""
    low_keys = {k.lower(): v for k, v in attrs.items()}
    for key in (
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-actualsrc",
        "data-img",
    ):
        v = (low_keys.get(key) or "").strip()
        if v and not v.startswith(("data:", "blob:", "about:")):
            return v
    ss = _first_url_from_srcset(low_keys.get("srcset"))
    if ss and not ss.startswith(("data:", "blob:")):
        return ss
    return None


def _bad_image_url(abs_u: str) -> bool:
    """Heuristic: 排除追踪像素、站头/导航、二维码等常见非正文图。"""
    low = abs_u.lower()
    if any(
        x in low
        for x in (
            "pixel",
            "tracking",
            "spacer",
            "1x1",
            "beacon",
            "analytics",
            "favicon",
            "logo.svg",
            "/icon",
            "qrcode",
            "qr_code",
            "ewm",  # 部分站点
            "common-images",  # 如早报/栏目配图条
            "imagesnew/head",  # 量子位等主题站头
            "avatar",
            "gravatar",
        )
    ):
        return True
    if re.search(
        r"(?:head|header|nav|logo|ad-|ads-|banner|sponsor|share-icon)[^/]*\.(?:png|gif|jpe?g|webp)(?:\?|$)",
        low,
    ):
        return True
    if re.search(r"(?:^|/)(?:loader|loading|placeholder|blank)\.(?:png|gif|webp?)(?:\?|$)", low):
        return True
    return False


def _embed_video_url(abs_u: str) -> bool:
    low = abs_u.lower()
    if any(
        h in low
        for h in (
            "youtube.com/embed",
            "youtube-nocookie.com",
            "youtu.be/",
            "vimeo.com",
            "player.vimeo.com",
            "bilibili.com",
            "bilivideo.com",
            "v.qq.com",
            "youku.com",
            "iqiyi.com",
        )
    ):
        return True
    if re.search(r"\.(?:m3u8|mp4|webm)(?:\?|$)", low):
        return True
    return False


def _chunk_looks_like_html(chunk: bytes) -> bool:
    s = chunk.lstrip()[:32].lower()
    return s.startswith(b"<!") or s.startswith(b"<ht") or s.startswith(b"<?xml")


def _chunk_looks_like_raster_image(chunk: bytes) -> bool:
    if len(chunk) < 12:
        return False
    if chunk[:3] == b"\xff\xd8\xff":
        return True
    if chunk.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if chunk[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if len(chunk) >= 12 and chunk[:4] == b"RIFF" and chunk[8:12] == b"WEBP":
        return True
    return False


def _http_sniff_get(url: str, referer: str, *, with_range: bool) -> tuple[int, str, bytes] | None:
    """
    GET 前 MEDIA_SNIFF_BYTES 字节；带 Range 失败（416 等）时由调用方再试全量。
    成功返回 (status, content_type_lower, body_prefix)；网络/非 HTTP 错误返回 None。
    """
    headers: dict[str, str] = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    if with_range:
        headers["Range"] = f"bytes=0-{MEDIA_SNIFF_BYTES - 1}"
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=MEDIA_CHECK_TIMEOUT) as resp:  # noqa: S310
            code = resp.getcode() or 0
            ct = (resp.headers.get("Content-Type") or "").lower()
            body = resp.read(MEDIA_SNIFF_BYTES)
    except urllib.error.HTTPError as e:
        if e.code == 416 and with_range:
            return None
        if e.code in (404, 410):
            return (e.code, (e.headers.get("Content-Type") or "").lower() if e.headers else "", b"")
        if e.code and e.code >= 400 and e.code != 416:
            try:
                raw = (e.read() or b"")[:MEDIA_SNIFF_BYTES] if e.fp else b""
            except (OSError, ValueError):
                raw = b""
            return (
                e.code,
                (e.headers.get("Content-Type") or "").lower() if e.headers else "",
                raw,
            )
        return None
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None
    return (code, ct, body)


def verify_image_url_reachable(url: str, referer: str) -> bool:
    """
    仅当能拿到「像图片」的响应时才为 True；404、HTML 整页、断链为 False。
    使用文章 link 作 Referer，以减轻部分图床防盗链对脚本 UA 的 403（与浏览器行为接近）。
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        return False
    for with_range in (True, False):
        got = _http_sniff_get(url, referer, with_range=with_range)
        if got is None:
            if with_range:
                continue
            return False
        code, ct, chunk = got
        if code in (404, 410) or code >= 500:
            return False
        if not (200 <= code < 300):
            return False
        if not chunk:
            return False
        if "text/html" in ct and "image" not in ct and "xml" not in ct:
            if _chunk_looks_like_html(chunk):
                return False
        if ct and (ct.startswith("image/") or "image/svg" in ct):
            if "text/html" in ct and _chunk_looks_like_html(chunk) and not _chunk_looks_like_raster_image(chunk):
                return False
            return True
        if _chunk_looks_like_html(chunk) and not _chunk_looks_like_raster_image(chunk):
            return False
        if _chunk_looks_like_raster_image(chunk):
            return True
        s = chunk.lstrip()
        if s.startswith(b"<svg"):
            return True
        return False
    return False


def verify_video_url_reachable(url: str, referer: str) -> bool:
    """
    嵌入类（YouTube 等）用短 GET 看是否 2xx；直链 m3u8/mp4/webm 做 ftyp/WEBM/ m3u8 嗅探。
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        return False
    low = url.lower()
    is_direct = re.search(r"\.(?:m3u8|mp4|webm|ogv|mov)(?:\?|#|$)", low) is not None
    if _embed_video_url(url) and not is_direct:
        g = _http_sniff_get(url, referer, with_range=True)
        if g is None:
            g = _http_sniff_get(url, referer, with_range=False)
        if g is None:
            return False
        code, _ct, _chunk = g
        if code in (404, 410) or code >= 500:
            return False
        return 200 <= code < 300
    for with_range in (True, False):
        got = _http_sniff_get(url, referer, with_range=with_range)
        if got is None:
            if with_range:
                continue
            return False
        code, ct, chunk = got
        if code in (404, 410) or code >= 500:
            return False
        if not (200 <= code < 300):
            return False
        if not chunk:
            if with_range:
                continue
            return False
        ctn = (ct or "").lower()
        if "text/html" in ctn and not is_direct and _chunk_looks_like_html(chunk):
            return False
        if chunk[:4] == b"\x1a\x45\xdf\xa3" or (len(chunk) >= 8 and chunk[4:8] == b"ftyp"):
            return True
        if b"#EXTM3U" in chunk[:32] or chunk.lstrip()[:7].lower() == b"#extm3u":
            return True
        if is_direct and (
            "video" in ctn
            or "mpegurl" in ctn
            or "x-mpeg" in ctn
            or "octet-stream" in ctn
        ) and (not _chunk_looks_like_html(chunk)):
            return True
        if is_direct and b"#EXT" in chunk[:32]:
            return True
    return False


def filter_reachable_body_media(
    imgs: list[str],
    vids: list[str],
    referer: str,
) -> tuple[list[str], list[str]]:
    """保序；仅保留 HTTP 可验证的图/视频条（各最多 N 由上游已截断）。"""
    out_i = [u for u in imgs if verify_image_url_reachable(u, referer)]
    out_v = [u for u in vids if verify_video_url_reachable(u, referer)]
    return out_i, out_v


class _BodyMediaParser(HTMLParser):
    """自正文顺序收集 <img>、<video>/<source>、嵌入视频 <iframe>。"""

    _SKIP = frozenset({"script", "style", "noscript", "template", "head"})
    # 仅对语义化标签成对跳过节选（避免 class 与闭合标签难配对）
    _SKIP_BOILERPLATE = frozenset({"header", "nav", "aside", "footer"})

    def __init__(self, base_url: str, max_images: int, max_videos: int) -> None:
        super().__init__(convert_charrefs=True)
        self._base = base_url
        self._max_img = max_images
        self._max_vid = max_videos
        self.images: list[str] = []
        self.videos: list[str] = []
        self._seen_img: set[str] = set()
        self._seen_vid: set[str] = set()
        self._skip_depth = 0
        self._boiler_depth = 0
        self._svg_depth = 0
        self._video_depth = 0

    def _resolve(self, raw: str | None) -> str | None:
        if not raw or not raw.strip():
            return None
        u = urljoin(self._base, raw.strip())
        if not u.startswith(("http://", "https://")):
            return None
        return u

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        t = tag.lower()
        ad = {a[0].lower(): (a[1] or "") for a in attrs}
        if t in self._SKIP:
            self._skip_depth += 1
        if t == "svg":
            self._svg_depth += 1
        if t in self._SKIP_BOILERPLATE:
            self._boiler_depth += 1
        if self._skip_depth > 0 or self._svg_depth > 0 or self._boiler_depth > 0:
            return
        if t == "video":
            self._video_depth += 1
            if len(self.videos) < self._max_vid:
                raw = (ad.get("src") or ad.get("data-src") or "").strip()
                u = self._resolve(raw)
                if u and u not in self._seen_vid:
                    low = u.lower()
                    if _embed_video_url(u) or re.search(
                        r"\.(?:mp4|webm|m3u8|ogv)(?:\?|$)", low
                    ):
                        self._seen_vid.add(u)
                        self.videos.append(u)
        elif t == "source" and self._video_depth > 0 and len(self.videos) < self._max_vid:
            u = self._resolve((ad.get("src") or "").strip())
            if u and u not in self._seen_vid:
                self._seen_vid.add(u)
                self.videos.append(u)
        elif t == "iframe" and len(self.videos) < self._max_vid:
            u = self._resolve((ad.get("src") or ad.get("data-src") or "").strip())
            if u and _embed_video_url(u) and u not in self._seen_vid:
                self._seen_vid.add(u)
                self.videos.append(u)
        elif t == "img" and len(self.images) < self._max_img:
            raw = _img_url_from_attrs(ad)
            u = self._resolve(raw)
            if u and not _bad_image_url(u) and u not in self._seen_img:
                self._seen_img.add(u)
                self.images.append(u)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        if t in self._SKIP_BOILERPLATE and self._boiler_depth > 0:
            self._boiler_depth -= 1
        if t == "svg" and self._svg_depth > 0:
            self._svg_depth -= 1
        if t == "video" and self._video_depth > 0:
            self._video_depth -= 1


def extract_body_media(html_fragment: str, base_url: str) -> tuple[list[str], list[str]]:
    """自正文 HTML 片段解析图片、视频 URL（各最多 N 条，顺序为文中出现顺序）。"""
    if not html_fragment or not base_url:
        return [], []
    p = _BodyMediaParser(base_url, ARTICLE_MAX_IMAGES, ARTICLE_MAX_VIDEOS)
    try:
        p.feed(html_fragment)
        p.close()
    except Exception:  # noqa: BLE001 — 容错
        return [], []
    return p.images[: ARTICLE_MAX_IMAGES], p.videos[: ARTICLE_MAX_VIDEOS]


def enrich_entry_with_body(entry: dict, *, verify_media_urls: bool = True) -> dict:
    """Fetch link HTML，追加 body_text、core_summary、正文内图片/视频（best-effort）。"""
    link = (entry.get("link") or "").strip()
    body_url = (entry.get("body_fetch_url") or link).strip()
    out = dict(entry)
    out["body_error"] = None
    out["body_images"] = []
    out["body_videos"] = []
    html = fetch_html_text(body_url)
    if html is None:
        out["body_error"] = "fetch_failed"
        return out

    extract: dict = {}
    fr = (entry.get("feed_render") or "").strip()
    if fr:
        try:
            mod = load_render_module(fr)
            cls = getattr(mod, fr, None)
            if isinstance(cls, type):
                inst = cls()
                if hasattr(inst, "enrich"):
                    raw = inst.enrich(html, link, out)
                    if isinstance(raw, dict):
                        extract = raw
        except (FileNotFoundError, ImportError, OSError, TypeError, ValueError):
            extract = {}
        except Exception:  # noqa: BLE001 — 单站 enrich 失败则回退通用逻辑
            extract = {}

    fragment = (extract.get("html_fragment_for_media") or "").strip() or extract_article_html_fragment(
        html
    )
    if extract.get("title"):
        out["title"] = str(extract["title"]).strip()
    if extract.get("summary"):
        out["summary"] = str(extract["summary"]).strip()[:500]

    body_text = html_to_visible_text(html)
    out["body_text"] = body_text
    if extract.get("summary"):
        out["core_summary"] = extractive_core_summary(str(extract["summary"]))
    else:
        out["core_summary"] = extractive_core_summary(body_text)
    imgs, vids = extract_body_media(fragment, body_url)
    if verify_media_urls and (imgs or vids):
        imgs, vids = filter_reachable_body_media(imgs, vids, body_url)
    out["body_images"] = imgs
    out["body_videos"] = vids
    # 兼容旧字段名
    out["core_images"] = imgs
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


def _feed_priority_value(raw: object) -> int:
    """Non-negative int; larger = higher priority. Invalid/missing → 0."""
    if raw is None or isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return max(0, raw)
    if isinstance(raw, float):
        return max(0, int(raw))
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return 0
        try:
            return max(0, int(s, 10))
        except ValueError:
            return 0
    return 0


def dedupe(entries: list[dict]) -> list[dict]:
    """Drop duplicate (link, title); keep the copy with higher feed_priority, then quality."""
    best: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for e in entries:
        key = (e.get("link") or "", e.get("title") or "")
        if key not in best:
            best[key] = e
            order.append(key)
            continue
        old = best[key]
        pe = _feed_priority_value(e.get("feed_priority"))
        po = _feed_priority_value(old.get("feed_priority"))
        if pe > po:
            best[key] = e
        elif pe == po and quality_score_entry(e) > quality_score_entry(old):
            best[key] = e
    return [best[k] for k in order]


def select_top_per_display_type(entries: list[dict], max_per: int) -> list[dict]:
    """
    与输出字段「类型」一致（仅 `classify_by_title`），每类最多保留 max_per 条；
    同类内按 feed_priority（越大越优先）、quality_score_entry 降序择优，再按发布时间升序输出整篇列表。
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
                -_feed_priority_value(e.get("feed_priority")),
                -quality_score_entry(e),
                -(e.get("published") or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
            )
        )
        selected.extend(group[:max_per])

    selected.sort(
        key=lambda e: e.get("published") or datetime.min.replace(tzinfo=timezone.utc)
    )
    return selected


def _format_media_line(label: str, urls: list[str] | None) -> str:
    u = [x.strip() for x in (urls or []) if (x or "").strip()]
    if not u:
        return f"{label}: （无）"
    return f"{label}: " + "；".join(_safe_text(x) for x in u)


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
        raw_im = e.get("body_images")
        imgs: list[str] = [str(x) for x in (raw_im if isinstance(raw_im, list) else []) if x]
        if not imgs:
            ci = e.get("core_images")
            if isinstance(ci, list):
                imgs = [str(x) for x in ci if x]
        raw_v = e.get("body_videos")
        vids: list[str] = raw_v if isinstance(raw_v, list) else []

        lines.append(f"【{i}】")
        lines.append(f"标题: {title}")
        lines.append(f"类型: {classify_by_title(e.get('title'))}")
        lines.append(f"来源: {source}")
        lines.append(f"日期: {published_str}")
        lines.append(f"链接: {link}")
        lines.append(f"摘要: {summary}")
        lines.append(_format_media_line("图片", imgs))
        lines.append(_format_media_line("视频", vids))
        lines.append("--------------------------------------------------------------")

    if lines:
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def flatten_feeds_config(feeds_data: list) -> list[dict]:
    """
    支持两种 feeds.json 形态：
    - 嵌套：顶层为各类别 { "name", "feeds": [ { "name", "url", "priority"? }, ... ] }，展平为单列表拉取。
    - 旧版：顶层直接为 { "name", "url", "priority"? }。
    priority 为可选非负整数，数值越大该源越优先（抓取顺序与同类截断择优均考虑）。
    """
    out: list[dict] = []
    for item in feeds_data:
        if not isinstance(item, dict):
            continue
        if item.get("url"):
            n = (item.get("name") or urlparse(str(item.get("url", ""))).netloc or "unknown").strip()
            row: dict = {"name": n, "url": str(item["url"]).strip()}
            p = _feed_priority_value(item.get("priority"))
            if p:
                row["priority"] = p
            rk = item.get("render")
            if rk:
                row["render"] = str(rk).strip()
            out.append(row)
            continue
        for sub in item.get("feeds") or []:
            if not isinstance(sub, dict):
                continue
            u = sub.get("url")
            if not u:
                continue
            n = (sub.get("name") or item.get("name") or urlparse(str(u)).netloc or "unknown").strip()
            row = {"name": n, "url": str(u).strip()}
            p = _feed_priority_value(sub.get("priority"))
            if p:
                row["priority"] = p
            rk = sub.get("render")
            if rk:
                row["render"] = str(rk).strip()
            out.append(row)
    return out


def load_render_module(base_name: str):
    """加载 scripts/render/<base_name>.py，须实现 parse_feed(listing_html, *, source_name, listing_url='')。"""
    script_dir = Path(__file__).resolve().parent
    path = script_dir / "render" / f"{base_name}.py"
    if not path.is_file():
        raise FileNotFoundError(str(path))
    mod_name = f"rss_digest_render_{base_name}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path.name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
        help=f"每类「类型」最多保留条数，同类内按 feeds.json 的 priority（高优先）、再按质量分择优（默认 {MAX_ITEMS_PER_CATEGORY}）",
    )
    parser.add_argument(
        "--skip-body-media",
        action="store_true",
        help="不逐条打开链接抓取正文内图片/视频（仅 RSS 摘要，生成更快）",
    )
    parser.add_argument(
        "--skip-media-url-check",
        action="store_true",
        help="不探测图片/视频 URL 是否可 HTTP 访问（与 --skip-body-media 互斥；可能写入失效链接，生成更快）",
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
    feed_list.sort(
        key=lambda f: (
            -_feed_priority_value(f.get("priority")),
            (f.get("name") or "").lower(),
        )
    )
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
            render_key = (feed.get("render") or "").strip()
            if render_key:
                rmod = load_render_module(render_key)
                parse_fn = getattr(rmod, "parse_feed", None)
                if not callable(parse_fn):
                    raise TypeError(f"render {render_key!r} missing parse_feed()")
                listing_html = fetch_html_text(url)
                if listing_html is None:
                    raise OSError("listing fetch failed (HTML)")
                parsed_items = parse_fn(listing_html, source_name=name, listing_url=url)
            else:
                data = fetch_xml(url)
                parsed_items = parse_feed_items(data, name)
            matched_items = 0
            prio = _feed_priority_value(feed.get("priority"))
            for item in parsed_items:
                d = date_in_shanghai(item.get("published"))
                if d == target:
                    row = dict(item)
                    row["feed_priority"] = prio
                    all_entries.append(row)
                    matched_items += 1
            usable_sources.append(f"{name}: ok (parsed={len(parsed_items)}, matched={matched_items})")
        except TimeoutError as ex:
            unusable_sources.append(f"{name}: timeout ({ex})")
            errors.append(f"{name} ({url}): {ex}")
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            ET.ParseError,
            OSError,
            ValueError,
            TypeError,
            FileNotFoundError,
            ImportError,
        ) as ex:
            unusable_sources.append(f"{name}: failed ({type(ex).__name__}: {ex})")
            errors.append(f"{name} ({url}): {ex}")

    all_entries = dedupe(all_entries)
    all_entries.sort(key=lambda e: (e.get("published") or datetime.min.replace(tzinfo=timezone.utc)))
    cap = max(0, int(args.max_per_category))
    all_entries = select_top_per_display_type(all_entries, cap)

    check_urls = (not args.skip_body_media) and (not args.skip_media_url_check)
    if not args.skip_body_media:
        all_entries = [enrich_entry_with_body(e, verify_media_urls=check_urls) for e in all_entries]

    out_file = repo_root / "temp" / target.isoformat() / "rss_articles.md"
    write_markdown(out_file, all_entries)

    extra = ""
    if not args.skip_body_media:
        extra = f" body_media=on (<= {ARTICLE_MAX_IMAGES} imgs / {ARTICLE_MAX_VIDEOS} videos per item)"
        if check_urls:
            extra += " media_url_check=on"
        else:
            extra += f" media_url_check=off{(' (--skip-media-url-check)' if args.skip_media_url_check else '')}"
    else:
        extra = " body_media=off (--skip-body-media)"
    print(
        f"Wrote {out_file} ({len(all_entries)} items, "
        f"max {cap} per display type, ranked by feed priority then quality_score).{extra}"
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
