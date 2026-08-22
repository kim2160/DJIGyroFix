from __future__ import annotations

from dataclasses import dataclass
import math
import struct
from typing import Iterator, Sequence


class ProtobufError(RuntimeError):
    pass


@dataclass(frozen=True)
class Field:
    number: int
    wire_type: int
    key_start: int
    value_start: int
    value_end: int
    payload_start: int
    payload_end: int


@dataclass
class QuaternionRef:
    values: list[float]
    offsets: list[int | None]


def _read_varint(data: bytes | bytearray, position: int, end: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while position < end and shift < 70:
        byte = data[position]
        position += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, position
        shift += 7
    raise ProtobufError("Invalid protobuf varint")


def iter_fields(
    data: bytes | bytearray, start: int = 0, end: int | None = None
) -> Iterator[Field]:
    if end is None:
        end = len(data)
    if start < 0 or end < start or end > len(data):
        raise ProtobufError("Invalid protobuf message boundary")
    position = start
    while position < end:
        key_start = position
        key, position = _read_varint(data, position, end)
        number, wire_type = key >> 3, key & 7
        if number == 0:
            raise ProtobufError("Invalid protobuf field number 0")
        value_start = position
        if wire_type == 0:
            _, position = _read_varint(data, position, end)
            payload_start, payload_end = value_start, position
        elif wire_type == 1:
            position += 8
            payload_start, payload_end = value_start, position
        elif wire_type == 2:
            length, payload_start = _read_varint(data, position, end)
            payload_end = payload_start + length
            position = payload_end
        elif wire_type == 5:
            position += 4
            payload_start, payload_end = value_start, position
        else:
            raise ProtobufError(f"Unsupported protobuf wire type {wire_type}")
        if position > end:
            raise ProtobufError("Protobuf field exceeds sample boundary")
        yield Field(
            number,
            wire_type,
            key_start,
            value_start,
            position,
            payload_start,
            payload_end,
        )


def _messages_at_path(
    data: bytes | bytearray,
    start: int,
    end: int,
    path: Sequence[int],
) -> list[tuple[int, int]]:
    spans = [(start, end)]
    for field_number in path:
        next_spans: list[tuple[int, int]] = []
        for span_start, span_end in spans:
            for field in iter_fields(data, span_start, span_end):
                if field.number == field_number and field.wire_type == 2:
                    next_spans.append((field.payload_start, field.payload_end))
        spans = next_spans
        if not spans:
            break
    return spans


def detect_dji_variant(first_samples: Sequence[bytes]) -> str:
    probe = b"".join(sample[:1024] for sample in first_samples[:5])
    lower = probe.lower()
    if b"oq101" in lower:
        return "oq101"
    if b"wa530" in lower:
        return "wa530"
    return "wm169"


def quaternion_refs(data: bytes | bytearray, variant: str) -> list[QuaternionRef]:
    paths = {
        "wm169": (3, 3, 2, 3),
        "wa530": (3, 3, 4, 3),
        "oq101": (3, 3, 2, 1, 3),
    }
    try:
        path = paths[variant]
    except KeyError as error:
        raise ProtobufError(f"Unknown DJI metadata variant: {variant}") from error

    refs: list[QuaternionRef] = []
    for start, end in _messages_at_path(data, 0, len(data), path):
        values = [0.0, 0.0, 0.0, 0.0]
        offsets: list[int | None] = [None, None, None, None]
        for field in iter_fields(data, start, end):
            if 1 <= field.number <= 4 and field.wire_type == 5:
                index = field.number - 1
                values[index] = struct.unpack_from("<f", data, field.payload_start)[0]
                offsets[index] = field.payload_start
        norm = math.sqrt(sum(value * value for value in values))
        if 0.5 <= norm <= 1.5 and all(math.isfinite(value) for value in values):
            refs.append(QuaternionRef(values, offsets))
    return refs


def write_quaternion(
    data: bytearray, ref: QuaternionRef, values: Sequence[float], tolerance: float = 1e-7
) -> None:
    if len(values) != 4 or any(not math.isfinite(value) for value in values):
        raise ProtobufError("Quaternion must contain four finite components")
    for index, value in enumerate(values):
        offset = ref.offsets[index]
        if offset is None:
            if abs(value) > tolerance:
                raise ProtobufError(
                    "A zero-valued quaternion component is omitted in the source protobuf; "
                    "it cannot be changed without resizing the MP4 sample."
                )
            continue
        struct.pack_into("<f", data, offset, float(value))
