"""Графическое окно Вью (Tkinter) — в стиле обычного Windows-приложения.

Возможности:
* окно с областью диалога и полем ввода;
* копирование/вставка (горячие клавиши и правый клик), работает при любой
  раскладке клавиатуры;
* автоматическое логирование всего диалога в текстовый файл;
* агент работает в фоновом потоке, окно не «зависает».

Tkinter входит в стандартную поставку Python на Windows — ничего доставлять
не нужно.
"""

from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from .agent import Agent
from .config import Config

_ICON = Path(__file__).resolve().parent.parent / "assets" / "viu_icon.ico"
_NAV_KEYS = {"Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next", "Shift_L", "Shift_R"}


class ViuGUI:
    def __init__(self) -> None:
        self.agent = Agent(config=Config())
        self._queue: "queue.Queue" = queue.Queue()
        self._busy = False

        # Файл лога на сессию.
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_path = self.agent.config.data_dir / "logs" / f"chat_{stamp}.txt"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self._build_ui()
        self._append("система", f"Вью готова. Модель: {self.agent.llm.name}. Лог: {self.log_path}")
        self.root.after(100, self._poll_queue)

    # ---------- построение интерфейса ----------

    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("Вью — Анабарра")
        self.root.geometry("880x600")
        self.root.minsize(560, 400)
        try:
            if _ICON.exists():
                self.root.iconbitmap(default=str(_ICON))
        except tk.TclError:
            pass  # на не-Windows .ico может не поддерживаться

        self._build_menu()

        # Диалог.
        self.output = scrolledtext.ScrolledText(
            self.root, wrap="word", font=("Segoe UI", 11), state="normal",
            background="#1e1e1e", foreground="#e6e6e6", insertbackground="#e6e6e6",
            padx=8, pady=8,
        )
        self.output.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self.output.tag_config("you", foreground="#4fc3f7")
        self.output.tag_config("viu", foreground="#a5d6a7")
        self.output.tag_config("step", foreground="#9e9e9e")
        self.output.tag_config("err", foreground="#ef9a9a")
        self.output.tag_config("sys", foreground="#ffcc80")
        self.output.bind("<Key>", self._readonly_guard)
        self._attach_context_menu(self.output)

        # Ввод + кнопка.
        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=8, pady=(0, 8))
        self.entry = tk.Text(bottom, height=3, wrap="word", font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="both", expand=True)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Shift-Return>", lambda e: None)  # перенос строки
        self._attach_context_menu(self.entry)
        self.entry.focus_set()

        self.send_btn = ttk.Button(bottom, text="Отправить", width=14, command=self._on_send)
        self.send_btn.pack(side="right", fill="y", padx=(6, 4))

        # Статус-строка.
        self.status = ttk.Label(self.root, anchor="w", relief="sunken",
                                text=f"Провайдер: {self.agent.llm.name}")
        self.status.pack(fill="x", side="bottom")

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Открыть папку логов", command=self._open_log_dir)
        m_file.add_command(label="Очистить окно", command=self._clear_output)
        m_file.add_separator()
        m_file.add_command(label="Выход", command=self.root.destroy)
        menubar.add_cascade(label="Файл", menu=m_file)

        m_edit = tk.Menu(menubar, tearoff=0)
        m_edit.add_command(label="Копировать", command=lambda: self._edit_event("<<Copy>>"))
        m_edit.add_command(label="Вставить", command=lambda: self._edit_event("<<Paste>>"))
        m_edit.add_command(label="Вырезать", command=lambda: self._edit_event("<<Cut>>"))
        menubar.add_cascade(label="Правка", menu=m_edit)

        self.root.config(menu=menubar)

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
        # Надёжное «выделить всё» независимо от раскладки.
        widget.bind("<Control-KeyPress>", self._ctrl_shortcuts)

    # ---------- обработчики ----------

    def _ctrl_shortcuts(self, event):
        # keycode 'a'/'A' = 38 на большинстве клавиатур; используем keysym и keycode.
        if event.keysym.lower() in ("a", "ф") or event.keycode == 38:
            self._select_all(event.widget)
            return "break"
        return None

    def _select_all(self, widget) -> None:
        try:
            widget.tag_add("sel", "1.0", "end-1c")
        except tk.TclError:
            pass

    def _readonly_guard(self, event):
        """Делает область диалога «только для чтения», но с копированием и навигацией."""
        if event.state & 0x0004:  # зажат Control -> пропускаем (копирование/выделение)
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
        return "break"  # не вставлять перевод строки

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
        self._append("ты", text)
        self._set_busy(True)
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, task: str) -> None:
        def on_step(step):
            if step.kind == "action":
                self._queue.put(("step", f"[{step.tool}] {step.thought}"))
                if step.observation:
                    self._queue.put(("step", "    " + step.observation.replace("\n", "\n    ")))
            elif step.kind == "error":
                self._queue.put(("step", step.observation))

        try:
            result = self.agent.run(task, on_step=on_step)
            self._queue.put(("final", result.final))
        except Exception as exc:  # noqa: BLE001
            self._queue.put(("error", f"{exc}\nПодсказка: запущена ли Ollama? Верна ли модель?"))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, text = self._queue.get_nowait()
                if kind == "step":
                    self._append("шаг", text, tag="step")
                elif kind == "final":
                    self._append("Вью", text, tag="viu")
                    self._set_busy(False)
                elif kind == "error":
                    self._append("ошибка", text, tag="err")
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ---------- вывод и лог ----------

    def _append(self, who: str, text: str, tag: str = None) -> None:
        tag = tag or {"ты": "you", "Вью": "viu", "ошибка": "err", "система": "sys"}.get(who, "step")
        line = f"{who}: {text}\n"
        self.output.insert("end", line, tag)
        self.output.see("end")
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {line}")
        except OSError:
            pass

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_btn.config(state="disabled" if busy else "normal", text="Думаю…" if busy else "Отправить")
        self.status.config(text=("Вью думает…" if busy else f"Провайдер: {self.agent.llm.name}"))

    def _clear_output(self) -> None:
        self.output.delete("1.0", "end")

    def _open_log_dir(self) -> None:
        folder = str(self.log_path.parent)
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except OSError:
            messagebox.showinfo("Логи", f"Папка логов:\n{folder}")

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    ViuGUI().run()
    return 0
