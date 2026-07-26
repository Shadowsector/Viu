"""Общие фикстуры pytest."""

from __future__ import annotations

import sys
import types


def _ensure_tkinter_stub() -> None:
    """Cloud/CI без python3-tk: достаточно заглушки для import-time GUI."""
    if "tkinter" in sys.modules and hasattr(sys.modules["tkinter"], "Tk"):
        try:
            import tkinter  # noqa: F401

            return
        except Exception:  # noqa: BLE001
            pass

    names = [
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.scrolledtext",
        "tkinter.simpledialog",
        "tkinter.font",
        "tkinter.constants",
    ]
    mods = {name: types.ModuleType(name) for name in names}
    for name, mod in mods.items():
        sys.modules[name] = mod

    tk = mods["tkinter"]
    dummy = type("TkDummy", (), {})
    const = {
        "END",
        "LEFT",
        "RIGHT",
        "TOP",
        "BOTTOM",
        "BOTH",
        "X",
        "Y",
        "N",
        "S",
        "E",
        "W",
        "HORIZONTAL",
        "VERTICAL",
        "DISABLED",
        "NORMAL",
        "ACTIVE",
        "WORD",
        "CHAR",
        "SOLID",
        "FLAT",
        "RAISED",
        "SUNKEN",
        "GROOVE",
        "RIDGE",
        "NSEW",
        "NS",
        "EW",
        "YES",
        "NO",
        "TRUE",
        "FALSE",
        "INSERT",
        "CURRENT",
        "ANCHOR",
        "ALL",
        "NONE",
    }
    widgets = (
        "Tk",
        "Toplevel",
        "Frame",
        "Label",
        "Button",
        "Entry",
        "Text",
        "Canvas",
        "Scrollbar",
        "Checkbutton",
        "Radiobutton",
        "Listbox",
        "Menu",
        "Menubutton",
        "Scale",
        "Spinbox",
        "PanedWindow",
        "LabelFrame",
        "Message",
        "OptionMenu",
        "BitmapImage",
        "PhotoImage",
        "StringVar",
        "IntVar",
        "DoubleVar",
        "BooleanVar",
        "Variable",
        "Event",
    )
    for name in widgets:
        setattr(tk, name, type(name, (dummy,), {}))
    for name in const:
        setattr(tk, name, name)

    def _noop(*_a, **_k):
        return None

    for modname, fns in (
        (
            "tkinter.messagebox",
            (
                "showinfo",
                "showwarning",
                "showerror",
                "askyesno",
                "askokcancel",
                "askquestion",
                "askretrycancel",
                "askyesnocancel",
            ),
        ),
        (
            "tkinter.simpledialog",
            ("askstring", "askinteger", "askfloat", "Dialog"),
        ),
        (
            "tkinter.filedialog",
            (
                "askopenfilename",
                "askopenfilenames",
                "askdirectory",
                "asksaveasfilename",
                "askopenfile",
                "asksaveasfile",
            ),
        ),
    ):
        m = mods[modname]
        for fn in fns:
            setattr(m, fn, _noop if fn != "Dialog" else type("Dialog", (dummy,), {}))

    ttk = mods["tkinter.ttk"]
    for name in (
        "Frame",
        "Label",
        "Button",
        "Entry",
        "Notebook",
        "Treeview",
        "Scrollbar",
        "Progressbar",
        "Combobox",
        "Checkbutton",
        "Radiobutton",
        "LabelFrame",
        "Separator",
        "Style",
        "Sizegrip",
    ):
        setattr(ttk, name, type(name, (dummy,), {}))

    mods["tkinter.scrolledtext"].ScrolledText = type("ScrolledText", (dummy,), {})
    mods["tkinter.font"].Font = type("Font", (dummy,), {})
    tk.messagebox = mods["tkinter.messagebox"]
    tk.simpledialog = mods["tkinter.simpledialog"]
    tk.filedialog = mods["tkinter.filedialog"]
    tk.ttk = ttk
    tk.scrolledtext = mods["tkinter.scrolledtext"]
    tk.font = mods["tkinter.font"]


_ensure_tkinter_stub()
