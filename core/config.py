"""Configuration management with JSON persistence."""

import base64
import json
import os
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .sanitize import sanitize_text


def _sanitize_sample(text: str) -> str:
    """Remove common secrets before persisting a style sample."""
    return sanitize_text(text)


@dataclass
class AppConfig:
    """Application configuration stored as JSON."""

    # DeepSeek / OpenAI-compatible API
    api_key: str = ""
    api_base: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    temperature: float = 0.8
    # Reasoning models spend tokens on hidden reasoning before answering;
    # 150 was too small and produced empty replies.
    max_tokens: int = 800

    # Contacts to auto-reply
    contacts: list = field(default_factory=list)

    # Group chats: only reply when the user is @-mentioned (by default).
    group_chats: list = field(default_factory=list)
    my_group_nickname: str = ""
    group_reply_on_mention_only: bool = True

    # Persona description for the AI
    persona: str = ""

    # Per-contact relationship and tone overrides.
    contact_profiles: dict = field(default_factory=dict)

    # Reply safety and preview behavior.
    conservative_mode: bool = False
    show_ai_assist_notice: bool = True
    auto_send_replies: bool = False

    # Human simulation parameters
    read_delay_min: float = 2.0
    read_delay_max: float = 8.0
    typing_speed_min: float = 0.3
    typing_speed_max: float = 0.8
    no_reply_probability: float = 0.08
    night_mode: bool = True

    # Conversation context
    context_length: int = 30

    # Style learning
    style_samples: list = field(default_factory=list)
    max_style_samples: int = 2000

    # Conversation history (contact -> [{role, content}, ...])
    conversations: dict = field(default_factory=dict)


class ConfigManager:
    """Thread-safe config load/save wrapper."""

    def __init__(self, path: str = "config.json"):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._needs_persist = False
        # The API key lives here, encrypted with Windows DPAPI, never in
        # config.json. It is read before _load so the key survives restarts.
        self.secrets_path = self.path.with_name("secrets.json")
        self._stored_api_key = self._load_stored_api_key()
        self.config: AppConfig = self._load()
        # Only write when the file needs initializing or the load actually
        # changed something (legacy secrets removed, samples sanitized/deduped).
        if self._needs_persist:
            self.save()

    def _load(self) -> AppConfig:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                valid = {
                    k: v
                    for k, v in data.items()
                    if k in AppConfig.__dataclass_fields__
                }
                config = AppConfig(**valid)
                # Migrate old configs whose completion budget is too small
                # for reasoning models; otherwise content is often empty.
                if config.max_tokens < 512:
                    config.max_tokens = 800
                    self._needs_persist = True
                raw_samples = list(config.style_samples)
                config.style_samples = [
                    _sanitize_sample(sample)
                    for sample in config.style_samples
                ]
                config.style_samples = list(dict.fromkeys(
                    sample for sample in config.style_samples if len(sample) >= 2
                ))[-config.max_style_samples:]
                # Persist only if the file still holds a secret or the samples
                # were sanitized/deduped into a different form than on disk.
                if data.get("api_key") or config.style_samples != raw_samples:
                    self._needs_persist = True
                # Precedence: environment variable > locally stored secret
                # > a legacy plaintext value still present in config.json.
                config.api_key = (
                    os.getenv("DEEPSEEK_API_KEY", "")
                    or self._stored_api_key
                    or str(data.get("api_key") or "")
                )
                return config
            except (json.JSONDecodeError, TypeError):
                pass
        config = AppConfig()
        config.api_key = (
            os.getenv("DEEPSEEK_API_KEY", "") or self._stored_api_key
        )
        self._needs_persist = True
        return config

    def _load_stored_api_key(self) -> str:
        """Read the DPAPI-encrypted API key, if one is stored."""
        try:
            if not self.secrets_path.exists():
                return ""
            with open(self.secrets_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, TypeError):
            return ""
        token = data.get("api_key_dpapi") if isinstance(data, dict) else None
        if token:
            try:
                import win32crypt
                blob = base64.b64decode(token.encode("ascii"))
                _description, raw = win32crypt.CryptUnprotectData(
                    blob, None, None, None, 0
                )
                return str(raw.decode("utf-8")).strip()
            except Exception:
                return ""
        # Allow a manually supplied plaintext secrets file.
        if isinstance(data, dict):
            return str(data.get("api_key") or "").strip()
        return ""

    @staticmethod
    def _encode_secret(key: str):
        """Encrypt a secret with Windows DPAPI (tied to the current user)."""
        try:
            import win32crypt
            blob = win32crypt.CryptProtectData(
                key.encode("utf-8"), "wechat-ai-auto-reply",
                None, None, None, 0,
            )
            return {"api_key_dpapi": base64.b64encode(blob).decode("ascii")}
        except Exception:
            return None

    def _persist_api_key(self) -> None:
        """Write the API key to secrets.json (encrypted) when it changed."""
        if os.getenv("DEEPSEEK_API_KEY"):
            # An environment secret is in use; never copy it to disk.
            return
        key = str(self.config.api_key or "").strip() or self._stored_api_key
        if not key:
            return
        if key == self._stored_api_key and self.secrets_path.exists():
            return
        payload = self._encode_secret(key)
        if not payload:
            return
        tmp_path = self.secrets_path.with_suffix(
            self.secrets_path.suffix + ".tmp"
        )
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, self.secrets_path)
            self._stored_api_key = key
        except OSError:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    def save(self) -> None:
        with self._lock:
            data = asdict(self.config)
            # API keys belong in DEEPSEEK_API_KEY, never in the JSON file.
            data["api_key"] = ""
            data["style_samples"] = [
                clean for clean in (
                    _sanitize_sample(sample)
                    for sample in data.get("style_samples", [])
                ) if len(clean) >= 2
            ]
            # Atomic write: dump to a temp file in the same directory, then
            # os.replace over the target so a crash cannot leave a partial file.
            tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.path)
            except Exception:
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass
                raise
            # A key is never written into config.json; keep it in the
            # encrypted sidecar file instead.
            self._persist_api_key()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return getattr(self.config, key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if hasattr(self.config, key):
                if key in ("api_base", "model") and not str(
                    value or ""
                ).strip():
                    # An empty field must never wipe a working endpoint/model.
                    return
                if key == "api_key":
                    env_key = os.getenv("DEEPSEEK_API_KEY")
                    if env_key:
                        # Do not let a GUI save overwrite an environment secret.
                        value = env_key
                    elif not str(value or "").strip():
                        # A blank field keeps the stored key instead of
                        # silently wiping it.
                        value = self.config.api_key or self._stored_api_key
                setattr(self.config, key, value)
        self.save()

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self.config, k):
                    if k in ("api_base", "model") and not str(
                        v or ""
                    ).strip():
                        continue
                    if k == "api_key":
                        env_key = os.getenv("DEEPSEEK_API_KEY")
                        if env_key:
                            v = env_key
                        elif not str(v or "").strip():
                            v = self.config.api_key or self._stored_api_key
                    setattr(self.config, k, v)
        self.save()

    def add_style_sample(self, text: str) -> None:
        with self._lock:
            samples = self.config.style_samples
            clean = _sanitize_sample(text)
            if len(clean) >= 2 and clean not in samples:
                samples.append(clean)
                max_s = self.config.max_style_samples
                if len(samples) > max_s:
                    del samples[: len(samples) - max_s]
        self.save()

    def add_style_samples(self, texts):
        """Batch-add style samples. Returns count actually added."""
        added = 0
        with self._lock:
            samples = self.config.style_samples
            for text in texts:
                t = _sanitize_sample(text)
                if len(t) >= 2 and t not in samples:
                    samples.append(t)
                    added += 1
            max_s = self.config.max_style_samples
            if len(samples) > max_s:
                del samples[: len(samples) - max_s]
        self.save()
        return added

    def get_conversation(self, contact: str) -> list:
        with self._lock:
            return list(self.config.conversations.get(contact, []))

    def add_message(self, contact: str, role: str, content: str) -> None:
        with self._lock:
            conv = self.config.conversations.setdefault(contact, [])
            conv.append({"role": role, "content": content})
            max_len = self.config.context_length
            if len(conv) > max_len:
                del conv[: len(conv) - max_len]
        self.save()

    def clear_conversation(self, contact: str) -> None:
        with self._lock:
            self.config.conversations.pop(contact, None)
        self.save()

    def add_contact(self, name: str) -> None:
        with self._lock:
            if name.strip() and name not in self.config.contacts:
                self.config.contacts.append(name.strip())
        self.save()

    def remove_contact(self, name: str) -> None:
        with self._lock:
            if name in self.config.contacts:
                self.config.contacts.remove(name)
        self.save()

    def add_group_chat(self, name: str) -> None:
        with self._lock:
            cleaned = name.strip()
            if cleaned and cleaned not in self.config.group_chats:
                self.config.group_chats.append(cleaned)
        self.save()

    def remove_group_chat(self, name: str) -> None:
        with self._lock:
            if name in self.config.group_chats:
                self.config.group_chats.remove(name)
        self.save()

    def get_contact_profile(self, name: str) -> dict:
        """Return a normalized contact profile without exposing mutable state."""
        with self._lock:
            raw = dict(self.config.contact_profiles.get(name, {}))
        relationship = raw.get("relationship", "unknown")
        tone = raw.get("tone", "natural")
        if relationship not in {
            "close_friend", "friend", "family", "work", "unknown"
        }:
            relationship = "unknown"
        if tone not in {"natural", "casual", "playful", "conservative"}:
            tone = "natural"
        return {
            "relationship": relationship,
            "tone": tone,
            "notes": str(raw.get("notes", "")).strip(),
        }

    def set_contact_profile(self, name: str, **profile: Any) -> None:
        """Persist a validated relationship/tone profile for one contact."""
        name = name.strip()
        if not name:
            return
        relationship = profile.get("relationship", "unknown")
        tone = profile.get("tone", "natural")
        if relationship not in {
            "close_friend", "friend", "family", "work", "unknown"
        }:
            relationship = "unknown"
        if tone not in {"natural", "casual", "playful", "conservative"}:
            tone = "natural"
        new_profile = {
            "relationship": relationship,
            "tone": tone,
            "notes": str(profile.get("notes", "")).strip(),
        }
        with self._lock:
            if self.config.contact_profiles.get(name) == new_profile:
                # Nothing changed; avoid a redundant full-config write.
                return
            self.config.contact_profiles[name] = new_profile
        self.save()
