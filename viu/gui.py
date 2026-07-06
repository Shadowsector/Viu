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
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from .agent import Agent
from .config import Config
from .gui_actions import ACTION_GROUPS, GuiAction, actions_by_group
from .integrations.unity.watcher import AnimationFolderWatcher
from .updater import auto_update_on_start, find_git_root, version_label

_ICON = Path(__file__).resolve().parent.parent / "assets" / "viu_icon.ico"
_NAV_KEYS = {"Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next", "Shift_L", "Shift_R"}
_CLIP_KEYS = {"c", "v", "x", "a", "ф", "м", "ч", "a"}


class ViuGUI:
    def __init__(self) -> None:
        self.agent = Agent(config=Config())
        self._queue: queue.Queue = queue.Queue()
        self._busy = False
        self._action_buttons: list[ttk.Button] = []

        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_path = self.agent.config.data_dir / "logs" / f"chat_{stamp}.txt"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self._build_ui()
        self._append("система", f"{version_label()}. Модель: {self.agent.llm.name}.")
        self._append("система", f"Лог: {self.log_path}", tag="sys")
        self._start_anim_watcher()
        self.root.after(100, self._poll_queue)
        self.root.after(300, self._check_updates_async)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("Вью — Анабарра")
        self.root.geometry("1024x680")
        self.root.minsize(760, 480)
        try:
            if _ICON.exists():
                self.root.iconbitmap(default=str(_ICON))
        except tk.TclError:
            pass

        self._build_menu()

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

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, width=220)
        frame.pack(side="left", fill="y", padx=(0, 0))
        frame.pack_propagate(False)

        header = ttk.Label(frame, text="Действия", font=("Segoe UI", 11, "bold"))
        header.pack(anchor="w", padx=10, pady=(10, 6))

        canvas = tk.Canvas(frame, highlightthickness=0, width=210)
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
            for action in actions:
                btn = ttk.Button(
                    box,
                    text=action.label,
                    command=lambda a=action: self._on_action(a),
                )
                btn.pack(fill="x", pady=2)
                self._action_buttons.append(btn)
                if action.hint:
                    self._attach_tooltip(btn, action.hint)

        chat_hint = ttk.Label(
            frame,
            text="Чат справа — свободная задача.\nEnter — отправить.",
            wraplength=200,
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
        m_file.add_command(label="Проверить обновления", command=self._check_updates_async)
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
        self._run_agent_task(text)

    def _on_action(self, action: GuiAction) -> None:
        if self._busy:
            return
        if action.tool == "__clear__":
            self._clear_output()
            return
        if action.tool == "__open_logs__":
            self._open_log_dir()
            return
        if action.tool == "__update__":
            self._check_updates_async(force=True)
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
        for btn in self._action_buttons:
            btn.config(state=state)
        ver = version_label()
        self.status.config(
            text=("Вью думает…" if busy else f"{ver} | {self.agent.llm.name}")
        )

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

    def _run_agent_task(self, task: str) -> None:
        self._append("ты", task)
        self._set_busy(True)
        threading.Thread(target=self._agent_worker, args=(task,), daemon=True).start()

    def _agent_worker(self, task: str) -> None:
        def on_step(step):
            if step.kind == "action":
                self._queue.put(("step", f"[{step.tool}] {step.thought}"))
                if step.observation:
                    self._queue.put(
                        ("step", "    " + step.observation.replace("\n", "\n    "))
                    )
            elif step.kind == "error":
                self._queue.put(("step", step.observation))

        try:
            result = self.agent.run(task, on_step=on_step)
            self._queue.put(("final", result.final))
        except Exception as exc:  # noqa: BLE001
            self._queue.put(("error", f"{exc}\nПодсказка: запущена ли Ollama?"))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, text = self._queue.get_nowait()
                if kind == "step":
                    self._append("шаг", text, tag="step")
                elif kind == "tool":
                    self._append("Вью", text, tag="tool")
                    self._set_busy(False)
                elif kind == "final":
                    self._append("Вью", text, tag="viu")
                    self._set_busy(False)
                elif kind == "error":
                    self._append("ошибка", text, tag="err")
                    self._set_busy(False)
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

    def _check_updates_async(self, force: bool = False) -> None:
        if self._busy and not force:
            return
        auto = os.environ.get("VIU_AUTO_UPDATE", "1") == "1"
        if not auto and not force:
            return
        self._append("система", "Проверка обновлений…", tag="sys")

        def work():
            try:
                branch = self.agent.config.update_branch
                result = auto_update_on_start(branch=branch)
                lines = [result.message]
                if result.local_ref:
                    lines.append(f"Локально: {result.local_ref}")
                if result.remote_ref and result.remote_ref != result.local_ref:
                    lines.append(f"На сервере: {result.remote_ref}")
                self._queue.put(("sys", "\n".join(lines)))
                if result.updated:
                    self._queue.put(("sys", "Обновлено. Перезапуск через секунду…"))
                    self._queue.put(("update_done", "restart"))
                else:
                    self._queue.put(("update_done", "ok"))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("error", f"Обновление: {exc}"))
                self._queue.put(("update_done", "ok"))

        threading.Thread(target=work, daemon=True).start()

    def _restart(self) -> None:
        root = find_git_root()
        cwd = str(root) if root else str(Path(__file__).resolve().parent.parent)
        exe = sys.executable
        # pythonw на Windows — без консоли
        if os.name == "nt" and exe.lower().endswith("python.exe"):
            pyw = Path(exe).with_name("pythonw.exe")
            if pyw.is_file():
                exe = str(pyw)
        try:
            subprocess.Popen(  # noqa: S603
                [exe, "-m", "viu", "gui"],
                cwd=cwd,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as exc:
            messagebox.showerror("Вью", f"Не удалось перезапустить: {exc}")
            return
        self.root.destroy()

    # ---------- вывод ----------

    def _append(self, who: str, text: str, tag: str | None = None) -> None:
        tag = tag or {"ты": "you", "Вью": "viu", "ошибка": "err", "система": "sys"}.get(
            who, "step"
        )
        line = f"{who}: {text}\n"
        self.output.insert("end", line, tag)
        self.output.see("end")
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

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
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
        except Exception:
            pass
        return 1
