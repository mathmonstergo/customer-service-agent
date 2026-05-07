from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


MESSAGE_RE = re.compile(r"^- \[(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2})\] (?P<speaker>.*?): (?P<content>.*)$")
LOW_VALUE_TOKENS = {"收到", "好的", "好", "👌", "[表情]", "[图片]"}
KEYWORDS = [
    "退款",
    "退货",
    "签收",
    "账号",
    "密码",
    "后台",
    "报告",
    "生成",
    "下载",
    "派发",
    "测评",
    "发票",
    "地址",
]


@dataclass(frozen=True)
class WechatMessage:
    sent_at: datetime
    speaker: str
    content: str


@dataclass(frozen=True)
class ChatChunk:
    start_at: datetime
    end_at: datetime
    message_count: int
    text: str
    keywords: list[str]


def parse_wechat_messages(markdown: str) -> list[WechatMessage]:
    """解析微信导出的 Markdown 消息，保留多行内容和回复引用。"""
    messages: list[WechatMessage] = []
    current: dict[str, object] | None = None
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        match = MESSAGE_RE.match(line)
        if match:
            if current is not None:
                messages.append(_build_message(current))
            current = {
                "sent_at": datetime.strptime(match.group("time"), "%Y-%m-%d %H:%M"),
                "speaker": match.group("speaker").strip(),
                "content": [match.group("content").strip()],
            }
            continue
        if current is not None and line.strip():
            current["content"].append(line.strip())  # type: ignore[index, union-attr]
    if current is not None:
        messages.append(_build_message(current))
    return messages


def chunk_messages(
    messages: list[WechatMessage],
    *,
    mode: str = "by_days",
    days: int = 1,
    gap_minutes: int = 30,
    max_messages: int = 120,
    max_chars: int = 8000,
) -> list[ChatChunk]:
    """按时间间隔和体量做可追溯粗切块，避免让 AI 决定原始边界。"""
    normalized_days = min(max(int(days), 1), 7)
    chunks: list[ChatChunk] = []
    current: list[WechatMessage] = []
    for message in messages:
        if _is_low_value(message):
            continue
        if current and _should_start_new_chunk(
            current,
            message,
            mode=mode,
            days=normalized_days,
            gap_minutes=gap_minutes,
            max_messages=max_messages,
            max_chars=max_chars,
        ):
            chunks.append(_build_chunk(current))
            current = []
        current.append(message)
    if current:
        chunks.append(_build_chunk(current))
    return chunks


def _build_message(raw: dict[str, object]) -> WechatMessage:
    """把解析中的临时字典收敛为消息对象。"""
    content_lines = raw["content"]
    if not isinstance(content_lines, list):
        content_lines = []
    return WechatMessage(
        sent_at=raw["sent_at"],  # type: ignore[arg-type]
        speaker=str(raw["speaker"]).strip(),
        content="\n".join(str(item).strip() for item in content_lines if str(item).strip()),
    )


def _is_low_value(message: WechatMessage) -> bool:
    """过滤明确无知识沉淀价值的系统消息和短确认。"""
    if message.speaker == "[系统]":
        return True
    normalized = message.content.strip()
    return normalized in LOW_VALUE_TOKENS


def _should_start_new_chunk(
    current_chunk: list[WechatMessage],
    next_message: WechatMessage,
    *,
    mode: str,
    days: int,
    gap_minutes: int,
    max_messages: int,
    max_chars: int,
) -> bool:
    """判断当前消息是否应开启新切块。"""
    previous = current_chunk[-1]
    if mode == "by_days" and (next_message.sent_at.date() - current_chunk[0].sent_at.date()).days >= days:
        return True
    if mode == "by_gap" and (next_message.sent_at - previous.sent_at).total_seconds() > gap_minutes * 60:
        return True
    if len(current_chunk) >= max_messages:
        return True
    current_chars = sum(len(message.content) + len(message.speaker) + 20 for message in current_chunk)
    next_chars = len(next_message.content) + len(next_message.speaker) + 20
    return current_chars + next_chars > max_chars


def _build_chunk(messages: list[WechatMessage]) -> ChatChunk:
    """从连续消息构造切块文本和关键词。"""
    lines = [
        f"[{message.sent_at:%Y-%m-%d %H:%M}] {message.speaker}: {message.content}"
        for message in messages
    ]
    text = "\n".join(lines)
    return ChatChunk(
        start_at=messages[0].sent_at,
        end_at=messages[-1].sent_at,
        message_count=len(messages),
        text=text,
        keywords=_extract_keywords(text),
    )


def _extract_keywords(text: str, limit: int = 4) -> list[str]:
    """用轻量关键词帮助审核列表扫描，不参与事实判断。"""
    found = [keyword for keyword in KEYWORDS if keyword in text]
    return found[:limit]
