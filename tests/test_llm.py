from customer_service_agent.llm import ChatClient, EmbeddingClient, RerankClient


class FakeEmbeddingResponse:
    data = [type("Item", (), {"embedding": [0.1, 0.2, 0.3]})()]


class FakeEmbeddings:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeEmbeddingResponse()


class FakeChatChoice:
    message = type("Message", (), {"content": "回答内容"})()


class FakeChatResponse:
    choices = [FakeChatChoice()]


class FakeStreamDelta:
    def __init__(self, content):
        self.content = content


class FakeStreamChoice:
    def __init__(self, content):
        self.delta = FakeStreamDelta(content)


class FakeStreamChunk:
    def __init__(self, content):
        self.choices = [FakeStreamChoice(content)]


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter([
                FakeStreamChunk("第一段"),
                FakeStreamChunk(""),
                FakeStreamChunk("第二段"),
            ])
        return FakeChatResponse()


class FakeClient:
    def __init__(self):
        self.embeddings = FakeEmbeddings()
        self.completions = FakeCompletions()
        self.chat = type("Chat", (), {"completions": self.completions})()


def test_embedding_client_sends_dimensions():
    fake = FakeClient()
    client = EmbeddingClient(fake, model="text-embedding-v4", dimensions=1024)
    assert client.embed("missing assigned item") == [0.1, 0.2, 0.3]
    assert fake.embeddings.calls[0]["dimensions"] == 1024


def test_chat_client_returns_content():
    fake = FakeClient()
    client = ChatClient(fake, model="deepseek-chat")
    result = client.complete("system", "user")
    assert result == "回答内容"
    call = fake.completions.calls[0]
    assert call["model"] == "deepseek-chat"
    assert call["messages"][0]["role"] == "system"


def test_chat_client_omits_empty_system_prompt():
    """系统提示词为空时不要发送空 system 消息，避免代码层默认提示伪装成配置。"""
    fake = FakeClient()
    client = ChatClient(fake, model="deepseek-chat")

    result = client.complete("", "user")

    assert result == "回答内容"
    call = fake.completions.calls[0]
    assert call["messages"] == [{"role": "user", "content": "user"}]


def test_chat_client_streams_delta_content():
    """ChatClient 默认支持 OpenAI-compatible 流式输出，并过滤空 delta。"""
    fake = FakeClient()
    client = ChatClient(fake, model="deepseek-chat")

    chunks = list(client.stream_complete("system", "user"))

    assert chunks == ["第一段", "第二段"]
    call = fake.completions.calls[0]
    assert call["stream"] is True
    assert call["model"] == "deepseek-chat"


def test_chat_client_stream_omits_empty_system_prompt():
    """流式生成同样遵守空系统提示词不注入 system 消息的约束。"""
    fake = FakeClient()
    client = ChatClient(fake, model="deepseek-chat")

    chunks = list(client.stream_complete("", "user"))

    assert chunks == ["第一段", "第二段"]
    call = fake.completions.calls[0]
    assert call["messages"] == [{"role": "user", "content": "user"}]


class _FakeRerankResponse:
    """模拟 Cohere /v1/rerank 返回。"""

    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.ok = True

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_rerank_client_from_settings_returns_none_when_missing_config():
    """RerankClient 三个核心字段缺一就回退到 None，让上游链路走原路。"""
    from types import SimpleNamespace

    settings = SimpleNamespace(
        rerank_base_url="",
        rerank_api_key="",
        rerank_model="",
        rerank_input_size=50,
    )
    assert RerankClient.from_settings(settings) is None

    settings = SimpleNamespace(
        rerank_base_url="https://rerank.example.com",
        rerank_api_key="key",
        rerank_model="",
        rerank_input_size=50,
    )
    assert RerankClient.from_settings(settings) is None


def test_rerank_client_from_settings_returns_instance_when_configured():
    """配齐 base_url + api_key + model 才返回可用实例。"""
    from types import SimpleNamespace

    settings = SimpleNamespace(
        rerank_base_url="https://rerank.example.com",
        rerank_api_key="rerank-key",
        rerank_model="bge-reranker-v2-m3",
        rerank_input_size=42,
    )

    client = RerankClient.from_settings(settings)

    assert client is not None
    assert client.base_url == "https://rerank.example.com"
    assert client.model == "bge-reranker-v2-m3"
    assert client.input_size == 42


def test_rerank_client_calls_cohere_protocol(monkeypatch):
    """rerank 调用应走 POST {base_url}/v1/rerank，body 必须包含 model/query/documents/top_n。"""
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeRerankResponse(
            {
                "results": [
                    {"index": 2, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.42},
                ]
            }
        )

    monkeypatch.setattr("customer_service_agent.llm.requests.post", fake_post)

    client = RerankClient(
        base_url="https://rerank.example.com/",
        api_key="rerank-key",
        model="bge-reranker-v2-m3",
        input_size=50,
    )
    results = client.rerank(
        "登录失败怎么办",
        ["如何登录", "重置密码", "登录失败排查"],
        top_n=2,
    )

    assert captured["url"] == "https://rerank.example.com/v1/rerank"
    assert captured["headers"]["Authorization"] == "Bearer rerank-key"
    assert captured["json"]["model"] == "bge-reranker-v2-m3"
    assert captured["json"]["query"] == "登录失败怎么办"
    assert captured["json"]["documents"] == ["如何登录", "重置密码", "登录失败排查"]
    assert captured["json"]["top_n"] == 2

    assert [item.index for item in results] == [2, 0]
    assert results[0].relevance_score == 0.91
    assert results[1].relevance_score == 0.42


def test_rerank_client_returns_empty_list_on_http_error(monkeypatch):
    """HTTP 异常应被吞掉返回空列表，上层据此跳过 rerank，绝不影响主链路。"""

    def fake_post(url, json=None, headers=None, timeout=None):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("customer_service_agent.llm.requests.post", fake_post)

    client = RerankClient(
        base_url="https://rerank.example.com",
        api_key="rerank-key",
        model="bge-reranker-v2-m3",
        input_size=50,
    )

    assert client.rerank("q", ["a", "b"], top_n=2) == []
