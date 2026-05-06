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


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
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
