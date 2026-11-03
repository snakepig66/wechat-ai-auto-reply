"""Always-on-top floating controller mixin."""

import logging
from tkinter import ttk
import tkinter as tk

from .theme import *

logger = logging.getLogger(__name__)


class FloatingMixin:
    def _build_floating_window(self):
        """Create a compact always-on-top controller for common actions."""
        window = tk.Toplevel(self.root)
        window.title("自动回复控制")
        # Build while hidden, then size to the content's requested height so
        # DPI scaling or font differences never clip the bottom buttons.
        window.withdraw()
        window.resizable(False, False)
        window.configure(bg=SURFACE)
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", self._hide_floating_window)

        header = tk.Frame(window, bg=PRIMARY, height=32)
        header.pack(fill="x")
        header.pack_propagate(False)
        title = tk.Label(
            header, text="自动回复控制", bg=PRIMARY, fg="white",
            font=(FONT_FAMILY, 10, "bold"), padx=10,
        )
        title.pack(side="left", fill="y")
        close_btn = tk.Button(
            header, text="×", command=self._hide_floating_window,
            bg=PRIMARY, fg="white", activebackground=PRIMARY_DK,
            activeforeground="white", relief="flat", borderwidth=0,
            font=(FONT_FAMILY, 14), width=2, cursor="hand2",
        )
        close_btn.pack(side="right", fill="y")

        body = tk.Frame(window, bg=SURFACE, padx=10, pady=8)
        body.pack(fill="both", expand=True)
        self._floating_status_label = tk.Label(
            body, text=self._floating_status_text(), bg=SURFACE,
            fg=TEXT_GRAY, anchor="w", font=(FONT_FAMILY, 9),
        )
        self._floating_status_label.pack(fill="x")

        controls = tk.Frame(body, bg=SURFACE)
        controls.pack(fill="x", pady=(7, 0))
        self._floating_send_var = tk.BooleanVar(value=self._auto_send_replies)
        send_check = tk.Checkbutton(
            controls, text="自动发送", variable=self._floating_send_var,
            command=self._toggle_floating_auto_send, bg=SURFACE,
            activebackground=SURFACE, fg=TEXT_DARK, selectcolor=SURFACE,
            font=(FONT_FAMILY, 9), padx=0,
        )
        send_check.pack(side="left")
        self._floating_toggle_btn = ttk.Button(
            controls, text="开启监听", width=10,
            command=self._toggle_worker,
        )
        self._floating_toggle_btn.pack(side="right")

        bottom = tk.Frame(body, bg=SURFACE)
        bottom.pack(fill="x", pady=(6, 0))
        ttk.Button(
            bottom, text="打开主窗口", command=self._show_main_window,
        ).pack(side="left")
        ttk.Button(
            bottom, text="隐藏悬浮窗", command=self._hide_floating_window,
        ).pack(side="right")

        self._floating_window = window
        window.update_idletasks()
        width = max(236, window.winfo_reqwidth())
        height = max(142, window.winfo_reqheight())
        window.minsize(width, height)
        # Park it in the top-right corner instead of top-left, where it
        # could sit on top of the main window's settings inputs. It stays
        # draggable, and the user can hide it from the main window.
        screen_w = window.winfo_screenwidth()
        x = max(0, screen_w - width - 24)
        window.geometry(f"{width}x{height}+{x}+24")
        window.deiconify()
    def _floating_status_text(self):
        listener = "监听中" if self._running else "未监听"
        sender = "自动发送" if self._auto_send_replies else "仅填充消息框"
        return f"状态：{listener} · {sender}"
    def _update_floating_window(self):
        if not self._floating_window or not self._floating_window.winfo_exists():
            return
        if self._floating_status_label:
            self._floating_status_label.config(text=self._floating_status_text())
        if hasattr(self, "_floating_toggle_btn"):
            self._floating_toggle_btn.config(
                text="停止监听" if self._running else "开启监听"
            )
        if self._floating_send_var:
            self._floating_send_var.set(self._auto_send_replies)
    def _hide_floating_window(self):
        if self._floating_window and self._floating_window.winfo_exists():
            self._floating_window.withdraw()
    def _show_floating_window(self):
        if self._floating_window and self._floating_window.winfo_exists():
            self._floating_window.deiconify()
            self._floating_window.attributes("-topmost", True)
            self._floating_window.lift()
            self._update_floating_window()
    def _show_main_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
    def _toggle_floating_auto_send(self):
        self.auto_send_var.set(bool(self._floating_send_var.get()))
        self._toggle_auto_send()
