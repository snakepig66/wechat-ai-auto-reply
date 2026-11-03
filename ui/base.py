"""AppGUI base: main window, styles, shared controls and lifecycle."""

import logging
import queue
import threading
from tkinter import ttk, messagebox
import tkinter as tk

from .theme import *
from core.context_cache import ContextCache

logger = logging.getLogger(__name__)


class AppGUIBase:
    def __init__(self, config_manager, ai_engine, human_simulator, wechat_agent):
        self.config = config_manager
        self.ai_engine = ai_engine
        self.human_sim = human_simulator
        self.wx_agent = wechat_agent

        self._running = False
        self._log_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._auto_send_replies = bool(
            getattr(self.config.config, "auto_send_replies", False)
        )
        self._context_cache = {}
        self._context_cache_lock = threading.RLock()
        # Deep per-contact archive lives next to config.json and is separate
        # from the smaller AI context window.
        config_path = getattr(config_manager, "path", None)
        cache_path = (
            config_path.with_name("context_cache.json")
            if config_path else None
        )
        self._context_store = ContextCache(cache_path)
        self._floating_window = None
        self._floating_status_label = None
        self._floating_send_var = None

        self._build_ui()
        self._setup_logging()
        self._load_config_to_ui()
        self._poll_log_queue()
    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Global background
        style.configure(".", background=BG, font=(FONT_FAMILY, 10))
        style.configure("TFrame", background=BG)
        style.configure("Page.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("Soft.TFrame", background=SOFT)
        style.configure("TLabel", background=BG, foreground=TEXT_DARK,
                        font=(FONT_FAMILY, 10))
        style.configure("Card.TLabel", background=CARD_BG, foreground=TEXT_DARK,
                        font=(FONT_FAMILY, 10))
        style.configure("Section.TLabel", background=CARD_BG,
                        foreground=TEXT_DARK,
                        font=(FONT_FAMILY, 11, "bold"))
        style.configure("Hint.TLabel", background=CARD_BG, foreground=TEXT_GRAY,
                        font=(FONT_FAMILY, 9))
        style.configure("Muted.TLabel", background=CARD_BG, foreground=TEXT_LIGHT,
                        font=(FONT_FAMILY, 9))
        style.configure("Count.TLabel", background=PRIMARY_SOFT,
                        foreground=PRIMARY_DK, font=(FONT_FAMILY, 10, "bold"),
                        padding=(10, 4))

        # Buttons
        style.configure("Primary.TButton", background=PRIMARY,
                        foreground="white", font=(FONT_FAMILY, 10, "bold"),
                        padding=(18, 8), borderwidth=0, relief="flat")
        style.map("Primary.TButton",
                  background=[("active", PRIMARY_DK),
                              ("disabled", "#9fd9bd")])

        style.configure("Danger.TButton", background=DANGER,
                        foreground="white", font=(FONT_FAMILY, 10, "bold"),
                        padding=(18, 8), borderwidth=0, relief="flat")
        style.map("Danger.TButton",
                  background=[("active", DANGER_DK),
                              ("disabled", "#f3b0b0")])

        style.configure("Secondary.TButton", background=SOFT,
                        foreground=TEXT_DARK, font=(FONT_FAMILY, 10),
                        padding=(14, 7), borderwidth=1, relief="solid",
                        bordercolor=BORDER)
        style.map("Secondary.TButton",
                  background=[("active", "#eef1f5")],
                  bordercolor=[("active", BORDER)])

        style.configure("Ghost.TButton", background=CARD_BG,
                        foreground=TEXT_GRAY, font=(FONT_FAMILY, 9),
                        padding=(10, 5), borderwidth=0, relief="flat")
        style.map("Ghost.TButton",
                  background=[("active", SOFT)],
                  foreground=[("active", TEXT_DARK)])

        style.configure("TButton", background=CARD_BG, foreground=TEXT_DARK,
                        font=(FONT_FAMILY, 10), padding=(12, 6),
                        borderwidth=1, relief="solid", bordercolor=BORDER)
        style.map("TButton",
                  background=[("active", SOFT)])

        # Segmented capture target control
        style.configure("Segment.TButton", background=CARD_BG,
                        foreground=TEXT_GRAY, font=(FONT_FAMILY, 9, "bold"),
                        padding=(12, 5), borderwidth=0, relief="flat")
        style.map("Segment.TButton", background=[("active", SOFT)])
        style.configure("SegmentActive.TButton", background=PRIMARY_SOFT,
                        foreground=PRIMARY_DK, font=(FONT_FAMILY, 9, "bold"),
                        padding=(12, 5), borderwidth=0, relief="flat")

        # Entry
        style.configure("TEntry", fieldbackground=CARD_BG,
                        foreground=TEXT_DARK, borderwidth=1, relief="solid",
                        bordercolor=BORDER, padding=4)
        style.map("TEntry",
                  bordercolor=[("focus", PRIMARY)],
                  fieldbackground=[("disabled", SOFT)])

        style.configure("TCombobox", fieldbackground=CARD_BG,
                        background=CARD_BG, foreground=TEXT_DARK,
                        arrowcolor=TEXT_GRAY, borderwidth=1, relief="solid",
                        bordercolor=BORDER, padding=4)
        style.map("TCombobox",
                  bordercolor=[("focus", PRIMARY)],
                  fieldbackground=[("readonly", SOFT)])

        # Scale
        style.configure("TScale", background=CARD_BG, troughcolor="#dfe4ea",
                        sliderlength=18, sliderrelief="flat")
        style.map("TScale", background=[("active", PRIMARY)])

        # Checkbutton
        style.configure("TCheckbutton", background=CARD_BG,
                        foreground=TEXT_DARK, font=(FONT_FAMILY, 10))
        style.map("TCheckbutton", background=[("active", CARD_BG)])

        # Scrollbar
        style.configure("Vertical.TScrollbar", background="#d5dbe3",
                        troughcolor=BG, borderwidth=0, arrowcolor=TEXT_GRAY)

        # Separator
        style.configure("TSeparator", background=BORDER)
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("微信 AI 自动回复")
        self.root.geometry("980x720")
        self.root.minsize(760, 600)
        self.root.configure(bg=BG)

        self._setup_style()

        # ── Header ──
        header = tk.Frame(self.root, bg=SURFACE, height=64)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        tk.Frame(header, bg=BORDER, height=1).pack(fill="x", side="bottom")

        header_inner = tk.Frame(header, bg=SURFACE)
        header_inner.pack(fill="both", expand=True, padx=20, pady=10)

        brand_mark = tk.Frame(header_inner, bg=PRIMARY, width=34, height=34)
        brand_mark.pack(side="left")
        brand_mark.pack_propagate(False)
        tk.Label(
            brand_mark, text="微", bg=PRIMARY, fg="white",
            font=(FONT_FAMILY, 13, "bold")
        ).pack(fill="both", expand=True)

        brand = tk.Frame(header_inner, bg=SURFACE)
        brand.pack(side="left", padx=(10, 0))
        tk.Label(
            brand, text="微信 AI 自动回复", bg=SURFACE, fg=TEXT_DARK,
            font=(FONT_FAMILY, 15, "bold")
        ).pack(anchor="w")
        tk.Label(
            brand, text="自动回复 · 拟人模拟 · 风格学习", bg=SURFACE,
            fg=TEXT_LIGHT, font=(FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(1, 0))

        self.status_badge = tk.Frame(header_inner, bg=DANGER_SOFT)
        self.status_badge.pack(side="right")
        self.status_label = tk.Label(
            self.status_badge, text="● 已停止", bg=DANGER_SOFT, fg=DANGER,
            font=(FONT_FAMILY, 9, "bold"), padx=12, pady=5
        )
        self.status_label.pack()

        # ── Custom tab bar ──
        tab_bar = tk.Frame(self.root, bg=SURFACE, height=46)
        tab_bar.pack(fill="x", side="top")
        tab_bar.pack_propagate(False)
        tk.Frame(tab_bar, bg=BORDER, height=1).pack(fill="x", side="bottom")

        self._tab_widgets = {}
        tab_names = [
            ("控制台", "console"),
            ("发消息", "send"),
            ("设置", "settings"),
            ("风格学习", "style"),
        ]
        for label, key in tab_names:
            tab = tk.Frame(tab_bar, bg=SURFACE, cursor="hand2")
            tab.pack(side="left")
            lbl = tk.Label(
                tab, text=label, bg=SURFACE, fg=TEXT_GRAY,
                font=(FONT_FAMILY, 10, "bold"), padx=24, pady=13
            )
            lbl.pack(side="top")
            underline = tk.Frame(tab, bg=SURFACE, height=3)
            underline.pack(side="bottom", fill="x")
            lbl.bind("<Button-1>", lambda e, k=key: self._show_tab(k))
            tab.bind("<Button-1>", lambda e, k=key: self._show_tab(k))
            self._tab_widgets[key] = {
                "label": lbl, "underline": underline, "frame": tab
            }

        # ── Page stack ──
        page_area = tk.Frame(self.root, bg=BG)
        page_area.pack(fill="both", expand=True, padx=16, pady=16)
        self._page_area = page_area
        self._pages = {}
        self._build_console_tab()
        self._build_send_tab()
        self._build_settings_tab()
        self._build_style_tab()
        self._show_tab("console")

        self._build_floating_window()

        self.root.bind("<Control-l>", lambda e: self._clear_log())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    def _show_tab(self, key):
        """Switch the visible page and update tab highlight styles."""
        for page in self._pages.values():
            page.place_forget()
        self._pages[key].place(
            relx=0, rely=0, relwidth=1, relheight=1
        )
        for tab_key, widgets in self._tab_widgets.items():
            selected = tab_key == key
            widgets["label"].config(
                fg=PRIMARY if selected else TEXT_GRAY
            )
            widgets["underline"].config(
                bg=PRIMARY if selected else SURFACE
            )
    def _make_card(self, parent, title, accent=PRIMARY, expand=False):
        """Create a white card with a colored accent, return the frame."""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="both" if expand else "x", expand=expand,
                  pady=(0, 12))

        header = tk.Frame(card, bg=SURFACE)
        header.pack(fill="x", padx=16, pady=(14, 0))

        accent_bar = tk.Frame(header, bg=accent, width=4, height=16)
        accent_bar.pack(side="left", padx=(0, 10))

        ttk.Label(
            header, text=title, style="Section.TLabel"
        ).pack(side="left")

        return card
    def _add_slider(self, parent, label, config_key, min_val, max_val):
        f = ttk.Frame(parent, style="Card.TFrame")
        f.pack(fill="x", pady=4)

        ttk.Label(
            f, text=label, style="Card.TLabel", width=24, anchor="w"
        ).pack(side="left")

        value_var = tk.DoubleVar(value=getattr(self.config.config, config_key))
        setattr(self, f"_slider_{config_key}", value_var)

        val_label = ttk.Label(
            f, text=f"{value_var.get():.2f}", style="Card.TLabel",
            font=(FONT_FAMILY, 10, "bold"),
            width=6, anchor="e"
        )
        val_label.pack(side="right", padx=(8, 0))

        slider = ttk.Scale(
            f, from_=min_val, to=max_val, variable=value_var,
            command=lambda v, vl=val_label: vl.config(
                text=f"{float(v):.2f}"
            ),
            orient="horizontal"
        )
        slider.pack(side="left", fill="x", expand=True, padx=(10, 4))
    def _add_int_slider(self, parent, label, config_key, min_val, max_val):
        f = ttk.Frame(parent, style="Card.TFrame")
        f.pack(fill="x", pady=4)

        ttk.Label(
            f, text=label, style="Card.TLabel", width=24, anchor="w"
        ).pack(side="left")

        value_var = tk.IntVar(
            value=int(getattr(self.config.config, config_key))
        )
        setattr(self, f"_slider_{config_key}", value_var)

        val_label = ttk.Label(
            f, text=str(value_var.get()), style="Card.TLabel",
            font=(FONT_FAMILY, 10, "bold"), width=6, anchor="e"
        )
        val_label.pack(side="right", padx=(8, 0))

        slider = ttk.Scale(
            f, from_=min_val, to=max_val, variable=value_var,
            command=lambda v, vl=val_label: vl.config(
                text=str(int(float(v)))
            ),
            orient="horizontal"
        )
        slider.pack(side="left", fill="x", expand=True, padx=(10, 4))
    def _setup_logging(self):
        handler = LogQueueHandler(self._log_queue)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S")
        )
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
    def _log(self, msg):
        self._log_queue.put(f"{timestamp()} {_redact_log_text(msg)}")
    def _poll_log_queue(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                tag = _log_tag(msg)
                parts = msg.split(" ", 1)
                ts = parts[0]
                content = parts[1] if len(parts) > 1 else ""
                self.log_text.config(state="normal")
                self.log_text.insert("end", ts + " ", "timestamp")
                self.log_text.insert("end", content + "\n", tag)
                self.log_text.see("end")
                self.log_text.config(state="disabled")
        except queue.Empty:
            pass
        except Exception:
            # Never let log polling die — it would silence all future logs
            pass
        self.root.after(200, self._poll_log_queue)
    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
    def _save_context_cache(self):
        store = getattr(self, "_context_store", None)
        if store is not None:
            try:
                store.save()
            except Exception:
                pass
    def _on_close(self):
        # Closing the window should never discard edited settings or context.
        if hasattr(self, "_persist_api_ui_state"):
            self._persist_api_ui_state()
        if hasattr(self, "_save_group_settings"):
            self._save_group_settings()
        self._save_context_cache()
        if self._running:
            self._stop_worker()
            if self._worker_thread is not None:
                self._worker_thread.join(timeout=5)
        if self._floating_window and self._floating_window.winfo_exists():
            self._floating_window.destroy()
        self.root.destroy()
    def run(self):
        self.root.mainloop()
