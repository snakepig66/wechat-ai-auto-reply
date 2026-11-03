"""Settings tab mixin."""

import logging
import threading
from tkinter import ttk, messagebox
import tkinter as tk

from .theme import *

logger = logging.getLogger(__name__)


class SettingsTabMixin:
    def _build_settings_tab(self):
        page = ttk.Frame(self._page_area, style="Page.TFrame")
        self._pages["settings"] = page

        # Scrollable area
        canvas = tk.Canvas(page, bg=BG, borderwidth=0,
                           highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical",
                                   command=canvas.yview)
        self._settings_frame = ttk.Frame(canvas)
        self._settings_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        self._settings_window_id = canvas.create_window(
            (0, 0), window=self._settings_frame, anchor="nw"
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(
                self._settings_window_id, width=e.width
            ),
            add="+",
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_wheel_tree(widget):
            # Text/Listbox keep their own wheel handling; everything else in
            # the page scrolls the settings canvas. This scopes the wheel to
            # this page instead of bind_all, which would hijack the log box
            # and style preview too.
            if not isinstance(widget, (tk.Text, tk.Listbox)):
                widget.bind("<MouseWheel>", _on_mousewheel, add="+")
            for child in widget.winfo_children():
                _bind_wheel_tree(child)

        sf = self._settings_frame

        # ── API Key card ──
        card1 = self._make_card(sf, "AI 接口配置", accent=BLUE)
        body1 = ttk.Frame(card1, style="Card.TFrame")
        body1.pack(fill="x", padx=16, pady=(4, 14))

        ttk.Label(
            body1, text="DeepSeek API Key", style="Card.TLabel"
        ).pack(anchor="w", pady=(0, 6))

        key_frame = ttk.Frame(body1, style="Card.TFrame")
        key_frame.pack(fill="x", pady=(0, 6))

        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(
            key_frame, textvariable=self.api_key_var, show="\u2022"
        )
        self.api_key_entry.pack(side="left", fill="x", expand=True)

        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            key_frame, text="显示", variable=self.show_key_var,
            command=self._toggle_key_visibility
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            body1,
            text=(
                "建议使用环境变量 DEEPSEEK_API_KEY；未设置时会加密保存在"
                "本机 secrets.json，不写入 config.json"
            ),
            style="Hint.TLabel"
        ).pack(anchor="w", pady=(2, 0))

        ttk.Label(
            body1, text="API 地址", style="Card.TLabel"
        ).pack(anchor="w", pady=(12, 6))
        self.api_base_var = tk.StringVar()
        ttk.Entry(
            body1, textvariable=self.api_base_var
        ).pack(fill="x")

        ttk.Label(
            body1, text="模型", style="Card.TLabel"
        ).pack(anchor="w", pady=(12, 6))
        model_row = ttk.Frame(body1, style="Card.TFrame")
        model_row.pack(fill="x")
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(
            model_row, textvariable=self.model_var,
            values=("deepseek-chat", "deepseek-reasoner"),
        )
        self.model_combo.pack(side="left", fill="x", expand=True)
        self.fetch_models_btn = ttk.Button(
            model_row, text="拉取模型", style="Secondary.TButton",
            command=self._fetch_models,
        )
        self.fetch_models_btn.pack(side="left", padx=(8, 0))
        self.model_status_label = ttk.Label(
            body1, text="可直接输入模型名，或从接口拉取", style="Hint.TLabel"
        )
        self.model_status_label.pack(anchor="w", pady=(4, 0))

        gen_row = ttk.Frame(body1, style="Card.TFrame")
        gen_row.pack(fill="x", pady=(12, 0))
        ttk.Label(gen_row, text="温度", style="Card.TLabel").pack(side="left")
        self.temperature_var = tk.StringVar()
        ttk.Entry(
            gen_row, textvariable=self.temperature_var, width=8
        ).pack(side="left", padx=(8, 18))
        ttk.Label(
            gen_row, text="最大 tokens", style="Card.TLabel"
        ).pack(side="left")
        self.max_tokens_var = tk.StringVar()
        ttk.Entry(
            gen_row, textvariable=self.max_tokens_var, width=8
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            body1,
            text=(
                "推理模型建议“最大 tokens”≥800；"
                "修改后自动保存，关闭窗口或开始监听时也会保存"
            ),
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(8, 0))

        # ── Contacts card ──
        card2 = self._make_card(sf, "目标联系人", accent=PRIMARY)
        body2 = ttk.Frame(card2, style="Card.TFrame")
        body2.pack(fill="x", padx=16, pady=(4, 14))

        ttk.Label(
            body2,
            text=(
                "用于设置关系和语气；自动回复作用于当前打开的聊天，"
                "同名群聊也会使用这里的设置"
            ),
            style="Hint.TLabel"
        ).pack(anchor="w", pady=(0, 10))

        contact_frame = ttk.Frame(body2, style="Card.TFrame")
        contact_frame.pack(fill="x")

        list_frame = tk.Frame(
            contact_frame, highlightthickness=1, highlightbackground=BORDER
        )
        list_frame.pack(side="left")

        self.contact_listbox = tk.Listbox(
            list_frame, height=6, width=26,
            font=(FONT_FAMILY, 10), bg=SURFACE, fg=TEXT_DARK,
            selectbackground=PRIMARY_SOFT, selectforeground=PRIMARY_DK,
            borderwidth=0, highlightthickness=0, activestyle="none"
        )
        self.contact_listbox.pack(side="left", padx=2, pady=2)
        self.contact_listbox.bind(
            "<<ListboxSelect>>", self._load_selected_contact_profile
        )

        btn_frame = ttk.Frame(contact_frame, style="Card.TFrame")
        btn_frame.pack(side="left", padx=(12, 0))

        self.contact_new_var = tk.StringVar()
        ttk.Entry(
            btn_frame, textvariable=self.contact_new_var, width=20
        ).pack(pady=(0, 6))
        ttk.Button(
            btn_frame, text="+ 添加", style="Secondary.TButton",
            command=self._add_contact
        ).pack(fill="x", pady=1)
        ttk.Button(
            btn_frame, text="\u2212 删除", style="Secondary.TButton",
            command=self._remove_contact
        ).pack(fill="x", pady=1)
        ttk.Button(
            btn_frame, text="使用当前聊天", style="Secondary.TButton",
            command=self._add_current_chat,
        ).pack(fill="x", pady=1)
        ttk.Button(
            btn_frame, text="深度缓存当前聊天", style="Secondary.TButton",
            command=self._deep_cache_current_chat,
        ).pack(fill="x", pady=1)

        profile_frame = ttk.Frame(body2, style="Card.TFrame")
        profile_frame.pack(fill="x", pady=(12, 0))
        ttk.Label(profile_frame, text="关系", style="Card.TLabel").pack(
            side="left"
        )
        self.relationship_var = tk.StringVar(value="unknown")
        self.relationship_combo = ttk.Combobox(
            profile_frame, textvariable=self.relationship_var, state="readonly",
            values=("unknown", "friend", "close_friend", "family", "work"),
            width=15,
        )
        self.relationship_combo.pack(side="left", padx=(8, 18))
        ttk.Label(profile_frame, text="语气", style="Card.TLabel").pack(
            side="left"
        )
        self.tone_var = tk.StringVar(value="natural")
        self.tone_combo = ttk.Combobox(
            profile_frame, textvariable=self.tone_var, state="readonly",
            values=("natural", "casual", "playful", "conservative"),
            width=15,
        )
        self.tone_combo.pack(side="left", padx=(8, 0))
        self.contact_notes_var = tk.StringVar()
        ttk.Label(profile_frame, text="备注", style="Card.TLabel").pack(
            side="left", padx=(18, 8)
        )
        self.contact_notes_entry = ttk.Entry(
            profile_frame, textvariable=self.contact_notes_var, width=24
        )
        self.contact_notes_entry.pack(side="left", fill="x", expand=True)
        self.relationship_combo.bind(
            "<<ComboboxSelected>>", self._save_selected_contact_profile
        )
        self.tone_combo.bind(
            "<<ComboboxSelected>>", self._save_selected_contact_profile
        )
        # Save notes on focus loss or Enter instead of on every keystroke,
        # so typing a note does not trigger a full-config write per character.
        self.contact_notes_entry.bind(
            "<FocusOut>", self._save_selected_contact_profile
        )
        self.contact_notes_entry.bind(
            "<Return>", self._save_selected_contact_profile
        )

        # ── Group chats card ──
        card_group = self._make_card(sf, "群聊设置", accent=BLUE)
        body_group = ttk.Frame(card_group, style="Card.TFrame")
        body_group.pack(fill="x", padx=16, pady=(4, 14))

        ttk.Label(
            body_group,
            text=(
                "群聊默认只在你被 @ 时回复；未 @ 的消息只记入上下文。"
                "昵称和开关修改后自动保存"
            ),
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        group_row = ttk.Frame(body_group, style="Card.TFrame")
        group_row.pack(fill="x")
        group_list_frame = tk.Frame(
            group_row, highlightthickness=1, highlightbackground=BORDER
        )
        group_list_frame.pack(side="left")
        self.group_listbox = tk.Listbox(
            group_list_frame, height=4, width=26,
            font=(FONT_FAMILY, 10), bg=SURFACE, fg=TEXT_DARK,
            selectbackground=PRIMARY_SOFT, selectforeground=PRIMARY_DK,
            borderwidth=0, highlightthickness=0, activestyle="none",
        )
        self.group_listbox.pack(side="left", padx=2, pady=2)

        group_btn_frame = ttk.Frame(group_row, style="Card.TFrame")
        group_btn_frame.pack(side="left", padx=(12, 0))
        self.group_new_var = tk.StringVar()
        ttk.Entry(
            group_btn_frame, textvariable=self.group_new_var, width=20
        ).pack(pady=(0, 6))
        ttk.Button(
            group_btn_frame, text="+ 添加群", style="Secondary.TButton",
            command=self._add_group,
        ).pack(fill="x", pady=1)
        ttk.Button(
            group_btn_frame, text="\u2212 删除", style="Secondary.TButton",
            command=self._remove_group,
        ).pack(fill="x", pady=1)

        nick_row = ttk.Frame(body_group, style="Card.TFrame")
        nick_row.pack(fill="x", pady=(12, 0))
        ttk.Label(nick_row, text="我的群昵称", style="Card.TLabel").pack(
            side="left"
        )
        self.group_nickname_var = tk.StringVar()
        self.group_nickname_entry = ttk.Entry(
            nick_row, textvariable=self.group_nickname_var, width=24
        )
        self.group_nickname_entry.pack(side="left", padx=(8, 8))
        # Save on focus loss / Enter so typing a nickname and clicking
        # anywhere else does not lose it.
        self.group_nickname_entry.bind(
            "<FocusOut>", self._save_group_settings
        )
        self.group_nickname_entry.bind(
            "<Return>", self._save_group_settings
        )
        ttk.Label(
            nick_row, text="多个用逗号分隔", style="Hint.TLabel"
        ).pack(side="left")

        self.group_mention_only_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            body_group, text="群里仅被 @ 时回复",
            variable=self.group_mention_only_var,
            command=self._save_group_settings,
        ).pack(anchor="w", pady=(10, 0))
        self.group_mode_label = ttk.Label(
            body_group, text="", style="Hint.TLabel"
        )
        self.group_mode_label.pack(anchor="w", pady=(4, 0))
        self._update_group_mode_label()

        # ── Persona card ──
        card3 = self._make_card(sf, "人设描述", accent=AMBER)
        body3 = ttk.Frame(card3, style="Card.TFrame")
        body3.pack(fill="x", padx=16, pady=(4, 14))

        ttk.Label(
            body3, text="描述你的性格、身份、说话习惯，让 AI 更像你",
            style="Hint.TLabel"
        ).pack(anchor="w", pady=(0, 6))

        self.persona_text = tk.Text(
            body3, height=4, wrap="word",
            font=(FONT_FAMILY, 10), bg=SURFACE, fg=TEXT_DARK,
            relief="solid", borderwidth=1, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
            padx=10, pady=8
        )
        self.persona_text.pack(fill="x")

        persona_actions = ttk.Frame(body3, style="Card.TFrame")
        persona_actions.pack(fill="x", pady=(10, 0))

        self.persona_gen_btn = ttk.Button(
            persona_actions, text="AI 生成人设", style="Primary.TButton",
            command=lambda: self._persona_generate(optimize=False)
        )
        self.persona_gen_btn.pack(side="left")

        self.persona_optimize_btn = ttk.Button(
            persona_actions, text="优化人设", style="Secondary.TButton",
            command=lambda: self._persona_generate(optimize=True)
        )
        self.persona_optimize_btn.pack(side="left", padx=(8, 0))

        self.persona_status_label = ttk.Label(
            body3, text="当前风格样本: 0 条", style="Muted.TLabel"
        )
        self.persona_status_label.pack(anchor="w", pady=(10, 0))

        ttk.Label(
            body3, text="补充要求（可选）", style="Hint.TLabel"
        ).pack(anchor="w", pady=(8, 4))
        self.persona_extra_var = tk.StringVar()
        self.persona_extra_entry = ttk.Entry(
            body3, textvariable=self.persona_extra_var
        )
        self.persona_extra_entry.pack(fill="x")

        ttk.Button(
            body3, text="测试回复（不发送）", style="Secondary.TButton",
            command=self._open_reply_preview
        ).pack(anchor="w", pady=(10, 0))

        # ── Parameters card ──
        card4 = self._make_card(sf, "回复参数", accent=SLATE)
        body4 = ttk.Frame(card4, style="Card.TFrame")
        body4.pack(fill="x", padx=16, pady=(4, 14))

        self._add_slider(body4, "阅读延迟(秒) 最小值",
                         "read_delay_min", 0.5, 15.0)
        self._add_slider(body4, "阅读延迟(秒) 最大值",
                         "read_delay_max", 0.5, 15.0)
        self._add_slider(body4, "打字速度(秒/字) 最小值",
                         "typing_speed_min", 0.05, 2.0)
        self._add_slider(body4, "打字速度(秒/字) 最大值",
                         "typing_speed_max", 0.05, 2.0)
        self._add_slider(body4, "不回复概率",
                         "no_reply_probability", 0.0, 0.5)
        self._add_int_slider(body4, "上下文条数",
                             "context_length", 4, 50)
        ttk.Label(
            body4,
            text="上下文越多，模型越了解前文；启动回看时会多翻几页",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        night_frame = ttk.Frame(body4, style="Card.TFrame")
        night_frame.pack(fill="x", pady=8)
        self.night_mode_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            night_frame,
            text="深夜模式 (23:00-7:00 回复更慢、概率更低)",
            variable=self.night_mode_var
        ).pack(side="left")

        self.conservative_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            night_frame, text="保守回复模式（减少俚语、脏话和主动延伸）",
            variable=self.conservative_mode_var
        ).pack(side="left", padx=(18, 0))

        self.show_ai_notice_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            night_frame, text="显示 AI 辅助提示",
            variable=self.show_ai_notice_var
        ).pack(side="left", padx=(18, 0))

        # ── Save ──
        ttk.Button(
            sf, text="保存设置", style="Primary.TButton",
            command=self._save_settings
        ).pack(anchor="e", padx=16, pady=(0, 16))

        # Bind after the subtree exists so every settings widget scrolls
        # this page without a global binding.
        canvas.bind("<MouseWheel>", _on_mousewheel, add="+")
        _bind_wheel_tree(sf)
    def _toggle_key_visibility(self):
        self.api_key_entry.config(
            show="" if self.show_key_var.get() else "\u2022"
        )
    def _fetch_models(self):
        """Ask the configured endpoint for its model list, in background."""
        api_key = (
            self.api_key_var.get().strip()
            or self.config.get("api_key")
            or ""
        )
        if not api_key:
            messagebox.showwarning("提示", "请先填写 API Key")
            return
        api_base = self.api_base_var.get().strip()
        self.fetch_models_btn.config(state="disabled", text="拉取中...")
        self.model_status_label.config(text="正在请求模型列表...")

        def worker():
            try:
                ids = self.ai_engine.list_models(
                    api_key=api_key, api_base=api_base
                )
            except Exception as exc:
                err = str(exc)

                def fail():
                    self.model_status_label.config(
                        text=f"拉取失败: {err[:100]}"
                    )
                    self._log(f"拉取模型失败: {err}")
                self.root.after(0, fail)
                return
            finally:
                self.root.after(
                    0,
                    lambda: self.fetch_models_btn.config(
                        state="normal", text="拉取模型"
                    ),
                )

            def done():
                if ids:
                    self.model_combo.configure(values=ids)
                    if self.model_var.get().strip() not in ids:
                        self.model_var.set(ids[0])
                    self.model_status_label.config(
                        text=f"已获取 {len(ids)} 个模型"
                    )
                    self._log(f"拉取到 {len(ids)} 个模型")
                else:
                    self.model_status_label.config(
                        text="接口没有返回模型列表，可手动输入模型名"
                    )
            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()
    def _add_contact(self):
        name = self.contact_new_var.get().strip()
        if not name:
            return
        self.config.add_contact(name)
        self.contact_new_var.set("")
        self._refresh_contact_list()
        if hasattr(self, "send_contact_combo"):
            self.send_contact_combo.configure(values=self.config.get("contacts"))
    def _remove_contact(self):
        sel = self.contact_listbox.curselection()
        if not sel:
            return
        name = self.contact_listbox.get(sel[0])
        self.config.remove_contact(name)
        self._refresh_contact_list()
    def _deep_cache_current_chat(self):
        """Fetch and persist a deep context archive for the open chat."""
        if self._running:
            messagebox.showwarning(
                "提示", "请先停止自动监听，再深度缓存上下文"
            )
            return

        def worker():
            import pythoncom
            pythoncom.CoInitialize()
            name = None
            reviewed = []
            blocked = False
            try:
                self.wx_agent.ensure_connected()
                name = self.wx_agent.get_current_chat_name()
                if name:
                    has_draft = getattr(
                        self.wx_agent, "has_user_draft", lambda: False
                    )
                    if has_draft():
                        blocked = True
                        self.root.after(
                            0,
                            lambda: self._log(
                                "检测到你正在输入，已取消深度缓存"
                            ),
                        )
                    else:
                        reviewed = self.wx_agent.review_current_context(
                            max_pages=30, max_messages=300
                        )
            except Exception as exc:
                err = str(exc)
                self.root.after(
                    0, lambda e=err: self._log(f"深度缓存失败: {e}")
                )
            finally:
                try:
                    if not self._running:
                        self.wx_agent.disconnect()
                except Exception:
                    pass
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

            if blocked:
                return
            if not name:
                self.root.after(
                    0, lambda: self._log("没有检测到当前聊天")
                )
                return

            def apply():
                merged = self._merge_context(
                    self.config.get_conversation(name), reviewed
                )
                self._remember_context(name, merged)
                self._save_context_cache()
                self._log(
                    f"已深度缓存 {name}: 本次读取 {len(reviewed)} 条，"
                    f"缓存共 {len(merged)} 条"
                )
            self.root.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()
    def _add_current_chat(self):
        """Add the currently open WeChat chat so its profile can be set."""
        if self._running:
            messagebox.showwarning(
                "提示", "请先停止自动监听，再加入当前聊天"
            )
            return

        def worker():
            import pythoncom
            pythoncom.CoInitialize()
            name = None
            try:
                self.wx_agent.ensure_connected()
                name = self.wx_agent.get_current_chat_name()
            except Exception as exc:
                err = str(exc)
                self.root.after(
                    0, lambda e=err: self._log(f"获取当前聊天失败: {e}")
                )
            finally:
                try:
                    if not self._running:
                        self.wx_agent.disconnect()
                except Exception:
                    pass
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
            if not name:
                self.root.after(0, lambda: self._log("没有检测到当前聊天"))
                return

            def apply():
                self.config.add_contact(name)
                self._refresh_contact_list()
                items = list(self.contact_listbox.get(0, "end"))
                if name in items:
                    idx = items.index(name)
                    self.contact_listbox.selection_clear(0, "end")
                    self.contact_listbox.selection_set(idx)
                    self._load_selected_contact_profile()
                self._log(f"已加入当前聊天: {name}")
            self.root.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()
    def _selected_contact(self):
        sel = self.contact_listbox.curselection()
        return self.contact_listbox.get(sel[0]) if sel else ""
    def _get_contact_profile(self, name):
        getter = getattr(self.config, "get_contact_profile", None)
        if getter:
            return getter(name)
        return {"relationship": "unknown", "tone": "natural", "notes": ""}
    def _save_selected_contact_profile(self, *_args):
        contact = self._selected_contact()
        if not contact or not hasattr(self, "relationship_var"):
            return
        setter = getattr(self.config, "set_contact_profile", None)
        if not setter:
            return
        relationship = self.relationship_var.get()
        tone = self.tone_var.get()
        notes = self.contact_notes_var.get()
        # Skip the write when the UI still matches the persisted profile
        # (e.g. right after loading a contact), so loading a contact does not
        # trigger another full-config save.
        current = self._get_contact_profile(contact)
        if (
            current["relationship"] == relationship
            and current["tone"] == tone
            and current["notes"] == notes
        ):
            return
        setter(
            contact,
            relationship=relationship,
            tone=tone,
            notes=notes,
        )
    def _load_selected_contact_profile(self, *_args):
        contact = self._selected_contact()
        if not contact or not hasattr(self, "relationship_var"):
            return
        profile = self._get_contact_profile(contact)
        self.relationship_var.set(profile["relationship"])
        self.tone_var.set(profile["tone"])
        self.contact_notes_var.set(profile["notes"])
    def _refresh_contact_list(self):
        self.contact_listbox.delete(0, "end")
        for c in self.config.get("contacts"):
            self.contact_listbox.insert("end", c)
        if self.config.get("contacts"):
            self.contact_listbox.selection_set(0)
            self._load_selected_contact_profile()
    def _add_group(self):
        name = self.group_new_var.get().strip()
        if not name:
            return
        self.config.add_group_chat(name)
        self.group_new_var.set("")
        self._refresh_group_list()
    def _remove_group(self):
        sel = self.group_listbox.curselection()
        if not sel:
            return
        self.config.remove_group_chat(self.group_listbox.get(sel[0]))
        self._refresh_group_list()
    def _refresh_group_list(self):
        self.group_listbox.delete(0, "end")
        groups = getattr(self.config.config, "group_chats", []) or []
        for name in groups:
            self.group_listbox.insert("end", name)
    def _load_config_to_ui(self):
        cfg = self.config.config
        self.api_key_var.set(cfg.api_key)
        self.api_base_var.set(
            getattr(cfg, "api_base", "") or "https://api.deepseek.com"
        )
        self.model_var.set(getattr(cfg, "model", "") or "deepseek-chat")
        self.temperature_var.set(str(getattr(cfg, "temperature", 0.8)))
        self.max_tokens_var.set(str(getattr(cfg, "max_tokens", 150)))
        self.persona_text.delete("1.0", "end")
        self.persona_text.insert("1.0", cfg.persona)
        self._refresh_contact_list()
        self._refresh_group_list()
        self.group_nickname_var.set(
            getattr(cfg, "my_group_nickname", "") or ""
        )
        self.group_mention_only_var.set(
            bool(getattr(cfg, "group_reply_on_mention_only", True))
        )
        self._update_group_mode_label()
        if hasattr(self, "send_contact_combo"):
            self.send_contact_combo.configure(values=cfg.contacts)
        self.conservative_mode_var.set(
            getattr(cfg, "conservative_mode", False)
        )
        self.show_ai_notice_var.set(
            getattr(cfg, "show_ai_assist_notice", True)
        )
        self._auto_send_replies = bool(
            getattr(cfg, "auto_send_replies", False)
        )
        self.auto_send_var.set(self._auto_send_replies)
        self._update_auto_send_status()
        self._update_style_preview()
    def _update_group_mode_label(self):
        """Show the active group reply mode right below the checkbox."""
        if not hasattr(self, "group_mode_label"):
            return
        if bool(self.group_mention_only_var.get()):
            text = "当前：仅 @ 我时回复"
        else:
            text = "当前：回复群里的所有消息"
        self.group_mode_label.config(text=text)
    def _save_group_settings(self, *_args):
        """Persist the group nickname/toggle as soon as they change."""
        try:
            self._update_group_mode_label()
            nickname = self.group_nickname_var.get().strip()
            mention_only = bool(self.group_mention_only_var.get())
            current_nick = self.config.get("my_group_nickname") or ""
            current_flag = bool(
                self.config.get("group_reply_on_mention_only", True)
            )
            if nickname == current_nick and mention_only == current_flag:
                return
            self.config.update(
                my_group_nickname=nickname,
                group_reply_on_mention_only=mention_only,
            )
            mode = "仅 @ 我时回复" if mention_only else "回复所有群消息"
            self._log(f"群聊设置已保存：{mode}")
        except Exception as exc:
            self._log(f"保存群聊设置失败: {exc}")
    def _persist_api_ui_state(self):
        """Save the API fields even if 保存设置 was never clicked.

        Called when the window closes or monitoring starts, so a typed
        URL/model/key is not lost on exit. Blank values never overwrite
        the stored defaults or an existing key.
        """
        try:
            updates = {}
            api_base = self.api_base_var.get().strip()
            model = self.model_var.get().strip()
            # Only write non-empty, actually changed values. A blank field
            # keeps the stored endpoint/model instead of resetting it.
            if api_base and api_base != self.config.get("api_base"):
                updates["api_base"] = api_base
            if model and model != self.config.get("model"):
                updates["model"] = model
            key = self.api_key_var.get().strip()
            if key and key != (self.config.get("api_key") or ""):
                updates["api_key"] = key
            if not updates:
                return
            self.config.update(**updates)
            self.ai_engine.reset_client()
        except Exception:
            pass
    def _save_settings(self):
        # Never overwrite a working endpoint/model with an empty field:
        # fall back to the stored value, then to the built-in default.
        api_base = (
            self.api_base_var.get().strip()
            or self.config.get("api_base")
            or "https://api.deepseek.com"
        )
        model = (
            self.model_var.get().strip()
            or self.config.get("model")
            or "deepseek-chat"
        )
        self.api_base_var.set(api_base)
        self.model_var.set(model)
        try:
            temperature = float(self.temperature_var.get().strip())
        except ValueError:
            temperature = float(self.config.get("temperature"))
            self.temperature_var.set(str(temperature))
        try:
            max_tokens = int(float(self.max_tokens_var.get().strip()))
        except ValueError:
            max_tokens = int(self.config.get("max_tokens"))
            self.max_tokens_var.set(str(max_tokens))
        temperature = min(max(temperature, 0.0), 2.0)
        max_tokens = min(max(max_tokens, 1), 32768)
        self.temperature_var.set(str(temperature))
        self.max_tokens_var.set(str(max_tokens))
        self.config.update(
            api_key=self.api_key_var.get(),
            api_base=api_base,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            my_group_nickname=self.group_nickname_var.get().strip(),
            group_reply_on_mention_only=(
                self.group_mention_only_var.get()
            ),
            persona=self.persona_text.get("1.0", "end").strip(),
            read_delay_min=round(self._slider_read_delay_min.get(), 2),
            read_delay_max=round(self._slider_read_delay_max.get(), 2),
            typing_speed_min=round(self._slider_typing_speed_min.get(), 2),
            typing_speed_max=round(self._slider_typing_speed_max.get(), 2),
            no_reply_probability=round(
                self._slider_no_reply_probability.get(), 3
            ),
            context_length=round(self._slider_context_length.get()),
            night_mode=self.night_mode_var.get(),
            conservative_mode=self.conservative_mode_var.get(),
            show_ai_assist_notice=self.show_ai_notice_var.get(),
            auto_send_replies=self.auto_send_var.get(),
        )
        self._auto_send_replies = self.auto_send_var.get()
        self._update_auto_send_status()
        self.ai_engine.reset_client()
        messagebox.showinfo("保存", "设置已保存")
    def _persona_generate(self, optimize=False):
        """Start persona generation/optimization in a background thread."""
        api_key = self.config.get("api_key")
        if not api_key:
            messagebox.showwarning("提示", "请先在设置页填入 API Key")
            return
        samples = self.config.get("style_samples")
        if not samples:
            messagebox.showwarning(
                "提示", "还没有风格样本，请先在风格学习页采集聊天记录"
            )
            return
        current_persona = self.persona_text.get("1.0", "end").strip()
        if optimize and not current_persona:
            messagebox.showwarning(
                "提示", "请先填写或生成一个人设，再使用优化"
            )
            return

        self.persona_gen_btn.config(state="disabled")
        self.persona_optimize_btn.config(state="disabled")
        self.persona_status_label.config(text="AI 分析中，请稍候...")
        threading.Thread(
            target=self._persona_generate_worker,
            args=(optimize, current_persona,
                  self.persona_extra_var.get().strip()),
            daemon=True,
        ).start()
    def _persona_generate_worker(self, optimize, current_persona,
                                 extra_instruction):
        """Background thread: ask AI to generate or refine the persona."""
        try:
            persona = self.ai_engine.generate_persona(
                samples=self.config.get("style_samples"),
                current_persona=current_persona,
                optimize=optimize,
                extra_instruction=extra_instruction,
            )

            def _fill():
                self.persona_text.delete("1.0", "end")
                self.persona_text.insert("1.0", persona)
                self.persona_status_label.config(
                    text="已生成，请检查后点击保存设置"
                )
                self._log("人设已生成")
            self.root.after(0, _fill)
        except Exception as e:
            err = str(e)

            def _show_err():
                self.persona_status_label.config(text=f"生成失败: {err}")
                self._log(f"人设生成失败: {err}")
            self.root.after(0, _show_err)
        finally:
            def _done():
                self.persona_gen_btn.config(state="normal")
                self.persona_optimize_btn.config(state="normal")
            self.root.after(0, _done)
