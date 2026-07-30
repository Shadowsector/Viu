"""Графическое окно Вью — культурное Windows-приложение.

* Боковая панель с кнопками (Unity, Blender, сервис)
* Инструменты без чёрных терминалов — вывод в окно чата
* Автообновление при запуске (git pull)
* Копирование/вставка: Ctrl+C/V/X/A, правый клик, любая раскладка
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from .agent import Agent
from .config import Config
from .gui_actions import ACTION_GROUPS, GUI_ACTIONS, GuiAction, actions_by_group
from .pipeline import action_visible, get_pipeline_context
from .health import ollama_available
from .llm_roles import (
    REFLECT_MODEL_CHOICES,
    REFLECT_MODEL_IDS,
    effective_model,
    model_label,
    reflect_combo_labels,
    reflect_model_from_combo,
    set_reflect_model,
)
from .integrations.unity.watcher import AnimationFolderWatcher
from .runtime_settings import (
    get_update_interval_min,
    get_window_geometry,
    sanitize_window_geometry,
    set_window_geometry,
)
from .updater import (
    apply_update_smart,
    auto_update_on_start,
    check_for_update,
    cleanup_obsolete,
    cleanup_broken_git,
    find_git_root,
    install_package,
    package_root,
    running_sha,
    stamp_changed_since,
    usable_git_root,
    update_viu_full,
    version_label,
)

_ICON = Path(__file__).resolve().parent.parent / "assets" / "viu_icon.ico"
_NAV_KEYS = {"Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next", "Shift_L", "Shift_R"}
_GUI_DEFAULT_GEOMETRY = "1200x840"
_GUI_MIN_WIDTH = 920
_GUI_MIN_HEIGHT = 640


class ViuGUI:
    def __init__(self) -> None:
        self.agent = Agent(config=Config())
        self._queue: queue.Queue = queue.Queue()
        self._tool_busy = False  # Comfy/lab/скрипт — GPU/файлы, не LLM
        self._llm_busy = False  # агент думает — чат ждёт
        self._llm_comfy_yield = False
        self._action_buttons: list[tuple[str, ttk.Button]] = []
        self._action_group_boxes: dict[str, ttk.LabelFrame] = {}
        self._sidebar_stage_label: ttk.Label | None = None
        self._auto_update_job: str | None = None
        self._telegram = None
        self._telegram_waiting_reply = False
        self._last_via_telegram = False
        self._heartbeat_job: str | None = None
        self._away_ping_job: str | None = None
        self._heartbeat_notify = False
        self._lab_job: str | None = None
        self._chat_history: deque[str] = deque(maxlen=16)
        self._llm_turns: deque[dict[str, str]] = deque(maxlen=32)
        self._boot_sha = running_sha(package_root())
        self._geometry_save_job: str | None = None

        # story_memory: только ingest логов, без заливки в reflect-историю
        try:
            from .story_memory import ensure_logs_ingested

            n, msg = ensure_logs_ingested(self.agent.config)
            self._story_ingest_msg = msg if n else ""
        except OSError:
            self._story_ingest_msg = ""

        try:
            from .viu_memory import ensure_viu_memory, sanitize_poisoned_summaries

            ensure_viu_memory(self.agent.config)
            sanitize_poisoned_summaries(self.agent.config)
        except OSError:
            pass

        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_path = self.agent.config.data_dir / "logs" / f"chat_{stamp}.txt"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Тихо убираем старые батники из корня (наследие прошлых версий).
        try:
            removed = cleanup_obsolete()
        except Exception:  # noqa: BLE001
            removed = []

        self._build_ui()
        from .llm_roles import needs_viu_wrap_hint

        self._append("система", f"{version_label()}.")
        if os.environ.get("VIU_AUTO_UPDATE", "1") == "1":
            iv = get_update_interval_min(self.agent.config)
            if iv > 0:
                self._append(
                    "система",
                    f"Авто-проверка GitHub: каждые {iv} мин "
                    "(viu/package_sha.txt → скачает и перезапустит при новой версии).",
                    tag="sys",
                )
        self._append(
            "система",
            "Модель чата: вторая строка сверху (выпадающий список) или меню «Чат».",
            tag="sys",
        )
        if needs_viu_wrap_hint(self.agent.config):
            self._append(
                "система",
                "В .env у reflect нет viu-обёртки. Поставь "
                "VIU_MODEL_REFLECT=viu-cydonia и перезапусти "
                "(или create_viu_ollama_models.bat, если тега нет).",
                tag="sys",
            )
        try:
            from .prompts.reflect_mode import (
                reflect_dump_enabled,
                reflect_include_story_history,
                reflect_no_history,
                reflect_no_system,
                reflect_use_filters,
            )

            if any(
                (
                    reflect_no_history(),
                    reflect_use_filters(),
                    reflect_include_story_history(),
                    reflect_dump_enabled(),
                    not reflect_no_system(),
                )
            ):
                bits = []
                if reflect_no_history():
                    bits.append("без истории (отладка)")
                if not reflect_no_system():
                    bits.append("system от Viu")
                if reflect_use_filters():
                    bits.append("FILTERED=1 (старый retry)")
                if reflect_include_story_history():
                    bits.append("story_memory в чат")
                if reflect_dump_enabled():
                    bits.append("дамп reflect_last_request.json")
                self._append(
                    "система",
                    "Reflect отладка: " + ", ".join(bits),
                    tag="sys",
                )
        except Exception:  # noqa: BLE001
            pass
        if getattr(self, "_story_ingest_msg", ""):
            self._append("система", self._story_ingest_msg, tag="sys")
        if removed:
            self._append(
                "система",
                "Прибралась в папке — убрала лишние файлы: " + ", ".join(removed),
                tag="sys",
            )
        self._append("система", f"Лог: {self.log_path}", tag="sys")
        self._start_anim_watcher()
        self.root.after(100, self._poll_queue)
        self.root.after(300, self._check_updates_on_start)
        self.root.after(600, self._show_next_step_banner)
        self.root.after(2500, self._maybe_prompt_comfy_clip_pick)
        self.root.after(4000, self._maybe_prompt_comfy_wan_editor)
        self._refresh_status()
        self._schedule_auto_update()
        self._start_telegram()
        self._schedule_heartbeat()
        self._schedule_away_ping()
        self._schedule_cursor_inbox()
        self._schedule_lab()
        self._schedule_comfy_home_watch()
        try:
            from .integrations.comfy.focus import maybe_migrate_focus_from_env

            maybe_migrate_focus_from_env(self.agent.config)
        except Exception:  # noqa: BLE001
            pass
        try:
            from .reference_catalog.migrate import migrate_legacy_reference_files

            n, msg = migrate_legacy_reference_files(self.agent.config)
            if msg:
                self._append("система", msg, tag="sys")
        except Exception:  # noqa: BLE001
            pass
        try:
            from .anabarra_layout import migrate_inbox_to_anabarra, preserve_user_reflect_mode

            seed = preserve_user_reflect_mode(self.agent.config)
            if seed:
                self._append("система", seed, tag="sys")
            moved, mig = migrate_inbox_to_anabarra(self.agent.config)
            if moved and mig:
                self._append("система", mig, tag="sys")
        except Exception:  # noqa: BLE001
            pass
        try:
            from .vision import ensure_vision

            ensure_vision(self.agent.config)
        except OSError:
            pass
        self._ensure_anim_barn_reminder()
        if stamp_changed_since(self._boot_sha):
            self._append(
                "система",
                "На диске уже новая версия Viu — перезапуск через 3 с…",
                tag="sys",
            )
            self.root.after(3000, self._restart)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        self.root = tk.Tk()
        try:
            (Path(__file__).resolve().parent.parent / ".viu_gui_started").write_text(
                "ok\n", encoding="utf-8"
            )
            (Path(__file__).resolve().parent.parent / ".viu_launch_status").write_text(
                "tk_ready", encoding="utf-8"
            )
        except OSError:
            pass
        self.root.title("Вью — Анабарра")
        saved_geom = get_window_geometry(self.agent.config)
        geom = sanitize_window_geometry(
            saved_geom,
            default=_GUI_DEFAULT_GEOMETRY,
            min_w=_GUI_MIN_WIDTH,
            min_h=_GUI_MIN_HEIGHT,
        )
        if saved_geom and geom != saved_geom:
            set_window_geometry(self.agent.config, geom)
            try:
                self.root.after(
                    800,
                    lambda: self._append(
                        "система",
                        f"Окно было за экраном ({saved_geom}) — вернула на основной монитор.",
                        tag="sys",
                    ),
                )
            except Exception:  # noqa: BLE001
                pass
        self.root.geometry(geom)
        self.root.minsize(_GUI_MIN_WIDTH, _GUI_MIN_HEIGHT)
        # На всякий: поверх и не iconic
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(600, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        try:
            if _ICON.exists():
                self.root.iconbitmap(default=str(_ICON))
        except tk.TclError:
            pass

        self._build_menu()
        self._build_top_status()
        self.root.bind_all("<Control-KeyPress>", self._global_ctrl_key, add="+")

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)

        self._build_sidebar(body)
        self._build_chat(body)

        self.status = ttk.Label(
            self.root,
            anchor="w",
            relief="sunken",
            text=f"Провайдер: {self.agent.llm.name}",
        )
        self.status.pack(fill="x", side="bottom")

    def _on_root_configure(self, _event: tk.Event) -> None:
        if self._geometry_save_job:
            self.root.after_cancel(self._geometry_save_job)

        def _save() -> None:
            self._geometry_save_job = None
            try:
                if self.root.state() != "iconic":
                    set_window_geometry(self.agent.config, self.root.geometry())
            except tk.TclError:
                pass

        self._geometry_save_job = self.root.after(400, _save)

    def _on_close(self) -> None:
        try:
            set_window_geometry(self.agent.config, self.root.geometry())
        except tk.TclError:
            pass
        self.root.destroy()

    def _build_top_status(self) -> None:
        """Верх: статус + отдельная строка «Модель чата» + Дома."""
        outer = ttk.Frame(self.root)
        outer.pack(fill="x", padx=8, pady=(6, 0))

        status_row = ttk.Frame(outer)
        status_row.pack(fill="x")
        self.top_status_var = tk.StringVar(value="…")
        ttk.Label(status_row, textvariable=self.top_status_var, font=("Segoe UI", 9)).pack(
            side="left", anchor="w"
        )

        tools_row = ttk.Frame(outer)
        tools_row.pack(fill="x", pady=(5, 2))
        ttk.Label(
            tools_row,
            text="Модель чата:",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 6))
        self._reflect_model_var = tk.StringVar()
        self._reflect_combo = ttk.Combobox(
            tools_row,
            textvariable=self._reflect_model_var,
            values=list(REFLECT_MODEL_IDS),
            state="readonly",
            width=18,
            font=("Segoe UI", 10),
        )
        self._reflect_combo.pack(side="left")
        self._reflect_combo.bind("<<ComboboxSelected>>", self._on_reflect_model_pick)
        self._attach_tooltip(
            self._reflect_combo,
            "Reflect для чата и Telegram:\n"
            "viu-cydonia — чат\n"
            "viu-command-r — GDD/квесты\n"
            "viu-magnum — лит. NSFW\n"
            "viu-qwen32 — общая 32B",
        )
        self._sync_reflect_model_combo()

        self._presence_btn = tk.Button(
            tools_row,
            text="● Дома",
            font=("Segoe UI", 10, "bold"),
            relief="raised",
            bd=2,
            padx=12,
            pady=2,
            cursor="hand2",
            command=self._toggle_presence,
        )
        self._presence_btn.pack(side="right")
        ttk.Label(tools_row, text="Ты:", font=("Segoe UI", 9)).pack(side="right", padx=(0, 6))
        self._refresh_presence_button()

    def _reflect_combo_value_for(self, model_id: str) -> str:
        mid = (model_id or "").strip()
        if mid in REFLECT_MODEL_IDS:
            return mid
        for label in reflect_combo_labels():
            if label.startswith(mid + " ·"):
                return mid
        return mid

    def _sync_reflect_model_combo(self) -> None:
        mid = effective_model(self.agent.config, "reflect")
        self._reflect_model_var.set(self._reflect_combo_value_for(mid))
        if hasattr(self, "_chat_model_var"):
            self._chat_model_var.set(mid)

    def _pick_reflect_model(self, model_id: str) -> None:
        picked = (model_id or "").strip()
        if not picked:
            return
        set_reflect_model(self.agent.config, picked)
        self._sync_reflect_model_combo()
        self._append(
            "система",
            f"Модель чата: {picked} (reflect + Telegram, в .viu/runtime.json).",
            tag="sys",
        )
        self._refresh_presence_button()

    def _on_reflect_model_pick(self, _event=None) -> None:
        raw = self._reflect_model_var.get()
        picked = reflect_model_from_combo(raw) or raw.strip()
        self._pick_reflect_model(picked)

    def _toggle_presence(self) -> None:
        from .decision_queue import flush_prompt_for_home
        from .presence import presence_label, toggle_presence

        mode = toggle_presence(self.agent.config)
        label = presence_label(self.agent.config)
        self._append("ты", "[Режим присутствия]")
        self._append("Вью", label, tag="sys")
        self._refresh_presence_button()
        self._refresh_status()
        self._schedule_heartbeat()
        self._schedule_away_ping()
        if mode == "home":
            flush = flush_prompt_for_home(self.agent.config)
            if flush:
                self._append("Вью", flush, tag="tool")
                self._telegram_notify_chat(flush[:1500])
        else:
            from .runtime_settings import get_away_auto_comfy

            if get_away_auto_comfy(self.agent.config):
                away_note = (
                    "Автономный режим (нет дома): inbox, lab и Comfy сама; "
                    "вопросы копятся. Через ~2 мин напишу тебе сама (Telegram), "
                    "если Ollama жива."
                )
                self.root.after(2000, lambda: self._lab_tick(auto=True))
            else:
                away_note = (
                    "Автономный режим (нет дома): вопросы копятся, Comfy сама "
                    "не поднимаю (away_auto_comfy выкл). Через ~2 мин напишу "
                    "тебе сама (Telegram), если Ollama жива."
                )
                # Lab без Comfy (Cascadeur и т.п.) — по таймеру; Comfy в tick пропустится.
                self.root.after(2000, lambda: self._lab_tick(auto=True))
            self._append("система", away_note, tag="sys")
            # Первый away-ping не через 8 часов — через 2 минуты.
            self.root.after(120_000, self._run_away_ping)

    def _show_decision_queue(self) -> None:
        from .decision_queue import render_open

        self._append("ты", "[Очередь вопросов]")
        self._append("Вью", render_open(self.agent.config), tag="tool")

    def _refresh_presence_button(self) -> None:
        from .presence import is_away

        away = is_away(self.agent.config)
        btn = getattr(self, "_presence_btn", None)
        if btn is not None:
            if away:
                btn.config(
                    text="● Нет дома",
                    bg="#c62828",
                    fg="#ffffff",
                    activebackground="#b71c1c",
                    activeforeground="#ffffff",
                )
            else:
                btn.config(
                    text="● Дома",
                    bg="#2e7d32",
                    fg="#ffffff",
                    activebackground="#1b5e20",
                    activeforeground="#ffffff",
                )
        text = "Режим: меня нет (автономно)" if away else "Режим: я дома (с вопросами)"
        for aid, b in self._action_buttons:
            if aid == "presence_toggle":
                b.config(text=text)
                break

    def _refresh_status(self) -> None:
        cfg = self.agent.config

        def compute() -> str:
            from .decision_queue import count_open
            from .integrations.comfy.pipeline_status import comfy_pipeline_status_brief

            ollama = "Ollama ✓" if ollama_available(cfg.base_url) else "Ollama ✗"
            unity = Path(cfg.unity_project).name if cfg.unity_project else "Unity —"
            git = "git" if usable_git_root() else "zip"
            qn = count_open(cfg)
            q = f" | вопросов: {qn}" if qn else ""
            comfy = comfy_pipeline_status_brief(cfg)
            mid = f"  |  {comfy}" if comfy else ""
            return f"{ollama}{q}{mid}  |  {unity}  |  {version_label()} ({git})"

        self._run_bg(compute, self._set_top_status)
        try:
            self._refresh_presence_button()
        except Exception:  # noqa: BLE001
            pass
        interval = 2000 if self._tool_busy else 5000
        self.root.after(interval, self._refresh_status)

    def _set_top_status(self, result) -> None:
        if isinstance(result, Exception):
            return
        self.top_status_var.set(result)

    def _run_bg(self, func, on_done) -> None:
        def worker() -> None:
            try:
                result = func()
            except Exception as exc:  # noqa: BLE001
                result = exc
            self.root.after(0, lambda: on_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, width=260)
        frame.pack(side="left", fill="y", padx=(0, 0))
        frame.pack_propagate(False)

        header = ttk.Label(frame, text="Действия", font=("Segoe UI", 11, "bold"))
        header.pack(anchor="w", padx=10, pady=(10, 2))
        ttk.Label(
            frame,
            text=(
                "Сейчас: «Тело Шани» + блок «Девушки — риг и шоу». "
                "Наведи на кнопку — длинная подсказка. "
                "Comfy MoCap / Cascadeur lab на паузе."
            ),
            wraplength=240,
            justify="left",
            font=("Segoe UI", 8),
            foreground="#888888",
        ).pack(anchor="w", padx=10, pady=(0, 4))
        self._sidebar_stage_label = ttk.Label(
            frame,
            text="",
            wraplength=240,
            justify="left",
            font=("Segoe UI", 9),
            foreground="#666666",
        )
        self._sidebar_stage_label.pack(anchor="w", padx=10, pady=(0, 6))

        canvas = tk.Canvas(frame, highlightthickness=0, width=248)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)

        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        scroll.pack(side="right", fill="y", pady=(0, 8))

        grouped = actions_by_group()
        for group in ACTION_GROUPS:
            actions = grouped.get(group, [])
            if not actions:
                continue
            box = ttk.LabelFrame(inner, text=group, padding=6)
            box.pack(fill="x", padx=4, pady=4)
            self._action_group_boxes[group] = box
            for action in actions:
                btn = ttk.Button(
                    box,
                    text=action.label,
                    command=lambda a=action: self._on_action(a),
                )
                btn.pack(fill="x", pady=2)
                self._action_buttons.append((action.action_id, btn))
                if action.hint:
                    self._attach_tooltip(btn, action.hint)

        self._refresh_action_visibility()
        self._refresh_presence_button()

        chat_hint = ttk.Label(
            frame,
            text="Справа — живая Вью.\nМодель чата — вторая строка сверху или меню «Чат».",
            wraplength=240,
            justify="left",
            font=("Segoe UI", 9),
        )
        chat_hint.pack(anchor="w", padx=10, pady=(0, 8))

    def _build_chat(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.pack(side="left", fill="both", expand=True)

        chat_head = ttk.Frame(frame)
        chat_head.pack(fill="x", padx=(4, 8), pady=(8, 0))
        ttk.Label(
            chat_head,
            text="Живая Вью",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        self._chat_model_var = tk.StringVar(value=effective_model(self.agent.config, "reflect"))
        ttk.Label(
            chat_head,
            textvariable=self._chat_model_var,
            font=("Segoe UI", 9, "bold"),
            foreground="#81c784",
        ).pack(side="left", padx=(10, 0))
        ttk.Label(
            chat_head,
            text="свободный разговор · сюжет · идеи",
            font=("Segoe UI", 8),
            foreground="#888888",
        ).pack(side="left", padx=(8, 0))

        self.output = scrolledtext.ScrolledText(
            frame,
            wrap="word",
            font=("Segoe UI", 11),
            background="#1e1e1e",
            foreground="#e6e6e6",
            insertbackground="#e6e6e6",
            padx=8,
            pady=8,
            exportselection=True,
        )
        self.output.pack(fill="both", expand=True, padx=(4, 8), pady=(4, 4))
        for tag, color in (
            ("you", "#4fc3f7"),
            ("viu", "#a5d6a7"),
            ("step", "#9e9e9e"),
            ("err", "#ef9a9a"),
            ("sys", "#ffcc80"),
            ("tool", "#ce93d8"),
        ):
            self.output.tag_config(tag, foreground=color)
        self.output.bind("<Key>", self._readonly_guard)
        self._attach_context_menu(self.output)
        self._bind_clipboard(self.output)

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", padx=(4, 8), pady=(0, 8))
        self.entry = tk.Text(bottom, height=3, wrap="word", font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="both", expand=True)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Shift-Return>", lambda _e: None)
        self._attach_context_menu(self.entry)
        self._bind_clipboard(self.entry)
        self.entry.focus_set()

        self.send_btn = tk.Button(
            bottom,
            text="Отправить",
            width=12,
            font=("Segoe UI", 10, "bold"),
            bg="#1565c0",
            fg="#ffffff",
            activebackground="#0d47a1",
            activeforeground="#ffffff",
            relief="raised",
            bd=2,
            cursor="hand2",
            command=self._on_send,
        )
        self.send_btn.pack(side="right", fill="y", padx=(8, 0))

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Обновить Вью", command=self._update_viu_full)
        m_file.add_command(label="Создать ярлык на рабочий стол", command=self._make_shortcut)
        m_file.add_command(label="Перезапустить Вью", command=self._restart)
        m_file.add_separator()
        m_file.add_command(label="Открыть папку логов", command=self._open_log_dir)
        m_file.add_command(label="Очистить чат", command=self._clear_output)
        m_file.add_separator()
        m_file.add_command(label="Выход", command=self.root.destroy)
        menubar.add_cascade(label="Файл", menu=m_file)

        m_edit = tk.Menu(menubar, tearoff=0)
        m_edit.add_command(label="Копировать", command=lambda: self._edit_event("<<Copy>>"))
        m_edit.add_command(label="Вставить", command=lambda: self._edit_event("<<Paste>>"))
        m_edit.add_command(label="Вырезать", command=lambda: self._edit_event("<<Cut>>"))
        m_edit.add_command(label="Выделить всё", command=self._select_all_focused)
        menubar.add_cascade(label="Правка", menu=m_edit)

        m_places = tk.Menu(menubar, tearoff=0)
        m_places.add_command(label="Все места…", command=self._open_places_window)
        m_places.add_separator()
        try:
            from .places import places_by_group

            for group, items in places_by_group().items():
                sub = tk.Menu(m_places, tearoff=0)
                for place in items:
                    sub.add_command(
                        label=place.label,
                        command=lambda p=place: self._open_place(p),
                    )
                m_places.add_cascade(label=group, menu=sub)
        except Exception:  # noqa: BLE001
            pass
        m_places.add_separator()
        m_places.add_command(
            label="Показать пути в чате",
            command=self._show_places_in_chat,
        )
        menubar.add_cascade(label="Места", menu=m_places)

        m_chat = tk.Menu(menubar, tearoff=0)
        for mid, hint in REFLECT_MODEL_CHOICES:
            m_chat.add_command(
                label=f"{mid} — {hint}",
                command=lambda m=mid: self._pick_reflect_model(m),
            )
        menubar.add_cascade(label="Чат", menu=m_chat)

        self.root.config(menu=menubar)

    def _attach_tooltip(self, widget: tk.Widget, text: str) -> None:
        tip: dict[str, Optional[tk.Toplevel]] = {"win": None}

        def show(_event=None):
            if tip["win"] is not None:
                return
            tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{widget.winfo_rootx() + 20}+{widget.winfo_rooty() + 24}")
            lbl = ttk.Label(
                tw,
                text=text,
                padding=8,
                relief="solid",
                wraplength=320,
                justify="left",
            )
            lbl.pack()
            tip["win"] = tw

        def hide(_event=None):
            if tip["win"] is not None:
                tip["win"].destroy()
                tip["win"] = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _attach_context_menu(self, widget: tk.Widget) -> None:
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=lambda: self._select_all(widget))

        def show(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        widget.bind("<Button-3>", show)
        widget.bind("<Button-3>", show)

    def _bind_clipboard(self, widget: tk.Widget) -> None:
        def _clip(event, virt: str):
            try:
                event.widget.event_generate(virt)
            except tk.TclError:
                pass
            return "break"

        for seq, virt in (
            ("<Control-c>", "<<Copy>>"),
            ("<Control-C>", "<<Copy>>"),
            ("<Control-v>", "<<Paste>>"),
            ("<Control-V>", "<<Paste>>"),
            ("<Control-x>", "<<Cut>>"),
            ("<Control-X>", "<<Cut>>"),
            ("<Control-Insert>", "<<Copy>>"),
            ("<Shift-Insert>", "<<Paste>>"),
        ):
            widget.bind(seq, lambda e, v=virt: _clip(e, v), add="+")

    # ---------- события ----------

    def _global_ctrl_key(self, event: tk.Event) -> str | None:
        """Ctrl+C/V/X/A — в т.ч. русская раскладка (по keycode)."""
        if not (event.state & 0x0004):
            return None
        widget = event.widget
        if not isinstance(widget, (tk.Text, tk.Entry)):
            return None
        kc = int(getattr(event, "keycode", 0) or 0)
        keysym = (event.keysym or "").lower()
        # A / ф
        if kc == 65 or keysym in ("a", "ф"):
            self._select_all(widget)
            return "break"
        # C / с — копировать (из чата тоже)
        if kc == 67 or keysym in ("c", "с", "cyrillic_es"):
            try:
                widget.event_generate("<<Copy>>")
            except tk.TclError:
                pass
            return "break"
        # V / м — вставить (только поле ввода, не лог)
        if kc == 86 or keysym in ("v", "м", "cyrillic_em"):
            if widget is self.output:
                return "break"
            try:
                widget.event_generate("<<Paste>>")
            except tk.TclError:
                pass
            return "break"
        # X / ч — вырезать (не из лога)
        if kc == 88 or keysym in ("x", "ч", "cyrillic_che"):
            if widget is self.output:
                return "break"
            try:
                widget.event_generate("<<Cut>>")
            except tk.TclError:
                pass
            return "break"
        return None

    def _ctrl_shortcuts(self, event):
        if event.keysym.lower() in ("a", "ф") or event.keycode == 38:
            self._select_all(event.widget)
            return "break"
        return None

    def _select_all(self, widget) -> None:
        try:
            widget.tag_add("sel", "1.0", "end-1c")
        except tk.TclError:
            pass

    def _select_all_focused(self) -> None:
        widget = self.root.focus_get()
        if isinstance(widget, (tk.Text, tk.Entry)):
            self._select_all(widget)

    def _readonly_guard(self, event):
        # Ctrl/Shift — не блокировать (копирование, навигация)
        if event.state & 0x0004:
            return None
        if event.state & 0x0001:
            return None
        if event.keysym in _NAV_KEYS:
            return None
        return "break"

    def _edit_event(self, virtual: str) -> None:
        widget = self.root.focus_get()
        if isinstance(widget, (tk.Text, tk.Entry)):
            widget.event_generate(virtual)

    def _on_enter(self, event):
        self._on_send()
        return "break"

    def _maybe_handle_compose_chat(
        self, text: str, *, echo_user: bool = True, notify_telegram: bool = False
    ) -> bool:
        """Сочинение квестов/зёрен + improve — без LLM."""
        try:
            from .self_compose import try_handle_compose_chat

            out = try_handle_compose_chat(self.agent.config, text)
            if not out.handled:
                return False
            if echo_user:
                self._append("ты", text)
                self._record_llm_turn("user", text)
            self._append("Вью", out.message, tag="tool")
            self._record_llm_turn("assistant", out.message)
            try:
                from .story_memory import get_story_memory

                get_story_memory(self.agent.config).add_exchange(
                    text, out.message, source="chat", tags=["compose"]
                )
            except Exception:  # noqa: BLE001
                pass
            if notify_telegram and self._telegram is not None and out.message:
                self._telegram.notify_chat(out.message[:3500])
            return True
        except Exception:  # noqa: BLE001
            return False

    def _maybe_handle_comfy_chat(
        self, text: str, *, echo_user: bool = True, notify_telegram: bool = False
    ) -> bool:
        """NL Comfy: рефы / разбор / LoRA / видео — без имён тулов."""
        try:
            from .integrations.comfy.chat_flow import try_handle_comfy_chat

            out = try_handle_comfy_chat(self.agent.config, text)
            if not out.handled:
                return False
            if echo_user:
                display = text
                if text.startswith("[tg_photo:"):
                    display = "(фото из Telegram)" + (
                        "\n" + text.split("]", 1)[-1].strip()
                        if "]" in text
                        else ""
                    )
                self._append("ты", display)
                self._record_llm_turn("user", text)
            self._append("Вью", out.message, tag="tool")
            if notify_telegram and self._telegram is not None and out.message:
                self._telegram.notify_chat(out.message[:3500])
            for kind, path in out.media_to_send:
                if self._telegram is None:
                    break
                if kind == "video":
                    self._telegram.notify_video(path, caption="Клип от Вью")
                else:
                    self._telegram.notify_photo(path, caption="")
            if out.start_shoot and not self._tool_busy:
                action = str(getattr(out, "shoot_action", "") or "")
                profile = str(getattr(out, "render_profile", "") or "")
                style = str(getattr(out, "show_style", "") or "realism")
                auto_fire = bool(getattr(out, "auto_fire", False))
                wan_pos = str(getattr(out, "wan_positive", "") or "")
                wan_neg = str(getattr(out, "wan_negative", "") or "")
                lora_idx = list(getattr(out, "lora_indices", None) or [])
                shoot_mode = str(getattr(out, "shoot_mode", "") or "")
                seed_path = str(getattr(out, "seed_image_path", "") or "")
                # Directed invent: промпт+LoRA готовы — снимаем без панели.
                if auto_fire:
                    self.root.after(
                        0,
                        lambda a=action, p=profile, s=style, wp=wan_pos, wn=wan_neg, li=lora_idx, sm=shoot_mode, sp=seed_path: self._lab_comfy_action(
                            action=a or None,
                            render_profile=p,
                            show_style=s,
                            auto_fire=True,
                            wan_positive=wp,
                            wan_negative=wn,
                            lora_indices=li,
                            shoot_mode=sm,
                            seed_image_path=sp,
                        ),
                    )
                # Шоу — в панель съёмки, не в lab→План MoCap.
                elif profile in ("show", "шоу", "smoothmix", "beauty"):
                    from .integrations.comfy.prompts import clean_action_for_wan
                    from .integrations.comfy.show_profile import arm_show_profile
                    from .lab.comfy_pipeline import COMFY_TOPIC
                    from .lab.session import load_session, new_session, save_session

                    sess = load_session(self.agent.config, COMFY_TOPIC) or new_session(
                        COMFY_TOPIC
                    )
                    act = clean_action_for_wan(action) or (
                        "standing relaxed in soft light, cinematic atmosphere"
                    )
                    arm_show_profile(sess.meta, style=style or "realism", action=act)
                    sess.meta["catalog_slug"] = "show"
                    sess.meta.pop("wan_positive", None)
                    sess.meta.pop("wan_negative", None)
                    save_session(self.agent.config, sess)
                    self.root.after(
                        0,
                        lambda s=style: self._open_comfy_studio(
                            initial_profile="show", initial_style=s or "realism"
                        ),
                    )
                else:
                    self.root.after(
                        0,
                        lambda a=action, p=profile, s=style: self._lab_comfy_action(
                            action=a or None,
                            render_profile=p,
                            show_style=s,
                        ),
                    )
            return True
        except Exception:  # noqa: BLE001
            return False

    def _maybe_handle_comfy_reply(
        self, text: str, *, echo_user: bool = True, notify_telegram: bool = False
    ) -> bool:
        """Comfy lab ждёт промпт/LoRA/клип — ответ в чате Вью, не в LLM."""
        try:
            from .integrations.comfy.approval import try_handle_comfy_telegram
            from .lab.comfy_pipeline import COMFY_TOPIC
            from .lab.session import load_session

            handled, msg = try_handle_comfy_telegram(
                self.agent.config, text, for_telegram=notify_telegram
            )
            if not handled:
                return False
            if echo_user:
                self._append("ты", text)
                self._record_llm_turn("user", text)
            self._append("Вью", msg, tag="tool")
            if notify_telegram and self._telegram is not None:
                limit = 3800 if "--- POSITIVE" in msg else 1200
                self._telegram.notify_chat(msg[:limit])
            # После keep — прислать mp4 в Telegram, если есть.
            session = load_session(self.agent.config, COMFY_TOPIC)
            if session and notify_telegram and self._telegram is not None:
                kept = str(session.meta.get("clip_kept_path") or "").strip()
                if kept and Path(kept).is_file():
                    self._telegram.notify_video(kept, caption="Оставила этот клип")
            if (
                session
                and session.status == "running"
                and (
                    session.meta.get("approved")
                    or session.meta.get("lora_pick_done")
                    or session.meta.get("clip_kept_id")
                    or session.meta.get("clip_rejected_all")
                )
                and not self._tool_busy
            ):
                self._run_tool(
                    "lab_step",
                    {"topic": COMFY_TOPIC, "run_all": "1"},
                    label="Comfy: продолжаю lab",
                )
            return True
        except Exception:  # noqa: BLE001
            return False

    def _on_send(self) -> None:
        from .gui_busy import can_accept_chat

        # Comfy/lab может крутиться — чат отвечает, пока LLM свободна.
        if not can_accept_chat(llm_busy=self._llm_busy):
            return
        text = self.entry.get("1.0", "end-1c").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        if text.lower() in ("exit", "quit", "выход", "пока"):
            self.root.destroy()
            return
        if self._try_direct_tool_command(text):
            return
        if self._maybe_handle_comfy_reply(text):
            return
        if self._maybe_handle_comfy_chat(text):
            return
        if self._maybe_handle_compose_chat(text):
            return
        from .integrations.telegram.router import route_user_message
        from .modes import mode_log_label

        mode = route_user_message(text, waiting_for_user=self._telegram_waiting_reply)
        # Reflect — обычный чат, без плашки. Work — явно «сейчас делаю», без слов reflect/work.
        if mode == "work":
            self._append("система", f"· {mode_log_label(mode)}", tag="sys")
            self._run_agent_task(text)
        else:
            self._run_agent_reflect(text)

    def _on_action(self, action: GuiAction) -> None:
        from .gui_busy import can_accept_scripts

        if not can_accept_scripts(tool_busy=self._tool_busy, llm_busy=self._llm_busy):
            return
        from .lab.controller import action_interrupts_lab, lab_controller

        if action_interrupts_lab(action.tool):
            lab_controller.request_operator_priority(f"кнопка: {action.label}")
        elif action.tool in {
            "__lab_start__",
            "__lab_run_all__",
            "__lab_rate__",
            "__lab_comfy__",
            "__interaction_lab__",
            "__comfy_clips__",
            "__comfy_studio__",
        } or (
            action.tool and action.tool.startswith("lab_")
        ):
            lab_controller.clear_operator_priority()
        if action.tool == "__clear__":
            self._clear_output()
            return
        if action.tool == "__open_logs__":
            self._open_log_dir()
            return
        if action.tool == "__update_viu__":
            self._update_viu_full()
            return
        if action.tool == "__collect_logs__":
            self._collect_logs()
            return
        if action.tool == "__add_animation__":
            self._add_animation()
            return
        if action.tool == "__accept_animation__":
            self._accept_animation()
            return
        if action.tool == "__animation_review__":
            self._open_animation_review()
            return
        if action.tool == "__prop_catalog__":
            self._open_prop_catalog()
            return
        if action.tool == "__creature_catalog__":
            self._open_creature_catalog()
            return
        if action.tool == "__biped_canon_hub__":
            self._open_biped_canon_hub()
            return
        if action.tool == "__open_biped_queue__":
            self._open_biped_queue_folder()
            return
        if action.tool == "__characters_vision__":
            self._open_characters_vision()
            return
        if action.tool == "__places__":
            self._open_places_window()
            return
        if action.tool == "__next_step__":
            self._run_next_step()
            return
        if action.tool == "__lab_start__":
            self._lab_start_action()
            return
        if action.tool == "__lab_comfy__":
            self._lab_comfy_action()
            return
        if action.tool == "__interaction_lab__":
            self._interaction_lab_action()
            return
        if action.tool == "__lab_run_all__":
            self._lab_run_all_action()
            return
        if action.tool == "__lab_rate__":
            self._open_lab_rating()
            return
        if action.tool == "__comfy_clips__":
            self._open_comfy_clip_review()
            return
        if action.tool == "__comfy_shot_queue__":
            self._open_comfy_shot_queue()
            return
        if action.tool == "__comfy_seed_library__":
            self._open_comfy_seed_library()
            return
        if action.tool == "__comfy_studio__":
            self._open_comfy_studio()
            return
        # Шоу / съёмка: ВСЕГДА панель «Съёмка», даже если tool ещё comfy_show (старый ярлык).
        if action.tool in ("__comfy_shoot__", "comfy_show"):
            args = action.tool_args or {}
            profile = str(args.get("profile") or "show")
            style = str(args.get("style") or "realism")
            if action.tool == "comfy_show" and not args.get("profile"):
                profile = "show"
            self._append(
                "Вью",
                f"Открываю панель «СЪЁМКА ВИДЕО» ({profile}/{style}) — "
                "это не «План MoCap».",
                tag="viu",
            )
            self._open_comfy_studio(initial_profile=profile, initial_style=style)
            return
        if action.tool == "__comfy_prompt__":
            self._open_comfy_shot_queue(focus_lab=True)
            return
        if action.tool == "__reference_catalog__":
            self._open_reference_catalog()
            return
        if action.tool == "__comfy_open__":
            self._open_comfy_ui()
            return
        if action.tool == "__rescan_catalog__":
            self._open_prop_catalog()
            return
        if action.tool == "__telegram_test__":
            self._telegram_test()
            return
        if action.tool == "__presence_toggle__":
            self._toggle_presence()
            return
        if action.tool == "__decision_queue__":
            self._show_decision_queue()
            return
        if action.is_chain:
            self._run_tool_chain(action)
            return
        if action.tool:
            self._run_tool(action.tool, action.tool_args, label=action.label)
            return
        if action.prompt:
            self._run_agent_task(action.prompt)

    def _set_tool_busy(self, busy: bool) -> None:
        self._tool_busy = busy
        self._refresh_busy_ui()

    def _set_llm_busy(self, busy: bool) -> None:
        was_busy = self._llm_busy
        self._llm_busy = busy
        if busy and not was_busy:
            self._maybe_yield_comfy_for_llm()
        elif was_busy and not busy:
            self._release_comfy_yield()
        self._refresh_busy_ui()

    def _maybe_yield_comfy_for_llm(self) -> None:
        from .integrations.comfy.gpu_yield import (
            comfy_yield_on_chat_enabled,
            yield_comfy_for_llm,
        )
        from .lab.controller import lab_controller

        if not comfy_yield_on_chat_enabled():
            return
        lab_controller.request_operator_priority("reflect чат")
        self._llm_comfy_yield = True
        note = yield_comfy_for_llm(self.agent.config)
        if note:
            self.agent._log(note)

    def _release_comfy_yield(self) -> None:
        if not self._llm_comfy_yield:
            return
        self._llm_comfy_yield = False
        from .lab.controller import lab_controller

        lab_controller.clear_operator_priority()
        self.agent._log("comfy_yield: released (lab продолжит по таймеру, если «меня нет»)")

    def _set_busy(self, busy: bool) -> None:
        """Совместимость: полная блокировка (и tool, и LLM)."""
        self._tool_busy = busy
        self._llm_busy = busy
        self._refresh_busy_ui()

    def _refresh_busy_ui(self) -> None:
        from .gui_busy import busy_status_ru, can_accept_chat, can_accept_scripts

        chat_ok = can_accept_chat(llm_busy=self._llm_busy)
        scripts_ok = can_accept_scripts(
            tool_busy=self._tool_busy, llm_busy=self._llm_busy
        )
        send = getattr(self, "send_btn", None)
        if send is not None:
            send.config(
                state=("normal" if chat_ok else "disabled"),
                text=("Отправить" if chat_ok else "Думаю…"),
            )
            try:
                send.config(bg="#1565c0" if chat_ok else "#546e7a")
            except tk.TclError:
                pass
        side_state = "normal" if scripts_ok else "disabled"
        for _aid, btn in self._action_buttons:
            btn.config(state=side_state)
        status = getattr(self, "status", None)
        if status is not None:
            ver = version_label()
            if self._llm_busy:
                status.config(text="Вью думает…")
            elif self._tool_busy:
                try:
                    from .integrations.comfy.pipeline_status import comfy_pipeline_status_brief

                    brief = comfy_pipeline_status_brief(self.agent.config)
                except Exception:
                    brief = ""
                if brief:
                    status.config(text=f"{ver} | {brief} · чат свободен")
                else:
                    status.config(text=f"{ver} | lab/Comfy… (чат свободен)")
            else:
                status.config(text=f"{ver} | {self.agent.llm.name}")
        self._busy_label = busy_status_ru(
            tool_busy=self._tool_busy, llm_busy=self._llm_busy
        )

    def _run_tool_chain(self, action: GuiAction) -> None:
        from .gui_busy import can_start_tool

        if not can_start_tool(tool_busy=self._tool_busy, tool_name=action.tool or ""):
            self._append(
                "система",
                f"Уже крутится lab/Comfy — «{action.label}» подождёт. "
                "Статус: comfy_status или lab_status topic=comfy.",
                tag="sys",
            )
            return
        self._append("ты", f"[{action.label}]")
        self._set_tool_busy(True)
        threading.Thread(target=self._chain_worker, args=(action,), daemon=True).start()

    def _chain_worker(self, action: GuiAction) -> None:
        parts: list[str] = []
        all_ok = True
        try:
            for name, args in action.tool_chain:
                tool = self.agent.registry.get(name)
                if tool is None:
                    parts.append(f"⚠ {name}: не найден")
                    all_ok = False
                    continue
                result = tool.run(args, self.agent.ctx)
                mark = "✓" if result.ok else "✗"
                parts.append(f"{mark} {name}\n{result.content}")
                if not result.ok:
                    all_ok = False
            prefix = "OK" if all_ok else "ЧАСТИЧНО"
            self._queue.put(("tool", f"[{action.label}] {prefix}\n\n" + "\n\n".join(parts)))
        except Exception as exc:  # noqa: BLE001
            self._queue.put(("tool", f"[{action.label}] ОШИБКА\n{exc}"))

    def _add_animation(self) -> None:
        from tkinter import filedialog

        cfg = self.agent.config
        if not cfg.unity_project:
            self._append("ошибка", "Не задан путь к Unity-проекту (VIU_UNITY_PROJECT).", tag="err")
            return
        path = filedialog.askopenfilename(
            title="Выбери FBX с анимацией",
            filetypes=[("Анимация Unity (FBX)", "*.fbx"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        self._append("ты", f"[Импорт FBX] {Path(path).name}")
        self._set_tool_busy(True)

        def work():
            from .integrations.unity.animation_scan import ANIMATIONS_REL
            from .integrations.unity.paths import resolve_in_unity_project

            root = Path(cfg.unity_project).expanduser()
            dest_dir = resolve_in_unity_project(root, ANIMATIONS_REL)
            dest_dir.mkdir(parents=True, exist_ok=True)
            src = Path(path)
            dest = dest_dir / src.name
            import shutil as _sh

            _sh.copy2(src, dest)

            lines = [f"Скопировал: {src.name} → {dest_dir}"]
            for name in ("unity_deploy_setup", "unity_sync_animations", "unity_run_setup"):
                tool = self.agent.registry.get(name)
                if tool is None:
                    lines.append(f"⚠ {name}: не найден")
                    continue
                try:
                    res = tool.run({}, self.agent.ctx)
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"✗ {name}: {exc}")
                    break
                mark = "✓" if res.ok else "✗"
                lines.append(f"{mark} {name}")
                if not res.ok:
                    lines.append(res.content)
                    break
            else:
                lines.append(
                    "Готово: Walk в Animator, сцена GameTest с Шаней собрана.\n"
                    "«Открыть Unity» → GameTest.unity → ▶ Play → кликни окно Game → A/D."
                )
            return "\n".join(lines)

        def done(result):
            self._set_tool_busy(False)
            if isinstance(result, Exception):
                self._append("ошибка", str(result), tag="err")
                return
            self._append("Вью", result, tag="tool")

        self._run_bg(work, done)

    def _refresh_action_visibility(self) -> None:
        ctx = get_pipeline_context(self.agent.config)
        label = ctx.step_label
        try:
            from .integrations.comfy.pipeline_status import comfy_pipeline_status_brief
            from .lab.comfy_pipeline import COMFY_TOPIC
            from .lab.session import load_session

            if load_session(self.agent.config, COMFY_TOPIC) is not None:
                brief = comfy_pipeline_status_brief(self.agent.config)
                if brief:
                    label = brief
        except Exception:
            pass
        if self._sidebar_stage_label is not None:
            self._sidebar_stage_label.config(text=label)
        visible_by_group: dict[str, int] = {g: 0 for g in ACTION_GROUPS}
        action_map = {a.action_id: a for a in GUI_ACTIONS}
        for aid, btn in self._action_buttons:
            action = action_map.get(aid)
            if action is None:
                continue
            if action_visible(aid, ctx):
                btn.pack(fill="x", pady=2)
                visible_by_group[action.group] = visible_by_group.get(action.group, 0) + 1
            else:
                btn.pack_forget()
        for group, box in self._action_group_boxes.items():
            if visible_by_group.get(group, 0) > 0:
                box.pack(fill="x", padx=4, pady=4)
            else:
                box.pack_forget()

    def _show_next_step_banner(self) -> None:
        from .director import format_banner, plan_next_step

        def work():
            return format_banner(plan_next_step(self.agent.config))

        def done(result) -> None:
            if isinstance(result, Exception):
                return
            self._append("система", result, tag="sys")
            self.root.after(0, self._refresh_action_visibility)

        self._run_bg(work, done)

    def _run_next_step(self) -> None:
        from .director import format_banner, plan_next_step

        plan = plan_next_step(self.agent.config)
        self._append("система", format_banner(plan), tag="sys")
        if plan.idle or not plan.tool:
            self._refresh_action_visibility()
            return

        tool, args = plan.tool, plan.tool_args
        if tool == "__rescan_catalog__":
            self._open_prop_catalog()
            return
        if tool == "__prop_catalog__":
            self._open_prop_catalog()
            return
        if tool == "__collect_logs__":
            self._collect_logs()
            return
        if tool == "__clear__":
            self._clear_output()
            return
        if tool == "__open_logs__":
            self._open_log_dir()
            return
        if tool == "__update_viu__":
            self._update_viu_full()
            return
        if tool == "__add_animation__":
            self._add_animation()
            return
        self._run_tool(tool, args, label="Что делать дальше")
        self.root.after(500, self._refresh_action_visibility)

    def _open_prop_catalog(self) -> None:
        from .prop_catalog import PropCatalogStore, catalog_path, open_prop_catalog_review

        cfg = self.agent.config
        store = PropCatalogStore(catalog_path(cfg))
        self._append("система", "Открываю каталог предметов…", tag="sys")

        def open_win() -> None:
            from .prop_catalog.scanner import rescan_file_level_blends

            try:
                n, _ = rescan_file_level_blends(
                    store, blender_exe=cfg.blender_exe, config=cfg
                )
                if n:
                    self._append("система", f"Каталог: разложено {n} объектов из .blend", tag="sys")
            except RuntimeError as exc:
                self._append("система", f"Каталог: {exc}", tag="sys")

            def on_catalog_finished() -> None:
                self._append(
                    "система",
                    "Каталог закрыт. Разметка в .viu/prop_catalog.json",
                    tag="sys",
                )
                self._refresh_action_visibility()
                self._show_next_step_banner()

            open_prop_catalog_review(
                self.root,
                store,
                max_lift_kg=cfg.shanya_max_lift_kg,
                blender_exe=cfg.blender_exe,
                config=cfg,
                on_finished=on_catalog_finished,
            )

        self.root.after(0, open_win)

    def _open_reference_catalog(self) -> None:
        from .reference_catalog import open_reference_review
        from .reference_catalog.scanner import scan_references_inbox

        cfg = self.agent.config
        added, total = scan_references_inbox(cfg)
        self._append(
            "система",
            f"Референсы: inbox +{added}, в каталоге {total}. Открываю окно…",
            tag="sys",
        )
        self.root.after(0, lambda: open_reference_review(self.root, cfg))

    def _open_biped_queue_folder(self) -> None:
        """Проводник на Lab/Creatures/BipedCanonQueue."""
        from .creature_catalog.biped_canon import biped_canon_queue_dir
        from .places import _open_path

        folder = biped_canon_queue_dir(self.agent.config)
        ok, msg = _open_path(folder)
        if ok:
            self._append(
                "система",
                f"Папка AccuRIG-очереди:\n{folder}\n"
                "Сохраняй экспорт как slug_canon.fbx сюда, потом «Забрать канон».",
                tag="sys",
            )
        else:
            self._append("система", f"Не открыла папку: {msg}", tag="sys")

    def _open_biped_canon_hub(self) -> None:
        """Окно для ламера: шаги перерига / NSFW / шоу."""
        win = tk.Toplevel(self.root)
        win.title("Девушки — риг, органы, шоу")
        win.geometry("520x640")
        win.transient(self.root)

        head = ttk.Label(
            win,
            text="Простыми словами",
            font=("Segoe UI", 12, "bold"),
        )
        head.pack(anchor="w", padx=12, pady=(12, 4))

        intro = (
            "Цель: у всех девок один скелет (как у Unity), общие анимации, "
            "органы спрятаны (scale≈0), 6 мишеней для NSFW, "
            "и отдельно — красивый шоу-клип SmoothMix (не MoCap).\n\n"
            "Порядок: 1 список → 2 органы в каталог → 3 папка → "
            "4 AccuRIG руками → 5 забрать канон → в Studio кнопка "
            "«Всё NSFW сразу» (мишени+penis) → поправить глазами → FBX. "
            "Шоу — когда захочешь красивый дубль."
        )
        ttk.Label(win, text=intro, wraplength=480, justify="left").pack(
            anchor="w", padx=12, pady=(0, 8)
        )

        canvas = tk.Canvas(win, highlightthickness=0)
        scroll = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 12))
        scroll.pack(side="right", fill="y", pady=(0, 12), padx=(0, 8))

        from .gui_actions import GUI_ACTIONS

        hub_ids = (
            "biped_list_girls",
            "biped_mark_genital",
            "biped_queue_girls",
            "biped_open_queue",
            "biped_ingest",
            "biped_sockets",
            "biped_guide",
            "show_double",
            "show_double_anime",
            "comfy_shoot_panel",
        )
        by_id = {a.action_id: a for a in GUI_ACTIONS}
        for aid in hub_ids:
            action = by_id.get(aid)
            if action is None:
                continue
            row = ttk.Frame(inner)
            row.pack(fill="x", pady=6, padx=4)
            btn = ttk.Button(
                row,
                text=action.label,
                command=lambda a=action, w=win: (
                    w.destroy(),
                    self._on_action(a),
                ),
            )
            btn.pack(fill="x")
            if action.hint:
                ttk.Label(
                    row,
                    text=action.hint,
                    wraplength=460,
                    justify="left",
                    font=("Segoe UI", 8),
                    foreground="#666666",
                ).pack(anchor="w", pady=(2, 0))

        ttk.Button(win, text="Закрыть", command=win.destroy).pack(
            side="bottom", pady=8
        )

    def _open_creature_catalog(self) -> None:
        """Скан Inbox → авто по именам → окно кнопок размеров."""
        from .creature_catalog import (
            CreatureCatalogStore,
            auto_apply_size_guesses,
            creature_catalog_path,
            ensure_girl_sockets_doc,
            open_creature_catalog_review,
            scan_creatures_inbox,
        )

        cfg = self.agent.config
        self._append("система", "Сканирую существ и открываю разметку…", tag="sys")

        def open_win() -> None:
            try:
                added, total, scan_msg = scan_creatures_inbox(cfg)
                ensure_girl_sockets_doc(cfg)
                store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
                auto_n, auto_lines = auto_apply_size_guesses(store)
                parts = [scan_msg.split("\n")[0]]
                if auto_n:
                    parts.append(f"Авто по имени: +{auto_n}")
                    parts.extend(auto_lines[:8])
                pending = len(store.pending())
                parts.append(f"В очереди на кнопки: {pending} (всего в каталоге {total}).")
                self._append("система", "\n".join(parts), tag="sys")

                def on_finished() -> None:
                    store2 = CreatureCatalogStore(creature_catalog_path(cfg)).load()
                    self._append(
                        "система",
                        "Разметка существ закрыта.\n" + store2.summary_text(),
                        tag="sys",
                    )
                    self._refresh_action_visibility()

                if pending == 0 and added == 0 and total == 0:
                    self._append(
                        "система",
                        "Inbox пуст. Положи модели в "
                        "Lab\\Creatures\\Inbox и снова «Разметить существ».",
                        tag="sys",
                    )
                    return

                open_creature_catalog_review(
                    self.root,
                    store,
                    config=cfg,
                    on_finished=on_finished,
                )
            except Exception as exc:
                self._append("система", f"Существа: {exc}", tag="err")

        self.root.after(0, open_win)

    def _open_characters_vision(self) -> None:
        from .characters_vision import open_characters_vision

        ok, msg = open_characters_vision(self.agent.config)
        self._append("ты", "[Персонажи]")
        self._append("система", msg, tag="sys" if ok else "err")

    def _open_place(self, place) -> None:
        from .places import open_place

        ok, msg = open_place(self.agent.config, place)
        self._append("система", msg, tag="sys" if ok else "err")

    def _show_places_in_chat(self) -> None:
        from .places import describe_places

        self._append("ты", "[Места]")
        self._append("система", describe_places(self.agent.config), tag="sys")

    def _open_places_window(self) -> None:
        from .places import places_by_group

        win = tk.Toplevel(self.root)
        win.title("Места — входы и выходы Вью")
        win.geometry("520x560")
        win.transient(self.root)

        outer = ttk.Frame(win, padding=8)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Куда класть модели / откуда забирать клипы и правки.",
            wraplength=480,
            font=("Segoe UI", 9),
            foreground="#666666",
        ).pack(anchor="w", pady=(0, 6))

        canvas = tk.Canvas(outer, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for group, items in places_by_group().items():
            box = ttk.LabelFrame(inner, text=group, padding=6)
            box.pack(fill="x", padx=4, pady=4)
            for place in items:
                row = ttk.Frame(box)
                row.pack(fill="x", pady=2)
                btn = ttk.Button(
                    row,
                    text=place.label,
                    width=36,
                    command=lambda p=place: self._open_place(p),
                )
                btn.pack(side="left")
                if place.hint:
                    self._attach_tooltip(btn, place.hint)

        foot = ttk.Frame(outer)
        foot.pack(fill="x", pady=(8, 0))
        ttk.Button(
            foot,
            text="Пути в чат",
            command=self._show_places_in_chat,
        ).pack(side="left")
        ttk.Button(foot, text="Закрыть", command=win.destroy).pack(side="right")

        self._append("ты", "[Места]")
        self._append("система", "Окно мест: папки и файлы взаимодействия.", tag="sys")

    def _open_animation_review(self) -> None:
        from .animation_catalog import AnimationCatalogStore, animation_catalog_path
        from .animation_catalog.review_gui import open_animation_review

        store = AnimationCatalogStore(animation_catalog_path(self.agent.config)).load()
        if not store.pending_reviews():
            self._append(
                "система",
                "Нет анимаций в очереди.\n"
                "Положи один FBX в Inbox → «Принять анимацию».",
                tag="sys",
            )
            return
        self._append("система", "Окно описания анимации…", tag="sys")

        def on_finished() -> None:
            self._append("система", "Каталог анимаций сохранён.", tag="sys")
            self._refresh_action_visibility()
            self._show_next_step_banner()

        self.root.after(
            0,
            lambda: open_animation_review(
                self.root,
                store,
                on_finished=on_finished,
            ),
        )

    def _accept_animation(self) -> None:
        self._append("ты", "[Принять анимацию (Inbox)]")
        self._set_tool_busy(True)

        def work():
            from .drop_router import accept_single_animation

            return accept_single_animation(self.agent.config)

        def done(result) -> None:
            self._set_tool_busy(False)
            if isinstance(result, Exception):
                self._append("ошибка", str(result), tag="err")
                return
            prefix = "OK" if result.ok else "ОШИБКА"
            self._append("Вью", f"[Принять анимацию] {prefix}\n{result.format()}", tag="tool")
            self._refresh_action_visibility()
            if result.ok and result.open_animation_review:
                self.root.after(300, self._open_animation_review)

        self._run_bg(work, done)

    def _collect_logs(self) -> None:
        self._append("ты", "[Отправить логи разработчику]")
        self._set_tool_busy(True)

        def work():
            from .integrations.github.handoff import append_handoff, push_handoff
            from .support import collect_support_bundle, upload_bundle_to_gist

            bundle = collect_support_bundle(self.agent.config)
            ok, msg = upload_bundle_to_gist(bundle, description="Viu logs — Анабарра")
            handoff_note = ""
            try:
                body = (
                    f"Ден нажал «Собрать логи».\n\n"
                    f"Bundle: `{bundle}`\n"
                    f"Gist: {msg}\n\n"
                    "Проверь launch/relaunch, Comfy (:8188), reflect/дубли, память."
                )
                append_handoff("Viu support logs", body[:8000], author="Viu")
                h_ok, h_msg = push_handoff(message="Viu: support logs for Cursor")
                handoff_note = f"\nHandoff Cursor: {'OK — ' + h_msg if h_ok else 'FAIL — ' + h_msg}"
            except Exception as exc:  # noqa: BLE001
                handoff_note = f"\nHandoff: {exc}"
            return bundle, ok, msg + handoff_note

        def done(result):
            self._set_tool_busy(False)
            if isinstance(result, Exception):
                self._append("ошибка", str(result), tag="err")
                return
            bundle, ok, msg = result
            self._append(
                "Вью",
                f"Логи собраны: {bundle}\n{msg}\n"
                "Cursor читает handoff/gist — не ищи файлы вручную.",
                tag="tool",
            )
            try:
                folder = str(Path(bundle).parent)
                if os.name == "nt":
                    os.startfile(folder)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(["xdg-open", folder])
            except OSError:
                pass

        self._run_bg(work, done)

    def _update_viu_full(self) -> None:
        from .lab.controller import lab_controller

        lab_controller.request_operator_priority("обновление Viu")
        self._append("ты", "[Обновить Вью]")
        self._set_busy(True)

        def work():
            return update_viu_full(
                branch=self.agent.config.update_branch,
                full_sync=True,
            )

        def done(result):
            self._set_busy(False)
            if isinstance(result, Exception):
                self._append("ошибка", str(result), tag="err")
                return
            ok, text, restart = result
            tag = "sys" if ok else "err"
            self._append("Вью", text, tag="tool" if ok else tag)
            stale = stamp_changed_since(self._boot_sha)
            if restart or stale:
                if stale and not restart:
                    self._append(
                        "система",
                        "Обновление уже на диске (bootstrap/Viu.cmd) — перезапуск через 2 с…",
                        tag="sys",
                    )
                elif restart:
                    self._append("система", "Перезапуск через 2 с…", tag="sys")
                self.root.after(2000, self._restart)

        self._run_bg(work, done)

    # ---------- Telegram ----------

    def _start_telegram(self) -> None:
        from .integrations.telegram import try_start_notifier

        def on_reply(text: str) -> None:
            self._queue.put(("telegram_reply", text))

        self._telegram = try_start_notifier(
            self.agent.config,
            on_reply=on_reply,
            get_status=self._telegram_status_line,
        )
        if self._telegram is not None:
            self._append(
                "система",
                "Telegram: бот включён. Напиши ему /start, если ещё не привязал чат.",
                tag="sys",
            )

    def _telegram_status_line(self) -> str:
        cfg = self.agent.config
        unity = cfg.unity_project or "(Unity не задан)"
        chat = "привязан" if self._telegram and self._telegram.enabled else "нет"
        from .integrations.telegram import settings as tg_settings
        from .llm_roles import model_label
        from .presence import is_away

        cid = tg_settings.chat_id(cfg)
        owners = ",".join(str(x) for x in sorted(tg_settings.owner_ids(cfg)))
        home = "нет дома" if is_away(cfg) else "дома"
        return (
            f"{version_label()}\n"
            f"Режим: {home} · {model_label(cfg, 'reflect')}\n"
            f"Ollama: {'ok' if ollama_available() else 'нет'}\n"
            f"Unity: {unity}\n"
            f"Занята: {getattr(self, '_busy_label', None) or ('да' if (self._tool_busy or self._llm_busy) else 'нет')}\n"
            f"Telegram chat: {cid or 'не привязан'} ({chat})\n"
            f"Telegram owner: {owners}\n"
            f"Ждём ответ: {'да' if self._telegram_waiting_reply else 'нет'}"
        )

    def _telegram_notify_question(self, text: str) -> None:
        if self._telegram is not None:
            self._telegram.notify_question(text)

    def _telegram_notify_error(self, text: str) -> None:
        if self._telegram is not None:
            self._telegram.notify_error(text)

    def _telegram_notify_done(self, text: str) -> None:
        from .quiet_hours import in_quiet_hours

        if in_quiet_hours(self.agent.config):
            return
        if self._telegram is not None and not self._telegram_waiting_reply:
            self._telegram.notify_done(text)

    def _telegram_notify_chat(self, text: str) -> None:
        if self._telegram is not None:
            self._telegram.notify_chat(text)

    def _handle_telegram_reply(self, text: str) -> None:
        from .integrations.telegram.router import route_telegram_message

        display = text
        if text.startswith("[tg_photo:"):
            cap = text.split("]", 1)[-1].strip() if "]" in text else ""
            display = "(фото)" + (f" {cap}" if cap else "")
        self._append("ты", f"[Telegram] {display}")
        self._record_llm_turn("user", text)

        # Прямая команда tool — без Ollama (creature_catalog_scan и т.п.).
        from .gui_direct import looks_like_missing_creature_tool, parse_direct_tool_command

        raw_low = " ".join((text or "").strip().lower().split())
        if raw_low in (
            "разметить существ",
            "разметка существ",
            "размечай существ",
            "существа разметить",
        ):
            self._telegram_waiting_reply = False
            # GUI только на ПК — в Telegram скажем открыть кнопку.
            msg = (
                "Разметка существ — кнопками в окне Вью:\n"
                "слева «Разметить существ» (или на ПК в чате Вью то же слово).\n"
                "Из Telegram могу только скан/авто: напиши «сканируй существ»."
            )
            self._append("система", msg, tag="sys")
            if self._telegram is not None:
                self._telegram.notify_chat(msg)
            # на всякий случай открыть окно, если Вью на этом же ПК
            self.root.after(0, self._open_creature_catalog)
            return

        parsed = parse_direct_tool_command(text, self.agent.registry)
        if parsed is not None:
            self._telegram_waiting_reply = False
            name, args = parsed
            self._run_tool(
                name, args, label=text, echo_user=False, notify_telegram=True
            )
            return
        if looks_like_missing_creature_tool(text) and self.agent.registry.get(
            "creature_catalog_scan"
        ) is None:
            self._telegram_waiting_reply = False
            msg = (
                "Команда существ ещё не в этой сборке.\n"
                "В окне Вью: «Обновить Вью» → перезапуск → снова "
                "`creature_catalog_scan` (один раз)."
            )
            self._append("система", msg, tag="sys")
            if self._telegram is not None:
                self._telegram.notify_chat(msg)
            return

        try:
            from .integrations.comfy.prompt_edit import is_prompt_show_request

            if is_prompt_show_request(text) and self._maybe_handle_comfy_reply(
                text, echo_user=False, notify_telegram=True
            ):
                self._telegram_waiting_reply = False
                return
        except Exception:  # noqa: BLE001
            pass

        try:
            if self._maybe_handle_comfy_reply(
                text, echo_user=False, notify_telegram=True
            ):
                self._telegram_waiting_reply = False
                return
        except Exception:  # noqa: BLE001
            pass

        try:
            if self._maybe_handle_comfy_chat(
                text, echo_user=False, notify_telegram=True
            ):
                self._telegram_waiting_reply = False
                return
        except Exception:  # noqa: BLE001
            pass

        try:
            if self._maybe_handle_compose_chat(
                text, echo_user=False, notify_telegram=True
            ):
                self._telegram_waiting_reply = False
                return
        except Exception:  # noqa: BLE001
            pass

        from .gui_busy import can_accept_chat

        # Lab/Comfy ≠ LLM: болтовня из Telegram идёт, пока модель не думает.
        if not can_accept_chat(llm_busy=self._llm_busy):
            self._append(
                "система",
                "Вью сейчас думает — ответ из Telegram подождёт.",
                tag="sys",
            )
            return
        mode = route_telegram_message(text, waiting_for_user=self._telegram_waiting_reply)
        self._telegram_waiting_reply = False
        if mode == "work":
            from .modes import mode_log_label

            self._append("система", f"· {mode_log_label(mode)} (Telegram)", tag="sys")
            self._run_agent_task(f"[Telegram — команда] {text}", via_telegram=True)
        else:
            self._run_agent_reflect(text, via_telegram=True)

    def _telegram_test(self) -> None:
        self._append("ты", "[Тест Telegram]")
        if self._telegram is None:
            from .integrations.telegram.notifier import TelegramNotifier

            probe = TelegramNotifier(
                self.agent.config,
                on_reply=lambda _t: None,
                get_status=lambda: "test",
            )
            ok, msg = probe.test_connection()
            tag = "tool" if ok else "err"
            self._append("Вью", msg, tag=tag)
            return
        ok, msg = self._telegram.test_connection()
        tag = "tool" if ok else "err"
        self._append("Вью", msg, tag=tag)

    def _try_direct_tool_command(self, text: str) -> bool:
        """Имя инструмента + args — сразу tool.run, без «размышляет»."""
        from .gui_direct import looks_like_missing_creature_tool, parse_direct_tool_command

        raw_low = " ".join((text or "").strip().lower().split())
        if raw_low in (
            "разметить существ",
            "разметка существ",
            "размечай существ",
            "существа разметить",
        ):
            self._append("ты", text)
            self._open_creature_catalog()
            return True

        parsed = parse_direct_tool_command(text, self.agent.registry)
        if parsed is None:
            if looks_like_missing_creature_tool(text) and self.agent.registry.get(
                "creature_catalog_scan"
            ) is None:
                self._append("ты", text)
                self._append(
                    "система",
                    "Команда существ есть в новой сборке, но здесь её ещё нет.\n"
                    "«Обновить Вью» (ветка cursor/viu-agent-core-65c2) → перезапуск окна.\n"
                    "Потом снова: creature_catalog_scan  (один раз, без склейки).",
                    tag="sys",
                )
                return True
            return False
        name, args = parsed
        raw = (text or "").strip()
        self._run_tool(name, args, label=raw)
        return True

    def _run_tool(
        self,
        name: str,
        args: dict,
        label: str = "",
        *,
        echo_user: bool = True,
        notify_telegram: bool = False,
    ) -> None:
        from .gui_busy import can_start_tool

        title = label or name
        # comfy_show из чата/алиаса — панель съёмки, не lab→«План MoCap».
        if name == "comfy_show":
            style = str((args or {}).get("style") or "realism")
            action = str((args or {}).get("action") or "").strip()
            if echo_user:
                self._append("ты", f"[{title}]")
            from .integrations.comfy.prompts import clean_action_for_wan
            from .integrations.comfy.show_profile import arm_show_profile
            from .lab.comfy_pipeline import COMFY_TOPIC
            from .lab.session import load_session, new_session, save_session

            sess = load_session(self.agent.config, COMFY_TOPIC) or new_session(COMFY_TOPIC)
            act = clean_action_for_wan(action) or (
                "standing relaxed in soft light, cinematic atmosphere"
            )
            arm_show_profile(sess.meta, style=style, action=act)
            sess.meta["catalog_slug"] = "show"
            sess.meta.pop("wan_positive", None)
            sess.meta.pop("wan_negative", None)
            save_session(self.agent.config, sess)
            self._append(
                "Вью",
                f"Шоу ({style}) — открываю «СЪЁМКА ВИДЕО», не План MoCap.\n"
                f"Поза: {act[:120]}",
                tag="viu",
            )
            self._open_comfy_studio(initial_profile="show", initial_style=style)
            return

        from .gui_busy import TOOLS_ALLOWED_DURING_LAB, can_start_tool

        readonly_diag = name in TOOLS_ALLOWED_DURING_LAB and self._tool_busy
        if not readonly_diag:
            if not can_start_tool(tool_busy=self._tool_busy, tool_name=name):
                msg = (
                    f"Уже крутится lab/Comfy — «{title}» подождёт.\n"
                    "Сейчас можно: **comfy_diag** / **comfy_status** / "
                    "**lab_status topic=comfy**.\n"
                    "ComfyUI: http://127.0.0.1:8188"
                )
                self._append("система", msg, tag="sys")
                if notify_telegram and self._telegram is not None:
                    self._telegram.notify_chat(msg)
                return
        if echo_user:
            self._append("ты", f"[{title}]")
        if not readonly_diag:
            self._set_tool_busy(True)
        threading.Thread(
            target=self._tool_worker,
            args=(name, args, title, notify_telegram, readonly_diag),
            daemon=True,
        ).start()

    def _tool_worker(
        self, name: str, args: dict, title: str, notify_telegram: bool = False,
        readonly_diag: bool = False,
    ) -> None:
        try:
            from .lab.controller import LAB_TOOL_NAMES, lab_controller

            if name in LAB_TOOL_NAMES:
                lab_controller.clear_operator_priority()
            tool = self.agent.registry.get(name)
            if tool is None:
                self._queue.put(("error", f"Инструмент {name!r} не найден."))
                return
            result = tool.run(args, self.agent.ctx)
            prefix = "OK" if result.ok else "ОШИБКА"
            body = f"[{title}] {prefix}\n{result.content}"
            self._queue.put(("tool_diag" if readonly_diag else "tool", body))
            if notify_telegram and self._telegram is not None:
                self._telegram.notify_chat(body[:1500])
        except Exception as exc:  # noqa: BLE001
            body = f"[{title}] ОШИБКА\n{exc}"
            self._queue.put(("tool_diag" if readonly_diag else "tool", body))
            if notify_telegram and self._telegram is not None:
                self._telegram.notify_error(body[:1500])

    def _run_agent_task(self, task: str, *, via_telegram: bool = False) -> None:
        if not via_telegram:
            self._append("ты", task)
        self._set_llm_busy(True)
        self._last_via_telegram = via_telegram
        threading.Thread(
            target=self._agent_worker,
            args=(task, "work", None, False),
            daemon=True,
        ).start()

    def _llm_history(self) -> list[dict[str, str]]:
        return list(self._llm_turns)

    def _record_llm_turn(self, who: str, text: str) -> None:
        clean = text.strip()
        if not clean or clean.startswith("["):
            return
        role = "user" if who in ("ты", "user") else "assistant"
        if role == "assistant":
            try:
                from .agent import sanitize_reflect_visible

                cleaned = sanitize_reflect_visible(clean)
                if cleaned:
                    clean = cleaned
            except Exception:  # noqa: BLE001
                pass
        self._llm_turns.append({"role": role, "content": clean[:4000]})

    def _run_agent_reflect(
        self,
        task: str,
        *,
        via_telegram: bool = False,
        heartbeat: bool = False,
        away_ping: bool = False,
    ) -> None:
        from .prompts.reflect_mode import reflect_no_history

        if not via_telegram and not heartbeat and not away_ping:
            self._append("ты", task)
            self._record_llm_turn("user", task)
        self._set_llm_busy(True)
        self._last_via_telegram = via_telegram or heartbeat or away_ping
        echo_tg = via_telegram
        if heartbeat or away_ping or reflect_no_history():
            history: list[dict[str, str]] = []
        else:
            hist = self._llm_history()
            history = hist[:-1] if hist and hist[-1].get("role") == "user" else hist
        threading.Thread(
            target=self._agent_worker,
            args=(task, "reflect", history, heartbeat, echo_tg, away_ping),
            daemon=True,
        ).start()

    def _agent_worker(
        self,
        task: str,
        mode: str,
        history: list | None = None,
        heartbeat: bool = False,
        echo_telegram: bool = False,
        away_ping: bool = False,
    ) -> None:
        def on_step(step):
            if step.kind == "think":
                preview = step.thought[:280] + ("…" if len(step.thought) > 280 else "")
                self._queue.put(("thinking", preview))
            elif step.kind == "action":
                self._queue.put(("step", f"[{step.tool}] {step.thought}"))
                if step.observation:
                    self._queue.put(
                        ("step", "    " + step.observation.replace("\n", "\n    "))
                    )
            elif step.kind == "error":
                self._queue.put(("step", step.observation))

        try:
            if mode == "reflect":
                result = self.agent.run_reflect(
                    task,
                    on_step=on_step,
                    history=history or [],
                    heartbeat=heartbeat,
                    away_ping=away_ping,
                    echo_telegram=echo_telegram,
                )
            else:
                result = self.agent.run(task, on_step=on_step)
            parts = result.final_parts or [result.final]
            for idx, part in enumerate(parts):
                is_last = idx == len(parts) - 1
                self._queue.put(
                    (
                        "final",
                        part,
                        result.waiting_for_user and is_last,
                        result.chat_only,
                        result.inner_thought if idx == 0 else "",
                        not result.tool_errors and is_last,
                        result.echo_telegram or echo_telegram,
                        is_last,
                        result.final if is_last and len(parts) > 1 else "",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "VIU_LLM_TIMEOUT" in msg or "не успела" in msg.lower():
                hint = ""
            elif "timed out" in msg.lower():
                hint = "\nЭто таймаут ответа модели, не «Ollama выключена». Увеличь VIU_LLM_TIMEOUT."
            else:
                hint = "\nПодсказка: запущена ли Ollama? Верна ли VIU_BASE_URL / VIU_MODEL?"
            self._queue.put(("error", msg + hint))

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                inner_thought = ""
                task_ok = True
                echo_telegram = False
                is_last = True
                full_for_history = ""
                if isinstance(item, tuple) and len(item) == 2:
                    kind, text = item
                    waiting = False
                    chat_only = False
                elif isinstance(item, tuple) and len(item) == 3:
                    kind, text, waiting = item
                    chat_only = False
                elif isinstance(item, tuple) and len(item) == 4:
                    kind, text, waiting, chat_only = item
                elif isinstance(item, tuple) and len(item) == 5:
                    kind, text, waiting, chat_only, inner_thought = item
                elif isinstance(item, tuple) and len(item) == 6:
                    kind, text, waiting, chat_only, inner_thought, task_ok = item
                elif isinstance(item, tuple) and len(item) >= 7:
                    kind, text, waiting, chat_only, inner_thought, task_ok, echo_telegram = (
                        item[0],
                        item[1],
                        item[2],
                        item[3],
                        item[4],
                        item[5],
                        item[6],
                    )
                    is_last = item[7] if len(item) > 7 else True
                    full_for_history = item[8] if len(item) > 8 and item[8] else text
                else:
                    continue
                if kind == "step":
                    self._append("шаг", text, tag="step")
                elif kind == "thinking":
                    self._append("размышляет", text, tag="step")
                elif kind in ("tool", "tool_diag"):
                    self._append("Вью", text, tag="tool")
                    if kind == "tool":
                        self._set_tool_busy(False)
                        from .lab.controller import lab_controller

                        lab_controller.clear_operator_priority()
                    self._refresh_action_visibility()
                    self._maybe_prompt_lab_rating()
                    self._maybe_prompt_comfy_clip_pick()
                    if text.startswith("[") and "ОШИБКА" in text:
                        self._telegram_notify_error(text)
                elif kind == "final":
                    # thought уже показан через kind=thinking — не дублировать
                    self._append("Вью", text, tag="viu")
                    if is_last:
                        self._set_llm_busy(False)
                        if full_for_history and full_for_history != text:
                            self._record_llm_turn("Вью", full_for_history)
                        else:
                            self._record_llm_turn("Вью", text)
                    if waiting:
                        self._telegram_waiting_reply = True
                        self._telegram_notify_question(text)
                    elif chat_only and (echo_telegram or self._last_via_telegram):
                        msg = ("💭 " + text) if self._heartbeat_notify else text
                        self._heartbeat_notify = False
                        self._telegram_notify_chat(msg)
                    elif chat_only:
                        pass
                    elif task_ok:
                        self._telegram_notify_done(text)
                    else:
                        self._telegram_notify_chat(f"⚠️ Не всё вышло.\n\n{text}")
                elif kind == "error":
                    self._append("ошибка", text, tag="err")
                    self._set_llm_busy(False)
                    self._telegram_notify_error(text)
                elif kind == "telegram_reply":
                    self._handle_telegram_reply(text)
                elif kind == "sys":
                    self._append("система", text, tag="sys")
                    if "Обновлено" in text or "Перезапуск" in text:
                        pass
                elif kind == "update_done":
                    self._set_busy(False)
                    if text == "restart":
                        self.root.after(500, self._restart)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _schedule_heartbeat(self) -> None:
        from .runtime_settings import get_heartbeat_interval_min

        minutes = get_heartbeat_interval_min(self.agent.config)
        if self._heartbeat_job is not None:
            try:
                self.root.after_cancel(self._heartbeat_job)
            except tk.TclError:
                pass
            self._heartbeat_job = None
        if minutes <= 0:
            return

        def tick() -> None:
            from .gui_busy import can_run_background_tick

            if can_run_background_tick(
                tool_busy=self._tool_busy, llm_busy=self._llm_busy
            ):
                self._run_heartbeat()
            self._heartbeat_job = self.root.after(minutes * 60_000, tick)

        self._heartbeat_job = self.root.after(minutes * 60_000, tick)

    def _run_heartbeat(self) -> None:
        from .presence import is_away
        from .quiet_hours import in_quiet_hours
        from .vision import ensure_vision

        if is_away(self.agent.config):
            return
        if in_quiet_hours(self.agent.config):
            # Ночь: тихое зерно вместо пинга Дена (self-compose).
            try:
                from .self_compose import maybe_night_think

                maybe_night_think(self.agent.config)
            except Exception:  # noqa: BLE001
                pass
            return

        ensure_vision(self.agent.config)
        self._append("система", "⏰ Вью проснулась по таймеру — смотрю, что можно сделать.", tag="sys")
        self._last_via_telegram = True
        self._heartbeat_notify = True
        self._run_agent_reflect("", heartbeat=True)

    def _schedule_away_ping(self) -> None:
        import random

        from .presence import is_away
        from .runtime_settings import away_ping_interval_min, get_away_ping_per_day

        if self._away_ping_job is not None:
            try:
                self.root.after_cancel(self._away_ping_job)
            except tk.TclError:
                pass
            self._away_ping_job = None

        if not is_away(self.agent.config) or get_away_ping_per_day(self.agent.config) <= 0:
            return

        base_min = away_ping_interval_min(self.agent.config)
        jitter = random.uniform(0.85, 1.15)
        minutes = max(60, int(base_min * jitter))

        def tick() -> None:
            # Comfy/lab могут идти часами — не сжигать слот ping из‑за tool_busy.
            if self._llm_busy:
                self._away_ping_job = self.root.after(10 * 60_000, tick)
                return
            self._run_away_ping()
            self._schedule_away_ping()

        self._away_ping_job = self.root.after(minutes * 60_000, tick)

    def _run_away_ping(self) -> None:
        from .presence import is_away
        from .quiet_hours import in_quiet_hours
        from .vision import ensure_vision

        if not is_away(self.agent.config):
            return
        if in_quiet_hours(self.agent.config):
            try:
                from .self_compose import maybe_night_think

                maybe_night_think(self.agent.config)
            except Exception:  # noqa: BLE001
                pass
            return

        ensure_vision(self.agent.config)
        self._append(
            "система",
            "💌 Вью сама пишет Дену (режим «меня нет»).",
            tag="sys",
        )
        self._last_via_telegram = True
        self._heartbeat_notify = False
        self._run_agent_reflect("", heartbeat=True, away_ping=True)

    def _schedule_lab(self) -> None:
        from .lab.paths import lab_interval_min

        minutes = lab_interval_min(self.agent.config)
        if self._lab_job is not None:
            try:
                self.root.after_cancel(self._lab_job)
            except tk.TclError:
                pass
            self._lab_job = None
        if minutes <= 0:
            return

        def tick() -> None:
            self._lab_tick(auto=True)
            self._lab_job = self.root.after(minutes * 60_000, tick)

        self._lab_job = self.root.after(minutes * 60_000, tick)

    def _lab_tick(self, *, auto: bool = False) -> None:
        from .gui_busy import can_run_background_tick

        if not can_run_background_tick(
            tool_busy=self._tool_busy, llm_busy=self._llm_busy
        ):
            return
        from .presence import is_away

        if auto and not is_away(self.agent.config):
            return
        from .lab.cascadeur_pipeline import CASCADEUR_TOPIC
        from .lab.comfy_pipeline import COMFY_TOPIC
        from .lab.session import load_session

        from .runtime_settings import get_away_auto_comfy

        away_comfy = (not auto) or get_away_auto_comfy(self.agent.config)

        # Сначала дожать Comfy, если ждём/в процессе (в away — только если away_auto_comfy)
        comfy = load_session(self.agent.config, COMFY_TOPIC)
        if away_comfy and comfy is not None and comfy.status in (
            "running",
            "paused",
            "awaiting_prompt",
            "awaiting_lora_pick",
            "awaiting_clip_pick",
        ):
            # Промпт и LoRA — только ответ Дена в Telegram, не auto-tick.
            if comfy.status in ("awaiting_prompt", "awaiting_lora_pick"):
                return
            if comfy.status == "awaiting_clip_pick" and auto:
                from .integrations.comfy.angles import AWAY_AUTO_TAKE_ID
                from .lab.session import load_session as _ls

                sess = _ls(self.agent.config, COMFY_TOPIC)
                pick_args = {
                    "angle": AWAY_AUTO_TAKE_ID,
                    "score": "3",
                    "notes": "auto away (fallback a/c если нет b)",
                }
                # не затирать catalog_slug / граф
                if sess is not None:
                    if sess.meta.get("catalog_slug"):
                        pick_args["catalog_slug"] = str(sess.meta["catalog_slug"])
                    ef = sess.meta.get("enters_from") or []
                    et = sess.meta.get("exits_to") or []
                    if ef:
                        pick_args["enters_from"] = ",".join(ef) if isinstance(ef, list) else str(ef)
                    if et:
                        pick_args["exits_to"] = ",".join(et) if isinstance(et, list) else str(et)
                self._run_tool(
                    "comfy_clip_pick",
                    pick_args,
                    label="Comfy: авто-выбор дубля",
                )
                self._run_tool(
                    "lab_step",
                    {"topic": COMFY_TOPIC, "run_all": "1"},
                    label="Lab Comfy (auto)",
                )
                return
            if comfy.status in ("running", "paused"):
                self._run_tool(
                    "lab_step",
                    {"topic": COMFY_TOPIC, "run_all": "1"},
                    label="Lab Comfy (auto)",
                )
                return

        # Периодически новая Comfy-съёмка (Вью сама выбирает кадр)
        if (
            away_comfy
            and auto
            and (comfy is None or comfy.status in ("completed", "idle", "awaiting_rating"))
        ):
            # чередование: если cascadeur активен — сначала его; иначе comfy
            cas = load_session(self.agent.config, CASCADEUR_TOPIC)
            if cas is not None and cas.status in ("running", "paused"):
                pass  # fall through to cascadeur
            elif cas is None or cas.status in ("completed", "idle", "awaiting_rating"):
                from .lab.comfy_director import invent_next_shot

                probe = invent_next_shot(self.agent.config)
                if probe.stop_cycle:
                    self._append("Вью", probe.summary_ru(), tag="viu")
                    return
                self._lab_comfy_action(auto=True)
                return

        session = load_session(self.agent.config, CASCADEUR_TOPIC)
        if session is None:
            if auto:
                self._run_tool(
                    "lab_run_all",
                    {"topic": CASCADEUR_TOPIC, "reset": "1"},
                    label="Lab: весь цикл (auto)",
                )
            else:
                self._lab_start_action()
            return
        if session.status == "awaiting_rating":
            if not auto:
                self._lab_start_action()
            return
        if session.status in ("completed", "idle"):
            if auto:
                return
            self._lab_start_action(reset=True)
            return
        self._run_tool("lab_step", {"topic": CASCADEUR_TOPIC, "run_all": "1"}, label="Lab: весь цикл")

    def _lab_start_action(self, *, reset: bool = False) -> None:
        from .lab.cascadeur_pipeline import CASCADEUR_TOPIC

        args: dict = {"topic": CASCADEUR_TOPIC, "run_all": "1"}
        if reset:
            args["reset"] = "1"
        self._run_tool("lab_start", args, label="Лаборатория: Cascadeur", echo_user=True)

    def _lab_comfy_action(
        self,
        *,
        auto: bool = False,
        action: str | None = None,
        render_profile: str = "",
        show_style: str = "realism",
        auto_fire: bool = False,
        wan_positive: str = "",
        wan_negative: str = "",
        lora_indices: list | None = None,
        shoot_mode: str = "",
        seed_image_path: str = "",
    ) -> None:
        """Вью сама выбирает кадр (каталог/граф). Без диалога idle stand.

        action= — явная сцена из чата (описание Дена), без invent.
        render_profile=show — шоу-дубль (SmoothMix / cinematic), не MoCap×5.
        auto_fire= — промпт+LoRA уже собраны в чате → сразу генерация (from_shoot_panel).
        shoot_mode=t2i/i2i — still PNG в Telegram.
        """
        from .lab.comfy_director import invent_next_shot
        from .lab.comfy_pipeline import COMFY_TOPIC
        from .lab.session import load_session
        from .presence import is_away

        chat_action = (action or "").strip()
        profile = (render_profile or "").strip().lower()
        if auto_fire and chat_action:
            from pathlib import Path

            from .lab.session import new_session, save_session
            from .integrations.comfy.lora import (
                spec_to_dict,
                specs_from_indices,
            )
            from .integrations.comfy.shoot_settings import (
                MODE_I2I,
                MODE_T2I,
                apply_shoot_settings,
                normalize_shoot_mode,
            )

            existing = load_session(self.agent.config, COMFY_TOPIC)
            if existing is None:
                existing = new_session(COMFY_TOPIC)
            existing.status = "running"
            existing.step = 0
            existing.meta["shoot_intent"] = True
            existing.meta["from_shoot_panel"] = True
            existing.meta["auto_invent_shoot"] = True
            existing.meta.pop("auto_approved_shoot", None)
            existing.meta["approved"] = False
            existing.meta["action"] = chat_action
            existing.meta["approved_action"] = chat_action
            existing.meta["catalog_slug"] = (
                "show" if profile in ("show", "шоу", "smoothmix", "beauty") else "chat_scene"
            )
            existing.meta["shot_reason"] = "chat: invent auto"
            existing.meta["prompt_user_edited"] = True
            mode = normalize_shoot_mode(shoot_mode) if shoot_mode else MODE_T2I
            seed_p = Path(seed_image_path) if seed_image_path else None
            if seed_p is not None and seed_p.is_file() and mode == MODE_T2I:
                mode = MODE_I2I
            apply_shoot_settings(existing.meta, mode=mode)
            if seed_p is not None and seed_p.is_file():
                try:
                    from .integrations.comfy.seed_pose import (
                        save_seed_state,
                        stage_seed_for_comfy,
                    )

                    ok_s, _msg_s, staged = stage_seed_for_comfy(
                        self.agent.config, seed_p
                    )
                    if ok_s:
                        save_seed_state(
                            self.agent.config,
                            enabled=True,
                            path=str(seed_p),
                            comfy_name=staged or "viu_pose_seed.png",
                        )
                        existing.meta["i2v_seed_enabled"] = True
                        existing.meta["i2v_seed_path"] = str(seed_p)
                        existing.meta["i2v_seed_comfy"] = staged or "viu_pose_seed.png"
                except Exception:  # noqa: BLE001
                    pass
            if profile in ("show", "шоу", "smoothmix", "beauty"):
                from .integrations.comfy.show_profile import arm_show_profile

                arm_show_profile(
                    existing.meta,
                    style=show_style or "realism",
                    action=chat_action,
                    keep_prompts=True,
                )
                existing.meta["render_profile"] = "show"
            else:
                existing.meta["render_profile"] = "mocap"
                existing.meta.pop("show_style", None)
            if wan_positive.strip():
                existing.meta["wan_positive"] = wan_positive.strip()
            if wan_negative.strip():
                existing.meta["wan_negative"] = wan_negative.strip()
            idxs = [int(x) for x in (lora_indices or [])]
            existing.meta["setup_lora_indices"] = idxs
            existing.meta["lora_last_pick"] = idxs
            try:
                specs = specs_from_indices(self.agent.config, idxs) if idxs else []
                existing.meta["selected_loras"] = [spec_to_dict(s) for s in specs]
            except Exception:  # noqa: BLE001
                existing.meta["selected_loras"] = []
            existing.meta.pop("lora_pick_done", None)
            existing.meta.pop("clip_batch_id", None)
            existing.meta.pop("clip_candidate_ids", None)
            existing.meta.pop("clip_kept_id", None)
            save_session(self.agent.config, existing)
            kind = "картинку" if mode in (MODE_T2I, MODE_I2I) else "клип"
            self._append(
                "Вью",
                f"Снимаю сама ({mode}) — {chat_action[:120]}.\n"
                f"Болтаем дальше; когда будет готово — пришлю {kind}.",
                tag="viu",
            )
            start_args = {
                "topic": COMFY_TOPIC,
                "run_all": "1",
                "reset": "0",
                "shoot": "1",
                "action": chat_action,
                "catalog_slug": existing.meta["catalog_slug"],
                "shot_reason": "chat: invent auto",
                "from_shoot_panel": "1",
                "render_profile": existing.meta.get("render_profile") or "mocap",
                "show_style": show_style or "realism",
            }
            if wan_positive.strip():
                start_args["_wan_positive"] = wan_positive.strip()
            if wan_negative.strip():
                start_args["_wan_negative"] = wan_negative.strip()
            self._run_tool(
                "lab_start",
                start_args,
                label="Съёмка: invent из чата",
                echo_user=True,
            )
            return

        if profile in ("show", "шоу", "smoothmix", "beauty"):
            from .integrations.comfy.prompts import clean_action_for_wan
            from .integrations.comfy.show_profile import (
                arm_show_profile,
                find_show_unet,
            )
            from .lab.session import new_session, save_session

            existing = load_session(self.agent.config, COMFY_TOPIC)
            if existing is None:
                existing = new_session(COMFY_TOPIC)
            if not chat_action:
                chat_action = (
                    str(existing.meta.get("approved_action") or "").strip()
                    or str(existing.meta.get("action") or "").strip()
                    or "standing relaxed in soft light, cinematic atmosphere"
                )
            chat_action = clean_action_for_wan(chat_action)
            keep = bool(existing.meta.get("prompt_user_edited"))
            from_panel = bool(existing.meta.get("from_shoot_panel"))
            kept_pos = str(existing.meta.get("wan_positive") or "") if keep else ""
            kept_neg = str(existing.meta.get("wan_negative") or "") if keep else ""
            existing.status = "running"
            existing.step = 0
            arm_show_profile(
                existing.meta,
                style=show_style or "realism",
                action=chat_action,
                keep_prompts=keep or from_panel,
            )
            existing.meta["catalog_slug"] = "show"
            if from_panel:
                existing.meta["from_shoot_panel"] = True
                existing.meta["shoot_intent"] = True
            existing.meta.pop("lora_pick_done", None)
            existing.meta.pop("clip_batch_id", None)
            existing.meta.pop("clip_candidate_ids", None)
            if keep and kept_pos:
                existing.meta["wan_positive"] = kept_pos
                existing.meta["prompt_user_edited"] = True
            if keep and kept_neg:
                existing.meta["wan_negative"] = kept_neg
            save_session(self.agent.config, existing)
            unet, note = find_show_unet(self.agent.config)
            self._append(
                "Вью",
                f"Шоу-дубль ({show_style or 'realism'}) — {chat_action[:100]}.\n"
                f"{note}\n"
                + ("SmoothMix подхвачу. " if unet else "Пока без SmoothMix — cinematic Wan. ")
                + (
                    "Снимаю сразу (панель Съёмка)."
                    if from_panel
                    else "Снимаю по настройкам панели «Съёмка»."
                ),
                tag="viu",
            )
            start_args = {
                "topic": COMFY_TOPIC,
                "run_all": "1",
                "reset": "0" if (keep or from_panel) else "1",
                "shoot": "1",
                "action": chat_action,
                "catalog_slug": "show",
                "shot_reason": "chat: show double",
                "render_profile": "show",
                "show_style": show_style or "realism",
            }
            if from_panel:
                start_args["from_shoot_panel"] = "1"
            if keep and kept_pos:
                start_args["_wan_positive"] = kept_pos
            if keep and kept_neg:
                start_args["_wan_negative"] = kept_neg
            self._run_tool(
                "lab_start",
                start_args,
                label="Шоу-дубль",
                echo_user=True,
            )
            return

        if chat_action and not auto:
            from .lab.session import new_session, save_session

            existing = load_session(self.agent.config, COMFY_TOPIC)
            if existing is None:
                existing = new_session(COMFY_TOPIC)
            # Не угадывать catalog slug — иначе sync затрёт EN-сцену idle/sit_down.
            slug = "chat_scene"
            existing.status = "running"
            existing.step = 0
            existing.meta["shoot_intent"] = True
            existing.meta.pop("auto_approved_shoot", None)
            existing.meta["approved"] = False
            existing.meta["action"] = chat_action
            existing.meta["approved_action"] = chat_action
            existing.meta["catalog_slug"] = slug
            existing.meta["shot_reason"] = "chat: directed scene"
            existing.meta["prompt_user_edited"] = True
            existing.meta["render_profile"] = "mocap"
            existing.meta.pop("show_style", None)
            existing.meta.pop("lora_pick_done", None)
            existing.meta.pop("clip_batch_id", None)
            existing.meta.pop("clip_candidate_ids", None)
            save_session(self.agent.config, existing)
            self._append(
                "Вью",
                f"Сцена из чата — {chat_action[:120]}.\n"
                "Поднимаю Comfy → панель в Telegram: Промпт / LoRA, потом «Снять».",
                tag="viu",
            )
            self._run_tool(
                "lab_start",
                {
                    "topic": COMFY_TOPIC,
                    "run_all": "1",
                    "reset": "1",
                    "shoot": "1",
                    "action": chat_action,
                    "catalog_slug": slug,
                    "shot_reason": "chat: directed scene",
                    "render_profile": "mocap",
                },
                label="MoCap: сцена из чата",
                echo_user=True,
            )
            return

        existing = load_session(self.agent.config, COMFY_TOPIC)
        # Уже ждём промпт/LoRA ИЛИ Ден правил Wan-промпт — не invent+reset
        # (иначе sit-on-bed стирается и встаёт touch_self, а очередь пустая).
        has_user_prompt = bool(
            existing is not None
            and existing.meta.get("prompt_user_edited")
            and (
                existing.meta.get("wan_positive")
                or existing.meta.get("approved_action")
                or existing.meta.get("action")
            )
        )
        if (
            not auto
            and existing is not None
            and (
                existing.status
                in (
                    "awaiting_prompt",
                    "awaiting_lora_pick",
                    "awaiting_rating",
                    "awaiting_clip_pick",
                )
                or has_user_prompt
            )
        ):
            from .lab.comfy_director import infer_slug_from_action
            from .lab.session import save_session

            action = str(
                existing.meta.get("approved_action")
                or existing.meta.get("action")
                or ""
            )
            slug = str(existing.meta.get("catalog_slug") or "")
            inferred = infer_slug_from_action(action)
            # Ручной sit-промпт не должен оставаться на slug touch_self.
            if inferred and inferred != slug:
                slug = inferred
                existing.meta["catalog_slug"] = slug
                existing.meta["prompt_edit_slug"] = slug
            # Оценка / idle / completed не должны стопорить съёмку.
            if existing.status in (
                "completed",
                "idle",
                "awaiting_rating",
                "awaiting_clip_pick",
            ):
                if existing.status == "awaiting_rating":
                    existing.rating_notes = (
                        existing.rating_notes or "auto-skip: MoCap shoot"
                    )
                existing.status = "running"
                existing.step = 0
            existing.meta["shoot_intent"] = True
            # Уже на панели — GUI «Снять» = старт генерации.
            if existing.status in ("awaiting_prompt", "awaiting_lora_pick"):
                from .integrations.comfy.comfy_panel import apply_setup_and_start
                from .lab.comfy_pipeline import run_until_done
                from .lab.session import save_session as _save

                if existing.status == "awaiting_lora_pick":
                    existing.status = "awaiting_prompt"
                if action:
                    existing.meta["action"] = action
                    existing.meta["approved_action"] = action
                _save(self.agent.config, existing)
                start_msg = apply_setup_and_start(self.agent.config, existing)
                self._append("Вью", start_msg, tag="viu")
                ok, cont = run_until_done(self.agent.config, existing)
                if cont:
                    self._append("Вью", cont[:800], tag="tool")
                return
            existing.meta.pop("auto_approved_shoot", None)
            existing.meta["approved"] = False
            if action:
                existing.meta["approved_action"] = action
                existing.meta["action"] = action
            # Не оставлять awaiting_* без панели — иначе lab молчит.
            if existing.status in (
                "awaiting_rating",
                "awaiting_clip_pick",
                "completed",
                "idle",
                "paused",
            ):
                existing.status = "running"
                if existing.step < 3:
                    existing.step = 0
            existing.meta.pop("lora_pick_done", None)
            existing.meta.pop("clip_batch_id", None)
            existing.meta.pop("clip_candidate_ids", None)
            save_session(self.agent.config, existing)
            self._append(
                "Вью",
                f"Кадр `{slug or '…'}`"
                + (f" — {action[:80]}" if action else "")
                + ".\n"
                "Панель в Telegram: настрой Промпт/LoRA, жми «Снять».",
                tag="viu",
            )
            start_args = {
                "topic": COMFY_TOPIC,
                "run_all": "1",
                "shoot": "1",
            }
            if action:
                start_args["action"] = action
            if slug:
                start_args["catalog_slug"] = slug
            self._run_tool(
                "lab_start",
                start_args,
                label="MoCap: продолжить съёмку",
                echo_user=True,
            )
            return

        plan = invent_next_shot(self.agent.config, consume_queue=True)
        if plan.stop_cycle:
            self._append("Вью", plan.summary_ru(), tag="viu")
            return
        self._append("Вью", plan.summary_ru(), tag="viu")
        from ..integrations.comfy.focus import focus_cycle_status
        from .lab.session import save_session

        self._append("Вью", focus_cycle_status(self.agent.config), tag="viu")
        if plan.from_queue or plan.wan_positive:
            sess = load_session(self.agent.config, COMFY_TOPIC)
            if sess is None:
                from .lab.session import new_session

                sess = new_session(COMFY_TOPIC)
            if plan.wan_positive:
                sess.meta["wan_positive"] = plan.wan_positive
                sess.meta["prompt_user_edited"] = True
                sess.meta["prompt_edit_slug"] = plan.catalog_slug
            if plan.wan_negative:
                sess.meta["wan_negative"] = plan.wan_negative
            if plan.queue_notes:
                sess.meta["queue_notes"] = plan.queue_notes
            save_session(self.agent.config, sess)
        if plan.from_queue:
            from .integrations.comfy.shot_queue import (
                ShotQueueItem,
                apply_item_lora_to_session,
                apply_item_seeds_to_session,
            )

            q_item = ShotQueueItem(
                id="from-plan",
                catalog_slug=plan.catalog_slug,
                action=plan.action,
                lora_mode=plan.lora_mode or "inherit",
                lora_indices=list(plan.lora_indices or []),
                start_seed_id=str(getattr(plan, "start_seed_id", "") or ""),
                end_seed_id=str(getattr(plan, "end_seed_id", "") or ""),
            )
            seed_msg = apply_item_seeds_to_session(self.agent.config, q_item)
            if seed_msg:
                self._append("Вью", seed_msg, tag="viu")
            if (plan.lora_mode or "inherit") != "inherit":
                lora_msg = apply_item_lora_to_session(self.agent.config, q_item)
                if lora_msg:
                    self._append("Вью", lora_msg, tag="viu")
        if not auto and not is_away(self.agent.config):
            self._append(
                "Вью",
                "Сначала подниму ComfyUI (если спит), затем ставлю jobs в очередь API.\n"
                "Управление — Студия Comfy; браузерный canvas для MoCap не нужен.\n"
                "В логе должно появиться `got prompt` и загрузка GPU.",
                tag="viu",
            )
        args = {
            "topic": COMFY_TOPIC,
            "run_all": "1",
            "reset": "1",
            "shoot": "1",
            "action": plan.action,
            "catalog_slug": plan.catalog_slug,
            "enters_from": ",".join(plan.enters_from),
            "exits_to": ",".join(plan.exits_to),
            "shot_reason": plan.reason,
            "looped": "1" if plan.looped else "0",
        }
        self._run_tool(
            "lab_start",
            args,
            label="MoCap: снять клип",
            echo_user=not auto,
        )

    def _interaction_lab_action(self) -> None:
        """Совместные анимации: lab topic=interaction, пилот wave 1."""
        from .interaction_catalog import InteractionCatalogStore, interaction_catalog_path
        from .lab.interaction_pipeline import INTERACTION_TOPIC

        store = InteractionCatalogStore(interaction_catalog_path(self.agent.config)).load()
        holes = store.holes_for_wave(wave=1)
        slug = holes[0].slug if holes else "shanya_wolf_approach"
        title = holes[0].title_ru if holes else "совместная сцена"
        self._append(
            "Вью",
            f"Лаборатория совместных анимаций: `{slug}` — {title}\n"
            "Шаги: blocking → master draft Comfy → …\n"
            "Нужны: Shanya.fbx + wolf_alpha в creature_catalog (см. docs/INTERACTION_SETUP.md).",
            tag="viu",
        )
        self._run_tool(
            "lab_start",
            {
                "topic": INTERACTION_TOPIC,
                "run_all": "1",
                "reset": "1",
                "catalog_slug": slug,
            },
            label="Лаборатория: совместные",
            echo_user=True,
        )

    def _lab_run_all_action(self, *, reset: bool = False) -> None:
        from .lab.cascadeur_pipeline import CASCADEUR_TOPIC

        args: dict = {"topic": CASCADEUR_TOPIC, "run_all": "1"}
        if reset:
            args["reset"] = "1"
        self._run_tool("lab_run_all", args, label="Lab: весь цикл", echo_user=True)

    def _schedule_comfy_home_watch(self) -> None:
        """Дома: если ждут выбора клипа — открыть окно само (не искать кнопку)."""

        def tick() -> None:
            try:
                from .presence import is_away

                if not is_away(self.agent.config):
                    self._maybe_prompt_comfy_clip_pick()
                    self._maybe_prompt_comfy_wan_editor()
            except Exception:
                pass
            self.root.after(20_000, tick)

        self.root.after(8_000, tick)

    def _maybe_prompt_comfy_wan_editor(self) -> None:
        """Дома: если ждут одобрения промпта — напомнить в чате, НЕ открывать План MoCap.

        План MoCap плодил окна. Съёмка идёт через «СЪЁМКА ВИДЕО».
        """
        from .lab.comfy_pipeline import COMFY_TOPIC
        from .lab.session import load_session
        from .presence import is_away

        if is_away(self.agent.config):
            return
        if getattr(self, "_comfy_prompt_prompt_open", False):
            return
        if self._tool_busy:
            return
        session = load_session(self.agent.config, COMFY_TOPIC)
        if session is None or session.status != "awaiting_prompt":
            return
        self._comfy_prompt_prompt_open = True
        self._append(
            "Вью",
            "Жду «Снять» в панели «СЪЁМКА ВИДЕО» (или ок / Снять в Telegram).\n"
            "«План MoCap» сама не открываю — он для очереди по графам.",
            tag="viu",
        )
        self.root.after(
            60_000, lambda: setattr(self, "_comfy_prompt_prompt_open", False)
        )

    def _maybe_prompt_comfy_clip_pick(self) -> None:
        from .lab.comfy_pipeline import COMFY_TOPIC
        from .lab.session import load_session
        from .presence import is_away

        if is_away(self.agent.config):
            return
        if getattr(self, "_comfy_clip_prompt_open", False):
            return
        if self._tool_busy:
            return
        session = load_session(self.agent.config, COMFY_TOPIC)
        if session is None or session.status != "awaiting_clip_pick":
            return
        self._comfy_clip_prompt_open = True
        self._append(
            "Вью",
            "Клипы готовы — открою «Оценить видео» (выбор лучшего mp4).\n"
            "Или в чате: «лучший: take_b» / «отклонить все».\n"
            "Это оценка видео, не Cascadeur lab.",
            tag="viu",
        )
        try:
            self._open_comfy_clip_review()
        finally:
            # снова предложить, если закрыли без выбора
            self.root.after(30_000, lambda: setattr(self, "_comfy_clip_prompt_open", False))

    def _maybe_prompt_lab_rating(self) -> None:
        from .lab.cascadeur_pipeline import CASCADEUR_TOPIC
        from .lab.comfy_pipeline import COMFY_TOPIC
        from .lab.session import load_session

        comfy = load_session(self.agent.config, COMFY_TOPIC)
        if comfy is not None and comfy.status == "awaiting_clip_pick":
            self._append(
                "система",
                "Видео готово к оценке — «3. Оценить видео (лучший клип)» "
                "в ComfyUI или Студия → Оценить видео.",
                tag="sys",
            )
            return
        session = load_session(self.agent.config, CASCADEUR_TOPIC)
        if session is None or session.status != "awaiting_rating":
            return
        self._append(
            "система",
            "Cascadeur lab готова к оценке FBX — «Оценить результат lab» "
            "(это не видео Comfy).",
            tag="sys",
        )

    def _open_lab_rating(self) -> None:
        from .lab.comfy_pipeline import COMFY_TOPIC
        from .lab.cascadeur_pipeline import CASCADEUR_TOPIC
        from .lab.review_gui import open_lab_rating_review
        from .lab.session import load_session

        topic = CASCADEUR_TOPIC
        comfy = load_session(self.agent.config, COMFY_TOPIC)
        if comfy is not None and comfy.status == "awaiting_rating":
            topic = COMFY_TOPIC

        def done(ok: bool, msg: str) -> None:
            tag = "tool" if ok else "sys"
            self._append("Вью", msg, tag=tag)

        open_lab_rating_review(self.root, self.agent.config, topic, on_finished=done)

    def _open_comfy_ui(self) -> None:
        import webbrowser

        url = str(getattr(self.agent.config, "comfy_url", None) or "http://127.0.0.1:8188")
        self._append("ты", "[Открыть ComfyUI]")

        def work() -> tuple[bool, str]:
            from .integrations.comfy.client import ComfyClient
            from .integrations.comfy.process import ensure_comfy_running

            try:
                ok, msg = ComfyClient(base_url=url, timeout=3.0).ping()
                if ok:
                    return True, msg
                ok2, msg2 = ensure_comfy_running(
                    self.agent.config,
                    wait_seconds=180.0,
                    auto_install=True,
                    force_restart=True,
                )
                return ok2, msg2
            except Exception as exc:  # noqa: BLE001
                return False, str(exc)

        def done(result) -> None:
            if isinstance(result, Exception):
                self._append(
                    "ошибка",
                    f"Не проверила Comfy: {result}\nОткрой сам: {url}",
                    tag="err",
                )
                return
            ok, ping = result
            if not ok:
                self._append(
                    "Вью",
                    f"ComfyUI **не поднялся** на {url}\n{ping}\n\n"
                    "Студия Comfy → «Поднять ComfyUI». Лог: `.viu/logs/comfy_launch.log`.\n"
                    "Браузер не открываю — страница была бы пустой.",
                    tag="err",
                )
                return
            try:
                webbrowser.open(url)
            except Exception as exc:  # noqa: BLE001
                self._append(
                    "ошибка",
                    f"Не открыла браузер: {exc}\nОткрой сама: {url}",
                    tag="err",
                )
                return
            self._append(
                "Вью",
                f"ComfyUI отвечает на {url} — сервер жив.\n"
                "Съёмка не через этот canvas: «MoCap: снять клип» / **Студия Comfy**.\n"
                "Браузер открыла только как монитор :8188; пустой Unsaved Workflow — ожидаемо.\n"
                "Прогресс GPU/очереди — Студия и `.viu/logs/comfy_launch.log` "
                "(должно появиться `got prompt`).",
                tag="tool",
            )

        self._run_bg(work, done)

    def _open_comfy_clip_review(self) -> None:
        from .integrations.comfy.clip_review_gui import open_comfy_clip_review
        from .lab.comfy_pipeline import COMFY_TOPIC
        from .lab.session import load_session

        def done(ok: bool, msg: str) -> None:
            self._append("Вью", msg, tag="tool" if ok else "sys")
            session = load_session(self.agent.config, COMFY_TOPIC)
            if (
                ok
                and session
                and session.status == "running"
                and not self._tool_busy
            ):
                self._run_tool(
                    "lab_step",
                    {"topic": COMFY_TOPIC, "run_all": "1"},
                    label="Comfy: отчёт после выбора",
                    echo_user=False,
                )

        open_comfy_clip_review(self.root, self.agent.config, on_finished=done)

    def _open_comfy_prompt_editor(self) -> None:
        """Совместимость: открывает объединённый «План MoCap» в режиме lab."""
        self._open_comfy_shot_queue(focus_lab=True)

    def _open_comfy_studio(
        self,
        *,
        initial_profile: str = "",
        initial_style: str = "realism",
    ) -> None:
        from .integrations.comfy.studio_gui import ComfyStudioCallbacks, open_comfy_studio

        def shoot(profile: str, style: str) -> None:
            from .lab.comfy_pipeline import COMFY_TOPIC
            from .lab.session import load_session, save_session

            sess = load_session(self.agent.config, COMFY_TOPIC)
            action = ""
            if sess is not None:
                action = str(
                    sess.meta.get("approved_action")
                    or sess.meta.get("action")
                    or ""
                ).strip()
                sess.meta["from_shoot_panel"] = True
                sess.meta["shoot_intent"] = True
                save_session(self.agent.config, sess)
            self._append(
                "Вью",
                "Снимаю из панели «Съёмка» — сразу в Comfy, без «План MoCap».\n"
                "Статус: смотри строку в панели / comfy_status. "
                "«В фон» = общаться; «Стоп генерации» = interrupt.",
                tag="viu",
            )
            if profile == "show":
                self._lab_comfy_action(
                    action=action or None,
                    render_profile="show",
                    show_style=style or "realism",
                )
            else:
                self._lab_comfy_action(action=action or None)

        def new_clip(profile: str, style: str) -> None:
            label = f"шоу ({style})" if profile == "show" else "MoCap"
            self._append(
                "Вью",
                f"Новый клип — профиль {label}. Правишь в панели → «Снять».",
                tag="viu",
            )

        def background_chat() -> None:
            # Чат и так свободен при tool_busy; снимаем блокировку сайдбара/ожидания.
            self._set_tool_busy(False)
            from .lab.controller import lab_controller

            lab_controller.clear_operator_priority()
            self._append(
                "Вью",
                "Панель съёмки в фоне. Можно общаться.\n"
                "Генерация в Comfy продолжается (если уже пошла).\n"
                "Остановить job: снова открой Съёмку → «Стоп генерации» "
                "или comfy_queue_clear force=1.",
                tag="viu",
            )

        def stop_generation() -> None:
            from .integrations.comfy.client import ComfyClient
            from .integrations.comfy.queue_manage import clear_comfy_queue
            from .lab.comfy_pipeline import COMFY_TOPIC
            from .lab.controller import lab_controller
            from .lab.session import load_session, save_session

            lab_controller.request_operator_priority("стоп генерации из панели")
            url = getattr(self.agent.config, "comfy_url", None) or "http://127.0.0.1:8188"
            client = ComfyClient(base_url=str(url))
            ok, ping = client.ping()
            parts = []
            if ok:
                msg = clear_comfy_queue(client, interrupt_running=True, free_memory=False)
                parts.append(msg)
            else:
                parts.append(f"Comfy недоступен: {ping}")
            sess = load_session(self.agent.config, COMFY_TOPIC)
            if sess is not None and sess.status in (
                "running",
                "awaiting_prompt",
                "awaiting_lora_pick",
                "awaiting_clip_pick",
            ):
                sess.status = "paused"
                sess.pause_reason = "stopped_from_shoot_panel"
                sess.meta.pop("from_shoot_panel", None)
                save_session(self.agent.config, sess)
                parts.append(f"Lab comfy → paused ({sess.pause_reason}).")
            self._set_tool_busy(False)
            self._append("Вью", "⏹ Стоп генерации:\n" + "\n".join(parts), tag="viu")

        cb = ComfyStudioCallbacks(
            on_ensure_comfy=lambda: self._ensure_comfy_from_studio(),
            on_mocap_shoot=lambda: self._lab_comfy_action(),
            on_edit_prompt=lambda: self._open_comfy_shot_queue(focus_lab=True),
            on_pick_clips=lambda: self._open_comfy_clip_review(),
            on_open_browser=lambda: self._open_comfy_ui(),
            on_shot_queue=lambda: self._open_comfy_shot_queue(),
            on_comfy_diag=lambda: self._run_tool(
                "comfy_diag", {}, label="Диагностика Comfy", echo_user=True
            ),
            on_shoot=shoot,
            on_new_clip=new_clip,
            on_background_chat=background_chat,
            on_stop_generation=stop_generation,
        )
        open_comfy_studio(
            self.root,
            self.agent.config,
            cb,
            initial_profile=initial_profile,
            initial_style=initial_style,
        )

    def _ensure_comfy_from_studio(self) -> None:
        """Студия «Поднять» — всегда restart, чтобы не залипать на зомби :8188."""
        self._append(
            "Вью",
            "Поднимаю ComfyUI (restart)… Смотри `.viu/logs/comfy_launch.log`. "
            "Если снова пусто — VIU_COMFY_SHOW_CONSOLE=1 в .env.",
            tag="viu",
        )
        self._run_tool(
            "comfy_ensure",
            {"restart": "1", "wait": "180"},
            label="Поднять ComfyUI",
            echo_user=True,
        )

    def _open_comfy_shot_queue(self, *, focus_lab: bool = False) -> None:
        from .integrations.comfy.shot_queue_gui import open_shot_queue_editor

        def done(ok: bool, msg: str) -> None:
            if ok and msg:
                self._append("Вью", msg, tag="tool")

        open_shot_queue_editor(
            self.root,
            self.agent.config,
            on_finished=done,
            on_shoot=lambda: self._lab_comfy_action(),
            focus_lab=focus_lab,
        )

    def _open_comfy_seed_library(self) -> None:
        from .integrations.comfy.seed_library_gui import open_seed_library

        def done(ok: bool, msg: str) -> None:
            if ok and msg:
                self._append("Вью", msg, tag="tool")

        open_seed_library(self.root, self.agent.config, on_finished=done)

    def _schedule_cursor_inbox(self) -> None:
        """Раз в несколько минут — забрать задачи Cursor с GitHub и выполнить без Дена."""
        self.root.after(45_000, self._poll_cursor_inbox_once)

        def tick() -> None:
            self._poll_cursor_inbox_once()
            self.root.after(180_000, tick)

        self.root.after(180_000, tick)

    def _poll_cursor_inbox_once(self) -> None:
        from .gui_busy import can_run_background_tick

        if not can_run_background_tick(
            tool_busy=self._tool_busy, llm_busy=self._llm_busy
        ):
            return

        def work():
            from .integrations.github.inbox import (
                claim_task,
                fetch_inbox,
                format_task_prompt,
                mark_task,
                pending_tasks,
                push_inbox,
                save_inbox_local,
            )

            ok, data = fetch_inbox()
            if not ok or not isinstance(data, dict):
                return None
            pending = pending_tasks(data)
            if not pending:
                return None
            task = pending[0]
            # Claim сразу, чтобы через 3 мин не стартанула вторая копия.
            tid = str(task.get("id") or "")
            if tid and claim_task(data, tid):
                save_inbox_local(data)
                try:
                    push_inbox(data, message=f"Viu: claim {tid}")
                except Exception:  # noqa: BLE001
                    pass
            # Прямой инструмент — без Ollama (таймауты LLM не блокируют пайплайн).
            direct = str(task.get("direct_tool") or "").strip()
            if direct:
                return {"mode": "direct", "task": task, "inbox": data}
            return {"mode": "agent", "prompt": format_task_prompt(task), "task_id": tid, "inbox": data}

        def done(result) -> None:
            from .gui_busy import can_run_background_tick

            if isinstance(result, Exception) or not result:
                return
            if not can_run_background_tick(
                tool_busy=self._tool_busy, llm_busy=self._llm_busy
            ):
                return
            if result.get("mode") == "direct":
                self._run_direct_inbox_task(result["task"], result["inbox"])
                return
            self._append(
                "система",
                "📥 Задача от Cursor — выполняю сама (без кнопок).",
                tag="sys",
            )
            self._run_agent_task(result["prompt"], via_telegram=True)

        self._run_bg(work, done)

    def _run_direct_inbox_task(self, task: dict, inbox: dict) -> None:
        """Выполнить tool из inbox без LLM — отчёт в Telegram/чат + complete."""
        from .escalate import classify_direct_status, escalate_failure
        from .integrations.github.inbox import (
            mark_task,
            push_inbox,
            save_inbox_local,
        )

        tid = str(task.get("id") or "")
        tool_name = str(task.get("direct_tool") or "").strip()
        tool_args = task.get("direct_args") if isinstance(task.get("direct_args"), dict) else {}
        self._append(
            "система",
            f"📥 Cursor → `{tool_name}` (без Ollama, id={tid})",
            tag="sys",
        )
        self._set_tool_busy(True)

        def work():
            # Уже claimed в poll — не claim повторно.
            tool = self.agent.registry.get(tool_name)
            if tool is None:
                status = "blocked"
                body = f"Нет инструмента `{tool_name}`"
                mark_task(inbox, tid, status=status, result=body)
                save_inbox_local(inbox)
                push_inbox(inbox, message=f"Viu: task {tid} → {status}")
                _, esc = escalate_failure(
                    self.agent.ctx,
                    tool_name=tool_name or "missing_tool",
                    error_text=body,
                    task_id=tid,
                )
                return False, body + "\n\n" + esc

            ctx = self.agent.ctx
            res = tool.run(tool_args or {}, ctx)
            status = classify_direct_status(tool_name, res.ok, res.content)
            body = res.content

            if status == "blocked":
                _, esc = escalate_failure(
                    ctx,
                    tool_name=tool_name,
                    error_text=res.content,
                    task_id=tid,
                )
                body = res.content + "\n\n--- escalate ---\n" + esc

            mark_task(inbox, tid, status=status, result=body[:3500])
            save_inbox_local(inbox)
            push_ok, push_msg = push_inbox(inbox, message=f"Viu: task {tid} → {status}")
            if not push_ok:
                body += f"\n\n(inbox push: {push_msg})"

            if status == "done":
                try:
                    from .integrations.github.handoff import append_handoff, push_handoff

                    append_handoff(
                        f"direct `{tool_name}` → {status}",
                        body[:6000],
                        author="Viu",
                    )
                    push_handoff(message=f"Viu: {tid} {status}")
                except Exception as exc:  # noqa: BLE001
                    body += f"\n\nhandoff: {exc}"

            return status == "done", body

        def done(result) -> None:
            self._set_tool_busy(False)
            if isinstance(result, Exception):
                self._append("ошибка", str(result), tag="err")
                self._telegram_notify_error(str(result))
                return
            ok, text = result
            self._append("Вью", text, tag="tool" if ok else "err")
            if ok:
                self._telegram_notify_done(text[:1500])
            else:
                self._telegram_notify_error(text[:1500])

        self._run_bg(work, done)

    # ---------- фоновые сервисы ----------

    def _start_anim_watcher(self) -> None:
        cfg = self.agent.config
        if not cfg.unity_project:
            return
        interval = cfg.unity_anim_scan_sec
        self._anim_watcher = AnimationFolderWatcher(
            cfg,
            interval_sec=interval,
            on_notify=lambda msg: self._queue.put(("step", f"[анимации] {msg}")),
        )
        self._anim_watcher.start()
        self._append(
            "система",
            f"Автоскан Animations/ каждые {int(interval)}с",
            tag="sys",
        )

    def _check_updates_async(self, force: bool = False, apply: bool = False) -> None:
        auto = os.environ.get("VIU_AUTO_UPDATE", "1") == "1"
        if not auto and not force and not apply:
            return
        if apply:
            self._apply_update_confirmed()
            return
        self._append("система", "Проверка обновлений…", tag="sys")

        def work():
            branch = self.agent.config.update_branch
            return check_for_update(branch=branch)

        def done(result):
            if isinstance(result, Exception):
                self._append("ошибка", str(result), tag="err")
                return
            lines = [result.message]
            if result.behind:
                lines.append(f"Отстаём на {result.behind} коммит(ов).")
            if result.has_updates and not usable_git_root():
                lines.append("Нажми кнопку «Обновить Вью».")
            self._append("система", "\n".join(lines), tag="sys")
            if not result.has_updates and stamp_changed_since(self._boot_sha):
                self._append(
                    "система",
                    "На диске новая версия — перезапуск через 2 с…",
                    tag="sys",
                )
                self.root.after(2000, self._restart)

        self._run_bg(work, done)

    def _apply_update_confirmed(self) -> None:
        if not messagebox.askyesno(
            "Обновление Viu",
            "Скачать/применить последнюю версию с GitHub?\n"
            "(без git — zip поверх папки; .viu не трогаем)",
        ):
            return
        self._append("система", "Обновление…", tag="sys")
        self._set_busy(True)

        def work():
            branch = self.agent.config.update_branch
            hard = os.environ.get("VIU_UPDATE_RESET", "0") == "1"
            result = apply_update_smart(branch=branch, hard_reset=hard)
            if result.updated:
                ok, pip_msg = install_package()
                result.message += f"\n{pip_msg}" if ok else f"\n⚠ {pip_msg}"
            return result

        def done(result):
            self._set_busy(False)
            if isinstance(result, Exception):
                self._append("ошибка", str(result), tag="err")
                return
            self._append("система", result.message, tag="sys")
            if result.updated:
                self._append("система", "Перезапуск через 2 с…", tag="sys")
                self.root.after(2000, self._restart)

        self._run_bg(work, done)

    def _install_deps(self) -> None:
        self._append("система", "pip install -e . …", tag="sys")
        self._set_busy(True)

        def work():
            return install_package()

        def done(result):
            self._set_busy(False)
            if isinstance(result, Exception):
                self._append("ошибка", str(result), tag="err")
                return
            ok, msg = result
            self._append("система", msg, tag="sys" if ok else "err")

        self._run_bg(work, done)

    def _schedule_auto_update(self) -> None:
        if self._auto_update_job:
            self.root.after_cancel(self._auto_update_job)
            self._auto_update_job = None
        minutes = get_update_interval_min(self.agent.config)
        if minutes <= 0:
            return

        def tick():
            self._periodic_auto_update()
            self._auto_update_job = self.root.after(minutes * 60_000, tick)

        self._auto_update_job = self.root.after(minutes * 60_000, tick)

    def _periodic_auto_update(self) -> None:
        """Тихая проверка GitHub; при новой версии — zip/git + pip + рестарт."""
        if os.environ.get("VIU_AUTO_UPDATE", "1") != "1":
            return
        if self._tool_busy or self._llm_busy:
            return

        def work():
            return auto_update_on_start(
                branch=self.agent.config.update_branch,
                allow_zip=True,
            )

        def done(result):
            if isinstance(result, Exception):
                return
            if result.updated:
                self._append(
                    "система",
                    f"Автообновление: {result.message}",
                    tag="sys",
                )
                self.root.after(1500, self._restart)
            elif result.has_updates and not result.updated:
                self._append("система", result.message, tag="sys")

        self._run_bg(work, done)

    def _check_updates_on_start(self) -> None:
        """Тихая проверка при старте: SHA на GitHub vs package_sha → zip/git + рестарт."""
        if os.environ.get("VIU_AUTO_UPDATE", "1") != "1":
            return
        self._append("система", "Проверка обновлений…", tag="sys")

        def work():
            return auto_update_on_start(
                branch=self.agent.config.update_branch,
                allow_zip=True,
            )

        def done(result):
            if isinstance(result, Exception):
                return
            self._append("система", result.message, tag="sys")
            if result.updated or stamp_changed_since(self._boot_sha):
                self._append("система", "Перезапуск…", tag="sys")
                self.root.after(1500, self._restart)

        self._run_bg(work, done)

    def _restart(self) -> None:
        try:
            set_window_geometry(self.agent.config, self.root.geometry())
        except tk.TclError:
            pass
        if self._telegram is not None:
            try:
                self._telegram.stop()
            except Exception:  # noqa: BLE001
                pass
        if getattr(self, "_anim_watcher", None) is not None:
            try:
                self._anim_watcher.stop()
            except Exception:  # noqa: BLE001
                pass
        release_single_instance()
        root = package_root()
        log_path = root / "viu_startup.log"
        try:
            prev = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            log_path.write_text(
                prev + f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} relaunch from GUI\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        try:
            # Тихий pythonw + лог — без чёрных окон relaunch.cmd / python.exe.
            relaunch_gui()
        except OSError as exc:
            messagebox.showerror("Вью", f"Не удалось перезапустить: {exc}")
            return
        try:
            self.root.quit()
        except tk.TclError:
            pass
        os._exit(0)

    # ---------- вывод ----------

    def _ensure_anim_barn_reminder(self) -> None:
        """Пока Ден на работе: через ~10 сообщений напомнить про анимации и сарай."""
        try:
            from .reminders import list_pending, schedule

            if any(i.get("tag") == "anim_barn" for i in list_pending(self.agent.config)):
                return
            ok, msg = schedule(
                self.agent.config,
                "Дома: скачай анимации Mixamo (Female Walk и др.) и поправь сарай "
                "(docs/WALK_FEET_FIX.md, docs/BARN_EDIT_STEPS.md). "
                "Пока ты был на работе — ComfyUI уже встраивается во Вью.",
                after_user_messages=10,
                tag="anim_barn",
            )
            if ok:
                self._append("система", msg, tag="sys")
        except OSError:
            pass

    def _append(self, who: str, text: str, tag: str | None = None) -> None:
        # Не дублировать одинаковый текст подряд (два окна редактора / двойной клик).
        if who == "Вью" and self._chat_history:
            prev = self._chat_history[-1]
            if prev == f"{who}: {text[:400]}":
                return
        tag = tag or {"ты": "you", "Вью": "viu", "ошибка": "err", "система": "sys"}.get(
            who, "step"
        )
        line = f"{who}: {text}\n"
        self.output.insert("end", line, tag)
        self.output.see("end")
        if who in ("ты", "Вью") and not text.startswith("["):
            self._chat_history.append(f"{who}: {text[:400]}")
        # Не писать assistant в _llm_turns здесь — иначе final ещё раз дублирует
        # историю и модель повторяет сама себя («два процесса»).
        if who == "ты":
            try:
                from .reminders import on_user_message

                for remind in on_user_message(self.agent.config):
                    self.output.insert(
                        "end",
                        f"система: ⏰ Напоминание: {remind}\n",
                        "sys",
                    )
                    self.output.see("end")
            except OSError:
                pass
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {line}")
        except OSError:
            pass

    def _clear_output(self) -> None:
        self.output.delete("1.0", "end")

    def _open_log_dir(self) -> None:
        folder = str(self.log_path.parent)
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", folder])
        except OSError:
            messagebox.showinfo("Логи", f"Папка логов:\n{folder}")

    def _make_shortcut(self) -> None:
        if os.name != "nt":
            self._append("система", "Ярлык создаётся только на Windows.", tag="sys")
            return
        root = find_git_root() or Path(__file__).resolve().parent.parent
        target = root / "Viu.cmd"
        icon = root / "assets" / "viu_icon.ico"
        ps = (
            "$d=[Environment]::GetFolderPath('Desktop');"
            "$n=-join([char]0x0412,[char]0x044C,[char]0x044E);"
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
            "(Join-Path $d ($n+'.lnk')));"
            f"$s.TargetPath='{target}';$s.WorkingDirectory='{root}';"
            f"$s.IconLocation='{icon}';$s.Description='Viu - Anabarra';$s.Save()"
        )
        try:
            subprocess.run(  # noqa: S603
                ["powershell", "-NoProfile", "-Command", ps],
                cwd=str(root),
                capture_output=True,
                timeout=30,
            )
            self._append("система", "Ярлык «Вью» создан на рабочем столе.", tag="sys")
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._append("ошибка", f"Не удалось создать ярлык: {exc}", tag="err")

    def run(self) -> None:
        self.root.mainloop()


# Единственный экземпляр окна: держим сокет на локальном порту.
_INSTANCE_PORT = 47615
_instance_sock = None


def release_single_instance() -> None:
    """Освободить порт единственного экземпляра перед relaunch."""
    global _instance_sock
    if _instance_sock is not None:
        try:
            _instance_sock.close()
        except OSError:
            pass
        _instance_sock = None


def build_relaunch_command(cwd: Path | None = None) -> tuple[list[str], str]:
    """Команда перезапуска GUI (run_gui.pyw или python -m viu gui)."""
    root = cwd or usable_git_root() or package_root()
    workdir = str(root)
    exe = sys.executable
    # Windows: pythonw без консоли; ошибки — в viu_startup.log / MessageBox.
    # VIU_SHOW_CONSOLE=1 оставляет python.exe для отладки.
    if os.name == "nt" and not os.environ.get("VIU_SHOW_CONSOLE"):
        if exe.lower().endswith("python.exe"):
            pyw = Path(exe).with_name("pythonw.exe")
            if pyw.is_file():
                exe = str(pyw)
    run_gui = root / "run_gui.pyw"
    if run_gui.is_file():
        return [exe, str(run_gui)], workdir
    return [exe, "-m", "viu", "gui"], workdir


def relaunch_gui() -> None:
    """Запустить новый процесс Viu (после release_single_instance)."""
    # Дать старому процессу отпустить single-instance порт.
    time.sleep(1.2)
    cmd, workdir = build_relaunch_command()
    kwargs: dict = {"cwd": workdir}
    if os.name == "nt":
        create_no_window = 0x08000000
        new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs["creationflags"] = create_no_window | new_group
        log_path = Path(workdir) / "viu_startup.log"
        try:
            log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
            kwargs["stdout"] = log_f
            kwargs["stderr"] = subprocess.STDOUT
        except OSError:
            pass
    subprocess.Popen(cmd, **kwargs)  # noqa: S603


def acquire_single_instance(port: int = _INSTANCE_PORT):
    """Возвращает сокет-замок или None, если Вью уже открыта."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == "nt":
        # На Windows SO_REUSEADDR разрешает ДВА процесса на одном порту (не то,
        # что на Linux). Нужен SO_EXCLUSIVEADDRUSE, иначе замок не держит —
        # открывается второе окно Вью.
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        except (AttributeError, OSError):
            pass
    else:
        # На Linux/macOS SO_REUSEADDR избавляет от TIME_WAIT при перезапуске,
        # но НЕ даёт второму процессу занять активно слушающий порт.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
    except OSError:
        sock.close()
        return None
    return sock


def main() -> int:
    global _instance_sock
    root_dir = Path(__file__).resolve().parent.parent
    status_path = root_dir / ".viu_launch_status"
    started_path = root_dir / ".viu_gui_started"

    def _status(msg: str) -> None:
        try:
            status_path.write_text(msg, encoding="utf-8")
        except OSError:
            pass

    def _mark_started() -> None:
        try:
            started_path.write_text("ok\n", encoding="utf-8")
            _status("running")
        except OSError:
            pass

    _status("locking")
    _instance_sock = acquire_single_instance()
    if _instance_sock is None:
        _status("already_running")
        try:
            (root_dir / "viu_startup.log").write_text(
                "Вью уже запущена (порт 47615 занят).\n"
                "Найди окно на панели задач или запусти fix_viu_lock.bat\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                "Вью уже открыта",
                "Окно Вью уже запущено. Найди его на панели задач.\n"
                "Если окна не видно — запусти fix_viu_lock.bat "
                "или заверши python/pythonw в Диспетчере задач.",
            )
            root.destroy()
        except Exception:  # noqa: BLE001
            pass
        return 0

    try:
        _status("creating_gui")
        _mark_started()
        app = ViuGUI()
        app.run()
        return 0
    except Exception as exc:  # noqa: BLE001
        import traceback

        _status("crash")
        log = root_dir / "viu_startup.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Вью — ошибка",
                f"{exc}\n\nЛог: {log}",
            )
            root.destroy()
        except Exception:  # noqa: BLE001
            pass
        return 1
