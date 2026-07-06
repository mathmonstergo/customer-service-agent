import pytest

from cyclops.kg import (
    KnowledgeGraphExtractionError,
    build_kg_entity_knowledge_chunk_row,
    build_kg_relation_knowledge_chunk_row,
    parse_kg_extraction_response,
)
from cyclops.kg_ai import KnowledgeGraphAiAssistant


def test_knowledge_graph_ai_assistant_parses_model_output_with_source():
    """KG AI 助手应调用 Chat 模型并把结果解析为待审核候选。"""

    class FakeChat:
        def __init__(self):
            self.calls = []

        def complete(self, system_prompt, user_prompt):
            self.calls.append((system_prompt, user_prompt))
            return """
            {"entities":[{"name":"报告导出","entity_type":"feature_ui_action","evidence":[{"excerpt":"报告导出失败时，先检查账号权限。"}]}],
             "relations":[{"head":"报告导出","head_type":"feature_ui_action","relation_type":"requires","tail":"账号权限","tail_type":"role_permission_channel","evidence":[{"excerpt":"先检查账号权限。"}]}]}
            """

    chat = FakeChat()
    assistant = KnowledgeGraphAiAssistant(chat)

    result = assistant.extract(
        source_text="报告导出失败时，先检查账号权限。",
        source={
            "source_type": "document",
            "source_id": "imp_1",
            "source_chunk_id": "chunk_1",
            "source_title": "平台手册.pdf",
        },
    )

    assert result["entities"][0]["status"] == "needs_review"
    assert result["relations"][0]["relation_type"] == "requires"
    assert "product_platform_module" in chat.calls[0][0]
    assert "报告导出失败时，先检查账号权限。" in chat.calls[0][1]


def test_parse_kg_extraction_response_defaults_to_review_and_preserves_evidence():
    """KG 抽取解析必须让模型结果进入待审核，并保留 FAQ/文档来源证据。"""
    payload = {
        "entities": [
            {
                "name": "报告导出",
                "entity_type": "feature_ui_action",
                "aliases": ["导出报告"],
                "description": "后台导出团体报告的功能入口。",
                "confidence": 0.86,
                "evidence": [{"excerpt": "报告导出失败时，先检查账号权限。"}],
            }
        ],
        "relations": [
            {
                "head": "报告导出",
                "head_type": "feature_ui_action",
                "relation_type": "requires",
                "tail": "账号权限",
                "tail_type": "role_permission_channel",
                "description": "导出报告需要账号具备报告权限。",
                "confidence": 0.8,
                "evidence": [{"excerpt": "先检查账号权限。"}],
            }
        ],
    }
    source = {
        "source_type": "document",
        "source_id": "imp_1",
        "source_chunk_id": "chunk_1",
        "source_title": "平台使用手册.pdf",
        "section_path": ["报告", "导出"],
        "page_start": 3,
        "page_end": 4,
    }

    result = parse_kg_extraction_response(payload, source=source)

    entity = result["entities"][0]
    relation = result["relations"][0]
    assert entity["id"].startswith("kg_ent_")
    assert entity["status"] == "needs_review"
    assert entity["entity_type"] == "feature_ui_action"
    assert entity["aliases"] == ["导出报告"]
    assert entity["evidence"][0]["source_id"] == "imp_1"
    assert entity["evidence"][0]["source_chunk_id"] == "chunk_1"
    assert entity["evidence"][0]["section_path"] == ["报告", "导出"]
    assert relation["id"].startswith("kg_rel_")
    assert relation["head_entity_id"] == entity["id"]
    assert relation["tail_entity_id"].startswith("kg_ent_")
    assert relation["status"] == "needs_review"
    assert relation["evidence"][0]["excerpt"] == "先检查账号权限。"


def test_parse_kg_extraction_response_rejects_freeform_types():
    """KG 抽取解析必须拒绝枚举外类型，避免模型自由造 schema。"""
    with pytest.raises(KnowledgeGraphExtractionError, match="entity_type"):
        parse_kg_extraction_response(
            {
                "entities": [
                    {
                        "name": "报告导出",
                        "entity_type": "random_type",
                        "evidence": [{"excerpt": "证据"}],
                    }
                ],
                "relations": [],
            },
            source={"source_type": "faq", "source_id": "faq_1"},
        )


def test_parse_kg_extraction_response_requires_evidence():
    """实体和关系候选必须有证据，避免不可追溯事实进入审核池。"""
    with pytest.raises(KnowledgeGraphExtractionError, match="evidence"):
        parse_kg_extraction_response(
            {
                "entities": [
                    {
                        "name": "报告导出",
                        "entity_type": "feature_ui_action",
                    }
                ],
                "relations": [],
            },
            source={"source_type": "faq", "source_id": "faq_1"},
        )


def test_build_kg_entity_knowledge_chunk_row_uses_stable_projected_source():
    """已确认实体投影到 knowledge_chunks 时必须使用稳定 KG source_type/source_id。"""
    entity = {
        "id": "kg_ent_abc",
        "name": "报告导出",
        "entity_type": "feature_ui_action",
        "aliases": ["导出报告"],
        "description": "后台导出团体报告的功能入口。",
        "confidence": 0.86,
        "status": "usable",
    }
    evidence = [{"source_id": "imp_1", "source_chunk_id": "chunk_1", "excerpt": "检查账号权限"}]

    chunk = build_kg_entity_knowledge_chunk_row(entity, evidence)

    assert chunk["id"] == "kc_kg_entity_kg_ent_abc"
    assert chunk["source_type"] == "kg_entity"
    assert chunk["source_id"] == "kg_ent_abc"
    assert chunk["source_title"] == "报告导出"
    assert "类型：feature_ui_action" in chunk["content"]
    assert "别名：导出报告" in chunk["content"]
    assert chunk["metadata"]["evidence"] == evidence
    assert chunk["status"] == "usable"


def test_build_kg_relation_knowledge_chunk_row_keeps_node_ids_and_evidence():
    """已确认关系投影必须保留头尾实体 ID，供后续 2D/3D 子图复用。"""
    relation = {
        "id": "kg_rel_abc",
        "head_entity_id": "kg_ent_head",
        "tail_entity_id": "kg_ent_tail",
        "relation_type": "requires",
        "description": "导出报告需要账号具备报告权限。",
        "confidence": 0.8,
        "status": "usable",
    }
    head = {"name": "报告导出", "entity_type": "feature_ui_action"}
    tail = {"name": "账号权限", "entity_type": "role_permission_channel"}
    evidence = [{"source_id": "imp_1", "source_chunk_id": "chunk_1", "excerpt": "先检查账号权限"}]

    chunk = build_kg_relation_knowledge_chunk_row(relation, head, tail, evidence)

    assert chunk["id"] == "kc_kg_relation_kg_rel_abc"
    assert chunk["source_type"] == "kg_relation"
    assert chunk["source_id"] == "kg_rel_abc"
    assert chunk["source_title"] == "报告导出 requires 账号权限"
    assert "头实体：报告导出" in chunk["content"]
    assert "尾实体：账号权限" in chunk["content"]
    assert chunk["metadata"]["head_entity_id"] == "kg_ent_head"
    assert chunk["metadata"]["tail_entity_id"] == "kg_ent_tail"
    assert chunk["metadata"]["evidence"] == evidence


def test_strip_json_fence_handles_nested_json():
    """括号计数方法必须正确处理嵌套 JSON 对象中的内层 }。"""
    kg_json = '{"entities":[{"name":"x","evidence":[{"excerpt":"..."}]}],"relations":[]}'
    fenced = f"```json\n{kg_json}\n```"
    result = KnowledgeGraphAiAssistant._strip_json_fence(fenced)
    assert result == kg_json


def test_strip_json_fence_unfenced_text_returned_as_is():
    """非围栏文本应原样返回。"""
    text = '{"entities":[],"relations":[]}'
    assert KnowledgeGraphAiAssistant._strip_json_fence(text) == text


def test_strip_json_fence_empty_text():
    """空文本和纯空白应原样返回。"""
    assert KnowledgeGraphAiAssistant._strip_json_fence("") == ""
