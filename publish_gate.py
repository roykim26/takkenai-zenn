from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any, Optional
from timezone_utils import get_timezone


@dataclass
class GateDecision:
    allowed: bool
    reason: str


class PublishGate:
    def __init__(
        self,
        *,
        control_file: str,
        timezone_name: str,
        total_daily_push_limit: int,
        new_daily_push_limit: int,
        retry_cooldown_hours: int,
        retry_daily_limit_per_slug: int,
    ) -> None:
        self.control_path = Path(control_file)
        self.control_path.parent.mkdir(parents=True, exist_ok=True)
        self.tz = get_timezone(timezone_name)
        self.total_daily_push_limit = max(1, int(total_daily_push_limit))
        self.new_daily_push_limit = max(1, int(new_daily_push_limit))
        self.retry_cooldown_hours = max(1, int(retry_cooldown_hours))
        self.retry_daily_limit_per_slug = max(1, int(retry_daily_limit_per_slug))

    def _now(self) -> datetime:
        return datetime.now(self.tz)

    def _today_str(self) -> str:
        return self._now().date().isoformat()

    def _empty_state(self) -> dict[str, Any]:
        return {
            "today": self._today_str(),
            "total_push_count": 0,
            "new_publish_count": 0,
            "last_push_at": "",
            "last_new_push_at": "",
            "last_retry_at_by_slug": {},
            "retry_count_by_slug_today": {},
            "history": [],
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.control_path.exists():
            state = self._empty_state()
            self._save_state(state)
            return state

        try:
            state = json.loads(self.control_path.read_text(encoding="utf-8"))
        except Exception:
            state = self._empty_state()
            self._save_state(state)
            return state

        today = self._today_str()
        if state.get("today") != today:
            state["today"] = today
            state["total_push_count"] = 0
            state["new_publish_count"] = 0
            state["retry_count_by_slug_today"] = {}
            self._save_state(state)
        return state

    def _save_state(self, state: dict[str, Any]) -> None:
        self.control_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _parse_dt(value: str, tz: tzinfo) -> Optional[datetime]:
        text = (value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=tz)
            return dt.astimezone(tz)
        except Exception:
            return None

    def can_push_new(self) -> GateDecision:
        state = self._load_state()
        total_push_count = int(state.get("total_push_count", 0))
        new_publish_count = int(state.get("new_publish_count", 0))

        if total_push_count >= self.total_daily_push_limit:
            return GateDecision(False, f"已达到今日总 push 上限 {self.total_daily_push_limit}")
        if new_publish_count >= self.new_daily_push_limit:
            return GateDecision(False, f"已达到今日新发布上限 {self.new_daily_push_limit}")
        return GateDecision(True, "允许新发布 push")

    def can_retry(self, slug: str) -> GateDecision:
        state = self._load_state()
        total_push_count = int(state.get("total_push_count", 0))
        if total_push_count >= self.total_daily_push_limit:
            return GateDecision(False, f"已达到今日总 push 上限 {self.total_daily_push_limit}")

        retry_count_today = int(state.get("retry_count_by_slug_today", {}).get(slug, 0))
        if retry_count_today >= self.retry_daily_limit_per_slug:
            return GateDecision(False, f"slug={slug} 今日 retry 已达到上限 {self.retry_daily_limit_per_slug}")

        last_retry_at = self._parse_dt(state.get("last_retry_at_by_slug", {}).get(slug, ""), self.tz)
        if last_retry_at is None:
            return GateDecision(True, "允许 retry push")

        cooldown_until = last_retry_at + timedelta(hours=self.retry_cooldown_hours)
        now = self._now()
        if now < cooldown_until:
            return GateDecision(False, f"slug={slug} retry 冷却中，需等待到 {cooldown_until.strftime('%Y-%m-%d %H:%M:%S')}")

        return GateDecision(True, "允许 retry push")

    def mark_new_push(self, *, slug: str, record_id: str, commit: str) -> None:
        state = self._load_state()
        now_text = self._now().isoformat()
        state["total_push_count"] = int(state.get("total_push_count", 0)) + 1
        state["new_publish_count"] = int(state.get("new_publish_count", 0)) + 1
        state["last_push_at"] = now_text
        state["last_new_push_at"] = now_text
        history = list(state.get("history", []))
        history.append({
            "time": now_text,
            "type": "new_publish",
            "slug": slug,
            "record_id": record_id,
            "commit": commit,
        })
        state["history"] = history[-100:]
        self._save_state(state)

    def mark_retry_push(self, *, slug: str, record_id: str, commit: str) -> None:
        state = self._load_state()
        now_text = self._now().isoformat()
        state["total_push_count"] = int(state.get("total_push_count", 0)) + 1
        state["last_push_at"] = now_text

        retry_map = dict(state.get("last_retry_at_by_slug", {}))
        retry_map[slug] = now_text
        state["last_retry_at_by_slug"] = retry_map

        retry_count_map = dict(state.get("retry_count_by_slug_today", {}))
        retry_count_map[slug] = int(retry_count_map.get(slug, 0)) + 1
        state["retry_count_by_slug_today"] = retry_count_map

        history = list(state.get("history", []))
        history.append({
            "time": now_text,
            "type": "retry",
            "slug": slug,
            "record_id": record_id,
            "commit": commit,
        })
        state["history"] = history[-100:]
        self._save_state(state)
