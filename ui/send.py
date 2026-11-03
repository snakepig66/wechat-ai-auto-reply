"""Manual send tab mixin."""

import logging
import threading
from tkinter import ttk, messagebox
import tkinter as tk

from .theme import *

from core.ai.prompts import NO_REPLY_MARKER

logger = logging.getLogger(__name__)


class SendTabMixin:
    def _build_send_tab(self):
        page = ttk.Frame(self._page_area, style="Page.TFrame")
        self._pages["send"] = page

        # ── Contact + compose card ──
        card1 = self._make_card(page, "主动发消息", accent=PRIMARY)
        body1 = ttk.Frame(card1, style="Card.TFrame")
        body1.pack(fill="x", padx=16, pady=(4, 14))

        contact_row = ttk.Frame(body1, style="Card.TFrame")
        contact_row.pack(fill="x", pady=(0, 10))

        ttk.Label(
            contact_row, text="发送给", style="Card.TLabel"
        ).pack(side="left")

        self.send_contact_var = tk.StringVar()
        self.send_contact_combo = ttk.Combobox(
            contact_row, textvariable=self.send_contact_var,
            values=self.config.get("contacts"), width=28,
            font=(FONT_FAMILY, 10)
        )
        self.send_contact_combo.pack(side="left", padx=(10, 8))

        ttk.Button(
            contact_row, text="刷新会话", style="Secondary.TButton",
            command=self._refresh_session_contacts
        ).pack(side="left")

        ttk.Label(
            body1, text="消息内容", style="Card.TLabel"
        ).pack(anchor="w", pady=(0, 6))

        self.send_msg_text = tk.Text(
            body1, height=5, wrap="word",
            font=(FONT_FAMILY, 11), bg=SURFACE, fg=TEXT_DARK,
            relief="solid", borderwidth=1, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
            insertbackground=TEXT_DARK, padx=12, pady=8
        )
        self.send_msg_text.pack(fill="x", pady=(0, 10))

        btn_row = ttk.Frame(body1, style="Card.TFrame")
        btn_row.pack(fill="x")

        self.send_btn = ttk.Button(
            btn_row, text="发送", style="Primary.TButton",
            command=self._do_send_message
        )
        self.send_btn.pack(side="left")

        ttk.Button(
            btn_row, text="AI 生成",
            command=self._ai_generate_proactive
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            btn_row, text="清空",
            command=lambda: self.send_msg_text.delete("1.0", "end")
        ).pack(side="left", padx=(8, 0))

        # ── Conversation history card ──
        card2 = self._make_card(page, "对话记录", accent=BLUE)
        body2 = ttk.Frame(card2, style="Card.TFrame")
        body2.pack(fill="both", expand=True, padx=16, pady=(4, 14))

        self.conv_display = tk.Text(
            body2, wrap="word", state="disabled",
            font=(FONT_FAMILY, 10), bg=SOFT_BG, fg=TEXT_DARK,
            relief="flat", borderwidth=0, padx=14, pady=12,
            spacing1=4, spacing3=6,
        )
        self.conv_display.pack(fill="both", expand=True)

        self.conv_display.tag_config(
            "user_msg", foreground=TEXT_DARK, background="#eceff3",
            lmargin1=8, lmargin2=8, rmargin=24,
            spacing1=2, spacing2=1, spacing3=4
        )
        self.conv_display.tag_config(
            "self_msg", foreground=TEXT_DARK, background=PRIMARY_SOFT,
            lmargin1=8, lmargin2=8, rmargin=24,
            spacing1=2, spacing2=1, spacing3=4
        )
        self.conv_display.tag_config(
            "conv_time", foreground=TEXT_LIGHT, font=(FONT_FAMILY, 8)
        )

        self.send_contact_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self._refresh_conversation_display()
        )
        self.send_msg_text.bind(
            "<Control-Return>", lambda e: self._do_send_message()
        )
    def _refresh_session_contacts(self):
        """Populate contact dropdown from WeChat recent sessions."""
        def _do():
            import pythoncom
            pythoncom.CoInitialize()
            try:
                self.wx_agent.ensure_connected()
                names = self.wx_agent.get_session_contacts()
                all_names = list(set(names + self.config.get("contacts")))
                all_names.sort()
                self.root.after(0, lambda: self.send_contact_combo.configure(
                    values=all_names
                ))
                self._log(f"刷新到 {len(all_names)} 个联系人")
                if not self._running:
                    self.wx_agent.disconnect()
            except Exception as e:
                self._log(f"刷新会话失败: {e}")
        threading.Thread(target=_do, daemon=True).start()
    def _refresh_conversation_display(self):
        """Show stored conversation history for the selected contact."""
        contact = self.send_contact_var.get().strip()
        self.conv_display.config(state="normal")
        self.conv_display.delete("1.0", "end")
        if not contact:
            self.conv_display.insert("end", "请选择联系人\n")
            self.conv_display.config(state="disabled")
            return
        conv = self.config.get_conversation(contact)
        if not conv:
            self.conv_display.insert("end", "暂无对话记录\n")
        else:
            for msg in conv:
                role = msg["role"]
                text = msg["content"]
                if role == "user":
                    self.conv_display.insert(
                        "end", "对方  ", ("conv_time", "user_msg")
                    )
                    self.conv_display.insert("end", f"{text}\n", "user_msg")
                else:
                    self.conv_display.insert(
                        "end", "我  ", ("conv_time", "self_msg")
                    )
                    self.conv_display.insert("end", f"{text}\n", "self_msg")
        self.conv_display.config(state="disabled")
        self.conv_display.see("end")
    def _do_send_message(self):
        """Send the typed message to the selected contact."""
        contact = self.send_contact_var.get().strip()
        text = self.send_msg_text.get("1.0", "end").strip()
        if not contact:
            messagebox.showwarning("提示", "请选择发送对象")
            return
        if not text:
            messagebox.showwarning("提示", "请输入消息内容")
            return
        self.send_btn.config(state="disabled", text="发送中...")
        threading.Thread(
            target=self._do_send_worker, args=(contact, text), daemon=True
        ).start()
    def _do_send_worker(self, contact, text):
        """Background thread: connect if needed, send, log result."""
        import pythoncom
        pythoncom.CoInitialize()
        need_disconnect = False
        try:
            if not self.wx_agent.is_connected:
                self.wx_agent.connect()
                need_disconnect = True
            ok = self.wx_agent.send_to_contact(contact, text)
            if ok:
                self._log(f"已发送给 {contact}: {text[:50]}")
                self.config.add_message(contact, "assistant", text)
                self._append_context(contact, "assistant", text)
            else:
                self._log(f"发送失败: {text[:50]}")
        except Exception as e:
            self._log(f"发送出错: {e}")
        finally:
            if need_disconnect:
                try:
                    self.wx_agent.disconnect()
                except Exception:
                    pass
            self.root.after(0, self._send_done)
    def _send_done(self):
        try:
            self.send_btn.config(state="normal", text="发送")
            self._refresh_conversation_display()
        except Exception:
            pass
    def _ai_generate_proactive(self):
        """Use AI to draft a proactive message, fill the text box."""
        contact = self.send_contact_var.get().strip()
        if not contact:
            messagebox.showwarning("提示", "请先选择联系人")
            return
        api_key = self.config.get("api_key")
        if not api_key:
            messagebox.showwarning("提示", "请先在设置页填入 API Key")
            return
        self.send_msg_text.delete("1.0", "end")
        self.send_msg_text.insert("end", "AI 生成中...")
        threading.Thread(
            target=self._ai_generate_worker, args=(contact,), daemon=True
        ).start()
    def _ai_generate_worker(self, contact):
        """Background thread: ask AI to draft a proactive message."""
        try:
            history = self.config.get_conversation(contact)
            messages = [
                {"role": "system", "content": self._proactive_prompt()}
            ]
            messages.extend(history)
            messages.append({
                "role": "user",
                "content": "[主动发消息] 请给对方发一条自然的消息"
            })

            resp = self.ai_engine.client.chat.completions.create(
                model=self.config.get("model"),
                messages=messages,
                temperature=self.config.get("temperature"),
                max_tokens=self.config.get("max_tokens"),
            )
            reply = (resp.choices[0].message.content or "").strip()
            if not reply or NO_REPLY_MARKER in reply:
                reply = ""

            def _fill():
                self.send_msg_text.delete("1.0", "end")
                self.send_msg_text.insert("1.0", reply)
            self.root.after(0, _fill)
        except Exception as e:
            err = str(e)
            def _show_err():
                self.send_msg_text.delete("1.0", "end")
                self._log(f"AI 生成失败: {err}")
            self.root.after(0, _show_err)
    def _proactive_prompt(self):
        """System prompt for proactive message generation."""
        samples = self.ai_engine.prepare_style_samples(
            self.config.get("style_samples"), limit=60
        )
        if samples:
            sample_lines = "\n".join(f"- {s}" for s in samples[:60])
            style_block = f"以下是你的真实聊天记录样本：\n{sample_lines}"
        else:
            style_block = "（暂无样本，请使用自然随性的中文口语风格）"

        persona = self.config.get("persona").strip()
        if not persona:
            persona = "一个普通的中国微信用户，说话随性自然"

        contact = self.send_contact_var.get().strip()
        profile = self.config.get_contact_profile(contact)
        return (
            "你是微信聊天回复协作者，现在要主动给联系人发一条自然的消息。\n"
            "只输出消息内容本身，简洁口语化，不要 Markdown、解释或模板化开场。\n"
            "根据历史语境和联系人关系决定是否适合主动发消息；不要编造经历或已经完成的事情。\n\n"
            f"关系：{profile['relationship']}\n"
            f"语气：{profile['tone']}\n"
            f"## 你的说话风格\n{style_block}\n\n## 你的风格画像\n{persona}"
        )
