"""Listener, message processing and auto-send worker mixin."""

import logging
import threading
import time
from tkinter import messagebox

from .theme import *

logger = logging.getLogger(__name__)


class WorkerMixin:
    def _auto_send_label(self):
        return "自动发送：开启" if self._auto_send_replies else "自动发送：关闭"
    def _update_auto_send_status(self):
        if hasattr(self, "auto_send_status"):
            self.auto_send_status.config(text=self._auto_send_label())
        if hasattr(self, "status_detail") and self._running:
            mode = "自动发送" if self._auto_send_replies else "仅填充消息框"
            self.status_detail.config(text=f"正在监听当前聊天 · {mode}")
    def _toggle_auto_send(self):
        """Change sending mode independently from the listener thread."""
        self._auto_send_replies = bool(self.auto_send_var.get())
        self.config.set("auto_send_replies", self._auto_send_replies)
        self._update_auto_send_status()
        self._update_floating_window()
        mode = "开启" if self._auto_send_replies else "关闭"
        self._log(f"自动发送已{mode}；监听仍保持运行")
    def _toggle_worker(self):
        if self._running:
            self._stop_worker()
        else:
            self._start_worker()
    def _start_worker(self):
        # Persist API fields typed in the settings page before checking them.
        if hasattr(self, "_persist_api_ui_state"):
            self._persist_api_ui_state()
        api_key = self.config.get("api_key")
        if not api_key:
            messagebox.showwarning("提示", "请先在设置页填入 DeepSeek API Key")
            return

        # Guard against starting while an old thread is still alive
        if self._worker_thread and self._worker_thread.is_alive():
            self._log("上一个监听线程仍在退出，请稍候...")
            return

        self.start_btn.config(text="启动中...", state="normal")
        self._running = True
        self._stop_event.clear()
        self._group_nickname_warned = False
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True
        )
        self._worker_thread.start()
    def _worker_loop(self):
        """Main worker loop: poll current chat for new messages."""
        try:
            self.wx_agent.connect()
            self._log("已连接到微信")

            # Keep the newest incoming text as a one-shot pending candidate.
            # This covers messages received just before monitoring starts.
            self.wx_agent.reset_msg_count(preserve_latest_incoming=True)
            current_chat = self.wx_agent.get_current_chat_name()
            if current_chat:
                self._log(f"当前聊天: {current_chat}")
                self._review_context(current_chat)
                self._save_context_cache()
            self._log("开始监听当前聊天窗口")

            self.root.after(0, self._on_worker_started)

            poll_interval = 2  # seconds
            last_chat = current_chat

            while not self._stop_event.is_set():
                # Check if chat switched
                chat = self.wx_agent.get_current_chat_name()
                if chat and chat != last_chat:
                    self._log(f"切换到聊天: {chat}")
                    last_chat = chat
                    self.wx_agent.reset_msg_count(
                        preserve_latest_incoming=True
                    )
                    self._review_context(chat, force=True)
                    self._save_context_cache()

                # Group settings may change while monitoring.
                group_chats = set(self.config.get("group_chats") or [])
                mention_only = bool(
                    self.config.get("group_reply_on_mention_only", True)
                )
                nickname = self.config.get("my_group_nickname", "")
                if (
                    group_chats and mention_only and not nickname.strip()
                    and not getattr(self, "_group_nickname_warned", False)
                ):
                    self._group_nickname_warned = True
                    self._log(
                        "提示：群聊仅@回复已开启，但未设置“我的群昵称”，"
                        "群消息会被跳过"
                    )

                # Get new messages
                new_msgs = self.wx_agent.get_new_messages()
                for msg in new_msgs:
                    text = msg.get("text", "")
                    if not text:
                        continue
                    contact = chat or "当前聊天"
                    is_group = contact in group_chats
                    if is_group:
                        prepared = self.human_sim.prepare_group_message(
                            text, nickname, mention_only
                        )
                        if prepared is None:
                            # Keep non-@ group traffic in the in-memory
                            # context so the model still understands the
                            # conversation, but never reply to it.
                            self._append_context(contact, "user", text)
                            self._log(f"群消息未@我，跳过: {text[:40]}")
                            continue
                        text = prepared
                        mode = "仅@回复" if mention_only else "回复所有"
                        self._log(f"群消息[{mode}] 收到: {text[:60]}")
                    else:
                        self._log(f"收到: {text[:60]}")
                    self._process_message(
                        contact, contact, text, None, is_group=is_group,
                        group_mention_only=mention_only,
                    )

                if self._stop_event.wait(poll_interval):
                    break

        except Exception as e:
            self._log(f"错误: {e}")
            logger.exception("Worker error")
        finally:
            self._cleanup_worker()
    def _on_worker_started(self):
        self.status_badge.config(bg=PRIMARY_SOFT)
        self.status_label.config(
            text="● 运行中", bg=PRIMARY_SOFT, fg=PRIMARY_DK
        )
        self.status_dot.config(fg=PRIMARY_DK)
        self.status_detail.config(
            text=(
                "正在监听当前聊天 · "
                + ("自动发送" if self._auto_send_replies else "仅填充消息框")
            )
        )
        self.start_btn.config(
            text="停止自动监听", style="Danger.TButton", state="normal"
        )
        self._update_floating_window()
    def _trim_context(self, context):
        limit = max(8, int(self.config.get("context_length")))
        return list(context[-limit:])
    def _merge_context(self, older, newer):
        """Merge persisted history with newer messages, keeping order."""
        merged = []
        seen = set()
        for message in list(older or []) + list(newer or []):
            role = message.get("role")
            content = (message.get("content") or "").strip()
            if not content:
                continue
            key = (role, content)
            if key in seen:
                continue
            seen.add(key)
            merged.append({"role": role, "content": content})
        return merged
    def _remember_context(self, contact, merged):
        """Update the AI context window and the deep on-disk archive."""
        with self._context_cache_lock:
            self._context_cache[contact] = self._trim_context(merged)
        store = getattr(self, "_context_store", None)
        if store is not None:
            store.merge(contact, merged)
    def _append_context(self, contact, role, content):
        """Append a message to the context window and deep archive."""
        content = (content or "").strip()
        if not content:
            return
        with self._context_cache_lock:
            context = self._context_cache.setdefault(contact, [])
            context.append({"role": role, "content": content})
            self._context_cache[contact] = self._trim_context(context)
        store = getattr(self, "_context_store", None)
        if store is not None:
            store.append(contact, role, content)
    def _get_cached_context(self, contact):
        with self._context_cache_lock:
            return list(self._context_cache.get(contact, []))
    def _review_context(self, contact, force=False):
        """Use the deep archive when available; seed it once otherwise.

        Cached chats only sync the currently visible messages (no Page Up
        scrolling). A chat without any archive gets one deep review.
        """
        cached = self._get_cached_context(contact)
        if cached and not force:
            return cached

        fallback = self.config.get_conversation(contact)
        store = getattr(self, "_context_store", None)
        archived = store.get(contact) if store is not None else []
        base = archived or fallback

        if self._user_is_typing():
            # Scrolling the chat would steal focus from the user's input.
            self._log("检测到你在微信输入框输入，跳过上下文回看")
            self._remember_context(contact, base)
            return self._get_cached_context(contact)

        try:
            if archived:
                visible = self.wx_agent.get_visible_context()
                merged = self._merge_context(archived, visible)
                self._remember_context(contact, merged)
                self._log(
                    f"使用本地缓存 {len(archived)} 条，"
                    f"同步可见消息 {len(visible)} 条（未翻页）"
                )
                return self._get_cached_context(contact)

            # First time for this chat: deep review once, then cache it.
            self._log("首次缓存该聊天，正在深度回看...")
            reviewed = self.wx_agent.review_current_context(
                max_pages=30,
                max_messages=300,
                check_stop=lambda: self._stop_event.is_set(),
            )
            merged = self._merge_context(fallback, reviewed)
            if merged:
                self._remember_context(contact, merged)
                self._log(f"已缓存 {len(merged)} 条上下文")
                return self._get_cached_context(contact)
        except Exception as e:
            self._log(f"上下文查看失败，使用已有记录: {e}")

        self._remember_context(contact, base)
        return self._get_cached_context(contact)
    def _process_message(self, contact, sender, text, chat=None,
                         is_group=False, group_mention_only=True):
        """Process a single incoming message with AI + human simulation."""
        history = self.config.get_conversation(contact)
        if any(
            m.get("role") == "assistant" and m.get("content") == text
            for m in history
        ):
            self._log(f"跳过自己发送过的消息: {text[:40]}")
            return

        # The first message for a chat triggers one visual context review;
        # later messages only extend the local cache.
        reply_history = self._review_context(contact)
        if not any(
            m.get("role") == "user" and m.get("content") == text
            for m in reply_history
        ):
            self._append_context(contact, "user", text)
            self.config.add_message(contact, "user", text)

        if self.human_sim.is_trivial_message(text):
            self._log(f"跳过简短消息: {text}")
            return

        if not self.human_sim.should_reply(
            text=text, history=reply_history, contact=contact
        ):
            self._log(f"不回复 {sender} (模拟忽略)")
            return

        delay = self.human_sim.reading_delay(text=text, history=reply_history)
        self._log(f"阅读延迟 {delay:.1f}s...")
        if self._stop_event.wait(delay):
            return

        # The user may start typing during the reading delay; never
        # overwrite a manual draft.
        if self._auto_send_replies and self._user_is_typing():
            self._log("检测到你在微信输入框手动输入，已跳过自动回复")
            return

        try:
            if self._stop_event.is_set():
                return
            # The newly received message is already in the cache.
            cached_history = self._get_cached_context(contact)
            if cached_history and cached_history[-1].get("content") == text:
                cached_history = cached_history[:-1]
            reply = self.ai_engine.generate_reply(
                contact, text, history=cached_history, is_group=is_group,
                group_mention_only=group_mention_only,
            )
        except Exception as e:
            self._log(f"AI 生成失败: {e}")
            return

        if self._stop_event.is_set():
            return

        if reply is None:
            reason = getattr(
                self.ai_engine, "last_skip_reason", ""
            ) or "no_reply"
            self._log(f"AI 判断无需回复: {text[:40]} ({reason})")
            if str(reason).startswith("empty_content"):
                self._log(
                    "提示：模型返回空内容，可能是 max_tokens 太小。"
                    "推理模型建议在设置页把最大 tokens 调到 800 以上"
                )
            return

        self._log(f"AI 回复: {reply[:80]}")

        parts = self.human_sim.split_message(reply)
        if not self._auto_send_replies:
            self._fill_reply_draft(contact, parts)
            self._log("自动发送关闭，回复已填入消息框")
            return

        sent_parts = []
        for i, part in enumerate(parts):
            if self._stop_event.is_set():
                self._save_sent_parts(contact, sent_parts)
                return
            td = self.human_sim.typing_delay(part)
            self._log(f"打字延迟 {td:.1f}s (部分 {i+1}/{len(parts)})")
            if self._stop_event.wait(td):
                self._save_sent_parts(contact, sent_parts)
                return
            if self._user_is_typing():
                self._log("检测到你在手动输入，已取消本次自动发送")
                self._save_sent_parts(contact, sent_parts)
                return
            ok = self.wx_agent.send_message(
                part, respect_user_draft=True
            )
            if ok:
                sent_parts.append(part)
                self._log(f"已发送: {part[:50]}")
            else:
                if getattr(
                    self.wx_agent, "last_send_error", ""
                ) == "user_draft":
                    self._log("检测到你正在输入，已取消发送，草稿已保留")
                else:
                    self._log(f"发送失败: {part[:50]}")
                self._save_sent_parts(contact, sent_parts)
                return
            if i < len(parts) - 1:
                gap = self.human_sim.inter_message_delay()
                if self._stop_event.wait(gap):
                    self._save_sent_parts(contact, sent_parts)
                    return

        self._save_sent_parts(contact, sent_parts)
    def _user_is_typing(self):
        """True when the WeChat input box already contains user text."""
        try:
            return bool(self.wx_agent.get_input_draft())
        except Exception:
            return False
    def _save_sent_parts(self, contact, sent_parts):
        """Persist only the parts that were actually sent."""
        if not sent_parts:
            return
        text = " ".join(sent_parts)
        self.config.add_message(contact, "assistant", text)
        self._append_context(contact, "assistant", text)
    def _fill_reply_draft(self, contact, parts):
        """Fill the manual-send composer without sending or saving history."""
        draft = "\n".join(parts).strip()
        if not draft:
            return

        def update_ui():
            try:
                self.send_contact_var.set(contact)
                self.send_msg_text.delete("1.0", "end")
                self.send_msg_text.insert("1.0", draft)
                self._show_tab("send")
                self.send_msg_text.focus_set()
            except Exception as exc:
                self._log(f"填充回复草稿失败: {exc}")

        self.root.after(0, update_ui)
    def _stop_worker(self):
        """Stop auto-reply. Immediately resets UI without waiting for thread."""
        self._stop_event.set()
        self._running = False
        self._log("正在停止...")
        # Immediately reset UI so user can interact again
        self.status_badge.config(bg=DANGER_SOFT)
        self.status_label.config(
            text="● 已停止", bg=DANGER_SOFT, fg=DANGER
        )
        self.status_dot.config(fg=TEXT_LIGHT)
        self.status_detail.config(text="未启动 — 手动打开聊天后点击开始")
        self.start_btn.config(
            text="开启自动监听", style="Primary.TButton", state="normal"
        )
        self._update_floating_window()
        self._save_context_cache()
        self._log("自动回复已停止")
    def _cleanup_worker(self):
        """Fallback cleanup when worker thread exits naturally."""
        self._save_context_cache()
        try:
            self.wx_agent.stop_listening()
            self.wx_agent.disconnect()
        except Exception:
            pass
        # Only update UI if still running (stop button may have already reset)
        if self._running:
            try:
                self.root.after(0, self._on_worker_stopped)
            except Exception:
                pass
    def _on_worker_stopped(self):
        self.status_badge.config(bg=DANGER_SOFT)
        self.status_label.config(
            text="● 已停止", bg=DANGER_SOFT, fg=DANGER
        )
        self.status_dot.config(fg=TEXT_LIGHT)
        self.status_detail.config(text="未启动 — 手动打开聊天后点击开始")
        self._running = False
        self._stop_event.clear()
        self.start_btn.config(
            text="开启自动监听", style="Primary.TButton", state="normal"
        )
        self._update_floating_window()
        self._log("自动回复已停止")
