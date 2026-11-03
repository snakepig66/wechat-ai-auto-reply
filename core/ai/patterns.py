"""Shared regular expressions used by style and reply processing."""

import re

from ..sanitize import API_KEY_RE, LONG_NUMBER_RE, URL_RE

MARKDOWN_RE = re.compile(r"```+|^\s{0,3}[*#>-]+\s*", re.MULTILINE)
QUOTE_PREFIX_RE = re.compile(r"^\s*(?:回复|回答|消息内容)\s*[:：]\s*", re.I)

__all__ = [
    "URL_RE",
    "API_KEY_RE",
    "LONG_NUMBER_RE",
    "MARKDOWN_RE",
    "QUOTE_PREFIX_RE",
]

