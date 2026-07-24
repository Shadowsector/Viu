"""Единое окно: статус Comfy MoCap, запуск, промпт и LoRA без команд в Telegram."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Callable, List, Optional

from ...config import Config
from ...lab.comfy_pipeline import COMFY_TOPIC, apply_lora_pick_decision
from ...lab.session import load_session, new_session, save_session
from .lora import load_index, scan_loras, spec_to_dict, specs_from_indices
from .pipeline_status import comfy_pipeline_status, comfy_pipeline_status_brief


@dataclass
class ComfyStudioCallbacks:
    on_ensure_comfy: Callable[[], None]
    on_mocap_shoot: Callable[[], None]
    on_edit_prompt: Callable[[], None]
    on_pick_clips: Callable[[], None]
    on_open_browser: Callable[[], None]
    on_shot_queue: Optional[Callable[[], None]] = None


def _strip_md_bold(text: str) -> str:
    return text.replace("**", "")


def apply_lora_from_indices(config: Config, indices: List[int]) -> str:
    """Текущий шаг LoRA или пресет для следующей съёмки."""
    session = load_session(config, COMFY_TOPIC)
    if session is None:
        session = new_session(COMFY_TOPIC)
        save_session(config, session)
    scan_loras(config)
    if session.status == "awaiting_lora_pick":
        return apply_lora_pick_decision(config, session, indices)
    specs = specs_from_indices(config, indices)
    session.meta["lora_last_pick"] = list(indices)
    session.meta["selected_loras"] = [spec_to_dict(s) for s in specs]
    save_session(config, session)
    if not specs:
        return "Пресет LoRA: без LoRA (чистый Wan) — применю на следующем шаге выбора."
    names = ", ".join(s.file for s in specs)
    return f"Пресет LoRA сохранён: {names}"


def open_comfy_studio(
    master: tk.Misc,
    config: Config,
    callbacks: ComfyStudioCallbacks,
    *,
    on_finished: Optional[Callable[[], None]] = None,
) -> None:
    win = tk.Toplevel(master)
    win.title("Студия Comfy — MoCap")
    win.geometry("920x720")
    win.minsize(760, 560)

    body = ttk.Frame(win, padding=10)
    body.pack(fill="both", expand=True)

    brief_var = tk.StringVar(value="")
    ttk.Label(body, textvariable=brief_var, font=("Segoe UI", 11, "bold")).pack(
        anchor="w", pady=(0, 6)
    )

    ttk.Label(
        body,
        text=(
            "Съёмка и оценка видео — здесь и в кнопках ниже. "
            "«Оценить видео» = выбор лучшего mp4 (не Cascadeur lab). "
            "«Очередь анимаций» = план кадров наперёд перед уходом на работу. "
            "Браузер :8188 — только монитор сервера."
        ),
        wraplength=860,
    ).pack(anchor="w", pady=(0, 8))

    status_txt = tk.Text(body, height=14, wrap="word", font=("Consolas", 9))
    status_txt.pack(fill="both", expand=True)
    status_txt.configure(state="disabled")

    btn_row = ttk.Frame(body)
    btn_row.pack(fill="x", pady=(8, 4))

    lora_frame = ttk.LabelFrame(body, text="LoRA для текущего / следующего пула", padding=8)
    lora_frame.pack(fill="both", expand=True, pady=(4, 0))

    lora_list = tk.Listbox(lora_frame, selectmode=tk.EXTENDED, height=8, font=("Consolas", 9))
    lora_scroll = ttk.Scrollbar(lora_frame, orient="vertical", command=lora_list.yview)
    lora_list.configure(yscrollcommand=lora_scroll.set)
    lora_list.pack(side="left", fill="both", expand=True)
    lora_scroll.pack(side="right", fill="y")

    lora_btns = ttk.Frame(lora_frame)
    lora_btns.pack(fill="x", pady=(6, 0))

    index_by_row: List[int] = []

    def reload_lora_list() -> None:
        nonlocal index_by_row
        lora_list.delete(0, "end")
        index_by_row = []
        entries = load_index(config)
        for e in entries:
            tag = f" [{','.join(e.tags)}]" if e.tags else ""
            line = f"{e.index:>3}. {e.file}  ({e.size_mb:.0f} MB){tag}"
            lora_list.insert("end", line)
            index_by_row.append(e.index)
        session = load_session(config, COMFY_TOPIC)
        pick = []
        if session is not None:
            pick = [int(x) for x in (session.meta.get("lora_last_pick") or []) if str(x).isdigit()]
        for i, idx in enumerate(index_by_row):
            if idx in pick:
                lora_list.selection_set(i)

    def selected_indices() -> List[int]:
        out: List[int] = []
        for i in lora_list.curselection():
            if 0 <= i < len(index_by_row):
                out.append(index_by_row[i])
        return sorted(set(out))

    def refresh_status() -> None:
        brief_var.set(comfy_pipeline_status_brief(config))
        text = _strip_md_bold(comfy_pipeline_status(config))
        status_txt.configure(state="normal")
        status_txt.delete("1.0", "end")
        status_txt.insert("1.0", text)
        status_txt.configure(state="disabled")

    def tick() -> None:
        if not win.winfo_exists():
            return
        refresh_status()
        win.after(2500, tick)

    def on_apply_lora() -> None:
        idx = selected_indices()
        try:
            msg = apply_lora_from_indices(config, idx)
        except Exception as exc:
            messagebox.showerror("LoRA", str(exc), parent=win)
            return
        messagebox.showinfo("LoRA", msg, parent=win)
        refresh_status()

    def on_rescan() -> None:
        try:
            n = len(scan_loras(config))
        except Exception as exc:
            messagebox.showerror("LoRA", str(exc), parent=win)
            return
        reload_lora_list()
        messagebox.showinfo("LoRA", f"Просканировано файлов: {n}.", parent=win)

    def on_none_lora() -> None:
        try:
            msg = apply_lora_from_indices(config, [])
        except Exception as exc:
            messagebox.showerror("LoRA", str(exc), parent=win)
            return
        lora_list.selection_clear(0, "end")
        messagebox.showinfo("LoRA", msg, parent=win)
        refresh_status()

    ttk.Button(btn_row, text="Обновить статус", command=refresh_status).pack(side="left")
    ttk.Button(btn_row, text="Поднять ComfyUI", command=callbacks.on_ensure_comfy).pack(
        side="left", padx=(8, 0)
    )
    ttk.Button(btn_row, text="MoCap: снять клип", command=callbacks.on_mocap_shoot).pack(
        side="left", padx=(8, 0)
    )
    ttk.Button(btn_row, text="Промпт Wan", command=callbacks.on_edit_prompt).pack(
        side="left", padx=(8, 0)
    )
    ttk.Button(btn_row, text="Оценить видео", command=callbacks.on_pick_clips).pack(
        side="left", padx=(8, 0)
    )
    if callbacks.on_shot_queue is not None:
        ttk.Button(
            btn_row, text="Очередь анимаций", command=callbacks.on_shot_queue
        ).pack(side="left", padx=(8, 0))
    ttk.Button(btn_row, text="Comfy в браузере", command=callbacks.on_open_browser).pack(
        side="left", padx=(8, 0)
    )

    ttk.Button(lora_btns, text="Пересканировать loras/", command=on_rescan).pack(side="left")
    ttk.Button(lora_btns, text="Применить выбор", command=on_apply_lora).pack(
        side="left", padx=8
    )
    ttk.Button(lora_btns, text="Без LoRA", command=on_none_lora).pack(side="left")

    def on_close() -> None:
        if on_finished:
            on_finished()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    reload_lora_list()
    refresh_status()
    tick()
