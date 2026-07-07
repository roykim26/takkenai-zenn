from __future__ import annotations

import logging
import os
import random
import re
from typing import Any, Dict, List

from openai import OpenAI

from link_inserter import insert_home_links


LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一名擅长撰写日文博客文章的编辑，目标发布平台是 Zenn 或 Hatena Blog。
你的任务是直接输出“可发布”的完整日文 Markdown 正文。

硬性要求：
1. 全文必须使用自然、专业、可读的日语。
2. 必须输出完整文章，不是提纲，不是需求复述，不是模板草稿。
3. 不要输出 JSON。
4. 不要输出 ```markdown 或 ``` 代码块。
5. 不要写一级标题，正文从导语开始，小节使用 ## / ###。
6. 至少包含以下结构：
   - 导入
   - 背景 / 问题说明
   - 核心方法 / 思路
   - 具体步骤或实操建议
   - 注意点
   - 总结
7. 严禁输出占位符或未完成内容，例如：
   - 202X年X月
   - 平日X時間 / 休日X時間
   - 初心者 / 中級者
   - 〇〇
   - XXX
   - 「ここに〜を書く」
8. 如果补充信息不足，请基于主题和关键词合理展开，但不要编造权威数据或虚假来源。
9. 如需插入相关链接，请使用标准 Markdown 链接格式，不要输出裸链接。
10. 品牌相关表达必须自然，不要为了植入而生硬插入。"""


class ArticleQualityError(ValueError):
    """正文生成成功但质量不足时抛出，用于触发延时重试。"""


def _split_keywords(value: str) -> List[str]:
    if not value:
        return []
    parts = re.split(r"[,，、\n\r\t]+", value)
    cleaned = []
    for part in parts:
        item = part.strip()
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned[:6]


def _cleanup_body_md(body_md: str) -> str:
    body = body_md.strip()

    code_fence_match = re.search(r"```(?:markdown)?\s*(.*)\s*```", body, re.DOTALL)
    if code_fence_match:
        body = code_fence_match.group(1).strip()

    body = re.sub(r"^\s*#\s+.+?$", "", body, count=1, flags=re.MULTILINE).strip()
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body


def _count_headings(body_md: str) -> int:
    return len(re.findall(r"^\s*##+\s+", body_md, flags=re.MULTILINE))


def _count_paragraphs(body_md: str) -> int:
    parts = [x.strip() for x in re.split(r"\n\s*\n", body_md) if x.strip()]
    return len(parts)


PLACEHOLDER_DIRECT_PATTERNS: list[tuple[str, str]] = [
    ("20XX", r"20XX"),
    ("XX", r"\bXX\b"),
    ("XXX", r"\bXXX\b"),
    ("〇〇", r"〇〇"),
    ("平日X時間", r"平日X時間"),
    ("休日X時間", r"休日X時間"),
    ("X時間", r"X時間"),
    ("X日", r"X日"),
    ("X週間", r"X週間"),
    ("Xか月", r"Xか月"),
    ("初心者 / 中級者", r"初心者\s*/\s*中級者"),
    ("ここに", r"ここに"),
    ("入力してください", r"入力してください"),
    ("TODO", r"\bTODO\b"),
]

PLACEHOLDER_CONTEXT_TERMS = (
    "\u30c6\u30f3\u30d7\u30ec",
    "\u30b5\u30f3\u30d7\u30eb",
    "\u96db\u5f62",
)
PLACEHOLDER_CONTEXT_ACTIONS = (
    "\u5165\u529b",
    "\u8a18\u5165",
    "\u8a2d\u5b9a",
    "\u5dee\u3057\u66ff\u3048",
    "\u7f6e\u63db",
    "\u8ffd\u52a0",
    "\u7de8\u96c6",
    "\u8cbc\u308a\u4ed8\u3051",
    "\u57cb\u3081",
    "\u53cd\u6620",
)
PLACEHOLDER_CONTEXT_PARTICLES = ("", "\u3092", "\u306f", "\u3068\u3057\u3066")
PLACEHOLDER_CONTEXT_REQUESTS = (
    "",
    "\u3057\u3066\u304f\u3060\u3055\u3044",
    "\u3057\u307e\u3059",
    "\u3059\u308b",
    "\u7528",
)
PLACEHOLDER_WRAPPING_PAIRS = (
    ('"', '"'),
    ("'", "'"),
    ("[", "]"),
    ("(", ")"),
    ("\u300c", "\u300d"),
    ("\u300e", "\u300f"),
    ("\u3010", "\u3011"),
    ("\uff08", "\uff09"),
)


def _unwrap_placeholder_line(text: str) -> str:
    cleaned = text.strip().lstrip("-*").strip()
    changed = True
    while cleaned and changed:
        changed = False
        for left, right in PLACEHOLDER_WRAPPING_PAIRS:
            if cleaned.startswith(left) and cleaned.endswith(right) and len(cleaned) > len(left) + len(right):
                cleaned = cleaned[len(left):-len(right)].strip()
                changed = True
    return cleaned


def _find_contextual_placeholder_hits(text: str) -> list[str]:
    hits: list[str] = []

    for term in PLACEHOLDER_CONTEXT_TERMS:
        for line in text.splitlines():
            if _unwrap_placeholder_line(line) == term:
                hits.append(term)
                break
        if term in hits:
            continue

        if any(f"{term}{particle}{action}" in text for particle in PLACEHOLDER_CONTEXT_PARTICLES for action in PLACEHOLDER_CONTEXT_ACTIONS):
            hits.append(term)
            continue

        if any(f"{action}{request}" in text and term in text for action in PLACEHOLDER_CONTEXT_ACTIONS for request in PLACEHOLDER_CONTEXT_REQUESTS):
            prefix = text.split(term, 1)[0].rstrip()
            if any(prefix.endswith(f"{action}{request}") or prefix.endswith(f"{action}{request}:") or prefix.endswith(f"{action}{request}\uff1a") for action in PLACEHOLDER_CONTEXT_ACTIONS for request in PLACEHOLDER_CONTEXT_REQUESTS):
                hits.append(term)

    return hits


def _find_placeholder_hits(text: str) -> list[str]:
    hits: list[str] = []

    for label, pattern in PLACEHOLDER_DIRECT_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(label)

    for term in _find_contextual_placeholder_hits(text):
        if term not in hits:
            hits.append(term)

    return hits


def _contains_placeholder(text: str) -> bool:
    return bool(_find_placeholder_hits(text))


def _check_article_quality(body_md: str, min_chars: int) -> dict[str, Any]:
    reasons: list[str] = []
    non_placeholder_reasons: list[str] = []

    body = body_md.strip()
    char_count = len(re.sub(r"\s+", "", body))
    heading_count = _count_headings(body)
    paragraph_count = _count_paragraphs(body)
    placeholder_hits = _find_placeholder_hits(body)

    if char_count < min_chars:
        reason = f"正文长度不足（当前约 {char_count} 字，要求至少 {min_chars} 字）"
        reasons.append(reason)
        non_placeholder_reasons.append(reason)

    if heading_count < 3:
        reason = f"小标题过少（当前 {heading_count} 个）"
        reasons.append(reason)
        non_placeholder_reasons.append(reason)

    if paragraph_count < 5:
        reason = f"段落过少（当前 {paragraph_count} 段）"
        reasons.append(reason)
        non_placeholder_reasons.append(reason)

    if placeholder_hits:
        reasons.append("正文包含模板占位符或未完成内容，命中项：" + ", ".join(placeholder_hits[:8]))

    suspicious_lines = 0
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^[「『【\[]?(条件|规格内容|要件|前提)[」』】\]]?", s):
            suspicious_lines += 1
    if suspicious_lines >= 2:
        reason = "正文更像需求复述或提纲，不像完整文章"
        reasons.append(reason)
        non_placeholder_reasons.append(reason)

    return {
        "is_thin": len(reasons) > 0,
        "reasons": reasons,
        "placeholder_hits": placeholder_hits,
        "placeholder_only": bool(placeholder_hits) and not non_placeholder_reasons,
    }


def _is_thin_article(body_md: str, min_chars: int) -> tuple[bool, list[str]]:
    quality = _check_article_quality(body_md, min_chars)
    return quality["is_thin"], quality["reasons"]


def _build_excerpt_from_body(body_md: str, max_len: int = 100) -> str:
    text = re.sub(r"^#+\s+", "", body_md, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] if text else "今回のテーマを整理した記事です。"


class ArticleGenerator:
    def __init__(self) -> None:
        llm_config = self._resolve_llm_config()
        self.api_key = llm_config["api_key"]
        self.base_url = llm_config["base_url"]
        self.model = llm_config["model"]
        self.temperature_raw = llm_config["temperature"] or "0.7"
        self.provider_name = llm_config["provider_name"]

        self.min_body_chars_default = int(os.getenv("ARTICLE_MIN_BODY_CHARS", "1200").strip())
        self.min_body_chars_zenn = int(os.getenv("ARTICLE_MIN_BODY_CHARS_ZENN", "1400").strip())
        self.min_body_chars_hatena = int(os.getenv("ARTICLE_MIN_BODY_CHARS_HATENA", "900").strip())
        self.max_tokens = int(os.getenv("ARTICLE_MAX_TOKENS", "3200").strip())
        self.max_keyword_links = int(os.getenv("ARTICLE_MAX_KEYWORD_LINKS", "3").strip())
        self.homepage_url = os.getenv("HOMEPAGE_URL", "https://www.takkenai.jp/").strip() or "https://www.takkenai.jp/"

        if not self.api_key:
            raise ValueError("缺少 QWEN_API_KEY / DASHSCOPE_API_KEY / MOONSHOT_API_KEY")
        if not self.base_url:
            raise ValueError("缺少 QWEN_BASE_URL / DASHSCOPE_BASE_URL / MOONSHOT_BASE_URL")
        if not self.model:
            raise ValueError("缺少 QWEN_MODEL / DASHSCOPE_MODEL / MOONSHOT_MODEL")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    @staticmethod
    def _env_first(*names: str) -> str:
        for name in names:
            value = os.getenv(name, "").strip()
            if value:
                return value
        return ""

    def _resolve_llm_config(self) -> dict[str, str]:
        provider_groups = [
            {
                "provider_name": "Qwen",
                "api_key": self._env_first("QWEN_API_KEY", "DASHSCOPE_API_KEY"),
                "base_url": self._env_first("QWEN_BASE_URL", "DASHSCOPE_BASE_URL"),
                "model": self._env_first("QWEN_MODEL", "DASHSCOPE_MODEL"),
                "temperature": self._env_first("QWEN_TEMPERATURE", "DASHSCOPE_TEMPERATURE"),
            },
            {
                "provider_name": "Moonshot",
                "api_key": self._env_first("MOONSHOT_API_KEY"),
                "base_url": self._env_first("MOONSHOT_BASE_URL"),
                "model": self._env_first("MOONSHOT_MODEL"),
                "temperature": self._env_first("MOONSHOT_TEMPERATURE"),
            },
        ]

        for config in provider_groups:
            if config["api_key"] and config["base_url"] and config["model"]:
                return config

        qwen_names = (
            "QWEN_API_KEY",
            "QWEN_BASE_URL",
            "QWEN_MODEL",
            "DASHSCOPE_API_KEY",
            "DASHSCOPE_BASE_URL",
            "DASHSCOPE_MODEL",
        )
        if any(os.getenv(name, "").strip() for name in qwen_names):
            raise ValueError("Qwen 配置不完整，请同时设置 QWEN_API_KEY、QWEN_BASE_URL、QWEN_MODEL")

        return provider_groups[-1]

    def _should_omit_temperature(self) -> bool:
        return "kimi-k2.5" in self.model.lower()

    def _resolve_min_chars(self, source: Dict[str, Any]) -> int:
        platform = str(source.get("platform", "")).strip().lower()
        if platform == "zenn":
            return self.min_body_chars_zenn
        if platform == "hatenablog":
            return self.min_body_chars_hatena
        return self.min_body_chars_default

    def _build_request_kwargs(self, messages: list[dict[str, str]], include_temperature: bool) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        if include_temperature:
            try:
                kwargs["temperature"] = float(self.temperature_raw or "0.7")
            except Exception:
                kwargs["temperature"] = 0.7

        return kwargs

    def _create_completion(self, messages: list[dict[str, str]]):
        include_temperature = not self._should_omit_temperature()

        if not include_temperature:
            LOGGER.info("检测到模型 %s，不传 temperature 参数", self.model)

        kwargs = self._build_request_kwargs(messages, include_temperature=include_temperature)

        try:
            return self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            err_text = str(exc).lower()
            need_retry_without_temperature = (
                "invalid temperature" in err_text
                or "only 1 is allowed for this model" in err_text
                or ("temperature" in err_text and "invalid_request_error" in err_text)
            )

            if include_temperature and need_retry_without_temperature:
                LOGGER.warning("模型拒绝 temperature 参数，自动改为不传 temperature 重试一次")
                retry_kwargs = self._build_request_kwargs(messages, include_temperature=False)
                return self.client.chat.completions.create(**retry_kwargs)

            raise

    def _build_user_prompt(self, source: Dict[str, Any]) -> str:
        title = source.get("source_title", "").strip()
        keywords = source.get("keywords", "").strip()
        prompt = source.get("prompt", "").strip()
        platform = str(source.get("platform", "")).strip().lower()

        platform_block = ""
        if platform == "hatenablog":
            platform_block = """
【平台要求】
- 目标平台是 Hatena Blog。
- 风格偏易读、实用、面向普通读者的博客文章。
- 必须写成完整博客文章，不要写成提纲。
- 至少包含 5 个以上小节，并且每个小节都要有自然段展开。"""
        elif platform == "zenn":
            platform_block = """
【平台要求】
- 目标平台是 Zenn。
- 风格偏技术 / 方法论，结构清晰，但要保持自然可读。
- 至少包含 5 个以上小节，并且每个小节都要有自然段展开。"""

        return f"""请基于以下主题信息，直接输出一篇完整的日文 Markdown 正文。
【主题标题】{title or "(未提供，请你根据主题拟定文章方向)"}

【关键词】{keywords or "(未提供)"}

【补充要求 / 主题说明】{prompt or "(未提供，请围绕标题和关键词合理展开)"}

{platform_block}

【正文写作硬性要求】
1. 直接输出完整 Markdown 正文，不要输出 JSON。
2. 不要写一级标题。
3. 必须包含导入、背景说明、核心观点、实操建议、注意点、总结。
4. 至少包含 5 个以上二级小标题。
5. 每个小标题下都要有完整自然段，不要只有一句话。
6. 不要出现任何模板占位符，例如 202X、X時間、初心者 / 中級者、〇〇、XXX。
7. 不要把补充要求原样复述成正文。
8. 不要只写几百字，要写成适合正式发布的完整文章。
9. 如需插入相关链接，请使用标准 Markdown 链接格式，不要输出裸链接。
10. 关键词可以自然分散地融入正文，但不要刻意堆砌。
11. 如果语境自然、表达不生硬，可以只提及一次「不動産AI」或「TakkenAI」中的其中一个；如果不自然，就不要强行加入。
12. 不要在结尾写“以上”“以下是正文”“请参考”等元说明。
请直接开始写正文。"""

    def _build_placeholder_repair_prompt(self, placeholder_hits: list[str]) -> str:
        hit_text = ", ".join(placeholder_hits[:8]) if placeholder_hits else "placeholder"
        return (
            "上一次正文里仍然出现了疑似模板占位符，请直接重写为可发布的完整日文 Markdown 正文。"
            f"疑似命中项: {hit_text}。"
            "保留原主题，不要输出说明，不要保留任何模板词、TODO、XX、XXX、未填写提示或半成品内容。"
            "如果这些词是作为业务概念出现，也请改写成自然表达，避免原词直接出现。"
        )

    def _generate_body_with_quality_gate(
        self,
        *,
        title: str,
        min_chars: int,
        messages: list[dict[str, str]],
    ) -> str:
        response = self._create_completion(messages)
        content = response.choices[0].message.content or ""
        body_md = _cleanup_body_md(content)
        quality = _check_article_quality(body_md, min_chars)

        if quality["placeholder_hits"]:
            LOGGER.warning(
                "正文命中占位符检测，title=%s, hits=%s",
                title or "（空）",
                ", ".join(quality["placeholder_hits"]),
            )

        if quality["placeholder_only"]:
            LOGGER.info(
                "正文仅因占位符检测被拦截，尝试同轮修复重写一次，title=%s",
                title or "（空）",
            )
            repair_messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": self._build_placeholder_repair_prompt(quality["placeholder_hits"])},
            ]
            retry_response = self._create_completion(repair_messages)
            retry_content = retry_response.choices[0].message.content or ""
            retry_body_md = _cleanup_body_md(retry_content)
            retry_quality = _check_article_quality(retry_body_md, min_chars)

            if retry_quality["placeholder_hits"]:
                LOGGER.warning(
                    "同轮修复重写后仍命中占位符，title=%s, hits=%s",
                    title or "（空）",
                    ", ".join(retry_quality["placeholder_hits"]),
                )

            if not retry_quality["is_thin"]:
                return retry_body_md

            quality = retry_quality
            body_md = retry_body_md

        if quality["is_thin"]:
            raise ArticleQualityError(
                "生成的正文质量不足。本次原因：" + "；".join(quality["reasons"] or ["正文过短或模板化"])
            )

        return body_md

    def generate_article(self, source: Dict[str, Any]) -> Dict[str, Any]:
        title = source.get("source_title", "").strip()
        min_chars = self._resolve_min_chars(source)
        platform = str(source.get("platform", "")).strip().lower()
        utm_source = None
        if platform == "zenn":
            utm_source = "zenn"
        elif platform == "hatenablog":
            utm_source = "hatena"

        LOGGER.info("开始调用 %s 生成正文，title=%s", self.provider_name, title or "（空）")

        user_prompt = self._build_user_prompt(source)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        body_md = self._generate_body_with_quality_gate(
            title=title,
            min_chars=min_chars,
            messages=messages,
        )

        insert_result = insert_home_links(
            markdown_body=body_md,
            keywords_raw=source.get("keywords", ""),
            homepage_url=self.homepage_url,
            max_keyword_links=self.max_keyword_links,
            utm_source=utm_source,
        )
        body_md = insert_result.content

        LOGGER.info(
            "正文插链完成，title=%s，keyword_hits=%s，brand_hit=%s",
            title or "（空）",
            insert_result.keyword_hits,
            insert_result.brand_hit,
        )

        final_title = title or f"ブログ記事 {random.randint(1000, 9999)}"
        topics = _split_keywords(source.get("keywords", ""))[:5]
        if not topics:
            topics = ["ai", "blog"]

        return {
            "title": final_title,
            "excerpt": _build_excerpt_from_body(body_md, 100),
            "topics": topics,
            "emoji": "📝",
            "type": "tech",
            "body_md": body_md,
            "link_stats": {
                "keyword_hits": insert_result.keyword_hits,
                "brand_hit": insert_result.brand_hit,
            },
        }
