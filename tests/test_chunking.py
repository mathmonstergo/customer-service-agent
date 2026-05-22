from customer_service_agent.chunking import (
    attach_media_context_to_blocks,
    extract_pdf_positions,
    normalize_children_delimiter,
    ragflow_naive_merge_blocks,
    split_with_pattern,
)


def test_ragflow_naive_merge_blocks_respects_token_budget_and_metadata():
    """RAGFlow 式 naive merge 会按 token 预算合并结构块，并保留来源块。"""
    blocks = [
        {
            "text": "账号登录",
            "block_type": "title",
            "page_number": 1,
            "section_title": "账号",
            "evidence": {"source_file": "manual.pdf"},
        },
        {
            "text": "第一段处理流程",
            "block_type": "text",
            "page_number": 1,
            "section_title": "账号",
            "evidence": {"source_file": "manual.pdf"},
        },
        {
            "text": "第二段处理流程",
            "block_type": "text",
            "page_number": 2,
            "section_title": "账号",
            "evidence": {"source_file": "manual.pdf"},
        },
    ]

    chunks = ragflow_naive_merge_blocks(
        blocks,
        chunk_token_num=9,
        delimiter="\n。；！？",
        overlapped_percent=0,
        token_counter=len,
    )

    assert [chunk.text for chunk in chunks] == [
        "账号登录\n第一段处理流程",
        "第二段处理流程",
    ]
    assert chunks[0].source_blocks == blocks[:2]
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 1
    assert chunks[0].block_type == "mixed"
    assert chunks[1].source_blocks == blocks[2:]
    assert chunks[1].page_start == 2
    assert chunks[1].page_end == 2
    assert chunks[1].block_type == "text"


def test_ragflow_naive_merge_blocks_supports_backtick_custom_delimiter():
    """反引号 delimiter 走 RAGFlow 自定义分隔逻辑，而不是按字符切。"""
    blocks = [
        {
            "text": "问题一###问题二###问题三",
            "block_type": "text",
            "page_number": 1,
            "section_title": "FAQ",
            "evidence": {},
        }
    ]

    chunks = ragflow_naive_merge_blocks(
        blocks,
        chunk_token_num=128,
        delimiter="`###`",
        token_counter=len,
    )

    assert [chunk.text for chunk in chunks] == ["问题一", "问题二", "问题三"]
    assert all(chunk.source_blocks[0]["section_title"] == "FAQ" for chunk in chunks)


def test_split_with_pattern_matches_ragflow_child_delimiter_behavior():
    """children_delimiter 会保留紧随前文的分隔符，匹配 RAGFlow split_with_pattern。"""
    pattern = normalize_children_delimiter(r"\n")

    assert split_with_pattern("第一问\n第二问\n第三问", pattern) == [
        "第一问\n",
        "第二问\n",
        "第三问",
    ]


def test_attach_media_context_to_blocks_adds_neighbor_text_to_table():
    """表格块会按 RAGFlow 媒体上下文窗口补充相邻文本。"""
    blocks = [
        {
            "text": "退款规则如下。",
            "block_type": "text",
            "page_number": 1,
            "section_title": "售后",
            "evidence": {},
        },
        {
            "text": "状态 | 处理\n待发货 | 可退款",
            "block_type": "table",
            "page_number": 1,
            "section_title": "售后",
            "evidence": {"block_type": "table"},
        },
        {
            "text": "超过时效需要人工审核。",
            "block_type": "text",
            "page_number": 1,
            "section_title": "售后",
            "evidence": {},
        },
    ]

    result = attach_media_context_to_blocks(
        blocks,
        table_context_size=100,
        image_context_size=0,
        token_counter=len,
    )

    assert result[1]["text"] == "退款规则如下。\n状态 | 处理\n待发货 | 可退款\n超过时效需要人工审核。"
    assert result[1]["context_above"] == "退款规则如下。"
    assert result[1]["context_below"] == "超过时效需要人工审核。"
    assert result[1]["evidence"]["media_context"] == {
        "before": "退款规则如下。",
        "after": "超过时效需要人工审核。",
    }


def test_extract_pdf_positions_matches_ragflow_position_sources():
    """PDF 坐标会按 RAGFlow _pdf_positions 口径统一为 1 起始页码。"""
    assert extract_pdf_positions({"position_tag": "@@1\t100.0\t200.0\t80.0\t160.0##"}) == [
        [1, 100.0, 200.0, 80.0, 160.0]
    ]
    assert extract_pdf_positions({"page_number": 2, "x0": 20, "x1": 120, "top": 40, "bottom": 90}) == [
        [2, 20.0, 120.0, 40.0, 90.0]
    ]


def test_attach_media_context_to_blocks_uses_overlapping_pdf_text():
    """媒体块有坐标时优先用同页重叠文本拆出上下文，匹配 RAGFlow attach_media_context。"""
    blocks = [
        {
            "text": "状态 | 处理\n待发货 | 可退款",
            "block_type": "table",
            "page_number": 1,
            "section_title": "售后",
            "position_tag": "@@1\t120.0\t420.0\t120.0\t180.0##",
            "evidence": {"block_type": "table"},
        },
        {
            "text": "退款规则如下。不同订单状态处理不同。超过时效需要人工审核。请保留凭证。",
            "block_type": "text",
            "page_number": 1,
            "section_title": "售后",
            "position_tag": "@@1\t100.0\t440.0\t80.0\t220.0##",
            "evidence": {},
        },
    ]

    result = attach_media_context_to_blocks(
        blocks,
        table_context_size=100,
        image_context_size=0,
        token_counter=len,
    )

    assert [block["block_type"] for block in result] == ["text", "table"]
    assert result[1]["context_above"] == "退款规则如下。不同订单状态处理不同。"
    assert result[1]["context_below"] == "超过时效需要人工审核。请保留凭证。"
    assert result[1]["text"] == (
        "退款规则如下。不同订单状态处理不同。\n"
        "状态 | 处理\n待发货 | 可退款\n"
        "超过时效需要人工审核。请保留凭证。"
    )


def test_num_tokens_from_string_returns_char_count_when_tiktoken_missing(monkeypatch, caplog):
    """tiktoken 不可用时静默退回字符近似值，不打 warning。"""
    import logging

    import tiktoken

    from customer_service_agent import chunking

    def raise_import(name):
        raise ImportError(f"simulated tiktoken missing: {name}")

    monkeypatch.setattr(tiktoken, "get_encoding", raise_import)

    with caplog.at_level(logging.WARNING, logger="customer_service_agent.chunking"):
        assert chunking.num_tokens_from_string("hello") == 5

    assert not [record for record in caplog.records if record.levelname == "WARNING"]


def test_num_tokens_from_string_warns_on_unexpected_tiktoken_failure(monkeypatch, caplog):
    """tiktoken 抛非 ImportError 时打 warning，避免真实 bug 被静默吞掉。"""
    import logging

    import tiktoken

    from customer_service_agent import chunking

    def raise_runtime(name):
        raise RuntimeError("encoder build broke")

    monkeypatch.setattr(tiktoken, "get_encoding", raise_runtime)

    with caplog.at_level(logging.WARNING, logger="customer_service_agent.chunking"):
        assert chunking.num_tokens_from_string("hello") == 5

    warning_records = [record for record in caplog.records if record.levelname == "WARNING"]
    assert warning_records
    assert any("tiktoken" in record.message.lower() for record in warning_records)


def test_ragflow_naive_merge_blocks_source_offsets_include_pdf_positions():
    """合并后的来源偏移同时保留 position_tag 和 RAGFlow 规范化坐标。"""
    chunks = ragflow_naive_merge_blocks(
        [
            {
                "text": "退款规则以订单状态为准。",
                "block_type": "text",
                "page_number": 1,
                "section_title": "售后",
                "position_tag": "@@1\t100.0\t200.0\t80.0\t160.0##",
                "evidence": {},
            }
        ],
        chunk_token_num=128,
        token_counter=len,
    )

    assert chunks[0].source_offsets == {
        "position_tags": ["@@1\t100.0\t200.0\t80.0\t160.0##"],
        "pdf_positions": [[1, 100.0, 200.0, 80.0, 160.0]],
    }
