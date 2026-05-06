from customer_service_agent.wechat_service import split_text


def test_split_text_keeps_short_text():
    assert split_text("hello", limit=10) == ["hello"]


def test_split_text_splits_on_line_boundaries():
    text = "第一行\n第二行很长\n第三行"
    assert split_text(text, limit=8) == ["第一行", "第二行很长", "第三行"]


def test_split_text_splits_long_single_line():
    assert split_text("x" * 25, limit=10) == ["x" * 10, "x" * 10, "x" * 5]


def test_split_text_returns_placeholder_for_blank_text():
    assert split_text("", limit=10) == ["..."]


def test_handle_message_catches_send_failure_for_rag_reply(capsys):
    from customer_service_agent.wechat_service import handle_message

    class FakeBot:
        def extract_text(self, msg):
            return "hello"

        def send_text(self, to_user_id, text, context_token=""):
            raise RuntimeError("send failed")

    class FakeRag:
        def answer(self, text):
            return "answer"

    class FakeSettings:
        wechat_message_chunk_size = 10

    handle_message(
        FakeBot(),
        FakeRag(),
        FakeSettings(),
        {"from_user_id": "user-1", "context_token": "ctx-1"},
    )

    captured = capsys.readouterr()
    assert "send failed" in captured.err or "send failed" in captured.out


def test_run_service_backs_off_when_get_updates_fails(monkeypatch, tmp_path, capsys):
    from customer_service_agent import cli
    from customer_service_agent import wechat_service

    sleeps = []

    class FakeBot:
        token = "token"
        bot_id = "bot"

        def __init__(self, token_file):
            self.token_file = token_file

        def get_updates(self, timeout):
            raise RuntimeError("api down")

    class FakeSettings:
        wechat_token_file = tmp_path / "token.json"

    class FakeLock:
        def bind(self, address):
            self.address = address

    monkeypatch.setattr(wechat_service, "WxBotClient", FakeBot)
    monkeypatch.setattr(cli, "build_rag", lambda settings: object())
    monkeypatch.setattr(wechat_service.socket, "socket", lambda family, kind: FakeLock())

    def fake_sleep(seconds):
        sleeps.append(seconds)
        raise SystemExit

    monkeypatch.setattr(wechat_service.time, "sleep", fake_sleep)

    try:
        wechat_service.run_service(FakeSettings())
    except SystemExit:
        pass

    captured = capsys.readouterr()
    assert sleeps == [5]
    assert "api down" in captured.err or "api down" in captured.out
