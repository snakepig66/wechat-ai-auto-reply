"""Human behavior simulation for realistic reply timing."""

import random
import re
from datetime import datetime

_GROUP_NICKNAME_SPLIT_RE = re.compile(r"[,，、;；\s]+")


class HumanSimulator:
    """Simulates human reading/thinking/typing delays and behavior."""

    def __init__(self, config_manager):
        self.config = config_manager

    def _is_night(self) -> bool:
        hour = datetime.now().hour
        return hour >= 23 or hour < 7

    def _is_meal_time(self) -> bool:
        hour = datetime.now().hour
        return (11 <= hour <= 13) or (17 <= hour <= 19)

    def reading_delay(self, text="", history=None) -> float:
        """Seconds to wait before starting to type (reading + thinking)."""
        lo = self.config.get("read_delay_min")
        hi = self.config.get("read_delay_max")
        delay = random.uniform(lo, hi)
        if self.config.get("night_mode") and self._is_night():
            delay *= 1.6
        if self._is_meal_time():
            delay *= 1.3
        text = str(text or "").strip()
        if len(text) <= 3:
            delay *= 0.55
        elif "?" in text or "？" in text or len(text) >= 40:
            delay *= 1.18
        delay *= random.uniform(0.7, 1.3)
        return min(max(0.5, delay), 20.0)

    def typing_delay(self, text: str) -> float:
        """Seconds to 'type' a message of the given length."""
        speed_min = self.config.get("typing_speed_min")
        speed_max = self.config.get("typing_speed_max")
        char_count = max(len(text), 1)
        speed = random.uniform(speed_min, speed_max)
        delay = char_count * speed
        if self._is_night():
            delay *= 1.4
        delay *= random.uniform(0.7, 1.3)
        return min(max(delay, 0.5), 20.0)

    def split_message(self, text: str) -> list:
        """Split a reply into natural WeChat bubbles.

        The model can explicitly request separate bubbles with the internal
        ``<MSG_SPLIT>`` marker. Long replies still use punctuation as a
        conservative fallback.
        """
        text = text.strip()
        if not text:
            return []

        explicit_parts = [
            part.strip()
            for part in re.split(r"\s*<MSG_SPLIT>\s*", text,
                                 flags=re.IGNORECASE)
            if part.strip()
        ]
        if len(explicit_parts) > 1:
            parts = []
            for part in explicit_parts:
                parts.extend(self._split_long_part(part))
            return parts

        return self._split_long_part(text)

    def _split_long_part(self, text: str) -> list:
        """Fallback splitter for a single overlong model response."""
        if re.search(r"https?://|www\.|```", text):
            return [text]

        # A short Chinese reply can still read naturally as two bubbles when
        # a comma separates two independent reactions, for example:
        # ``你咋了，撇嘴是几个意思``. Keep this deliberately conservative so
        # ordinary phrases such as ``好的，没问题`` stay together.
        comma_parts = [part.strip() for part in re.split(r"，", text)]
        if len(comma_parts) == 2:
            left, right = comma_parts
            if (
                len(text) >= 8
                and len(left) >= 3
                and len(right) >= 3
                and not re.search(r"\d", text)
                and not re.search(r"^(?:好的?|行|嗯|哦|对|没问题)[，,]", text)
            ):
                return [left + "，", right]

        if len(text) <= 20:
            return [text]
        parts = re.split(r"(?<=[。！？\n…])", text)
        chunks = []
        current = ""
        for part in parts:
            current += part
            if len(current) >= 15 and re.search(r"[。！？\n…]$", current):
                chunks.append(current.strip())
                current = ""
        if current.strip():
            chunks.append(current.strip())
        if len(chunks) >= 2 and len(chunks[-1]) <= 3:
            chunks[-2] = chunks[-2] + chunks[-1]
            chunks.pop()
        return chunks if chunks else [text]

    def inter_message_delay(self) -> float:
        """Delay between sending split message parts."""
        return random.uniform(0.8, 2.5)

    def should_reply(self, text="", history=None, contact=None) -> bool:
        """Decide whether to reply, using context while keeping old API support."""
        text = str(text or "").strip()
        if self.is_trivial_message(text) and not ("?" in text or "？" in text):
            return False
        if history:
            recent = history[-1]
            if (recent.get("role") == "assistant"
                    and recent.get("content", "").strip() == text):
                return False
        prob = self.config.get("no_reply_probability")
        if prob >= 1.0:
            return False
        if "?" in text or "？" in text:
            prob *= 0.35
        if self.config.get("night_mode") and self._is_night():
            prob = min(prob * 2.5, 0.30)
        return random.random() > prob

    def is_trivial_message(self, text: str) -> bool:
        """Check if a message is trivial and likely does not need a reply."""
        text = text.strip()
        trivial = {
            "嗯", "嗯嗯", "哦", "哦哦", "好", "好的", "行", "收到",
            "ok", "OK", "Ok", "哈哈", "哈哈哈", "嘿", "嗯哼",
        }
        if text in trivial:
            return True
        return bool(re.fullmatch(r"[\W_]{1,3}", text, flags=re.UNICODE))

    @staticmethod
    def _group_nicknames(my_nickname) -> list:
        """Split the configured nickname string into individual names."""
        return [
            name for name in _GROUP_NICKNAME_SPLIT_RE.split(
                str(my_nickname or "").strip()
            )
            if name
        ]

    def is_group_mention(self, text: str, my_nickname="") -> bool:
        """True if ``text`` contains an @ mention of one of my nicknames."""
        text = str(text or "")
        for nickname in self._group_nicknames(my_nickname):
            pattern = (
                r"[@＠]\s*" + re.escape(nickname)
                + r"(?![\w\u4e00-\u9fff])"
            )
            if re.search(pattern, text, flags=re.IGNORECASE):
                return True
        return False

    def strip_group_mention(self, text: str, my_nickname="") -> str:
        """Remove the @-mention of my nickname from a group message."""
        text = str(text or "")
        for nickname in self._group_nicknames(my_nickname):
            pattern = (
                r"[@＠]\s*" + re.escape(nickname)
                + r"(?![\w\u4e00-\u9fff])"
            )
            text = re.sub(
                pattern, "", text, count=1, flags=re.IGNORECASE
            )
        return text.strip(" \t\r\n\u2005\u3000")

    def prepare_group_message(self, text: str, my_nickname="",
                              mention_only=True):
        """Return the cleaned text, or None if the group message is ignored.

        When ``mention_only`` is enabled, only messages @-mentioning one of
        my group nicknames are accepted. The mention prefix is stripped so
        the model sees the actual content.
        """
        text = str(text or "").strip()
        if not text:
            return None
        if not mention_only:
            return text
        if not self.is_group_mention(text, my_nickname):
            return None
        cleaned = self.strip_group_mention(text, my_nickname)
        # A bare "@我" with no body still deserves a reply.
        return cleaned if cleaned else text
