from __future__ import annotations

import json
import logging

from feishu_client import FeishuClient


LOGGER = logging.getLogger(__name__)


class BotNotifier:
    def __init__(self, feishu_client: FeishuClient, chat_id: str, receive_id_type: str = "chat_id") -> None:
        self.feishu_client = feishu_client
        self.chat_id = (chat_id or "").strip()
        self.receive_id_type = (receive_id_type or "chat_id").strip() or "chat_id"

    def send(self, text: str) -> bool:
        if not self.chat_id:
            LOGGER.warning("未配置 FEISHU_NOTIFY_CHAT_ID，跳过飞书群聊通知")
            return False

        try:
            content = json.dumps({"text": text}, ensure_ascii=False)
            self.feishu_client._request(
                "POST",
                "/im/v1/messages",
                params={"receive_id_type": self.receive_id_type},
                json_body={
                    "receive_id": self.chat_id,
                    "msg_type": "text",
                    "content": content,
                },
            )
            return True
        except Exception as exc:
            LOGGER.exception("飞书群聊通知发送失败: %s", exc)
            return False
