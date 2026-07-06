from __future__ import annotations

# 本模块的 naive merge / children split 逻辑按 RAGFlow rag/nlp/__init__.py
# 适配；RAGFlow 源码使用 Apache License 2.0。

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable


logger = logging.getLogger(__name__)

TokenCounter = Callable[[str], int]
PDF_POSITIONS_KEY = "_pdf_positions"
PDF_POSITION_TAG_RE = re.compile(r"@@([0-9-]+)\t([0-9.]+)\t([0-9.]+)\t([0-9.]+)\t([0-9.]+)##")


@dataclass(frozen=True)
class StructuredChunk:
    """表示按 RAGFlow naive merge 合并后的结构化 chunk。"""

    text: str
    source_blocks: list[dict[str, Any]]
    section_path: list[str]
    page_start: int | None
    page_end: int | None
    block_type: str
    source_offsets: dict[str, Any]


def num_tokens_from_string(text: str) -> int:
    """按 RAGFlow token_utils 口径计数；缺少 tiktoken 时退回字符近似值。

    关键约束：只对 ImportError 静默回退（依赖未安装是预期场景）；其它异常打 warning
    并仍然回退，避免真实 bug 被静默吞掉导致排查困难。
    """
    try:
        import tiktoken

        encoder = tiktoken.get_encoding("cl100k_base")
        return len(encoder.encode(text))
    except ImportError:
        return len(str(text or ""))
    except Exception as exc:
        logger.warning(
            "tiktoken token count failed, fallback to char count: %s", exc, exc_info=True
        )
        return len(str(text or ""))


def normalize_children_delimiter(delimiter: str | None) -> str:
    """把 children_delimiter 转成 RAGFlow split_with_pattern 可用的正则片段。"""
    if not delimiter:
        return ""
    try:
        text = str(delimiter).encode("utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        text = str(delimiter)
    custom_delimiters = sorted(
        {match.group(1) for match in re.finditer(r"`([^`]+)`", text) if match.group(1)},
        key=lambda item: -len(item),
    )
    normal_text = re.sub(r"`([^`]+)`", "", text)
    parts = [re.escape(char) for char in normal_text if char]
    parts.extend(re.escape(item) for item in custom_delimiters)
    return "|".join(parts)


def split_with_pattern(content: str, pattern: str) -> list[str]:
    """按 RAGFlow split_with_pattern 规则拆 child，并把分隔符留在前一段。"""
    text = str(content or "")
    if not text.strip():
        return []
    if not pattern:
        return [text]
    try:
        compiled_pattern = re.compile(r"(%s)" % pattern, flags=re.DOTALL)
    except re.error:
        return [text]
    pieces = compiled_pattern.split(text)
    chunks: list[str] = []
    for index in range(0, len(pieces), 2):
        chunk = pieces[index]
        if not chunk:
            continue
        if index + 1 < len(pieces):
            chunk += pieces[index + 1]
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def attach_media_context_to_blocks(
    blocks: Iterable[dict[str, Any]],
    *,
    table_context_size: int = 0,
    image_context_size: int = 0,
    token_counter: TokenCounter = num_tokens_from_string,
) -> list[dict[str, Any]]:
    """按 RAGFlow attach_media_context 思路给表格/图片块补邻近文本。"""
    # 保留有文字 / 或有资产路径的媒体块；后者文字为空但是是图/表实体，不能在这里被过滤掉。
    normalized = [_normalize_block(block) for block in blocks if _has_content(block)]
    if not normalized or (table_context_size <= 0 and image_context_size <= 0):
        return normalized

    ordered = _order_blocks_by_pdf_position(normalized)
    result: list[dict[str, Any]] = []
    for index, block in enumerate(ordered):
        budget = _media_context_budget(block, table_context_size, image_context_size)
        if budget <= 0:
            result.append(block)
            continue
        before, after = _overlapping_media_context(ordered, index, budget, token_counter)
        if not before and not after:
            before = _neighbor_context(ordered, index, budget, token_counter, reverse=True)
            after = _neighbor_context(ordered, index, budget, token_counter, reverse=False)
        if not before and not after:
            result.append(block)
            continue
        enriched = dict(block)
        enriched["context_above"] = before
        enriched["context_below"] = after
        enriched["text"] = "\n".join(part for part in (before, block["text"], after) if part)
        evidence = dict(enriched.get("evidence") or {})
        evidence["media_context"] = {"before": before, "after": after}
        enriched["evidence"] = evidence
        result.append(enriched)
    return result


def extract_pdf_positions(block: dict[str, Any]) -> list[list[float]]:
    """按 RAGFlow extract_pdf_positions 口径统一 PDF 坐标字段。"""
    if not isinstance(block, dict):
        return []
    raw_positions = _raw_pdf_positions(block)
    uses_position_tag = bool(isinstance(block.get("position_tag"), str) and block.get("position_tag"))
    ref_page = _optional_int(block.get("page_number"))
    if ref_page is not None and ref_page <= 0:
        ref_page += 1

    positions: list[list[float]] = []
    for raw in raw_positions:
        if not isinstance(raw, (list, tuple)) or len(raw) < 5:
            continue
        page_value = raw[0][-1] if isinstance(raw[0], (list, tuple)) else raw[0]
        try:
            page_number = int(page_value)
            if uses_position_tag and page_number <= 0:
                page_number += 1
            elif ref_page is not None and page_number == ref_page - 1:
                page_number = ref_page
            elif page_number <= 0:
                page_number += 1
            left = float(raw[1])
            right = float(raw[2])
            top = float(raw[3])
            bottom = float(raw[4])
        except (TypeError, ValueError):
            continue
        if right < left:
            left, right = right, left
        if bottom < top:
            top, bottom = bottom, top
        positions.append([page_number, left, right, top, bottom])
    return positions


def _raw_pdf_positions(block: dict[str, Any]) -> list[Any]:
    """读取 RAGFlow 兼容的多种原始坐标字段。"""
    for key in (PDF_POSITIONS_KEY, "pdf_positions", "positions"):
        value = block.get(key)
        if isinstance(value, list):
            return value

    evidence = block.get("evidence") if isinstance(block.get("evidence"), dict) else {}
    for key in (PDF_POSITIONS_KEY, "pdf_positions", "positions"):
        value = evidence.get(key)
        if isinstance(value, list):
            return value

    position_tag = block.get("position_tag") or evidence.get("position_tag")
    if isinstance(position_tag, str) and position_tag:
        return _positions_from_tag(position_tag)

    position_int = block.get("position_int") or evidence.get("position_int")
    if isinstance(position_int, list):
        return [list(pos) for pos in position_int if isinstance(pos, (list, tuple)) and len(pos) >= 5]

    values = [block.get(key) for key in ("page_number", "x0", "x1", "top", "bottom")]
    if values[0] is not None and all(value is not None for value in values[1:]):
        return [values]
    return []


def _positions_from_tag(position_tag: str) -> list[list[Any]]:
    """解析 RAGFlow @@page 坐标 tag，页码先按 0 起始保存再统一归一。"""
    positions: list[list[Any]] = []
    for match in PDF_POSITION_TAG_RE.finditer(position_tag):
        page_text, left, right, top, bottom = match.groups()
        pages = [int(page) - 1 for page in page_text.split("-") if page]
        if not pages:
            continue
        positions.append([pages, float(left), float(right), float(top), float(bottom)])
    return positions


def ragflow_naive_merge_blocks(
    blocks: Iterable[dict[str, Any]],
    *,
    chunk_token_num: int = 512,
    delimiter: str = "\n。；！？",
    overlapped_percent: int = 0,
    token_counter: TokenCounter = num_tokens_from_string,
) -> list[StructuredChunk]:
    """按 RAGFlow naive_merge 思路合并结构块，同时保留结构化来源。"""
    # 保留两类块：①有文字的块；②虽然没文字但带资产路径的媒体块（image/table/equation）。
    # 后者是 MinerU 对无 caption 截图的常见输出 —— 只看 text 会让 image 块在 merge 阶段被砍光。
    normalized = [_normalize_block(block) for block in blocks if _has_content(block)]
    if not normalized:
        return []

    custom_delimiters = [
        match.group(1)
        for match in re.finditer(r"`([^`]+)`", delimiter or "")
        if match.group(1)
    ]
    if custom_delimiters:
        return _split_blocks_by_custom_delimiters(
            normalized,
            sorted(set(custom_delimiters), key=lambda item: -len(item)),
        )

    threshold = max(chunk_token_num, 0) * (100 - _normalize_overlap(overlapped_percent)) / 100
    current_text = ""
    current_blocks: list[dict[str, Any]] = []
    current_tokens = 0
    chunks: list[StructuredChunk] = []

    for block in normalized:
        block_text = "\n" + _block_text(block)
        block_tokens = token_counter(block_text)
        if not current_text or current_tokens > threshold:
            if current_text:
                chunks.append(_structured_chunk(current_text, current_blocks))
            overlap_text = _overlap_tail(current_text, overlapped_percent)
            current_text = (overlap_text + block_text).strip()
            current_blocks = [block]
            current_tokens = block_tokens
            continue

        current_text = (current_text + block_text).strip()
        current_blocks.append(block)
        current_tokens += block_tokens

    if current_text:
        chunks.append(_structured_chunk(current_text, current_blocks))
    return chunks


def _media_context_budget(
    block: dict[str, Any],
    table_context_size: int,
    image_context_size: int,
) -> int:
    """判断媒体块上下文预算，非媒体块返回 0。"""
    block_type = str(block.get("block_type") or "").strip().lower()
    if block_type == "table":
        return max(int(table_context_size or 0), 0)
    if block_type in {"image", "figure"}:
        return max(int(image_context_size or 0), 0)
    return 0


def _order_blocks_by_pdf_position(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """有 PDF 坐标时按页码、纵向、横向排序，模拟 RAGFlow 的阅读顺序。"""
    positioned = []
    unpositioned = []
    for index, block in enumerate(blocks):
        positions = extract_pdf_positions(block)
        if positions:
            page, left, _right, top, _bottom = positions[0]
            positioned.append((int(page), float(top), float(left), index, block))
        else:
            unpositioned.append((index, block))
    if not positioned:
        return blocks
    return [item[-1] for item in sorted(positioned)] + [block for _index, block in unpositioned]


def _overlapping_media_context(
    blocks: list[dict[str, Any]],
    media_index: int,
    token_budget: int,
    token_counter: TokenCounter,
) -> tuple[str, str]:
    """媒体块与文本坐标重叠时，从最接近的文本块中拆前后上下文。"""
    media_bounds = _bounds_by_page(blocks[media_index])
    if not media_bounds:
        return "", ""

    best_text = ""
    best_distance: float | None = None
    for index, block in enumerate(blocks):
        if index == media_index or _media_context_budget(block, 1, 1) > 0:
            continue
        for page_number, (text_top, text_bottom) in _bounds_by_page(block).items():
            if page_number not in media_bounds:
                continue
            media_top, media_bottom = media_bounds[page_number]
            if media_bottom < text_top or media_top > text_bottom:
                continue
            media_mid = (media_top + media_bottom) / 2
            text_mid = (text_top + text_bottom) / 2
            distance = abs(media_mid - text_mid)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_text = str(block.get("text") or "")

    if not best_text:
        return "", ""
    sentences = _split_sentences(best_text)
    if not sentences:
        return "", ""
    boundary = _middle_sentence_index(sentences, token_counter)
    before, after = _context_around_sentence_boundary(
        sentences,
        boundary,
        token_budget,
        token_counter,
    )
    return before.strip(), after.strip()


def _bounds_by_page(block: dict[str, Any]) -> dict[int, tuple[float, float]]:
    """把一个块的多个坐标压成每页的 top/bottom 范围。"""
    bounds: dict[int, tuple[float, float]] = {}
    for page_number, _left, _right, top, bottom in extract_pdf_positions(block):
        page = int(page_number)
        top_value = float(top)
        bottom_value = float(bottom)
        if bottom_value < top_value:
            top_value, bottom_value = bottom_value, top_value
        if page in bounds:
            bounds[page] = (
                min(bounds[page][0], top_value),
                max(bounds[page][1], bottom_value),
            )
        else:
            bounds[page] = (top_value, bottom_value)
    return bounds


def _neighbor_context(
    blocks: list[dict[str, Any]],
    media_index: int,
    token_budget: int,
    token_counter: TokenCounter,
    *,
    reverse: bool,
) -> str:
    """收集媒体块前后最近的文本上下文，优先同页并遵守 token 预算。"""
    collected: list[str] = []
    remaining = token_budget
    indices = range(media_index - 1, -1, -1) if reverse else range(media_index + 1, len(blocks))
    for index in indices:
        block = blocks[index]
        if _media_context_budget(block, table_context_size=1, image_context_size=1) > 0:
            continue
        text = block.get("text", "")
        picked = _take_context_text(text, remaining, token_counter, from_tail=reverse)
        if not picked:
            continue
        collected.append(picked)
        remaining -= token_counter(picked)
        if remaining <= 0:
            break
    if reverse:
        collected.reverse()
    return "\n".join(collected).strip()


def _take_context_text(
    text: str,
    token_budget: int,
    token_counter: TokenCounter,
    *,
    from_tail: bool,
) -> str:
    """按句子粒度截取上下文，保留超预算首句以匹配 RAGFlow 容忍策略。"""
    if token_budget <= 0:
        return ""
    sentences = _split_sentences(text)
    if from_tail:
        sentences = list(reversed(sentences))
    picked = []
    remaining = token_budget
    for sentence in sentences:
        tokens = token_counter(sentence)
        if tokens <= 0:
            continue
        picked.append(sentence)
        remaining -= tokens
        if remaining <= 0:
            break
    if from_tail:
        picked.reverse()
    return "".join(picked).strip()


def _middle_sentence_index(sentences: list[str], token_counter: TokenCounter) -> int:
    """按 RAGFlow find_mid_sentence_index 逻辑找到文本中点附近句子。"""
    if not sentences:
        return 0
    total = sum(max(0, token_counter(sentence)) for sentence in sentences)
    if total <= 0:
        return max(0, len(sentences) // 2)
    target = total / 2
    best_index = 0
    best_diff: float | None = None
    current = 0
    for index, sentence in enumerate(sentences):
        current += max(0, token_counter(sentence))
        diff = abs(current - target)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_index = index
    return best_index


def _context_around_sentence_boundary(
    sentences: list[str],
    boundary_index: int,
    token_budget: int,
    token_counter: TokenCounter,
) -> tuple[str, str]:
    """从边界句前后各取一段上下文，超预算句子按 RAGFlow 策略保留。"""
    before_parts: list[str] = []
    remaining_before = token_budget
    for sentence in reversed(sentences[: boundary_index + 1]):
        if remaining_before <= 0:
            break
        picked = _take_context_text(sentence, remaining_before, token_counter, from_tail=True)
        if not picked:
            continue
        before_parts.append(picked)
        remaining_before -= token_counter(picked)
    before_parts.reverse()

    after_parts: list[str] = []
    remaining_after = token_budget
    for sentence in sentences[boundary_index + 1 :]:
        if remaining_after <= 0:
            break
        picked = _take_context_text(sentence, remaining_after, token_counter, from_tail=False)
        if not picked:
            continue
        after_parts.append(picked)
        remaining_after -= token_counter(picked)
    return "".join(before_parts), "".join(after_parts)


def _split_sentences(text: str) -> list[str]:
    """按 RAGFlow 媒体上下文的中英文标点规则粗分句。"""
    parts = re.split(r"([.。！？!?；;：:\n])", str(text or ""))
    sentences = []
    buffer = ""
    for part in parts:
        if not part:
            continue
        buffer += part
        if re.fullmatch(r"[.。！？!?；;：:\n]", part):
            sentences.append(buffer)
            buffer = ""
    if buffer:
        sentences.append(buffer)
    return sentences


def _split_blocks_by_custom_delimiters(
    blocks: list[dict[str, Any]],
    custom_delimiters: list[str],
) -> list[StructuredChunk]:
    """处理 RAGFlow 反引号自定义分隔符，每个子段独立成 chunk。"""
    pattern = "|".join(re.escape(item) for item in custom_delimiters)
    chunks: list[StructuredChunk] = []
    for block in blocks:
        for piece in re.split(r"(%s)" % pattern, _block_text(block), flags=re.DOTALL):
            if not piece or re.fullmatch(pattern, piece):
                continue
            child = {**block, "text": piece.strip()}
            if child["text"]:
                chunks.append(_structured_chunk(child["text"], [child]))
    return chunks


def _structured_chunk(text: str, blocks: list[dict[str, Any]]) -> StructuredChunk:
    """从一组来源块归纳 chunk metadata，保持和 import_chunks 字段一致。"""
    pages = [_optional_int(block.get("page_number")) for block in blocks]
    pages = [page for page in pages if page is not None]
    return StructuredChunk(
        text=remove_position_tags(text).strip(),
        source_blocks=[dict(block) for block in blocks],
        section_path=_chunk_section_path(blocks),
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        block_type=_chunk_block_type(blocks),
        source_offsets=_chunk_source_offsets(blocks),
    )


def remove_position_tags(text: str) -> str:
    """移除 RAGFlow @@page 坐标 tag，避免用户审核正文混入内部位置编码。"""
    return re.sub(r"@@[0-9-]+\t[0-9.\t]+##", "", str(text or ""))


def _normalize_block(block: dict[str, Any]) -> dict[str, Any]:
    """整理来源块字段，保证后续 merge 只处理稳定结构。"""
    payload = dict(block)
    payload["text"] = _block_text(payload)
    payload["block_type"] = str(payload.get("block_type") or "text").strip() or "text"
    payload["section_title"] = (
        str(payload.get("section_title")).strip()
        if payload.get("section_title") is not None
        else None
    )
    if "evidence" not in payload or not isinstance(payload["evidence"], dict):
        payload["evidence"] = {}
    positions = extract_pdf_positions(payload)
    if positions:
        payload["pdf_positions"] = positions
        payload["evidence"] = {**payload["evidence"], "pdf_positions": positions}
    return payload


def _block_text(block: dict[str, Any]) -> str:
    """读取来源块正文，空白块不参与 chunk。"""
    return str(block.get("text") or "").strip()


def _has_content(block: dict[str, Any]) -> bool:
    """文字非空，或带 asset_paths（image/table/equation 块），都视为有内容、参与 chunk。"""
    if _block_text(block):
        return True
    evidence = block.get("evidence") if isinstance(block.get("evidence"), dict) else {}
    return bool(evidence.get("asset_paths"))


def _chunk_section_path(blocks: list[dict[str, Any]]) -> list[str]:
    """按当前 chunk 最后一个章节标题生成章节路径。"""
    sections = [str(block.get("section_title") or "").strip() for block in blocks]
    sections = [section for section in sections if section]
    if not sections:
        return []
    return [part.strip() for part in sections[-1].split(">") if part.strip()]


def _chunk_block_type(blocks: list[dict[str, Any]]) -> str:
    """归纳 chunk 类型，多个类型合并时标记 mixed。"""
    types = {
        str(block.get("block_type") or "").strip()
        for block in blocks
        if str(block.get("block_type") or "").strip()
    }
    if not types:
        return "text"
    if len(types) == 1:
        return next(iter(types))
    return "mixed"


def _chunk_source_offsets(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总 RAGFlow position tag，保持位置证据可追溯。"""
    tags = []
    pdf_positions = []
    for block in blocks:
        evidence = block.get("evidence") if isinstance(block.get("evidence"), dict) else {}
        position_tag = block.get("position_tag") or evidence.get("position_tag")
        if position_tag:
            tags.append(str(position_tag))
        for position in extract_pdf_positions(block):
            if position not in pdf_positions:
                pdf_positions.append(position)
    offsets: dict[str, Any] = {}
    if tags:
        offsets["position_tags"] = tags
    if pdf_positions:
        offsets["pdf_positions"] = pdf_positions
    return offsets


def _optional_int(value: Any) -> int | None:
    """把页码字段转为整数，非法值保持为空。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_overlap(value: int) -> int:
    """把 overlap 百分比限制在 RAGFlow 可解释范围内。"""
    try:
        overlap = int(value)
    except (TypeError, ValueError):
        return 0
    return min(max(overlap, 0), 99)


def _overlap_tail(text: str, overlapped_percent: int) -> str:
    """按 RAGFlow 字符尾部 overlap 方式取上一 chunk 的尾部。"""
    overlap = _normalize_overlap(overlapped_percent)
    if not text or overlap <= 0:
        return ""
    start = int(len(text) * (100 - overlap) / 100)
    return text[start:]
