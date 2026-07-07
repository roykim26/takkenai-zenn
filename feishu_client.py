from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

import requests


LOGGER = logging.getLogger(__name__)


class FeishuClient:
    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        timeout: int = 30,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self.timeout = timeout
        self._access_token: Optional[str] = None
        self._access_token_expire_at: float = 0.0

        if not self.app_id:
            raise ValueError("缺少 FEISHU_APP_ID")
        if not self.app_secret:
            raise ValueError("缺少 FEISHU_APP_SECRET")
        if not self.app_token:
            raise ValueError("缺少 FEISHU_APP_TOKEN")
        if not self.table_id:
            raise ValueError("缺少 FEISHU_TABLE_ID")

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expire_at - 60:
            return self._access_token

        url = f"{self.BASE_URL}/auth/v3/app_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0:
            raise RuntimeError(f"获取飞书 app_access_token 失败: {data}")

        self._access_token = data["app_access_token"]
        expire_seconds = int(data.get("expire", 7200))
        self._access_token_expire_at = now + expire_seconds
        return self._access_token

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        token = self._get_access_token()
        url = f"{self.BASE_URL}{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0:
            raise RuntimeError(f"飞书接口调用失败: {method} {path} => {data}")

        return data.get("data", {})

    def list_all_records(self, page_size: int = 200) -> list[dict[str, Any]]:
        path = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        items: list[dict[str, Any]] = []
        page_token: Optional[str] = None

        while True:
            params: Dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token

            data = self._request("GET", path, params=params)
            batch = data.get("items", [])
            items.extend(batch)

            if not data.get("has_more"):
                break
            page_token = data.get("page_token")

        return items

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        clean_fields = {k: v for k, v in fields.items() if k and v is not None}
        if not clean_fields:
            LOGGER.info("record=%s 没有可回写字段，跳过 update_record", record_id)
            return {}

        path = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}"
        return self._request("PUT", path, json_body={"fields": clean_fields})

    def send_bot_text(self, open_id: str, text: str) -> Dict[str, Any]:
        if not open_id:
            raise ValueError("open_id 为空，无法发送飞书消息")

        path = "/im/v1/messages"
        params = {"receive_id_type": "open_id"}
        content = json.dumps({"text": text}, ensure_ascii=False)
        payload = {
            "receive_id": open_id,
            "msg_type": "text",
            "content": content,
        }
        return self._request("POST", path, params=params, json_body=payload)

    @staticmethod
    def get_field_by_aliases(fields: Dict[str, Any], aliases: Iterable[str]) -> Any:
        if not fields:
            return None

        alias_map = {str(k).strip().lower(): v for k, v in fields.items()}
        for alias in aliases:
            alias_key = str(alias).strip().lower()
            if not alias_key:
                continue
            if alias_key in alias_map:
                return alias_map[alias_key]
        return None

    @staticmethod
    def to_text(value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, (int, float)):
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return str(value)

        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                text = FeishuClient.to_text(item)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()

        if isinstance(value, dict):
            for key in ("text", "name", "value", "title", "email", "link", "url"):
                if key in value and value[key] not in (None, ""):
                    return FeishuClient.to_text(value[key])
            return json.dumps(value, ensure_ascii=False)

        return str(value).strip()

    @staticmethod
    def to_int(value: Any, default: int = 0) -> int:
        text = FeishuClient.to_text(value)
        if not text:
            return default
        try:
            return int(float(text))
        except Exception:
            return default

    @staticmethod
    def to_bool(value: Any, default: bool = False) -> bool:
        text = FeishuClient.to_text(value).lower()
        if text in {"1", "true", "yes", "y", "是", "開", "on"}:
            return True
        if text in {"0", "false", "no", "n", "否", "关", "off"}:
            return False
        return default

    @staticmethod
    def parse_date(value: Any) -> Optional[datetime]:
        if value is None or value == "":
            return None

        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000.0
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)

        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None

            if text.isdigit():
                return FeishuClient.parse_date(int(text))

            text = text.replace("/", "-")
            candidates = [
                ("%Y-%m-%d", 10),
                ("%Y-%m-%d %H:%M", 16),
                ("%Y-%m-%d %H:%M:%S", 19),
                ("%Y-%m-%dT%H:%M:%S", 19),
                ("%Y-%m-%dT%H:%M:%S%z", None),
            ]
            for fmt, cut in candidates:
                try:
                    candidate = text if cut is None else text[:cut]
                    dt = datetime.strptime(candidate, fmt)
                    if dt.tzinfo is None:
                        return dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    continue

            try:
                dt = datetime.fromisoformat(text)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return None

        if isinstance(value, dict):
            for key in ("value", "text"):
                if key in value:
                    return FeishuClient.parse_date(value[key])

        if isinstance(value, list) and value:
            return FeishuClient.parse_date(value[0])

        return None
