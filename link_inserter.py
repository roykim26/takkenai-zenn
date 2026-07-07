# link_inserter.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

HOME_URL = "https://www.takkenai.jp/"
DEFAULT_MAX_KEYWORD_LINKS = 3
BRAND_TERMS = ["不動産AI", "TakkenAI"]


@dataclass
class InsertResult:
    content: str
    keyword_hits: List[str]
    brand_hit: Optional[str]


def parse_keywords(raw: str | None) -> List[str]:
    if not raw:
        return []

    text = str(raw).strip()
    if not text:
        return []

    # 支持逗号、日文顿号、中文顿号、分号、换行、竖线
    parts = re.split(r"[\n\r,，、；;|]+", text)
    cleaned: List[str] = []

    for p in parts:
        s = p.strip()
        if not s:
            continue
        if s not in cleaned:
            cleaned.append(s)

    # 长关键词优先，避免短词抢先命中
    cleaned.sort(key=len, reverse=True)
    return cleaned


def _protect_segments(text: str) -> Tuple[str, Dict[str, str]]:
    """
    保护以下片段，避免插链误伤：
    1. 代码块 ```...```
    2. 行内代码 `...`
    3. 已有 markdown 链接 [text](url)
    """
    token_map: Dict[str, str] = {}
    counter = 0

    def _stash(pattern: str, src: str) -> str:
        nonlocal counter
        def repl(m: re.Match) -> str:
            nonlocal counter
            token = f"@@PROTECTED_{counter}@@"
            token_map[token] = m.group(0)
            counter += 1
            return token
        return re.sub(pattern, repl, src, flags=re.DOTALL)

    text = _stash(r"```.*?```", text)
    text = _stash(r"`[^`\n]+`", text)
    text = _stash(r"\[[^\]]+?\]\([^)]+?\)", text)
    return text, token_map


def _restore_segments(text: str, token_map: Dict[str, str]) -> str:
    for token, original in token_map.items():
        text = text.replace(token, original)
    return text


def _is_heading_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("#")


def _replace_first_literal(text: str, needle: str, replacement: str) -> Tuple[str, bool]:
    idx = text.find(needle)
    if idx < 0:
        return text, False
    return text[:idx] + replacement + text[idx + len(needle):], True


def _linkify_term_once(line: str, term: str, url: str) -> Tuple[str, bool]:
    link = f"[{term}]({url})"
    return _replace_first_literal(line, term, link)


def add_utm_source(url: str, utm_source: str | None) -> str:
    if not url or not utm_source:
        return url

    source = str(utm_source).strip()
    if not source:
        return url

    parts = urlsplit(url)
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    if any(key == "utm_source" for key, _ in query_pairs):
        return url

    query_pairs.append(("utm_source", source))
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query_pairs),
        parts.fragment,
    ))


def insert_home_links(
    markdown_body: str,
    keywords_raw: str | None,
    homepage_url: str = HOME_URL,
    max_keyword_links: int = DEFAULT_MAX_KEYWORD_LINKS,
    brand_terms: Optional[List[str]] = None,
    utm_source: str | None = None,
) -> InsertResult:
    """
    规则：
    - 只根据 keywords 插链
    - 每个关键词最多链接 1 次
    - 全文最多插 max_keyword_links 个关键词链接
    - 如果正文自然出现品牌词，则仅给品牌词链接 1 次
    - 不在标题 / 代码块 / 行内代码 / 已有链接中插入
    """
    if not markdown_body or not markdown_body.strip():
        return InsertResult(content=markdown_body, keyword_hits=[], brand_hit=None)

    brand_terms = brand_terms or BRAND_TERMS
    keywords = parse_keywords(keywords_raw)
    link_url = add_utm_source(homepage_url, utm_source)

    protected_text, token_map = _protect_segments(markdown_body)
    lines = protected_text.splitlines(keepends=True)

    used_keywords: List[str] = []
    brand_hit: Optional[str] = None
    keyword_link_count = 0

    new_lines: List[str] = []

    for line in lines:
        if _is_heading_line(line):
            new_lines.append(line)
            continue

        working = line

        # 先处理关键词
        if keyword_link_count < max_keyword_links:
            for kw in keywords:
                if kw in used_keywords:
                    continue
                if kw not in working:
                    continue

                working, replaced = _linkify_term_once(working, kw, link_url)
                if replaced:
                    used_keywords.append(kw)
                    keyword_link_count += 1
                    if keyword_link_count >= max_keyword_links:
                        break

        # 再处理品牌词（只链接一次，且只链接正文中自然出现的）
        if brand_hit is None:
            for brand in brand_terms:
                if brand in working:
                    working, replaced = _linkify_term_once(working, brand, link_url)
                    if replaced:
                        brand_hit = brand
                        break

        new_lines.append(working)

    restored = _restore_segments("".join(new_lines), token_map)

    return InsertResult(
        content=restored,
        keyword_hits=used_keywords,
        brand_hit=brand_hit,
    )
