"""
Build Fast with AI 博客列表: https://www.buildfastwithai.com/blogs/all?category=4

Next.js 页内每条为 ``<a class="group flex flex-col" href="/blogs/...">`` 卡片:
分类 ``span``、标题 ``h3``、日期 ``<p class="text-sm text-muted-foreground mt-auto">Month D, YYYY</p>``（英文月名）。
主脚本按上海自然日筛选；``published`` 取该日 12:00（Asia/Shanghai）。

单篇 enrich：``h1``、``og:description``，正文图自 ``div`` 含 ``prose prose-lg`` 区块（与 ``articleSelector: main`` 二选一、优先本模块片段）。
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

try:
    _TZ_SH = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    _TZ_SH = timezone(timedelta(hours=8))

_BASE = "https://www.buildfastwithai.com"

_CARD = re.compile(
    r'(?is)<a class="group flex flex-col" href="(/blogs/(?!all)[a-z0-9][a-z0-9\-]*)">(.*?)</a>',
)

_H3 = re.compile(r'(?is)<h3 class="[^"]*"[^>]*>(.*?)</h3>')
_DATE_P = re.compile(
    r'(?is)<p class="text-sm text-muted-foreground mt-auto">([^<]+)</p>',
)
_CAT_SPAN = re.compile(
    r'(?is)<span class="inline-block w-fit[^"]*"[^>]*>([^<]+)</span>',
)
_IMG_ALT = re.compile(
    r'(?is)<img[^>]*alt="([^"]*)"',
    re.I,
)

_OG_DESC = re.compile(
    r'(?is)<meta\s+property="og:description"\s+content="([^"]+)"',
)
_H1 = re.compile(r'(?is)<h1 class="[^"]*"[^>]*>(.*?)</h1>')
_H1_LOOSE = re.compile(r"(?is)<h1[^>]*>(.*?)</h1>")

_PROSE_OPEN = re.compile(
    r'(?is)<div\s+class="[^"]*\bprose\b[^"]*\bprose-lg\b[^"]*"[^>]*>',
)


def _strip_tags(html: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?is)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t)).strip()


def _parse_mdy_english(s: str) -> date | None:
    raw = (s or "").strip()
    if not raw:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _extract_prose_inner(html: str) -> str:
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


def parse_feed(
    listing_html: str,
    *,
    source_name: str,
    listing_url: str = "",
) -> list[dict[str, Any]]:
    """
    解析 ``/blogs/all`` 类列表页。字段: source, title, link, published, summary。
    """
    if not listing_html or "group flex flex-col" not in listing_html:
        return []

    base = _BASE
    lu = (listing_url or "").strip()
    if lu and "buildfastwithai.com" in lu.lower():
        p = urlparse(lu)
        if p.scheme and p.netloc:
            base = f"{p.scheme}://{p.netloc}"

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _CARD.finditer(listing_html):
        path, inner = m.group(1), m.group(2) or ""
        if not path.startswith("/blogs/") or path.rstrip("/") == "/blogs/all":
            continue
        h3m = _H3.search(inner)
        title = _strip_tags(h3m.group(1) if h3m else "") or ""
        if not title:
            am = _IMG_ALT.search(inner)
            title = unescape((am.group(1) or "").strip()) if am else ""
        if not title:
            title = "(无标题)"

        dm = _DATE_P.search(inner)
        d_raw = (dm.group(1) or "").strip() if dm else ""
        pub_d = _parse_mdy_english(d_raw)
        if pub_d is None:
            continue

        published = datetime.combine(pub_d, time(12, 0), tzinfo=_TZ_SH)
        cat_m = _CAT_SPAN.search(inner)
        cat = _strip_tags(cat_m.group(1) or "") if cat_m else ""
        if cat and cat.lower() not in title.lower():
            summary = f"{cat} — {title}"[:500]
        else:
            summary = title[:500]

        link = urljoin(base + "/", path.lstrip("/"))
        key = path
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "source": source_name,
                "title": title,
                "link": link,
                "published": published,
                "summary": summary,
            }
        )

    return items


class BuildFastWithaAiRender:
    """单篇博客: 标题、摘要、``prose`` 区内 HTML 供配图解析。"""

    def enrich(self, html: str, link: str, entry: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        low = (link or "").lower()
        if "buildfastwithai.com" not in low or "/blogs/" not in low:
            return out
        path = urlparse(link).path or ""
        if path.rstrip("/").endswith("/blogs/all") or path.rstrip("/") == "/blogs":
            return out

        m = _H1.search(html) or _H1_LOOSE.search(html)
        if m:
            t = _strip_tags(m.group(1) or "")
            if t:
                out["title"] = t

        if not out.get("title") and entry.get("title"):
            out["title"] = str(entry["title"]).strip()

        om = _OG_DESC.search(html)
        if om:
            s = _strip_tags(om.group(1) or "")
            if s:
                out["summary"] = s[:2000]

        frag = _extract_prose_inner(html)
        if frag:
            out["html_fragment_for_media"] = frag
        return out

    @classmethod
    def expand_html_feed(
        cls,
        html: str,
        feed_url: str,
        source_name: str,
        feed_priority: int,
        target: date,
    ) -> list[dict[str, Any]] | None:
        rows = parse_feed(html, source_name=source_name, listing_url=feed_url)
        out = [r for r in rows if r.get("published") and r["published"].date() == target]
        for r in out:
            r["feed_priority"] = feed_priority
        return out or None
