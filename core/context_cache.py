"""Persistent per-contact conversation archive.

The AI still only receives the last ``context_length`` messages, but this
archive keeps a much deeper history (default 300 messages) on disk so the
app does not have to scroll through WeChat again on every launch.
"""

import json
import os
import threading
from pathlib import Path

MAX_MESSAGES = 300


class ContextCache:
    """Thread-safe, atomically persisted conversation archive."""

    def __init__(self, path=None, max_messages=MAX_MESSAGES,
                 save_every=20):
        self.path = Path(path) if path else None
        self.max_messages = max(1, int(max_messages))
        self.save_every = max(1, int(save_every))
        self._lock = threading.RLock()
        self._data = self._load()
        self._dirty = False
        self._unsaved = 0

    def _clean(self, messages):
        result = []
        seen = set()
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = str(message.get("content") or "").strip()
            if role not in ("user", "assistant") or not content:
                continue
            key = (role, content)
            if key in seen:
                continue
            seen.add(key)
            result.append({"role": role, "content": content})
        return result[-self.max_messages:]

    def _load(self):
        if not self.path or not self.path.exists():
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, TypeError):
            return {}
        if not isinstance(data, dict):
            return {}
        loaded = {}
        for contact, messages in data.items():
            cleaned = self._clean(messages)
            if cleaned:
                loaded[str(contact)] = cleaned
        return loaded

    def has(self, contact):
        with self._lock:
            return bool(self._data.get(contact))

    def get(self, contact):
        with self._lock:
            return list(self._data.get(contact, []))

    def merge(self, contact, messages):
        """Merge messages into a contact's archive, returning the result."""
        with self._lock:
            old = self._data.get(contact, [])
            merged = self._clean(list(old) + list(messages or []))
            if merged != old:
                self._data[contact] = merged
                self._dirty = True
                self._unsaved += 1
                if self._unsaved >= self.save_every:
                    self.save()
            return list(merged)

    def append(self, contact, role, content):
        return self.merge(
            contact, [{"role": role, "content": content}]
        )

    def save(self, force=False):
        with self._lock:
            if not self.path:
                return
            if not self._dirty and not force:
                return
            data = {
                contact: messages
                for contact, messages in self._data.items()
                if messages
            }
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
                self._dirty = False
                self._unsaved = 0
            except OSError:
                try:
                    if tmp.exists():
                        tmp.unlink()
                except OSError:
                    pass


__all__ = ["ContextCache", "MAX_MESSAGES"]
