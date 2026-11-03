"""Tests for AIEngine persona generation."""

import os
import sys
import tempfile
import shutil
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai import AIEngine
from core.config import ConfigManager


class FakeResponse:
    choices = [SimpleNamespace(message=SimpleNamespace(
        content="性格：随性自然\n说话风格：简短口语"
    ))]


class FakeCompletions:
    def __init__(self, client):
        self.client = client

    def create(self, **kwargs):
        self.client.calls.append(kwargs)
        return FakeResponse()


class FakeChat:
    def __init__(self, client):
        self.completions = FakeCompletions(client)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.chat = FakeChat(self)


class PersonaGenerationTest(unittest.TestCase):
    """AIEngine persona generation, using an isolated temp config."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="persona_test_")
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)

    def _make_engine(self):
        cfg = ConfigManager(os.path.join(self._tmpdir, "config.json"))
        cfg.config.api_key = "sk-test"
        cfg.config.model = "test-model"
        cfg.config.style_samples = ["你好呀", "哈哈哈哈，笑死我了"]
        return AIEngine(cfg)

    def test_generate_persona_uses_samples(self):
        ai = self._make_engine()
        client = FakeClient()
        ai._client = client

        persona = ai.generate_persona()

        assert "性格" in persona
        call = client.calls[-1]
        assert call["model"] == "test-model"
        user_content = call["messages"][1]["content"]
        assert "你好呀" in user_content

    def test_optimize_persona_keeps_current_persona(self):
        ai = self._make_engine()
        client = FakeClient()
        ai._client = client

        ai.generate_persona(current_persona="旧人设：话少", optimize=True)

        call = client.calls[-1]
        user_content = call["messages"][1]["content"]
        assert "## 当前人设" in user_content
        assert "旧人设：话少" in user_content

    def test_generate_persona_requires_samples(self):
        ai = self._make_engine()
        ai.config.config.style_samples = []
        try:
            ai.generate_persona(samples=[])
        except RuntimeError as exc:
            assert "风格样本" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for empty samples")


if __name__ == "__main__":
    unittest.main()