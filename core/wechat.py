"""WeChat operation layer using raw uiautomation for WeChat 4.x.

No external wxauto dependency. Directly uses Windows UI Automation
to find controls, read messages, and send text via clipboard paste.
"""

import logging
import threading
import time
from collections import deque

import ctypes
import pythoncom
import win32clipboard
import win32con
import win32gui
import uiautomation as uia
from PIL import Image

logger = logging.getLogger(__name__)


def _find_wechat_hwnd():
    """Find the WeChat 4.x main window handle.

    Uses FindWindow only. EnumWindows is intentionally avoided: on some
    systems it raises pywintypes.error(2) while scanning unstable
    windows, which is unrelated to WeChat.
    """
    # Exact class + title lookup (WeChat 4.x default)
    try:
        hwnd = win32gui.FindWindow("Qt51514QWindowIcon", "微信")
        if hwnd:
            return hwnd
    except Exception:
        pass

    # Fallback: match by class name alone (title may have been changed)
    try:
        hwnd = win32gui.FindWindow("Qt51514QWindowIcon", None)
        if hwnd:
            return hwnd
    except Exception:
        pass

    return None


def _bring_to_front(hwnd):
    """Bring window to foreground (best-effort)."""
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _walk_children(ctrl, max_depth=25):
    """Recursively yield (control, depth) for all descendants."""
    stack = [(ctrl, 0)]
    while stack:
        c, d = stack.pop()
        yield c, d
        if d < max_depth:
            try:
                for child in c.GetChildren():
                    stack.append((child, d + 1))
            except Exception:
                pass


def _find_by(ctrl, class_name=None, auto_id=None, control_type=None,
             name=None, max_depth=25):
    """Find first descendant matching all given criteria."""
    for c, _ in _walk_children(ctrl, max_depth):
        try:
            if class_name and class_name not in (c.ClassName or ""):
                continue
            if auto_id and auto_id not in (c.AutomationId or ""):
                continue
            if control_type and c.ControlTypeName != control_type:
                continue
            if name and c.Name != name:
                continue
            return c
        except Exception:
            continue
    return None


def _set_clipboard_text(text):
    """Set the system clipboard to the given Unicode text."""
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(
            win32clipboard.CF_UNICODETEXT, text
        )
    finally:
        win32clipboard.CloseClipboard()


def _has_multiple_monitors():
    """Return whether Windows currently reports more than one monitor."""
    try:
        # SM_CMONITORS (80) reports the number of display monitors.
        return ctypes.windll.user32.GetSystemMetrics(80) > 1
    except Exception:
        return False


# Virtual key codes
_VK_CONTROL = 0x11
_VK_RETURN = 0x0D
_VK_V = 0x56
_VK_A = 0x41
_VK_DELETE = 0x2E
_VK_PRIOR = 0x21   # Page Up
_VK_END = 0x23     # End


def _key_down(vk):
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)


def _key_up(vk):
    ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)


def _press_key(vk, delay=0.03):
    _key_down(vk)
    time.sleep(delay)
    _key_up(vk)


def _ctrl_combo(vk, delay=0.03):
    _key_down(_VK_CONTROL)
    time.sleep(delay)
    _key_down(vk)
    time.sleep(delay)
    _key_up(vk)
    time.sleep(delay)
    _key_up(_VK_CONTROL)


def _is_input_focused(input_field):
    """Check if the input field already has keyboard focus."""
    try:
        focused = uia.GetFocusedControl()
        return focused and focused.Name == input_field.Name
    except Exception:
        return False


class WeChatAgent:
    """Wraps WeChat 4.x via raw UI Automation."""

    def __init__(self):
        self._hwnd = None
        self._ctrl = None
        self._lock = threading.Lock()
        self._last_msg_count = 0
        self._last_msg_text = ""
        self._recent_sent = deque(maxlen=80)
        self.last_send_error = ""
        self._msg_list_ctrl = None
        self._input_field_ctrl = None

    @property
    def is_connected(self):
        return self._ctrl is not None

    def connect(self):
        """Find and connect to the WeChat window."""
        with self._lock:
            if self._ctrl:
                return
            pythoncom.CoInitialize()
            hwnd = _find_wechat_hwnd()
            if not hwnd:
                raise RuntimeError(
                    "未找到微信窗口，请确保微信 4.x 已登录且窗口未最小化"
                )
            _bring_to_front(hwnd)
            time.sleep(0.5)
            ctrl = uia.ControlFromHandle(hwnd)
            if not ctrl:
                raise RuntimeError("无法连接到微信窗口的 UI Automation 接口")
            self._hwnd = hwnd
            self._ctrl = ctrl
            self._clear_cached_controls()

    def _clear_cached_controls(self):
        """Drop cached control references (call under self._lock)."""
        self._msg_list_ctrl = None
        self._input_field_ctrl = None

    def ensure_connected(self):
        if not self._ctrl:
            self.connect()

    def is_online(self):
        return self._ctrl is not None

    # ── Session list ─────────────────────────────────────────────────

    def get_session_contacts(self):
        """Return list of (name, preview) for recent sessions."""
        ctrl = self._ctrl
        if not ctrl:
            return []
        session_list = _find_by(ctrl, auto_id="session_list")
        if not session_list:
            return []
        results = []
        for item in session_list.GetChildren():
            try:
                name = item.Name or ""
                # Parse: "联系人名\n已置顶\n预览消息\n时间\n" or similar
                parts = name.split("\n")
                contact = parts[0].strip() if parts else ""
                if contact:
                    results.append(contact)
            except Exception:
                pass
        return results

    def get_current_chat_name(self):
        """Get the name of the currently open chat.

        Reads the input field's placeholder name and strips the
        '输入文字...' placeholder suffix that WeChat 4.x appends.
        """
        ctrl = self._ctrl
        if not ctrl:
            return None
        input_field = self._find_input_field()
        if input_field and input_field.Name:
            name = input_field.Name.strip()
            # Strip the placeholder text appended by WeChat, e.g.
            # "<联系人昵称>输入文字，或按住..."
            for suffix in ["输入文字", "输入文字，或按住"]:
                idx = name.find(suffix)
                if idx > 0:
                    name = name[:idx].strip()
                    break
            return name if name else None
        return None

    # ── Message reading ──────────────────────────────────────────────

    @staticmethod
    def _ctrl_is_valid(ctrl):
        """Cheap liveness check for a cached UIA control reference.

        Accessing BoundingRectangle on a stale element raises, so a
        successful read means the control is still attached to the tree.
        """
        if ctrl is None:
            return False
        try:
            ctrl.BoundingRectangle
            return True
        except Exception:
            return False

    def _find_msg_list(self):
        """Find the chat message list control (cached)."""
        ctrl = self._ctrl
        if not ctrl:
            return None
        if self._ctrl_is_valid(self._msg_list_ctrl):
            return self._msg_list_ctrl
        # Try by auto_id first, then by class name
        for criteria in [
            {"auto_id": "chat_message_list"},
            {"class_name": "RecyclerListView"},
        ]:
            found = _find_by(ctrl, **criteria)
            if found:
                self._msg_list_ctrl = found
                return found
        self._msg_list_ctrl = None
        return None

    def _find_input_field(self):
        """Find the chat input field control (cached)."""
        ctrl = self._ctrl
        if not ctrl:
            return None
        if self._ctrl_is_valid(self._input_field_ctrl):
            return self._input_field_ctrl
        for criteria in [
            {"auto_id": "chat_input_field"},
            {"class_name": "ChatInputField"},
        ]:
            found = _find_by(ctrl, **criteria)
            if found:
                self._input_field_ctrl = found
                return found
        self._input_field_ctrl = None
        return None

    def get_input_draft(self):
        """Return text currently typed into the chat input box.

        WeChat 4.x exposes the editable text through the UIA Value
        pattern. An empty string means the box is empty.
        """
        field = self._find_input_field()
        if not field:
            return ""
        try:
            value = field.GetValuePattern().Value
        except Exception:
            value = ""
        return str(value or "").strip()

    def has_user_draft(self):
        """True when the input box contains something the user typed."""
        return bool(self.get_input_draft())

    def get_messages(self):
        """Read all visible text messages from the current chat.

        Returns list of dicts: {text, class_name, is_self, side}.

        WeChat 4.x does not expose sender info through UI Automation
        (all items span the full list width and have identical
        properties), so we use a screenshot: the user's own messages
        are rendered as green bubbles on the RIGHT side, while the
        friend's messages are white bubbles on the LEFT.
        """
        msg_list = self._find_msg_list()
        if not msg_list:
            return []

        # _capture_list_screenshot already returns None for unusable grabs,
        # so the batch validity is known once and reused for every row.
        screenshot = self._capture_list_screenshot(msg_list)
        screenshot_usable = screenshot is not None
        list_rect = msg_list.BoundingRectangle

        messages = []
        # RecyclerListView is virtualized; GetChildren() returns 0,
        # so walk descendants to find the message bubble items.
        for c, _ in _walk_children(msg_list, max_depth=6):
            try:
                cls = c.ClassName or ""
                name = (c.Name or "").strip()
                if not name:
                    continue
                if "Chat" not in cls or "RecyclerListView" in cls:
                    continue
                # Skip time separators (plain ChatItemView with short text)
                if cls == "mmui::ChatItemView" and len(name) <= 6:
                    continue
                side = self._get_message_side(
                    c, screenshot, list_rect, screenshot_usable
                )
                if side == "unknown":
                    # Rect may be stale relative to the batch screenshot;
                    # retry with a fresh row screenshot before giving up.
                    side = self._get_message_side(c)
                messages.append({
                    "text": name,
                    "class_name": cls,
                    "is_self": side == "right",
                    "side": side,
                })
            except Exception:
                continue
        # _walk_children uses a stack (LIFO), so items are yielded
        # bottom-to-top (newest first). Reverse to get chronological
        # order: messages[0] = oldest (top), messages[-1] = newest.
        messages.reverse()
        return messages

    def get_visible_context(self):
        """Return visible text messages as role/content without scrolling."""
        context = []
        for message in self.get_messages():
            if "ChatTextItemView" not in message.get("class_name", ""):
                continue
            side = message.get("side")
            if side not in ("left", "right"):
                continue
            context.append({
                "role": "assistant" if side == "right" else "user",
                "content": message["text"],
            })
        return context

    def _capture_list_screenshot(self, msg_list):
        """Capture the message list area for bubble-color analysis."""
        try:
            rect = msg_list.BoundingRectangle
            shot = self._grab_region(
                (rect.left, rect.top, rect.right, rect.bottom)
            )
            return shot if self._is_usable_screenshot(shot) else None
        except Exception:
            return None

    @staticmethod
    def _grab_region(bbox):
        """Capture a region, enabling all-screens mode only when needed."""
        from PIL import ImageGrab
        multi_monitor = _has_multiple_monitors()
        try:
            if multi_monitor:
                return ImageGrab.grab(bbox=bbox, all_screens=True)
            return ImageGrab.grab(bbox=bbox)
        except TypeError:
            return ImageGrab.grab(bbox=bbox)

    @staticmethod
    def _is_usable_screenshot(image):
        """Reject black/empty captures that would corrupt side detection."""
        if image is None:
            return False
        try:
            return image.getbbox() is not None
        except Exception:
            return False

    @staticmethod
    def _is_green_pixel(r, g, b):
        """WeChat default theme bubble green (~#9DF29F)."""
        return (
            g > 150 and r < 160 and b < 160
            and g > r + 40 and g > b + 40
        )

    @staticmethod
    def _is_dark_pixel(r, g, b):
        """Text/avatar pixels are much darker than the white/green bubble."""
        return r + g + b < 330

    @staticmethod
    def _count_region_colors(region):
        """Count green and dark pixels in a small RGB image region.

        Uses getcolors() (C-level histogram) instead of per-pixel
        getpixel() loops. Returns (green_count, dark_count).
        """
        green = 0
        dark = 0
        try:
            colors = region.getcolors(
                maxcolors=region.width * region.height
            )
        except Exception:
            return green, dark
        if not colors:
            return green, dark
        for count, pixel in colors:
            r, g, b = pixel[:3]
            if WeChatAgent._is_green_pixel(r, g, b):
                green += count
            elif WeChatAgent._is_dark_pixel(r, g, b):
                dark += count
        return green, dark

    def _get_message_side(self, item, screenshot=None, list_rect=None,
                          screenshot_usable=None):
        """Return 'left' (friend), 'right' (self), or 'unknown'.

        ``screenshot_usable`` is the batch screenshot validity verdict
        computed once by get_messages(); when a batch screenshot is
        provided the full-image validation is not repeated here. Only a
        freshly captured row screenshot (screenshot is None) is
        validated here.
        """
        try:
            rect = item.BoundingRectangle
            if screenshot is None:
                shot = self._grab_region(
                    (rect.left, rect.top, rect.right, rect.bottom)
                )
                if not self._is_usable_screenshot(shot):
                    return "unknown"
                x0, y0 = 0, 0
                x1, y1 = shot.width, shot.height
            else:
                if screenshot_usable is False:
                    return "unknown"
                shot = screenshot
                x0 = max(0, rect.left - list_rect.left)
                x1 = min(shot.width, rect.right - list_rect.left)
                y0 = max(0, rect.top - list_rect.top)
                y1 = min(shot.height, rect.bottom - list_rect.top)
            if x1 <= x0 or y1 <= y0:
                return "unknown"

            # Crop the row and sample it down so the color scan runs on
            # small images instead of the full screenshot.
            row = shot.crop((x0, y0, x1, y1))
            if row.mode != "RGB":
                row = row.convert("RGB")
            sample = row
            if row.width > 96 or row.height > 48:
                sample = row.resize(
                    (max(1, row.width // 2), max(1, row.height // 2)),
                    resample=Image.NEAREST,
                )
            # Split the row into left/right halves and histogram each.
            mid = sample.width // 2
            left_half = sample.crop((0, 0, mid, sample.height))
            right_half = sample.crop((mid, 0, sample.width, sample.height))
            green_left, dark_left = self._count_region_colors(left_half)
            green_right, dark_right = self._count_region_colors(right_half)

            # Own messages use the green bubble on the right.
            if green_right > 5:
                return "right"
            if green_left > 5 and green_right <= 5:
                return "left"
            # Friend messages are white bubbles on the left; compare the
            # horizontal center of the text/avatar pixels when color is
            # inconclusive.
            if dark_left + dark_right > 10:
                return "left" if dark_left > dark_right else "right"
            return "unknown"
        except Exception:
            return "unknown"

    def get_new_messages(self):
        """Get messages that arrived since last check.

        Returns list of new message dicts. Assumes all new messages
        are incoming (friend), since we adjust count after our own sends.
        """
        all_msgs = self.get_messages()
        current_count = len(all_msgs)
        new_msgs = []

        if current_count > self._last_msg_count:
            new_count = current_count - self._last_msg_count
            new_msgs = all_msgs[-new_count:]
        elif current_count == self._last_msg_count and all_msgs:
            last_text = all_msgs[-1]["text"]
            if last_text != self._last_msg_text:
                new_msgs = [all_msgs[-1]]

        self._last_msg_count = current_count
        if all_msgs:
            self._last_msg_text = all_msgs[-1]["text"]

        # Only friend messages trigger auto-reply; skip our own green
        # bubbles (whether sent manually or by this program).
        return [
            m for m in new_msgs
            if "ChatTextItemView" in m["class_name"]
            and m.get("side") == "left"
            and not self._is_recent_sent(m["text"])
        ]

    def review_current_context(self, max_pages=2, max_messages=12,
                               on_progress=None, check_stop=None):
        """Scroll up briefly, read recent context, then return to the bottom.

        The returned roles match the conversation format used by AIEngine:
        left-side messages are ``user`` and right-side messages are
        ``assistant``. The review is deliberately short so monitoring still
        feels like a person glancing at the previous messages.
        """
        ctrl = self._ctrl
        if not ctrl:
            raise RuntimeError("WeChat not connected")
        hwnd = self._hwnd

        msg_list = self._find_msg_list()
        if not msg_list:
            return []

        def read_visible():
            visible = []
            for msg in self.get_messages():
                if "ChatTextItemView" not in msg["class_name"]:
                    continue
                side = msg.get("side")
                if side not in ("left", "right"):
                    continue
                visible.append({
                    "role": "assistant" if side == "right" else "user",
                    "content": msg["text"],
                })
            return visible

        def merge_older(older, newer):
            merged = []
            seen = set()
            for message in older + newer:
                key = (message["role"], message["content"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(message)
            return merged

        context = []
        try:
            context = read_visible()
            if on_progress:
                on_progress(0, len(context))

            # Focus the chat list so Page Up/End operate on the conversation.
            _bring_to_front(hwnd)
            time.sleep(0.15)
            rect = msg_list.BoundingRectangle
            cx = int((rect.left + rect.right) / 2)
            cy = int(rect.top + (rect.bottom - rect.top) * 0.2)
            ctypes.windll.user32.SetCursorPos(cx, cy)
            time.sleep(0.05)
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.02)
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.15)

            for page in range(max_pages):
                if check_stop and check_stop():
                    break
                # Stop as soon as enough context has been collected instead
                # of always scrolling the fixed number of pages.
                if len(context) >= max_messages:
                    break
                before = tuple(
                    (m["role"], m["content"]) for m in context
                )
                _press_key(_VK_PRIOR, delay=0.03)
                time.sleep(0.35)
                visible = read_visible()
                context = merge_older(visible, context)
                if on_progress:
                    on_progress(page + 1, len(context))
                after = tuple(
                    (m["role"], m["content"]) for m in context
                )
                if after == before:
                    break
        finally:
            # Monitoring must always leave the chat at the newest messages.
            _press_key(_VK_END, delay=0.04)
            time.sleep(0.3)

        return context[-max_messages:]

    def reset_msg_count(self, preserve_latest_incoming=False):
        """Reset polling baseline, optionally keeping the latest incoming text.

        Monitoring is often started after a friend has already sent a message.
        In that case skipping the entire visible list would lose the newest
        pending message. We keep only that final left-side text message as a
        one-shot candidate; all older messages remain part of the baseline.
        """
        msgs = self.get_messages()
        preserve = bool(
            preserve_latest_incoming
            and msgs
            and "ChatTextItemView" in msgs[-1].get("class_name", "")
            and msgs[-1].get("side") == "left"
            and not self._is_recent_sent(msgs[-1].get("text", ""))
        )
        baseline_count = len(msgs) - 1 if preserve else len(msgs)
        self._last_msg_count = max(0, baseline_count)
        if baseline_count > 0:
            self._last_msg_text = msgs[baseline_count - 1]["text"]
        else:
            self._last_msg_text = ""

    def bump_msg_count(self, n=1):
        """Increment message counter by n after we send messages.

        This prevents our own sent messages from being detected as
        new incoming messages on the next poll.
        """
        self._last_msg_count += n

    def _remember_sent(self, text):
        """Remember outgoing text so polling never treats it as incoming."""
        with self._lock:
            self._recent_sent.append((time.time(), text))

    def _is_recent_sent(self, text, window=90):
        """True if the text was sent by this app within the window."""
        now = time.time()
        with self._lock:
            kept = deque(maxlen=self._recent_sent.maxlen)
            for sent_at, sent_text in self._recent_sent:
                if now - sent_at <= window:
                    kept.append((sent_at, sent_text))
            self._recent_sent = kept
            return any(sent_text == text for _, sent_text in kept)

    # ── Sending ──────────────────────────────────────────────────────

    def send_message(self, text, respect_user_draft=False):
        """Send a text message to the current chat via clipboard paste.

        Uses SetFocus instead of Click to avoid accidentally closing
        the chat. Uses ctypes keybd_event for reliable keyboard input.

        When ``respect_user_draft`` is true (automatic replies), a
        non-empty input box means the user is typing, so sending is
        cancelled and the draft is left untouched.
        """
        self.last_send_error = ""
        ctrl = self._ctrl
        if not ctrl:
            raise RuntimeError("WeChat not connected")

        input_field = self._find_input_field()
        if not input_field:
            raise RuntimeError("找不到输入框，请确保聊天窗口已打开")

        if respect_user_draft and self.get_input_draft():
            self.last_send_error = "user_draft"
            return False

        # Focus the input field without clicking (avoids closing chat)
        if not _is_input_focused(input_field):
            try:
                input_field.SetFocus()
            except Exception:
                # Fallback: click at the center of the input field only
                rect = input_field.BoundingRectangle
                cx = int((rect.left + rect.right) / 2)
                cy = int((rect.top + rect.bottom) / 2)
                ctypes.windll.user32.SetCursorPos(cx, cy)
                time.sleep(0.05)
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                time.sleep(0.03)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.3)

        # Re-check right before clearing; the user may have started typing
        # while focus was being set.
        if respect_user_draft and self.get_input_draft():
            self.last_send_error = "user_draft"
            return False

        # Clear any existing text (Ctrl+A then Delete)
        _ctrl_combo(_VK_A)
        time.sleep(0.05)
        _press_key(_VK_DELETE)
        time.sleep(0.1)

        # Set clipboard and paste
        _set_clipboard_text(text)
        time.sleep(0.1)
        _ctrl_combo(_VK_V)
        time.sleep(0.3)

        # Remember the outgoing text before it appears so the polling
        # thread never treats our own send as an incoming message.
        self._remember_sent(text)
        _press_key(_VK_RETURN)
        time.sleep(0.3)
        return True

    def send_to_contact(self, contact, text):
        """Send a message to a specific contact.

        Only clicks the session item if that chat is not already open,
        to avoid closing an already-open chat panel.
        """
        ctrl = self._ctrl
        if not ctrl:
            raise RuntimeError("WeChat not connected")

        # Check if the desired chat is already open
        current = self.get_current_chat_name()
        if current != contact:
            # Need to switch: find and click the session item
            session_item = _find_by(
                ctrl, auto_id=f"session_item_{contact}"
            )
            if not session_item:
                raise RuntimeError(f"找不到联系人 {contact} 的会话")

            # Click by coordinates (more reliable than .Click())
            rect = session_item.BoundingRectangle
            import ctypes as _ct
            cx = int((rect.left + rect.right) / 2)
            cy = int((rect.top + rect.bottom) / 2)
            _ct.windll.user32.SetCursorPos(cx, cy)
            time.sleep(0.05)
            _ct.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.03)
            _ct.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(2)

        return self.send_message(text)

    # ── Style capture ────────────────────────────────────────────────

    def capture_history(self, contact=None, count=100):
        """Get self text messages from current chat for style learning.

        If contact is given and differs from the currently open chat,
        switches to that contact first (only once). Otherwise reads
        the current chat directly without clicking anything.
        """
        ctrl = self._ctrl
        if not ctrl:
            raise RuntimeError("WeChat not connected")

        # Only switch if a specific contact is requested AND it's not
        # already the current chat
        if contact:
            current = self.get_current_chat_name()
            if current != contact:
                session_item = _find_by(
                    ctrl, auto_id=f"session_item_{contact}"
                )
                if session_item:
                    rect = session_item.BoundingRectangle
                    import ctypes as _ct
                    cx = int((rect.left + rect.right) / 2)
                    cy = int((rect.top + rect.bottom) / 2)
                    _ct.windll.user32.SetCursorPos(cx, cy)
                    time.sleep(0.05)
                    _ct.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                    time.sleep(0.03)
                    _ct.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                    time.sleep(2)

        # Read visible messages
        messages = self.get_messages()
        return [
            m["text"] for m in messages
            if m["is_self"] and "ChatTextItemView" in m["class_name"]
        ]

    def capture_current_history(self, max_scrolls=400,
                                 on_progress=None, check_stop=None,
                                 target_count=None, only_self=False):
        """Get text messages from the currently open chat.

        Uses a two-thread approach: a background collector thread
        continuously reads visible messages while the main thread
        rapidly presses Page Up. This catches messages that are only
        briefly visible during scroll transitions before the
        virtualized list unloads them.

        Args:
            max_scrolls: safety limit on Page Up attempts.
            on_progress: optional callback(count, pages) for UI.
            check_stop: optional callable returning True to abort early.
            target_count: stop early once this many messages are collected.
            only_self: if True, only collect your own green bubbles.

        Returns list of text strings (both sides, or only yours).
        """
        ctrl = self._ctrl
        if not ctrl:
            raise RuntimeError("WeChat not connected")
        hwnd = self._hwnd

        msg_list = self._find_msg_list()
        all_texts = []
        seen = set()
        collector_stop = threading.Event()
        new_since_check = [0]

        def _accept(m):
            if "ChatTextItemView" not in m["class_name"]:
                return False
            if only_self and not m.get("is_self", False):
                return False
            return True

        def _initial_collect():
            for m in self.get_messages():
                if not _accept(m):
                    continue
                t = m["text"]
                if t not in seen:
                    seen.add(t)
                    all_texts.append(t)

        def _collector():
            """Background thread: continuously read visible messages."""
            import pythoncom
            pythoncom.CoInitialize()
            try:
                while not collector_stop.is_set():
                    try:
                        for m in self.get_messages():
                            if not _accept(m):
                                continue
                            t = m["text"]
                            if t not in seen:
                                seen.add(t)
                                all_texts.append(t)
                                new_since_check[0] += 1
                    except Exception:
                        pass
                    time.sleep(0.02)
            finally:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        # Collect currently visible messages
        _initial_collect()
        if on_progress:
            on_progress(len(all_texts), 0)

        if not msg_list:
            return all_texts

        # Bring WeChat to front and click the message list for focus
        _bring_to_front(hwnd)
        time.sleep(0.3)
        rect = msg_list.BoundingRectangle
        cx = int((rect.left + rect.right) / 2)
        cy = int(rect.top + (rect.bottom - rect.top) * 0.2)
        ctypes.windll.user32.SetCursorPos(cx, cy)
        time.sleep(0.15)
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.03)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.3)

        # Start the background collector thread
        collector_thread = threading.Thread(target=_collector, daemon=True)
        collector_thread.start()

        # Main thread: rapidly press Page Up while collector reads.
        # Stop after 10 consecutive checks with zero new messages.
        empty_streak = 0
        pages_done = 0
        for i in range(max_scrolls):
            if check_stop and check_stop():
                break
            _press_key(_VK_PRIOR, delay=0.02)
            time.sleep(0.06)
            pages_done = i + 1

            # Check what the collector found since last check
            found = new_since_check[0]
            new_since_check[0] = 0
            if found > 0:
                empty_streak = 0
            else:
                empty_streak += 1

            if on_progress:
                on_progress(len(all_texts), pages_done)
            if target_count and len(all_texts) >= target_count:
                break
            if empty_streak >= 10:
                break

        # Stop collector and let it flush any remaining reads
        collector_stop.set()
        collector_thread.join(timeout=2)

        # Final collect to catch anything at the top
        for m in self.get_messages():
            if not _accept(m):
                continue
            t = m["text"]
            if t not in seen:
                seen.add(t)
                all_texts.append(t)

        if on_progress:
            on_progress(len(all_texts), pages_done)

        # Scroll back to bottom
        _press_key(_VK_END, delay=0.05)
        time.sleep(0.4)

        return all_texts

    # ── Listener compat (no-op for raw mode) ────────────────────────

    def start_listening(self, contacts, on_message_callback):
        """No-op: we use polling instead of listener callbacks."""
        pass

    def stop_listening(self):
        """No-op for raw mode."""
        pass

    def disconnect(self):
        """Release the connection."""
        with self._lock:
            self._ctrl = None
            self._hwnd = None
            self._clear_cached_controls()
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
