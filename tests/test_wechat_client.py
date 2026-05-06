import json
import stat

import requests

from customer_service_agent.wechat_client import WxBotClient


def test_save_creates_token_file_with_private_permissions(tmp_path):
    token_file = tmp_path / "wechat" / "token.json"
    client = WxBotClient(token_file)
    client.token = "token"
    client.bot_id = "bot"
    client._buf = "buf"

    client._save()

    mode = stat.S_IMODE(token_file.stat().st_mode)
    assert mode == 0o600
    assert json.loads(token_file.read_text("utf-8")) == {
        "bot_token": "token",
        "ilink_bot_id": "bot",
        "updates_buf": "buf",
    }


def test_corrupt_existing_token_json_starts_empty(tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text("{not-json", "utf-8")

    client = WxBotClient(token_file)

    assert client.token == ""
    assert client.bot_id == ""
    assert client._buf == ""


def test_non_object_token_json_starts_empty(tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text("null", "utf-8")

    client = WxBotClient(str(token_file))

    assert client.token == ""
    assert client.bot_id == ""
    assert client._buf == ""


def test_get_updates_returns_empty_with_backoff_on_request_error(monkeypatch, tmp_path, capsys):
    sleeps = []
    client = WxBotClient(tmp_path / "token.json")

    def fake_post(endpoint, body, timeout):
        raise requests.RequestException("network failed")

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr("customer_service_agent.wechat_client.time.sleep", lambda seconds: sleeps.append(seconds))

    assert client.get_updates() == []

    captured = capsys.readouterr()
    assert sleeps == [5]
    assert "network failed" in captured.err or "network failed" in captured.out


def test_get_updates_returns_empty_with_backoff_on_json_parse_error(monkeypatch, tmp_path, capsys):
    sleeps = []
    client = WxBotClient(tmp_path / "token.json")

    def fake_post(endpoint, body, timeout):
        raise ValueError("bad json")

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr("customer_service_agent.wechat_client.time.sleep", lambda seconds: sleeps.append(seconds))

    assert client.get_updates() == []

    captured = capsys.readouterr()
    assert sleeps == [5]
    assert "bad json" in captured.err or "bad json" in captured.out
