from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from timezone_utils import get_timezone


ATOM_NS = "http://www.w3.org/2005/Atom"
APP_NS = "http://www.w3.org/2007/app"
HATENA_BLOG_NS = "http://www.hatena.ne.jp/info/xmlns#hatenablog"

ET.register_namespace("", ATOM_NS)
ET.register_namespace("app", APP_NS)
ET.register_namespace("hatenablog", HATENA_BLOG_NS)


class HatenaWriter:
    def __init__(self, export_dir: str, timezone_name: str = "Asia/Tokyo") -> None:
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.tz = get_timezone(timezone_name)

    @staticmethod
    def _normalize_categories(categories: Iterable[str]) -> list[str]:
        result: list[str] = []
        for item in categories:
            text = str(item).strip()
            if text and text not in result:
                result.append(text)
        return result[:10]

    def save_local_copy(self, slug: str, article: dict) -> dict:
        title = str(article.get("title", "")).strip()
        excerpt = str(article.get("excerpt", "")).strip()
        body_md = str(article.get("body_md", "")).strip()
        categories = self._normalize_categories(article.get("topics", []))

        content = []
        if title:
            content.append(f"# {title}\n\n")
        if excerpt:
            content.append(f"> {excerpt}\n\n")
        if categories:
            content.append("categories: " + ", ".join(categories) + "\n\n")
        content.append(body_md)
        final_text = "".join(content).rstrip() + "\n"

        path = self.export_dir / f"{slug}.md"
        path.write_text(final_text, encoding="utf-8")
        return {
            "absolute_path": str(path),
            "relative_path": str(path).replace("\\", "/"),
        }

    def build_entry_xml(
        self,
        *,
        article: dict,
        content_type: str,
        author_name: str,
        categories: list[str],
        is_draft: bool,
        enable_preview: bool,
        use_scheduled: bool,
        custom_url: str | None,
    ) -> str:
        entry = ET.Element(f"{{{ATOM_NS}}}entry")

        title_el = ET.SubElement(entry, f"{{{ATOM_NS}}}title")
        title_el.text = str(article.get("title", "")).strip()

        author_el = ET.SubElement(entry, f"{{{ATOM_NS}}}author")
        name_el = ET.SubElement(author_el, f"{{{ATOM_NS}}}name")
        name_el.text = author_name

        content_el = ET.SubElement(entry, f"{{{ATOM_NS}}}content", {"type": content_type})
        content_el.text = str(article.get("body_md", "")).strip()

        updated_el = ET.SubElement(entry, f"{{{ATOM_NS}}}updated")
        updated_el.text = datetime.now(self.tz).isoformat(timespec="seconds")

        for category in self._normalize_categories(categories):
            ET.SubElement(entry, f"{{{ATOM_NS}}}category", {"term": category})

        control_el = ET.SubElement(entry, f"{{{APP_NS}}}control")
        draft_el = ET.SubElement(control_el, f"{{{APP_NS}}}draft")
        draft_el.text = "yes" if is_draft else "no"
        preview_el = ET.SubElement(control_el, f"{{{APP_NS}}}preview")
        preview_el.text = "yes" if is_draft and enable_preview else "no"
        scheduled_el = ET.SubElement(control_el, f"{{{HATENA_BLOG_NS}}}scheduled")
        scheduled_el.text = "yes" if is_draft and use_scheduled else "no"

        if custom_url:
            custom_el = ET.SubElement(entry, f"{{{HATENA_BLOG_NS}}}custom-url")
            custom_el.text = custom_url.strip("/")

        xml_bytes = ET.tostring(entry, encoding="utf-8", xml_declaration=True)
        return xml_bytes.decode("utf-8")
