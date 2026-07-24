from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from watermark_engine import (
    VIDEO_EXTENSIONS,
    WatermarkOptions,
    default_font_path,
    find_binary,
    make_output_path,
    render_video,
)


class WatermarkApp(tk.Tk):
    BG = "#F4F5F8"
    CARD = "#FFFFFF"
    CARD_ALT = "#F8F8FB"
    TEXT = "#191A20"
    MUTED = "#717580"
    BORDER = "#E3E5EA"
    ACCENT = "#6558F5"
    ACCENT_HOVER = "#5547E8"
    ACCENT_SOFT = "#EEECFF"
    PRIMARY = "#4B3FD1"
    PRIMARY_HOVER = "#3D32B5"
    PRIMARY_BORDER = "#30278F"
    SUCCESS = "#1E9D68"
    DANGER = "#D94B57"

    def __init__(self) -> None:
        super().__init__()
        self.title("水印工坊")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        # Tk reports the full macOS screen bounds, including the menu bar and
        # Dock. Reserve a safe area so the fixed export bar is visible on
        # first launch without requiring the user to maximize the window.
        is_macos = sys.platform == "darwin"
        side_safe_area = 40
        top_safe_area = 48 if is_macos else 30
        bottom_safe_area = 90 if is_macos else 50
        available_width = max(760, screen_width - side_safe_area * 2)
        available_height = max(
            480,
            screen_height - top_safe_area - bottom_safe_area,
        )

        window_width = min(1160, available_width)
        window_height = min(760, available_height)
        window_x = max(
            side_safe_area,
            (screen_width - window_width) // 2,
        )
        window_y = top_safe_area + max(
            0,
            (available_height - window_height) // 2,
        )
        self.geometry(
            f"{window_width}x{window_height}+{window_x}+{window_y}"
        )
        self.minsize(
            min(820, window_width),
            min(520, window_height),
        )
        self.configure(bg=self.BG)

        self.video_paths: list[str] = []
        self.output_dir = tk.StringVar(
            value=str(Path.home() / "Movies" / "Watermarked")
        )
        self.mode = tk.StringVar(value="动态文字水印")
        self.image_path = tk.StringVar()
        self.watermark_text = tk.StringVar(value="© Your Brand")
        self.position = tk.StringVar(value="右下")
        self.opacity = tk.DoubleVar(value=38)
        self.size_percent = tk.DoubleVar(value=5)
        self.margin = tk.IntVar(value=24)
        initial_font_path = default_font_path()
        self.font_path = tk.StringVar(value=initial_font_path)
        self.font_display = tk.StringVar(
            value=(
                Path(initial_font_path).stem
                if initial_font_path
                else "系统默认字体"
            )
        )
        self.font_color = tk.StringVar(value="white")
        self.motion_style = tk.StringVar(value="斜向流动")
        self.speed = tk.DoubleVar(value=70)
        self.density = tk.IntVar(value=5)
        self.quality = tk.StringVar(value="高质量")
        self.status = tk.StringVar(value="等待添加视频")
        self.file_count = tk.StringVar(value="0 个视频")
        self.progress = tk.DoubleVar(value=0)

        self.events: queue.Queue = queue.Queue()
        self.current_process: subprocess.Popen | None = None
        self.cancelled = False
        self.running = False
        self.last_output_dir = ""
        self.job_paths: list[str] = []
        self.job_output_dir = ""
        self.job_options = WatermarkOptions()
        self.preview_phase = 0.0

        self._configure_styles()
        self._build_ui()
        self._refresh_mode_ui()
        self.after(100, self._poll_events)
        self.after(80, self._animate_dynamic_preview)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Files.Treeview",
            background=self.CARD,
            fieldbackground=self.CARD,
            foreground=self.TEXT,
            rowheight=34,
            borderwidth=0,
            font=("Helvetica Neue", 11),
        )
        style.map(
            "Files.Treeview",
            background=[("selected", self.ACCENT_SOFT)],
            foreground=[("selected", self.TEXT)],
        )
        style.configure(
            "Files.Treeview.Heading",
            background=self.CARD_ALT,
            foreground=self.MUTED,
            borderwidth=0,
            font=("Helvetica Neue", 10, "bold"),
        )
        style.map("Files.Treeview.Heading", background=[("active", self.CARD_ALT)])
        style.configure(
            "Clean.Horizontal.TProgressbar",
            troughcolor="#E7E8ED",
            background=self.ACCENT,
            borderwidth=0,
            thickness=8,
        )
        style.configure(
            "Clean.Horizontal.TScale",
            background=self.CARD,
            troughcolor="#E4E5EA",
            borderwidth=0,
        )

    def _build_ui(self) -> None:
        shell = tk.Frame(self, bg=self.BG)
        shell.pack(fill="both", expand=True, padx=28, pady=(24, 22))

        self._build_header(shell)

        content = tk.Frame(shell, bg=self.BG)
        content.pack(fill="both", expand=True, pady=(20, 16))
        content.grid_columnconfigure(0, weight=46, uniform="content")
        content.grid_columnconfigure(1, weight=54, uniform="content")
        content.grid_rowconfigure(0, weight=1)

        left = self._card(content)
        right = self._card(content)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        self._build_file_panel(left)
        self._build_settings_panel(right)
        self._build_action_bar(shell)

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=self.BG)
        header.pack(fill="x")

        logo = tk.Label(
            header,
            text="W",
            bg=self.ACCENT,
            fg="white",
            width=3,
            height=1,
            font=("Helvetica Neue", 20, "bold"),
        )
        logo.pack(side="left")

        titles = tk.Frame(header, bg=self.BG)
        titles.pack(side="left", padx=13)
        tk.Label(
            titles,
            text="水印工坊",
            bg=self.BG,
            fg=self.TEXT,
            font=("Helvetica Neue", 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            titles,
            text="批量添加视频水印，所有素材仅在本地处理",
            bg=self.BG,
            fg=self.MUTED,
            font=("Helvetica Neue", 10),
        ).pack(anchor="w", pady=(2, 0))

        self.ffmpeg_badge = tk.Label(
            header,
            text="●  FFmpeg 已就绪",
            bg="#E8F7F0",
            fg=self.SUCCESS,
            padx=12,
            pady=7,
            font=("Helvetica Neue", 10, "bold"),
        )
        self.ffmpeg_badge.pack(side="right")
        self._update_ffmpeg_badge()

    def _build_file_panel(self, parent: tk.Frame) -> None:
        body = tk.Frame(parent, bg=self.CARD)
        body.pack(fill="both", expand=True, padx=20, pady=18)

        self._section_heading(
            body,
            "1",
            "选择视频",
            "可一次添加多个视频，系统会按顺序批量处理",
        )

        add_area = tk.Frame(
            body,
            bg=self.CARD_ALT,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            height=94,
        )
        add_area.pack(fill="x", pady=(15, 12))
        add_area.pack_propagate(False)

        add_copy = tk.Frame(add_area, bg=self.CARD_ALT)
        add_copy.pack(side="left", padx=18, pady=15)
        tk.Label(
            add_copy,
            text="把需要处理的视频添加到列表",
            bg=self.CARD_ALT,
            fg=self.TEXT,
            font=("Helvetica Neue", 11, "bold"),
        ).pack(anchor="w")
        tk.Label(
            add_copy,
            text="MP4、MOV、MKV、AVI、WebM",
            bg=self.CARD_ALT,
            fg=self.MUTED,
            font=("Helvetica Neue", 9),
        ).pack(anchor="w", pady=(5, 0))

        self._button(
            add_area,
            "+  添加视频",
            self._add_videos,
            primary=True,
            padx=16,
            pady=9,
        ).pack(side="right", padx=16)

        list_header = tk.Frame(body, bg=self.CARD)
        list_header.pack(fill="x", pady=(2, 7))
        tk.Label(
            list_header,
            text="视频列表",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Helvetica Neue", 10, "bold"),
        ).pack(side="left")
        tk.Label(
            list_header,
            textvariable=self.file_count,
            bg=self.CARD,
            fg=self.MUTED,
            font=("Helvetica Neue", 10),
        ).pack(side="right")

        list_wrap = tk.Frame(
            body,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        list_wrap.pack(fill="both", expand=True)

        self.video_list = ttk.Treeview(
            list_wrap,
            columns=("name", "size"),
            show="headings",
            selectmode="extended",
            style="Files.Treeview",
        )
        self.video_list.heading("name", text="文件名")
        self.video_list.heading("size", text="大小")
        self.video_list.column("name", width=285, minwidth=160, anchor="w")
        self.video_list.column("size", width=75, minwidth=65, anchor="e")
        self.video_list.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            list_wrap, orient="vertical", command=self.video_list.yview
        )
        scrollbar.pack(side="right", fill="y")
        self.video_list.configure(yscrollcommand=scrollbar.set)

        list_actions = tk.Frame(body, bg=self.CARD)
        list_actions.pack(fill="x", pady=(10, 17))
        self._text_button(
            list_actions, "移除所选", self._remove_selected
        ).pack(side="left")
        self._text_button(
            list_actions, "清空列表", self._clear_videos, danger=True
        ).pack(side="left", padx=16)

        divider = tk.Frame(body, bg=self.BORDER, height=1)
        divider.pack(fill="x", pady=(0, 15))

        self._section_heading(
            body,
            "2",
            "保存位置",
            "同名文件会自动编号，不会覆盖原文件",
            compact=True,
        )
        output_row = tk.Frame(body, bg=self.CARD)
        output_row.pack(fill="x", pady=(12, 0))
        self.output_entry = tk.Entry(
            output_row,
            textvariable=self.output_dir,
            bg=self.CARD_ALT,
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="flat",
            highlightbackground=self.BORDER,
            highlightcolor=self.ACCENT,
            highlightthickness=1,
            font=("Helvetica Neue", 10),
        )
        self.output_entry.pack(side="left", fill="x", expand=True, ipady=9)
        self._button(
            output_row,
            "浏览…",
            self._choose_output,
            primary=False,
            padx=14,
            pady=8,
        ).pack(side="left", padx=(9, 0))

    def _build_settings_panel(self, parent: tk.Frame) -> None:
        scroll_container = tk.Frame(parent, bg=self.CARD)
        scroll_container.pack(fill="both", expand=True)

        self.settings_canvas = tk.Canvas(
            scroll_container,
            bg=self.CARD,
            highlightthickness=0,
            bd=0,
        )
        settings_scrollbar = ttk.Scrollbar(
            scroll_container,
            orient="vertical",
            command=self.settings_canvas.yview,
        )
        self.settings_canvas.configure(
            yscrollcommand=settings_scrollbar.set
        )
        settings_scrollbar.pack(side="right", fill="y")
        self.settings_canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(self.settings_canvas, bg=self.CARD)
        self.settings_window = self.settings_canvas.create_window(
            (0, 0),
            window=body,
            anchor="nw",
        )
        body.bind("<Configure>", self._on_settings_content_resize)
        self.settings_canvas.bind(
            "<Configure>", self._on_settings_canvas_resize
        )
        self.bind_all(
            "<MouseWheel>", self._on_settings_mousewheel, add="+"
        )
        self.bind_all(
            "<Button-4>", self._on_settings_mousewheel, add="+"
        )
        self.bind_all(
            "<Button-5>", self._on_settings_mousewheel, add="+"
        )

        body.configure(padx=20, pady=18)

        self._section_heading(
            body,
            "3",
            "设置水印",
            "选择水印类型，再调整显示效果",
        )

        mode_switch = tk.Frame(body, bg=self.CARD_ALT)
        mode_switch.pack(fill="x", pady=(15, 13))
        self.mode_buttons: dict[str, tk.Radiobutton] = {}
        for value, label in (
            ("动态文字水印", "↗  动态文字"),
            ("图片水印", "▧  图片"),
            ("文字水印", "T  静态文字"),
        ):
            button = tk.Radiobutton(
                mode_switch,
                text=label,
                value=value,
                variable=self.mode,
                command=self._refresh_mode_ui,
                indicatoron=False,
                relief="flat",
                bd=0,
                bg=self.CARD_ALT,
                fg=self.MUTED,
                selectcolor=self.ACCENT_SOFT,
                activebackground=self.ACCENT_SOFT,
                activeforeground=self.ACCENT,
                font=("Helvetica Neue", 10, "bold"),
                padx=16,
                pady=9,
                cursor="hand2",
            )
            button.pack(side="left", fill="x", expand=True, padx=2, pady=2)
            self.mode_buttons[value] = button

        self.mode_content = tk.Frame(body, bg=self.CARD)
        self.mode_content.pack(fill="x")
        self._build_image_settings(self.mode_content)
        self._build_text_settings(self.mode_content)
        self._build_dynamic_settings(body)

        self.settings_divider = tk.Frame(body, bg=self.BORDER, height=1)
        self.settings_divider.pack(fill="x", pady=14)

        self.position_label = tk.Label(
            body,
            text="水印位置",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Helvetica Neue", 10, "bold"),
        )
        self.position_label.pack(anchor="w")

        self.position_wrap = tk.Frame(body, bg=self.CARD)
        self.position_wrap.pack(fill="x", pady=(9, 12))
        positions = [
            ("左上", "↖"), ("顶部居中", "↑"), ("右上", "↗"),
            ("左侧居中", "←"), ("正中", "●"), ("右侧居中", "→"),
            ("左下", "↙"), ("底部居中", "↓"), ("右下", "↘"),
        ]
        for column in range(3):
            self.position_wrap.grid_columnconfigure(column, weight=1)
        self.position_buttons: dict[str, tk.Radiobutton] = {}
        for index, (value, symbol) in enumerate(positions):
            button = tk.Radiobutton(
                self.position_wrap,
                text=symbol,
                value=value,
                variable=self.position,
                indicatoron=False,
                relief="flat",
                bd=0,
                bg=self.CARD_ALT,
                fg=self.MUTED,
                selectcolor=self.ACCENT_SOFT,
                activebackground=self.ACCENT_SOFT,
                activeforeground=self.ACCENT,
                font=("Helvetica Neue", 14, "bold"),
                height=1,
                cursor="hand2",
            )
            button.grid(
                row=index // 3,
                column=index % 3,
                sticky="ew",
                padx=3,
                pady=3,
                ipady=3,
            )
            self.position_buttons[value] = button

        sliders = tk.Frame(body, bg=self.CARD)
        sliders.pack(fill="x")
        self._slider_row(sliders, "透明度", self.opacity, 5, 100, "%")
        self._slider_row(sliders, "文字大小", self.size_percent, 2, 24, "%")
        self.margin_row = self._slider_row(
            sliders, "边缘距离", self.margin, 0, 100, " px"
        )

        tk.Frame(body, bg=self.BORDER, height=1).pack(fill="x", pady=14)

        tk.Label(
            body,
            text="导出质量",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Helvetica Neue", 10, "bold"),
        ).pack(anchor="w")

        quality_wrap = tk.Frame(body, bg=self.CARD)
        quality_wrap.pack(fill="x", pady=(9, 0))
        qualities = [
            ("高质量", "画质优先"),
            ("均衡", "推荐日常使用"),
            ("小体积", "节省空间"),
        ]
        for column in range(3):
            quality_wrap.grid_columnconfigure(column, weight=1)
        self.quality_buttons: dict[str, tk.Radiobutton] = {}
        for index, (value, description) in enumerate(qualities):
            option = tk.Radiobutton(
                quality_wrap,
                text=f"{value}\n{description}",
                value=value,
                variable=self.quality,
                command=self._refresh_quality_ui,
                indicatoron=False,
                justify="center",
                relief="flat",
                bd=0,
                bg=self.CARD_ALT,
                fg=self.TEXT,
                selectcolor=self.CARD_ALT,
                activebackground=self.ACCENT_SOFT,
                activeforeground=self.ACCENT,
                highlightbackground=self.BORDER,
                highlightcolor=self.BORDER,
                highlightthickness=1,
                font=("Helvetica Neue", 9, "bold"),
                cursor="hand2",
                pady=8,
            )
            option.grid(row=0, column=index, sticky="ew", padx=3)
            self.quality_buttons[value] = option
        self._refresh_quality_ui()

    def _refresh_quality_ui(self) -> None:
        """Keep the export-quality selection visible on every Tk platform."""
        for value, button in self.quality_buttons.items():
            selected = value == self.quality.get()
            button.configure(
                bg=self.PRIMARY if selected else self.CARD_ALT,
                fg="white" if selected else self.TEXT,
                selectcolor=self.PRIMARY if selected else self.CARD_ALT,
                activebackground=(
                    self.PRIMARY_HOVER if selected else self.ACCENT_SOFT
                ),
                activeforeground="white" if selected else self.ACCENT,
                highlightbackground=(
                    self.PRIMARY_BORDER if selected else self.BORDER
                ),
                highlightcolor=(
                    self.PRIMARY_BORDER if selected else self.BORDER
                ),
            )

    def _on_settings_content_resize(self, _event=None) -> None:
        self.settings_canvas.configure(
            scrollregion=self.settings_canvas.bbox("all")
        )

    def _on_settings_canvas_resize(self, event) -> None:
        self.settings_canvas.itemconfigure(
            self.settings_window,
            width=event.width,
        )

    def _pointer_is_over_settings(self) -> bool:
        pointer_x, pointer_y = self.winfo_pointerxy()
        left = self.settings_canvas.winfo_rootx()
        top = self.settings_canvas.winfo_rooty()
        right = left + self.settings_canvas.winfo_width()
        bottom = top + self.settings_canvas.winfo_height()
        return left <= pointer_x <= right and top <= pointer_y <= bottom

    def _on_settings_mousewheel(self, event) -> None:
        if not self._pointer_is_over_settings():
            return
        if getattr(event, "num", None) == 4:
            units = -2
        elif getattr(event, "num", None) == 5:
            units = 2
        else:
            delta = getattr(event, "delta", 0)
            if delta == 0:
                return
            units = -1 if delta > 0 else 1
            if abs(delta) >= 120:
                units *= max(1, abs(int(delta / 120)))
        self.settings_canvas.yview_scroll(units, "units")

    def _build_image_settings(self, parent: tk.Frame) -> None:
        self.image_panel = tk.Frame(parent, bg=self.CARD)
        tk.Label(
            self.image_panel,
            text="水印图片",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Helvetica Neue", 10, "bold"),
        ).pack(anchor="w")

        row = tk.Frame(self.image_panel, bg=self.CARD)
        row.pack(fill="x", pady=(8, 0))
        entry = tk.Entry(
            row,
            textvariable=self.image_path,
            bg=self.CARD_ALT,
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="flat",
            highlightbackground=self.BORDER,
            highlightcolor=self.ACCENT,
            highlightthickness=1,
            font=("Helvetica Neue", 10),
        )
        entry.pack(side="left", fill="x", expand=True, ipady=8)
        self._button(
            row, "选择图片", self._choose_image, padx=13, pady=8
        ).pack(side="left", padx=(8, 0))
        tk.Label(
            self.image_panel,
            text="推荐使用透明背景 PNG，画面会更干净",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Helvetica Neue", 9),
        ).pack(anchor="w", pady=(6, 0))

    def _build_text_settings(self, parent: tk.Frame) -> None:
        self.text_panel = tk.Frame(parent, bg=self.CARD)
        tk.Label(
            self.text_panel,
            text="水印文字",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Helvetica Neue", 10, "bold"),
        ).pack(anchor="w")

        entry = tk.Entry(
            self.text_panel,
            textvariable=self.watermark_text,
            bg=self.CARD_ALT,
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="flat",
            highlightbackground=self.BORDER,
            highlightcolor=self.ACCENT,
            highlightthickness=1,
            font=("Helvetica Neue", 11),
        )
        entry.pack(fill="x", pady=(8, 9), ipady=8)

        color_row = tk.Frame(self.text_panel, bg=self.CARD)
        color_row.pack(fill="x")
        tk.Label(
            color_row,
            text="文字颜色",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Helvetica Neue", 9),
        ).pack(side="left")
        self.color_swatch = tk.Label(
            color_row,
            text="",
            bg="#FFFFFF",
            width=3,
            height=1,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        self.color_swatch.pack(side="left", padx=(10, 6))
        self.color_value = tk.Label(
            color_row,
            textvariable=self.font_color,
            bg=self.CARD,
            fg=self.TEXT,
            font=("Helvetica Neue", 9),
        )
        self.color_value.pack(side="left")
        self._text_button(
            color_row, "更改颜色", self._choose_color
        ).pack(side="right")

        font_row = tk.Frame(self.text_panel, bg=self.CARD)
        font_row.pack(fill="x", pady=(10, 0))
        tk.Label(
            font_row,
            text="水印字体",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Helvetica Neue", 9),
        ).pack(side="left")
        tk.Label(
            font_row,
            textvariable=self.font_display,
            bg=self.CARD_ALT,
            fg=self.TEXT,
            anchor="w",
            padx=9,
            pady=5,
            font=("Helvetica Neue", 9, "bold"),
        ).pack(side="left", fill="x", expand=True, padx=(10, 8))
        self._button(
            font_row,
            "选择字体…",
            self._choose_font,
            padx=10,
            pady=5,
        ).pack(side="left")
        self._text_button(
            font_row,
            "恢复默认",
            self._reset_font,
        ).pack(side="left", padx=(9, 0))

        tk.Label(
            self.text_panel,
            text="支持 TTF、OTF、TTC；视频导出会使用所选字体文件",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Helvetica Neue", 8),
        ).pack(anchor="w", pady=(6, 0))

    def _build_dynamic_settings(self, parent: tk.Frame) -> None:
        self.dynamic_options_panel = tk.Frame(parent, bg=self.CARD)

        tk.Label(
            self.dynamic_options_panel,
            text="动态效果预览",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Helvetica Neue", 10, "bold"),
        ).pack(anchor="w", pady=(11, 7))

        self.preview_canvas = tk.Canvas(
            self.dynamic_options_panel,
            height=94,
            bg="#252832",
            highlightbackground=self.BORDER,
            highlightthickness=1,
            bd=0,
        )
        self.preview_canvas.pack(fill="x")

        tk.Label(
            self.dynamic_options_panel,
            text="流动方向",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Helvetica Neue", 9),
        ).pack(anchor="w", pady=(11, 6))

        direction_row = tk.Frame(self.dynamic_options_panel, bg=self.CARD)
        direction_row.pack(fill="x")
        directions = [
            ("向左流动", "←"),
            ("向右流动", "→"),
            ("向上流动", "↑"),
            ("向下流动", "↓"),
            ("斜向流动", "↗"),
        ]
        for column in range(len(directions)):
            direction_row.grid_columnconfigure(column, weight=1)
        self.direction_buttons: dict[str, tk.Radiobutton] = {}
        for column, (value, symbol) in enumerate(directions):
            button = tk.Radiobutton(
                direction_row,
                text=f"{symbol}  {value[:2]}",
                value=value,
                variable=self.motion_style,
                indicatoron=False,
                relief="flat",
                bd=0,
                bg=self.CARD_ALT,
                fg=self.MUTED,
                selectcolor=self.ACCENT_SOFT,
                activebackground=self.ACCENT_SOFT,
                activeforeground=self.ACCENT,
                font=("Helvetica Neue", 8, "bold"),
                cursor="hand2",
                pady=6,
            )
            button.grid(row=0, column=column, sticky="ew", padx=2)
            self.direction_buttons[value] = button

        dynamic_sliders = tk.Frame(self.dynamic_options_panel, bg=self.CARD)
        dynamic_sliders.pack(fill="x", pady=(7, 0))
        self._slider_row(
            dynamic_sliders, "流动速度", self.speed, 10, 240, " px/s"
        )
        self._slider_row(
            dynamic_sliders, "密铺程度", self.density, 1, 10, " 级"
        )

    def _build_action_bar(self, parent: tk.Frame) -> None:
        bar = tk.Frame(
            parent,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        bar.pack(fill="x")

        left = tk.Frame(bar, bg=self.CARD)
        left.pack(side="left", fill="x", expand=True, padx=18, pady=13)
        status_row = tk.Frame(left, bg=self.CARD)
        status_row.pack(fill="x")
        tk.Label(
            status_row,
            textvariable=self.status,
            bg=self.CARD,
            fg=self.TEXT,
            font=("Helvetica Neue", 10, "bold"),
        ).pack(side="left")
        self.progress_label = tk.Label(
            status_row,
            text="",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Helvetica Neue", 9),
        )
        self.progress_label.pack(side="right")
        ttk.Progressbar(
            left,
            variable=self.progress,
            maximum=100,
            style="Clean.Horizontal.TProgressbar",
        ).pack(fill="x", pady=(8, 0))

        actions = tk.Frame(bar, bg=self.CARD)
        actions.pack(side="right", padx=14, pady=11)
        self.open_button = self._button(
            actions,
            "打开输出文件夹",
            self._open_output_folder,
            padx=14,
            pady=10,
        )
        self.open_button.configure(state="disabled")
        self.open_button.pack(side="left", padx=(0, 8))
        self.cancel_button = self._button(
            actions,
            "取消",
            self._cancel,
            padx=13,
            pady=10,
        )
        self.cancel_button.configure(state="disabled")
        self.cancel_button.pack(side="left", padx=(0, 8))
        self.start_button = self._button(
            actions,
            "开始批量导出  →",
            self._start,
            primary=True,
            padx=18,
            pady=10,
        )
        self.start_button.pack(side="left")

    def _card(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )

    def _section_heading(
        self,
        parent: tk.Frame,
        number: str,
        title: str,
        subtitle: str,
        compact: bool = False,
    ) -> None:
        row = tk.Frame(parent, bg=self.CARD)
        row.pack(fill="x")
        badge = tk.Label(
            row,
            text=number,
            bg=self.ACCENT_SOFT,
            fg=self.ACCENT,
            width=2,
            font=("Helvetica Neue", 10, "bold"),
        )
        badge.pack(side="left", anchor="n", ipady=3)
        copy = tk.Frame(row, bg=self.CARD)
        copy.pack(side="left", padx=10)
        tk.Label(
            copy,
            text=title,
            bg=self.CARD,
            fg=self.TEXT,
            font=("Helvetica Neue", 13 if not compact else 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            copy,
            text=subtitle,
            bg=self.CARD,
            fg=self.MUTED,
            font=("Helvetica Neue", 9),
        ).pack(anchor="w", pady=(2, 0))

    def _button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        primary: bool = False,
        padx: int = 12,
        pady: int = 7,
    ) -> tk.Button:
        background = self.PRIMARY if primary else self.CARD
        foreground = "white" if primary else self.TEXT
        active_background = self.PRIMARY_HOVER if primary else self.CARD_ALT
        border = self.PRIMARY_BORDER if primary else self.BORDER
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=active_background,
            activeforeground=foreground,
            disabledforeground="#A5A8B0",
            relief="flat",
            bd=0,
            highlightbackground=border,
            highlightcolor=border,
            highlightthickness=1,
            font=("Helvetica Neue", 10, "bold"),
            padx=padx,
            pady=pady,
            cursor="hand2",
        )

    def _text_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        danger: bool = False,
    ) -> tk.Button:
        color = self.DANGER if danger else self.ACCENT
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.CARD,
            fg=color,
            activebackground=self.CARD,
            activeforeground=color,
            relief="flat",
            bd=0,
            font=("Helvetica Neue", 9, "bold"),
            padx=0,
            pady=0,
            cursor="hand2",
        )

    def _slider_row(
        self,
        parent: tk.Frame,
        label: str,
        variable: tk.Variable,
        start: float,
        end: float,
        suffix: str,
    ) -> tk.Frame:
        row = tk.Frame(parent, bg=self.CARD)
        row.pack(fill="x", pady=4)
        tk.Label(
            row,
            text=label,
            bg=self.CARD,
            fg=self.MUTED,
            width=9,
            anchor="w",
            font=("Helvetica Neue", 9),
        ).pack(side="left")
        ttk.Scale(
            row,
            variable=variable,
            from_=start,
            to=end,
            style="Clean.Horizontal.TScale",
        ).pack(side="left", fill="x", expand=True)
        value_label = tk.Label(
            row,
            text="",
            bg=self.CARD_ALT,
            fg=self.TEXT,
            width=7,
            font=("Helvetica Neue", 9, "bold"),
        )
        value_label.pack(side="left", padx=(10, 0), ipady=3)

        def update(*_: object) -> None:
            value_label.configure(
                text=f"{int(round(float(variable.get())))}{suffix}"
            )

        variable.trace_add("write", update)
        update()
        return row

    def _update_ffmpeg_badge(self) -> None:
        try:
            find_binary("ffmpeg")
            find_binary("ffprobe")
        except FileNotFoundError:
            self.ffmpeg_badge.configure(
                text="●  FFmpeg 未找到",
                bg="#FCEBED",
                fg=self.DANGER,
            )

    def _refresh_mode_ui(self) -> None:
        for value, button in self.mode_buttons.items():
            selected = value == self.mode.get()
            button.configure(
                fg=self.ACCENT if selected else self.MUTED,
                bg=self.ACCENT_SOFT if selected else self.CARD_ALT,
            )
        self.image_panel.pack_forget()
        self.text_panel.pack_forget()
        self.dynamic_options_panel.pack_forget()
        if self.mode.get() == "图片水印":
            self.image_panel.pack(fill="x")
        elif self.mode.get() == "文字水印":
            self.text_panel.pack(fill="x")
        else:
            self.text_panel.pack(fill="x")
            self.dynamic_options_panel.pack(
                fill="x", after=self.mode_content
            )

        is_dynamic = self.mode.get() == "动态文字水印"
        if is_dynamic:
            self.position_label.pack_forget()
            self.position_wrap.pack_forget()
            self.margin_row.pack_forget()
        else:
            if not self.position_label.winfo_manager():
                self.position_label.pack(
                    anchor="w", after=self.settings_divider
                )
            if not self.position_wrap.winfo_manager():
                self.position_wrap.pack(
                    fill="x",
                    pady=(9, 12),
                    after=self.position_label,
                )
            if not self.margin_row.winfo_manager():
                self.margin_row.pack(fill="x", pady=4)

    def _preview_color(self) -> str:
        background = self.preview_canvas.cget("bg")
        try:
            fg_rgb = self.winfo_rgb(self.font_color.get())
            bg_rgb = self.winfo_rgb(background)
        except tk.TclError:
            fg_rgb = self.winfo_rgb("white")
            bg_rgb = self.winfo_rgb(background)
        alpha = max(0.05, min(self.opacity.get() / 100, 1.0))
        channels = []
        for fg, bg in zip(fg_rgb, bg_rgb):
            blended = int((fg * alpha + bg * (1 - alpha)) / 257)
            channels.append(max(0, min(blended, 255)))
        return f"#{channels[0]:02x}{channels[1]:02x}{channels[2]:02x}"

    def _animate_dynamic_preview(self) -> None:
        try:
            if (
                hasattr(self, "preview_canvas")
                and self.mode.get() == "动态文字水印"
                and self.preview_canvas.winfo_ismapped()
            ):
                canvas = self.preview_canvas
                width = max(canvas.winfo_width(), 420)
                height = max(canvas.winfo_height(), 94)
                canvas.delete("watermark")

                speed = max(1.0, float(self.speed.get()))
                self.preview_phase = (
                    self.preview_phase + speed * 0.0032
                ) % max(width, height)
                density = max(1, min(int(self.density.get()), 10))
                columns = 2 + round(density * 0.6)
                rows = 1 + round(density * 0.4)
                text = self.watermark_text.get().strip() or "Your Watermark"
                font_size = max(
                    9, min(int(height * self.size_percent.get() / 100 * 2.2), 24)
                )
                color = self._preview_color()
                direction = self.motion_style.get()

                for row in range(rows):
                    for column in range(columns):
                        x = (column + 0.25) / columns * width
                        y = (row + 0.35) / rows * height
                        phase = self.preview_phase
                        if direction == "向左流动":
                            x = (x - phase) % (width + 80) - 40
                        elif direction == "向右流动":
                            x = (x + phase) % (width + 80) - 40
                        elif direction == "向上流动":
                            y = (y - phase) % (height + 30) - 15
                        elif direction == "向下流动":
                            y = (y + phase) % (height + 30) - 15
                        else:
                            x = (x - phase) % (width + 80) - 40
                            y = (y + phase * 0.58) % (height + 30) - 15
                        canvas.create_text(
                            x,
                            y,
                            text=text,
                            fill=color,
                            font=("Helvetica Neue", font_size, "bold"),
                            tags="watermark",
                        )
        finally:
            self.after(50, self._animate_dynamic_preview)

    @staticmethod
    def _format_size(path: str) -> str:
        try:
            size = Path(path).stat().st_size
        except OSError:
            return "—"
        if size >= 1024 ** 3:
            return f"{size / 1024 ** 3:.1f} GB"
        if size >= 1024 ** 2:
            return f"{size / 1024 ** 2:.1f} MB"
        return f"{size / 1024:.0f} KB"

    def _update_file_summary(self) -> None:
        count = len(self.video_paths)
        self.file_count.set(f"{count} 个视频")
        self.status.set("等待添加视频" if count == 0 else f"已准备 {count} 个视频")

    def _add_videos(self) -> None:
        files = filedialog.askopenfilenames(
            title="选择一个或多个视频",
            filetypes=[
                ("视频文件", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mts *.m2ts"),
                ("所有文件", "*.*"),
            ],
        )
        for file in files:
            if (
                Path(file).suffix.lower() in VIDEO_EXTENSIONS
                and file not in self.video_paths
            ):
                self.video_paths.append(file)
                self.video_list.insert(
                    "",
                    "end",
                    iid=str(len(self.video_paths) - 1),
                    values=(Path(file).name, self._format_size(file)),
                )
        self._rebuild_tree_ids()
        self._update_file_summary()

    def _rebuild_tree_ids(self) -> None:
        selected_paths = {
            self.video_paths[int(item)]
            for item in self.video_list.selection()
            if item.isdigit() and int(item) < len(self.video_paths)
        }
        for item in self.video_list.get_children():
            self.video_list.delete(item)
        for index, path in enumerate(self.video_paths):
            self.video_list.insert(
                "",
                "end",
                iid=str(index),
                values=(Path(path).name, self._format_size(path)),
            )
            if path in selected_paths:
                self.video_list.selection_add(str(index))

    def _remove_selected(self) -> None:
        indices = sorted(
            (int(item) for item in self.video_list.selection()),
            reverse=True,
        )
        for index in indices:
            if 0 <= index < len(self.video_paths):
                self.video_paths.pop(index)
        self._rebuild_tree_ids()
        self._update_file_summary()

    def _clear_videos(self) -> None:
        self.video_paths.clear()
        for item in self.video_list.get_children():
            self.video_list.delete(item)
        self._update_file_summary()

    def _choose_output(self) -> None:
        folder = filedialog.askdirectory(title="选择输出目录")
        if folder:
            self.output_dir.set(folder)

    def _choose_image(self) -> None:
        file = filedialog.askopenfilename(
            title="选择水印图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.webp"),
                ("所有文件", "*.*"),
            ],
        )
        if file:
            self.image_path.set(file)

    def _choose_color(self) -> None:
        color = colorchooser.askcolor(title="选择文字颜色")
        if color[1]:
            self.font_color.set(color[1])
            self.color_swatch.configure(bg=color[1])

    def _choose_font(self) -> None:
        file = filedialog.askopenfilename(
            title="选择水印字体",
            filetypes=[
                ("字体文件", "*.ttf *.otf *.ttc"),
                ("TrueType 字体", "*.ttf *.ttc"),
                ("OpenType 字体", "*.otf"),
                ("所有文件", "*.*"),
            ],
        )
        if not file:
            return
        if Path(file).suffix.lower() not in {".ttf", ".otf", ".ttc"}:
            messagebox.showwarning(
                "不支持的字体格式",
                "请选择 TTF、OTF 或 TTC 字体文件。",
            )
            return
        self.font_path.set(file)
        self.font_display.set(Path(file).stem)

    def _reset_font(self) -> None:
        font_path = default_font_path()
        self.font_path.set(font_path)
        self.font_display.set(
            Path(font_path).stem if font_path else "系统默认字体"
        )

    def _get_watermark_options(self) -> WatermarkOptions:
        crf = {"高质量": 18, "均衡": 21, "小体积": 24}[self.quality.get()]
        return WatermarkOptions(
            mode=self.mode.get(),
            image_path=self.image_path.get(),
            text=self.watermark_text.get(),
            position=self.position.get(),
            opacity=self.opacity.get() / 100,
            size_percent=self.size_percent.get(),
            margin=self.margin.get(),
            font_path=self.font_path.get(),
            font_color=self.font_color.get(),
            motion_style=self.motion_style.get(),
            speed=self.speed.get(),
            density=self.density.get(),
            crf=crf,
        )

    def _validate(self) -> bool:
        try:
            find_binary("ffmpeg")
            find_binary("ffprobe")
        except FileNotFoundError as error:
            messagebox.showerror("FFmpeg 未找到", str(error))
            return False
        if not self.video_paths:
            messagebox.showwarning("还没有视频", "请先添加至少一个视频。")
            return False
        options = self._get_watermark_options()
        if options.mode == "图片水印" and not Path(options.image_path).is_file():
            messagebox.showwarning(
                "缺少水印图片", "请选择 PNG、JPG 或 WebP 水印图片。"
            )
            return False
        if options.mode != "图片水印" and not options.text.strip():
            messagebox.showwarning("缺少文字", "请输入水印文字。")
            return False
        if (
            options.mode != "图片水印"
            and options.font_path
            and not Path(options.font_path).is_file()
        ):
            messagebox.showwarning(
                "字体文件不存在",
                "当前选择的字体文件可能已被移动或删除，请重新选择字体。",
            )
            return False
        if not self.output_dir.get().strip():
            messagebox.showwarning("缺少输出目录", "请选择视频保存位置。")
            return False
        return True

    def _start(self) -> None:
        if self.running or not self._validate():
            return
        self.running = True
        self.cancelled = False
        self.progress.set(0)
        self.progress_label.configure(text="0%")
        self.start_button.configure(state="disabled", cursor="")
        self.cancel_button.configure(state="normal", cursor="hand2")
        self.open_button.configure(state="disabled", cursor="")

        self.job_paths = list(self.video_paths)
        self.job_output_dir = self.output_dir.get()
        self.job_options = self._get_watermark_options()
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        Path(self.job_output_dir).mkdir(parents=True, exist_ok=True)
        total = len(self.job_paths)
        completed = 0
        try:
            for index, input_path in enumerate(self.job_paths, start=1):
                if self.cancelled:
                    break
                output_path = make_output_path(input_path, self.job_output_dir)
                self.events.put(
                    (
                        "status",
                        f"正在处理 {index}/{total} · {Path(input_path).name}",
                    )
                )

                def on_progress(value: float, item=index) -> None:
                    overall = ((item - 1) + value) / total * 100
                    self.events.put(("progress", overall))

                render_video(
                    input_path,
                    output_path,
                    self.job_options,
                    progress_callback=on_progress,
                    process_callback=lambda process: setattr(
                        self, "current_process", process
                    ),
                )
                completed += 1
            if self.cancelled:
                self.events.put(
                    (
                        "done",
                        f"已取消 · 完成 {completed}/{total} 个视频",
                        self.job_output_dir,
                    )
                )
            else:
                self.events.put(
                    (
                        "done",
                        f"导出完成 · 共 {completed} 个视频",
                        self.job_output_dir,
                    )
                )
        except Exception as error:
            self.events.put(("error", str(error)))
        finally:
            self.current_process = None

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "status":
                    self.status.set(event[1])
                elif event[0] == "progress":
                    value = event[1]
                    self.progress.set(value)
                    self.progress_label.configure(text=f"{int(value)}%")
                elif event[0] == "done":
                    self.running = False
                    self.last_output_dir = event[2]
                    self.start_button.configure(state="normal", cursor="hand2")
                    self.cancel_button.configure(state="disabled", cursor="")
                    self.open_button.configure(state="normal", cursor="hand2")
                    self.status.set(event[1])
                    if not self.cancelled:
                        self.progress.set(100)
                        self.progress_label.configure(text="100%")
                    messagebox.showinfo(
                        "处理完成",
                        f"{event[1]}\n\n文件已保存至：\n{event[2]}",
                    )
                elif event[0] == "error":
                    self.running = False
                    self.start_button.configure(state="normal", cursor="hand2")
                    self.cancel_button.configure(state="disabled", cursor="")
                    self.status.set("处理失败，请查看错误信息")
                    messagebox.showerror("处理失败", event[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _cancel(self) -> None:
        self.cancelled = True
        self.status.set("正在安全取消…")
        if self.current_process and self.current_process.poll() is None:
            self.current_process.terminate()

    def _open_output_folder(self) -> None:
        folder = self.last_output_dir or self.output_dir.get()
        if not folder or not Path(folder).exists():
            messagebox.showwarning("文件夹不存在", "输出文件夹尚未创建。")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            elif os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", folder])
        except OSError as error:
            messagebox.showerror("无法打开文件夹", str(error))

    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno(
                "退出工具", "视频仍在处理中，确定要取消并退出吗？"
            ):
                return
            self._cancel()
        self.destroy()


if __name__ == "__main__":
    WatermarkApp().mainloop()
