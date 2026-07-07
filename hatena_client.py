from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests


LOGGER = logging.getLogger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"
APP_NS = "http://www.w3.org/2007/app"
NS = {"atom": ATOM_NS, "app": APP_NS}


def normalize_hatena_blog_id(value: str) -> str:
    text = (value or "").strip().strip("/")
    if "://" not in text:
        return text

    parsed = urlparse(text)
    hostname = (parsed.netloc or "").strip()
    if hostname:
        return hostname.strip("/")
    return text


class HatenaClient:
    def __init__(self, *, hatena_id: str, blog_id: str, api_key: str, base_url: str, timeout: int = 30) -> None:
        self.hatena_id = hatena_id.strip().strip("/")
        self.blog_id = normalize_hatena_blog_id(blog_id)
        self.api_key = api_key.strip()
        self.base_url = (base_url or "https://blog.hatena.ne.jp").strip().rstrip("/")
        self.timeout = timeout

        if not self.hatena_id:
            raise ValueError("缺少 HATENA_ID")
        if not self.blog_id:
            raise ValueError("缺少 HATENA_BLOG_ID")
        if not self.api_key:
            raise ValueError("缺少 HATENA_API_KEY")

    @property
    def entry_collection_url(self) -> str:
        return f"{self.base_url}/{self.hatena_id}/{self.blog_id}/atom/entry"

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/atom+xml;type=entry;charset=utf-8",
            "Accept": "application/atom+xml;type=entry, application/xml, text/xml",
            "User-Agent": "zenn-hatena-auto-publisher/1.0",
        }

    def publish_entry(self, entry_xml: str) -> dict[str, Any]:
        response = requests.post(
            self.entry_collection_url,
            data=entry_xml.encode("utf-8"),
            headers=self._headers(),
            auth=(self.hatena_id, self.api_key),
            timeout=self.timeout,
        )

        if response.status_code not in {200, 201}:
            raise RuntimeError(
                f"Hatena 发布失败: HTTP {response.status_code}\n"
                f"body:\n{response.text[:2000]}"
            )

        location = response.headers.get("Location", "").strip()
        parsed = self._parse_entry_xml(response.text)
        if not parsed.get("edit_url") and location:
            parsed["edit_url"] = location
        if not parsed.get("platform_post_id") and location:
            parsed["platform_post_id"] = location.rstrip("/").split("/")[-1]
        return parsed

    def _parse_entry_xml(self, xml_text: str) -> dict[str, Any]:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
        title = self._find_text(root, "atom:title")
        entry_id = self._find_text(root, "atom:id")
        published_at = self._find_text(root, "atom:published") or self._find_text(root, "atom:updated")
        updated_at = self._find_text(root, "atom:updated")
        edit_url = self._find_link_href(root, rel="edit")
        article_url = self._find_link_href(root, rel="alternate")
        preview_url = self._find_link_href(root, rel="preview")
        platform_post_id = ""
        if edit_url:
            platform_post_id = edit_url.rstrip("/").split("/")[-1]

        return {
            "title": title,
            "entry_id": entry_id,
            "edit_url": edit_url,
            "article_url": article_url,
            "preview_url": preview_url,
            "published_at": published_at,
            "updated_at": updated_at,
            "platform_post_id": platform_post_id,
            "raw_xml": xml_text,
        }

    @staticmethod
    def _find_text(root: ET.Element, xpath: str) -> str:
        node = root.find(xpath, NS)
        return (node.text or "").strip() if node is not None and node.text else ""

    @staticmethod
    def _find_link_href(root: ET.Element, rel: str) -> str:
        for link in root.findall("atom:link", NS):
            if link.attrib.get("rel") == rel:
                return (link.attrib.get("href") or "").strip()
        return ""
