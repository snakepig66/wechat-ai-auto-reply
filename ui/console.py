"""Console tab mixin."""

import logging
from tkinter import ttk
import tkinter as tk

from .theme import *

logger = logging.getLogger(__name__)


class ConsoleTabMixin:
    def _build_console_tab(self):
        page = ttk.Frame(self._page_area, style="Page.TFrame")
        self._pages["console"] = page

        # ── Status control card ──
        ctrl_card = self._make_card(page, "运行控制", accent=PRIMARY)
        inner = ttk.Frame(ctrl_card, style="Card.TFrame")
        inner.pack(fill="x", padx=16, pady=(4, 14))

        left = ttk.Frame(inner, style="Card.TFrame")
        left.pack(side="left")

        self.status_dot = tk.Label(
            left, text="●", bg=SURFACE, fg=TEXT_LIGHT,
            font=(FONT_FAMILY, 16, "bold")
        )
        self.status_dot.pack(side="left", padx=(0, 10))

        status_text = ttk.Frame(left, style="Card.TFrame")
        status_text.pack(side="left")

        ttk.Label(
            status_text, text="自动回复状态", style="Section.TLabel"
        ).pack(anchor="w")

        self.status_detail = ttk.Label(
            status_text, text="未启动 — 手动打开聊天后点击开始",
            style="Hint.TLabel"
        )
        self.status_detail.pack(anchor="w", pady=(3, 0))

        self.start_btn = ttk.Button(
            inner, text="开启自动监听", style="Primary.TButton",
            command=self._toggle_worker
        )
        self.start_btn.pack(side="right")

        self.auto_send_var = tk.BooleanVar(value=self._auto_send_replies)
        self.auto_send_check = ttk.Checkbutton(
            inner,
            text="自动发送回复",
            variable=self.auto_send_var,
            command=self._toggle_auto_send,
        )
        self.auto_send_check.pack(side="right", padx=(0, 14))

        self.auto_send_status = ttk.Label(
            inner,
            text=self._auto_send_label(),
            style="Muted.TLabel",
        )
        self.auto_send_status.pack(side="right", padx=(0, 14))

        ttk.Button(
            inner, text="显示悬浮窗", style="Ghost.TButton",
            command=self._show_floating_window,
        ).pack(side="right", padx=(0, 14))

        # ── Console log card ──
        log_card = self._make_card(page, "运行日志", accent=SLATE,
                                   expand=True)
        log_body = ttk.Frame(log_card, style="Card.TFrame")
        log_body.pack(fill="both", expand=True, padx=16, pady=(4, 14))

        log_header = ttk.Frame(log_body, style="Card.TFrame")
        log_header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            log_header, text="实时输出", style="Muted.TLabel"
        ).pack(side="left")
        ttk.Button(
            log_header, text="清空", style="Ghost.TButton",
            command=self._clear_log
        ).pack(side="right")

        console = tk.Frame(
            log_body, bg=LOG_BG, highlightthickness=1,
            highlightbackground="#1e293b"
        )
        console.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            console, wrap="word", state="disabled",
            font=(FONT_MONO, 10), bg=LOG_BG, fg=LOG_FG,
            insertbackground=LOG_FG, borderwidth=0, highlightthickness=0,
            padx=14, pady=10, spacing1=1, spacing3=1,
        )
        self.log_text.pack(fill="both", expand=True)

        # Log color tags
        self.log_text.tag_config("normal", foreground=LOG_FG)
        self.log_text.tag_config("success", foreground=LOG_GREEN)
        self.log_text.tag_config("error", foreground=LOG_RED)
        self.log_text.tag_config("incoming", foreground=LOG_YELLOW)
        self.log_text.tag_config("ai", foreground=LOG_BLUE)
        self.log_text.tag_config("skip", foreground=LOG_GRAY)
        self.log_text.tag_config("timestamp", foreground=LOG_TIMESTAMP)
