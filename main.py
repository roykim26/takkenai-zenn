from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import requests

from bot_notifier import BotNotifier
from feishu_client import FeishuClient
from generator import ArticleGenerator, ArticleQualityError
from git_publisher import GitPublisher
from hatena_publisher import HatenaPublisher
from image_manager import ImageManager
from publish_gate import PublishGate
from retry_manager import (
    build_quality_retry_exhausted_update,
    can_attempt_quality_retry,
    is_retryable_hatena_publish_error,
    on_hatena_publish_failure,
    on_quality_failure,
    parse_retry_error,
)
from timezone_utils import get_timezone
from zenn_writer import ZennWriter


LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def setup_logging() -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = logging.FileHandler(LOG_DIR / "publish.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)


LOGGER = logging.getLogger(__name__)


@dataclass
class Settings:
    timezone_name: str
    publish_start_hour: int
    publish_start_minute: int
    target_platform: str
    zenn_repo_path: str
    git_remote: str
    git_branch: str
    gate_control_file: str
    gate_total_daily_push_limit: int
    gate_new_daily_push_limit: int
    gate_retry_cooldown_hours: int
    gate_retry_daily_limit_per_slug: int

    field_platform: list[str]
    field_status: list[str]
    field_publish_date: list[str]
    field_title: list[str]
    field_keywords: list[str]
    field_prompt: list[str]
    field_image_prompt: list[str]
    field_anchor_links: list[str]
    field_slug: list[str]
    field_categories: list[str]
    field_is_draft: list[str]
    field_hatena_account: list[str]

    write_field_status: str
    write_field_slug: str
    write_field_article_title: str
    write_field_article_excerpt: str
    write_field_article_path: str
    write_field_retry_count: str
    write_field_error_message: str
    write_field_article_url: str
    write_field_edit_url: str
    write_field_platform_post_id: str
    write_field_published_at: str
    write_field_last_push_at: str
    write_field_last_result: str

    status_ready: str
    status_publishing: str
    status_queued: str
    status_waiting: str
    status_published: str
    status_failed: str


def split_aliases(raw: str | None, defaults: list[str]) -> list[str]:
    if raw is None or raw.strip() == "":
        return defaults
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_settings() -> Settings:
    return Settings(
        timezone_name=os.getenv("TIMEZONE", "Asia/Tokyo").strip() or "Asia/Tokyo",
        publish_start_hour=int(os.getenv("PUBLISH_START_HOUR", "10") or "10"),
        publish_start_minute=int(os.getenv("PUBLISH_START_MINUTE", "0") or "0"),
        target_platform=os.getenv("TARGET_PLATFORM", "all").strip().lower() or "all",
        zenn_repo_path=os.getenv("ZENN_REPO_PATH", "").strip(),
        git_remote=os.getenv("GIT_REMOTE", "origin").strip() or "origin",
        git_branch=os.getenv("GIT_BRANCH", "main").strip() or "main",
        gate_control_file=os.getenv("PUBLISH_GATE_FILE", "publish_control.json").strip() or "publish_control.json",
        gate_total_daily_push_limit=int(os.getenv("GATE_TOTAL_DAILY_PUSH_LIMIT", "1") or "1"),
        gate_new_daily_push_limit=int(os.getenv("GATE_NEW_DAILY_PUSH_LIMIT", "1") or "1"),
        gate_retry_cooldown_hours=int(os.getenv("GATE_RETRY_COOLDOWN_HOURS", "24") or "24"),
        gate_retry_daily_limit_per_slug=int(os.getenv("GATE_RETRY_DAILY_LIMIT_PER_SLUG", "1") or "1"),
        field_platform=split_aliases(os.getenv("FIELD_PLATFORM"), ["platform"]),
        field_status=split_aliases(os.getenv("FIELD_STATUS"), ["status"]),
        field_publish_date=split_aliases(os.getenv("FIELD_PUBLISH_DATE"), ["publish_date"]),
        field_title=split_aliases(os.getenv("FIELD_TITLE"), ["topic"]),
        field_keywords=split_aliases(os.getenv("FIELD_KEYWORDS"), ["keywords"]),
        field_prompt=split_aliases(os.getenv("FIELD_PROMPT"), ["brief"]),
        field_image_prompt=split_aliases(os.getenv("FIELD_IMAGE_PROMPT"), ["image_prompt"]),
        field_anchor_links=split_aliases(os.getenv("FIELD_ANCHOR_LINKS"), ["anchor_links"]),
        field_slug=split_aliases(os.getenv("FIELD_SLUG"), ["slug"]),
        field_categories=split_aliases(os.getenv("FIELD_CATEGORIES"), ["categories"]),
        field_is_draft=split_aliases(os.getenv("FIELD_IS_DRAFT"), ["is_draft"]),
        field_hatena_account=split_aliases(os.getenv("FIELD_HATENA_ACCOUNT"), ["hatena_account"]),
        write_field_status=os.getenv("WRITE_FIELD_STATUS", "status").strip(),
        write_field_slug=os.getenv("WRITE_FIELD_SLUG", "slug").strip(),
        write_field_article_title=os.getenv("WRITE_FIELD_ARTICLE_TITLE", "article_title").strip(),
        write_field_article_excerpt=os.getenv("WRITE_FIELD_ARTICLE_EXCERPT", "article_excerpt").strip(),
        write_field_article_path=os.getenv("WRITE_FIELD_ARTICLE_PATH", "article_path").strip(),
        write_field_retry_count=os.getenv("WRITE_FIELD_RETRY_COUNT", "retry_count").strip(),
        write_field_error_message=os.getenv("WRITE_FIELD_ERROR_MESSAGE", "error_message").strip(),
        write_field_article_url=os.getenv("WRITE_FIELD_ARTICLE_URL", "article_url").strip(),
        write_field_edit_url=os.getenv("WRITE_FIELD_EDIT_URL", "edit_url").strip(),
        write_field_platform_post_id=os.getenv("WRITE_FIELD_PLATFORM_POST_ID", "platform_post_id").strip(),
        write_field_published_at=os.getenv("WRITE_FIELD_PUBLISHED_AT", "published_at").strip(),
        write_field_last_push_at=os.getenv("WRITE_FIELD_LAST_PUSH_AT", "last_push_at").strip(),
        write_field_last_result=os.getenv("WRITE_FIELD_LAST_RESULT", "last_result").strip(),
        status_ready=os.getenv("STATUS_READY", "ready").strip() or "ready",
        status_publishing=os.getenv("STATUS_PUBLISHING", "publishing").strip() or "publishing",
        status_queued=os.getenv("STATUS_QUEUED", "queued").strip() or "queued",
        status_waiting=os.getenv("STATUS_WAITING", "waiting").strip() or "waiting",
        status_published=os.getenv("STATUS_PUBLISHED", "published").strip() or "published",
        status_failed=os.getenv("STATUS_FAILED", "failed").strip() or "failed",
    )


def load_environment() -> None:
    """
    Load .env with a tolerant fallback so a few bad bytes do not block startup.
    """
    dotenv_path = Path(".env")
    if not dotenv_path.exists():
        load_dotenv()
        return

    try:
        load_dotenv(dotenv_path=dotenv_path, override=False)
        return
    except UnicodeDecodeError as exc:
        LOGGER.warning(".env UTF-8 decode failed, retrying with tolerant fallback: %s", exc)

    with dotenv_path.open("r", encoding="utf-8", errors="replace") as stream:
        load_dotenv(stream=stream, override=False)
    LOGGER.warning(".env contained invalid UTF-8 bytes; loaded with replacement fallback")


class SingleInstanceLock:
    def __init__(self, lock_path: str = ".publish.lock") -> None:
        self.lock_path = Path(lock_path)
        self.fp = None
        self.locked = False

    def __enter__(self) -> "SingleInstanceLock":
        import msvcrt

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.fp = open(self.lock_path, "a+b")
        try:
            self.fp.seek(0)
            msvcrt.locking(self.fp.fileno(), msvcrt.LK_NBLCK, 1)
            self.locked = True
        except OSError:
            if self.fp:
                self.fp.close()
                self.fp = None
            raise RuntimeError("检测到已有发布任务在运行，本次执行已跳过")

        self.fp.seek(0)
        self.fp.truncate()
        self.fp.write(b"running")
        self.fp.flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        import msvcrt

        if not self.fp:
            return None
        try:
            self.fp.seek(0)
            self.fp.truncate()
            self.fp.write(b"done")
            self.fp.flush()
        finally:
            try:
                if self.locked:
                    self.fp.seek(0)
                    try:
                        msvcrt.locking(self.fp.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError as e:
                        LOGGER.warning("释放单实例锁时忽略异常: %s", e)
            finally:
                try:
                    self.fp.close()
                finally:
                    self.fp = None
                    self.locked = False
        return None


def build_write_fields(settings: Settings, **kwargs: Any) -> dict[str, Any]:
    mapping = {
        settings.write_field_status: kwargs.get("status"),
        settings.write_field_slug: kwargs.get("slug"),
        settings.write_field_article_title: kwargs.get("article_title"),
        settings.write_field_article_excerpt: kwargs.get("article_excerpt"),
        settings.write_field_article_path: kwargs.get("article_path"),
        settings.write_field_retry_count: kwargs.get("retry_count"),
        settings.write_field_error_message: kwargs.get("error_message"),
        settings.write_field_article_url: kwargs.get("article_url"),
        settings.write_field_edit_url: kwargs.get("edit_url"),
        settings.write_field_platform_post_id: kwargs.get("platform_post_id"),
        settings.write_field_published_at: kwargs.get("published_at"),
        settings.write_field_last_push_at: kwargs.get("last_push_at"),
        settings.write_field_last_result: kwargs.get("last_result"),
    }
    return {k: v for k, v in mapping.items() if k}


def now_iso(tz_name: str) -> str:
    return datetime.now(get_timezone(tz_name)).isoformat(timespec="seconds")


def safe_slug(seed_title: str, fallback_text: str, prefix: str = "ai") -> str:
    slug = re.sub(r"[^a-zA-Z0-9-_]+", "-", (seed_title or "").lower()).strip("-_")
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.lower()

    if 12 <= len(slug) <= 50:
        return slug

    digest = hashlib.md5((fallback_text or seed_title or prefix).encode("utf-8")).hexdigest()[:8]
    timestamp = datetime.now().strftime("%m%d%H%M")
    fallback_slug = f"{prefix}-{timestamp}-{digest}".lower()
    return fallback_slug[:50]


def touch_retry_marker(file_path: str, tz_name: str) -> None:
    """
    旧版 retry_manager.py 提供过 touch_retry_marker。
    现在 retry_manager.py 已改成质量重试状态机，这里内置一个等价 helper，
    用于 waiting 状态下给 Zenn 文章制造一次可提交的 git diff。
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"waiting 待重试文章不存在: {path}")

    text = path.read_text(encoding="utf-8")
    stamp = now_iso(tz_name)
    marker_line = f"<!-- zenn-retry-marker: {stamp} -->"

    if re.search(r"<!-- zenn-retry-marker: .*? -->\s*$", text, flags=re.DOTALL):
        text = re.sub(
            r"<!-- zenn-retry-marker: .*? -->\s*$",
            marker_line,
            text,
            flags=re.DOTALL,
        )
    else:
        text = text.rstrip() + "\n\n" + marker_line + "\n"

    path.write_text(text, encoding="utf-8")


def record_to_payload(item: dict[str, Any], settings: Settings, tz: tzinfo) -> dict[str, Any]:
    fields = item.get("fields", {})

    platform = FeishuClient.to_text(FeishuClient.get_field_by_aliases(fields, settings.field_platform)).lower()
    status = FeishuClient.to_text(FeishuClient.get_field_by_aliases(fields, settings.field_status)).lower()
    title = FeishuClient.to_text(FeishuClient.get_field_by_aliases(fields, settings.field_title))
    keywords = FeishuClient.to_text(FeishuClient.get_field_by_aliases(fields, settings.field_keywords))
    prompt = FeishuClient.to_text(FeishuClient.get_field_by_aliases(fields, settings.field_prompt))
    image_prompt = FeishuClient.to_text(FeishuClient.get_field_by_aliases(fields, settings.field_image_prompt))
    slug = FeishuClient.to_text(FeishuClient.get_field_by_aliases(fields, settings.field_slug))
    categories = FeishuClient.to_text(FeishuClient.get_field_by_aliases(fields, settings.field_categories))
    is_draft = FeishuClient.to_bool(FeishuClient.get_field_by_aliases(fields, settings.field_is_draft), False)
    hatena_account = FeishuClient.to_text(FeishuClient.get_field_by_aliases(fields, settings.field_hatena_account)).strip()

    publish_dt = FeishuClient.parse_date(FeishuClient.get_field_by_aliases(fields, settings.field_publish_date))
    publish_date = None
    if publish_dt:
        publish_date = publish_dt.astimezone(tz).date()

    article_path = FeishuClient.to_text(fields.get(settings.write_field_article_path)) if settings.write_field_article_path else ""
    retry_count = FeishuClient.to_int(fields.get(settings.write_field_retry_count), 0) if settings.write_field_retry_count else 0
    error_message = FeishuClient.to_text(fields.get(settings.write_field_error_message)) if settings.write_field_error_message else ""
    published_at = FeishuClient.to_text(fields.get(settings.write_field_published_at)) if settings.write_field_published_at else ""
    article_url = FeishuClient.to_text(fields.get(settings.write_field_article_url)) if settings.write_field_article_url else ""

    return {
        "record_id": item["record_id"],
        "fields": fields,
        "platform": platform,
        "status": status,
        "publish_date": publish_date,
        "source_title": title,
        "keywords": keywords,
        "prompt": prompt,
        "image_prompt": image_prompt,
        "slug": slug,
        "categories": categories,
        "is_draft": is_draft,
        "hatena_account": hatena_account or "A",
        "article_path": article_path,
        "retry_count": retry_count,
        "error_message": error_message,
        "published_at": published_at,
        "article_url": article_url,
    }


def should_process(record: dict[str, Any], settings: Settings, today) -> bool:
    platform = record["platform"]
    if settings.target_platform not in {"", "all"} and platform != settings.target_platform:
        return False

    status = record["status"]
    if platform == "zenn":
        if status in {settings.status_queued.lower(), settings.status_waiting.lower()}:
            return True
        if status != settings.status_ready.lower():
            return False
        return record["publish_date"] is not None and record["publish_date"] <= today
    if platform == "hatenablog":
        if status != settings.status_ready.lower():
            return False
        return record["publish_date"] is not None and record["publish_date"] <= today
    return False


def is_today_unpublished(record: dict[str, Any], settings: Settings, today) -> bool:
    platform = record["platform"]
    if settings.target_platform not in {"", "all"} and platform != settings.target_platform:
        return False
    if platform not in {"zenn", "hatenablog"}:
        return False
    if record["publish_date"] != today:
        return False
    return record["status"] != settings.status_published.lower()


def parse_published_at(record: dict[str, Any], settings: Settings, tz: tzinfo) -> datetime | None:
    if not settings.write_field_published_at:
        return None
    dt = FeishuClient.parse_date(record.get("fields", {}).get(settings.write_field_published_at))
    if dt is None:
        return None
    return dt.astimezone(tz)


def has_future_publish_date_after_publication(record: dict[str, Any], settings: Settings, tz: tzinfo) -> bool:
    if record.get("platform") not in {"zenn", "hatenablog"}:
        return False
    if record.get("status") != settings.status_published.lower():
        return False
    publish_date = record.get("publish_date")
    if publish_date is None:
        return False
    published_at = parse_published_at(record, settings, tz)
    if published_at is None:
        return False
    return published_at.date() < publish_date


def build_future_publish_date_notice(records: list[dict[str, Any]], settings: Settings, tz: tzinfo) -> str:
    lines = [
        "Publish self-check alert: published records have future publish_date",
        f"Found {len(records)} published record(s) where published_at < publish_date.",
    ]
    for record in records[:15]:
        title = record.get("source_title") or "(empty title)"
        published_at = parse_published_at(record, settings, tz)
        published_date_text = published_at.isoformat() if published_at else "(empty)"
        article_url = record.get("article_url") or "(empty url)"
        lines.append(
            " - "
            f"{record.get('platform')} "
            f"record_id={record.get('record_id')} "
            f"publish_date={record.get('publish_date')} "
            f"published_at={published_date_text} "
            f"title={title} "
            f"url={article_url}"
        )
    if len(records) > 15:
        lines.append(f" - ... {len(records) - 15} more")
    lines.append("Please check whether publish_date was changed after the article was published.")
    return "\n".join(lines)


def diagnose_unpublished_record(record: dict[str, Any], settings: Settings) -> str:
    status = str(record.get("status") or "").strip().lower()
    platform = str(record.get("platform") or "").strip().lower()
    error_message = str(record.get("error_message") or "").strip()

    if platform == "zenn":
        if status == settings.status_ready.lower():
            retry_payload = parse_retry_error(error_message)
            if retry_payload and retry_payload.get("retry_after"):
                return f"ready; retry_after={retry_payload.get('retry_after')}"
            return "ready; not processed yet or waiting for quota"
        if status == settings.status_queued.lower():
            return "queued; article generated, waiting for Zenn push quota"
        if status == settings.status_waiting.lower():
            return "waiting; pushed to GitHub, waiting for Zenn confirmation or retry window"
        if status == settings.status_publishing.lower():
            return "publishing; previous run may have stopped before final write-back"
        if status == settings.status_failed.lower():
            return f"failed; {error_message[:160] or 'no error_message'}"

    if platform == "hatenablog":
        if status == settings.status_ready.lower():
            retry_payload = parse_retry_error(error_message)
            if retry_payload and retry_payload.get("retry_after"):
                return f"ready; retry_after={retry_payload.get('retry_after')}"
            return "ready; not processed yet or waiting for retry window"
        if status == settings.status_publishing.lower():
            return "publishing; previous run may have stopped before final write-back"
        if status == settings.status_failed.lower():
            return f"failed; {error_message[:160] or 'no error_message'}"

    return f"unsupported automatic retry status: {status or '(empty)'}"


def build_self_check_notice(
    records: list[dict[str, Any]],
    settings: Settings,
    today,
    *,
    include_retry_line: bool = True,
) -> str:
    lines = [
        f"Publish self-check alert: {today}",
        f"Found {len(records)} today record(s) not published.",
    ]
    for record in records[:10]:
        title = record.get("source_title") or "(empty title)"
        lines.append(
            " - "
            f"{record.get('platform')}/{record.get('status')} "
            f"record_id={record.get('record_id')} "
            f"title={title} "
            f"reason={diagnose_unpublished_record(record, settings)}"
        )
    if len(records) > 10:
        lines.append(f" - ... {len(records) - 10} more")
    if include_retry_line:
        lines.append("Self-check will now retry records that are safe for automatic processing.")
    return "\n".join(lines)


def get_ready_retry_sort_penalty(record: dict[str, Any]) -> int:
    if str(record.get("status") or "").strip().lower() != "ready":
        return 0

    payload = parse_retry_error(record.get("error_message"))
    if not payload:
        return 0

    can_run, _ = can_attempt_quality_retry(record)
    return 0 if can_run else 1


def collect_image_files(repo_path: str, slug: str) -> list[str]:
    image_dir = Path(repo_path) / "images" / slug
    if not image_dir.exists():
        return []
    result: list[str] = []
    for path in image_dir.rglob("*"):
        if path.is_file():
            result.append(str(path.relative_to(repo_path)).replace("\\", "/"))
    return sorted(result)


def build_zenn_public_article_url(git_publisher: GitPublisher, slug: str) -> str | None:
    owner = git_publisher.get_remote_owner()
    if not owner or not slug:
        return None
    return f"https://zenn.dev/{owner}/articles/{slug}"


def confirm_zenn_publication(
    record: dict[str, Any],
    *,
    git_publisher: GitPublisher,
    timezone_name: str,
) -> dict[str, Any] | None:
    slug = str(record.get("slug") or "").strip()
    if not slug:
        return None

    article_url = build_zenn_public_article_url(git_publisher, slug)
    if not article_url:
        return None

    try:
        response = requests.get(
            article_url,
            timeout=15,
            headers={"User-Agent": "zenn-bot/1.0"},
        )
    except Exception as exc:
        LOGGER.debug("Zenn publish confirmation request failed for slug=%s: %s", slug, exc)
        return None

    if response.status_code != 200:
        return None

    return {
        "article_url": article_url,
        "published_at": now_iso(timezone_name),
    }


def get_link_notice(article: dict[str, Any]) -> tuple[int, str]:
    link_stats = article.get("link_stats", {}) or {}
    keyword_hits = link_stats.get("keyword_hits", []) or []
    brand_hit = link_stats.get("brand_hit")
    keyword_count = len(keyword_hits)
    brand_text = brand_hit if brand_hit else "无"
    return keyword_count, brand_text


def process_zenn_ready(
    record: dict[str, Any],
    *,
    settings: Settings,
    feishu: FeishuClient,
    generator: ArticleGenerator,
    image_manager: ImageManager,
    writer: ZennWriter,
    git_publisher: GitPublisher,
    gate: PublishGate,
    notifier: BotNotifier,
) -> None:
    record_id = record["record_id"]

    preflight_decision = gate.can_push_new()
    if not preflight_decision.allowed:
        LOGGER.info(
            "zenn ready skipped before generation, record_id=%s, reason=%s",
            record_id,
            preflight_decision.reason,
        )
        return

    feishu.update_record(record_id, build_write_fields(settings, status=settings.status_publishing, error_message=""))

    article = generator.generate_article(record)
    slug = record["slug"] or safe_slug(article["title"] or record["source_title"], f"{record_id}-{article['title']}", "ai")

    image_result = None
    if record["image_prompt"].strip():
        image_result = image_manager.generate_image(
            prompt=record["image_prompt"],
            slug=slug,
            repo_path=settings.zenn_repo_path,
        )

    write_result = writer.write_article(
        slug=slug,
        article=article,
        image_markdown_path=image_result["markdown_path"] if image_result else None,
    )

    decision = gate.can_push_new()
    keyword_link_count, brand_text = get_link_notice(article)

    if not decision.allowed:
        feishu.update_record(
            record_id,
            build_write_fields(
                settings,
                status=settings.status_queued,
                slug=slug,
                article_title=article["title"],
                article_excerpt=article["excerpt"],
                article_path=write_result["relative_path"],
                retry_count=0,
                error_message="",
                last_result=decision.reason,
            ),
        )
        notifier.send(
            "Zenn 已生成文章，但因配额保护未执行 push\n"
            f"标题：{article['title']}\n"
            f"slug：{slug}\n"
            f"文件：{write_result['relative_path']}\n"
            f"当前状态：{settings.status_queued}\n"
            f"原因：{decision.reason}\n"
            f"关键词链接：{keyword_link_count} 个\n"
            f"品牌词链接：{brand_text}"
        )
        LOGGER.info("record_id=%s 进入 queued，原因：%s", record_id, decision.reason)
        return

    files_to_commit = [write_result["relative_path"]]
    if image_result:
        files_to_commit.append(image_result["relative_path"])

    git_result = git_publisher.add_commit_push(files_to_commit, commit_message=f"zenn: publish {slug}")
    pushed_at = now_iso(settings.timezone_name) if git_result.get("pushed") else ""
    if git_result.get("pushed"):
        gate.mark_new_push(slug=slug, record_id=record_id, commit=git_result["commit"])

    feishu.update_record(
        record_id,
        build_write_fields(
            settings,
            status=settings.status_waiting,
            slug=slug,
            article_title=article["title"],
            article_excerpt=article["excerpt"],
            article_path=write_result["relative_path"],
            retry_count=0,
            error_message="",
            last_push_at=pushed_at,
            last_result=(
                f"pushed commit={git_result['commit']}"
                if git_result.get("pushed")
                else "no staged changes; push skipped"
            ),
        ),
    )

    notifier.send(
        f"Zenn 新文章已推送 GitHub，当前状态已写回 {settings.status_waiting}\n"
        f"标题：{article['title']}\n"
        f"slug：{slug}\n"
        f"文件：{write_result['relative_path']}\n"
        f"commit：{git_result['commit']}\n"
        f"插图：{'有' if image_result else '无'}\n"
        f"关键词链接：{keyword_link_count} 个\n"
        f"品牌词链接：{brand_text}"
    )


def process_zenn_queued(
    record: dict[str, Any],
    *,
    settings: Settings,
    feishu: FeishuClient,
    git_publisher: GitPublisher,
    gate: PublishGate,
    notifier: BotNotifier,
) -> None:
    decision = gate.can_push_new()
    if not decision.allowed:
        LOGGER.info("queued 跳过 push，record_id=%s，原因：%s", record["record_id"], decision.reason)
        return

    record_id = record["record_id"]
    slug = record["slug"]
    if not slug:
        raise ValueError("queued 状态缺少 slug，无法找到待发布文章")

    relative_article_path = record["article_path"] or f"articles/{slug}.md"
    abs_article_path = Path(settings.zenn_repo_path) / relative_article_path
    if not abs_article_path.exists():
        raise FileNotFoundError(f"queued 待发布文章不存在: {abs_article_path}")

    files_to_commit = [relative_article_path] + collect_image_files(settings.zenn_repo_path, slug)

    feishu.update_record(record_id, build_write_fields(settings, status=settings.status_publishing, error_message=""))

    git_result = git_publisher.add_commit_push(files_to_commit, commit_message=f"zenn: publish queued {slug}")
    pushed_at = now_iso(settings.timezone_name) if git_result.get("pushed") else ""
    if git_result.get("pushed"):
        gate.mark_new_push(slug=slug, record_id=record_id, commit=git_result["commit"])

    feishu.update_record(
        record_id,
        build_write_fields(
            settings,
            status=settings.status_waiting,
            slug=slug,
            article_path=relative_article_path,
            retry_count=0,
            error_message="",
            last_push_at=pushed_at,
            last_result=(
                f"queued pushed commit={git_result['commit']}"
                if git_result.get("pushed")
                else "no staged changes; push skipped"
            ),
        ),
    )

    notifier.send(
        "Zenn queued 文章已进入正式 push\n"
        f"slug：{slug}\n"
        f"文件：{relative_article_path}\n"
        f"commit：{git_result['commit']}\n"
        f"当前状态：{settings.status_waiting}"
    )


def process_zenn_waiting(
    record: dict[str, Any],
    *,
    settings: Settings,
    feishu: FeishuClient,
    git_publisher: GitPublisher,
    gate: PublishGate,
    notifier: BotNotifier,
) -> None:
    record_id = record["record_id"]
    slug = record["slug"]
    if not slug:
        raise ValueError("waiting 状态缺少 slug，无法复用原文章")

    relative_article_path = record["article_path"] or f"articles/{slug}.md"
    abs_article_path = str(Path(settings.zenn_repo_path) / relative_article_path)

    published_check = confirm_zenn_publication(
        record,
        git_publisher=git_publisher,
        timezone_name=settings.timezone_name,
    )
    if published_check:
        published_at = published_check["published_at"]
        feishu.update_record(
            record_id,
            build_write_fields(
                settings,
                status=settings.status_published,
                slug=slug,
                article_path=relative_article_path,
                retry_count=int(record.get("retry_count", 0)),
                error_message="",
                article_url=published_check["article_url"],
                published_at=published_at,
                last_push_at=record.get("last_push_at") or published_at,
                last_result="confirmed published on zenn",
            ),
        )
        notifier.send(
            f"Zenn waiting 已确认发布成功，状态已写回 {settings.status_published}\n"
            f"slug：{slug}\n"
            f"文件：{relative_article_path}\n"
            f"文章地址：{published_check['article_url']}"
        )
        LOGGER.info("waiting 记录已确认发布成功并写回 published，record_id=%s, slug=%s", record_id, slug)
        return

    decision = gate.can_retry(slug)
    if not decision.allowed:
        LOGGER.info("waiting 跳过 retry，record_id=%s，原因：%s", record_id, decision.reason)
        return

    feishu.update_record(record_id, build_write_fields(settings, status=settings.status_publishing, error_message=""))

    touch_retry_marker(abs_article_path, settings.timezone_name)
    git_result = git_publisher.add_commit_push([relative_article_path], commit_message=f"zenn: retry {slug}")
    pushed_at = now_iso(settings.timezone_name)
    gate.mark_retry_push(slug=slug, record_id=record_id, commit=git_result["commit"])

    new_retry_count = int(record.get("retry_count", 0)) + 1
    feishu.update_record(
        record_id,
        build_write_fields(
            settings,
            status=settings.status_waiting,
            slug=slug,
            article_path=relative_article_path,
            retry_count=new_retry_count,
            error_message="",
            last_push_at=pushed_at,
            last_result=f"retry pushed commit={git_result['commit']}",
        ),
    )

    notifier.send(
        f"Zenn waiting 自动重试已推送 GitHub\n"
        f"slug：{slug}\n"
        f"文件：{relative_article_path}\n"
        f"重试次数：{new_retry_count}\n"
        f"commit：{git_result['commit']}"
    )


def process_hatena_ready(
    record: dict[str, Any],
    *,
    settings: Settings,
    feishu: FeishuClient,
    generator: ArticleGenerator,
    notifier: BotNotifier,
    hatena_publisher: HatenaPublisher,
) -> None:
    record_id = record["record_id"]
    hatena_account = record.get("hatena_account", "A")
    LOGGER.info(
        "开始处理 Hatena 发布，record_id=%s, account=%s, title=%s, publish_date=%s",
        record_id,
        hatena_account,
        record.get("source_title") or "（空）",
        record.get("publish_date"),
    )
    feishu.update_record(record_id, build_write_fields(settings, status=settings.status_publishing, error_message=""))

    article = generator.generate_article(record)
    slug = record["slug"] or safe_slug(article["title"] or record["source_title"], f"hatena-{record_id}-{article['title']}", "ai")
    result = hatena_publisher.publish(record=record, article=article, slug=slug)
    hatena_account = result.get("hatena_account", hatena_account)

    keyword_link_count, brand_text = get_link_notice(article)

    feishu.update_record(
        record_id,
        build_write_fields(
            settings,
            status=settings.status_published,
            slug=slug,
            article_title=article["title"],
            article_excerpt=article["excerpt"],
            article_path=result["article_path"],
            retry_count=0,
            error_message="",
            article_url=result.get("article_url", ""),
            edit_url=result.get("edit_url", ""),
            platform_post_id=result.get("platform_post_id", ""),
            published_at=result.get("published_at", "") or now_iso(settings.timezone_name),
            last_push_at=now_iso(settings.timezone_name),
            last_result=(
                f"draft published via hatena api account={hatena_account}"
                if result.get("is_draft")
                else f"published via hatena api account={hatena_account}"
            ),
        ),
    )
    LOGGER.info(
        "Hatena publish succeeded, record_id=%s, account=%s, slug=%s, article_url=%s, edit_url=%s",
        record_id,
        hatena_account,
        slug,
        result.get("article_url", ""),
        result.get("edit_url", ""),
    )

    notice = (
        f"Hatena 文章已自动发布\n"
        f"账号：{hatena_account}\n"
        f"标题：{article['title']}\n"
        f"slug：{slug}\n"
        f"本地文件：{result['article_path']}\n"
        f"文章地址：{result.get('article_url') or '(未返回)'}\n"
        f"编辑地址：{result.get('edit_url') or '(未返回)'}\n"
        f"关键词链接：{keyword_link_count} 个\n"
        f"品牌词链接：{brand_text}"
    )
    notifier.send(notice)


def process_one_record(
    record: dict[str, Any],
    *,
    settings: Settings,
    feishu: FeishuClient,
    generator: ArticleGenerator,
    image_manager: ImageManager,
    writer: ZennWriter | None,
    git_publisher: GitPublisher | None,
    gate: PublishGate,
    notifier: BotNotifier,
    hatena_publisher: HatenaPublisher,
) -> None:
    platform = record["platform"]
    status = record["status"]

    try:
        if platform == "zenn":
            if status == settings.status_ready.lower():
                can_run, reason = can_attempt_quality_retry(record)
                if not can_run:
                    exhausted_updates = build_quality_retry_exhausted_update(record)
                    if exhausted_updates:
                        feishu.update_record(
                            record["record_id"],
                            build_write_fields(
                                settings,
                                status=exhausted_updates.get("status"),
                                retry_count=exhausted_updates.get("retry_count"),
                                error_message=exhausted_updates.get("error_message"),
                                last_result=exhausted_updates.get("last_result"),
                            ),
                        )
                        LOGGER.warning(
                            "zenn ready 记录质量重试次数已达上限，已兜底标记 failed，record_id=%s",
                            record["record_id"],
                        )
                        return
                    LOGGER.info("跳过 zenn ready 记录，record_id=%s，原因：%s", record["record_id"], reason)
                    return

                if not writer or not git_publisher:
                    raise ValueError("Zenn 发布器未初始化")
                process_zenn_ready(
                    record,
                    settings=settings,
                    feishu=feishu,
                    generator=generator,
                    image_manager=image_manager,
                    writer=writer,
                    git_publisher=git_publisher,
                    gate=gate,
                    notifier=notifier,
                )
            elif status == settings.status_queued.lower():
                if not git_publisher:
                    raise ValueError("Zenn Git 发布器未初始化")
                process_zenn_queued(
                    record,
                    settings=settings,
                    feishu=feishu,
                    git_publisher=git_publisher,
                    gate=gate,
                    notifier=notifier,
                )
            elif status == settings.status_waiting.lower():
                if not git_publisher:
                    raise ValueError("Zenn Git 发布器未初始化")
                process_zenn_waiting(
                    record,
                    settings=settings,
                    feishu=feishu,
                    git_publisher=git_publisher,
                    gate=gate,
                    notifier=notifier,
                )
            else:
                LOGGER.info("跳过未支持状态: %s", status)
            return

        if platform == "hatenablog":
            if status == settings.status_ready.lower():
                can_run, reason = can_attempt_quality_retry(record)
                if not can_run:
                    exhausted_updates = build_quality_retry_exhausted_update(record)
                    if exhausted_updates:
                        feishu.update_record(
                            record["record_id"],
                            build_write_fields(
                                settings,
                                status=exhausted_updates.get("status"),
                                retry_count=exhausted_updates.get("retry_count"),
                                error_message=exhausted_updates.get("error_message"),
                                last_result=exhausted_updates.get("last_result"),
                            ),
                        )
                        LOGGER.warning(
                            "hatena ready 记录质量重试次数已达上限，已兜底标记 failed，record_id=%s",
                            record["record_id"],
                        )
                        return
                    LOGGER.info("跳过 hatena ready 记录，record_id=%s，原因：%s", record["record_id"], reason)
                    return

                process_hatena_ready(
                    record,
                    settings=settings,
                    feishu=feishu,
                    generator=generator,
                    notifier=notifier,
                    hatena_publisher=hatena_publisher,
                )
            else:
                LOGGER.info("Hatena 跳过未支持状态: %s", status)
            return

        LOGGER.info("跳过未支持平台: %s", platform)

    except ArticleQualityError as exc:
        updates = on_quality_failure(record, str(exc))
        feishu.update_record(
            record["record_id"],
            build_write_fields(
                settings,
                status=updates.get("status"),
                retry_count=updates.get("retry_count"),
                error_message=updates.get("error_message"),
                last_result=updates.get("last_result"),
            ),
        )

        final_status = updates.get("status")
        if final_status == settings.status_failed:
            notifier.send(
                f"{platform or '未知平台'} 文章生成质量不足，已达到最大重试次数并标记为 failed\n"
                f"record_id：{record['record_id']}\n"
                f"标题：{record.get('source_title') or '(空)'}\n"
                f"错误：{exc}"
            )
        else:
            notifier.send(
                f"{platform or '未知平台'} 文章生成质量不足，已安排 1 小时后重试\n"
                f"record_id：{record['record_id']}\n"
                f"标题：{record.get('source_title') or '(空)'}\n"
                f"当前重试次数：{updates.get('retry_count')}\n"
                f"错误：{exc}"
            )

        LOGGER.warning("文章质量不足，已按规则处理：record_id=%s, status=%s, error=%s", record["record_id"], final_status, exc)

    except Exception as exc:
        err_text = f"{type(exc).__name__}: {exc}"
        if platform == "hatenablog" and is_retryable_hatena_publish_error(exc):
            updates = on_hatena_publish_failure(record, err_text)
            feishu.update_record(
                record["record_id"],
                build_write_fields(
                    settings,
                    status=updates.get("status"),
                    retry_count=updates.get("retry_count"),
                    error_message=updates.get("error_message"),
                    last_result=updates.get("last_result"),
                ),
            )

            final_status = updates.get("status")
            if final_status == settings.status_failed:
                notifier.send(
                    f"Hatena 发布失败，已达到最大自动重试次数并标记为 failed\n"
                    f"record_id：{record['record_id']}\n"
                    f"标题：{record.get('source_title') or '(空)'}\n"
                    f"错误：{err_text}"
                )
            else:
                notifier.send(
                    f"Hatena 发布失败，已安排 1 小时后自动重试\n"
                    f"record_id：{record['record_id']}\n"
                    f"标题：{record.get('source_title') or '(空)'}\n"
                    f"当前重试次数：{updates.get('retry_count')}\n"
                    f"错误：{err_text}"
                )
            LOGGER.warning("Hatena 发布失败，已按重试规则处理：record_id=%s, status=%s, error=%s", record["record_id"], final_status, err_text)
            return

        feishu.update_record(
            record["record_id"],
            build_write_fields(
                settings,
                status=settings.status_failed,
                error_message=err_text[:500],
                last_result=err_text[:500],
            ),
        )
        notifier.send(
            f"{platform or '未知平台'} 自动发布失败\n"
            f"record_id：{record['record_id']}\n"
            f"标题：{record.get('source_title') or '(空)'}\n"
            f"状态：{status}\n"
            f"错误：{err_text}"
        )
        LOGGER.error("处理失败\n%s", traceback.format_exc())


def build_runtime(settings: Settings) -> dict[str, Any]:
    feishu = FeishuClient(
        app_id=os.getenv("FEISHU_APP_ID", "").strip(),
        app_secret=os.getenv("FEISHU_APP_SECRET", "").strip(),
        app_token=os.getenv("FEISHU_APP_TOKEN", "").strip(),
        table_id=os.getenv("FEISHU_TABLE_ID", "").strip(),
    )
    generator = ArticleGenerator()
    image_manager = ImageManager()
    gate = PublishGate(
        control_file=settings.gate_control_file,
        timezone_name=settings.timezone_name,
        total_daily_push_limit=settings.gate_total_daily_push_limit,
        new_daily_push_limit=settings.gate_new_daily_push_limit,
        retry_cooldown_hours=settings.gate_retry_cooldown_hours,
        retry_daily_limit_per_slug=settings.gate_retry_daily_limit_per_slug,
    )
    notify_chat_id = os.getenv("FEISHU_NOTIFY_CHAT_ID", "").strip()
    notifier = BotNotifier(feishu, notify_chat_id, "chat_id")
    hatena_publisher = HatenaPublisher(settings.timezone_name)

    writer = None
    git_publisher = None
    if settings.target_platform in {"", "all", "zenn"} or os.getenv("ZENN_REPO_PATH", "").strip():
        if settings.zenn_repo_path:
            writer = ZennWriter(settings.zenn_repo_path)
            git_publisher = GitPublisher(
                repo_path=settings.zenn_repo_path,
                remote=settings.git_remote,
                branch=settings.git_branch,
                push_retry_times=int(os.getenv("GIT_PUSH_RETRY_TIMES", "3") or "3"),
            )

    return {
        "feishu": feishu,
        "generator": generator,
        "image_manager": image_manager,
        "gate": gate,
        "notifier": notifier,
        "hatena_publisher": hatena_publisher,
        "writer": writer,
        "git_publisher": git_publisher,
    }


def sort_process_candidates(candidates: list[dict[str, Any]], settings: Settings) -> None:
    status_priority = {
        settings.status_waiting.lower(): 0,
        settings.status_queued.lower(): 1,
        settings.status_ready.lower(): 2,
    }
    platform_priority = {"zenn": 0, "hatenablog": 1}
    candidates.sort(
        key=lambda x: (
            platform_priority.get(x["platform"], 99),
            status_priority.get(x["status"], 99),
            get_ready_retry_sort_penalty(x),
            x["publish_date"] or datetime.max.date(),
            x["record_id"],
        )
    )


def dispatch_candidates(
    candidates: list[dict[str, Any]],
    *,
    settings: Settings,
    runtime: dict[str, Any],
) -> None:
    sort_process_candidates(candidates, settings)
    for record in candidates:
        LOGGER.info(
            "开始处理 record_id=%s, platform=%s, status=%s, title=%s, publish_date=%s",
            record["record_id"],
            record["platform"],
            record["status"],
            record["source_title"] or "（空）",
            record["publish_date"],
        )
        LOGGER.info(
            "dispatch record_id=%s platform=%s status=%s hatena_account=%s title=%s publish_date=%s",
            record["record_id"],
            record["platform"],
            record["status"],
            record.get("hatena_account", ""),
            record["source_title"] or "（空）",
            record["publish_date"],
        )
        process_one_record(
            record,
            settings=settings,
            feishu=runtime["feishu"],
            generator=runtime["generator"],
            image_manager=runtime["image_manager"],
            writer=runtime["writer"],
            git_publisher=runtime["git_publisher"],
            gate=runtime["gate"],
            notifier=runtime["notifier"],
            hatena_publisher=runtime["hatena_publisher"],
        )


def run_normal_publish(settings: Settings, runtime: dict[str, Any], tz: tzinfo, today) -> None:
    with SingleInstanceLock():
        records = runtime["feishu"].list_all_records()
        payloads = [record_to_payload(item, settings, tz) for item in records]
        candidates = [r for r in payloads if should_process(r, settings, today)]

        LOGGER.info("今日可检查记录数: %s", len(candidates))
        if not candidates:
            return

        dispatch_candidates(candidates, settings=settings, runtime=runtime)


def run_self_check(settings: Settings, runtime: dict[str, Any], tz: tzinfo, today) -> None:
    with SingleInstanceLock():
        records = runtime["feishu"].list_all_records()
        payloads = [record_to_payload(item, settings, tz) for item in records]
        future_publish_date_records = [
            r
            for r in payloads
            if r.get("publish_date") is not None
            and r["publish_date"] > today
            and has_future_publish_date_after_publication(r, settings, tz)
        ]
        unpublished_today = [r for r in payloads if is_today_unpublished(r, settings, today)]

        LOGGER.info("self-check future publish_date after published count: %s", len(future_publish_date_records))
        if future_publish_date_records:
            future_publish_date_records.sort(
                key=lambda x: (
                    x.get("publish_date") or datetime.max.date(),
                    x.get("record_id") or "",
                )
            )
            runtime["notifier"].send(build_future_publish_date_notice(future_publish_date_records, settings, tz))

        LOGGER.info("self-check unpublished today count: %s", len(unpublished_today))
        if not unpublished_today:
            LOGGER.info("self-check passed: all today records are published or no today records")
            return

        sort_process_candidates(unpublished_today, settings)
        runtime["notifier"].send(build_self_check_notice(unpublished_today, settings, today))

        retry_candidates = [r for r in unpublished_today if should_process(r, settings, today)]
        if retry_candidates:
            dispatch_candidates(retry_candidates, settings=settings, runtime=runtime)
        else:
            LOGGER.info("self-check found no records safe for automatic retry")

        refreshed_records = runtime["feishu"].list_all_records()
        refreshed_payloads = [record_to_payload(item, settings, tz) for item in refreshed_records]
        remaining = [r for r in refreshed_payloads if is_today_unpublished(r, settings, today)]
        if remaining:
            sort_process_candidates(remaining, settings)
            runtime["notifier"].send(
                "Publish self-check finished, but some today records are still not published.\n"
                + build_self_check_notice(remaining, settings, today, include_retry_line=False)
            )
        else:
            runtime["notifier"].send(f"Publish self-check finished: all today records are published. date={today}")


def should_skip_before_publish_start(settings: Settings, now: datetime) -> bool:
    start_hour = min(max(settings.publish_start_hour, 0), 23)
    start_minute = min(max(settings.publish_start_minute, 0), 59)
    publish_start = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    if now >= publish_start:
        return False

    LOGGER.info(
        "publish skipped before daily start time: now=%s start=%s timezone=%s",
        now.isoformat(timespec="seconds"),
        publish_start.isoformat(timespec="seconds"),
        settings.timezone_name,
    )
    return True


def main() -> None:
    setup_logging()
    load_environment()

    settings = load_settings()
    tz = get_timezone(settings.timezone_name)
    now = datetime.now(tz)
    today = now.date()

    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode in {"--self-check", "self-check"}:
        runtime = build_runtime(settings)
        run_self_check(settings, runtime, tz, today)
        return

    if should_skip_before_publish_start(settings, now):
        return

    runtime = build_runtime(settings)
    run_normal_publish(settings, runtime, tz, today)


if __name__ == "__main__":
    main()
