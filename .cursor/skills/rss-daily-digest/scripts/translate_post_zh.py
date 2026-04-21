#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def should_translate(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    if has_cjk(cleaned):
        return False
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return False
    return bool(re.search(r"[A-Za-z]", cleaned))


def google_translate(text: str, cache: dict[str, str]) -> str:
    if text in cache:
        return cache[text]
    query = urllib.parse.quote(text)
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl=zh-CN&dt=t&q={query}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        translated = "".join(chunk[0] for chunk in data[0] if chunk and chunk[0]).strip()
    except Exception:
        translated = text
    cache[text] = translated if translated else text
    return cache[text]


def translate_overview_line(line: str, cache: dict[str, str]) -> str:
    m = re.match(r"^(- )(.+?)(\[↗\]\(.+\))$", line)
    if not m:
        return line
    prefix, title, suffix = m.groups()
    if not should_translate(title):
        return line
    zh = google_translate(title, cache)
    return f"{prefix}{zh}{suffix}"


def translate_article_heading(line: str, cache: dict[str, str]) -> str:
    m = re.match(r"^(## \[)(.+?)(\]\(.+\))$", line)
    if not m:
        return line
    pre, title, post = m.groups()
    if not should_translate(title):
        return line
    zh = google_translate(title, cache)
    return f"{pre}{zh}{post}"


def process_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[str] = []
    cache: dict[str, str] = {}

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("- ") and "[↗](" in line:
            out.append(translate_overview_line(line, cache))
            i += 1
            continue

        if line.startswith("## [") and "](" in line and line.endswith(")"):
            out.append(translate_article_heading(line, cache))
            i += 1
            continue

        if line.startswith("- ") and not line.startswith("- [https://"):
            if i + 1 < len(lines) and lines[i + 1].startswith("  "):
                paragraph = [line[2:].strip()]
                j = i + 1
                while j < len(lines) and lines[j].startswith("  "):
                    paragraph.append(lines[j].strip())
                    j += 1
                full = " ".join(part for part in paragraph if part).strip()
                if should_translate(full):
                    zh = google_translate(full, cache)
                    wrapped = textwrap.wrap(zh, width=74)
                    if wrapped:
                        out.append(f"- {wrapped[0]}")
                        for seg in wrapped[1:]:
                            out.append(f"  {seg}")
                    else:
                        out.append(f"- {zh}")
                    i = j
                    continue
            else:
                content = line[2:].strip()
                if should_translate(content):
                    zh = google_translate(content, cache)
                    out.append(f"- {zh}")
                    i += 1
                    continue

        out.append(line)
        i += 1

    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate daily post into Chinese.")
    parser.add_argument("file", help="Markdown file path.")
    args = parser.parse_args()
    process_file(Path(args.file))
    print(f"Translated: {args.file}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def should_translate(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    if has_cjk(cleaned):
        return False
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return False
    return bool(re.search(r"[A-Za-z]", cleaned))


def google_translate(text: str, cache: dict[str, str]) -> str:
    if text in cache:
        return cache[text]
    query = urllib.parse.quote(text)
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl=zh-CN&dt=t&q={query}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        translated = "".join(chunk[0] for chunk in data[0] if chunk and chunk[0]).strip()
    except Exception:
        translated = text
    cache[text] = translated if translated else text
    return cache[text]


def translate_overview_line(line: str, cache: dict[str, str]) -> str:
    m = re.match(r"^(- )(.+?)(\[↗\]\(.+\))$", line)
    if not m:
        return line
    prefix, title, suffix = m.groups()
    if not should_translate(title):
        return line
    zh = google_translate(title, cache)
    return f"{prefix}{zh}{suffix}"


def translate_article_heading(line: str, cache: dict[str, str]) -> str:
    m = re.match(r"^(## \[)(.+?)(\]\(.+\))$", line)
    if not m:
        return line
    pre, title, post = m.groups()
    if not should_translate(title):
        return line
    zh = google_translate(title, cache)
    return f"{pre}{zh}{post}"


def process_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[str] = []
    cache: dict[str, str] = {}

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("- ") and "[↗](" in line:
            out.append(translate_overview_line(line, cache))
            i += 1
            continue

        if line.startswith("## [") and "](" in line and line.endswith(")"):
            out.append(translate_article_heading(line, cache))
            i += 1
            continue

        if line.startswith("- ") and not line.startswith("- [https://"):
            if i + 1 < len(lines) and lines[i + 1].startswith("  "):
                paragraph = [line[2:].strip()]
                j = i + 1
                while j < len(lines) and lines[j].startswith("  "):
                    paragraph.append(lines[j].strip())
                    j += 1
                full = " ".join(part for part in paragraph if part).strip()
                if should_translate(full):
                    zh = google_translate(full, cache)
                    wrapped = textwrap.wrap(zh, width=74)
                    if wrapped:
                        out.append(f"- {wrapped[0]}")
                        for seg in wrapped[1:]:
                            out.append(f"  {seg}")
                    else:
                        out.append(f"- {zh}")
                    i = j
                    continue
            else:
                content = line[2:].strip()
                if should_translate(content):
                    zh = google_translate(content, cache)
                    out.append(f"- {zh}")
                    i += 1
                    continue

        out.append(line)
        i += 1

    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate daily post into Chinese.")
    parser.add_argument("file", help="Markdown file path.")
    args = parser.parse_args()
    process_file(Path(args.file))
    print(f"Translated: {args.file}")


if __name__ == "__main__":
    main()
