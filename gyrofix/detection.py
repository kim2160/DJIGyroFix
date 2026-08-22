from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import statistics
import threading
from typing import Callable, Sequence

from .processor import ProcessingCancelled, inspect_video
from .protobuf import quaternion_refs
from .smoothing import dot, inverse, multiply, normalize


DetectionProgress = Callable[[str, float], None]


@dataclass(frozen=True)
class DetectionEvent:
    start_seconds: float
    end_seconds: float
    peak_seconds: float
    severity_score: float
    severity_label: str
    baseline_ratio: float
    dominant_axes: tuple[str, ...]
    spike_count: int
    event_type: str

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass(frozen=True)
class DetectionResult:
    source_path: Path
    start_seconds: float
    end_seconds: float
    sample_count: int
    sample_rate: float
    baseline_metric: float
    threshold_metric: float
    events: tuple[DetectionEvent, ...]


def format_timestamp(seconds: float, milliseconds: bool = True) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int(seconds % 3600 // 60)
    remaining = seconds - hours * 3600 - minutes * 60
    if milliseconds:
        return f"{hours:02d}:{minutes:02d}:{remaining:06.3f}"
    return f"{hours:02d}:{minutes:02d}:{int(remaining):02d}"


def describe_detection(result: DetectionResult) -> str:
    range_text = f"{format_timestamp(result.start_seconds)} ~ {format_timestamp(result.end_seconds)}"
    if not result.events:
        return (
            f"검출 범위  {range_text}\n"
            "기준을 넘는 고주파 자세 떨림이 검출되지 않았습니다."
        )
    lines = [
        f"검출 범위  {range_text}",
        f"이상 흔들림 {len(result.events)}개가 검출되었습니다.",
    ]
    for index, event in enumerate(result.events, start=1):
        axes = "/".join(event.dominant_axes) if event.dominant_axes else "복합"
        lines.extend(
            [
                "",
                f"{index}. {format_timestamp(event.start_seconds)} ~ {format_timestamp(event.end_seconds)} "
                f"({event.duration_seconds:.3f}초)",
                f"   최대 지점 {format_timestamp(event.peak_seconds)} · "
                f"강도 {event.severity_score:.1f}/10 ({event.severity_label})",
                f"   {event.event_type} · 영향 축 {axes} · "
                f"평상시 대비 {event.baseline_ratio:.1f}배 · 급변 지점 {event.spike_count}개",
            ]
        )
    return "\n".join(lines)


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProcessingCancelled("작업이 취소되었습니다.")


def _rotation_velocity(previous: Sequence[float], current: Sequence[float], dt: float) -> list[float]:
    delta = multiply(current, inverse(previous))
    if delta[0] < 0.0:
        delta = [-value for value in delta]
    vector_norm = math.sqrt(sum(value * value for value in delta[1:]))
    if vector_norm < 1e-12 or dt <= 0.0:
        return [0.0, 0.0, 0.0]
    angle = 2.0 * math.atan2(vector_norm, max(0.0, delta[0]))
    scale = math.degrees(angle) / (vector_norm * dt)
    return [delta[index] * scale for index in range(1, 4)]


def _box_blur_vectors(values: Sequence[Sequence[float]], radius: int) -> list[list[float]]:
    if radius <= 0:
        return [list(value) for value in values]
    prefixes = [[0.0] * (len(values) + 1) for _ in range(3)]
    for index, value in enumerate(values):
        for axis in range(3):
            prefixes[axis][index + 1] = prefixes[axis][index] + value[axis]
    output: list[list[float]] = []
    for index in range(len(values)):
        first = max(0, index - radius)
        last = min(len(values), index + radius + 1)
        count = last - first
        output.append(
            [
                (prefixes[axis][last] - prefixes[axis][first]) / count
                for axis in range(3)
            ]
        )
    return output


def _local_peak_count(values: Sequence[float], threshold: float) -> int:
    candidates = [
        index
        for index in range(1, len(values) - 1)
        if values[index] >= threshold
        and values[index] >= values[index - 1]
        and values[index] > values[index + 1]
    ]
    selected: list[int] = []
    for index in sorted(candidates, key=lambda item: values[item], reverse=True):
        if all(abs(index - existing) >= 3 for existing in selected):
            selected.append(index)
    return max(1, len(selected))


def _detect_events(
    bin_times: Sequence[float],
    metrics: Sequence[float],
    axis_energy: Sequence[Sequence[float]],
    baseline: float,
    threshold: float,
    start_seconds: float,
    end_seconds: float,
    bin_seconds: float,
) -> tuple[DetectionEvent, ...]:
    active = [metric >= threshold for metric in metrics]
    groups: list[tuple[int, int]] = []
    index = 0
    max_gap_bins = max(1, round(0.20 / bin_seconds))
    while index < len(active):
        if not active[index]:
            index += 1
            continue
        first = index
        last_active = index
        gap = 0
        index += 1
        while index < len(active):
            if active[index]:
                last_active = index
                gap = 0
            else:
                gap += 1
                if gap > max_gap_bins:
                    break
            index += 1
        groups.append((first, last_active))

    events: list[DetectionEvent] = []
    padding_bins = max(1, round(0.02 / bin_seconds))
    axis_names = ("X", "Y", "Z")
    for raw_first, raw_last in groups:
        active_count = sum(active[raw_first : raw_last + 1])
        peak_index = max(range(raw_first, raw_last + 1), key=lambda item: metrics[item])
        peak_ratio = metrics[peak_index] / max(threshold, 1e-9)
        if active_count < 2 and peak_ratio < 1.7:
            continue
        first = max(0, raw_first - padding_bins)
        last = min(len(metrics) - 1, raw_last + padding_bins)
        event_start = max(start_seconds, bin_times[first] - bin_seconds / 2.0)
        event_end = min(end_seconds, bin_times[last] + bin_seconds / 2.0)
        energies = [
            sum(axis_energy[item][axis] for item in range(raw_first, raw_last + 1))
            for axis in range(3)
        ]
        maximum_energy = max(energies) if energies else 0.0
        dominant = tuple(
            axis_names[axis]
            for axis in sorted(range(3), key=lambda item: energies[item], reverse=True)
            if maximum_energy > 0.0 and energies[axis] >= maximum_energy * 0.35
        )
        baseline_ratio = metrics[peak_index] / max(baseline, 1e-9)
        severity_score = min(10.0, 4.0 + 3.0 * math.log2(max(1.0, peak_ratio)))
        if severity_score < 6.0:
            severity_label = "약함"
        elif severity_score < 8.2:
            severity_label = "중간"
        else:
            severity_label = "강함"
        local_values = metrics[raw_first : raw_last + 1]
        spike_count = _local_peak_count(local_values, threshold)
        event_type = "순간 자세 충격" if event_end - event_start < 0.10 else "고주파 자세 떨림"
        events.append(
            DetectionEvent(
                start_seconds=event_start,
                end_seconds=event_end,
                peak_seconds=bin_times[peak_index],
                severity_score=severity_score,
                severity_label=severity_label,
                baseline_ratio=baseline_ratio,
                dominant_axes=dominant,
                spike_count=spike_count,
                event_type=event_type,
            )
        )
    return tuple(events)


def detect_video_jitter(
    source: str | Path,
    start_seconds: float,
    end_seconds: float,
    *,
    progress: DetectionProgress | None = None,
    cancel: threading.Event | None = None,
) -> DetectionResult:
    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {source_path}")
    if not math.isfinite(start_seconds) or not math.isfinite(end_seconds):
        raise ValueError("검출 시간은 유한한 값이어야 합니다.")
    if start_seconds < 0.0 or end_seconds <= start_seconds:
        raise ValueError(
            "검출 구간은 0 이상이며 종료 시간이 시작 시간보다 뒤여야 합니다."
        )
    if progress:
        progress("DJI 자세 데이터 확인 중", 0.02)
    _, metadata, variant = inspect_video(source_path)
    if end_seconds > metadata.duration_seconds:
        raise ValueError(
            f"종료 시간({end_seconds:.3f}초)이 영상 길이({metadata.duration_seconds:.3f}초)를 넘습니다."
        )

    context = 0.10
    sample_indices = list(
        metadata.sample_range(
            max(0.0, start_seconds - context),
            min(metadata.duration_seconds, end_seconds + context),
        )
    )
    times: list[float] = []
    quaternions: list[list[float]] = []
    with source_path.open("rb") as file:
        for sequence, sample_index in enumerate(sample_indices):
            _check_cancel(cancel)
            file.seek(metadata.sample_offsets[sample_index])
            data = file.read(metadata.sample_sizes[sample_index])
            if len(data) != metadata.sample_sizes[sample_index]:
                raise OSError("DJI 메타데이터 샘플을 끝까지 읽지 못했습니다.")
            refs = quaternion_refs(data, variant)
            sample_time = metadata.sample_dts[sample_index] / metadata.timescale
            if sample_index + 1 < len(metadata.sample_dts):
                next_time = metadata.sample_dts[sample_index + 1] / metadata.timescale
            else:
                next_time = metadata.duration_seconds
            for subindex, ref in enumerate(refs):
                times.append(sample_time + (next_time - sample_time) * subindex / max(1, len(refs)))
                value = normalize(ref.values)
                if quaternions and dot(quaternions[-1], value) < 0.0:
                    value = [-component for component in value]
                quaternions.append(value)
            if progress and sequence % 100 == 0:
                progress("선택 구간 자세 데이터 읽는 중", 0.04 + 0.36 * sequence / max(1, len(sample_indices)))

    if len(times) < 20:
        raise RuntimeError("검출에 필요한 자세 데이터가 부족합니다.")
    intervals = [right - left for left, right in zip(times, times[1:]) if right > left]
    if not intervals:
        raise RuntimeError("검출에 필요한 유효한 자세 데이터 시간값이 없습니다.")
    sample_interval = statistics.median(intervals)
    sample_rate = 1.0 / sample_interval
    velocities: list[list[float]] = [[0.0, 0.0, 0.0]]
    for index in range(1, len(quaternions)):
        velocities.append(
            _rotation_velocity(
                quaternions[index - 1],
                quaternions[index],
                max(sample_interval, times[index] - times[index - 1]),
            )
        )
    if progress:
        progress("고주파 흔들림 계산 중", 0.50)
    radius = max(2, round(0.012 / sample_interval))
    lowpass = _box_blur_vectors(velocities, radius)
    residuals = [
        [value[axis] - smooth[axis] for axis in range(3)]
        for value, smooth in zip(velocities, lowpass)
    ]

    bin_seconds = 0.010
    bin_count = max(1, math.ceil((end_seconds - start_seconds) / bin_seconds))
    sums = [0.0] * bin_count
    counts = [0] * bin_count
    energies = [[0.0, 0.0, 0.0] for _ in range(bin_count)]
    for time, residual in zip(times, residuals):
        if not (start_seconds <= time < end_seconds):
            continue
        bin_index = min(bin_count - 1, int((time - start_seconds) / bin_seconds))
        squared = sum(component * component for component in residual)
        sums[bin_index] += squared
        counts[bin_index] += 1
        for axis in range(3):
            energies[bin_index][axis] += residual[axis] * residual[axis]
    metrics = [
        math.sqrt(sums[index] / counts[index]) if counts[index] else 0.0
        for index in range(bin_count)
    ]
    bin_times = [start_seconds + (index + 0.5) * bin_seconds for index in range(bin_count)]
    nonzero = sorted(metric for metric in metrics if metric > 0.0)
    if not nonzero:
        baseline = threshold = 0.0
        events: tuple[DetectionEvent, ...] = ()
    else:
        quiet_count = max(5, round(len(nonzero) * 0.55))
        quiet = nonzero[:quiet_count]
        baseline = statistics.median(quiet)
        deviations = [abs(metric - baseline) for metric in quiet]
        mad = statistics.median(deviations) if deviations else 0.0
        threshold = max(60.0, baseline * 3.0, baseline + mad * 8.0)
        events = _detect_events(
            bin_times,
            metrics,
            energies,
            baseline,
            threshold,
            start_seconds,
            end_seconds,
            bin_seconds,
        )
    if progress:
        progress("검출 완료", 1.0)
    return DetectionResult(
        source_path=source_path,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        sample_count=sum(1 for time in times if start_seconds <= time < end_seconds),
        sample_rate=sample_rate,
        baseline_metric=baseline,
        threshold_metric=threshold,
        events=events,
    )
