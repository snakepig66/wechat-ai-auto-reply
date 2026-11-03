"""Tests for HumanSimulator."""
import sys
import os
import tempfile
import shutil
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import AppConfig, ConfigManager
from core.human_simulator import HumanSimulator


class HumanSimulatorTest(unittest.TestCase):
    """HumanSimulator behavior tests, each with an isolated temp config."""

    def setUp(self):
        # Never use the default "config.json" path: that would read/write
        # the project-root config containing real user chat data.
        self._tmpdir = tempfile.mkdtemp(prefix="human_simulator_test_")
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        self.cfg = ConfigManager(os.path.join(self._tmpdir, "config.json"))
        self.hs = HumanSimulator(self.cfg)

    def test_should_reply_default(self):
        self.cfg.config.no_reply_probability = 0.0
        assert self.hs.should_reply() is True, "0% probability should always reply"

    def test_should_reply_never(self):
        self.cfg.config.no_reply_probability = 1.0
        assert self.hs.should_reply() is False, "100% probability should never reply"

    def test_should_reply_context_prefers_questions(self):
        self.cfg.config.no_reply_probability = 1.0
        # Questions lower the random ignore probability, but 100% remains a
        # hard opt-out for this compatibility test.
        assert self.hs.should_reply("你在吗？") is False

    def test_trivial_punctuation_message(self):
        assert self.hs.is_trivial_message("？") is True

    def test_reading_delay_range(self):
        self.cfg.config.read_delay_min = 2.0
        self.cfg.config.read_delay_max = 8.0
        for _ in range(100):
            d = self.hs.reading_delay()
            assert d >= 0.5, f"Delay too small: {d}"
            assert d <= 20.0, f"Delay too large: {d}"

    def test_typing_delay(self):
        self.cfg.config.typing_speed_min = 0.3
        self.cfg.config.typing_speed_max = 0.8
        d = self.hs.typing_delay("测试消息十字符")
        assert d >= 0.5, f"Typing delay too small: {d}"
        assert d <= 20.0, f"Typing delay too large: {d}"

    def test_split_message_short(self):
        result = self.hs.split_message("好的")
        assert result == ["好的"], f"Short message should not be split: {result}"

    def test_split_message_long(self):
        text = "好的，没问题。我晚点过去找你。然后我们一起吃饭。"
        result = self.hs.split_message(text)
        assert len(result) >= 1, f"Should have at least one part: {result}"
        assert "".join(result) == text, "Split should preserve all content"

    def test_split_message_marker(self):
        result = self.hs.split_message("你先忙吧<MSG_SPLIT>我等你消息")
        assert result == ["你先忙吧", "我等你消息"], result

    def test_split_message_natural_comma_pause(self):
        text = "你咋了，撇嘴是几个意思"
        result = self.hs.split_message(text)
        assert result == ["你咋了，", "撇嘴是几个意思"], result

    def test_split_message_keeps_common_comma_phrase(self):
        assert self.hs.split_message("好的，没问题") == ["好的，没问题"]

    def test_is_trivial_message(self):
        assert self.hs.is_trivial_message("嗯") is True
        assert self.hs.is_trivial_message("好的") is True
        assert self.hs.is_trivial_message("哈哈") is True
        assert self.hs.is_trivial_message("你好") is False
        assert self.hs.is_trivial_message("今天天气不错") is False

    def test_inter_message_delay(self):
        for _ in range(50):
            d = self.hs.inter_message_delay()
            assert 0.8 <= d <= 2.5, f"Delay out of range: {d}"

    def test_group_mention_detection(self):
        assert self.hs.is_group_mention("你好 @张三 在吗", "张三")
        assert self.hs.is_group_mention("@ 张三 在吗", "张三")
        assert self.hs.is_group_mention("＠张三 你好", "张三")
        assert self.hs.is_group_mention("@小李 你好", "小王, 小李")
        assert not self.hs.is_group_mention("@张三丰 在吗", "张三")
        assert not self.hs.is_group_mention("群里正常聊天", "张三")
        assert not self.hs.is_group_mention("@张三 在吗", "")

    def test_prepare_group_message(self):
        assert self.hs.prepare_group_message("随便聊聊", "张三") is None
        assert self.hs.prepare_group_message(
            "@张三 你好", "张三"
        ) == "你好"
        assert self.hs.prepare_group_message(
            "随便聊聊", "张三", mention_only=False
        ) == "随便聊聊"
        # A bare "@我" still deserves a reply.
        assert self.hs.prepare_group_message("@张三", "张三") == "@张三"


if __name__ == "__main__":
    unittest.main()
