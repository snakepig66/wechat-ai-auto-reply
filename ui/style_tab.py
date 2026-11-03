"""Style learning tab mixin."""

import logging
import threading
from tkinter import ttk, messagebox, filedialog
import tkinter as tk

from .theme import *

logger = logging.getLogger(__name__)


class StyleTabMixin:
    def _build_style_tab(self):
        page = ttk.Frame(self._page_area, style="Page.TFrame")
        self._pages["style"] = page

        # ── Action card ──
        card1 = self._make_card(page, "采集聊天样本", accent=PRIMARY)
        body1 = ttk.Frame(card1, style="Card.TFrame")
        body1.pack(fill="x", padx=16, pady=(4, 14))

        ttk.Label(
            body1,
            text="导入你的真实聊天记录，AI 会学习你的用词、句长、标点和语气",
            style="Hint.TLabel"
        ).pack(anchor="w", pady=(0, 10))

        btn_row = ttk.Frame(body1, style="Card.TFrame")
        btn_row.pack(fill="x")

        ttk.Button(
            btn_row, text="导入聊天记录文件", style="Secondary.TButton",
            command=self._import_style_file
        ).pack(side="left")

        self.capture_btn = ttk.Button(
            btn_row, text="从微信抓取历史", style="Primary.TButton",
            command=self._capture_style
        )
        self.capture_btn.pack(side="left", padx=(10, 0))

        ttk.Button(
            btn_row, text="清空样本", style="TButton",
            command=self._clear_style_samples
        ).pack(side="left", padx=(10, 0))

        ttk.Label(
            body1, text="从微信抓取时只采集你自己的消息",
            style="Hint.TLabel"
        ).pack(anchor="w", pady=(6, 0))

        # ── Capture target segmented control ──
        seg_row = ttk.Frame(body1, style="Card.TFrame")
        seg_row.pack(fill="x", pady=(12, 0))
        ttk.Label(
            seg_row, text="抓取量", style="Card.TLabel"
        ).pack(side="left", padx=(0, 10))

        seg_frame = tk.Frame(
            seg_row, bg=SURFACE, highlightthickness=1,
            highlightbackground=BORDER
        )
        seg_frame.pack(side="left")
        self.capture_target_var = tk.StringVar(value="全部")
        self.capture_segment_buttons = {}
        for idx, value in enumerate(["全部", "300", "500", "1000", "自定义"]):
            btn = ttk.Button(
                seg_frame, text=value,
                style="SegmentActive.TButton" if idx == 0 else
                      "Segment.TButton",
                command=lambda v=value: self._on_capture_segment_change(v)
            )
            btn.pack(side="left", padx=(2, 2))
            self.capture_segment_buttons[value] = btn

        self.capture_custom_entry = ttk.Entry(seg_row, width=7)
        self.capture_custom_entry.pack_forget()

        self.sample_count_label = ttk.Label(
            body1, text="已收集样本: 0 条", style="Count.TLabel"
        )
        self.sample_count_label.pack(anchor="w", pady=(12, 0))

        # Live status display for capture operations
        self.capture_status_text = tk.Text(
            body1, wrap="word", state="disabled",
            font=(FONT_MONO, 9), bg=LOG_BG, fg=LOG_FG,
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground="#1e293b", padx=12, pady=10,
            height=4, spacing1=2, spacing3=2,
        )
        self.capture_status_text.pack(fill="x", pady=(10, 0))

        # ── Preview card ──
        card2 = self._make_card(page, "风格特征预览", accent=BLUE,
                                expand=True)
        body2 = ttk.Frame(card2, style="Card.TFrame")
        body2.pack(fill="both", expand=True, padx=16, pady=(4, 14))

        self.style_preview_text = tk.Text(
            body2, wrap="word", state="disabled",
            font=(FONT_MONO, 10), bg=SOFT_BG, fg=TEXT_DARK,
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground=BORDER, padx=12, pady=10,
            spacing1=2, spacing3=2,
        )
        self.style_preview_text.pack(fill="both", expand=True)
    def _update_style_preview(self):
        preview = self.ai_engine.get_style_preview()
        self.style_preview_text.config(state="normal")
        self.style_preview_text.delete("1.0", "end")
        self.style_preview_text.insert("1.0", preview)
        self.style_preview_text.config(state="disabled")
        samples = self.config.get("style_samples")
        self.sample_count_label.config(
            text=f"已收集样本: {len(samples)} 条"
        )
        if hasattr(self, "persona_status_label"):
            self.persona_status_label.config(
                text=f"当前风格样本: {len(samples)} 条"
            )
    def _import_style_file(self):
        path = filedialog.askopenfilename(
            title="选择聊天记录文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败: {e}")
            return

        valid_lines = []
        for line in lines:
            line = line.strip()
            if line and len(line) >= 2:
                valid_lines.append(line)
        count = self.config.add_style_samples(valid_lines)
        self._update_style_preview()
        self._log(f"从文件导入 {count} 条风格样本")
    def _on_capture_segment_change(self, val):
        self.capture_target_var.set(val)
        for key, btn in self.capture_segment_buttons.items():
            btn.configure(
                style="SegmentActive.TButton" if key == val else
                      "Segment.TButton"
            )
        if val == "自定义":
            self.capture_custom_entry.pack(side="left", padx=(10, 0))
            self.capture_custom_entry.focus_set()
        else:
            self.capture_custom_entry.pack_forget()
    def _get_capture_target(self):
        val = self.capture_target_var.get()
        if val == "全部":
            return None
        if val == "自定义":
            raw = self.capture_custom_entry.get().strip()
            try:
                n = int(raw)
                return n if n > 0 else None
            except ValueError:
                return None
        try:
            return int(val)
        except ValueError:
            return None
    def _set_capture_status(self, text, color=TEXT_GRAY):
        """Update the capture status display (thread-safe via after)."""
        def _do():
            try:
                self.capture_status_text.config(state="normal")
                self.capture_status_text.delete("1.0", "end")
                self.capture_status_text.insert("1.0", text)
                self.capture_status_text.config(
                    state="disabled", fg=color
                )
            except Exception:
                pass
        try:
            self.root.after(0, _do)
        except Exception:
            pass
    def _capture_style(self):
        if self._running:
            messagebox.showwarning(
                "提示", "请先停止自动回复后再抓取历史记录"
            )
            return

        self.capture_btn.config(state="disabled", text="抓取中...")
        self._set_capture_status("正在启动抓取...", LOG_BLUE)
        threading.Thread(target=self._do_capture, daemon=True).start()
    def _do_capture(self):
        import pythoncom
        pythoncom.CoInitialize()
        try:
            self._set_capture_status("正在连接微信...", LOG_BLUE)
            self._log("正在连接微信...")
            self.wx_agent.connect()

            self._set_capture_status("已连接，正在读取当前聊天...", LOG_BLUE)
            self._log("已连接，正在读取当前聊天...")
            current = self.wx_agent.get_current_chat_name()
            if not current:
                msg = "未检测到打开的聊天，请先在微信中点开一个对话"
                self._set_capture_status(msg, DANGER)
                self._log(msg)
                self.wx_agent.disconnect()
                return

            self._set_capture_status(
                f"当前聊天: {current}\n正在向上滚动抓取自己的消息...",
                LOG_BLUE
            )
            self._log(f"当前聊天: {current}，正在抓取自己的可见消息...")

            def _on_progress(count, scrolls):
                self._set_capture_status(
                    f"当前聊天: {current}\n"
                    f"已滚动 {scrolls} 次，累计抓取 {count} 条消息...",
                    LOG_BLUE
                )

            target = self._get_capture_target()
            msgs = self.wx_agent.capture_current_history(
                on_progress=_on_progress,
                check_stop=lambda: self._stop_event.is_set(),
                target_count=target,
                only_self=True,
            )
            self._log(f"读取到 {len(msgs)} 条自己的文本消息")

            total_before = len(self.config.get("style_samples"))
            added = self.config.add_style_samples(msgs)
            total_after = len(self.config.get("style_samples"))

            if added > 0:
                self._set_capture_status(
                    f"完成！从 [{current}] 抓到 {len(msgs)} 条自己的消息\n"
                    f"新增 {added} 条风格样本（去重后），"
                    f"当前共 {total_after} 条",
                    LOG_GREEN
                )
                self._log(
                    f"已导入 {added} 条自己的风格样本（来自 {current}），"
                    f"当前共 {total_after} 条"
                )
            else:
                self._set_capture_status(
                    f"当前聊天 [{current}] 没有抓取到自己的文本消息\n"
                    f"（可能只有表情、图片、语音等非文本内容）",
                    LOG_YELLOW
                )
                self._log("未抓取到自己的文本消息")
            self.wx_agent.disconnect()
        except Exception as e:
            self._set_capture_status(f"抓取失败: {e}", DANGER)
            self._log(f"抓取失败: {e}")
            logger.exception("Capture failed")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            try:
                self.root.after(0, self._capture_done)
            except Exception:
                pass
    def _capture_done(self):
        try:
            self.capture_btn.config(state="normal", text="从微信抓取历史")
            self._update_style_preview()
        except Exception:
            pass
    def _clear_style_samples(self):
        if not messagebox.askyesno("确认", "确定清空所有风格样本？"):
            return
        self.config.update(style_samples=[])
        self._update_style_preview()
        self._log("风格样本已清空")
