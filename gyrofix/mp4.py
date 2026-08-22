from __future__ import annotations

from dataclasses import dataclass, field
import bisect
import os
import struct
from typing import BinaryIO, Iterable, Iterator


class Mp4Error(RuntimeError):
    pass


@dataclass(frozen=True)
class Box:
    type: str
    start: int
    size: int
    header_size: int

    @property
    def data_start(self) -> int:
        return self.start + self.header_size

    @property
    def end(self) -> int:
        return self.start + self.size


@dataclass
class Track:
    track_id: int = 0
    handler_type: str = ""
    handler_name: str = ""
    sample_entry: str = ""
    timescale: int = 0
    duration: int = 0
    sample_sizes: list[int] = field(default_factory=list)
    chunk_offsets: list[int] = field(default_factory=list)
    stsc: list[tuple[int, int, int]] = field(default_factory=list)
    stts: list[tuple[int, int]] = field(default_factory=list)
    sample_offsets: list[int] = field(default_factory=list)
    sample_dts: list[int] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return self.duration / self.timescale if self.timescale else 0.0

    def finalize(self) -> None:
        if not self.sample_sizes:
            raise Mp4Error(f"Track {self.track_id}: sample sizes are missing")
        if not self.chunk_offsets or not self.stsc:
            raise Mp4Error(f"Track {self.track_id}: chunk table is missing")
        if not self.stts:
            raise Mp4Error(f"Track {self.track_id}: timing table is missing")
        if self.timescale <= 0:
            raise Mp4Error(f"Track {self.track_id}: invalid timescale {self.timescale}")
        if self.stsc[0][0] != 1:
            raise Mp4Error(f"Track {self.track_id}: first stsc entry must start at chunk 1")
        previous_chunk = 0
        for first_chunk, samples_per_chunk, description_index in self.stsc:
            if (
                first_chunk <= previous_chunk
                or samples_per_chunk <= 0
                or description_index <= 0
            ):
                raise Mp4Error(f"Track {self.track_id}: invalid stsc table")
            previous_chunk = first_chunk

        offsets: list[int] = []
        sample_index = 0
        stsc_index = 0
        for chunk_index, chunk_offset in enumerate(self.chunk_offsets, start=1):
            if sample_index >= len(self.sample_sizes):
                break
            while (
                stsc_index + 1 < len(self.stsc)
                and self.stsc[stsc_index + 1][0] <= chunk_index
            ):
                stsc_index += 1
            samples_per_chunk = self.stsc[stsc_index][1]
            offset = chunk_offset
            for _ in range(samples_per_chunk):
                if sample_index >= len(self.sample_sizes):
                    break
                offsets.append(offset)
                offset += self.sample_sizes[sample_index]
                sample_index += 1

        if len(offsets) != len(self.sample_sizes):
            raise Mp4Error(
                f"Track {self.track_id}: mapped {len(offsets)} of "
                f"{len(self.sample_sizes)} samples"
            )
        self.sample_offsets = offsets

        dts: list[int] = []
        value = 0
        for count, delta in self.stts:
            if count <= 0:
                raise Mp4Error(f"Track {self.track_id}: invalid stts table")
            remaining = len(self.sample_sizes) - len(dts)
            take = min(count, remaining)
            dts.extend(value + index * delta for index in range(take))
            value += count * delta
            if len(dts) == len(self.sample_sizes):
                break
        if len(dts) < len(self.sample_sizes):
            raise Mp4Error(
                f"Track {self.track_id}: timing table has {len(dts)} entries for "
                f"{len(self.sample_sizes)} samples"
            )
        self.sample_dts = dts[: len(self.sample_sizes)]

    def sample_range(self, start_seconds: float, end_seconds: float) -> range:
        if not self.sample_dts or not self.timescale:
            return range(0)
        start_tick = max(0, int(start_seconds * self.timescale))
        end_tick = max(start_tick, int(end_seconds * self.timescale))
        first = max(0, bisect.bisect_left(self.sample_dts, start_tick) - 1)
        last = min(len(self.sample_dts), bisect.bisect_right(self.sample_dts, end_tick) + 1)
        return range(first, last)


def _decode_type(raw: bytes) -> str:
    return raw.decode("latin-1", errors="replace")


def iter_boxes(file: BinaryIO, start: int, end: int) -> Iterator[Box]:
    position = start
    while position + 8 <= end:
        file.seek(position)
        header = file.read(8)
        if len(header) != 8:
            break
        size32, raw_type = struct.unpack(">I4s", header)
        header_size = 8
        if size32 == 1:
            large = file.read(8)
            if len(large) != 8:
                raise Mp4Error(f"Truncated extended box header at {position}")
            size = struct.unpack(">Q", large)[0]
            header_size = 16
        elif size32 == 0:
            size = end - position
        else:
            size = size32
        if size < header_size or position + size > end:
            raise Mp4Error(
                f"Invalid MP4 box {_decode_type(raw_type)!r} at {position}: size={size}"
            )
        yield Box(_decode_type(raw_type), position, size, header_size)
        position += size


def _find_child(file: BinaryIO, parent: Box, type_name: str) -> Box | None:
    return next(
        (box for box in iter_boxes(file, parent.data_start, parent.end) if box.type == type_name),
        None,
    )


def _read_exact(file: BinaryIO, offset: int, size: int) -> bytes:
    file.seek(offset)
    data = file.read(size)
    if len(data) != size:
        raise Mp4Error(f"Unexpected end of file at {offset}")
    return data


def _parse_tkhd(file: BinaryIO, box: Box) -> int:
    data = _read_exact(file, box.data_start, min(box.size - box.header_size, 32))
    if len(data) < 1:
        raise Mp4Error("Invalid tkhd box")
    version = data[0]
    required = 24 if version == 1 else 16
    if len(data) < required:
        raise Mp4Error("Invalid tkhd box")
    return struct.unpack_from(">I", data, 20 if version == 1 else 12)[0]


def _parse_mdhd(file: BinaryIO, box: Box) -> tuple[int, int]:
    data = _read_exact(file, box.data_start, min(box.size - box.header_size, 40))
    if len(data) < 1:
        raise Mp4Error("Invalid mdhd box")
    version = data[0]
    if version == 1:
        if len(data) < 32:
            raise Mp4Error("Invalid mdhd box")
        return struct.unpack_from(">IQ", data, 20)
    if len(data) < 20:
        raise Mp4Error("Invalid mdhd box")
    return struct.unpack_from(">II", data, 12)


def _parse_hdlr(file: BinaryIO, box: Box) -> tuple[str, str]:
    data = _read_exact(file, box.data_start, box.size - box.header_size)
    if len(data) < 12:
        raise Mp4Error("Invalid hdlr box")
    handler = _decode_type(data[8:12])
    name = data[24:].rstrip(b"\0").decode("utf-8", errors="replace") if len(data) > 24 else ""
    return handler, name


def _parse_stsd(file: BinaryIO, box: Box) -> str:
    data = _read_exact(file, box.data_start, min(box.size - box.header_size, 24))
    if len(data) < 16 or struct.unpack_from(">I", data, 4)[0] == 0:
        return ""
    return _decode_type(data[12:16])


def _parse_stts(file: BinaryIO, box: Box) -> list[tuple[int, int]]:
    data = _read_exact(file, box.data_start, box.size - box.header_size)
    if len(data) < 8:
        raise Mp4Error("Invalid stts box")
    count = struct.unpack_from(">I", data, 4)[0]
    if len(data) < 8 + count * 8:
        raise Mp4Error("Invalid stts box")
    return [struct.unpack_from(">II", data, 8 + index * 8) for index in range(count)]


def _parse_stsc(file: BinaryIO, box: Box) -> list[tuple[int, int, int]]:
    data = _read_exact(file, box.data_start, box.size - box.header_size)
    if len(data) < 8:
        raise Mp4Error("Invalid stsc box")
    count = struct.unpack_from(">I", data, 4)[0]
    if len(data) < 8 + count * 12:
        raise Mp4Error("Invalid stsc box")
    return [struct.unpack_from(">III", data, 8 + index * 12) for index in range(count)]


def _parse_stsz(file: BinaryIO, box: Box) -> list[int]:
    data = _read_exact(file, box.data_start, box.size - box.header_size)
    if len(data) < 12:
        raise Mp4Error("Invalid stsz box")
    fixed_size, count = struct.unpack_from(">II", data, 4)
    if fixed_size:
        return [fixed_size] * count
    if len(data) < 12 + count * 4:
        raise Mp4Error("Invalid stsz sample table")
    return list(struct.unpack_from(f">{count}I", data, 12))


def _parse_chunk_offsets(file: BinaryIO, box: Box) -> list[int]:
    data = _read_exact(file, box.data_start, box.size - box.header_size)
    if len(data) < 8:
        raise Mp4Error(f"Invalid {box.type} box")
    count = struct.unpack_from(">I", data, 4)[0]
    width, code = (8, "Q") if box.type == "co64" else (4, "I")
    if len(data) < 8 + count * width:
        raise Mp4Error(f"Invalid {box.type} box")
    return list(struct.unpack_from(f">{count}{code}", data, 8))


def _parse_track(file: BinaryIO, trak: Box) -> Track:
    track = Track()
    tkhd = _find_child(file, trak, "tkhd")
    mdia = _find_child(file, trak, "mdia")
    if not tkhd or not mdia:
        raise Mp4Error("Track is missing tkhd or mdia")
    track.track_id = _parse_tkhd(file, tkhd)

    mdhd = _find_child(file, mdia, "mdhd")
    hdlr = _find_child(file, mdia, "hdlr")
    minf = _find_child(file, mdia, "minf")
    if not mdhd or not hdlr or not minf:
        raise Mp4Error(f"Track {track.track_id}: incomplete mdia box")
    track.timescale, track.duration = _parse_mdhd(file, mdhd)
    track.handler_type, track.handler_name = _parse_hdlr(file, hdlr)

    stbl = _find_child(file, minf, "stbl")
    if not stbl:
        raise Mp4Error(f"Track {track.track_id}: missing stbl")
    children = {box.type: box for box in iter_boxes(file, stbl.data_start, stbl.end)}
    if "stsd" in children:
        track.sample_entry = _parse_stsd(file, children["stsd"])
    if "stts" in children:
        track.stts = _parse_stts(file, children["stts"])
    if "stsc" in children:
        track.stsc = _parse_stsc(file, children["stsc"])
    if "stsz" in children:
        track.sample_sizes = _parse_stsz(file, children["stsz"])
    chunk_box = children.get("co64") or children.get("stco")
    if chunk_box:
        track.chunk_offsets = _parse_chunk_offsets(file, chunk_box)
    track.finalize()
    return track


def parse_tracks(path: os.PathLike[str] | str) -> list[Track]:
    size = os.path.getsize(path)
    with open(path, "rb") as file:
        moov = next((box for box in iter_boxes(file, 0, size) if box.type == "moov"), None)
        if not moov:
            raise Mp4Error("MP4 moov box was not found")
        tracks = [
            _parse_track(file, box)
            for box in iter_boxes(file, moov.data_start, moov.end)
            if box.type == "trak"
        ]
    if not tracks:
        raise Mp4Error("MP4 track was not found")
    for track in tracks:
        for offset, sample_size in zip(track.sample_offsets, track.sample_sizes):
            if offset < 0 or sample_size < 0 or offset + sample_size > size:
                raise Mp4Error(
                    f"Track {track.track_id}: sample points outside the file boundary"
                )
    return tracks


def find_dji_metadata_track(tracks: Iterable[Track]) -> Track:
    candidates = [
        track
        for track in tracks
        if track.sample_entry == "djmd"
        or "dji meta" in track.handler_name.casefold()
        or "cam meta" in track.handler_name.casefold()
    ]
    if not candidates:
        raise Mp4Error("DJI 자이로 메타데이터(djmd) 트랙을 찾지 못했습니다.")
    return max(candidates, key=lambda track: len(track.sample_sizes))
