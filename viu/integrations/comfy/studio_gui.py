"""Единая панель «Съёмка видео»: цель, режим, длина, чекпоинт, эталон, LoRA, промпт."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, List, Optional

from ...config import Config
from ...lab.comfy_pipeline import COMFY_TOPIC, apply_lora_pick_decision
from ...lab.session import load_session, new_session, save_session
from .lora import load_index, scan_loras, spec_to_dict, specs_from_indices
from .pipeline_status import comfy_pipeline_status_brief
from .prompt_edit import apply_draft_text, format_wan_editor_text
from .shoot_settings import (
    DEFAULT_MOCAP_FRAMES,
    MODE_I2I,
    MODE_I2V,
    MODE_T2I,
    MODE_T2V,
    apply_shoot_settings,
    describe_mode,
    frames_from_seconds,
    length_from_meta,
    list_diffusion_checkpoints,
    mode_needs_seed,
    seconds_from_frames,
    seed_list_labels,
    shoot_mode_from_meta,
    unet_from_meta,
)
from .show_profile import (
    PROFILE_MOCAP,
    PROFILE_SHOW,
    SHOW_LENGTH,
    arm_show_profile,
    clear_show_profile,
    find_show_unet,
    is_show_profile,
    show_style_from_meta,
)


@dataclass
class ComfyStudioCallbacks:
    on_ensure_comfy: Callable[[], None]
    on_mocap_shoot: Callable[[], None]
    on_edit_prompt: Callable[[], None]
    on_pick_clips: Callable[[], None]
    on_open_browser: Callable[[], None]
    on_shot_queue: Optional[Callable[[], None]] = None
    on_comfy_diag: Optional[Callable[[], None]] = None
    # Новый контракт: снять с учётом профиля панели.
    on_shoot: Optional[Callable[[str, str], None]] = None
    on_new_clip: Optional[Callable[[str, str], None]] = None


def _strip_md_bold(text: str) -> str:
    return text.replace("**", "")


def apply_lora_from_indices(config: Config, indices: List[int]) -> str:
    """Текущий шаг LoRA или пресет для следующей съёмки."""
    session = load_session(config, COMFY_TOPIC)
    if session is None:
        session = new_session(COMFY_TOPIC)
        save_session(config, session)
    scan_loras(config)
    if session.status in ("awaiting_lora_pick", "awaiting_prompt"):
        return apply_lora_pick_decision(config, session, indices)
    specs = specs_from_indices(config, indices)
    session.meta["lora_last_pick"] = list(indices)
    session.meta["setup_lora_indices"] = list(indices)
    session.meta["selected_loras"] = [spec_to_dict(s) for s in specs]
    save_session(config, session)
    if not specs:
        return "Пресет LoRA: без LoRA (чистый Wan) — применю на следующем шаге выбора."
    names = ", ".join(s.file for s in specs)
    return f"Пресет LoRA сохранён: {names}"


def _ensure_session(config: Config):
    session = load_session(config, COMFY_TOPIC)
    if session is None:
        session = new_session(COMFY_TOPIC)
        save_session(config, session)
    return session


def open_comfy_studio(
    master: tk.Misc,
    config: Config,
    callbacks: ComfyStudioCallbacks,
    *,
    on_finished: Optional[Callable[[], None]] = None,
    initial_profile: str = "",
    initial_style: str = "realism",
) -> None:
    win = tk.Toplevel(master)
    win.title("Съёмка видео — Comfy")
    win.geometry("1040x900")
    win.minsize(860, 720)

    body = ttk.Frame(win, padding=10)
    body.pack(fill="both", expand=True)

    brief_var = tk.StringVar(value="")
    ttk.Label(body, textvariable=brief_var, font=("Segoe UI", 11, "bold")).pack(
        anchor="w", pady=(0, 4)
    )
    ttk.Label(
        body,
        text=(
            "Одна панель: цель → режим → длина → чекпоинт/LoRA → эталон → промпт → «Снять». "
            "«Новый клип» сбрасывает сессию под выбранную цель — без чужого окна MoCap."
        ),
        wraplength=980,
    ).pack(anchor="w", pady=(0, 8))

    # --- Цель / режим / длина ---
    top = ttk.LabelFrame(body, text="Цель и режим", padding=8)
    top.pack(fill="x", pady=(0, 6))

    profile_var = tk.StringVar(value=PROFILE_MOCAP)
    style_var = tk.StringVar(value="realism")
    mode_var = tk.StringVar(value=MODE_T2V)
    seconds_var = tk.StringVar(value=str(seconds_from_frames(SHOW_LENGTH)))

    row1 = ttk.Frame(top)
    row1.pack(fill="x")
    ttk.Label(row1, text="Цель:").pack(side="left")
    ttk.Radiobutton(
        row1, text="MoCap ×5 (Cascadeur)", variable=profile_var, value=PROFILE_MOCAP
    ).pack(side="left", padx=(8, 0))
    ttk.Radiobutton(
        row1, text="Шоу realism", variable=profile_var, value="show_realism"
    ).pack(side="left", padx=(8, 0))
    ttk.Radiobutton(
        row1, text="Шоу anime", variable=profile_var, value="show_anime"
    ).pack(side="left", padx=(8, 0))

    row2 = ttk.Frame(top)
    row2.pack(fill="x", pady=(6, 0))
    ttk.Label(row2, text="Режим:").pack(side="left")
    for label, val in (
        ("T2V", MODE_T2V),
        ("I2V", MODE_I2V),
        ("T2I", MODE_T2I),
        ("I2I", MODE_I2I),
    ):
        ttk.Radiobutton(row2, text=label, variable=mode_var, value=val).pack(
            side="left", padx=(8, 0)
        )
    mode_hint = tk.StringVar(value="")
    ttk.Label(row2, textvariable=mode_hint, foreground="#555").pack(
        side="left", padx=(12, 0)
    )

    row3 = ttk.Frame(top)
    row3.pack(fill="x", pady=(6, 0))
    ttk.Label(row3, text="Длина ролика (сек):").pack(side="left")
    sec_spin = ttk.Spinbox(
        row3,
        from_=0.7,
        to=5.0,
        increment=0.1,
        textvariable=seconds_var,
        width=6,
    )
    sec_spin.pack(side="left", padx=(8, 0))
    frames_var = tk.StringVar(value="")
    ttk.Label(row3, textvariable=frames_var).pack(side="left", padx=(8, 0))

    # --- Чекпоинт ---
    ckpt_frame = ttk.LabelFrame(body, text="Чекпоинт (UNET / SmoothMix / Wan)", padding=8)
    ckpt_frame.pack(fill="x", pady=(0, 6))
    ckpt_list = tk.Listbox(ckpt_frame, height=4, font=("Consolas", 9), exportselection=False)
    ckpt_list.pack(fill="x")
    ckpt_btns = ttk.Frame(ckpt_frame)
    ckpt_btns.pack(fill="x", pady=(4, 0))
    ckpt_names: List[str] = []

    # --- Эталон ---
    seed_frame = ttk.LabelFrame(body, text="Эталон (нужен для I2V / I2I)", padding=8)
    seed_frame.pack(fill="x", pady=(0, 6))
    seed_var = tk.StringVar(value="")
    ttk.Label(seed_frame, textvariable=seed_var, wraplength=980).pack(anchor="w")
    seed_list = tk.Listbox(seed_frame, height=4, font=("Consolas", 9), exportselection=False)
    seed_list.pack(fill="x", pady=(4, 0))
    seed_btns = ttk.Frame(seed_frame)
    seed_btns.pack(fill="x", pady=(6, 0))
    seed_entries: list = []

    # --- LoRA ---
    lora_frame = ttk.LabelFrame(body, text="LoRA", padding=8)
    lora_frame.pack(fill="x", pady=(0, 6))
    lora_list = tk.Listbox(
        lora_frame, selectmode=tk.EXTENDED, height=4, font=("Consolas", 9)
    )
    lora_scroll = ttk.Scrollbar(lora_frame, orient="vertical", command=lora_list.yview)
    lora_list.configure(yscrollcommand=lora_scroll.set)
    lora_list.pack(side="left", fill="both", expand=True)
    lora_scroll.pack(side="right", fill="y")
    lora_btns = ttk.Frame(body)
    lora_btns.pack(fill="x", pady=(0, 6))
    index_by_row: List[int] = []

    # --- Промпт ---
    prompt_frame = ttk.LabelFrame(body, text="Промпт Wan (редактируй здесь)", padding=8)
    prompt_frame.pack(fill="both", expand=True, pady=(0, 6))
    prompt_txt = tk.Text(prompt_frame, height=10, wrap="word", font=("Consolas", 9))
    prompt_txt.pack(fill="both", expand=True)
    prompt_btns = ttk.Frame(prompt_frame)
    prompt_btns.pack(fill="x", pady=(4, 0))

    # --- Действия ---
    btn_row = ttk.Frame(body)
    btn_row.pack(fill="x", pady=(4, 0))

    def _profile_pair() -> tuple[str, str]:
        raw = profile_var.get()
        if raw == "show_anime":
            return PROFILE_SHOW, "anime"
        if raw == "show_realism":
            return PROFILE_SHOW, "realism"
        return PROFILE_MOCAP, "realism"

    def _sync_frames_label(*_a) -> None:
        try:
            sec = float(seconds_var.get().replace(",", "."))
        except ValueError:
            sec = seconds_from_frames(SHOW_LENGTH)
        fr = frames_from_seconds(sec)
        frames_var.set(f"≈ {fr} кадров @ 24fps")
        mode_hint.set(describe_mode(mode_var.get()))

    def _read_ui_into_session(*, refresh_prompt: bool = False) -> None:
        session = _ensure_session(config)
        profile, style = _profile_pair()
        if profile == PROFILE_SHOW:
            arm_show_profile(
                session.meta,
                style=style,
                action=str(session.meta.get("action") or "").strip()
                or "standing relaxed in soft light, cinematic atmosphere",
            )
            session.meta["catalog_slug"] = "show"
            default_len = SHOW_LENGTH
        else:
            clear_show_profile(session.meta)
            default_len = DEFAULT_MOCAP_FRAMES
        try:
            sec = float(seconds_var.get().replace(",", "."))
        except ValueError:
            sec = seconds_from_frames(default_len)
        apply_shoot_settings(
            session.meta,
            mode=mode_var.get(),
            length_frames=frames_from_seconds(sec),
        )
        save_session(config, session)
        if refresh_prompt:
            _load_prompt_editor()

    def _load_prompt_editor() -> None:
        text = format_wan_editor_text(config)
        prompt_txt.delete("1.0", "end")
        prompt_txt.insert("1.0", text)

    def _save_prompt() -> str:
        _read_ui_into_session()
        ok, msg = apply_draft_text(config, prompt_txt.get("1.0", "end"), approve=False)
        if not ok:
            raise RuntimeError(msg)
        return msg

    def reload_ckpt_list() -> None:
        nonlocal ckpt_names
        ckpt_list.delete(0, "end")
        ckpt_names = list_diffusion_checkpoints(config)
        session = load_session(config, COMFY_TOPIC)
        selected = unet_from_meta(session.meta if session else None)
        if not selected:
            auto, _ = find_show_unet(config)
            selected = auto or ""
        for i, name in enumerate(ckpt_names):
            mark = "★ " if name == selected else "  "
            ckpt_list.insert("end", f"{mark}{name}")
            if name == selected:
                ckpt_list.selection_set(i)
                ckpt_list.see(i)

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
            pick = [
                int(x)
                for x in (session.meta.get("lora_last_pick") or [])
                if str(x).isdigit()
            ]
        for i, idx in enumerate(index_by_row):
            if idx in pick:
                lora_list.selection_set(i)

    def selected_lora_indices() -> List[int]:
        out: List[int] = []
        for i in lora_list.curselection():
            if 0 <= i < len(index_by_row):
                out.append(index_by_row[i])
        return sorted(set(out))

    def refresh_seed_line() -> None:
        nonlocal seed_entries
        from .seed_library import load_library
        from .seed_pose import i2v_status_line

        seed_var.set(i2v_status_line(config))
        seed_list.delete(0, "end")
        seed_entries = load_library(config)[:12]
        for line in seed_list_labels(config, seed_entries):
            seed_list.insert("end", line)
        # Подсветить ★ строку.
        for i, line in enumerate(seed_list_labels(config, seed_entries)):
            if "← ВЫБРАН" in line:
                seed_list.selection_set(i)
                seed_list.see(i)
                break

    def refresh_status() -> None:
        brief_var.set(comfy_pipeline_status_brief(config))
        session = load_session(config, COMFY_TOPIC)
        if session is not None:
            if is_show_profile(session.meta):
                st = show_style_from_meta(session.meta)
                profile_var.set("show_anime" if st == "anime" else "show_realism")
            else:
                profile_var.set(PROFILE_MOCAP)
            mode_var.set(shoot_mode_from_meta(session.meta))
            default = (
                SHOW_LENGTH
                if is_show_profile(session.meta)
                else DEFAULT_MOCAP_FRAMES
            )
            fr = length_from_meta(session.meta, default=default)
            seconds_var.set(str(seconds_from_frames(fr)))
        _sync_frames_label()
        refresh_seed_line()
        reload_ckpt_list()

    def on_open_seed_library() -> None:
        from .seed_library_gui import open_seed_library

        session = load_session(config, COMFY_TOPIC)
        slug = ""
        if session is not None:
            slug = str(session.meta.get("catalog_slug") or "")
        open_seed_library(win, config, default_slug=slug)
        refresh_seed_line()
        refresh_status()

    def on_activate_listed_seed() -> None:
        from .seed_library import activate_seed

        sel = seed_list.curselection()
        if not sel or int(sel[0]) >= len(seed_entries):
            messagebox.showinfo(
                "Эталон",
                "Выбери строку со ★ или любую из списка, потом «Выбрать».",
                parent=win,
            )
            return
        ok, msg = activate_seed(config, seed_entries[int(sel[0])].id, role="start")
        if ok:
            messagebox.showinfo("Эталон", f"Выбран:\n{msg}", parent=win)
        else:
            messagebox.showerror("Эталон", msg, parent=win)
        refresh_seed_line()
        refresh_status()

    def on_pick_seed() -> None:
        from tkinter import filedialog

        from .seed_pose import set_pose_seed

        path = filedialog.askopenfilename(
            parent=win,
            title="Эталон для I2V / I2I (кадр позы)",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All", "*.*"),
            ],
        )
        if not path:
            return
        session = load_session(config, COMFY_TOPIC)
        slug = ""
        if session is not None:
            slug = str(session.meta.get("catalog_slug") or "")
        ok, msg = set_pose_seed(config, Path(path), slug=slug)
        if ok:
            messagebox.showinfo("Эталон", msg, parent=win)
        else:
            messagebox.showerror("Эталон", msg, parent=win)
        refresh_seed_line()
        refresh_status()

    def on_clear_seed() -> None:
        from .seed_pose import clear_pose_seed

        msg = clear_pose_seed(config)
        messagebox.showinfo("Эталон", msg, parent=win)
        refresh_seed_line()
        refresh_status()

    def on_apply_ckpt() -> None:
        sel = ckpt_list.curselection()
        if not sel or int(sel[0]) >= len(ckpt_names):
            messagebox.showinfo("Чекпоинт", "Выбери файл в списке.", parent=win)
            return
        name = ckpt_names[int(sel[0])]
        session = _ensure_session(config)
        apply_shoot_settings(session.meta, unet=name)
        save_session(config, session)
        messagebox.showinfo("Чекпоинт", f"Буду снимать на:\n{name}", parent=win)
        reload_ckpt_list()

    def on_auto_ckpt() -> None:
        session = _ensure_session(config)
        apply_shoot_settings(session.meta, clear_unet=True)
        save_session(config, session)
        name, note = find_show_unet(config)
        messagebox.showinfo(
            "Чекпоинт",
            f"Авто: {name or 'Wan по умолчанию'}\n{note}",
            parent=win,
        )
        reload_ckpt_list()

    def on_apply_lora() -> None:
        idx = selected_lora_indices()
        try:
            msg = apply_lora_from_indices(config, idx)
        except Exception as exc:
            messagebox.showerror("LoRA", str(exc), parent=win)
            return
        messagebox.showinfo("LoRA", msg, parent=win)

    def on_rescan_lora() -> None:
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

    def on_save_prompt() -> None:
        try:
            msg = _save_prompt()
        except Exception as exc:
            messagebox.showerror("Промпт", str(exc), parent=win)
            return
        messagebox.showinfo("Промпт", msg, parent=win)
        _load_prompt_editor()

    def on_reload_prompt() -> None:
        _read_ui_into_session(refresh_prompt=True)

    def on_new_clip() -> None:
        _read_ui_into_session()
        profile, style = _profile_pair()
        session = _ensure_session(config)
        session.status = "idle"
        session.step = 0
        session.meta.pop("wan_positive", None)
        session.meta.pop("wan_negative", None)
        session.meta.pop("draft", None)
        session.meta.pop("prompt_user_edited", None)
        session.meta.pop("clip_batch_id", None)
        session.meta.pop("clip_candidate_ids", None)
        session.meta.pop("lora_pick_done", None)
        if profile == PROFILE_SHOW:
            arm_show_profile(
                session.meta,
                style=style,
                action="standing relaxed in soft light, cinematic atmosphere",
            )
            session.meta["catalog_slug"] = "show"
            apply_shoot_settings(
                session.meta, mode=mode_var.get() or MODE_T2V, length_frames=SHOW_LENGTH
            )
            seconds_var.set(str(seconds_from_frames(SHOW_LENGTH)))
        else:
            clear_show_profile(session.meta)
            session.meta["action"] = "posing in soft light"
            session.meta["approved_action"] = "posing in soft light"
            session.meta["catalog_slug"] = "chat_scene"
            apply_shoot_settings(
                session.meta,
                mode=mode_var.get() or MODE_T2V,
                length_frames=DEFAULT_MOCAP_FRAMES,
            )
            seconds_var.set(str(seconds_from_frames(DEFAULT_MOCAP_FRAMES)))
        save_session(config, session)
        _load_prompt_editor()
        refresh_status()
        if callbacks.on_new_clip:
            callbacks.on_new_clip(profile, style)
        messagebox.showinfo(
            "Новый клип",
            "Сессия сброшена под выбранную цель.\n"
            "Правишь промпт / чекпоинт / эталон → «Снять».",
            parent=win,
        )

    def on_shoot() -> None:
        try:
            _save_prompt()
        except Exception as exc:
            messagebox.showerror("Промпт", str(exc), parent=win)
            return
        _read_ui_into_session()
        profile, style = _profile_pair()
        if mode_needs_seed(mode_var.get()):
            from .seed_pose import resolve_active_seed

            _p, _n, on = resolve_active_seed(config)
            if not on:
                messagebox.showwarning(
                    "Эталон",
                    f"Режим {mode_var.get().upper()} без эталона.\n"
                    "Выбери ★ в списке или «Файл…», либо переключись на T2V.",
                    parent=win,
                )
                return
        if callbacks.on_shoot:
            callbacks.on_shoot(profile, style)
        elif profile == PROFILE_SHOW:
            # Совместимость: старый колбэк только mocap.
            callbacks.on_mocap_shoot()
        else:
            callbacks.on_mocap_shoot()

    def on_profile_change(*_a) -> None:
        _read_ui_into_session(refresh_prompt=True)
        refresh_status()

    def tick() -> None:
        if not win.winfo_exists():
            return
        brief_var.set(comfy_pipeline_status_brief(config))
        win.after(2500, tick)

    # Buttons
    ttk.Button(ckpt_btns, text="Применить чекпоинт", command=on_apply_ckpt).pack(
        side="left"
    )
    ttk.Button(ckpt_btns, text="Авто (SmoothMix/Wan)", command=on_auto_ckpt).pack(
        side="left", padx=8
    )
    ttk.Button(ckpt_btns, text="Обновить список", command=reload_ckpt_list).pack(
        side="left"
    )

    ttk.Button(seed_btns, text="Библиотека…", command=on_open_seed_library).pack(
        side="left"
    )
    ttk.Button(seed_btns, text="Выбрать ★", command=on_activate_listed_seed).pack(
        side="left", padx=6
    )
    ttk.Button(seed_btns, text="Файл…", command=on_pick_seed).pack(side="left")
    ttk.Button(seed_btns, text="Сбросить", command=on_clear_seed).pack(
        side="left", padx=8
    )

    ttk.Button(lora_btns, text="Пересканировать LoRA", command=on_rescan_lora).pack(
        side="left"
    )
    ttk.Button(lora_btns, text="Применить LoRA", command=on_apply_lora).pack(
        side="left", padx=8
    )
    ttk.Button(lora_btns, text="Без LoRA", command=on_none_lora).pack(side="left")

    ttk.Button(prompt_btns, text="Сохранить промпт", command=on_save_prompt).pack(
        side="left"
    )
    ttk.Button(
        prompt_btns, text="Пересобрать из цели", command=on_reload_prompt
    ).pack(side="left", padx=8)

    ttk.Button(btn_row, text="Новый клип", command=on_new_clip).pack(side="left")
    ttk.Button(btn_row, text="Снять", command=on_shoot).pack(side="left", padx=(8, 0))
    ttk.Button(btn_row, text="Оценить видео", command=callbacks.on_pick_clips).pack(
        side="left", padx=(8, 0)
    )
    ttk.Button(btn_row, text="Поднять Comfy", command=callbacks.on_ensure_comfy).pack(
        side="left", padx=(8, 0)
    )
    if callbacks.on_comfy_diag is not None:
        ttk.Button(btn_row, text="Диагностика", command=callbacks.on_comfy_diag).pack(
            side="left", padx=(8, 0)
        )
    ttk.Button(btn_row, text="Comfy в браузере", command=callbacks.on_open_browser).pack(
        side="left", padx=(8, 0)
    )
    plan_cb = callbacks.on_shot_queue or callbacks.on_edit_prompt
    ttk.Button(btn_row, text="План MoCap (очередь)", command=plan_cb).pack(
        side="left", padx=(8, 0)
    )

    def on_close() -> None:
        if on_finished:
            on_finished()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    # Initial profile from caller (шоу-кнопки).
    init = (initial_profile or "").strip().lower()
    if init in ("show", "шоу", "smoothmix"):
        st = (initial_style or "realism").strip().lower()
        profile_var.set("show_anime" if st == "anime" else "show_realism")
        mode_var.set(MODE_T2V)
        seconds_var.set(str(seconds_from_frames(SHOW_LENGTH)))
        session = _ensure_session(config)
        arm_show_profile(
            session.meta,
            style="anime" if st == "anime" else "realism",
            action=str(session.meta.get("action") or "").strip()
            or "standing relaxed in soft light, cinematic atmosphere",
        )
        session.meta["catalog_slug"] = "show"
        apply_shoot_settings(
            session.meta, mode=MODE_T2V, length_frames=SHOW_LENGTH
        )
        # Сбросить stale mocap overrides, чтобы редактор показал шоу-канон.
        session.meta.pop("wan_positive", None)
        session.meta.pop("wan_negative", None)
        save_session(config, session)
    elif init in ("mocap", "мокап"):
        profile_var.set(PROFILE_MOCAP)

    profile_var.trace_add("write", on_profile_change)
    mode_var.trace_add("write", lambda *_: _sync_frames_label())
    seconds_var.trace_add("write", lambda *_: _sync_frames_label())

    reload_lora_list()
    _read_ui_into_session(refresh_prompt=True)
    refresh_status()
    tick()
