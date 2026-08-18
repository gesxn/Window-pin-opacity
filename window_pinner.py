from __future__ import annotations

import ctypes
import os
import sys
import tkinter as tk
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk


if sys.platform != "win32":
    raise SystemExit("Window Pinner работает только в Windows.")


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x00000002
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GA_ROOT = 2

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
user32.GetLayeredWindowAttributes.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.COLORREF), ctypes.POINTER(wintypes.BYTE), ctypes.POINTER(wintypes.DWORD)]
user32.GetLayeredWindowAttributes.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

if ctypes.sizeof(ctypes.c_void_p) == 8:
    GetWindowLong = user32.GetWindowLongPtrW
    SetWindowLong = user32.SetWindowLongPtrW
else:
    GetWindowLong = user32.GetWindowLongW
    SetWindowLong = user32.SetWindowLongW
GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
GetWindowLong.restype = ctypes.c_ssize_t
SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
SetWindowLong.restype = ctypes.c_ssize_t


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    process: str
    is_topmost: bool


@dataclass
class OriginalState:
    exstyle: int
    was_topmost: bool
    layered_color: int | None = None
    layered_alpha: int | None = None
    layered_flags: int | None = None


def win_error(action: str) -> OSError:
    code = ctypes.get_last_error()
    return OSError(code, f"{action}: {ctypes.FormatError(code).strip()}")


def get_exstyle(hwnd: int) -> int:
    ctypes.set_last_error(0)
    result = GetWindowLong(hwnd, GWL_EXSTYLE)
    if result == 0 and ctypes.get_last_error():
        raise win_error("Не удалось прочитать свойства окна")
    return int(result)


def root_hwnd(hwnd: int) -> int:
    root = user32.GetAncestor(hwnd, GA_ROOT)
    return int(root or hwnd)


def get_process_name(hwnd: int) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return "Приложение"
    try:
        capacity = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(capacity)):
            return Path(buffer.value).stem
    finally:
        kernel32.CloseHandle(handle)
    return "Приложение"


class WindowPinner(tk.Tk):
    BG = "#0B1120"
    PANEL = "#111A2E"
    PANEL_ALT = "#162239"
    BORDER = "#263653"
    TEXT = "#F6F8FC"
    MUTED = "#94A3B8"
    ACCENT = "#6D5DFB"
    ACCENT_HOVER = "#8174FF"
    GREEN = "#2DD4BF"
    RED = "#FB7185"

    def __init__(self) -> None:
        super().__init__()
        self.title("Window Pinner")
        self.geometry("940x650")
        self.minsize(780, 560)
        self.configure(bg=self.BG)

        self.windows: dict[int, WindowInfo] = {}
        self.original_states: dict[int, OriginalState] = {}
        self.opacity_by_hwnd: dict[int, int] = {}
        self.selected_hwnd: int | None = None
        self.restore_on_exit = tk.BooleanVar(value=True)
        self.search_var = tk.StringVar()
        self.opacity_var = tk.IntVar(value=100)
        self.status_var = tk.StringVar(value="Готово")

        self._configure_styles()
        self._build_ui()
        self.search_var.trace_add("write", lambda *_: self._populate_tree())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self.refresh_windows)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Windows.Treeview",
            background=self.PANEL,
            fieldbackground=self.PANEL,
            foreground=self.TEXT,
            rowheight=46,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.map(
            "Windows.Treeview",
            background=[("selected", self.PANEL_ALT)],
            foreground=[("selected", self.TEXT)],
        )
        style.configure(
            "Windows.Treeview.Heading",
            background=self.PANEL,
            foreground=self.MUTED,
            borderwidth=0,
            relief="flat",
            padding=(12, 10),
            font=("Segoe UI Semibold", 9),
        )
        style.map("Windows.Treeview.Heading", background=[("active", self.PANEL)])
        style.configure(
            "Modern.Horizontal.TScale",
            background=self.PANEL,
            troughcolor="#273450",
            sliderthickness=20,
            borderwidth=0,
            lightcolor=self.ACCENT,
            darkcolor=self.ACCENT,
        )
        style.configure(
            "Modern.TCheckbutton",
            background=self.PANEL,
            foreground=self.MUTED,
            font=("Segoe UI", 9),
        )
        style.map("Modern.TCheckbutton", background=[("active", self.PANEL)])

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=self.BG, height=86)
        header.pack(fill="x", padx=28, pady=(22, 10))
        header.pack_propagate(False)

        logo = tk.Canvas(header, width=48, height=48, bg=self.BG, highlightthickness=0)
        logo.pack(side="left", pady=7)
        logo.create_oval(3, 3, 45, 45, fill=self.ACCENT, outline="")
        logo.create_text(24, 24, text="W", fill="white", font=("Segoe UI Semibold", 20))

        title_box = tk.Frame(header, bg=self.BG)
        title_box.pack(side="left", padx=14, pady=4)
        tk.Label(title_box, text="Window Pinner", bg=self.BG, fg=self.TEXT, font=("Segoe UI Semibold", 21)).pack(anchor="w")
        tk.Label(title_box, text="Закрепляйте окна и настраивайте их прозрачность", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))

        self._button(header, "Обновить", self.refresh_windows, secondary=True, width=118).pack(side="right", pady=12)
        self._button(header, "Выбрать окно", self.capture_foreground, width=144).pack(side="right", padx=(0, 10), pady=12)

        main = tk.Frame(self, bg=self.BG)
        main.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        list_panel = tk.Frame(main, bg=self.PANEL, highlightbackground=self.BORDER, highlightthickness=1)
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        list_top = tk.Frame(list_panel, bg=self.PANEL)
        list_top.pack(fill="x", padx=18, pady=(17, 10))
        tk.Label(list_top, text="Открытые окна", bg=self.PANEL, fg=self.TEXT, font=("Segoe UI Semibold", 12)).pack(side="left")
        self.count_label = tk.Label(list_top, text="0", bg=self.PANEL_ALT, fg=self.MUTED, padx=8, pady=3, font=("Segoe UI Semibold", 8))
        self.count_label.pack(side="left", padx=8)

        search_frame = tk.Frame(list_panel, bg=self.PANEL_ALT, highlightbackground=self.BORDER, highlightthickness=1)
        search_frame.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(search_frame, text="⌕", bg=self.PANEL_ALT, fg=self.MUTED, font=("Segoe UI", 15)).pack(side="left", padx=(10, 3))
        search = tk.Entry(search_frame, textvariable=self.search_var, bg=self.PANEL_ALT, fg=self.TEXT, insertbackground=self.TEXT, relief="flat", font=("Segoe UI", 10))
        search.pack(side="left", fill="x", expand=True, padx=(2, 10), pady=9)

        tree_wrap = tk.Frame(list_panel, bg=self.PANEL)
        tree_wrap.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self.tree = ttk.Treeview(tree_wrap, style="Windows.Treeview", columns=("app", "state"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="ОКНО", anchor="w")
        self.tree.heading("app", text="ПРИЛОЖЕНИЕ", anchor="w")
        self.tree.heading("state", text="СТАТУС", anchor="center")
        self.tree.column("#0", width=260, minwidth=150, stretch=True)
        self.tree.column("app", width=110, minwidth=80)
        self.tree.column("state", width=86, minwidth=76, anchor="center")
        scrollbar = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _event: self.toggle_pin())

        controls = tk.Frame(main, bg=self.PANEL, highlightbackground=self.BORDER, highlightthickness=1)
        controls.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        tk.Label(controls, text="Настройки окна", bg=self.PANEL, fg=self.TEXT, font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=20, pady=(18, 4))
        self.selection_label = tk.Label(controls, text="Выберите окно слева", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 9), wraplength=280, justify="left")
        self.selection_label.pack(anchor="w", padx=20, pady=(0, 18))

        self.pin_button = self._button(controls, "Закрепить поверх окон", self.toggle_pin)
        self.pin_button.pack(fill="x", padx=20, pady=(0, 20))

        separator = tk.Frame(controls, bg=self.BORDER, height=1)
        separator.pack(fill="x", padx=20)

        opacity_head = tk.Frame(controls, bg=self.PANEL)
        opacity_head.pack(fill="x", padx=20, pady=(20, 8))
        tk.Label(opacity_head, text="Прозрачность", bg=self.PANEL, fg=self.TEXT, font=("Segoe UI Semibold", 10)).pack(side="left")
        self.opacity_label = tk.Label(opacity_head, text="100%", bg=self.PANEL_ALT, fg=self.GREEN, padx=8, pady=3, font=("Segoe UI Semibold", 9))
        self.opacity_label.pack(side="right")

        self.scale = ttk.Scale(controls, style="Modern.Horizontal.TScale", from_=20, to=100, variable=self.opacity_var, command=self._opacity_preview)
        self.scale.pack(fill="x", padx=20, pady=(4, 5))
        self.scale.bind("<ButtonRelease-1>", self._apply_opacity_event)

        range_labels = tk.Frame(controls, bg=self.PANEL)
        range_labels.pack(fill="x", padx=20)
        tk.Label(range_labels, text="20%", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 8)).pack(side="left")
        tk.Label(range_labels, text="100%", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 8)).pack(side="right")

        self._button(controls, "Вернуть непрозрачность", self.reset_opacity, secondary=True).pack(fill="x", padx=20, pady=(18, 8))
        ttk.Checkbutton(controls, text="Восстанавливать окна при выходе", variable=self.restore_on_exit, style="Modern.TCheckbutton").pack(anchor="w", padx=18, pady=(8, 0))

        help_box = tk.Frame(controls, bg=self.PANEL_ALT, highlightbackground=self.BORDER, highlightthickness=1)
        help_box.pack(side="bottom", fill="x", padx=20, pady=20)
        tk.Label(help_box, text="Быстрый выбор", bg=self.PANEL_ALT, fg=self.GREEN, font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(help_box, text="Нажмите «Выбрать окно», затем в течение 3 секунд переключитесь на нужное окно.", bg=self.PANEL_ALT, fg=self.MUTED, font=("Segoe UI", 9), wraplength=275, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

        status = tk.Frame(self, bg=self.PANEL, height=34)
        status.pack(fill="x", side="bottom")
        tk.Label(status, textvariable=self.status_var, bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 9)).pack(side="left", padx=28, pady=7)

        self._set_controls_enabled(False)

    def _button(self, parent: tk.Misc, text: str, command, secondary: bool = False, width: int | None = None) -> tk.Button:
        bg = self.PANEL_ALT if secondary else self.ACCENT
        active = self.BORDER if secondary else self.ACCENT_HOVER
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=self.TEXT,
            activebackground=active,
            activeforeground=self.TEXT,
            disabledforeground="#64748B",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            padx=14,
            pady=10,
            font=("Segoe UI Semibold", 9),
        )
        if width:
            button.configure(width=max(1, width // 8))
        return button

    def _own_hwnd(self) -> int:
        self.update_idletasks()
        return root_hwnd(int(self.winfo_id()))

    def enumerate_windows(self) -> list[WindowInfo]:
        own = self._own_hwnd()
        result: list[WindowInfo] = []

        @EnumWindowsProc
        def callback(hwnd: int, _lparam: int) -> bool:
            if hwnd == own or not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            title_buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buffer, length + 1)
            title = title_buffer.value.strip()
            if not title:
                return True
            try:
                exstyle = get_exstyle(hwnd)
            except OSError:
                return True
            if exstyle & WS_EX_TOOLWINDOW:
                return True
            result.append(WindowInfo(int(hwnd), title, get_process_name(hwnd), bool(exstyle & WS_EX_TOPMOST)))
            return True

        if not user32.EnumWindows(callback, 0):
            raise win_error("Не удалось получить список окон")
        result.sort(key=lambda item: item.title.casefold())
        return result

    def refresh_windows(self, keep_selection: bool = True) -> None:
        previous = self.selected_hwnd if keep_selection else None
        try:
            items = self.enumerate_windows()
        except OSError as error:
            messagebox.showerror("Ошибка Windows API", str(error), parent=self)
            return
        self.windows = {item.hwnd: item for item in items}
        self._populate_tree()
        if previous in self.windows:
            iid = str(previous)
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self._select_hwnd(previous)
        elif self.selected_hwnd not in self.windows:
            self.selected_hwnd = None
            self._set_controls_enabled(False)
            self.selection_label.configure(text="Выберите окно слева")
        self.status_var.set(f"Найдено окон: {len(items)}")

    def _populate_tree(self) -> None:
        if not hasattr(self, "tree"):
            return
        selected = self.selected_hwnd
        for item in self.tree.get_children():
            self.tree.delete(item)
        needle = self.search_var.get().strip().casefold()
        visible_count = 0
        for info in self.windows.values():
            if needle and needle not in info.title.casefold() and needle not in info.process.casefold():
                continue
            pinned = self._is_topmost(info.hwnd)
            status = "● Закреплено" if pinned else "Обычное"
            self.tree.insert("", "end", iid=str(info.hwnd), text=info.title, values=(info.process, status))
            visible_count += 1
        self.count_label.configure(text=str(visible_count))
        if selected is not None and self.tree.exists(str(selected)):
            self.tree.selection_set(str(selected))

    def _is_topmost(self, hwnd: int) -> bool:
        if not user32.IsWindow(hwnd):
            return False
        try:
            return bool(get_exstyle(hwnd) & WS_EX_TOPMOST)
        except OSError:
            return False

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self._select_hwnd(int(selection[0]))

    def _select_hwnd(self, hwnd: int) -> None:
        if hwnd not in self.windows or not user32.IsWindow(hwnd):
            return
        self.selected_hwnd = hwnd
        info = self.windows[hwnd]
        self.selection_label.configure(text=f"{info.title}\n{info.process}")
        opacity = self.opacity_by_hwnd.get(hwnd, 100)
        self.opacity_var.set(opacity)
        self.opacity_label.configure(text=f"{opacity}%")
        self._set_controls_enabled(True)
        self._update_pin_button()

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.pin_button.configure(state=state)
        self.scale.configure(state=state)

    def _remember_original(self, hwnd: int) -> None:
        if hwnd not in self.original_states:
            exstyle = get_exstyle(hwnd)
            state = OriginalState(exstyle=exstyle, was_topmost=bool(exstyle & WS_EX_TOPMOST))
            if exstyle & WS_EX_LAYERED:
                color = wintypes.COLORREF()
                alpha = wintypes.BYTE()
                flags = wintypes.DWORD()
                if user32.GetLayeredWindowAttributes(hwnd, ctypes.byref(color), ctypes.byref(alpha), ctypes.byref(flags)):
                    state.layered_color = int(color.value)
                    state.layered_alpha = int(alpha.value)
                    state.layered_flags = int(flags.value)
            self.original_states[hwnd] = state

    def toggle_pin(self) -> None:
        hwnd = self.selected_hwnd
        if hwnd is None or not user32.IsWindow(hwnd):
            self._window_missing()
            return
        try:
            self._remember_original(hwnd)
            now_topmost = self._is_topmost(hwnd)
            target = HWND_NOTOPMOST if now_topmost else HWND_TOPMOST
            if not user32.SetWindowPos(hwnd, target, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER):
                raise win_error("Не удалось изменить закрепление")
            self.status_var.set("Закрепление снято" if now_topmost else "Окно закреплено поверх остальных")
            self._update_pin_button()
            self._populate_tree()
        except OSError as error:
            messagebox.showerror("Не удалось изменить окно", str(error), parent=self)

    def _update_pin_button(self) -> None:
        if self.selected_hwnd is None:
            return
        if self._is_topmost(self.selected_hwnd):
            self.pin_button.configure(text="Снять закрепление", bg=self.RED, activebackground="#FC8A9C")
        else:
            self.pin_button.configure(text="Закрепить поверх окон", bg=self.ACCENT, activebackground=self.ACCENT_HOVER)

    def _opacity_preview(self, value: str) -> None:
        percent = round(float(value))
        self.opacity_label.configure(text=f"{percent}%")

    def _apply_opacity_event(self, _event=None) -> None:
        self.apply_opacity(round(float(self.scale.get())))

    def apply_opacity(self, percent: int) -> None:
        hwnd = self.selected_hwnd
        if hwnd is None or not user32.IsWindow(hwnd):
            self._window_missing()
            return
        percent = max(20, min(100, int(percent)))
        try:
            self._remember_original(hwnd)
            current_style = get_exstyle(hwnd)
            if percent < 100:
                if not current_style & WS_EX_LAYERED:
                    ctypes.set_last_error(0)
                    SetWindowLong(hwnd, GWL_EXSTYLE, current_style | WS_EX_LAYERED)
                    if ctypes.get_last_error():
                        raise win_error("Не удалось включить прозрачность")
                alpha = round(255 * percent / 100)
                if not user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA):
                    raise win_error("Не удалось изменить прозрачность")
            else:
                if not user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA):
                    if current_style & WS_EX_LAYERED:
                        raise win_error("Не удалось вернуть непрозрачность")
                original = self.original_states.get(hwnd)
                if original and not original.exstyle & WS_EX_LAYERED:
                    SetWindowLong(hwnd, GWL_EXSTYLE, get_exstyle(hwnd) & ~WS_EX_LAYERED)
            self.opacity_by_hwnd[hwnd] = percent
            self.opacity_var.set(percent)
            self.opacity_label.configure(text=f"{percent}%")
            self.status_var.set(f"Прозрачность окна: {percent}%")
        except OSError as error:
            messagebox.showerror("Не удалось изменить окно", str(error), parent=self)

    def reset_opacity(self) -> None:
        self.apply_opacity(100)

    def capture_foreground(self) -> None:
        self.status_var.set("Переключитесь на нужное окно. Осталось 3 секунды...")
        self.iconify()
        self.after(3000, self._finish_capture)

    def _finish_capture(self) -> None:
        hwnd = int(user32.GetForegroundWindow() or 0)
        self.deiconify()
        self.lift()
        self.focus_force()
        self.refresh_windows(keep_selection=False)
        if hwnd in self.windows:
            self._select_hwnd(hwnd)
            iid = str(hwnd)
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)
            self.status_var.set("Окно выбрано")
        else:
            self.status_var.set("Окно не найдено. Попробуйте выбрать его в списке")

    def _window_missing(self) -> None:
        self.status_var.set("Выбранное окно уже закрыто")
        self.refresh_windows(keep_selection=False)

    def _restore_windows(self) -> None:
        for hwnd, original in list(self.original_states.items()):
            if not user32.IsWindow(hwnd):
                continue
            target = HWND_TOPMOST if original.was_topmost else HWND_NOTOPMOST
            user32.SetWindowPos(hwnd, target, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
            if original.exstyle & WS_EX_LAYERED:
                SetWindowLong(hwnd, GWL_EXSTYLE, original.exstyle & ~WS_EX_LAYERED)
            SetWindowLong(hwnd, GWL_EXSTYLE, original.exstyle)
            if original.layered_alpha is not None and original.layered_flags is not None:
                user32.SetLayeredWindowAttributes(
                    hwnd,
                    original.layered_color or 0,
                    original.layered_alpha,
                    original.layered_flags,
                )

    def _on_close(self) -> None:
        if self.restore_on_exit.get():
            self._restore_windows()
        self.destroy()


def main() -> None:
    app = WindowPinner()
    app.mainloop()


if __name__ == "__main__":
    main()

