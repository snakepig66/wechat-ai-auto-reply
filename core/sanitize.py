"""Shared text sanitization used by config persistence and style learning."""

import re

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
API_KEY_RE = re.compile(
    r"\b(?:sk[-_][A-Za-z0-9_-]{12,}|sk[A-Za-z0-9_-]{20,})\b",
    re.IGNORECASE,
)
LONG_NUMBER_RE = re.compile(r"\b\d{7,}\b")

_QUOTED_CONTEXT_RE = re.compile(
    r"\n\s*引用[^\n]*?(?:的消息\s*[:：]?|消息\s*[:：]?)"
)
_SECRET_LABEL_RE = re.compile(
    r"(?:识别码|验证码|远程协助|下载地址|api\s*key)\s*[:：]?\s*\S+",
    re.IGNORECASE,
)
_BRACKET_ONLY_RE = re.compile(r"[\[【].{0,20}[\]】]")
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_text(text: str) -> str:
    """Remove secrets and quoted context from a chat sample.

    Returns an empty string for samples that are empty, shorter than two
    characters, or only a bracketed placeholder such as ``[图片]``.
    """
    value = str(text or "").replace("\r", "").strip()
    if not value:
        return ""
    # Quoted WeChat messages describe someone else's words, not the
    # author's style. Keep only the author's part before the quote.
    value = _QUOTED_CONTEXT_RE.split(value)[0]
    value = URL_RE.sub("", value)
    value = API_KEY_RE.sub("", value)
    value = LONG_NUMBER_RE.sub("", value)
    value = _SECRET_LABEL_RE.sub("", value)
    value = _WHITESPACE_RE.sub(" ", value).strip()
    if not value or len(value) < 2:
        return ""
    if _BRACKET_ONLY_RE.fullmatch(value):
        return ""
    return value


__all__ = ["URL_RE", "API_KEY_RE", "LONG_NUMBER_RE", "sanitize_text"]
