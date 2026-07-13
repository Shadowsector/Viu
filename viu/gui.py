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
from .integrations.unity.watcher import AnimationFolderWatcher
from .runtime_settings import get_update_interval_min, get_window_geometry, set_window_geometry
from .updater import (
    apply_update_smart,
    auto_update_on_start,
    check_for_update,
    cleanup_obsolete,
    cleanup_broken_git,
    find_git_root,
    install_package,
    package_root,
    read_local_sha,
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
        self._busy = False
        self._action_buttons: list[tuple[str, ttk.Button]] = []
        self._action_group_boxes: dict[str, ttk.LabelFrame] = {}
        self._sidebar_stage_label: ttk.Label | None = None
        self._auto_update_job: str | None = None
        self._telegram = None
        self._telegram_waiting_reply = False
        self._last_via_telegram = False
        self._heartbeat_job: str | None = None
        self._heartbeat_notify = False
        self._lab_job: str | None = None
        self._chat_history: deque[str] = deque(maxlen=16)
        self._llm_turns: deque[dict[str, str]] = deque(maxlen=14)
        self._boot_sha = read_local_sha(package_root())
        self._geometry_save_job: str | None = None

        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_path = self.agent.config.data_dir / "logs" / f"chat_{stamp}.txt"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Тихо убираем старые батники из корня (наследие прошлых версий).
        try:
            removed = cleanup_obsolete()
        except Exception:  # noqa: BLE001
            removed = []

        self._build_ui()
        self._append("система", f"{version_label()}. Модель: {self.agent.llm.name}.")
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
        self._refresh_status()
        self._schedule_auto_update()
        self._start_telegram()
        self._schedule_heartbeat()
        self._schedule_cursor_inbox()
        self._schedule_lab()
        try:
            from .vision import ensure_vision

            ensure_vision(self.agent.config)
        except OSError:
            pass
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
        self.root.title("Вью — Анабарра")
        saved_geom = get_window_geometry(self.agent.config)
        self.root.geometry(saved_geom if saved_geom else _GUI_DEFAULT_GEOMETRY)
        self.root.minsize(_GUI_MIN_WIDTH, _GUI_MIN_HEIGHT)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        try:
            if _ICON.exists():
                self.root.iconbitmap(default=str(_ICON))
        except tk.TclError:
            pass

        self._build_menu()
        self._build_top_status()

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
        """Строка статуса как у Mia: Ollama, Unity, версия."""
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=(6, 0))
        self.top_status_var = tk.StringVar(value="…")
        ttk.Label(bar, textvariable=self.top_status_var, font=("Segoe UI", 9)).pack(
            side="left", anchor="w"
        )

    def _toggle_presence(self) -> None:
        from .decision_queue import flush_prompt_for_home
        from .presence import is_away, presence_label, toggle_presence

        mode = toggle_presence(self.agent.config)
        label = presence_label(self.agent.config)
        self._append("ты", "[Режим присутствия]")
        self._append("Вью", label, tag="sys")
        self._refresh_presence_button()
        self._refresh_status()
        if mode == "home":
            flush = flush_prompt_for_home(self.agent.config)
            if flush:
                self._append("Вью", flush, tag="tool")
                self._telegram_notify_chat(flush[:1500])
        else:
            self._append(
                "система",
                "Автономный режим: inbox/оверлей сама; вопросы копятся в «Очередь вопросов».",
                tag="sys",
            )
            self.root.after(2000, lambda: self._lab_tick(auto=True))

    def _show_decision_queue(self) -> None:
        from .decision_queue import render_open

        self._append("ты", "[Очередь вопросов]")
        self._append("Вью", render_open(self.agent.config), tag="tool")

    def _refresh_presence_button(self) -> None:
        from .presence import is_away

        away = is_away(self.agent.config)
        text = "Режим: меня нет (автономно)" if away else "Режим: я дома (с вопросами)"
        for aid, btn in self._action_buttons:
            if aid == "presence_toggle":
                btn.config(text=text)
                break

    def _refresh_status(self) -> None:
        cfg = self.agent.config

        def compute() -> str:
            from .decision_queue import count_open
            from .presence import is_away

            ollama = "Ollama ✓" if ollama_available(cfg.base_url) else "Ollama ✗"
            unity = Path(cfg.unity_project).name if cfg.unity_project else "Unity —"
            git = "git" if usable_git_root() else "zip"
            mode = "автономно" if is_away(cfg) else "дома"
            qn = count_open(cfg)
            q = f" | вопросов: {qn}" if qn else ""
            return (
                f"{ollama}  |  {mode}{q}  |  {unity}  |  {version_label()} ({git})  |  "
                f"Модель: {self.agent.llm.name}"
            )

        self._run_bg(compute, self._set_top_status)
        self.root.after(5000, self._refresh_status)

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
            text="Чат справа — свободная задача.\nEnter — отправить.",
            wraplength=240,
            justify="left",
            font=("Segoe UI", 9),
        )
        chat_hint.pack(anchor="w", padx=10, pady=(0, 8))

    def _build_chat(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.pack(side="left", fill="both", expand=True)

        self.output = scrolledtext.ScrolledText(
            frame,
            wrap="word",
            font=("Segoe UI", 11),
            background="#1e1e1e",
            foreground="#e6e6e6",
            insertbackground="#e6e6e6",
            padx=8,
            pady=8,
        )
        self.output.pack(fill="both", expand=True, padx=(4, 8), pady=(8, 4))
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

        self.send_btn = ttk.Button(bottom, text="Отправить", width=14, command=self._on_send)
        self.send_btn.pack(side="right", fill="y", padx=(6, 0))

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

        self.root.config(menu=menubar)

    def _attach_tooltip(self, widget: tk.Widget, text: str) -> None:
        tip: dict[str, Optional[tk.Toplevel]] = {"win": None}

        def show(_event=None):
            if tip["win"] is not None:
                return
            tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{widget.winfo_rootx() + 20}+{widget.winfo_rooty() + 24}")
            lbl = ttk.Label(tw, text=text, padding=6, relief="solid")
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
        widget.bind("<Control-KeyPress>", self._ctrl_shortcuts)

    def _bind_clipboard(self, widget: tk.Widget) -> None:
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
            widget.bind(seq, lambda e, v=virt: (e.widget.event_generate(v), "break"))

    # ---------- события ----------

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
        if event.state & 0x0004:
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

    def _on_send(self) -> None:
        if self._busy:
            return
        text = self.entry.get("1.0", "end-1c").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        if text.lower() in ("exit", "quit", "выход", "пока"):
            self.root.destroy()
            return
        from .integrations.telegram.router import route_user_message

        mode = route_user_message(text, waiting_for_user=self._telegram_waiting_reply)
        if mode == "work":
            self._run_agent_task(text)
        else:
            self._run_agent_reflect(text)

    def _on_action(self, action: GuiAction) -> None:
        if self._busy:
            return
        from .lab.controller import lab_controller

        lab_controller.request_operator_priority(f"кнопка: {action.label}")
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
        if action.tool == "__next_step__":
            self._run_next_step()
            return
        if action.tool == "__lab_start__":
            self._lab_start_action()
            return
        if action.tool == "__lab_rate__":
            self._open_lab_rating()
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

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.send_btn.config(state=state, text="Думаю…" if busy else "Отправить")
        for _aid, btn in self._action_buttons:
            btn.config(state=state)
        ver = version_label()
        self.status.config(
            text=("Вью думает…" if busy else f"{ver} | {self.agent.llm.name}")
        )

    def _run_tool_chain(self, action: GuiAction) -> None:
        self._append("ты", f"[{action.label}]")
        self._set_busy(True)
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
            self._queue.put(("error", f"{action.label}: {exc}"))

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
        self._set_busy(True)

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
            self._set_busy(False)
            if isinstance(result, Exception):
                self._append("ошибка", str(result), tag="err")
                return
            self._append("Вью", result, tag="tool")

        self._run_bg(work, done)

    def _refresh_action_visibility(self) -> None:
        ctx = get_pipeline_context(self.agent.config)
        if self._sidebar_stage_label is not None:
            self._sidebar_stage_label.config(text=ctx.step_label)
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
        self._run_tool(tool, args, label="Следующий шаг")
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
        self._set_busy(True)

        def work():
            from .drop_router import accept_single_animation

            return accept_single_animation(self.agent.config)

        def done(result) -> None:
            self._set_busy(False)
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
        self._set_busy(True)

        def work():
            from .support import collect_support_bundle, upload_bundle_to_gist

            bundle = collect_support_bundle(self.agent.config)
            ok, msg = upload_bundle_to_gist(bundle, description="Viu logs — Анабарра")
            return bundle, ok, msg

        def done(result):
            self._set_busy(False)
            if isinstance(result, Exception):
                self._append("ошибка", str(result), tag="err")
                return
            bundle, ok, msg = result
            self._append("Вью", f"Логи собраны: {bundle}\n{msg}", tag="tool")
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
            return update_viu_full(branch=self.agent.config.update_branch)

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

        cid = tg_settings.chat_id(cfg)
        return (
            f"{version_label()}\n"
            f"Ollama: {'ok' if ollama_available() else 'нет'}\n"
            f"Unity: {unity}\n"
            f"Занята: {'да' if self._busy else 'нет'}\n"
            f"Telegram chat: {cid or 'не привязан'} ({chat})\n"
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

        self._append("ты", f"[Telegram] {text}")
        self._record_llm_turn("user", text)
        if self._busy:
            self._append(
                "система",
                "Вью сейчас занята — ответ из Telegram подождёт.",
                tag="sys",
            )
            return
        mode = route_telegram_message(text, waiting_for_user=self._telegram_waiting_reply)
        self._telegram_waiting_reply = False
        if mode == "work":
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

    def _run_tool(self, name: str, args: dict, label: str = "") -> None:
        title = label or name
        self._append("ты", f"[{title}]")
        self._set_busy(True)
        threading.Thread(
            target=self._tool_worker,
            args=(name, args, title),
            daemon=True,
        ).start()

    def _tool_worker(self, name: str, args: dict, title: str) -> None:
        try:
            tool = self.agent.registry.get(name)
            if tool is None:
                self._queue.put(("error", f"Инструмент {name!r} не найден."))
                return
            result = tool.run(args, self.agent.ctx)
            prefix = "OK" if result.ok else "ОШИБКА"
            self._queue.put(("tool", f"[{title}] {prefix}\n{result.content}"))
        except Exception as exc:  # noqa: BLE001
            self._queue.put(("error", f"{title}: {exc}"))

    def _run_agent_task(self, task: str, *, via_telegram: bool = False) -> None:
        if not via_telegram:
            self._append("ты", task)
        self._set_busy(True)
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
        self._llm_turns.append({"role": role, "content": clean[:600]})

    def _run_agent_reflect(self, task: str, *, via_telegram: bool = False, heartbeat: bool = False) -> None:
        if not via_telegram and not heartbeat:
            self._append("ты", task)
            self._record_llm_turn("user", task)
        self._set_busy(True)
        self._last_via_telegram = via_telegram or heartbeat
        if heartbeat:
            history: list[dict[str, str]] = []
        else:
            hist = self._llm_history()
            history = hist[:-1] if hist and hist[-1].get("role") == "user" else hist
        threading.Thread(
            target=self._agent_worker,
            args=(task, "reflect", history, heartbeat),
            daemon=True,
        ).start()

    def _agent_worker(
        self,
        task: str,
        mode: str,
        history: list | None = None,
        heartbeat: bool = False,
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
                )
            else:
                result = self.agent.run(task, on_step=on_step)
            self._queue.put(
                (
                    "final",
                    result.final,
                    result.waiting_for_user,
                    result.chat_only,
                    result.inner_thought,
                    not result.tool_errors,
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
                else:
                    continue
                if kind == "step":
                    self._append("шаг", text, tag="step")
                elif kind == "thinking":
                    self._append("размышляет", text, tag="step")
                elif kind == "tool":
                    self._append("Вью", text, tag="tool")
                    self._set_busy(False)
                    from .lab.controller import lab_controller

                    lab_controller.clear_operator_priority()
                    self._refresh_action_visibility()
                    self._maybe_prompt_lab_rating()
                    if text.startswith("[") and "ОШИБКА" in text:
                        self._telegram_notify_error(text)
                elif kind == "final":
                    if inner_thought and not self._last_via_telegram:
                        preview = inner_thought[:280] + ("…" if len(inner_thought) > 280 else "")
                        self._append("размышляет", preview, tag="step")
                    self._append("Вью", text, tag="viu")
                    self._set_busy(False)
                    if waiting:
                        self._telegram_waiting_reply = True
                        self._telegram_notify_question(text)
                    elif chat_only and self._last_via_telegram:
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
                    self._set_busy(False)
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
            if not self._busy:
                self._run_heartbeat()
            self._heartbeat_job = self.root.after(minutes * 60_000, tick)

        self._heartbeat_job = self.root.after(minutes * 60_000, tick)

    def _run_heartbeat(self) -> None:
        from .prompts.reflect_mode import HEARTBEAT_TASK
        from .quiet_hours import in_quiet_hours
        from .vision import ensure_vision

        if in_quiet_hours(self.agent.config):
            return

        ensure_vision(self.agent.config)
        self._append("система", "⏰ Вью проснулась по таймеру — смотрю, что можно сделать.", tag="sys")
        self._last_via_telegram = True
        self._heartbeat_notify = True
        self._run_agent_reflect("", heartbeat=True)

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
        if self._busy:
            return
        from .presence import is_away

        if auto and not is_away(self.agent.config):
            return
        from .lab.cascadeur_pipeline import CASCADEUR_TOPIC
        from .lab.session import load_session

        session = load_session(self.agent.config, CASCADEUR_TOPIC)
        if session is None:
            if not auto:
                self._lab_start_action()
            return
        if session.status == "awaiting_rating":
            self._maybe_prompt_lab_rating()
            return
        if session.status in ("completed", "idle"):
            if auto:
                return
            self._lab_start_action(reset=True)
            return
        self._run_tool("lab_step", {"topic": CASCADEUR_TOPIC}, label="Lab: шаг")

    def _lab_start_action(self, *, reset: bool = False) -> None:
        from .lab.cascadeur_pipeline import CASCADEUR_TOPIC

        self._append("ты", "[Лаборатория: Cascadeur]")
        args: dict = {"topic": CASCADEUR_TOPIC}
        if reset:
            args["reset"] = "1"
        self._run_tool("lab_start", args, label="Лаборатория: Cascadeur")

    def _maybe_prompt_lab_rating(self) -> None:
        from .lab.cascadeur_pipeline import CASCADEUR_TOPIC
        from .lab.session import load_session

        session = load_session(self.agent.config, CASCADEUR_TOPIC)
        if session is None or session.status != "awaiting_rating":
            return
        self._append(
            "система",
            "Lab готова к оценке — «Оценить лабораторию» в Редко.",
            tag="sys",
        )

    def _open_lab_rating(self) -> None:
        from .lab.review_gui import open_lab_rating_review

        def done(ok: bool, msg: str) -> None:
            tag = "tool" if ok else "sys"
            self._append("Вью", msg, tag=tag)

        open_lab_rating_review(self.root, self.agent.config, "cascadeur", on_finished=done)

    def _schedule_cursor_inbox(self) -> None:
        """Раз в несколько минут — забрать задачи Cursor с GitHub и выполнить без Дена."""
        self.root.after(45_000, self._poll_cursor_inbox_once)

        def tick() -> None:
            self._poll_cursor_inbox_once()
            self.root.after(180_000, tick)

        self.root.after(180_000, tick)

    def _poll_cursor_inbox_once(self) -> None:
        if self._busy:
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
            if isinstance(result, Exception) or not result:
                return
            if self._busy:
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
        self._set_busy(True)

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
            self._set_busy(False)
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
            self._check_updates_async(force=True, apply=False)
            self._auto_update_job = self.root.after(minutes * 60_000, tick)

        self._auto_update_job = self.root.after(minutes * 60_000, tick)

    def _check_updates_on_start(self) -> None:
        """Тихая проверка при старте (только git, без zip)."""
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
            if os.name == "nt":
                relaunch = root / "relaunch.cmd"
                if relaunch.is_file():
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    detached = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                    subprocess.Popen(  # noqa: S603
                        ["cmd.exe", "/c", str(relaunch)],
                        cwd=str(root),
                        creationflags=flags | detached,
                    )
                    os._exit(0)
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

    def _append(self, who: str, text: str, tag: str | None = None) -> None:
        tag = tag or {"ты": "you", "Вью": "viu", "ошибка": "err", "система": "sys"}.get(
            who, "step"
        )
        line = f"{who}: {text}\n"
        self.output.insert("end", line, tag)
        self.output.see("end")
        if who in ("ты", "Вью") and not text.startswith("["):
            self._chat_history.append(f"{who}: {text[:400]}")
        if who == "Вью":
            self._record_llm_turn("assistant", text)
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
    if os.name == "nt" and exe.lower().endswith("python.exe"):
        pyw = Path(exe).with_name("pythonw.exe")
        if pyw.is_file():
            exe = str(pyw)
    run_gui = root / "run_gui.pyw"
    if run_gui.is_file():
        return [exe, str(run_gui)], workdir
    return [exe, "-m", "viu", "gui"], workdir


def relaunch_gui() -> None:
    """Запустить новый процесс Viu (после release_single_instance)."""
    cmd, workdir = build_relaunch_command()
    subprocess.Popen(  # noqa: S603
        cmd,
        cwd=workdir,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


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
    _instance_sock = acquire_single_instance()
    if _instance_sock is None:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                "Вью уже открыта",
                "Окно Вью уже запущено. Найди его на панели задач.\n"
                "Если окна не видно — заверши процесс python в Диспетчере задач и запусти снова.",
            )
            root.destroy()
        except Exception:  # noqa: BLE001
            pass
        return 0

    try:
        ViuGUI().run()
        return 0
    except Exception as exc:  # noqa: BLE001
        import traceback

        log = Path(__file__).resolve().parent.parent / "viu_startup.log"
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
