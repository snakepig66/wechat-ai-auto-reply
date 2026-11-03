"""Local reply preview dialog mixin."""

import logging
import threading
from tkinter import ttk
import tkinter as tk

from .theme import *

logger = logging.getLogger(__name__)


class ReplyPreviewMixin:
    def _open_reply_preview(self):
        """Open a local, non-sending reply preview window."""
        window = tk.Toplevel(self.root)
        window.title("测试回复（不发送）")
        window.geometry("680x560")
        window.configure(bg=BG)

        frame = ttk.Frame(window, style="Page.TFrame")
        frame.pack(fill="both", expand=True, padx=18, pady=18)
        ttk.Label(frame, text="联系人", style="Card.TLabel").pack(anchor="w")
        contact_var = tk.StringVar(value=self._selected_contact())
        contact_combo = ttk.Combobox(
            frame, textvariable=contact_var, values=self.config.get("contacts"),
            width=28,
        )
        contact_combo.pack(fill="x", pady=(4, 10))

        mode_row = ttk.Frame(frame, style="Page.TFrame")
        mode_row.pack(fill="x", pady=(0, 8))
        ttk.Label(mode_row, text="关系", style="Card.TLabel").pack(side="left")
        relationship_var = tk.StringVar(value="unknown")
        relationship_combo = ttk.Combobox(
            mode_row, textvariable=relationship_var, state="readonly",
            values=("unknown", "friend", "close_friend", "family", "work"),
            width=15,
        )
        relationship_combo.pack(side="left", padx=(8, 18))
        ttk.Label(mode_row, text="语气", style="Card.TLabel").pack(side="left")
        tone_var = tk.StringVar(value="natural")
        tone_combo = ttk.Combobox(
            mode_row, textvariable=tone_var, state="readonly",
            values=("natural", "casual", "playful", "conservative"),
            width=15,
        )
        tone_combo.pack(side="left", padx=(8, 0))

        ttk.Label(frame, text="模拟收到的消息", style="Card.TLabel").pack(
            anchor="w", pady=(4, 4)
        )
        incoming_text = tk.Text(
            frame, height=5, wrap="word", font=(FONT_FAMILY, 10),
            bg=SURFACE, fg=TEXT_DARK, relief="solid", borderwidth=1,
            padx=10, pady=8,
        )
        incoming_text.pack(fill="x")

        result = tk.Text(
            frame, height=10, wrap="word", state="disabled",
            font=(FONT_MONO, 10), bg=SOFT_BG, fg=TEXT_DARK,
            relief="flat", padx=10, pady=8,
        )
        result.pack(fill="both", expand=True, pady=(12, 8))

        def load_profile(*_args):
            profile = self._get_contact_profile(contact_var.get().strip())
            relationship_var.set(profile["relationship"])
            tone_var.set(profile["tone"])

        contact_combo.bind("<<ComboboxSelected>>", load_profile)
        load_profile()

        def set_result(text):
            result.config(state="normal")
            result.delete("1.0", "end")
            result.insert("1.0", text)
            result.config(state="disabled")

        def generate():
            contact = contact_var.get().strip() or "预览联系人"
            incoming = incoming_text.get("1.0", "end").strip()
            if not incoming:
                set_result("请输入一条模拟收到的消息")
                return
            button.config(state="disabled", text="生成中...")
            profile = {
                "relationship": relationship_var.get(),
                "tone": tone_var.get(),
                "notes": "",
            }

            def worker():
                try:
                    history = self.config.get_conversation(contact)
                    reply = self.ai_engine.generate_reply(
                        contact, incoming, history=history, profile=profile
                    )
                    if reply is None:
                        output = "AI 判断：无需回复"
                    else:
                        parts = self.human_sim.split_message(reply)
                        delays = [self.human_sim.typing_delay(part)
                                  for part in parts]
                        output = (
                            f"回复：{reply}\n\n"
                            f"分段：{parts}\n"
                            f"预计打字时间：{sum(delays):.1f} 秒"
                        )
                except Exception as exc:
                    output = f"生成失败：{exc}"
                self.root.after(0, lambda: set_result(output))
                self.root.after(0, lambda: button.config(
                    state="normal", text="生成预览"
                ))

            threading.Thread(target=worker, daemon=True).start()

        button = ttk.Button(
            frame, text="生成预览", style="Primary.TButton", command=generate
        )
        button.pack(anchor="e")
