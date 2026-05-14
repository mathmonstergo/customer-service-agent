from customer_service_agent.llm import ChatClient, EmbeddingClient


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
