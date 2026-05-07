from customer_service_agent.markdown_import import chunk_messages, parse_wechat_messages


SAMPLE = """# 聊天记录: 京师筑心2026春业务对接群

- [2025-08-25 16:20] 郑海生: @京师筑心-邝老师 邝老师，这个是还没生成的缘故吗
- [2025-08-25 16:23] 京师筑心-田老师: 前些天没开学,报告服务还没启动, 在启动
- [2025-08-25 16:30] 郑海生: 需要多久？
- [2025-08-25 16:31] 京师筑心-田老师: 教育局的话可能数据量大, 隔10分钟刷新一次页面查看进度
- [2025-08-25 17:21] 郑海生: 明天培训启动测评，请保障系统运转流畅
"""


def test_parse_wechat_messages_preserves_speaker_time_and_content():
    """解析微信 Markdown 时保留时间、发言人和正文，便于来源追溯。"""
    messages = parse_wechat_messages(SAMPLE)

    assert len(messages) == 5
    assert messages[0].speaker == "郑海生"
    assert messages[0].sent_at.isoformat(timespec="minutes") == "2025-08-25T16:20"
    assert "没生成" in messages[0].content


def test_parse_wechat_messages_keeps_multiline_content_and_reply_reference():
    """多行消息和回复引用属于同一条聊天消息。"""
    markdown = """- [2025-08-11 13:48] 京师筑心-邝老师: 账号：JSZX_demo101
密码：vlmffjbxdgww
  ↳ 回复 水木: JSZX_demo101 邝老师，这个账号的密码麻烦发一下
- [2025-08-11 13:52] 乘风破浪: 登上了
"""

    messages = parse_wechat_messages(markdown)

    assert len(messages) == 2
    assert "密码" in messages[0].content
    assert "回复 水木" in messages[0].content


def test_chunk_messages_splits_by_time_gap():
    """默认以时间间隔切粗块，AI 只负责后续提炼候选问答。"""
    messages = parse_wechat_messages(SAMPLE)
    chunks = chunk_messages(messages, mode="by_gap", gap_minutes=30)

    assert len(chunks) == 2
    assert chunks[0].message_count == 4
    assert chunks[0].start_at.isoformat(timespec="minutes") == "2025-08-25T16:20"
    assert chunks[0].end_at.isoformat(timespec="minutes") == "2025-08-25T16:31"
    assert chunks[1].message_count == 1
    assert "报告" in chunks[0].keywords


def test_chunk_messages_splits_overlarge_continuous_blocks():
    """连续聊天过长时继续按消息数拆分，避免单块超过 AI 处理窗口。"""
    markdown = "\n".join(
        f"- [2025-08-25 16:{minute:02d}] 用户: 报告下载问题 {minute}"
        for minute in range(6)
    )
    messages = parse_wechat_messages(markdown)

    chunks = chunk_messages(messages, gap_minutes=30, max_messages=2)

    assert [chunk.message_count for chunk in chunks] == [2, 2, 2]


def test_chunk_messages_defaults_to_one_day_time_ranges():
    """导入审核默认按 1 天时间范围切块，跨日期自动拆分。"""
    markdown = """- [2025-08-25 23:50] 用户: 报告下载不了
- [2025-08-26 00:05] 客服: 请隔10分钟刷新
"""
    messages = parse_wechat_messages(markdown)

    chunks = chunk_messages(messages)

    assert len(chunks) == 2
    assert chunks[0].start_at.date().isoformat() == "2025-08-25"
    assert chunks[1].start_at.date().isoformat() == "2025-08-26"


def test_chunk_messages_caps_day_range_at_seven_days():
    """时间范围切块最多允许 7 天，避免单块过大。"""
    messages = parse_wechat_messages(
        "\n".join(
            [
                "- [2025-08-01 09:00] 用户: 报告下载不了",
                "- [2025-08-08 09:00] 客服: 请刷新后再试",
            ]
        )
    )

    chunks = chunk_messages(messages, mode="by_days", days=30)

    assert len(chunks) == 2
