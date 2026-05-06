import json
from types import SimpleNamespace

from customer_service_agent.cli import build_parser, main


def test_parser_accepts_core_commands():
    parser = build_parser()
    for command in [
        "check-config",
        "init-db",
        "import-faq",
        "search",
        "ask",
        "tool-search",
        "tool-answer",
        "wechat-login",
        "wechat-service",
        "admin",
    ]:
        args = parser.parse_args([command])
        assert args.command == command


def test_wechat_login_dispatches_to_service(monkeypatch):
    settings = SimpleNamespace()
    called = []

    monkeypatch.setattr("customer_service_agent.cli.Settings.load", lambda: settings)

    from customer_service_agent import wechat_service

    monkeypatch.setattr(wechat_service, "login_wechat", lambda actual: called.append(actual))

    assert main(["wechat-login"]) == 0
    assert called == [settings]


def test_wechat_service_dispatches_to_service(monkeypatch):
    settings = SimpleNamespace()
    called = []

    monkeypatch.setattr("customer_service_agent.cli.Settings.load", lambda: settings)

    from customer_service_agent import wechat_service

    monkeypatch.setattr(wechat_service, "run_service", lambda actual: called.append(actual))

    assert main(["wechat-service"]) == 0
    assert called == [settings]


def test_tool_search_prints_json_for_agent(monkeypatch, capsys):
    settings = SimpleNamespace()
    monkeypatch.setattr("customer_service_agent.cli.Settings.load", lambda: settings)

    class FakeResponse:
        def to_dict(self):
            return {
                "tool": "faq_rag",
                "mode": "search",
                "question": "Why is the item missing?",
                "documents": [],
            }

    class FakeTool:
        def search(self, question):
            assert question == "Why is the item missing?"
            return FakeResponse()

    monkeypatch.setattr("customer_service_agent.cli.build_rag_tool", lambda actual: FakeTool())

    assert main(["tool-search", "Why is the item missing?"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "tool": "faq_rag",
        "mode": "search",
        "question": "Why is the item missing?",
        "documents": [],
    }


def test_tool_answer_prints_json_for_agent(monkeypatch, capsys):
    settings = SimpleNamespace()
    monkeypatch.setattr("customer_service_agent.cli.Settings.load", lambda: settings)

    class FakeResponse:
        def to_dict(self):
            return {
                "tool": "faq_rag",
                "mode": "answer_draft",
                "question": "Why is the item missing?",
                "answer_draft": "Please check whether the assignment was published first.",
                "documents": [],
            }

    class FakeTool:
        def answer(self, question):
            assert question == "Why is the item missing?"
            return FakeResponse()

    monkeypatch.setattr("customer_service_agent.cli.build_rag_tool", lambda actual: FakeTool())

    assert main(["tool-answer", "Why is the item missing?"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "tool": "faq_rag",
        "mode": "answer_draft",
        "question": "Why is the item missing?",
        "answer_draft": "Please check whether the assignment was published first.",
        "documents": [],
    }
