from __future__ import annotations

import socket
import sys
import time
import traceback

from customer_service_agent.config import Settings
from customer_service_agent.rag import RagService
from customer_service_agent.wechat_client import WxBotClient


def split_text(text: str, limit: int = 1800) -> list[str]:
    if not text.strip():
        return ["..."]
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        parts = [line[index : index + limit] for index in range(0, len(line), limit)] or [line]
        for part in parts:
            if len(part) == limit:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(part)
            elif current and len(current) + len(part) + 1 > limit:
                chunks.append(current)
                current = part
            else:
                current = f"{current}\n{part}" if current else part
    if current:
        chunks.append(current)
    return chunks or ["..."]


def _send_text_safely(bot: WxBotClient, uid: str, text: str, context_token: str = "") -> None:
    try:
        bot.send_text(uid, text, context_token=context_token)
    except Exception:
        print("[WeChat] send_text failed", file=sys.stderr)
        traceback.print_exc()


def login_wechat(settings: Settings) -> None:
    bot = WxBotClient(settings.wechat_token_file)
    bot.login_qr()


def handle_message(bot: WxBotClient, rag: RagService, settings: Settings, msg: dict) -> None:
    text = bot.extract_text(msg).strip()
    if not text:
        return
    uid = msg.get("from_user_id", "")
    context_token = msg.get("context_token", "")
    if text == "/ping":
        _send_text_safely(bot, uid, "pong", context_token=context_token)
        return
    if text == "/reload":
        _send_text_safely(bot, uid, "配置重载将在下一版支持；当前服务在线。", context_token=context_token)
        return
    try:
        answer = rag.answer(text)
    except Exception:
        traceback.print_exc()
        answer = "服务暂时不可用，请稍后重试；如问题紧急，请转人工处理。"
    for chunk in split_text(answer, settings.wechat_message_chunk_size):
        _send_text_safely(bot, uid, chunk, context_token=context_token)
        time.sleep(0.3)


def run_service(settings: Settings) -> None:
    from customer_service_agent.cli import build_rag

    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", 19529))
    except OSError:
        print("[WeChat] Another customer-service-agent service instance is running", file=sys.stderr)
        raise SystemExit(1)

    bot = WxBotClient(settings.wechat_token_file)
    if not bot.token:
        raise RuntimeError("WeChat token missing. Run `customer-service-agent wechat-login` first.")

    rag = build_rag(settings)
    seen: set[str] = set()
    print(f"WeChat RAG service started (bot_id={bot.bot_id})")
    while True:
        try:
            updates = bot.get_updates(30)
            for msg in updates:
                try:
                    message_id = str(msg.get("message_id", ""))
                    if not bot.is_user_msg(msg) or message_id in seen:
                        continue
                    seen.add(message_id)
                    if len(seen) > 5000:
                        seen = set(list(seen)[-2000:])
                    handle_message(bot, rag, settings, msg)
                except Exception:
                    print("[WeChat] message handling failed", file=sys.stderr)
                    traceback.print_exc()
                    time.sleep(5)
        except Exception:
            print("[WeChat] service loop failed", file=sys.stderr)
            traceback.print_exc()
            time.sleep(5)
