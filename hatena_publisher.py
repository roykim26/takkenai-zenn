from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from hatena_client import HatenaClient
from hatena_writer import HatenaWriter


LOGGER = logging.getLogger(__name__)


def split_csv_like(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"[,\n锛屻€亅锝?]+", text)
    result: list[str] = []
    for part in parts:
        item = part.strip()
        if item and item not in result:
            result.append(item)
    return result[:10]


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default


@dataclass
class HatenaAccount:
    key: str
    client: HatenaClient
    writer: HatenaWriter


class HatenaPublisher:
    def __init__(self, timezone_name: str = "Asia/Tokyo") -> None:
        self.timezone_name = timezone_name
        self.content_type = os.getenv("HATENA_CONTENT_TYPE", "text/x-markdown").strip() or "text/x-markdown"
        self.default_draft = (os.getenv("HATENA_DEFAULT_DRAFT", "no").strip().lower() == "yes")
        self.enable_custom_url = (os.getenv("HATENA_ENABLE_CUSTOM_URL", "true").strip().lower() == "true")
        self.enable_preview = (os.getenv("HATENA_ENABLE_PREVIEW", "no").strip().lower() == "yes")
        self.use_scheduled = (os.getenv("HATENA_USE_SCHEDULED", "no").strip().lower() == "yes")
        self.category_source = os.getenv("HATENA_CATEGORY_SOURCE", "keywords").strip() or "keywords"

        self.accounts: dict[str, HatenaAccount] = {
            "A": self._build_account(
                key="A",
                hatena_id=os.getenv("HATENA_ID", "").strip(),
                blog_id=os.getenv("HATENA_BLOG_ID", "").strip(),
                api_key=os.getenv("HATENA_API_KEY", "").strip(),
                base_url=os.getenv("HATENA_BASE_URL", "https://blog.hatena.ne.jp").strip(),
                export_dir=os.getenv("HATENA_EXPORT_DIR", "hatena_exports").strip() or "hatena_exports",
            )
        }

    def _build_account(
        self,
        *,
        key: str,
        hatena_id: str,
        blog_id: str,
        api_key: str,
        base_url: str,
        export_dir: str,
    ) -> HatenaAccount:
        return HatenaAccount(
            key=key,
            client=HatenaClient(
                hatena_id=hatena_id,
                blog_id=blog_id,
                api_key=api_key,
                base_url=base_url,
            ),
            writer=HatenaWriter(export_dir=export_dir, timezone_name=self.timezone_name),
        )

    @staticmethod
    def _normalize_account_key(value: Any) -> str:
        text = str(value or "").strip().upper()
        if text in {"", "DEFAULT", "ACCOUNT_A", "HATENA_A"}:
            return "A"
        if text in {"B", "ACCOUNT_B", "HATENA_B"}:
            return "B"
        return text

    def _get_account(self, record: dict[str, Any]) -> HatenaAccount:
        account_key = self._normalize_account_key(record.get("hatena_account"))
        if account_key == "A":
            return self.accounts["A"]
        if account_key == "B":
            if "B" not in self.accounts:
                self.accounts["B"] = self._build_account(
                    key="B",
                    hatena_id=env_first("HATENA_ACCOUNT_B_ID", "HATENA_B_ID"),
                    blog_id=env_first("HATENA_ACCOUNT_B_BLOG_ID", "HATENA_B_BLOG_ID"),
                    api_key=env_first("HATENA_ACCOUNT_B_API_KEY", "HATENA_B_API_KEY"),
                    base_url=env_first(
                        "HATENA_ACCOUNT_B_BASE_URL",
                        "HATENA_B_BASE_URL",
                        default=os.getenv("HATENA_BASE_URL", "https://blog.hatena.ne.jp").strip(),
                    ),
                    export_dir=env_first("HATENA_ACCOUNT_B_EXPORT_DIR", "HATENA_B_EXPORT_DIR", default="hatena_exports_b"),
                )
            return self.accounts["B"]
        raise ValueError(f"Unsupported hatena_account: {account_key}")

    def _pick_categories(self, record: dict[str, Any], article: dict[str, Any]) -> list[str]:
        explicit = split_csv_like(record.get("categories", ""))
        if explicit:
            return explicit
        if self.category_source == "topics":
            return [str(x).strip() for x in article.get("topics", []) if str(x).strip()][:10]
        if self.category_source == "keywords":
            return split_csv_like(record.get("keywords", ""))
        return [str(x).strip() for x in article.get("topics", []) if str(x).strip()][:10]

    def publish(self, *, record: dict[str, Any], article: dict[str, Any], slug: str) -> dict[str, Any]:
        account = self._get_account(record)
        local_copy = account.writer.save_local_copy(slug=slug, article=article)
        categories = self._pick_categories(record, article)
        is_draft = bool(record.get("is_draft", self.default_draft))
        custom_url = slug if self.enable_custom_url and slug else None

        entry_xml = account.writer.build_entry_xml(
            article=article,
            content_type=self.content_type,
            author_name=account.client.hatena_id,
            categories=categories,
            is_draft=is_draft,
            enable_preview=self.enable_preview,
            use_scheduled=self.use_scheduled,
            custom_url=custom_url,
        )
        published = account.client.publish_entry(entry_xml)
        return {
            "slug": slug,
            "hatena_account": account.key,
            "article_path": local_copy["relative_path"],
            "article_url": published.get("article_url", ""),
            "edit_url": published.get("edit_url", ""),
            "platform_post_id": published.get("platform_post_id", ""),
            "published_at": published.get("published_at", ""),
            "preview_url": published.get("preview_url", ""),
            "title": article.get("title", ""),
            "is_draft": is_draft,
        }
