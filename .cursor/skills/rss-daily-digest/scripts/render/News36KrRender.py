"""
36氪 资讯流（如 AI 频道）: https://www.36kr.com/information/AI/

首屏列表在 ``window.initialState`` 的 JSON 内：
``information.informationList.itemList``。每条 ``templateMaterial`` 含
``publishTime``（毫秒 Unix 时间戳）、``widgetTitle``、``summary``；文章页为
``https://www.36kr.com/p/{itemId}``。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

try:
    _TZ_SH = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    _TZ_SH = timezone(timedelta(hours=8))

_INITIAL_MARKER = "window.initialState="


def _parse_initial_state(html: str) -> dict[str, Any] | None:
    idx = html.find(_INITIAL_MARKER)
    if idx < 0:
        return None
    i = idx + len(_INITIAL_MARKER)
    while i < len(html) and html[i] in " \t\n\r":
        i += 1
    if i >= len(html) or html[i] != "{":
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(html[i:])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _ms_to_aware_dt(ms: float | int) -> datetime:
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)


def parse_feed(listing_html: str, *, source_name: str, listing_url: str = "") -> list[dict]:
    """
    解析 ``initialState.information.informationList.itemList``；
    ``published`` 为 UTC 的 aware datetime，由主脚本按上海自然日筛选。
    """
    if not listing_html or _INITIAL_MARKER not in listing_html:
        return []

    state = _parse_initial_state(listing_html)
    if not state:
        return []

    info = state.get("information")
    if not isinstance(info, dict):
        return []
    ilist = info.get("informationList")
    if not isinstance(ilist, dict):
        return []
    raw_items = ilist.get("itemList")
    if not isinstance(raw_items, list):
        return []

    items: list[dict] = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        tm = it.get("templateMaterial")
        if not isinstance(tm, dict):
            continue
        iid = it.get("itemId") or tm.get("itemId")
        if iid is None:
            continue
        title = (tm.get("widgetTitle") or "").strip() or "(无标题)"
        summary = (tm.get("summary") or "").strip()
        pt = tm.get("publishTime")
        if pt is None:
            continue
        try:
            published = _ms_to_aware_dt(pt)
        except (OSError, OverflowError, ValueError):
            continue

        row: dict[str, Any] = {
            "source": source_name,
            "title": title,
            "link": f"https://www.36kr.com/p/{iid}",
            "published": published,
            "summary": summary[:2000] if summary else "",
        }
        items.append(row)

    return items


class News36KrRender:
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
        out = [r for r in rows if r.get("published") and r["published"].astimezone(_TZ_SH).date() == target]
        for r in out:
            r["feed_priority"] = feed_priority
        return out or None
