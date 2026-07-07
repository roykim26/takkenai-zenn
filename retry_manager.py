from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

JST = timezone(timedelta(hours=9))

QUALITY_PREFIX = "[QUALITY_RETRY]"
HATENA_PUBLISH_PREFIX = "[HATENA_PUBLISH_RETRY]"

DEFAULT_MAX_QUALITY_RETRY = 3
DEFAULT_MAX_HATENA_PUBLISH_RETRY = 3
QUALITY_RETRY_DELAY_HOURS = 1
HATENA_PUBLISH_RETRY_DELAY_HOURS = 1

REASON_RETRY_COUNT_EXCEEDED = "retry count exceeded"


def now_jst() -> datetime:
    return datetime.now(JST)


def _read_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return value if value >= 1 else default


def get_max_quality_retry() -> int:
    return _read_positive_int_env("ARTICLE_MAX_QUALITY_RETRY", DEFAULT_MAX_QUALITY_RETRY)


def get_max_hatena_publish_retry() -> int:
    return _read_positive_int_env("HATENA_PUBLISH_MAX_RETRY", DEFAULT_MAX_HATENA_PUBLISH_RETRY)


def get_status_ready() -> str:
    return os.getenv("STATUS_READY", "ready").strip() or "ready"


def get_status_failed() -> str:
    return os.getenv("STATUS_FAILED", "failed").strip() or "failed"


def parse_retry_count(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_parse_dt(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _build_retry_error(
    *,
    prefix: str,
    kind: str,
    attempt: int,
    reason: str,
    retry_after: datetime,
) -> str:
    payload = {
        "kind": kind,
        "attempt": attempt,
        "reason": reason,
        "retry_after": retry_after.isoformat(),
    }
    return f"{prefix} {json.dumps(payload, ensure_ascii=False)}"


def build_quality_retry_error(
    attempt: int,
    reason: str,
    retry_after: datetime,
) -> str:
    return _build_retry_error(
        prefix=QUALITY_PREFIX,
        kind="quality_retry",
        attempt=attempt,
        reason=reason,
        retry_after=retry_after,
    )


def build_hatena_publish_retry_error(
    attempt: int,
    reason: str,
    retry_after: datetime,
) -> str:
    return _build_retry_error(
        prefix=HATENA_PUBLISH_PREFIX,
        kind="hatena_publish_retry",
        attempt=attempt,
        reason=reason,
        retry_after=retry_after,
    )


def parse_retry_error(error_message: str | None) -> Optional[Dict[str, Any]]:
    if not error_message:
        return None

    text = str(error_message).strip()
    prefix = None
    if text.startswith(QUALITY_PREFIX):
        prefix = QUALITY_PREFIX
    elif text.startswith(HATENA_PUBLISH_PREFIX):
        prefix = HATENA_PUBLISH_PREFIX

    if not prefix:
        return None

    raw = text[len(prefix):].strip()
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        payload["_prefix"] = prefix
        return payload
    except Exception:
        return None


def parse_quality_retry_error(error_message: str | None) -> Optional[Dict[str, Any]]:
    payload = parse_retry_error(error_message)
    if not payload:
        return None
    return payload if payload.get("kind") == "quality_retry" else None


def _get_retry_limit(payload: Optional[Dict[str, Any]]) -> int:
    if payload and payload.get("kind") == "hatena_publish_retry":
        return get_max_hatena_publish_retry()
    return get_max_quality_retry()


def can_attempt_quality_retry(record: Dict[str, Any], now: Optional[datetime] = None) -> Tuple[bool, str]:
    now = now or now_jst()

    status = str(record.get("status") or "").strip().lower()
    failed_status = get_status_failed().lower()
    if status == failed_status:
        return False, "record already failed"

    payload = parse_retry_error(record.get("error_message"))
    retry_count = parse_retry_count(record.get("retry_count"))
    if retry_count >= _get_retry_limit(payload):
        return False, REASON_RETRY_COUNT_EXCEEDED

    if not payload:
        return True, "no retry schedule"

    retry_after = _safe_parse_dt(payload.get("retry_after"))
    if not retry_after:
        return True, "invalid retry_after, allow attempt"

    if now < retry_after:
        return False, f"wait until {retry_after.isoformat()}"

    return True, "retry window reached"


def build_quality_retry_exhausted_update(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    status = str(record.get("status") or "").strip().lower()
    failed_status = get_status_failed()
    if status == failed_status.lower():
        return None

    payload = parse_retry_error(record.get("error_message"))
    retry_count = parse_retry_count(record.get("retry_count"))
    if retry_count < _get_retry_limit(payload):
        return None

    if payload and payload.get("kind") == "hatena_publish_retry":
        return {
            "status": failed_status,
            "retry_count": retry_count,
            "last_result": "hatena_publish_failed_max_retry_dirty_record",
            "error_message": "hatena publish retry count already exceeded; marked failed by safety fallback",
        }

    return {
        "status": failed_status,
        "retry_count": retry_count,
        "last_result": "quality_failed_max_retry_dirty_record",
        "error_message": "quality retry count already exceeded; marked failed by safety fallback",
    }


def on_quality_failure(
    record: Dict[str, Any],
    reason: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or now_jst()
    current_retry = parse_retry_count(record.get("retry_count"))
    next_retry = current_retry + 1

    updates: Dict[str, Any] = {
        "retry_count": next_retry,
    }

    if next_retry >= get_max_quality_retry():
        updates.update({
            "status": get_status_failed(),
            "last_result": "quality_failed_max_retry",
            "error_message": reason[:1000],
        })
        return updates

    retry_after = now + timedelta(hours=QUALITY_RETRY_DELAY_HOURS)
    updates.update({
        "status": get_status_ready(),
        "last_result": "quality_retry_scheduled",
        "error_message": build_quality_retry_error(
            attempt=next_retry,
            reason=reason[:500],
            retry_after=retry_after,
        ),
    })
    return updates


def is_retryable_hatena_publish_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    lower_text = text.lower()

    code_match = re.search(r"http\s+(\d{3})", text, flags=re.IGNORECASE)
    if code_match:
        code = int(code_match.group(1))
        return code in {408, 409, 425, 429, 500, 502, 503, 504}

    transient_markers = (
        "timeout",
        "timed out",
        "connection reset",
        "connection aborted",
        "connection refused",
        "connection error",
        "temporarily unavailable",
        "proxyerror",
        "remote disconnected",
    )
    return any(marker in lower_text for marker in transient_markers)


def on_hatena_publish_failure(
    record: Dict[str, Any],
    reason: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or now_jst()
    current_retry = parse_retry_count(record.get("retry_count"))
    next_retry = current_retry + 1

    updates: Dict[str, Any] = {
        "retry_count": next_retry,
    }

    if next_retry >= get_max_hatena_publish_retry():
        updates.update({
            "status": get_status_failed(),
            "last_result": "hatena_publish_failed_max_retry",
            "error_message": reason[:1000],
        })
        return updates

    retry_after = now + timedelta(hours=HATENA_PUBLISH_RETRY_DELAY_HOURS)
    updates.update({
        "status": get_status_ready(),
        "last_result": "hatena_publish_retry_scheduled",
        "error_message": build_hatena_publish_retry_error(
            attempt=next_retry,
            reason=reason[:500],
            retry_after=retry_after,
        ),
    })
    return updates


def on_publish_success() -> Dict[str, Any]:
    return {
        "retry_count": 0,
        "error_message": "",
        "last_result": "published",
    }
