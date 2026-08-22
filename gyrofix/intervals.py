"""Validation helpers for optional time-range rows in the desktop UI."""

from __future__ import annotations

from collections.abc import Sequence

from .processor import parse_time


def parse_time_rows(
    rows: Sequence[tuple[str, str]],
) -> list[tuple[int, float, float]]:
    """Return populated rows as ``(row_number, start, end)`` tuples.

    A completely blank row is intentionally ignored. A partially populated row
    is rejected so a missing boundary cannot silently widen the processing range.
    """

    intervals: list[tuple[int, float, float]] = []
    for row_number, (start_value, end_value) in enumerate(rows, start=1):
        start_text = start_value.strip()
        end_text = end_value.strip()
        if not start_text and not end_text:
            continue
        if not start_text or not end_text:
            raise ValueError(
                f"{row_number}번 구간은 시작 시간과 종료 시간을 모두 입력하거나 모두 비워 주세요."
            )
        try:
            start = parse_time(start_text)
            end = parse_time(end_text)
        except ValueError as error:
            raise ValueError(
                f"{row_number}번 구간의 시작 시간과 종료 시간을 확인해 주세요.\n{error}"
            ) from error
        if end <= start:
            raise ValueError(
                f"{row_number}번 구간의 종료 시간은 시작 시간보다 뒤여야 합니다."
            )
        intervals.append((row_number, start, end))

    if not intervals:
        raise ValueError("처리할 시작 시간과 종료 시간을 한 구간 이상 입력해 주세요.")
    return intervals
