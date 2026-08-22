from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import shutil
import tempfile
import threading
from typing import Callable, Sequence

from .mp4 import Track, find_dji_metadata_track, parse_tracks
from .protobuf import (
    QuaternionRef,
    detect_dji_variant,
    quaternion_refs,
    write_quaternion,
)
from .smoothing import angular_acceleration_score, smooth_quaternions


class ProcessingCancelled(RuntimeError):
    pass


ProgressCallback = Callable[[str, float], None]


@dataclass(frozen=True)
class ProcessingResult:
    output_path: Path
    duration_seconds: float
    variant: str
    source_samples_read: int
    metadata_samples_changed: int
    quaternions_changed: int
    score_before: float
    score_after: float
    interval_count: int = 1

    @property
    def improvement_percent(self) -> float:
        if self.score_before <= 0:
            return 0.0
        return max(0.0, (1.0 - self.score_after / self.score_before) * 100.0)


@dataclass
class _Point:
    time: float
    sample_index: int
    ref: QuaternionRef


def default_output_path(source: os.PathLike[str] | str) -> Path:
    path = Path(source)
    return path.with_name(f"{path.stem}_gyro_fixed{path.suffix}")


def parse_time(value: str | float | int) -> float:
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        text = value.strip().replace(",", ".")
        if not text:
            raise ValueError("시간을 입력해 주세요.")
        parts = text.split(":")
        if len(parts) > 3:
            raise ValueError(f"올바르지 않은 시간 형식: {value}")
        try:
            numbers = [float(part) for part in parts]
        except ValueError as error:
            raise ValueError(f"올바르지 않은 시간 형식: {value}") from error
        if any(not math.isfinite(number) or number < 0.0 for number in numbers):
            raise ValueError("시간은 유한한 0 이상의 값이어야 합니다.")
        if len(numbers) > 1 and any(number >= 60.0 for number in numbers[1:]):
            raise ValueError(f"분과 초는 60보다 작아야 합니다: {value}")
        seconds = 0.0
        for number in numbers:
            seconds = seconds * 60.0 + number
    if not math.isfinite(seconds) or seconds < 0.0:
        raise ValueError("시간은 유한한 0 이상의 값이어야 합니다.")
    return seconds


def inspect_video(source: os.PathLike[str] | str) -> tuple[list[Track], Track, str]:
    source_path = Path(source)
    tracks = parse_tracks(source_path)
    metadata = find_dji_metadata_track(tracks)
    first_samples: list[bytes] = []
    with source_path.open("rb") as file:
        for index in range(min(5, len(metadata.sample_offsets))):
            file.seek(metadata.sample_offsets[index])
            sample = file.read(metadata.sample_sizes[index])
            if len(sample) != metadata.sample_sizes[index]:
                raise OSError("DJI 메타데이터 샘플을 끝까지 읽지 못했습니다.")
            first_samples.append(sample)
    return tracks, metadata, detect_dji_variant(first_samples)


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProcessingCancelled("작업이 취소되었습니다.")


def _copy_with_progress(
    source: Path,
    destination: Path,
    callback: ProgressCallback | None,
    cancel: threading.Event | None,
) -> None:
    total = source.stat().st_size
    copied = 0
    buffer_size = 16 * 1024 * 1024
    with source.open("rb", buffering=0) as input_file, destination.open("wb", buffering=0) as output_file:
        while True:
            _check_cancel(cancel)
            chunk = input_file.read(buffer_size)
            if not chunk:
                break
            output_file.write(chunk)
            copied += len(chunk)
            if callback:
                callback("영상을 복사하는 중", 0.12 + 0.80 * copied / total)
        output_file.flush()
        os.fsync(output_file.fileno())


def _merge_intervals(
    intervals: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("모든 처리 시간은 유한한 값이어야 합니다.")
        if start < 0.0 or end <= start:
            raise ValueError(
                "모든 처리 구간은 0 이상이며 종료 시간이 시작 시간보다 뒤여야 합니다."
            )
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    if not merged:
        raise ValueError("처리할 시간 구간이 없습니다.")
    return merged


def _prepare_interval(
    source_path: Path,
    metadata: Track,
    variant: str,
    start_seconds: float,
    end_seconds: float,
    smoothing_ms: float,
    strength: float,
    patches: dict[int, bytes],
    progress: ProgressCallback | None,
    cancel: threading.Event | None,
    interval_index: int,
    interval_count: int,
) -> tuple[int, int, float, float]:
    context_seconds = max(0.75, smoothing_ms / 1000.0 * 4.0)
    sample_indices = list(
        metadata.sample_range(
            max(0.0, start_seconds - context_seconds),
            min(metadata.duration_seconds, end_seconds + context_seconds),
        )
    )
    sample_buffers: dict[int, bytearray] = {}
    points: list[_Point] = []

    with source_path.open("rb") as file:
        for sequence, sample_index in enumerate(sample_indices):
            _check_cancel(cancel)
            if sample_index in patches:
                data = bytearray(patches[sample_index])
            else:
                file.seek(metadata.sample_offsets[sample_index])
                raw_sample = file.read(metadata.sample_sizes[sample_index])
                if len(raw_sample) != metadata.sample_sizes[sample_index]:
                    raise OSError("DJI 메타데이터 샘플을 끝까지 읽지 못했습니다.")
                data = bytearray(raw_sample)
            refs = quaternion_refs(data, variant)
            sample_buffers[sample_index] = data
            sample_time = metadata.sample_dts[sample_index] / metadata.timescale
            if sample_index + 1 < len(metadata.sample_dts):
                next_time = metadata.sample_dts[sample_index + 1] / metadata.timescale
            else:
                next_time = metadata.duration_seconds
            for subindex, ref in enumerate(refs):
                time = sample_time + (next_time - sample_time) * subindex / max(1, len(refs))
                points.append(_Point(time, sample_index, ref))
            if progress and sequence % 50 == 0:
                interval_fraction = (interval_index + sequence / max(1, len(sample_indices))) / interval_count
                progress(
                    f"처리 구간 {interval_index + 1}/{interval_count} 자세 데이터 읽는 중",
                    0.02 + 0.06 * interval_fraction,
                )

    selected_count = sum(1 for point in points if start_seconds < point.time < end_seconds)
    if selected_count == 0:
        raise RuntimeError("선택한 구간에서 수정 가능한 자세 데이터를 찾지 못했습니다.")
    if progress:
        progress(
            f"처리 구간 {interval_index + 1}/{interval_count} 스무딩 중",
            0.08 + 0.03 * (interval_index + 1) / interval_count,
        )
    times = [point.time for point in points]
    originals = [point.ref.values for point in points]
    smoothed = smooth_quaternions(
        times,
        originals,
        start_seconds,
        end_seconds,
        smoothing_ms=smoothing_ms,
        strength=strength,
    )
    score_before = angular_acceleration_score(times, originals, start_seconds, end_seconds)
    score_after = angular_acceleration_score(times, smoothed, start_seconds, end_seconds)

    changed_samples: set[int] = set()
    for point, values in zip(points, smoothed):
        if not (start_seconds < point.time < end_seconds):
            continue
        write_quaternion(sample_buffers[point.sample_index], point.ref, values)
        changed_samples.add(point.sample_index)
    for sample_index in changed_samples:
        patches[sample_index] = bytes(sample_buffers[sample_index])
    return len(sample_indices), selected_count, score_before, score_after


def process_video_intervals(
    source: os.PathLike[str] | str,
    output: os.PathLike[str] | str,
    intervals: list[tuple[float, float]],
    *,
    smoothing_ms: float = 180.0,
    strength: float = 1.0,
    overwrite: bool = False,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> ProcessingResult:
    if not math.isfinite(smoothing_ms) or smoothing_ms <= 0.0:
        raise ValueError("스무딩 시간은 유한한 양수여야 합니다.")
    if not math.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise ValueError("스무딩 강도는 0과 1 사이의 유한한 값이어야 합니다.")
    merged_intervals = _merge_intervals(intervals)
    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {source_path}")
    if source_path == output_path:
        raise ValueError("원본과 출력 파일은 서로 달라야 합니다.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"출력 파일이 이미 존재합니다: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    free_space = shutil.disk_usage(output_path.parent).free
    if free_space < source_path.stat().st_size + 64 * 1024 * 1024:
        raise OSError("수정본을 저장할 디스크 공간이 부족합니다.")

    _check_cancel(cancel)
    if progress:
        progress("DJI 자이로 트랙을 찾는 중", 0.01)
    _, metadata, variant = inspect_video(source_path)
    if merged_intervals[-1][1] > metadata.duration_seconds:
        raise ValueError(
            f"종료 시간({merged_intervals[-1][1]:.3f}초)이 영상 길이({metadata.duration_seconds:.3f}초)를 넘습니다."
        )
    patches: dict[int, bytes] = {}
    source_samples_read = 0
    quaternion_count = 0
    weighted_before = 0.0
    weighted_after = 0.0
    for interval_index, (start_seconds, end_seconds) in enumerate(merged_intervals):
        samples_read, selected_count, before, after = _prepare_interval(
            source_path,
            metadata,
            variant,
            start_seconds,
            end_seconds,
            smoothing_ms,
            strength,
            patches,
            progress,
            cancel,
            interval_index,
            len(merged_intervals),
        )
        source_samples_read += samples_read
        quaternion_count += selected_count
        weighted_before += before * selected_count
        weighted_after += after * selected_count
    score_before = weighted_before / max(1, quaternion_count)
    score_after = weighted_after / max(1, quaternion_count)

    descriptor, partial_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".partial",
        dir=output_path.parent,
    )
    os.close(descriptor)
    partial_path = Path(partial_name)
    try:
        _copy_with_progress(source_path, partial_path, progress, cancel)
        _check_cancel(cancel)
        if progress:
            progress("수정된 자이로 데이터 기록 중", 0.94)
        with partial_path.open("r+b", buffering=0) as output_file:
            for sample_index in sorted(patches):
                output_file.seek(metadata.sample_offsets[sample_index])
                output_file.write(patches[sample_index])
            output_file.flush()
            os.fsync(output_file.fileno())

        if partial_path.stat().st_size != source_path.stat().st_size:
            raise RuntimeError("저장된 파일 크기가 원본과 일치하지 않습니다.")
        try:
            shutil.copystat(source_path, partial_path)
        except OSError:
            # Timestamp preservation is best-effort and must not invalidate a
            # fully written video on filesystems that reject metadata updates.
            pass
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {output_path}")
        os.replace(partial_path, output_path)
    except BaseException:
        try:
            partial_path.unlink(missing_ok=True)
        except OSError:
            # Preserve the original processing error if cleanup is rejected by
            # antivirus software or another process briefly holding the file.
            pass
        raise
    if progress:
        progress("완료", 1.0)

    return ProcessingResult(
        output_path=output_path,
        duration_seconds=metadata.duration_seconds,
        variant=variant,
        source_samples_read=source_samples_read,
        metadata_samples_changed=len(patches),
        quaternions_changed=quaternion_count,
        score_before=score_before,
        score_after=score_after,
        interval_count=len(merged_intervals),
    )


def process_video(
    source: os.PathLike[str] | str,
    output: os.PathLike[str] | str,
    start_seconds: float,
    end_seconds: float,
    *,
    smoothing_ms: float = 180.0,
    strength: float = 1.0,
    overwrite: bool = False,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> ProcessingResult:
    return process_video_intervals(
        source,
        output,
        [(start_seconds, end_seconds)],
        smoothing_ms=smoothing_ms,
        strength=strength,
        overwrite=overwrite,
        progress=progress,
        cancel=cancel,
    )
