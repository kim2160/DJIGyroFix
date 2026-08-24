from __future__ import annotations

import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .detection import DetectionResult, describe_detection, detect_video_jitter
from .i18n import Language, text, translate_error, translate_stage
from .intervals import parse_time_rows
from .processor import (
    ProcessingCancelled,
    ProcessingResult,
    default_output_path,
    process_video_intervals,
)


SMOOTHING_PRESETS: dict[str, float] = {
    "strong": 180.0,
    "medium": 100.0,
    "light": 50.0,
    "very_strong": 300.0,
}
PRESET_KEYS = tuple(SMOOTHING_PRESETS)
IS_MACOS = sys.platform == "darwin"
UI_LAYOUT_SCALE = 0.8 if IS_MACOS else 1.0
UI_FONT_FAMILY = "Apple SD Gothic Neo" if IS_MACOS else "Malgun Gothic"
UI_HINT_FONT_SIZE = 11 if IS_MACOS else 9
UI_FIELD_FONT_SIZE = 10 if IS_MACOS else 9
UI_BUTTON_FONT_SIZE = 12 if IS_MACOS else 10


def _ui_px(value: int) -> int:
    return round(value * UI_LAYOUT_SCALE)


UI_WINDOW_GEOMETRY = f"{_ui_px(800)}x{_ui_px(900)}"
UI_SUBTITLE_WRAP_LENGTH = _ui_px(730) if IS_MACOS else 0


class GyroFixApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"DJI Gyro Fix v{__version__}")
        self.geometry(UI_WINDOW_GEOMETRY)
        if not IS_MACOS:
            self.resizable(False, False)
        self.configure(bg="#11151c")

        self.language: Language = "ko"
        self._text_vars: dict[str, tk.StringVar] = {}
        self._preset_key = "strong"
        self._status_key: str | None = "initial_status"
        self._status_values: dict[str, object] = {}
        self._progress_stage: str | None = None
        self._result_key: str | None = "result_prompt"
        self._result_values: dict[str, object] = {}
        self._output_is_default = True

        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.preset_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0.0)

        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._cancel_event: threading.Event | None = None
        self._worker: threading.Thread | None = None
        self._busy = False
        self._fixed_input_widgets: list[tk.Widget] = []
        self._range_input_widgets: list[tk.Widget] = []
        self._input_widget_states: list[tuple[tk.Widget, str]] = []
        self._last_detection: tuple[tuple[int, DetectionResult], ...] | None = None
        self.time_ranges: list[tuple[tk.StringVar, tk.StringVar]] = [self._new_time_range()]

        self._configure_style()
        self._build_ui()
        if IS_MACOS:
            self.update_idletasks()
            self.resizable(False, False)
        self._apply_language()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.source_var.trace_add("write", self._input_changed)
        self.after(100, self._poll_events)

    def _t(self, key: str, **values: object) -> str:
        return text(self.language, key, **values)

    def _tv(self, key: str) -> tk.StringVar:
        variable = self._text_vars.get(key)
        if variable is None:
            variable = tk.StringVar()
            self._text_vars[key] = variable
        return variable

    def _set_status(self, key: str, **values: object) -> None:
        self._status_key = key
        self._status_values = values
        self._progress_stage = None
        self.status_var.set(self._t(key, **values))

    def _set_progress_status(self, stage: str) -> None:
        self._status_key = None
        self._status_values = {}
        self._progress_stage = stage
        self.status_var.set(translate_stage(self.language, stage))

    def _set_result_message(self, key: str, **values: object) -> None:
        self._result_key = key
        self._result_values = values
        self._set_result_text(self._t(key, **values))

    def _selected_preset_key(self) -> str:
        selected = self.preset_var.get()
        for key in PRESET_KEYS:
            if selected == self._t(f"preset_{key}"):
                return key
        return self._preset_key

    def _apply_language(self) -> None:
        self.title(self._t("app_title", version=__version__))
        for key, variable in self._text_vars.items():
            if key == "app_title":
                variable.set(self._t(key, version=__version__))
            else:
                variable.set(self._t(key))

        preset_values = [self._t(f"preset_{key}") for key in PRESET_KEYS]
        self.preset_combo.configure(values=preset_values)
        self.preset_var.set(self._t(f"preset_{self._preset_key}"))

        if self._output_is_default:
            self.output_var.set(self._t("output_auto"))
        if self._status_key is not None:
            self.status_var.set(self._t(self._status_key, **self._status_values))
        elif self._progress_stage is not None:
            self.status_var.set(translate_stage(self.language, self._progress_stage))

        if self._last_detection is not None:
            self._render_detection_results()
        elif self._result_key is not None:
            self._set_result_text(self._t(self._result_key, **self._result_values))
        self._update_language_buttons()

    def _set_language(self, language: Language) -> None:
        if language == self.language:
            return
        self._preset_key = self._selected_preset_key()
        self.language = language
        self._apply_language()

    def _update_language_buttons(self) -> None:
        self.korean_button.configure(
            style="LanguageActive.TButton" if self.language == "ko" else "LanguageInactive.TButton"
        )
        self.english_button.configure(
            style="LanguageActive.TButton" if self.language == "en" else "LanguageInactive.TButton"
        )

    def _configure_style(self) -> None:
        self.option_add("*TCombobox*Listbox.background", "#ffffff")
        self.option_add("*TCombobox*Listbox.foreground", "#000000")
        self.option_add("*TCombobox*Listbox.selectBackground", "#d9e7ff")
        self.option_add("*TCombobox*Listbox.selectForeground", "#000000")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#11151c")
        style.configure(
            "Card.TFrame",
            background="#1b212b",
            borderwidth=1,
            relief="solid",
            bordercolor="#313946",
            lightcolor="#313946",
            darkcolor="#313946",
        )
        style.configure("TLabel", background="#11151c", foreground="#edf1f7", font=(UI_FONT_FAMILY, 10))
        style.configure("Card.TLabel", background="#1b212b", foreground="#edf1f7", font=(UI_FONT_FAMILY, 10))
        style.configure("Title.TLabel", background="#11151c", foreground="#ffffff", font=(UI_FONT_FAMILY, 22, "bold"))
        style.configure("Hint.TLabel", background="#11151c", foreground="#9ca6b5", font=(UI_FONT_FAMILY, UI_HINT_FONT_SIZE))
        style.configure("Section.TLabel", background="#1b212b", foreground="#ffffff", font=(UI_FONT_FAMILY, 12, "bold"))
        style.configure("Field.TLabel", background="#1b212b", foreground="#c9d0dc", font=(UI_FONT_FAMILY, UI_FIELD_FONT_SIZE, "bold"))
        style.configure("CardHint.TLabel", background="#1b212b", foreground="#98a3b3", font=(UI_FONT_FAMILY, UI_FIELD_FONT_SIZE))
        style.configure("RangeNumber.TLabel", background="#1b212b", foreground="#aeb8c6", font=(UI_FONT_FAMILY, 10, "bold"), anchor="center")
        style.configure("TButton", font=(UI_FONT_FAMILY, UI_BUTTON_FONT_SIZE, "bold"), padding=(_ui_px(12), _ui_px(9)))
        style.configure("Accent.TButton", background="#3d7ff2", foreground="#ffffff", font=(UI_FONT_FAMILY, 11, "bold"), padding=(_ui_px(16), _ui_px(11)))
        style.map("Accent.TButton", background=[("active", "#5893f5"), ("disabled", "#354157")])
        style.configure("Detect.TButton", background="#303946", foreground="#ffffff", font=(UI_FONT_FAMILY, 11, "bold"), padding=(_ui_px(16), _ui_px(11)))
        style.map("Detect.TButton", background=[("active", "#414c5c"), ("disabled", "#282f39")])
        style.configure("Range.TButton", background="#29313d", foreground="#f2f5f9", font=(UI_FONT_FAMILY, 11, "bold"), padding=(_ui_px(4), _ui_px(5)))
        style.map("Range.TButton", background=[("active", "#3a4656"), ("disabled", "#242a33")])
        style.configure(
            "LanguageInactive.TButton",
            background="#1c2530",
            foreground="#c5cfdb",
            bordercolor="#344252",
            lightcolor="#344252",
            darkcolor="#344252",
            font=(UI_FONT_FAMILY, 9, "bold"),
            padding=(_ui_px(7), _ui_px(5)),
        )
        style.map(
            "LanguageInactive.TButton",
            background=[("active", "#293746")],
            foreground=[("active", "#ffffff")],
        )
        style.configure(
            "LanguageActive.TButton",
            background="#17536c",
            foreground="#f5fbff",
            bordercolor="#236c88",
            lightcolor="#236c88",
            darkcolor="#236c88",
            font=(UI_FONT_FAMILY, 9, "bold"),
            padding=(_ui_px(7), _ui_px(5)),
        )
        style.map(
            "LanguageActive.TButton",
            background=[("active", "#1d6683")],
            foreground=[("active", "#ffffff")],
        )
        style.configure("TEntry", fieldbackground="#11161e", foreground="#f4f6fa", insertcolor="#ffffff", bordercolor="#3a4352", lightcolor="#3a4352", darkcolor="#3a4352", padding=_ui_px(9))
        style.configure(
            "TCombobox",
            fieldbackground="#ffffff",
            background="#d9dde5",
            foreground="#000000",
            arrowcolor="#000000",
            selectbackground="#d9e7ff",
            selectforeground="#000000",
            padding=_ui_px(7),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#ffffff")],
            foreground=[("readonly", "#000000")],
            selectbackground=[("readonly", "#d9e7ff")],
            selectforeground=[("readonly", "#000000")],
        )
        style.configure("Horizontal.TProgressbar", background="#3d7ff2", troughcolor="#11161e", bordercolor="#11161e", thickness=_ui_px(10))
        style.configure("Vertical.TScrollbar", background="#394352", troughcolor="#161b23", arrowcolor="#cbd3df")

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=(_ui_px(24), _ui_px(20)))
        root.pack(fill="both", expand=True)

        title_row = ttk.Frame(root)
        title_row.pack(fill="x")
        ttk.Label(
            title_row,
            textvariable=self._tv("app_title"),
            style="Title.TLabel",
        ).pack(side="left", anchor="w")
        language_group = ttk.Frame(title_row)
        language_group.pack(side="left", anchor="w", padx=(_ui_px(12), 0), pady=(_ui_px(2), 0))
        self.korean_button = ttk.Button(
            language_group,
            text="KOR",
            style="LanguageActive.TButton",
            command=lambda: self._set_language("ko"),
            width=5,
        )
        self.korean_button.pack(side="left")
        self.english_button = ttk.Button(
            language_group,
            text="ENG",
            style="LanguageInactive.TButton",
            command=lambda: self._set_language("en"),
            width=5,
        )
        self.english_button.pack(side="left", padx=(_ui_px(4), 0))
        ttk.Label(
            root,
            textvariable=self._tv("subtitle"),
            style="Hint.TLabel",
            wraplength=UI_SUBTITLE_WRAP_LENGTH,
        ).pack(anchor="w", pady=(_ui_px(3), _ui_px(16)))

        file_card = ttk.Frame(root, style="Card.TFrame", padding=(_ui_px(16), _ui_px(14)))
        file_card.pack(fill="x")
        file_card.columnconfigure(0, weight=1)
        ttk.Label(
            file_card,
            textvariable=self._tv("file_section"),
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w")
        file_row = ttk.Frame(file_card, style="Card.TFrame")
        file_row.grid(row=1, column=0, sticky="ew", pady=(_ui_px(10), _ui_px(10)))
        file_row.columnconfigure(0, weight=1)
        source_entry = ttk.Entry(file_row, textvariable=self.source_var)
        source_entry.grid(row=0, column=0, sticky="ew")
        file_button = ttk.Button(
            file_row,
            textvariable=self._tv("file_select"),
            command=self._choose_file,
        )
        file_button.grid(row=0, column=1, padx=(_ui_px(8), 0))
        self._fixed_input_widgets.extend((source_entry, file_button))
        ttk.Label(
            file_card,
            textvariable=self._tv("save_location"),
            style="Field.TLabel",
        ).grid(row=2, column=0, sticky="w")
        ttk.Label(
            file_card,
            textvariable=self.output_var,
            style="CardHint.TLabel",
            wraplength=_ui_px(700),
        ).grid(row=3, column=0, sticky="w", pady=(_ui_px(4), 0))

        range_card = ttk.Frame(root, style="Card.TFrame", padding=(_ui_px(16), _ui_px(14)))
        range_card.pack(fill="x", pady=(_ui_px(12), 0))
        range_card.columnconfigure(0, weight=1)

        settings_row = ttk.Frame(range_card, style="Card.TFrame")
        settings_row.grid(row=0, column=0, sticky="ew")
        settings_row.columnconfigure(0, weight=1)
        ttk.Label(settings_row, textvariable=self._tv("time_ranges"), style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(settings_row, textvariable=self._tv("max_ranges"), style="CardHint.TLabel").grid(
            row=0, column=1, sticky="e", padx=(_ui_px(8), _ui_px(18))
        )
        ttk.Label(settings_row, textvariable=self._tv("smoothing"), style="Field.TLabel").grid(
            row=0, column=2, sticky="e", padx=(0, _ui_px(8))
        )
        self.preset_combo = ttk.Combobox(
            settings_row,
            textvariable=self.preset_var,
            state="readonly",
            width=17,
        )
        self.preset_combo.grid(row=0, column=3, sticky="e")
        self._fixed_input_widgets.append(self.preset_combo)

        ttk.Label(
            range_card,
            textvariable=self._tv("time_hint"),
            style="CardHint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(_ui_px(7), _ui_px(12)))

        range_header = ttk.Frame(range_card, style="Card.TFrame")
        range_header.grid(row=2, column=0, sticky="ew", pady=(0, _ui_px(6)), padx=(0, _ui_px(17)))
        range_header.columnconfigure(1, weight=1)
        range_header.columnconfigure(2, weight=1)
        ttk.Label(range_header, textvariable=self._tv("number"), width=5, style="Field.TLabel").grid(row=0, column=0)
        ttk.Label(range_header, textvariable=self._tv("start_time"), style="Field.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(range_header, textvariable=self._tv("end_time"), style="Field.TLabel").grid(row=0, column=2, sticky="w", padx=(_ui_px(8), 0))
        ttk.Label(range_header, textvariable=self._tv("manage"), width=8, style="Field.TLabel").grid(row=0, column=3, columnspan=2)

        range_area = ttk.Frame(range_card, style="Card.TFrame")
        range_area.grid(row=3, column=0, sticky="ew")
        range_area.columnconfigure(0, weight=1)
        self.time_canvas = tk.Canvas(
            range_area,
            height=_ui_px(150),
            background="#1b212b",
            highlightthickness=0,
            borderwidth=0,
        )
        self.range_scrollbar = ttk.Scrollbar(
            range_area, orient="vertical", command=self.time_canvas.yview
        )
        self.time_canvas.configure(yscrollcommand=self.range_scrollbar.set)
        self.time_canvas.grid(row=0, column=0, sticky="ew")
        self.range_scrollbar.grid(row=0, column=1, sticky="ns", padx=(_ui_px(5), 0))
        self.range_scrollbar.grid_remove()
        self.time_rows_frame = ttk.Frame(self.time_canvas, style="Card.TFrame")
        self._time_rows_window = self.time_canvas.create_window(
            (0, 0), window=self.time_rows_frame, anchor="nw"
        )
        self.time_rows_frame.bind("<Configure>", self._on_time_rows_configure)
        self.time_canvas.bind("<Configure>", self._on_time_canvas_configure)
        self._render_time_ranges()

        action_card = ttk.Frame(root, style="Card.TFrame", padding=(_ui_px(16), _ui_px(14)))
        action_card.pack(fill="x", pady=(_ui_px(12), 0))
        action_card.columnconfigure(0, weight=1)
        ttk.Label(action_card, textvariable=self._tv("run"), style="Section.TLabel").grid(row=0, column=0, sticky="w")

        action_row = ttk.Frame(action_card, style="Card.TFrame")
        action_row.grid(row=1, column=0, sticky="ew", pady=(_ui_px(10), 0))
        action_row.columnconfigure((0, 1), weight=1)
        self.detect_button = ttk.Button(
            action_row,
            textvariable=self._tv("detect"),
            style="Detect.TButton",
            command=self._detect,
        )
        self.detect_button.grid(row=0, column=0, sticky="ew")
        self.process_button = ttk.Button(
            action_row,
            textvariable=self._tv("fix"),
            style="Accent.TButton",
            command=self._start,
        )
        self.process_button.grid(row=0, column=1, sticky="ew", padx=(_ui_px(10), 0))

        self.progress_bar = ttk.Progressbar(action_card, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=2, column=0, sticky="ew", pady=(_ui_px(12), 0))
        ttk.Label(
            action_card,
            textvariable=self.status_var,
            style="CardHint.TLabel",
            wraplength=_ui_px(700),
        ).grid(row=3, column=0, sticky="w", pady=(_ui_px(7), 0))

        result_card = ttk.Frame(root, style="Card.TFrame", padding=(_ui_px(16), _ui_px(14)))
        result_card.pack(fill="both", expand=True, pady=(_ui_px(12), 0))
        ttk.Label(
            result_card,
            textvariable=self._tv("detection_results"),
            style="Section.TLabel",
        ).pack(anchor="w")
        result_body = ttk.Frame(result_card, style="Card.TFrame")
        result_body.pack(fill="both", expand=True, pady=(_ui_px(10), 0))
        result_body.columnconfigure(0, weight=1)
        result_body.rowconfigure(0, weight=1)
        self.result_text = tk.Text(
            result_body,
            height=4,
            wrap="word",
            relief="solid",
            borderwidth=1,
            background="#11161e",
            foreground="#dfe5ee",
            insertbackground="#ffffff",
            selectbackground="#315f9f",
            font=(UI_FONT_FAMILY, 9),
            padx=_ui_px(12),
            pady=_ui_px(10),
        )
        result_scrollbar = ttk.Scrollbar(result_body, orient="vertical", command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=result_scrollbar.set)
        self.result_text.grid(row=0, column=0, sticky="nsew")
        result_scrollbar.grid(row=0, column=1, sticky="ns", padx=(_ui_px(6), 0))

    def _new_time_range(self) -> tuple[tk.StringVar, tk.StringVar]:
        start_var = tk.StringVar(value="")
        end_var = tk.StringVar(value="")
        start_var.trace_add("write", self._input_changed)
        end_var.trace_add("write", self._input_changed)
        return start_var, end_var

    def _render_time_ranges(self) -> None:
        for child in self.time_rows_frame.winfo_children():
            child.destroy()
        self._range_input_widgets = []

        count = len(self.time_ranges)
        for index, (start_var, end_var) in enumerate(self.time_ranges):
            row = ttk.Frame(self.time_rows_frame, style="Card.TFrame")
            row.grid(row=index, column=0, sticky="ew", pady=(0, _ui_px(6)))
            row.columnconfigure(1, weight=1)
            row.columnconfigure(2, weight=1)

            ttk.Label(
                row,
                text=f"{index + 1}",
                width=5,
                anchor="center",
                justify="center",
                style="RangeNumber.TLabel",
            ).grid(
                row=0, column=0, sticky="nsew"
            )
            start_entry = ttk.Entry(row, textvariable=start_var)
            start_entry.grid(row=0, column=1, sticky="ew")
            end_entry = ttk.Entry(row, textvariable=end_var)
            end_entry.grid(
                row=0, column=2, sticky="ew", padx=(_ui_px(8), 0)
            )
            add_button = ttk.Button(
                row,
                text="+",
                width=3,
                style="Range.TButton",
                command=self._add_time_range,
                state="disabled" if count >= 10 else "normal",
            )
            add_button.grid(row=0, column=3, padx=(_ui_px(8), _ui_px(3)))
            remove_button = ttk.Button(
                row,
                text="−",
                width=3,
                style="Range.TButton",
                command=lambda position=index: self._remove_time_range(position),
                state="disabled" if count <= 1 else "normal",
            )
            remove_button.grid(row=0, column=4)
            self._range_input_widgets.extend(
                (start_entry, end_entry, add_button, remove_button)
            )

        self.time_rows_frame.columnconfigure(0, weight=1)
        self.after_idle(self._update_time_scrollbar)

    def _on_time_rows_configure(self, _event: tk.Event) -> None:
        self._update_time_scrollbar()

    def _on_time_canvas_configure(self, event: tk.Event) -> None:
        self.time_canvas.itemconfigure(self._time_rows_window, width=event.width)
        self.after_idle(self._update_time_scrollbar)

    def _update_time_scrollbar(self) -> None:
        content_height = max(_ui_px(40), self.time_rows_frame.winfo_reqheight())
        viewport_height = min(_ui_px(150), content_height)
        if int(float(self.time_canvas.cget("height"))) != viewport_height:
            self.time_canvas.configure(height=viewport_height)

        self.time_canvas.configure(scrollregion=self.time_canvas.bbox("all"))
        if content_height > viewport_height + 1:
            self.range_scrollbar.grid()
        else:
            self.range_scrollbar.grid_remove()
            self.time_canvas.yview_moveto(0.0)

    def _add_time_range(self) -> None:
        if len(self.time_ranges) >= 10:
            return
        self.time_ranges.append(self._new_time_range())
        self._render_time_ranges()
        self._input_changed()
        self._set_status("range_added", count=len(self.time_ranges))
        self.after_idle(lambda: self.time_canvas.yview_moveto(1.0))

    def _remove_time_range(self, index: int) -> None:
        if len(self.time_ranges) <= 1:
            return
        del self.time_ranges[index]
        self._render_time_ranges()
        self._input_changed()
        self._set_status("range_count", count=len(self.time_ranges))

    def _set_result_text(self, text: str) -> None:
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.configure(state="disabled")

    def _input_changed(self, *_args: object) -> None:
        if self._last_detection is None:
            return
        self._last_detection = None
        self._set_result_message("inputs_changed")

    def _read_inputs(self) -> tuple[Path, list[tuple[int, float, float]]]:
        source = Path(self.source_var.get().strip())
        if not source.is_file():
            raise ValueError(self._t("source_required"))
        intervals = parse_time_rows(
            [(start_var.get(), end_var.get()) for start_var, end_var in self.time_ranges],
            language=self.language,
        )
        return source, intervals

    def _choose_file(self) -> None:
        selected = filedialog.askopenfilename(
            title=self._t("file_dialog_title"),
            filetypes=[
                (self._t("file_dialog_video"), "*.mp4 *.MP4 *.mov *.MOV"),
                (self._t("file_dialog_all"), "*.*"),
            ],
        )
        if selected:
            self.source_var.set(selected)
            self._output_is_default = False
            self.output_var.set(str(default_output_path(selected)))
            self._set_status("file_selected_status")

    def _set_busy(self, busy: bool) -> None:
        if busy and not self._busy:
            input_widgets = self._fixed_input_widgets + self._range_input_widgets
            self._input_widget_states = [
                (widget, str(widget.cget("state")))
                for widget in input_widgets
                if widget.winfo_exists()
            ]
            for widget, _state in self._input_widget_states:
                widget.configure(state="disabled")
        elif not busy and self._busy:
            for widget, state in self._input_widget_states:
                if widget.winfo_exists():
                    widget.configure(state=state)
            self._input_widget_states = []
        self._busy = busy
        self.detect_button.configure(state="disabled" if busy else "normal")
        self.process_button.configure(state="disabled" if busy else "normal")

    def _finish_worker(self) -> None:
        self._worker = None
        self._cancel_event = None
        self._set_busy(False)

    def _on_close(self) -> None:
        if self._busy:
            messagebox.showwarning(
                self._t("busy_title"),
                self._t("busy_message"),
            )
            return
        self.destroy()

    def _detect(self) -> None:
        try:
            source, intervals = self._read_inputs()
        except ValueError as error:
            messagebox.showerror(self._t("input_error_title"), str(error))
            return

        self.progress_var.set(0)
        self._last_detection = None
        self._set_status("detecting_ranges", count=len(intervals))
        self._set_result_message("detecting")
        self._set_busy(True)
        self._cancel_event = threading.Event()

        def run() -> None:
            try:
                results: list[tuple[int, DetectionResult]] = []
                interval_count = len(intervals)
                for index, (row_number, start, end) in enumerate(intervals):
                    def callback(stage: str, amount: float, current: int = index) -> None:
                        overall = (current + amount) / interval_count
                        self._events.put(
                            ("progress", (f"[{current + 1}/{interval_count}] {stage}", overall))
                        )

                    results.append(
                        (
                            row_number,
                            detect_video_jitter(
                                source,
                                start,
                                end,
                                progress=callback,
                                cancel=self._cancel_event,
                            ),
                        )
                    )
                self._events.put(("detection_done", tuple(results)))
            except ProcessingCancelled as error:
                self._events.put(("cancelled", error))
            except Exception as error:
                self._events.put(("error", error))

        self._worker = threading.Thread(target=run, name="gyro-detect-worker", daemon=True)
        self._worker.start()

    def _start(self) -> None:
        try:
            source, entered_intervals = self._read_inputs()
            intervals = [(start, end) for _row_number, start, end in entered_intervals]
            output = default_output_path(source)
            self._preset_key = self._selected_preset_key()
            smoothing_ms = SMOOTHING_PRESETS[self._preset_key]
        except (ValueError, KeyError) as error:
            messagebox.showerror(self._t("input_error_title"), str(error))
            return

        try:
            overwrite = False
            if output.exists():
                overwrite = messagebox.askyesno(
                    self._t("overwrite_title"),
                    self._t("overwrite_message", output=output),
                )
                if not overwrite:
                    return
        except OSError as error:
            messagebox.showerror(
                self._t("input_error_title"),
                translate_error(self.language, str(error)),
            )
            return

        self._output_is_default = False
        self.output_var.set(str(output))
        self.progress_var.set(0)
        self._set_status("checking_file")
        self._set_busy(True)
        self._cancel_event = threading.Event()

        def callback(stage: str, amount: float) -> None:
            self._events.put(("progress", (stage, amount)))

        def run() -> None:
            try:
                result = process_video_intervals(
                    source,
                    output,
                    intervals,
                    smoothing_ms=smoothing_ms,
                    overwrite=overwrite,
                    progress=callback,
                    cancel=self._cancel_event,
                )
                self._events.put(("done", result))
            except ProcessingCancelled as error:
                self._events.put(("cancelled", error))
            except Exception as error:
                self._events.put(("error", error))

        self._worker = threading.Thread(target=run, name="gyro-fix-worker", daemon=True)
        self._worker.start()

    def _render_detection_results(self) -> None:
        if self._last_detection is None:
            return
        descriptions = []
        for row_number, result in self._last_detection:
            descriptions.append(
                "\n".join(
                    [
                        self._t(
                            "range_result_header",
                            row=row_number,
                            start=result.start_seconds,
                            end=result.end_seconds,
                        ),
                        describe_detection(result, language=self.language),
                    ]
                )
            )
        self._result_key = None
        self._result_values = {}
        self._set_result_text("\n\n".join(descriptions))

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self._events.get_nowait()
                if event == "progress":
                    stage, amount = payload  # type: ignore[misc]
                    self._set_progress_status(str(stage))
                    self.progress_var.set(float(amount) * 100.0)
                elif event == "detection_done":
                    results = payload
                    valid_results = isinstance(results, tuple) and all(
                        isinstance(item, tuple)
                        and len(item) == 2
                        and isinstance(item[0], int)
                        and isinstance(item[1], DetectionResult)
                        for item in results
                    )
                    if not valid_results:
                        self._finish_worker()
                        self._set_status("invalid_detection_status")
                        messagebox.showerror(
                            self._t("processing_error_title"),
                            self._t("invalid_detection_message"),
                        )
                        continue
                    self._last_detection = results
                    self._finish_worker()
                    self.progress_var.set(100)
                    self._render_detection_results()
                    event_count = sum(len(result.events) for _row_number, result in results)
                    if event_count:
                        self._set_status(
                            "detect_complete_events",
                            ranges=len(results),
                            events=event_count,
                        )
                    else:
                        self._set_status(
                            "detect_complete_none",
                            ranges=len(results),
                        )
                elif event == "done":
                    result = payload
                    if not isinstance(result, ProcessingResult):
                        self._finish_worker()
                        self._set_status("invalid_save_status")
                        messagebox.showerror(
                            self._t("processing_error_title"),
                            self._t("invalid_save_message"),
                        )
                        continue
                    self._finish_worker()
                    self.progress_var.set(100)
                    self._set_status(
                        "done_status",
                        ranges=result.interval_count,
                        samples=result.quaternions_changed,
                        improvement=result.improvement_percent,
                    )
                    messagebox.showinfo(
                        self._t("save_done_title"),
                        self._t("save_done_message", output=result.output_path),
                    )
                elif event == "cancelled":
                    self._finish_worker()
                    self.progress_var.set(0)
                    self._set_status("cancelled_status")
                elif event == "error":
                    self._finish_worker()
                    self._set_status("error_status")
                    messagebox.showerror(
                        self._t("processing_error_title"),
                        translate_error(self.language, str(payload)),
                    )
        except queue.Empty:
            pass
        self.after(100, self._poll_events)


def main() -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    app = GyroFixApp()
    app.mainloop()
