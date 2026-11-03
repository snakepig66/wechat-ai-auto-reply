"""AI engine using DeepSeek (OpenAI-compatible API) for reply generation."""

import threading
from functools import lru_cache

from openai import OpenAI

from .prompts import (
    MSG_SPLIT_MARKER,
    NO_REPLY_MARKER,
    PERSONA_GENERATE_PROMPT,
    PERSONA_REFINE_PROMPT,
    RELATIONSHIP_HINTS,
    RELATIONSHIP_LABELS,
    SYSTEM_PROMPT_TEMPLATE,
    TONE_LABELS,
)
from .reply import clean_reply, validate_reply
from .style import (
    analyze_style,
    build_style_profile,
    prepare_style_samples,
    sanitize_style_sample,
)


@lru_cache(maxsize=8)
def _style_prompt_parts(samples):
    """Build (style_block, style_stats) for the system prompt.

    Cached on the exact sample content (a tuple), so unchanged samples
    are not re-prepared or re-analyzed on every reply.  The returned
    strings are immutable, so no defensive copy is needed.
    """
    samples = prepare_style_samples(samples)
    if samples:
        sample_lines = "\n".join(f"- {s}" for s in samples)
        style_block = f"以下是你的真实聊天记录样本：\n{sample_lines}"
        stats = build_style_profile(samples)
        punct_str = ", ".join(
            f"'{k}'x{v}" for k, v in stats["punctuation"].items()
        ) or "很少使用标点"
        style_stats = "\n".join([
            f"- 平均长度: {stats['avg_length']} 字",
            f"- 长度分布: {stats['length_distribution']}",
            f"- 短消息比例: {stats['short_ratio']}",
            f"- 重复样本比例: {stats['repeat_ratio']}",
            f"- 高频表达: "
            f"{', '.join(stats['top_words'][:6]) or '无明显高频词'}",
            f"- 标点习惯: {punct_str}",
            f"- 表情频率: {stats['emoji_ratio']} 个/条",
        ])
    else:
        style_block = "（暂无样本，请使用自然随性的中文口语风格）"
        style_stats = "（暂无统计，保持自然随性）"
    return style_block, style_stats


class AIEngine:
    """Generates replies via DeepSeek API, with style learning."""

    sanitize_style_sample = staticmethod(sanitize_style_sample)
    prepare_style_samples = staticmethod(prepare_style_samples)
    build_style_profile = staticmethod(build_style_profile)
    analyze_style = staticmethod(analyze_style)
    clean_reply = staticmethod(clean_reply)
    validate_reply = staticmethod(validate_reply)

    def __init__(self, config_manager):
        self.config = config_manager
        self._client = None
        self._client_lock = threading.Lock()
        # Debug info for the caller to explain a skipped reply.
        self.last_skip_reason = ""
        self.last_raw_reply = ""

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            api_key = self.config.get("api_key")
            base_url = self.config.get("api_base")
            if not api_key:
                raise ValueError(
                    "API key 未设置，请在设置页填入 DeepSeek API Key"
                )
            with self._client_lock:
                if self._client is None:
                    self._client = OpenAI(
                        api_key=api_key,
                        base_url=base_url,
                        timeout=45.0,
                        max_retries=1,
                    )
        return self._client

    def reset_client(self) -> None:
        with self._client_lock:
            self._client = None

    def list_models(self, api_key=None, api_base=None, client=None,
                    timeout=20.0):
        """Fetch available model ids from an OpenAI-compatible endpoint.

        ``client`` may be injected for tests; otherwise a short-lived
        client is created from the supplied or saved credentials.
        """
        key = str(
            api_key if api_key is not None
            else self.config.get("api_key") or ""
        ).strip()
        base = str(
            api_base if api_base is not None
            else self.config.get("api_base") or ""
        ).strip()
        if client is None:
            if not key:
                raise ValueError("API key 未设置，请先填写 API Key")
            kwargs = {"api_key": key, "timeout": timeout, "max_retries": 0}
            if base:
                kwargs["base_url"] = base
            client = OpenAI(**kwargs)

        resp = client.models.list()
        data = getattr(resp, "data", None)
        if data is None and isinstance(resp, dict):
            data = resp.get("data")
        ids = []
        for item in data or []:
            mid = item.get("id") if isinstance(item, dict) else getattr(
                item, "id", None
            )
            if mid:
                ids.append(str(mid))
        return sorted(set(ids))

    def _build_system_prompt(self, history=None, contact=None,
                             profile=None, is_group=False,
                             group_mention_only=True) -> str:
        style_block, style_stats = _style_prompt_parts(
            tuple(self.config.get("style_samples") or ())
        )

        persona = self.config.get("persona").strip()
        if not persona:
            persona = "一个普通的中国微信用户，说话随性自然"

        recent_lines = []
        for msg in (history or [])[-8:]:
            role = "我" if msg.get("role") == "assistant" else "对方"
            content = (msg.get("content") or "").strip()
            if content:
                recent_lines.append(f"{role}: {content[:100]}")
        recent_context = "\n".join(recent_lines) or "（暂无历史对话）"

        profile = profile or self.config.get_contact_profile(contact or "")
        relationship = RELATIONSHIP_LABELS.get(
            profile.get("relationship", "unknown"), "关系未知"
        )
        tone = TONE_LABELS.get(profile.get("tone", "natural"), "自然平衡")
        if self.config.get("conservative_mode"):
            tone = "保守克制"
        relationship_hint = RELATIONSHIP_HINTS.get(
            profile.get("relationship", "unknown"),
            RELATIONSHIP_HINTS["unknown"],
        )

        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            no_reply_marker=NO_REPLY_MARKER,
            msg_split_marker=MSG_SPLIT_MARKER,
            recent_context=recent_context,
            style_block=style_block,
            style_stats=style_stats,
            persona=persona,
            relationship=relationship,
            tone=tone,
            relationship_hint=relationship_hint,
            contact_notes=profile.get("notes", "") or "无",
        )
        if is_group:
            if group_mention_only:
                prompt += (
                    "\n\n## 群聊说明\n"
                    "这是群聊消息，只有被 @ 时才需要回复。"
                    "消息可能来自不同成员，不要假定说话人身份，也不要编造对方是谁。"
                    "直接回应 @ 你的内容，不需要重复 @ 对方。"
                )
            else:
                prompt += (
                    "\n\n## 群聊说明\n"
                    "这是群聊消息，当前配置会回应群里的消息，不需要等待 @。"
                    "消息可能来自不同成员，不要假定说话人身份，也不要编造对方是谁。"
                    "直接回应最后一条消息即可。"
                )
        return prompt

    def generate_reply(self, contact, incoming_text, history=None,
                       retry_on_quality_error=True, profile=None,
                       is_group=False, group_mention_only=True):
        """Generate a reply. Returns reply text or None if no reply needed."""
        self.last_skip_reason = ""
        self.last_raw_reply = ""
        if history is None:
            history = self.config.get_conversation(contact)
        profile = profile or self.config.get_contact_profile(contact)
        system_prompt = self._build_system_prompt(
            history, contact=contact, profile=profile, is_group=is_group,
            group_mention_only=group_mention_only,
        )

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": incoming_text})

        base_max_tokens = int(self.config.get("max_tokens") or 150)
        max_tokens = base_max_tokens
        length_retried = False

        for attempt in range(2 if retry_on_quality_error else 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.config.get("model"),
                    messages=messages,
                    temperature=self.config.get("temperature"),
                    max_tokens=max_tokens,
                )
                choices = getattr(resp, "choices", None) or []
                if not choices:
                    raise RuntimeError("API 返回中没有 choices")
                choice = choices[0]
                message = getattr(choice, "message", None)
                reply = getattr(message, "content", "") if message else ""
                reply = str(reply or "").strip()
                finish_reason = getattr(choice, "finish_reason", None)
            except Exception as e:
                raise RuntimeError(f"API 调用或解析失败: {e}") from e

            self.last_raw_reply = reply

            # A reasoning model can spend the whole completion budget on
            # hidden reasoning and return empty content. Retry once with a
            # bigger budget instead of treating that as "no reply".
            if not reply and not length_retried:
                length_retried = True
                max_tokens = max(800, base_max_tokens * 4)
                try:
                    resp = self.client.chat.completions.create(
                        model=self.config.get("model"),
                        messages=messages,
                        temperature=self.config.get("temperature"),
                        max_tokens=max_tokens,
                    )
                    choices = getattr(resp, "choices", None) or []
                    if choices:
                        choice = choices[0]
                        message = getattr(choice, "message", None)
                        reply = getattr(message, "content", "") if message else ""
                        reply = str(reply or "").strip()
                        finish_reason = getattr(choice, "finish_reason", None)
                        self.last_raw_reply = reply
                except Exception as e:
                    raise RuntimeError(f"API 调用或解析失败: {e}") from e

            cleaned = self.clean_reply(reply)
            if not cleaned:
                self.last_skip_reason = (
                    "empty_content_length"
                    if finish_reason == "length"
                    else "empty_content"
                )
                return None
            if NO_REPLY_MARKER in cleaned:
                self.last_skip_reason = "no_reply_marker"
                return None
            problems = self.validate_reply(
                cleaned, history, incoming_text
            )
            if not problems:
                self.last_skip_reason = ""
                return cleaned
            if attempt == 0 and retry_on_quality_error:
                messages = [
                    *messages,
                    {"role": "assistant", "content": cleaned},
                    {"role": "user", "content":
                     "请重写上一条，只输出自然、具体的消息内容，"
                     "避免复述、模板化表达和任何内部说明。"},
                ]
                continue
            self.last_skip_reason = "quality:" + ",".join(problems)
        return None

    def generate_persona(self, samples=None, current_persona="",
                         optimize=False, extra_instruction=""):
        """Generate or refine a persona description from style samples."""
        if samples is None:
            samples = self.config.get("style_samples")
        samples = [s for s in (samples or []) if s.strip()]
        if not samples:
            raise RuntimeError(
                "还没有风格样本，请先在风格学习页采集聊天记录"
            )

        samples = self.prepare_style_samples(samples, limit=200)
        sample_block = "\n".join(f"- {s}" for s in samples)
        if optimize and current_persona.strip():
            system_prompt = PERSONA_REFINE_PROMPT
            user_content = (
                "## 当前人设\n"
                f"{current_persona.strip()}\n\n"
                "## 真实聊天记录样本\n"
                f"{sample_block}"
            )
        else:
            system_prompt = PERSONA_GENERATE_PROMPT
            user_content = "## 真实聊天记录样本\n" + sample_block

        extra = extra_instruction.strip()
        if extra:
            user_content += f"\n\n## 额外要求\n{extra}"

        try:
            resp = self.client.chat.completions.create(
                model=self.config.get("model"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.6,
                max_tokens=600,
            )
        except Exception as e:
            raise RuntimeError(f"API 调用失败: {e}") from e

        persona = (resp.choices[0].message.content or "").strip()
        if not persona:
            raise RuntimeError("AI 返回为空，请重试")
        return persona.strip('"').strip("'").strip()

    def get_style_preview(self):
        """Human-readable style summary for the GUI."""
        samples = self.config.get("style_samples")
        stats = self.analyze_style(samples)
        lines = []
        lines.append(f"样本数量: {stats['count']} 条")
        if stats["count"] == 0:
            return "\n".join(lines)
        lines.append(f"平均长度: {stats['avg_length']} 字")
        if stats["top_words"]:
            lines.append(f"高频表达: {', '.join(stats['top_words'][:8])}")
        if stats["punctuation"]:
            punct_str = ", ".join(
                f"'{k}'x{v}" for k, v in stats["punctuation"].items()
            )
            lines.append(f"标点习惯: {punct_str}")
        else:
            lines.append("标点习惯: 很少使用标点")
        lines.append(f"表情频率: {stats['emoji_ratio']} 个/条")
        return "\n".join(lines)

