from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI


LOGGER = logging.getLogger(__name__)


class ImageManager:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_IMAGE_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_IMAGE_BASE_URL", "").strip()
        self.model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1").strip() or "gpt-image-1"
        self.size = os.getenv("OPENAI_IMAGE_SIZE", "1536x1024").strip() or "1536x1024"

    def generate_image(
        self,
        *,
        prompt: str,
        slug: str,
        repo_path: str,
        filename: str = "cover.png",
    ) -> Optional[dict]:
        prompt = (prompt or "").strip()
        if not prompt:
            return None

        if not self.api_key:
            LOGGER.warning("存在 image_prompt，但未配置 OPENAI_API_KEY，跳过生图")
            return None

        image_dir = Path(repo_path) / "images" / slug
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / filename

        try:
            client_kwargs = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            client = OpenAI(**client_kwargs)
            result = client.images.generate(
                model=self.model,
                prompt=prompt,
                size=self.size,
            )
            image_base64 = result.data[0].b64_json
            image_bytes = base64.b64decode(image_base64)

            with open(image_path, "wb") as f:
                f.write(image_bytes)

            return {
                "absolute_path": str(image_path),
                "relative_path": f"images/{slug}/{filename}",
                "markdown_path": f"/images/{slug}/{filename}",
            }
        except Exception as exc:
            LOGGER.exception("图片生成失败，将按无图继续: %s", exc)
            return None
