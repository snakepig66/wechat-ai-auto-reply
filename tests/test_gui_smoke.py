"""Smoke test for the redesigned Tkinter GUI."""

import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import ConfigManager
from core.wechat import WeChatAgent
from ui.app import AppGUI


class FakeConfig:
    def __init__(self):
        self.config = SimpleNamespace(
            api_key="sk-test",
            persona="测试人设",
            contacts=["测试联系人"],
            group_chats=["测试群"],
            my_group_nickname="测试昵称",
            group_reply_on_mention_only=True,
            style_samples=["你好", "在吗"],
            read_delay_min=2.0,
            read_delay_max=8.0,
            typing_speed_min=0.3,
            typing_speed_max=0.8,
            no_reply_probability=0.08,
            night_mode=True,
            context_length=20,
            conversations={
                "测试联系人": [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "在呢"},
                ]
            },
        )

    def get(self, key, default=None):
        return getattr(self.config, key, default)

    def get_conversation(self, contact):
        return list(self.config.conversations.get(contact, []))


class FakeAIEngine:
    def get_style_preview(self):
        return "风格特征预览文本"

    def reset_client(self):
        pass


class FakeHumanSimulator:
    pass


class FakeWeChatAgent:
    is_connected = False


class ResetMsgCountTest(unittest.TestCase):
    """WeChatAgent.reset_msg_count behavior with a stubbed message source."""

    @staticmethod
    def _make_agent(messages):
        from collections import deque
        import threading

        agent = WeChatAgent.__new__(WeChatAgent)
        agent._last_msg_count = 0
        agent._last_msg_text = ""
        agent._lock = threading.Lock()
        agent._recent_sent = deque(maxlen=80)
        agent.get_messages = lambda: messages
        return agent

    def test_reset_msg_count_preserves_latest_incoming(self):
        agent = self._make_agent([
            {"text": "之前", "class_name": "ChatTextItemView", "side": "right"},
            {"text": "还没回", "class_name": "ChatTextItemView", "side": "left"},
        ])

        agent.reset_msg_count(preserve_latest_incoming=True)

        assert agent._last_msg_count == 1
        assert agent._last_msg_text == "之前"

    def test_reset_msg_count_skips_latest_self_message(self):
        agent = self._make_agent([
            {"text": "对方", "class_name": "ChatTextItemView", "side": "left"},
            {"text": "我的回复", "class_name": "ChatTextItemView", "side": "right"},
        ])

        agent.reset_msg_count(preserve_latest_incoming=True)

        assert agent._last_msg_count == 2
        assert agent._last_msg_text == "我的回复"


class GUISmokeTest(unittest.TestCase):
    def test_build_and_switch_tabs(self):
        try:
            app = AppGUI(
                FakeConfig(),
                FakeAIEngine(),
                FakeHumanSimulator(),
                FakeWeChatAgent(),
            )
        except tk.TclError as exc:
            self.skipTest(f"No display available: {exc}")

        try:
            app.root.update_idletasks()
            assert hasattr(app, "auto_send_var")
            assert app.auto_send_var.get() is False
            assert app.start_btn.cget("text") == "开启自动监听"
            assert app._floating_window is not None
            assert app._floating_window.attributes("-topmost") in (1, True, "1")
            app._hide_floating_window()
            assert app._floating_window.state() == "withdrawn"
            app._show_floating_window()
            assert app._floating_window.state() != "withdrawn"
            for key in ("console", "send", "settings", "style"):
                app._show_tab(key)
                app.root.update_idletasks()

            app.send_contact_var.set("测试联系人")
            app._refresh_conversation_display()
            app.root.update_idletasks()
        finally:
            app.root.destroy()


class ReviewContextMergeTest(unittest.TestCase):
    def test_review_merges_local_history_and_trims(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
                cfg = ConfigManager(path)
                cfg.set("context_length", 8)
                for i in range(5):
                    cfg.add_message("测试群", "user", f"旧{i}")

                class _WX:
                    is_connected = False

                    def get_input_draft(self):
                        return ""

                    def review_current_context(self, **kwargs):
                        return [
                            {"role": "user", "content": f"新{i}"}
                            for i in range(5)
                        ]

                try:
                    app = AppGUI(
                        cfg, FakeAIEngine(), FakeHumanSimulator(), _WX()
                    )
                except tk.TclError as exc:
                    self.skipTest(f"No display available: {exc}")
                try:
                    context = app._review_context("测试群", force=True)
                finally:
                    app.root.destroy()

                assert len(context) == 8
                assert context[0]["content"] == "旧2"
                assert context[-1]["content"] == "新4"

    def test_cached_chat_skips_deep_review(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            cache_path = os.path.join(tmp, "context_cache.json")
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({
                    "测试群": [
                        {"role": "user", "content": f"旧{i}"}
                        for i in range(5)
                    ]
                }, f)
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
                cfg = ConfigManager(path)
                cfg.set("context_length", 8)

                class _WX:
                    is_connected = False

                    def get_input_draft(self):
                        return ""

                    def get_visible_context(self):
                        return [
                            {"role": "assistant", "content": f"新{i}"}
                            for i in range(5)
                        ]

                    def review_current_context(self, **kwargs):
                        raise AssertionError(
                            "deep review must be skipped for a cached chat"
                        )

                try:
                    app = AppGUI(
                        cfg, FakeAIEngine(), FakeHumanSimulator(), _WX()
                    )
                except tk.TclError as exc:
                    self.skipTest(f"No display available: {exc}")
                try:
                    context = app._review_context("测试群", force=True)
                finally:
                    app.root.destroy()

                assert len(context) == 8
                assert context[0]["content"] == "旧2"
                assert context[-1]["content"] == "新4"


class WeChatInputProtectionTest(unittest.TestCase):
    def test_send_message_respects_user_draft(self):
        agent = WeChatAgent.__new__(WeChatAgent)
        agent._ctrl = object()
        agent.last_send_error = ""

        class _ValuePattern:
            Value = "我正在打字"

        class _Field:
            def GetValuePattern(self):
                return _ValuePattern()

        agent._find_input_field = lambda: _Field()
        assert agent.get_input_draft() == "我正在打字"
        assert agent.send_message(
            "自动回复", respect_user_draft=True
        ) is False
        assert agent.last_send_error == "user_draft"

    def test_empty_draft_is_not_blocked(self):
        agent = WeChatAgent.__new__(WeChatAgent)
        agent._ctrl = object()
        agent.last_send_error = ""

        class _ValuePattern:
            Value = ""

        class _Field:
            def GetValuePattern(self):
                return _ValuePattern()

        agent._find_input_field = lambda: _Field()
        assert agent.has_user_draft() is False


class ApiSettingsPersistenceTest(unittest.TestCase):
    def test_group_mode_label_reflects_toggle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
                cfg = ConfigManager(path)
                try:
                    app = AppGUI(
                        cfg, FakeAIEngine(), FakeHumanSimulator(),
                        FakeWeChatAgent(),
                    )
                except tk.TclError as exc:
                    self.skipTest(f"No display available: {exc}")
                try:
                    app.group_mention_only_var.set(True)
                    app._update_group_mode_label()
                    assert "仅" in app.group_mode_label.cget("text")
                    app.group_mention_only_var.set(False)
                    app._save_group_settings()
                    assert "所有" in app.group_mode_label.cget("text")
                    assert cfg.get("group_reply_on_mention_only") is False
                    assert ConfigManager(
                        path
                    ).get("group_reply_on_mention_only") is False
                finally:
                    app.root.destroy()

    def test_group_nickname_autosaves_on_focus_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
                cfg = ConfigManager(path)
                try:
                    app = AppGUI(
                        cfg, FakeAIEngine(), FakeHumanSimulator(),
                        FakeWeChatAgent(),
                    )
                except tk.TclError as exc:
                    self.skipTest(f"No display available: {exc}")
                try:
                    app.group_nickname_var.set("小王")
                    app._save_group_settings()
                    app.group_mention_only_var.set(False)
                    app._save_group_settings()
                finally:
                    app.root.destroy()

                cfg2 = ConfigManager(path)
                assert cfg2.get("my_group_nickname") == "小王"
                assert cfg2.get("group_reply_on_mention_only") is False

    def test_group_nickname_saved_on_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
                cfg = ConfigManager(path)
                try:
                    app = AppGUI(
                        cfg, FakeAIEngine(), FakeHumanSimulator(),
                        FakeWeChatAgent(),
                    )
                except tk.TclError as exc:
                    self.skipTest(f"No display available: {exc}")
                app.group_nickname_var.set("老王")
                app._on_close()

                cfg2 = ConfigManager(path)
                assert cfg2.get("my_group_nickname") == "老王"

    def test_blank_api_fields_do_not_reset_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
                cfg = ConfigManager(path)
                cfg.update(
                    api_base="https://custom.example/v1",
                    model="custom-model",
                    api_key="sk-test-key",
                )
                try:
                    app = AppGUI(
                        cfg, FakeAIEngine(), FakeHumanSimulator(),
                        FakeWeChatAgent(),
                    )
                except tk.TclError as exc:
                    self.skipTest(f"No display available: {exc}")
                try:
                    # Simulate fields left blank when the window closes.
                    app.api_base_var.set("")
                    app.model_var.set("")
                    app.api_key_var.set("")
                    app._persist_api_ui_state()
                finally:
                    app.root.destroy()

                cfg2 = ConfigManager(path)
                assert cfg2.get("api_base") == "https://custom.example/v1"
                assert cfg2.get("model") == "custom-model"
                assert cfg2.get("api_key") == "sk-test-key"


if __name__ == "__main__":
    unittest.main()
