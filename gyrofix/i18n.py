"""Korean and English text used by the desktop application."""

from __future__ import annotations

import re
from typing import Any, Literal


Language = Literal["ko", "en"]


STRINGS: dict[Language, dict[str, str]] = {
    "ko": {
        "app_title": "DJI Gyro Fix v{version}",
        "subtitle": "지정한 시간의 자이로 데이터만 부드럽게 수정합니다. 영상과 음성은 재인코딩하지 않습니다.",
        "output_auto": "파일을 선택하면 자동으로 정해집니다.",
        "initial_status": "DJI 원본 영상을 선택해 주세요.",
        "file_section": "파일",
        "file_select": "파일 선택",
        "save_location": "저장 위치",
        "time_ranges": "시간 구간",
        "max_ranges": "최대 10개",
        "smoothing": "스무딩",
        "time_hint": "시간 형식: 22.5 또는 00:00:22.500  ·  완전히 빈 행은 자동으로 건너뜁니다.",
        "number": "번호",
        "start_time": "시작 시간(초)",
        "end_time": "종료 시간(초)",
        "manage": "관리",
        "run": "실행",
        "detect": "검출",
        "fix": "FIX",
        "detection_results": "검출 결과",
        "result_prompt": "시간 범위를 입력하고 ‘검출’을 누르세요.",
        "range_added": "처리 시간 구간 {count}개 · 최대 10개까지 추가할 수 있습니다.",
        "range_count": "처리 시간 구간 {count}개",
        "inputs_changed": "입력 범위가 변경됐습니다. 필요하면 다시 ‘검출’을 눌러 주세요.",
        "source_required": "DJI 원본 영상 파일을 선택해 주세요.",
        "file_dialog_title": "DJI 원본 영상 선택",
        "file_dialog_video": "MP4/MOV 영상",
        "file_dialog_all": "모든 파일",
        "file_selected_status": "시간 구간을 정한 뒤 ‘검출’로 확인하거나 바로 ‘FIX’를 누르세요.",
        "busy_title": "작업 진행 중",
        "busy_message": "파일을 안전하게 저장하는 중입니다. 작업이 끝난 뒤 창을 닫아 주세요.",
        "input_error_title": "입력 확인",
        "detecting_ranges": "선택한 {count}개 구간의 자이로 데이터를 확인하는 중…",
        "detecting": "검출 중입니다…",
        "overwrite_title": "파일 덮어쓰기",
        "overwrite_message": "수정본이 이미 있습니다. 덮어쓸까요?\n\n{output}",
        "checking_file": "파일을 확인하는 중…",
        "processing_error_title": "처리 오류",
        "invalid_detection_status": "검출 결과를 읽지 못했습니다.",
        "invalid_detection_message": "올바르지 않은 검출 결과를 받았습니다.",
        "range_result_header": "[{row}번 입력 구간 · {start:.3f}~{end:.3f}초]",
        "detect_complete_events": "검출 완료 · 입력 구간 {ranges}개 · 이상 흔들림 {events}개 · FIX는 입력한 모든 시간 구간을 수정합니다.",
        "detect_complete_none": "검출 완료 · 입력 구간 {ranges}개 · 기준을 넘는 이상 흔들림이 없습니다. FIX는 입력한 모든 시간 구간에 적용할 수 있습니다.",
        "invalid_save_status": "저장 결과를 읽지 못했습니다.",
        "invalid_save_message": "올바르지 않은 저장 결과를 받았습니다.",
        "done_status": "완료 · 구간 {ranges}개 · 자세 샘플 {samples:,}개 수정 · 고주파 변화 {improvement:.1f}% 감소",
        "save_done_title": "저장 완료",
        "save_done_message": "원본은 그대로 두고 수정본을 저장했습니다.\n\n{output}",
        "cancelled_status": "작업이 취소됐습니다. 원본은 변경되지 않았습니다.",
        "error_status": "처리하지 못했습니다. 원본은 변경되지 않았습니다.",
        "preset_strong": "강하게 (권장)",
        "preset_medium": "보통",
        "preset_light": "약하게",
        "preset_very_strong": "매우 강하게",
        "time_required": "시간을 입력해 주세요.",
        "invalid_time_format": "올바르지 않은 시간 형식: {value}",
        "time_nonnegative": "시간은 유한한 0 이상의 값이어야 합니다.",
        "clock_component": "분과 초는 60보다 작아야 합니다: {value}",
        "row_both_or_blank": "{row}번 구간은 시작 시간과 종료 시간을 모두 입력하거나 모두 비워 주세요.",
        "row_check": "{row}번 구간의 시작 시간과 종료 시간을 확인해 주세요.\n{error}",
        "row_end_after": "{row}번 구간의 종료 시간은 시작 시간보다 뒤여야 합니다.",
        "one_range_required": "처리할 시작 시간과 종료 시간을 한 구간 이상 입력해 주세요.",
        "detection_range": "검출 범위  {range}",
        "no_jitter_found": "기준을 넘는 고주파 자세 떨림이 검출되지 않았습니다.",
        "jitter_events_found": "이상 흔들림 {count}개가 검출되었습니다.",
        "mixed_axes": "복합",
        "event_range": "{index}. {start} ~ {end} ({duration:.3f}초)",
        "event_peak": "   최대 지점 {peak} · 강도 {score:.1f}/10 ({severity})",
        "event_detail": "   {event_type} · 영향 축 {axes} · 평상시 대비 {ratio:.1f}배 · 급변 지점 {spikes}개",
        "severity_low": "약함",
        "severity_medium": "중간",
        "severity_high": "강함",
        "event_impact": "순간 자세 충격",
        "event_jitter": "고주파 자세 떨림",
    },
    "en": {
        "app_title": "DJI Gyro Fix v{version}",
        "subtitle": "Smooth only the gyro data in selected time ranges. Video and audio are not re-encoded.",
        "output_auto": "The output path will be set automatically after selecting a file.",
        "initial_status": "Select an original DJI video.",
        "file_section": "File",
        "file_select": "Browse",
        "save_location": "Output path",
        "time_ranges": "Time ranges",
        "max_ranges": "Up to 10",
        "smoothing": "Smoothing",
        "time_hint": "Time format: 22.5 or 00:00:22.500  ·  Completely blank rows are skipped.",
        "number": "No.",
        "start_time": "Start time (sec)",
        "end_time": "End time (sec)",
        "manage": "Manage",
        "run": "Run",
        "detect": "DETECT",
        "fix": "FIX",
        "detection_results": "Detection results",
        "result_prompt": "Enter a time range and click DETECT.",
        "range_added": "{count} time range(s) · You can add up to 10.",
        "range_count": "{count} time range(s)",
        "inputs_changed": "The input range changed. Run DETECT again if needed.",
        "source_required": "Select an original DJI video file.",
        "file_dialog_title": "Select an original DJI video",
        "file_dialog_video": "MP4/MOV video",
        "file_dialog_all": "All files",
        "file_selected_status": "Set the time range, then run DETECT or click FIX directly.",
        "busy_title": "Operation in progress",
        "busy_message": "The file is being saved safely. Close the window after the operation finishes.",
        "input_error_title": "Check input",
        "detecting_ranges": "Checking gyro data in {count} selected range(s)…",
        "detecting": "Detecting…",
        "overwrite_title": "Overwrite file",
        "overwrite_message": "The output file already exists. Overwrite it?\n\n{output}",
        "checking_file": "Checking the file…",
        "processing_error_title": "Processing error",
        "invalid_detection_status": "Could not read the detection result.",
        "invalid_detection_message": "An invalid detection result was received.",
        "range_result_header": "[Input range {row} · {start:.3f}~{end:.3f}s]",
        "detect_complete_events": "Detection complete · {ranges} input range(s) · {events} jitter event(s) · FIX processes every entered range.",
        "detect_complete_none": "Detection complete · {ranges} input range(s) · No jitter exceeded the threshold. FIX can still process every entered range.",
        "invalid_save_status": "Could not read the save result.",
        "invalid_save_message": "An invalid save result was received.",
        "done_status": "Done · {ranges} range(s) · {samples:,} attitude samples changed · high-frequency change reduced by {improvement:.1f}%",
        "save_done_title": "Save complete",
        "save_done_message": "The original was preserved and the fixed copy was saved.\n\n{output}",
        "cancelled_status": "The operation was cancelled. The original was not changed.",
        "error_status": "Processing failed. The original was not changed.",
        "preset_strong": "Strong (recommended)",
        "preset_medium": "Medium",
        "preset_light": "Light",
        "preset_very_strong": "Very strong",
        "time_required": "Enter a time value.",
        "invalid_time_format": "Invalid time format: {value}",
        "time_nonnegative": "Time must be a finite value of zero or greater.",
        "clock_component": "Minutes and seconds must be less than 60: {value}",
        "row_both_or_blank": "Range {row} must have both start and end times, or both fields must be blank.",
        "row_check": "Check the start and end times in range {row}.\n{error}",
        "row_end_after": "The end time in range {row} must be later than the start time.",
        "one_range_required": "Enter at least one start and end time range.",
        "detection_range": "Detection range  {range}",
        "no_jitter_found": "No high-frequency attitude jitter exceeded the detection threshold.",
        "jitter_events_found": "Detected {count} jitter event(s).",
        "mixed_axes": "Mixed",
        "event_range": "{index}. {start} ~ {end} ({duration:.3f}s)",
        "event_peak": "   Peak {peak} · Severity {score:.1f}/10 ({severity})",
        "event_detail": "   {event_type} · Axis {axes} · {ratio:.1f}× baseline · {spikes} spike(s)",
        "severity_low": "Low",
        "severity_medium": "Medium",
        "severity_high": "High",
        "event_impact": "Attitude impact",
        "event_jitter": "High-frequency attitude jitter",
    },
}


def text(language: Language, key: str, **values: Any) -> str:
    """Return formatted UI text, falling back to Korean for unknown languages."""

    table = STRINGS.get(language, STRINGS["ko"])
    try:
        template = table[key]
    except KeyError as error:
        raise KeyError(f"Unknown translation key: {key}") from error
    return template.format(**values)


_STAGE_ENGLISH = {
    "영상을 복사하는 중": "Copying video",
    "DJI 자이로 트랙을 찾는 중": "Locating DJI gyro track",
    "수정된 자이로 데이터 기록 중": "Writing fixed gyro data",
    "완료": "Complete",
    "DJI 자세 데이터 확인 중": "Checking DJI attitude data",
    "선택 구간 자세 데이터 읽는 중": "Reading attitude data in selected range",
    "고주파 흔들림 계산 중": "Calculating high-frequency jitter",
    "검출 완료": "Detection complete",
}


def translate_stage(language: Language, stage: str) -> str:
    """Translate progress text emitted by the language-neutral worker APIs."""

    if language == "ko":
        return stage
    prefix_match = re.fullmatch(r"(\[\d+/\d+\] )(.+)", stage)
    if prefix_match:
        return prefix_match.group(1) + translate_stage(language, prefix_match.group(2))
    interval_match = re.fullmatch(
        r"처리 구간 (\d+)/(\d+) (자세 데이터 읽는 중|스무딩 중)", stage
    )
    if interval_match:
        action = (
            "reading attitude data"
            if interval_match.group(3) == "자세 데이터 읽는 중"
            else "smoothing"
        )
        return f"Processing range {interval_match.group(1)}/{interval_match.group(2)}: {action}"
    return _STAGE_ENGLISH.get(stage, stage)


_ERROR_ENGLISH = {
    "작업이 취소되었습니다.": "The operation was cancelled.",
    "모든 처리 시간은 유한한 값이어야 합니다.": "All processing times must be finite.",
    "모든 처리 구간은 0 이상이며 종료 시간이 시작 시간보다 뒤여야 합니다.": "Every range must start at zero or later and end after it starts.",
    "처리할 시간 구간이 없습니다.": "There are no time ranges to process.",
    "선택한 구간에서 수정 가능한 자세 데이터를 찾지 못했습니다.": "No editable attitude data was found in the selected range.",
    "스무딩 시간은 유한한 양수여야 합니다.": "Smoothing duration must be a finite positive value.",
    "스무딩 강도는 0과 1 사이의 유한한 값이어야 합니다.": "Smoothing strength must be a finite value between zero and one.",
    "원본과 출력 파일은 서로 달라야 합니다.": "The source and output files must be different.",
    "수정본을 저장할 디스크 공간이 부족합니다.": "There is not enough disk space to save the fixed copy.",
    "저장된 파일 크기가 원본과 일치하지 않습니다.": "The saved file size does not match the original.",
    "DJI 자이로 메타데이터(djmd) 트랙을 찾지 못했습니다.": "No DJI gyro metadata (djmd) track was found.",
    "검출 시간은 유한한 값이어야 합니다.": "Detection times must be finite.",
    "검출 구간은 0 이상이며 종료 시간이 시작 시간보다 뒤여야 합니다.": "The detection range must start at zero or later and end after it starts.",
    "검출에 필요한 자세 데이터가 부족합니다.": "There is not enough attitude data for detection.",
    "검출에 필요한 유효한 자세 데이터 시간값이 없습니다.": "No valid attitude timestamps were found for detection.",
    "DJI 메타데이터 샘플을 끝까지 읽지 못했습니다.": "A DJI metadata sample could not be read completely.",
}


def translate_error(language: Language, message: str) -> str:
    """Translate known backend errors while preserving unknown technical details."""

    if language == "ko":
        return message
    if message in _ERROR_ENGLISH:
        return _ERROR_ENGLISH[message]
    replacements = (
        (r"^영상 파일을 찾을 수 없습니다: (.+)$", r"Video file not found: \1"),
        (r"^출력 파일이 이미 존재합니다: (.+)$", r"The output file already exists: \1"),
        (
            r"^종료 시간\(([\d.]+)초\)이 영상 길이\(([\d.]+)초\)를 넘습니다\.$",
            r"The end time (\1s) exceeds the video duration (\2s).",
        ),
    )
    for pattern, replacement in replacements:
        if re.match(pattern, message):
            return re.sub(pattern, replacement, message)
    return message
