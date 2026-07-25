"""Единое окно: очередь MoCap по графам + промпт Wan + LoRA."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Optional

from ...config import Config
from ...lab.comfy_pipeline import COMFY_TOPIC, apply_prompt_decision
from ...lab.session import load_session, new_session, save_session
from .shot_graphs import graph_for_slug, graph_path_label, group_items_by_graph
from .shot_queue import (
    ShotQueueItem,
    apply_item_lora_to_session,
    format_queue_brief,
    load_items,
    move_item,
    rebuild_queue,
    save_items,
    update_item,
)
from .studio_gui import apply_lora_from_indices
from .lora import load_index, scan_loras


def open_shot_queue_editor(
    master: tk.Misc,
    config: Config,
    *,
    on_finished: Optional[Callable[[bool, str], None]] = None,
    on_edit_prompt: Optional[Callable[[], None]] = None,
    on_shoot: Optional[Callable[[], None]] = None,
    focus_lab: bool = False,
) -> None:
    """План съёмки: каталог по графам, Wan-промпт, LoRA.

    on_edit_prompt — устаревший колбэк (игнорируется; всё в одном окне).
    focus_lab — сразу показать промпт текущей lab-сессии.
    """
    del on_edit_prompt  # совместимость вызовов

    win = tk.Toplevel(master)
    win.title("План MoCap — очередь, промпт Wan, LoRA")
    win.geometry("1040x780")
    win.minsize(860, 640)

    body = ttk.Frame(win, padding=10)
    body.pack(fill="both", expand=True)

    ttk.Label(
        body,
        text=(
            "Каталог по графам (лечь спать / залезть / сесть…). "
            "Правишь Wan и LoRA на кадр — away снимет по порядку. "
            "Двойной клик по списку больше не стирает несохранённый текст."
        ),
        wraplength=1000,
    ).pack(anchor="w", pady=(0, 6))

    mode_var = tk.StringVar(value="lab" if focus_lab else "queue")
    mode_row = ttk.Frame(body)
    mode_row.pack(fill="x", pady=(0, 6))
    ttk.Radiobutton(
        mode_row,
        text="Кадр из очереди",
        variable=mode_var,
        value="queue",
        command=lambda: on_mode_change(),
    ).pack(side="left")
    ttk.Radiobutton(
        mode_row,
        text="Текущий lab (сейчас в съёмке)",
        variable=mode_var,
        value="lab",
        command=lambda: on_mode_change(),
    ).pack(side="left", padx=12)

    paned = ttk.Panedwindow(body, orient="horizontal")
    paned.pack(fill="both", expand=True)

    left = ttk.Frame(paned, padding=(0, 0, 8, 0))
    right = ttk.Frame(paned)
    paned.add(left, weight=1)
    paned.add(right, weight=2)

    tree = ttk.Treeview(left, show="tree", selectmode="browse", height=24)
    tree.pack(fill="both", expand=True)
    list_btns = ttk.Frame(left)
    list_btns.pack(fill="x", pady=(6, 0))

    graph_var = tk.StringVar()
    slug_var = tk.StringVar()
    action_var = tk.StringVar()
    title_var = tk.StringVar()
    notes_var = tk.StringVar()
    status_var = tk.StringVar()
    lora_mode_var = tk.StringVar(value="inherit")

    ttk.Label(right, textvariable=graph_var, wraplength=620).pack(anchor="w", pady=(0, 4))
    ttk.Label(right, text="Slug").pack(anchor="w")
    ttk.Entry(right, textvariable=slug_var).pack(fill="x", pady=(0, 4))
    ttk.Label(right, text="Название").pack(anchor="w")
    ttk.Entry(right, textvariable=title_var).pack(fill="x", pady=(0, 4))
    ttk.Label(right, text="Действие / Action (EN)").pack(anchor="w")
    ttk.Entry(right, textvariable=action_var).pack(fill="x", pady=(0, 4))
    ttk.Label(right, text="Заметка для Вью").pack(anchor="w")
    ttk.Entry(right, textvariable=notes_var).pack(fill="x", pady=(0, 4))
    ttk.Label(right, textvariable=status_var).pack(anchor="w", pady=(0, 6))

    ttk.Label(right, text="Positive (Wan)").pack(anchor="w")
    pos_txt = tk.Text(right, height=7, wrap="word", font=("Consolas", 9))
    pos_txt.pack(fill="both", expand=True, pady=(0, 4))
    ttk.Label(right, text="Negative").pack(anchor="w")
    neg_txt = tk.Text(right, height=3, wrap="word", font=("Consolas", 9))
    neg_txt.pack(fill="both", expand=True, pady=(0, 4))

    lora_frame = ttk.LabelFrame(right, text="LoRA для этого кадра", padding=6)
    lora_frame.pack(fill="both", expand=True, pady=(4, 0))
    lora_mode_row = ttk.Frame(lora_frame)
    lora_mode_row.pack(fill="x", pady=(0, 4))
    ttk.Radiobutton(
        lora_mode_row, text="Как в сессии", variable=lora_mode_var, value="inherit"
    ).pack(side="left")
    ttk.Radiobutton(
        lora_mode_row, text="Выбор ниже", variable=lora_mode_var, value="pick"
    ).pack(side="left", padx=8)
    ttk.Radiobutton(
        lora_mode_row, text="Без LoRA", variable=lora_mode_var, value="none"
    ).pack(side="left")

    lora_list = tk.Listbox(
        lora_frame, selectmode=tk.EXTENDED, height=5, font=("Consolas", 9)
    )
    lora_scroll = ttk.Scrollbar(lora_frame, orient="vertical", command=lora_list.yview)
    lora_list.configure(yscrollcommand=lora_scroll.set)
    lora_list.pack(side="left", fill="both", expand=True)
    lora_scroll.pack(side="right", fill="y")
    lora_btns = ttk.Frame(lora_frame)
    lora_btns.pack(fill="x", pady=(4, 0))

    items: List[ShotQueueItem] = []
    selected_id: Optional[str] = None
    tree_iid_to_id: Dict[str, str] = {}
    index_by_row: List[int] = []
    _loading = False

    def reload_lora_list(select: Optional[List[int]] = None) -> None:
        nonlocal index_by_row
        lora_list.delete(0, "end")
        index_by_row = []
        try:
            entries = load_index(config)
        except Exception:
            entries = []
        for e in entries:
            tag = f" [{','.join(e.tags)}]" if e.tags else ""
            lora_list.insert("end", f"{e.index:>3}. {e.file}  ({e.size_mb:.0f} MB){tag}")
            index_by_row.append(e.index)
        want = set(select or [])
        for i, idx in enumerate(index_by_row):
            if idx in want:
                lora_list.selection_set(i)

    def selected_lora_indices() -> List[int]:
        out: List[int] = []
        for i in lora_list.curselection():
            if 0 <= i < len(index_by_row):
                out.append(index_by_row[i])
        return sorted(set(out))

    def current_item() -> Optional[ShotQueueItem]:
        sel = tree.selection()
        if not sel:
            return None
        iid = sel[0]
        item_id = tree_iid_to_id.get(iid)
        if not item_id:
            return None
        for it in items:
            if it.id == item_id:
                return it
        return None

    def _read_form_into(it: ShotQueueItem) -> None:
        it.catalog_slug = slug_var.get().strip()
        it.title_ru = title_var.get().strip()
        it.action = action_var.get().strip()
        it.notes = notes_var.get().strip()
        it.wan_positive = pos_txt.get("1.0", "end").strip()
        it.wan_negative = neg_txt.get("1.0", "end").strip()
        it.lora_mode = (lora_mode_var.get() or "inherit").strip().lower()
        if it.lora_mode not in ("inherit", "none", "pick"):
            it.lora_mode = "inherit"
        it.lora_indices = selected_lora_indices() if it.lora_mode == "pick" else []

    def save_by_id(item_id: str) -> bool:
        """Сохранить форму в item_id (даже если список уже переключился)."""
        if mode_var.get() != "queue":
            return False
        for it in items:
            if it.id != item_id:
                continue
            _read_form_into(it)
            update_item(
                config,
                it.id,
                catalog_slug=it.catalog_slug,
                title_ru=it.title_ru,
                action=it.action,
                notes=it.notes,
                wan_positive=it.wan_positive,
                wan_negative=it.wan_negative,
                lora_mode=it.lora_mode,
                lora_indices=list(it.lora_indices),
            )
            return True
        return False

    def save_current() -> bool:
        if mode_var.get() == "lab":
            return save_lab_form()
        it = current_item()
        if it is None:
            return False
        return save_by_id(it.id)

    def show_item(it: Optional[ShotQueueItem]) -> None:
        nonlocal selected_id, _loading
        _loading = True
        try:
            selected_id = it.id if it else None
            if it is None:
                graph_var.set("")
                slug_var.set("")
                title_var.set("")
                action_var.set("")
                notes_var.set("")
                status_var.set("")
                lora_mode_var.set("inherit")
                pos_txt.delete("1.0", "end")
                neg_txt.delete("1.0", "end")
                reload_lora_list([])
                return
            g = graph_for_slug(it.catalog_slug)
            graph_var.set(
                graph_path_label(
                    it.catalog_slug,
                    enters_from=it.enters_from,
                    exits_to=it.exits_to,
                )
                + (f"  · {g.hint}" if g.hint else "")
            )
            slug_var.set(it.catalog_slug)
            title_var.set(it.title_ru)
            action_var.set(it.action)
            notes_var.set(it.notes)
            status_var.set(f"Статус: {it.status}")
            lora_mode_var.set(it.lora_mode or "inherit")
            pos_txt.delete("1.0", "end")
            pos_txt.insert("1.0", it.wan_positive)
            neg_txt.delete("1.0", "end")
            neg_txt.insert("1.0", it.wan_negative)
            reload_lora_list(list(it.lora_indices or []))
        finally:
            _loading = False

    def show_lab() -> None:
        nonlocal selected_id, _loading
        from .prompt_edit import resolved_wan_lines

        _loading = True
        try:
            selected_id = None
            action, positive, negative = resolved_wan_lines(config)
            session = load_session(config, COMFY_TOPIC)
            slug = ""
            st = ""
            pick: List[int] = []
            if session is not None:
                slug = str(session.meta.get("catalog_slug") or "").strip()
                st = str(session.status or "")
                pick = [
                    int(x)
                    for x in (session.meta.get("lora_last_pick") or [])
                    if str(x).isdigit()
                ]
            g = graph_for_slug(slug)
            graph_var.set(
                f"Текущий lab · {g.title_ru}"
                + (f" · `{slug}`" if slug else "")
                + (f" · статус {st}" if st else "")
            )
            slug_var.set(slug)
            title_var.set("")
            action_var.set(action)
            notes_var.set("")
            status_var.set("Редактируешь lab-сессию (не строку очереди)")
            lora_mode_var.set("pick" if pick else "inherit")
            pos_txt.delete("1.0", "end")
            pos_txt.insert("1.0", positive)
            neg_txt.delete("1.0", "end")
            neg_txt.insert("1.0", negative)
            reload_lora_list(pick)
        finally:
            _loading = False

    def save_lab_form() -> bool:
        from .prompt_edit import apply_draft_to_session

        session = load_session(config, COMFY_TOPIC)
        if session is None:
            session = new_session(COMFY_TOPIC)
            save_session(config, session)
        body = (
            "--- POSITIVE (в ComfyUI / Wan) ---\n"
            f"{pos_txt.get('1.0', 'end').strip()}\n\n"
            "--- NEGATIVE ---\n"
            f"{neg_txt.get('1.0', 'end').strip()}\n\n"
            "--- ДЕЙСТВИЕ (EN) ---\n"
            f"{action_var.get().strip()}\n"
        )
        ok, msg = apply_draft_to_session(config, session, body)
        if not ok:
            messagebox.showerror("Промпт", msg, parent=win)
            return False
        mode = (lora_mode_var.get() or "inherit").strip().lower()
        if mode == "none":
            apply_lora_from_indices(config, [])
        elif mode == "pick":
            apply_lora_from_indices(config, selected_lora_indices())
        return True

    def refresh_tree(*, select_id: Optional[str] = None) -> None:
        nonlocal items, tree_iid_to_id
        items = load_items(config)
        tree.delete(*tree.get_children())
        tree_iid_to_id = {}
        for graph, chunk in group_items_by_graph(items):
            parent = tree.insert(
                "",
                "end",
                iid=f"g:{graph.id}",
                text=f"▸ {graph.title_ru}  ({len(chunk)})",
                open=True,
            )
            for it in chunk:
                mark = {"pending": "·", "done": "✓", "skipped": "✗"}.get(it.status, "?")
                title = it.title_ru or it.catalog_slug or "?"
                lora_mark = ""
                if it.lora_mode == "pick" and it.lora_indices:
                    lora_mark = " ⚙"
                elif it.lora_mode == "none":
                    lora_mark = " ∅"
                iid = f"i:{it.id}"
                tree.insert(
                    parent,
                    "end",
                    iid=iid,
                    text=f"{mark} {it.catalog_slug} — {title[:36]}{lora_mark}",
                )
                tree_iid_to_id[iid] = it.id
        if select_id:
            iid = f"i:{select_id}"
            if tree.exists(iid):
                tree.selection_set(iid)
                tree.see(iid)

    def on_select(_evt=None) -> None:
        nonlocal _loading
        if _loading or mode_var.get() != "queue":
            return
        sel = tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid.startswith("g:"):
            # Клик по графу — не трогаем форму (не стираем текст).
            return
        item_id = tree_iid_to_id.get(iid)
        if not item_id:
            return
        # Тот же кадр (в т.ч. повторный клик / «двойной») — не перезагружать поля.
        if item_id == selected_id:
            return
        prev = selected_id
        if prev:
            save_by_id(prev)
            _loading = True
            try:
                refresh_tree(select_id=item_id)
            finally:
                _loading = False
        for it in items:
            if it.id == item_id:
                show_item(it)
                break

    def on_mode_change() -> None:
        if mode_var.get() == "lab":
            if selected_id:
                save_by_id(selected_id)
            show_lab()
        else:
            save_lab_form()
            it = current_item()
            if it is None and items:
                refresh_tree(select_id=items[0].id)
                show_item(items[0])
            else:
                show_item(it)

    def on_rebuild() -> None:
        save_current()
        rebuilt = rebuild_queue(config, limit=12, keep_edits=True)
        mode_var.set("queue")
        refresh_tree(select_id=rebuilt[0].id if rebuilt else None)
        if rebuilt:
            show_item(rebuilt[0])
        messagebox.showinfo(
            "План MoCap",
            f"Собрала {len(rebuilt)} кадров.\n{format_queue_brief(config)}",
            parent=win,
        )

    def on_skip() -> None:
        if mode_var.get() != "queue":
            return
        it = current_item()
        if it is None:
            return
        save_current()
        update_item(config, it.id, status="skipped")
        refresh_tree()
        show_item(current_item())

    def on_pending() -> None:
        if mode_var.get() != "queue":
            return
        it = current_item()
        if it is None:
            return
        save_current()
        update_item(config, it.id, status="pending")
        refresh_tree(select_id=it.id)

    def _move(delta: int) -> None:
        if mode_var.get() != "queue":
            return
        it = current_item()
        if it is None:
            return
        save_current()
        move_item(config, it.id, delta=delta)
        refresh_tree(select_id=it.id)

    def on_clear_done() -> None:
        save_current()
        keep = [i for i in load_items(config) if i.status == "pending"]
        save_items(config, keep)
        refresh_tree()
        show_item(current_item())

    def push_to_lab(*, shoot: bool) -> None:
        if mode_var.get() == "lab":
            if not save_lab_form():
                return
            msg = "Промпт lab сохранён."
            if shoot:
                session = load_session(config, COMFY_TOPIC)
                if session is not None and session.status == "awaiting_prompt":
                    msg2 = apply_prompt_decision(
                        config,
                        session,
                        "approve",
                        str(session.meta.get("action") or ""),
                    )
                    msg = msg + "\n\n" + msg2
                elif session is not None:
                    session.meta["approved"] = True
                    session.meta["approved_action"] = str(
                        session.meta.get("action")
                        or session.meta.get("approved_action")
                        or ""
                    )
                    session.meta["shoot_intent"] = True
                    session.meta["auto_approved_shoot"] = True
                    session.meta.pop("lora_pick_done", None)
                    if session.status in ("idle", "completed", "paused"):
                        session.status = "running"
                        if session.step < 3:
                            session.step = 3
                    save_session(config, session)
                    msg += "\n\nЗапускаю съёмку."
            win.destroy()
            if on_finished:
                on_finished(True, msg)
            if shoot and on_shoot:
                on_shoot()
            return

        it = current_item()
        if it is None:
            messagebox.showerror("План MoCap", "Выбери кадр в очереди.", parent=win)
            return
        save_current()
        items_now = load_items(config)
        it = next((x for x in items_now if x.id == it.id), it)
        session = load_session(config, COMFY_TOPIC)
        if session is None:
            session = new_session(COMFY_TOPIC)
        session.meta["catalog_slug"] = it.catalog_slug
        session.meta["action"] = it.action
        session.meta["approved_action"] = it.action
        if it.wan_positive:
            session.meta["wan_positive"] = it.wan_positive
            session.meta["prompt_user_edited"] = True
            session.meta["prompt_edit_slug"] = it.catalog_slug
        if it.wan_negative:
            session.meta["wan_negative"] = it.wan_negative
        if it.notes:
            session.meta["queue_notes"] = it.notes
        if it.enters_from:
            session.meta["enters_from"] = list(it.enters_from)
        if it.exits_to:
            session.meta["exits_to"] = list(it.exits_to)
        save_session(config, session)
        lora_msg = apply_item_lora_to_session(config, it)
        msg = f"Кадр `{it.catalog_slug}` → lab."
        if lora_msg:
            msg += "\n" + lora_msg
        if shoot:
            session = load_session(config, COMFY_TOPIC) or session
            session.meta["approved"] = True
            session.meta["shoot_intent"] = True
            session.meta["auto_approved_shoot"] = True
            session.meta.pop("lora_pick_done", None)
            if session.status in ("idle", "completed", "paused", "awaiting_prompt"):
                if session.status == "awaiting_prompt":
                    apply_prompt_decision(
                        config,
                        session,
                        "approve",
                        it.action,
                    )
                    session = load_session(config, COMFY_TOPIC) or session
                else:
                    session.status = "running"
                    if session.step < 3:
                        session.step = 3
                    save_session(config, session)
            msg += "\nЗапускаю съёмку с этим промптом."
        win.destroy()
        if on_finished:
            on_finished(True, msg)
        if shoot and on_shoot:
            on_shoot()

    def on_save_close() -> None:
        save_current()
        msg = format_queue_brief(config)
        win.destroy()
        if on_finished:
            on_finished(True, msg)

    def on_rescan_lora() -> None:
        try:
            n = len(scan_loras(config))
        except Exception as exc:
            messagebox.showerror("LoRA", str(exc), parent=win)
            return
        reload_lora_list(selected_lora_indices())
        messagebox.showinfo("LoRA", f"Просканировано файлов: {n}.", parent=win)

    def on_apply_lora_session() -> None:
        """Пресет сессии из текущего выбора (удобно в режиме lab)."""
        mode = (lora_mode_var.get() or "inherit").strip().lower()
        try:
            if mode == "none":
                msg = apply_lora_from_indices(config, [])
            else:
                msg = apply_lora_from_indices(config, selected_lora_indices())
                if mode != "pick":
                    lora_mode_var.set("pick")
        except Exception as exc:
            messagebox.showerror("LoRA", str(exc), parent=win)
            return
        messagebox.showinfo("LoRA", msg, parent=win)

    tree.bind("<<TreeviewSelect>>", on_select)

    ttk.Button(list_btns, text="Собрать / обновить", command=on_rebuild).pack(side="left")
    ttk.Button(list_btns, text="↑", width=3, command=lambda: _move(-1)).pack(
        side="left", padx=4
    )
    ttk.Button(list_btns, text="↓", width=3, command=lambda: _move(1)).pack(side="left")

    edit_btns = ttk.Frame(right)
    edit_btns.pack(fill="x", pady=(6, 0))
    ttk.Button(edit_btns, text="Сохранить", command=save_current).pack(side="left")
    ttk.Button(
        edit_btns, text="В Comfy", command=lambda: push_to_lab(shoot=False)
    ).pack(side="left", padx=6)
    ttk.Button(
        edit_btns, text="В Comfy и снять", command=lambda: push_to_lab(shoot=True)
    ).pack(side="left")
    ttk.Button(edit_btns, text="Пропустить", command=on_skip).pack(side="left", padx=6)
    ttk.Button(edit_btns, text="Вернуть в очередь", command=on_pending).pack(side="left")

    ttk.Button(lora_btns, text="Пересканировать", command=on_rescan_lora).pack(
        side="left"
    )
    ttk.Button(lora_btns, text="В пресет сессии", command=on_apply_lora_session).pack(
        side="left", padx=8
    )

    bottom = ttk.Frame(body)
    bottom.pack(fill="x", pady=(8, 0))
    ttk.Button(bottom, text="Убрать done/skipped", command=on_clear_done).pack(
        side="left"
    )
    ttk.Button(bottom, text="Сохранить и закрыть", command=on_save_close).pack(
        side="right"
    )
    ttk.Button(bottom, text="Закрыть", command=win.destroy).pack(side="right", padx=8)

    items = load_items(config)
    if not items:
        items = rebuild_queue(config, limit=12)
    refresh_tree(select_id=items[0].id if items else None)
    if focus_lab:
        mode_var.set("lab")
        show_lab()
    elif items:
        iid = f"i:{items[0].id}"
        if tree.exists(iid):
            tree.selection_set(iid)
        show_item(items[0])
