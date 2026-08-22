from __future__ import annotations

import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .detection import DetectionResult, describe_detection, detect_video_jitter
from .intervals import parse_time_rows
from .processor import (
    ProcessingCancelled,
    ProcessingResult,
    default_output_path,
    process_video_intervals,
)


SMOOTHING_PRESETS = {
    "강하게 (권장)": 180.0,
    "보통": 100.0,
    "약하게": 50.0,
    "매우 강하게": 300.0,
}


class GyroFixApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"DJI Gyro Fix v{__version__}")
        self.geometry("800x900")
        self.resizable(False, False)
        self.configure(bg="#11151c")

        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar(value="파일을 선택하면 자동으로 정해집니다.")
        self.preset_var = tk.StringVar(value="강하게 (권장)")
        self.status_var = tk.StringVar(value="DJI 원본 영상을 선택해 주세요.")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._cancel_event: threading.Event | None = None
        self._worker: threading.Thread | None = None
        self._busy = False
        self._last_detection: tuple[tuple[int, DetectionResult], ...] | None = None
        self.time_ranges: list[tuple[tk.StringVar, tk.StringVar]] = [self._new_time_range()]

        self._configure_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.source_var.trace_add("write", self._input_changed)
        self.after(100, self._poll_events)

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
        style.configure("TLabel", background="#11151c", foreground="#edf1f7", font=("Malgun Gothic", 10))
        style.configure("Card.TLabel", background="#1b212b", foreground="#edf1f7", font=("Malgun Gothic", 10))
        style.configure("Title.TLabel", background="#11151c", foreground="#ffffff", font=("Malgun Gothic", 22, "bold"))
        style.configure("Hint.TLabel", background="#11151c", foreground="#9ca6b5", font=("Malgun Gothic", 9))
        style.configure("Section.TLabel", background="#1b212b", foreground="#ffffff", font=("Malgun Gothic", 12, "bold"))
        style.configure("Field.TLabel", background="#1b212b", foreground="#c9d0dc", font=("Malgun Gothic", 9, "bold"))
        style.configure("CardHint.TLabel", background="#1b212b", foreground="#98a3b3", font=("Malgun Gothic", 9))
        style.configure("RangeNumber.TLabel", background="#1b212b", foreground="#aeb8c6", font=("Malgun Gothic", 10, "bold"), anchor="center")
        style.configure("TButton", font=("Malgun Gothic", 10, "bold"), padding=(12, 9))
        style.configure("Accent.TButton", background="#3d7ff2", foreground="#ffffff", font=("Malgun Gothic", 11, "bold"), padding=(16, 11))
        style.map("Accent.TButton", background=[("active", "#5893f5"), ("disabled", "#354157")])
        style.configure("Detect.TButton", background="#303946", foreground="#ffffff", font=("Malgun Gothic", 11, "bold"), padding=(16, 11))
        style.map("Detect.TButton", background=[("active", "#414c5c"), ("disabled", "#282f39")])
        style.configure("Range.TButton", background="#29313d", foreground="#f2f5f9", font=("Malgun Gothic", 11, "bold"), padding=(4, 5))
        style.map("Range.TButton", background=[("active", "#3a4656"), ("disabled", "#242a33")])
        style.configure("TEntry", fieldbackground="#11161e", foreground="#f4f6fa", insertcolor="#ffffff", bordercolor="#3a4352", lightcolor="#3a4352", darkcolor="#3a4352", padding=9)
        style.configure(
            "TCombobox",
            fieldbackground="#ffffff",
            background="#d9dde5",
            foreground="#000000",
            arrowcolor="#000000",
            selectbackground="#d9e7ff",
            selectforeground="#000000",
            padding=7,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#ffffff")],
            foreground=[("readonly", "#000000")],
            selectbackground=[("readonly", "#d9e7ff")],
            selectforeground=[("readonly", "#000000")],
        )
        style.configure("Horizontal.TProgressbar", background="#3d7ff2", troughcolor="#11161e", bordercolor="#11161e", thickness=10)
        style.configure("Vertical.TScrollbar", background="#394352", troughcolor="#161b23", arrowcolor="#cbd3df")

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=(24, 20))
        root.pack(fill="both", expand=True)

        ttk.Label(root, text=f"DJI Gyro Fix v{__version__}", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text="지정한 시간의 자이로 데이터만 부드럽게 수정합니다. 영상과 음성은 재인코딩하지 않습니다.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(3, 16))

        file_card = ttk.Frame(root, style="Card.TFrame", padding=(16, 14))
        file_card.pack(fill="x")
        file_card.columnconfigure(0, weight=1)
        ttk.Label(file_card, text="파일", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        file_row = ttk.Frame(file_card, style="Card.TFrame")
        file_row.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        file_row.columnconfigure(0, weight=1)
        ttk.Entry(file_row, textvariable=self.source_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(file_row, text="파일 선택", command=self._choose_file).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(file_card, text="저장 위치", style="Field.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Label(
            file_card,
            textvariable=self.output_var,
            style="CardHint.TLabel",
            wraplength=700,
        ).grid(row=3, column=0, sticky="w", pady=(4, 0))

        range_card = ttk.Frame(root, style="Card.TFrame", padding=(16, 14))
        range_card.pack(fill="x", pady=(12, 0))
        range_card.columnconfigure(0, weight=1)

        settings_row = ttk.Frame(range_card, style="Card.TFrame")
        settings_row.grid(row=0, column=0, sticky="ew")
        settings_row.columnconfigure(0, weight=1)
        ttk.Label(settings_row, text="시간 구간", style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(settings_row, text="최대 10개", style="CardHint.TLabel").grid(
            row=0, column=1, sticky="e", padx=(8, 18)
        )
        ttk.Label(settings_row, text="스무딩", style="Field.TLabel").grid(
            row=0, column=2, sticky="e", padx=(0, 8)
        )
        ttk.Combobox(
            settings_row,
            textvariable=self.preset_var,
            values=list(SMOOTHING_PRESETS),
            state="readonly",
            width=17,
        ).grid(row=0, column=3, sticky="e")

        ttk.Label(
            range_card,
            text="시간 형식: 22.5 또는 00:00:22.500  ·  완전히 빈 행은 자동으로 건너뜁니다.",
            style="CardHint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(7, 12))

        range_header = ttk.Frame(range_card, style="Card.TFrame")
        range_header.grid(row=2, column=0, sticky="ew", pady=(0, 6), padx=(0, 17))
        range_header.columnconfigure(1, weight=1)
        range_header.columnconfigure(2, weight=1)
        ttk.Label(range_header, text="번호", width=5, style="Field.TLabel").grid(row=0, column=0)
        ttk.Label(range_header, text="시작 시간(초)", style="Field.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(range_header, text="종료 시간(초)", style="Field.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Label(range_header, text="관리", width=8, style="Field.TLabel").grid(row=0, column=3, columnspan=2)

        range_area = ttk.Frame(range_card, style="Card.TFrame")
        range_area.grid(row=3, column=0, sticky="ew")
        range_area.columnconfigure(0, weight=1)
        self.time_canvas = tk.Canvas(
            range_area,
            height=150,
            background="#1b212b",
            highlightthickness=0,
            borderwidth=0,
        )
        self.range_scrollbar = ttk.Scrollbar(
            range_area, orient="vertical", command=self.time_canvas.yview
        )
        self.time_canvas.configure(yscrollcommand=self.range_scrollbar.set)
        self.time_canvas.grid(row=0, column=0, sticky="ew")
        self.range_scrollbar.grid(row=0, column=1, sticky="ns", padx=(5, 0))
        self.range_scrollbar.grid_remove()
        self.time_rows_frame = ttk.Frame(self.time_canvas, style="Card.TFrame")
        self._time_rows_window = self.time_canvas.create_window(
            (0, 0), window=self.time_rows_frame, anchor="nw"
        )
        self.time_rows_frame.bind("<Configure>", self._on_time_rows_configure)
        self.time_canvas.bind("<Configure>", self._on_time_canvas_configure)
        self._render_time_ranges()

        action_card = ttk.Frame(root, style="Card.TFrame", padding=(16, 14))
        action_card.pack(fill="x", pady=(12, 0))
        action_card.columnconfigure(0, weight=1)
        ttk.Label(action_card, text="실행", style="Section.TLabel").grid(row=0, column=0, sticky="w")

        action_row = ttk.Frame(action_card, style="Card.TFrame")
        action_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        action_row.columnconfigure((0, 1), weight=1)
        self.detect_button = ttk.Button(
            action_row,
            text="검출",
            style="Detect.TButton",
            command=self._detect,
        )
        self.detect_button.grid(row=0, column=0, sticky="ew")
        self.process_button = ttk.Button(
            action_row,
            text="FIX",
            style="Accent.TButton",
            command=self._start,
        )
        self.process_button.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        self.progress_bar = ttk.Progressbar(action_card, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(
            action_card,
            textvariable=self.status_var,
            style="CardHint.TLabel",
            wraplength=700,
        ).grid(row=3, column=0, sticky="w", pady=(7, 0))

        result_card = ttk.Frame(root, style="Card.TFrame", padding=(16, 14))
        result_card.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(result_card, text="검출 결과", style="Section.TLabel").pack(anchor="w")
        result_body = ttk.Frame(result_card, style="Card.TFrame")
        result_body.pack(fill="both", expand=True, pady=(10, 0))
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
            font=("Malgun Gothic", 9),
            padx=12,
            pady=10,
        )
        result_scrollbar = ttk.Scrollbar(result_body, orient="vertical", command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=result_scrollbar.set)
        self.result_text.grid(row=0, column=0, sticky="nsew")
        result_scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self._set_result_text("시간 범위를 입력하고 ‘검출’을 누르세요.")

    def _new_time_range(self) -> tuple[tk.StringVar, tk.StringVar]:
        start_var = tk.StringVar(value="")
        end_var = tk.StringVar(value="")
        start_var.trace_add("write", self._input_changed)
        end_var.trace_add("write", self._input_changed)
        return start_var, end_var

    def _render_time_ranges(self) -> None:
        for child in self.time_rows_frame.winfo_children():
            child.destroy()

        count = len(self.time_ranges)
        for index, (start_var, end_var) in enumerate(self.time_ranges):
            row = ttk.Frame(self.time_rows_frame, style="Card.TFrame")
            row.grid(row=index, column=0, sticky="ew", pady=(0, 6))
            row.columnconfigure(1, weight=1)
            row.columnconfigure(2, weight=1)

            ttk.Label(row, text=f"{index + 1}", width=5, style="RangeNumber.TLabel").grid(
                row=0, column=0
            )
            ttk.Entry(row, textvariable=start_var).grid(row=0, column=1, sticky="ew")
            ttk.Entry(row, textvariable=end_var).grid(
                row=0, column=2, sticky="ew", padx=(8, 0)
            )
            ttk.Button(
                row,
                text="+",
                width=3,
                style="Range.TButton",
                command=self._add_time_range,
                state="disabled" if count >= 10 else "normal",
            ).grid(row=0, column=3, padx=(8, 3))
            ttk.Button(
                row,
                text="−",
                width=3,
                style="Range.TButton",
                command=lambda position=index: self._remove_time_range(position),
                state="disabled" if count <= 1 else "normal",
            ).grid(row=0, column=4)

        self.time_rows_frame.columnconfigure(0, weight=1)
        self.after_idle(self._update_time_scrollbar)

    def _on_time_rows_configure(self, _event: tk.Event) -> None:
        self._update_time_scrollbar()

    def _on_time_canvas_configure(self, event: tk.Event) -> None:
        self.time_canvas.itemconfigure(self._time_rows_window, width=event.width)
        self.after_idle(self._update_time_scrollbar)

    def _update_time_scrollbar(self) -> None:
        content_height = max(40, self.time_rows_frame.winfo_reqheight())
        viewport_height = min(150, content_height)
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
        self.status_var.set(f"처리 시간 구간 {len(self.time_ranges)}개 · 최대 10개까지 추가할 수 있습니다.")
        self.after_idle(lambda: self.time_canvas.yview_moveto(1.0))

    def _remove_time_range(self, index: int) -> None:
        if len(self.time_ranges) <= 1:
            return
        del self.time_ranges[index]
        self._render_time_ranges()
        self._input_changed()
        self.status_var.set(f"처리 시간 구간 {len(self.time_ranges)}개")

    def _set_result_text(self, text: str) -> None:
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.configure(state="disabled")

    def _input_changed(self, *_args: object) -> None:
        if self._last_detection is None:
            return
        self._last_detection = None
        self._set_result_text("입력 범위가 변경됐습니다. 필요하면 다시 ‘검출’을 눌러 주세요.")

    def _read_inputs(self) -> tuple[Path, list[tuple[int, float, float]]]:
        source = Path(self.source_var.get().strip())
        if not source.is_file():
            raise ValueError("DJI 원본 영상 파일을 선택해 주세요.")
        intervals = parse_time_rows(
            [(start_var.get(), end_var.get()) for start_var, end_var in self.time_ranges]
        )
        return source, intervals

    def _choose_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="DJI 원본 영상 선택",
            filetypes=[("MP4/MOV 영상", "*.mp4 *.MP4 *.mov *.MOV"), ("모든 파일", "*.*")],
        )
        if selected:
            self.source_var.set(selected)
            self.output_var.set(str(default_output_path(selected)))
            self.status_var.set("시간 구간을 정한 뒤 ‘검출’로 확인하거나 바로 ‘FIX’를 누르세요.")

    def _set_busy(self, busy: bool) -> None:
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
                "작업 진행 중",
                "파일을 안전하게 저장하는 중입니다. 작업이 끝난 뒤 창을 닫아 주세요.",
            )
            return
        self.destroy()

    def _detect(self) -> None:
        try:
            source, intervals = self._read_inputs()
        except ValueError as error:
            messagebox.showerror("입력 확인", str(error))
            return

        self.progress_var.set(0)
        self.status_var.set(f"선택한 {len(intervals)}개 구간의 자이로 데이터를 확인하는 중…")
        self._set_result_text("검출 중입니다…")
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
            smoothing_ms = SMOOTHING_PRESETS[self.preset_var.get()]
        except (ValueError, KeyError) as error:
            messagebox.showerror("입력 확인", str(error))
            return

        try:
            overwrite = False
            if output.exists():
                overwrite = messagebox.askyesno(
                    "파일 덮어쓰기",
                    f"수정본이 이미 있습니다. 덮어쓸까요?\n\n{output}",
                )
                if not overwrite:
                    return
        except OSError as error:
            messagebox.showerror("입력 확인", str(error))
            return

        self.output_var.set(str(output))
        self.progress_var.set(0)
        self.status_var.set("파일을 확인하는 중…")
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

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self._events.get_nowait()
                if event == "progress":
                    stage, amount = payload  # type: ignore[misc]
                    self.status_var.set(str(stage))
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
                        self.status_var.set("검출 결과를 읽지 못했습니다.")
                        messagebox.showerror("처리 오류", "올바르지 않은 검출 결과를 받았습니다.")
                        continue
                    self._last_detection = results
                    self._finish_worker()
                    self.progress_var.set(100)
                    descriptions = []
                    for row_number, result in results:
                        descriptions.append(
                            f"[{row_number}번 입력 구간 · "
                            f"{result.start_seconds:.3f}~{result.end_seconds:.3f}초]\n"
                            f"{describe_detection(result)}"
                        )
                    self._set_result_text("\n\n".join(descriptions))
                    event_count = sum(len(result.events) for _row_number, result in results)
                    if event_count:
                        self.status_var.set(
                            f"검출 완료 · 입력 구간 {len(results)}개 · 이상 흔들림 {event_count}개 · "
                            "FIX는 입력한 모든 시간 구간을 수정합니다."
                        )
                    else:
                        self.status_var.set(
                            f"검출 완료 · 입력 구간 {len(results)}개 · 기준을 넘는 이상 흔들림이 없습니다. "
                            "FIX는 입력한 모든 시간 구간에 적용할 수 있습니다."
                        )
                elif event == "done":
                    result = payload
                    if not isinstance(result, ProcessingResult):
                        self._finish_worker()
                        self.status_var.set("저장 결과를 읽지 못했습니다.")
                        messagebox.showerror("처리 오류", "올바르지 않은 저장 결과를 받았습니다.")
                        continue
                    self._finish_worker()
                    self.progress_var.set(100)
                    self.status_var.set(
                        f"완료 · 구간 {result.interval_count}개 · 자세 샘플 {result.quaternions_changed:,}개 수정 · "
                        f"고주파 변화 {result.improvement_percent:.1f}% 감소"
                    )
                    messagebox.showinfo(
                        "저장 완료",
                        f"원본은 그대로 두고 수정본을 저장했습니다.\n\n{result.output_path}",
                    )
                elif event == "cancelled":
                    self._finish_worker()
                    self.progress_var.set(0)
                    self.status_var.set("작업이 취소됐습니다. 원본은 변경되지 않았습니다.")
                elif event == "error":
                    self._finish_worker()
                    self.status_var.set("처리하지 못했습니다. 원본은 변경되지 않았습니다.")
                    messagebox.showerror("처리 오류", str(payload))
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
