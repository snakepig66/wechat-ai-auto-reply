"""Shared design tokens and UI helpers."""

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

BG          = "#f4f6f9"

CARD_BG     = "#ffffff"

SURFACE     = "#ffffff"

SOFT        = "#fafbfd"

SOFT_BG     = "#f7f9fc"

PRIMARY     = "#00b26a"

PRIMARY_DK  = "#059b56"

PRIMARY_SOFT = "#e6f7ef"

BLUE        = "#2f6fed"

BLUE_SOFT   = "#eaf1fe"

AMBER       = "#f59e0b"

AMBER_SOFT  = "#fdf3e2"

SLATE       = "#64748b"

SLATE_SOFT  = "#eef1f5"

DANGER      = "#ef4444"

DANGER_DK   = "#d93a3a"

DANGER_SOFT = "#fdecec"

TEXT_DARK   = "#17202a"

TEXT_GRAY   = "#5b6472"

TEXT_LIGHT  = "#9aa3af"

BORDER      = "#e6e9ef"

LOG_BG        = "#0f172a"

LOG_FG        = "#dbe4f0"

LOG_GREEN     = "#4ade80"

LOG_YELLOW    = "#fbbf24"

LOG_RED       = "#f87171"

LOG_BLUE      = "#60a5fa"

LOG_GRAY      = "#94a3b8"

LOG_TIMESTAMP = "#64748b"

FONT_FAMILY = "Microsoft YaHei UI"

FONT_MONO   = "Consolas"

_LOG_SECRET_RE = re.compile(
    r"https?://\S+|www\.\S+|\b(?:sk[-_][A-Za-z0-9_-]{12,}|sk[A-Za-z0-9_-]{20,})\b|\b\d{7,}\b",
    re.IGNORECASE,
)

def _redact_log_text(text):
    return _LOG_SECRET_RE.sub("[已脱敏]", str(text or ""))

class LogQueueHandler(logging.Handler):
    """Forward log records to a queue for thread-safe GUI updates."""

    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

def timestamp():
    return datetime.now().strftime("%H:%M:%S")

def _log_tag(msg):
    """Return a tag name for color-coding log lines."""
    lower = msg.lower()
    if "错误" in msg or "失败" in msg or "error" in lower:
        return "error"
    if "已发送" in msg or "开始监听" in msg or "运行中" in msg or "已连接" in msg or "刷新到" in msg:
        return "success"
    if "收到" in msg:
        return "incoming"
    if "ai" in lower or "回复" in msg:
        return "ai"
    if "跳过" in msg or "不回复" in msg or "无需回复" in msg:
        return "skip"
    return "normal"
__all__ = ['logger', '_LOG_SECRET_RE', '_redact_log_text', 'BG', 'CARD_BG', 'SURFACE', 'SOFT', 'SOFT_BG', 'PRIMARY', 'PRIMARY_DK', 'PRIMARY_SOFT', 'BLUE', 'BLUE_SOFT', 'AMBER', 'AMBER_SOFT', 'SLATE', 'SLATE_SOFT', 'DANGER', 'DANGER_DK', 'DANGER_SOFT', 'TEXT_DARK', 'TEXT_GRAY', 'TEXT_LIGHT', 'BORDER', 'LOG_BG', 'LOG_FG', 'LOG_GREEN', 'LOG_YELLOW', 'LOG_RED', 'LOG_BLUE', 'LOG_GRAY', 'LOG_TIMESTAMP', 'FONT_FAMILY', 'FONT_MONO', 'LogQueueHandler', 'timestamp', '_log_tag', 'logger']
