from __future__ import annotations

import base64
import json
import os
import struct
import sys
import time
import uuid
import webbrowser
from pathlib import Path

import qrcode
import requests

API = "https://ilinkai.weixin.qq.com"
VER = "2.1.8"
MSG_USER = 1
MSG_BOT = 2
ITEM_TEXT = 1
STATE_FINISH = 2


def _uin() -> str:
    return base64.b64encode(str(struct.unpack(">I", os.urandom(4))[0]).encode()).decode()


class WxBotClient:
    def __init__(self, token_file: str | Path):
        self._tf = Path(token_file)
        self._tf.parent.mkdir(parents=True, exist_ok=True)
        self._tf.parent.chmod(0o700)
        self.token = ""
        self.bot_id = ""
        self._buf = ""
        self._load()

    def _load(self) -> None:
        if not self._tf.exists():
            return
        try:
            data = json.loads(self._tf.read_text("utf-8"))
        except (OSError, ValueError):
            print(f"[WeChat] token file is unreadable; starting empty: {self._tf}", file=sys.stderr)
            self.token = ""
            self.bot_id = ""
            self._buf = ""
            return
        if not isinstance(data, dict):
            print(f"[WeChat] token file is not an object; starting empty: {self._tf}", file=sys.stderr)
            self.token = ""
            self.bot_id = ""
            self._buf = ""
            return
        self.token = data.get("bot_token", "")
        self.bot_id = data.get("ilink_bot_id", "")
        self._buf = data.get("updates_buf", "")

    def _save(self, **extra: object) -> None:
        data = {
            "bot_token": self.token,
            "ilink_bot_id": self.bot_id,
            "updates_buf": self._buf,
            **extra,
        }
        self._tf.parent.mkdir(parents=True, exist_ok=True)
        self._tf.parent.chmod(0o700)
        tmp = self._tf.with_name(f".{self._tf.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            tmp.chmod(0o600)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        os.replace(tmp, self._tf)

    def _post(self, endpoint: str, body: dict, timeout: int = 15) -> dict:
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": _uin(),
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = requests.post(f"{API}/{endpoint}", json=body, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def login_qr(self, poll_interval: int = 2) -> None:
        response = requests.get(f"{API}/ilink/bot/get_bot_qrcode", params={"bot_type": 3}, timeout=10)
        response.raise_for_status()
        data = response.json()
        qr_id = data["qrcode"]
        url = data.get("qrcode_img_content", "")
        print(f"[QR登录] ID: {qr_id}")
        if url:
            image_path = self._tf.parent / "wx_qr.png"
            qrcode.make(url).save(str(image_path))
            webbrowser.open(str(image_path))
            print(f"[QR登录] 二维码文件: {image_path}")
        last_status = ""
        while True:
            time.sleep(poll_interval)
            status_response = requests.get(
                f"{API}/ilink/bot/get_qrcode_status",
                params={"qrcode": qr_id},
                timeout=60,
            ).json()
            status = status_response.get("status", "")
            if status != last_status:
                print(f"  状态: {status}")
                last_status = status
            if status == "confirmed":
                self.token = status_response.get("bot_token", "")
                self.bot_id = status_response.get("ilink_bot_id", "")
                self._save(login_time=time.strftime("%Y-%m-%d %H:%M:%S"))
                print(f"[QR登录] 成功! bot_id={self.bot_id}")
                return
            if status == "expired":
                raise RuntimeError("二维码过期")

    def get_updates(self, timeout: int = 30) -> list[dict]:
        try:
            response = self._post(
                "ilink/bot/getupdates",
                {"get_updates_buf": self._buf, "base_info": {"channel_version": VER}},
                timeout=timeout + 5,
            )
        except requests.exceptions.ReadTimeout:
            return []
        except (requests.RequestException, ValueError) as exc:
            print(f"[getUpdates] request failed: {exc}", file=sys.stderr)
            time.sleep(5)
            return []
        if response.get("errcode"):
            print(
                f"[getUpdates] err: {response.get('errcode')} {response.get('errmsg', '')}",
                file=sys.stderr,
            )
            if response["errcode"] == -14:
                self._buf = ""
                self._save()
            return []
        next_buf = response.get("get_updates_buf", "")
        if next_buf:
            self._buf = next_buf
            self._save()
        return response.get("msgs") or []

    def send_text(self, to_user_id: str, text: str, context_token: str = "") -> dict:
        msg = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": f"pyclient-{uuid.uuid4().hex[:16]}",
            "message_type": MSG_BOT,
            "message_state": STATE_FINISH,
            "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
        }
        if context_token:
            msg["context_token"] = context_token
        return self._post("ilink/bot/sendmessage", {"msg": msg, "base_info": {"channel_version": VER}})

    @staticmethod
    def extract_text(msg: dict) -> str:
        return "\n".join(
            item["text_item"].get("text", "")
            for item in msg.get("item_list", [])
            if item.get("type") == ITEM_TEXT and item.get("text_item")
        )

    @staticmethod
    def is_user_msg(msg: dict) -> bool:
        return msg.get("message_type") == MSG_USER
