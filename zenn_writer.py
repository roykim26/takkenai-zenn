from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class ZennWriter:
    def __init__(self, repo_path: str) -> None:
        self.repo_path = Path(repo_path)
        self.articles_dir = self.repo_path / "articles"
        self.images_dir = self.repo_path / "images"

        self.articles_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_title(title: str) -> str:
        return title.replace("\\", "\\\\").replace('"', '\\"').strip()

    @staticmethod
    def _normalize_topics(topics: list[str]) -> list[str]:
        cleaned: list[str] = []
        for topic in topics:
            item = str(topic).strip()
            if not item:
                continue
            if item not in cleaned:
                cleaned.append(item)
        return cleaned[:5]

    def write_article(
        self,
        *,
        slug: str,
        article: dict,
        image_markdown_path: Optional[str] = None,
    ) -> dict:
        topics = self._normalize_topics(article.get("topics", []))
        if not topics:
            topics = ["ai", "zenn"]

        title = self._safe_title(article["title"])
        emoji = article.get("emoji", "📝")
        article_type = article.get("type", "tech")
        body_md = article.get("body_md", "").strip()

        frontmatter = (
            "---\n"
            f'title: "{title}"\n'
            f'emoji: "{emoji}"\n'
            f'type: "{article_type}"\n'
            f"topics: {json.dumps(topics, ensure_ascii=False)}\n"
            "published: true\n"
            "---\n\n"
        )

        content_parts = [frontmatter]

        if image_markdown_path:
            content_parts.append(f"![cover]({image_markdown_path})\n\n")

        content_parts.append(body_md)
        content = "".join(content_parts).rstrip() + "\n"

        article_path = self.articles_dir / f"{slug}.md"
        article_path.write_text(content, encoding="utf-8")

        return {
            "absolute_path": str(article_path),
            "relative_path": f"articles/{slug}.md",
        }
