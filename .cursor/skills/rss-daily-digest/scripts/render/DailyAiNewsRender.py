"""
AI工具集「每日AI快讯」列表页: https://ai-bot.cn/daily-ai-news/

HTML 结构要点:
- 正文: .panel-body.single.mt-2，至 #comments 之前
- 按日: .news-date（如 4月24·周五）
- 每条: .news-item > .news-content > h2 > a（标题+主链） + p（摘要，末为 span.news-time 来源）

主脚本通过模块级 ``parse_feed()`` 拉平为伪 RSS 条目；站外标题链若正文含 ai-bot.cn 内链则设 ``body_fetch_url`` 供配图抓取。
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from html import unescape
from typing import Any
from zoneinfo import ZoneInfo

try:
    _TZ_SH = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    _TZ_SH = timezone(timedelta(hours=8))

_ITEM_BLOCK = re.compile(
    r'(?is)<div class="news-item">\s*<div class="news-content">\s*'
    r'<h2[^>]*>\s*<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>\s*'
    r'<p[^>]*class="[^"]*text-muted[^"]*text-sm[^"]*"[^>]*>(.*?)</p>\s*</div>\s*</div>',
)
# 少数条目 p 仅有 text-sm 等 class，回退为任意 p
_ITEM_BLOCK_LOOSE = re.compile(
    r'(?is)<div class="news-item">\s*<div class="news-content">\s*'
    r'<h2[^>]*>\s*<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>\s*'
    r"<p[^>]*>(.*?)</p>\s*</div>\s*</div>",
)

_NEWS_DATE_RE = re.compile(r'(?is)<div class="news-date">([^<]+)</div>')
_META_MOD_RE = re.compile(
    r'<meta\s+property="article:modified_time"\s+content="([^"]+)"',
    re.I,
)
_PANEL_BODY_RE = re.compile(
    r'<div class="panel-body single mt-2">\s*(.*?)(?=<div[^>]*\bid=["\']comments["\']|\Z)',
    re.I | re.DOTALL,
)
_AIBOT_LINK_RE = re.compile(r'href="(https://ai-bot\.cn/[^"#?][^"]*)"', re.I)


def _strip_tags(html: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?is)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t)).strip()


def _parse_news_date_label(label: str, year: int) -> date | None:
    m = re.search(r"(\d{1,2})月(\d{1,2})", label or "")
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _fallback_date_from_meta(html: str) -> date | None:
    m = _META_MOD_RE.search(html)
    if not m:
        return None
    raw = (m.group(1) or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    return None


def _year_from_meta(html: str, fallback: date | None) -> int:
    m = _META_MOD_RE.search(html)
    if m:
        raw = (m.group(1) or "").strip()
        if len(raw) >= 4 and raw[:4].isdigit():
            return int(raw[:4])
    if fallback:
        return fallback.year
    return datetime.now(_TZ_SH).year


def _summary_from_phtml(phtml: str) -> str:
    cut = re.split(r'(?is)<span[^>]*class="[^"]*news-time', phtml, maxsplit=1)[0]
    return _strip_tags(cut)[:500]


def _first_aibot_url(phtml: str) -> str | None:
    m = _AIBOT_LINK_RE.search(phtml)
    return m.group(1).rstrip("/") if m else None


def _listing_chunk(html: str) -> str:
    pm = _PANEL_BODY_RE.search(html)
    return pm.group(1) if pm else html


def _iter_items(chunk: str):
    seen: set[int] = set()
    for im in _ITEM_BLOCK.finditer(chunk):
        seen.add(im.start())
        yield im
    for im in _ITEM_BLOCK_LOOSE.finditer(chunk):
        if im.start() not in seen:
            yield im


def parse_feed(listing_html: str, *, source_name: str, listing_url: str = "") -> list[dict]:
    """
    解析整页所有 .news-item；``published`` 取当日 12:00（上海），由主脚本按自然日筛选。

    条目字段: source, title, link, published, summary；可选 body_fetch_url。
    """
    if not listing_html or "news-item" not in listing_html:
        return []

    fb = _fallback_date_from_meta(listing_html)
    year = _year_from_meta(listing_html, fb)
    chunk = _listing_chunk(listing_html)

    events: list[tuple[str, int, int, Any]] = []
    for m in _NEWS_DATE_RE.finditer(chunk):
        events.append(("date", m.start(), m.end(), m.group(1).strip()))
    for im in _iter_items(chunk):
        events.append(("item", im.start(), im.end(), im))
    events.sort(key=lambda x: (x[1], x[2]))

    items: list[dict] = []
    current_day: date | None = fb

    for typ, _s, _e, data in events:
        if typ == "date":
            parsed = _parse_news_date_label(data, year)
            if parsed is not None:
                current_day = parsed
            continue

        im = data
        href = (im.group(1) or "").strip()
        title = _strip_tags(im.group(2) or "") or "(无标题)"
        phtml = im.group(3) or ""
        summary = _summary_from_phtml(phtml)
        pub_d = current_day or fb
        if pub_d is None:
            pub_d = datetime.now(_TZ_SH).date()
        published = datetime.combine(pub_d, time(12, 0), tzinfo=_TZ_SH)

        row: dict[str, Any] = {
            "source": source_name,
            "title": title,
            "link": href,
            "published": published,
            "summary": summary,
        }
        low = href.lower()
        internal = _first_aibot_url(phtml)
        if internal and "ai-bot.cn" not in low and internal.rstrip("/") != href.rstrip("/"):
            row["body_fetch_url"] = internal
        items.append(row)

    return items


class DailyAiNewsRender:
    """保留类封装，供测试或旧代码调用。"""

    @classmethod
    def expand_html_feed(
        cls,
        html: str,
        feed_url: str,
        source_name: str,
        feed_priority: int,
        target: date,
    ) -> list[dict] | None:
        rows = parse_feed(html, source_name=source_name, listing_url=feed_url)
        out = [r for r in rows if r.get("published") and r["published"].date() == target]
        for r in out:
            r["feed_priority"] = feed_priority
        return out or None

    def enrich(self, html: str, link: str, entry: dict[str, Any]) -> dict[str, Any]:
        """
        单篇 ai-bot 文章页：用 h1 与 .panel-body 区补充标题/摘要（聚合页勿用）。
        """
        out: dict[str, Any] = {}
        if "ai-bot.cn" not in (link or ""):
            return out
        if "/daily-ai-news" in link.rstrip("/").split("?")[0]:
            return out

        m = re.search(
            r'(?is)<h1[^>]*class="[^"]*\bh3\b[^"]*"[^>]*>(.*?)</h1>',
            html,
        ) or re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html)
        if m:
            t = _strip_tags(m.group(1))
            if t:
                out["title"] = t

        mb = re.search(
            r'(?is)<div class="panel-body single[^"]*"[^>]*>(.*?)</div>\s*<div class="post-tags',
            html,
        )
        if mb:
            body_html = mb.group(1) or ""
            text = _strip_tags(body_html)
            if len(text) > 40:
                out["summary"] = text[:2000]

        if not out.get("summary"):
            m2 = re.search(
                r'(?is)<meta\s+name="description"\s+content="([^"]+)"',
                html,
            )
            if m2:
                out["summary"] = _strip_tags(m2.group(1))[:2000]

        return out
