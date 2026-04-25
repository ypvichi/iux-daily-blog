"""
Cursor 中文博客列表: https://cursor.com/cn/blog

列表页含顶部「精选」大卡（``article.h-full``）与下方 ``blog-directory__row`` 目录行；
``<time dateTime>`` 为 UTC ISO8601。正文页主体在 ``div.prose.prose--blog`` 内。
"""

from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin

_H_FULL = re.compile(
    r'(?is)<article class="h-full">\s*<a[^>]*href="(/cn/blog/[a-z0-9\-]+)"[^>]*>(.*?)</a>\s*</article>',
)
_DIR_ROW = re.compile(
    r'(?is)<a class="blog-directory__row[^"]*"[^>]*href="(/cn/blog/[a-z0-9\-]+)"[^>]*>\s*'
    r'<article[^>]*class="grid[^"]*"[^>]*>(.*?)</article>\s*</a>',
)
_TIME_DT = re.compile(r'<time[^>]*dateTime="([^"]+)"')
_TITLE_FEATURE = re.compile(
    r'(?is)<p class="[^"]*\btype-md-lg\b[^"]*"[^>]*>(.*?)</p>',
)
_SUMMARY_FEATURE = re.compile(
    r'(?is)<p class="[^"]*\btext-theme-text-sec\b[^"]*"[^>]*>(.*?)</p>',
)
_TITLE_ROW = re.compile(
    r'(?is)<p class="[^"]*\btext-theme-text\b[^"]*\btext-pretty\b[^"]*"[^>]*>(.*?)</p>',
)
_PROSE_OPEN = re.compile(
    r'(?is)<div\s+class="[^"]*\bprose\b[^"]*\bprose--blog\b[^"]*"[^>]*>',
)
_H1 = re.compile(r'(?is)<h1 class="[^"]*\btype-lg\b[^"]*"[^>]*>(.*?)</h1>')
_H1_LOOSE = re.compile(r"(?is)<h1[^>]*>(.*?)</h1>")
_LEAD = re.compile(
    r'(?is)<p class="[^"]*\btype-md-sm\b[^"]*"[^>]*>(.*?)</p>',
)
_OG_DESC = re.compile(
    r'(?is)<meta\s+property="og:description"\s+content="([^"]+)"',
)


def _strip_tags(html: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?is)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t)).strip()


def _parse_published(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _extract_prose_blog_inner(html: str) -> str:
    m = _PROSE_OPEN.search(html)
    if not m:
        return ""
    start = m.end()
    depth = 1
    pos = start
    tag_re = re.compile(r"(?i)</div>|<div\b[^>]*>")
    while depth > 0:
        tm = tag_re.search(html, pos)
        if not tm:
            return ""
        tok = tm.group(0)
        if tok.lower().startswith("</"):
            depth -= 1
            if depth == 0:
                return html[start : tm.start()]
        else:
            depth += 1
        pos = tm.end()
    return ""


def parse_feed(listing_html: str, *, source_name: str, listing_url: str = "") -> list[dict]:
    """
    解析列表页条目；``published`` 为 ``dateTime`` 对应的 timezone-aware datetime，
    由主脚本按上海自然日筛选。

    字段: source, title, link, published, summary。
    """
    if not listing_html or "/cn/blog/" not in listing_html:
        return []

    base_root = "https://cursor.com"
    by_path: dict[str, dict[str, Any]] = {}

    def upsert(path: str, published: datetime | None, title: str, summary: str) -> None:
        if not path.startswith("/cn/blog/") or len(path) <= len("/cn/blog/"):
            return
        if published is None:
            return
        title_t = _strip_tags(title) or "(无标题)"
        sum_t = _strip_tags(summary)[:500]
        if not sum_t:
            sum_t = title_t[:500]
        link = urljoin(base_root, path)
        prev = by_path.get(path)
        row = {
            "source": source_name,
            "title": title_t,
            "link": link,
            "published": published,
            "summary": sum_t,
        }
        if prev is None:
            by_path[path] = row
            return
        if len(sum_t) > len(prev.get("summary") or ""):
            by_path[path] = row

    for m in _H_FULL.finditer(listing_html):
        path, inner = m.group(1), m.group(2) or ""
        tm = _TIME_DT.search(inner)
        if not tm:
            continue
        pub = _parse_published(tm.group(1))
        t_m = _TITLE_FEATURE.search(inner)
        s_m = _SUMMARY_FEATURE.search(inner)
        title_html = t_m.group(1) if t_m else ""
        summary_html = s_m.group(1) if s_m else ""
        upsert(path, pub, title_html, summary_html)

    for m in _DIR_ROW.finditer(listing_html):
        path, inner = m.group(1), m.group(2) or ""
        tm = _TIME_DT.search(inner)
        if not tm:
            continue
        pub = _parse_published(tm.group(1))
        t_m = _TITLE_ROW.search(inner)
        title_html = t_m.group(1) if t_m else ""
        upsert(path, pub, title_html, "")

    return list(by_path.values())


class CursorBlogRender:
    """单篇博客页：补充标题、导语摘要、正文区 HTML 供配图解析。"""

    def enrich(self, html: str, link: str, entry: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        low = (link or "").lower()
        if "cursor.com" not in low or "/cn/blog/" not in low:
            return out
        if low.rstrip("/").endswith("/cn/blog"):
            return out

        m = _H1.search(html) or _H1_LOOSE.search(html)
        if m:
            t = _strip_tags(m.group(1) or "")
            if t:
                out["title"] = t

        lm = _LEAD.search(html)
        if lm:
            s = _strip_tags(lm.group(1) or "")
            if len(s) > 40:
                out["summary"] = s[:2000]

        if not out.get("summary"):
            om = _OG_DESC.search(html)
            if om:
                out["summary"] = _strip_tags(om.group(1) or "")[:2000]

        frag = _extract_prose_blog_inner(html)
        if frag:
            out["html_fragment_for_media"] = frag
        return out
