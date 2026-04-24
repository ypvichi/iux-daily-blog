"""
AIGC IZZI 中文站「快讯」列表: https://aigc.izzi.cn/category/news

仅提取带「今日」角标的条目（<span class="site-card-badge site-card-new"><small>今日</small></span>），
与历史快讯区分；时间在 <strong>标题</strong> 后的 ``YYYY-MM-DD HH:MM:SS``。
可选摘要取自注释内的 ``<!--p class="overflowClip_1">...</p-->``。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from html import unescape
from typing import Any
from zoneinfo import ZoneInfo

try:
    _TZ_SH = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    _TZ_SH = timezone(timedelta(hours=8))

# 快讯区块：避免匹配「一周热点」「最新Ai工具」等同结构卡片
_KUAIXUN_CHUNK = re.compile(
    r"(?is)<h4[^>]*>.*?快讯.*?</h4>\s*<div[^>]*class=\"[^\"]*row[^\"]*\"[^>]*>(.*?)(?=<h4[^>]*class=\"text-gray\")",
)

_ITEM = re.compile(
    r'(?is)<a\s+[^>]*href="(https://aigc\.izzi\.cn/article/\d+\.html)"[^>]*\btitle="《([^"]*)"[^>]*>\s*'
    r'<span class="site-card-badge site-card-new">\s*<small>\s*今日\s*</small>\s*</span>\s*'
    r'<div class="xe-comment-entry">.*?'
    r'<strong>([^<]+)</strong>\s*'
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})",
)

_SUMMARY_IN_COMMENT = re.compile(
    r'(?is)<!--\s*p class="overflowClip_1"\s*>(.*?)</p\s*-->',
)


def _strip_tags(html: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?is)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t)).strip()


def _kuaixun_html(html: str) -> str:
    m = _KUAIXUN_CHUNK.search(html)
    return m.group(1) if m else html


def _summary_after_datetime(block_tail: str) -> str:
    sm = _SUMMARY_IN_COMMENT.search(block_tail)
    if not sm:
        return ""
    return _strip_tags(sm.group(1) or "")[:2000]


def parse_feed(listing_html: str, *, source_name: str, listing_url: str = "") -> list[dict]:
    """
    解析快讯区带「今日」角标的卡片；``published`` 取页面上的上海本地时间戳。
    """
    if not listing_html or "site-card-badge" not in listing_html:
        return []

    chunk = _kuaixun_html(listing_html)
    items: list[dict] = []

    for im in _ITEM.finditer(chunk):
        href = (im.group(1) or "").strip()
        title_attr = (im.group(2) or "").strip()
        title_strong = (im.group(3) or "").strip()
        ts_raw = (im.group(4) or "").strip()
        title = title_strong or title_attr or "(无标题)"

        try:
            published = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_TZ_SH)
        except ValueError:
            published = datetime.combine(
                datetime.now(_TZ_SH).date(),
                datetime.min.time().replace(hour=12, minute=0),
                tzinfo=_TZ_SH,
            )

        tail = chunk[im.end() : im.end() + 1200]
        summary = _summary_after_datetime(tail)

        row: dict[str, Any] = {
            "source": source_name,
            "title": title,
            "link": href,
            "published": published,
            "summary": summary,
        }
        items.append(row)

    return items


class AigcIzziCnRender:
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
