"""
Claude 官方博客列表: https://claude.com/blog

Webflow 页面：主网格中每条在 ``data-cta="Blog page"`` 的 ``clickable_link`` 上给出
``href`` 与 ``data-cta-copy``；日期在条目前方的 ``fs-list-field="date"`` 或
轮播/精选区的 ``u-foreground-tertiary`` 英文短日期（``Month D, YYYY``）。
``published`` 取该日 12:00（Asia/Shanghai），与主脚本的上海自然日筛选一致。

单篇：``og:title`` / ``og:description``，正文自首个非隐藏的 ``u-rich-text-blog w-richtext`` 区块
（站点点内无 ``<article>``，不依赖 ``articleSelector: article``）。
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

_BASE = "https://claude.com"

# 与 <div class="...u-rich-text-blog...w-richtext" 或类名顺序互换
_RICHTEXT_OPEN = re.compile(
    r'(?is)<div\b[^>]*\bu-rich-text-blog\b[^>]*\bw-richtext\b[^>]*>',
)
_RICHTEXT_OPEN_ALT = re.compile(
    r'(?is)<div\b[^>]*\bw-richtext\b[^>]*\bu-rich-text-blog\b[^>]*>',
)

def _og_meta(html: str, prop: str) -> str:
    """Webflow 常见 ``content=`` 在 ``property=`` 之前，两种顺序都试。"""
    p = re.escape(prop)
    for pat in (
        rf'(?is)<meta\s+content="([^"]+)"[^>]*\bproperty="{p}"',
        rf'(?is)<meta\s+property="{p}"[^>]*\bcontent="([^"]+)"',
    ):
        m = re.search(pat, html)
        if m:
            return unescape((m.group(1) or "").strip())
    return ""


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


def _is_post_path(path: str) -> bool:
    """仅 ``/blog/{slug}``，排除 ``/blog/category/...``。"""
    p = (path or "").split("?", 1)[0].strip()
    if not p.startswith("/"):
        p = "/" + p
    parts = [x for x in p.rstrip("/").split("/") if x]
    if len(parts) != 2 or parts[0].lower() != "blog":
        return False
    if parts[1].lower() == "category":
        return False
    return bool(re.match(r"^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?$", parts[1], re.I))


def _norm_post_path(href: str) -> str | None:
    u = (href or "").strip()
    if not u:
        return None
    if u.startswith("http"):
        p = urlparse(u).path or ""
    else:
        p = u.split("?", 1)[0]
    p = p if p.startswith("/") else "/" + p
    return p if _is_post_path(p) else None


def _date_str_before_index(html: str, idx: int) -> str | None:
    """在 ``idx`` 之前若干字符内，取与卡片对应的英文日期（列表或轮播区）。"""
    chunk = html[max(0, idx - 6000) : idx]
    fs = re.findall(
        r'(?is)fs-list-field="date"[^>]*>([^<]+)</div>\s*',
        chunk,
    )
    if fs:
        s = (fs[-1] or "").strip()
        if s:
            return s
    cap = re.findall(
        r'(?is)class="[^"]*u-foreground-tertiary[^"]*"[^>]*>([A-Z][a-z]+ \d{1,2}, \d{4})</div>',
        chunk,
    )
    if cap:
        s = (cap[-1] or "").strip()
        if s:
            return s
    return None


def _heading_fallback_before_index(html: str, idx: int) -> str:
    """``fs-list-field="heading"`` 隐藏域标题。"""
    chunk = html[max(0, idx - 4000) : idx]
    fs = re.findall(
        r'(?is)fs-list-field="heading"[^>]*>([^<]+)</div>\s*',
        chunk,
    )
    if not fs:
        return ""
    return _strip_tags(fs[-1] or "")


def _extract_div_depth_inner(html: str, open_tag_end: int) -> str:
    """自 opening div 的 ``>`` 之后，匹配到成对关闭的该 div 内层 HTML。"""
    start = open_tag_end
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


def _richest_richtext_fragment(html: str) -> str:
    """首个可见、含正文段落的 ``u-rich-text-blog`` 区（图/视频在 ``w-richtext`` 内）。"""
    best = ""
    for rx in (_RICHTEXT_OPEN, _RICHTEXT_OPEN_ALT):
        for m in rx.finditer(html):
            if "w-condition-invisible" in html[max(0, m.start() - 100) : m.start()]:
                continue
            inner = _extract_div_depth_inner(html, m.end())
            if not inner or "<p" not in inner.lower() and "<figure" not in inner.lower():
                continue
            if len(inner) > len(best):
                best = inner
    return best


def parse_feed(
    listing_html: str,
    *,
    source_name: str,
    listing_url: str = "",
) -> list[dict[str, Any]]:
    """
    解析 claude.com/blog 列表/轮播。字段: source, title, link, published, summary。
    """
    if not listing_html or "/blog/" not in listing_html:
        return []

    base = _BASE
    lu = (listing_url or "").strip()
    if lu and "claude.com" in lu.lower():
        p = urlparse(lu)
        if p.scheme and p.netloc:
            base = f"{p.scheme}://{p.netloc}"

    by_path: dict[str, dict[str, Any]] = {}

    def upsert(
        path: str, published: datetime | None, title: str, summary: str
    ) -> None:
        if not _is_post_path(path) or published is None:
            return
        title_t = (title or "").strip() or "(无标题)"
        if len(title_t) > 200:
            title_t = title_t[:200] + "…"
        sum_t = (summary or title_t)[:500]
        link = urljoin(base + "/", path.lstrip("/"))
        row = {
            "source": source_name,
            "title": title_t,
            "link": link,
            "published": published,
            "summary": sum_t,
        }
        prev = by_path.get(path)
        if prev is None or len(sum_t) > len(prev.get("summary") or ""):
            by_path[path] = row

    for m in re.finditer(r"(?is)<a\s+([^>]+)>", listing_html):
        atag = m.group(1) or ""
        if "clickable_link" not in atag or 'data-cta="Blog page"' not in atag:
            continue
        hm = re.search(r'(?i)href="([^"]+)"', atag)
        if not hm:
            continue
        path = _norm_post_path(hm.group(1))
        if not path:
            continue
        ctm = re.search(r'data-cta-copy="([^"]*)"', atag)
        title = unescape((ctm.group(1) if ctm else "").strip())
        if not title or title in {"Read more", ""}:
            title = _heading_fallback_before_index(listing_html, m.start()) or title
        if not title:
            title = "(无标题)"

        d_raw = _date_str_before_index(listing_html, m.start())
        pub_d = _parse_mdy_english(d_raw or "")
        if pub_d is None:
            continue
        published = datetime.combine(pub_d, time(12, 0), tzinfo=_TZ_SH)
        upsert(path, published, title, title[:500])

    return list(by_path.values())


class ClaudeBlogRender:
    """单篇：标题、og 摘要、正文区 HTML 供配图解析。"""

    def enrich(self, html: str, link: str, entry: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        low = (link or "").lower()
        if "claude.com" not in low or "/blog/" not in low:
            return out
        path = urlparse(link).path or ""
        pnorm = [x for x in path.rstrip("/").split("/") if x]
        if len(pnorm) < 2 or pnorm[0].lower() != "blog":
            return out
        if pnorm[1].lower() == "category":
            return out

        ogt = _og_meta(html, "og:title")
        if ogt:
            t = ogt.split("|", 1)[0].strip()
            t = _strip_tags(t) or t
            if t:
                out["title"] = t

        if not out.get("title") and entry.get("title"):
            out["title"] = str(entry["title"]).strip()

        ogo = _og_meta(html, "og:description")
        if ogo:
            s = _strip_tags(ogo)
            if s:
                out["summary"] = s[:2000]

        if not out.get("summary"):
            ogo2 = re.search(
                r'(?is)<meta\s+name="description"\s+content="([^"]+)"',
                html,
            )
            if ogo2:
                s = _strip_tags(ogo2.group(1) or "")
                if s:
                    out["summary"] = s[:2000]

        frag = _richest_richtext_fragment(html)
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
