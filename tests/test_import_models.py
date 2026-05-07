from customer_service_agent.import_models import detect_file_type


def test_detect_file_type_recognizes_supported_extensions():
    """上传入口保持通用，但要识别后续可扩展的文件类型。"""
    assert detect_file_type("chat.md") == ("markdown", "markdown_chat")
    assert detect_file_type("manual.pdf") == ("pdf", "unsupported")
    assert detect_file_type("faq.xlsx") == ("excel", "unsupported")
    assert detect_file_type("guide.docx") == ("word", "unsupported")


def test_detect_file_type_handles_unknown_extension():
    """未知扩展名进入暂不支持解析状态。"""
    assert detect_file_type("archive.zip") == ("unknown", "unsupported")
