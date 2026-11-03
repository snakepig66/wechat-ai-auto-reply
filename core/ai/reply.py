"""Reply normalization and quality validation."""

import re

from .patterns import API_KEY_RE, MARKDOWN_RE, QUOTE_PREFIX_RE, URL_RE
from .prompts import MSG_SPLIT_MARKER


def clean_reply(text: str) -> str:
    """Normalize model output without rewriting its conversational voice."""
    text = str(text or "").replace("\r", "").strip()
    text = MARKDOWN_RE.sub("", text).strip()
    text = QUOTE_PREFIX_RE.sub("", text).strip()
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text).strip()
    text = text.strip('"').strip("'").strip()
    return text


def validate_reply(reply: str, history=None, incoming_text=""):
    """Return quality issues; callers decide whether to retry or skip."""
    problems = []
    if not reply:
        return ["empty"]
    if len(reply) > 300:
        problems.append("too_long")
    if "```" in reply or re.search(
        r"(?:system prompt|API key|内部提示)", reply, re.I
    ):
        problems.append("internal_or_markdown")
    if API_KEY_RE.search(reply) or URL_RE.search(reply):
        problems.append("sensitive_content")
    normalized_reply = re.sub(r"\s+", "", reply)
    normalized_incoming = re.sub(r"\s+", "", str(incoming_text or ""))
    if (
        len(normalized_incoming) >= 3
        and normalized_reply == normalized_incoming
    ):
        problems.append("echoes_incoming")
    if re.search(r"(?!(.)\1+$)(.{2,8})\2\2", normalized_reply):
        problems.append("repeated_phrase")
    if reply.count(MSG_SPLIT_MARKER) > 2:
        problems.append("too_many_splits")
    return problems


__all__ = ["clean_reply", "validate_reply"]

