"""Тесты Ollama options в OpenAI-совместимом клиенте."""

import json
import urllib.request

from viu.llm.openai_compatible import OpenAICompatibleLLM


def test_num_ctx_and_keep_alive_in_payload(monkeypatch):
    captured: dict = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "ok"}}]}
            ).encode("utf-8")

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return Resp()

    monkeypatch.setenv("VIU_OLLAMA_NUM_CTX", "16384")
    monkeypatch.setenv("VIU_OLLAMA_KEEP_ALIVE", "5m")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    llm = OpenAICompatibleLLM(
        api_key="ollama",
        base_url="http://127.0.0.1:11434/v1",
        model="viu-cydonia",
    )
    assert llm.complete([{"role": "user", "content": "hi"}]) == "ok"
    body = captured["body"]
    assert body["options"]["num_ctx"] == 16384
    assert body["keep_alive"] == "5m"
