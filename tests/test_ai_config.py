"""Tests for AIEngine and ConfigManager."""
import sys
import os
import tempfile
import json
import shutil
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai import AIEngine
from core.config import ConfigManager


def _fake_completion_client(replies):
    """Build a fake OpenAI client returning (content, finish_reason) pairs."""
    class _Message:
        def __init__(self, content):
            self.content = content

    class _Choice:
        def __init__(self, content, finish):
            self.message = _Message(content)
            self.finish_reason = finish

    class _Response:
        def __init__(self, content, finish):
            self.choices = [_Choice(content, finish)]

    class _Completions:
        def __init__(self, items):
            self.items = list(items)
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            content, finish = self.items.pop(0)
            return _Response(content, finish)

    completions = _Completions(replies)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    return client, completions


class ConfigManagerTest(unittest.TestCase):
    """ConfigManager persistence and contact/context behavior."""

    def setUp(self):
        # Every test gets its own temp dir so no test ever touches the
        # project-root config.json and runs never pollute each other.
        self._tmpdir = tempfile.mkdtemp(prefix="ai_config_test_")
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)

    def _cfg_path(self):
        return os.path.join(self._tmpdir, "config.json")

    def test_config_save_load(self):
        path = self._cfg_path()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            cfg = ConfigManager(path)
            cfg.set("api_key", "test-key-123")
            cfg.add_contact("张三")
            cfg.add_style_sample("好的没问题")
            cfg.add_message("张三", "user", "你好")
            cfg.add_message("张三", "assistant", "你好呀")

            # Reload: the key survives via the encrypted sidecar file.
            cfg2 = ConfigManager(path)
            assert cfg2.get("api_key") == "test-key-123"
            assert "张三" in cfg2.get("contacts")
            assert "好的没问题" in cfg2.get("style_samples")
            conv = cfg2.get_conversation("张三")
            assert len(conv) == 2
            assert conv[0]["role"] == "user"
            assert conv[1]["role"] == "assistant"
            with open(path, "r", encoding="utf-8") as saved:
                assert json.load(saved)["api_key"] == ""
            secrets_path = os.path.join(self._tmpdir, "secrets.json")
            assert os.path.exists(secrets_path)
            raw = open(secrets_path, "r", encoding="utf-8").read()
            assert "test-key-123" not in raw, "key must not be stored in plaintext"

    def test_blank_api_key_keeps_stored_value(self):
        path = self._cfg_path()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            cfg = ConfigManager(path)
            cfg.set("api_key", "keep-me")
            cfg.update(api_key="", model="deepseek-chat")
            assert cfg.get("api_key") == "keep-me"
            assert ConfigManager(path).get("api_key") == "keep-me"

    def test_environment_key_takes_precedence(self):
        path = self._cfg_path()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env-key"}):
            cfg = ConfigManager(path)
            cfg.set("api_key", "ui-key")
            assert cfg.get("api_key") == "env-key"
            assert not os.path.exists(
                os.path.join(self._tmpdir, "secrets.json")
            )

    def test_config_duplicate_contact(self):
        cfg = ConfigManager(self._cfg_path())
        cfg.add_contact("张三")
        cfg.add_contact("张三")
        assert cfg.get("contacts").count("张三") == 1

    def test_config_context_limit(self):
        cfg = ConfigManager(self._cfg_path())
        cfg.config.context_length = 5
        for i in range(10):
            cfg.add_message("test", "user", f"msg{i}")
        conv = cfg.get_conversation("test")
        assert len(conv) == 5, f"Expected 5, got {len(conv)}"
        assert conv[0]["content"] == "msg5"
        assert conv[4]["content"] == "msg9"

    def test_contact_profile_round_trip(self):
        cfg = ConfigManager(self._cfg_path())
        cfg.set_contact_profile("张三", relationship="close_friend", tone="playful")
        assert cfg.get_contact_profile("张三")["relationship"] == "close_friend"
        assert cfg.get_contact_profile("未知")["tone"] == "natural"

    def test_low_max_tokens_is_migrated(self):
        path = self._cfg_path()
        cfg = ConfigManager(path)
        cfg.config.max_tokens = 150
        cfg.save()
        cfg2 = ConfigManager(path)
        assert cfg2.get("max_tokens") == 800

    def test_get_supports_default(self):
        cfg = ConfigManager(self._cfg_path())
        assert cfg.get("group_reply_on_mention_only", True) is True
        assert cfg.get("does_not_exist", "fallback") == "fallback"

    def test_blank_endpoint_and_model_are_ignored(self):
        cfg = ConfigManager(self._cfg_path())
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            cfg.update(api_base="https://custom.example/v1", model="m1")
            cfg.update(api_base="", model="")
            assert cfg.get("api_base") == "https://custom.example/v1"
            assert cfg.get("model") == "m1"

    def test_group_chat_config_round_trip(self):
        path = self._cfg_path()
        cfg = ConfigManager(path)
        cfg.add_group_chat("家庭群")
        cfg.add_group_chat("家庭群")
        cfg.set("my_group_nickname", "小王, 小李")
        cfg.set("group_reply_on_mention_only", True)

        cfg2 = ConfigManager(path)
        assert cfg2.get("group_chats") == ["家庭群"]
        assert cfg2.get("my_group_nickname") == "小王, 小李"
        assert cfg2.get("group_reply_on_mention_only") is True

    def test_auto_send_defaults_off_and_round_trips(self):
        cfg = ConfigManager(self._cfg_path())
        assert cfg.get("auto_send_replies") is False
        cfg.set("auto_send_replies", True)
        assert ConfigManager(str(cfg.path)).get("auto_send_replies") is True


class AIEngineTest(unittest.TestCase):
    """AIEngine static/class helpers and prompt building."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="ai_engine_test_")
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)

    def _cfg(self):
        return ConfigManager(os.path.join(self._tmpdir, "config.json"))

    def test_ai_style_analysis(self):
        samples = [
            "好的没问题",
            "好的没问题",
            "笑死了真的",
            "笑死了真的",
            "deepseek 68",
            "deepseek 68",
        ]
        stats = AIEngine.analyze_style(samples)
        assert stats["count"] == 6
        assert stats["avg_length"] > 0
        assert isinstance(stats["top_words"], list)
        assert isinstance(stats["punctuation"], dict)
        assert "好的没问题" in stats["top_words"]
        assert "笑死了真的" in stats["top_words"]
        assert "deepseek" in stats["top_words"]

    def test_ai_style_empty(self):
        stats = AIEngine.analyze_style([])
        assert stats["count"] == 0
        assert stats["avg_length"] == 0

    def test_ai_no_reply_marker(self):
        from ai_engine import NO_REPLY_MARKER
        assert "<NO_REPLY>" == NO_REPLY_MARKER

    def test_style_sample_sanitization_and_profile(self):
        sample = "去 https://example.com 看看 sk_tr_abcdefghijklmnop1234 识别码:123456789"
        clean = AIEngine.sanitize_style_sample(sample)
        assert "http" not in clean
        assert "sk_tr_" not in clean
        assert "123456789" not in clean
        profile = AIEngine.build_style_profile(["你好呀", "哈哈哈哈", sample])
        assert profile["count"] >= 2
        assert "length_distribution" in profile

    def test_reply_clean_and_validation(self):
        assert AIEngine.clean_reply("回复：**你好**") == "你好"
        assert "echoes_incoming" in AIEngine.validate_reply("你好呀", incoming_text="你好呀")
        assert "sensitive_content" in AIEngine.validate_reply("看 https://example.com")

    def test_ai_system_prompt_build(self):
        cfg = self._cfg()
        cfg.add_style_sample("测试样本")
        cfg.config.persona = "我是一个程序员"
        ai = AIEngine(cfg)
        prompt = ai._build_system_prompt()
        assert "测试样本" in prompt
        assert "程序员" in prompt

    def test_group_prompt_contains_group_note(self):
        ai = AIEngine(self._cfg())
        assert "群聊说明" in ai._build_system_prompt(is_group=True)
        assert "群聊说明" not in ai._build_system_prompt()

    def test_system_prompt_contains_relationship_hint(self):
        cfg = self._cfg()
        cfg.set_contact_profile("张三", relationship="family")
        ai = AIEngine(cfg)
        prompt = ai._build_system_prompt(contact="张三")
        assert "关系提示" in prompt
        assert "少用网络梗" in prompt

    def test_group_prompt_reflects_mention_mode(self):
        ai = AIEngine(self._cfg())
        on = ai._build_system_prompt(is_group=True, group_mention_only=True)
        off = ai._build_system_prompt(is_group=True, group_mention_only=False)
        assert "只有被 @ 时" in on
        assert "不需要等待 @" in off
        assert "只有被 @ 时" not in off

    def test_empty_content_retries_with_larger_budget(self):
        cfg = self._cfg()
        cfg.config.api_key = "sk-test"
        cfg.config.max_tokens = 150
        ai = AIEngine(cfg)
        client, completions = _fake_completion_client([
            ("", "length"), ("好呀", "stop"),
        ])
        ai._client = client
        reply = ai.generate_reply(
            "测试", "在吗", history=[], retry_on_quality_error=False
        )
        assert reply == "好呀"
        assert completions.calls[0]["max_tokens"] == 150
        assert completions.calls[1]["max_tokens"] >= 800
        assert ai.last_skip_reason == ""

    def test_empty_content_reason_is_reported(self):
        cfg = self._cfg()
        cfg.config.api_key = "sk-test"
        cfg.config.max_tokens = 150
        ai = AIEngine(cfg)
        client, _ = _fake_completion_client([
            ("", "length"), ("", "length"),
        ])
        ai._client = client
        reply = ai.generate_reply(
            "测试", "在吗", history=[], retry_on_quality_error=False
        )
        assert reply is None
        assert ai.last_skip_reason == "empty_content_length"

    def test_list_models_sorts_and_dedupes(self):
        class _Models:
            def list(self):
                return SimpleNamespace(data=[
                    SimpleNamespace(id="deepseek-reasoner"),
                    SimpleNamespace(id="deepseek-chat"),
                    {"id": "deepseek-chat"},
                ])

        class _Client:
            models = _Models()

        ai = AIEngine(self._cfg())
        assert ai.list_models(client=_Client()) == [
            "deepseek-chat", "deepseek-reasoner"
        ]

    def test_list_models_requires_api_key(self):
        ai = AIEngine(self._cfg())
        ai.config.config.api_key = ""
        with self.assertRaises(ValueError):
            ai.list_models()

    def test_ai_system_prompt_uses_context_and_style_stats(self):
        cfg = self._cfg()
        cfg.config.persona = "测试人设"
        cfg.config.style_samples = ["好的没问题", "哈哈这个好笑", "嗯嗯知道了"]
        ai = AIEngine(cfg)
        history = [
            {"role": "user", "content": "在吗"},
            {"role": "assistant", "content": "在呢"},
        ]
        prompt = ai._build_system_prompt(history)
        assert "最近对话语境" in prompt
        assert "对方: 在吗" in prompt
        assert "我: 在呢" in prompt
        assert "风格特征" in prompt
        assert "平均长度" in prompt


if __name__ == "__main__":
    unittest.main()
