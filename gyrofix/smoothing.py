from __future__ import annotations

import math
import statistics
from typing import Sequence


Quaternion = list[float]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def normalize(q: Sequence[float]) -> Quaternion:
    if len(q) != 4:
        raise ValueError("Quaternion must contain four components")
    norm = math.sqrt(dot(q, q))
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError("Invalid zero-length quaternion")
    return [value / norm for value in q]


def slerp(a: Sequence[float], b: Sequence[float], amount: float) -> Quaternion:
    qa = normalize(a)
    qb = normalize(b)
    cosine = dot(qa, qb)
    if cosine < 0.0:
        qb = [-value for value in qb]
        cosine = -cosine
    cosine = min(1.0, max(-1.0, cosine))
    amount = min(1.0, max(0.0, amount))
    if cosine > 0.9995:
        return normalize([x + amount * (y - x) for x, y in zip(qa, qb)])
    angle = math.acos(cosine)
    denominator = math.sin(angle)
    left = math.sin((1.0 - amount) * angle) / denominator
    right = math.sin(amount * angle) / denominator
    return normalize([left * x + right * y for x, y in zip(qa, qb)])


def multiply(a: Sequence[float], b: Sequence[float]) -> Quaternion:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return normalize(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ]
    )


def inverse(q: Sequence[float]) -> Quaternion:
    w, x, y, z = normalize(q)
    return [w, -x, -y, -z]


def _smoothstep(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def _box_blur(quaternions: Sequence[Sequence[float]], radius: int) -> list[Quaternion]:
    if radius <= 0 or len(quaternions) < 2:
        return [normalize(q) for q in quaternions]
    prefixes = [[0.0] * (len(quaternions) + 1) for _ in range(4)]
    for index, quaternion in enumerate(quaternions):
        for component in range(4):
            prefixes[component][index + 1] = (
                prefixes[component][index] + quaternion[component]
            )
    result: list[Quaternion] = []
    for index in range(len(quaternions)):
        first = max(0, index - radius)
        last = min(len(quaternions), index + radius + 1)
        count = last - first
        average = [
            (prefixes[component][last] - prefixes[component][first]) / count
            for component in range(4)
        ]
        result.append(normalize(average))
    return result


def smooth_quaternions(
    times: Sequence[float],
    quaternions: Sequence[Sequence[float]],
    start_seconds: float,
    end_seconds: float,
    smoothing_ms: float = 180.0,
    strength: float = 1.0,
) -> list[Quaternion]:
    """Smooth only the requested interval and retain each source quaternion sign.

    Three moving-average passes approximate a Gaussian low-pass filter. Processing
    happens on the quaternion components after sign unwrapping, then every result is
    normalized and blended with the source near the interval boundaries.
    """
    if len(times) != len(quaternions):
        raise ValueError("Time and quaternion arrays have different lengths")
    if not quaternions:
        return []
    if end_seconds <= start_seconds:
        raise ValueError("End time must be after start time")
    if not math.isfinite(smoothing_ms) or smoothing_ms <= 0:
        raise ValueError("Smoothing duration must be positive")
    if not math.isfinite(strength):
        raise ValueError("Smoothing strength must be finite")
    if any(not math.isfinite(time) for time in times):
        raise ValueError("Sample times must be finite")

    source = [normalize(q) for q in quaternions]
    continuous: list[Quaternion] = []
    for quaternion in source:
        value = quaternion
        if continuous and dot(continuous[-1], value) < 0.0:
            value = [-component for component in value]
        continuous.append(value)

    intervals = [
        right - left
        for left, right in zip(times, times[1:])
        if right > left and math.isfinite(right - left)
    ]
    if not intervals:
        return [list(q) for q in quaternions]
    sample_interval = statistics.median(intervals[: min(5000, len(intervals))])
    sigma_samples = max(1, round((smoothing_ms / 1000.0) / sample_interval))
    filtered = continuous
    for _ in range(3):
        filtered = _box_blur(filtered, sigma_samples)

    duration = end_seconds - start_seconds
    edge_seconds = min(0.20, duration * 0.15)
    strength = min(1.0, max(0.0, strength))
    start_index = min(range(len(times)), key=lambda index: abs(times[index] - start_seconds))
    end_index = min(range(len(times)), key=lambda index: abs(times[index] - end_seconds))
    start_correction = multiply(continuous[start_index], inverse(filtered[start_index]))
    end_correction = multiply(continuous[end_index], inverse(filtered[end_index]))
    identity = [1.0, 0.0, 0.0, 0.0]
    if start_correction[0] < 0.0:
        start_correction = [-value for value in start_correction]
    if end_correction[0] < 0.0:
        end_correction = [-value for value in end_correction]

    output: list[Quaternion] = []
    for time, original, aligned, smoothed in zip(times, source, continuous, filtered):
        if time <= start_seconds or time >= end_seconds:
            output.append(list(original))
            continue
        value = smoothed
        if edge_seconds > 0 and time < start_seconds + edge_seconds:
            correction = slerp(
                start_correction,
                identity,
                _smoothstep((time - start_seconds) / edge_seconds),
            )
            value = multiply(correction, value)
        if edge_seconds > 0 and time > end_seconds - edge_seconds:
            correction = slerp(
                identity,
                end_correction,
                _smoothstep((time - (end_seconds - edge_seconds)) / edge_seconds),
            )
            value = multiply(correction, value)
        if strength < 1.0:
            value = slerp(aligned, value, strength)
        if dot(value, original) < 0.0:
            value = [-component for component in value]
        output.append(value)
    return output


def angular_acceleration_score(
    times: Sequence[float], quaternions: Sequence[Sequence[float]], start: float, end: float
) -> float:
    velocities: list[tuple[float, float]] = []
    normalized = [normalize(q) for q in quaternions]
    for index in range(1, len(times)):
        if not (start <= times[index] <= end):
            continue
        interval = times[index] - times[index - 1]
        if interval <= 0:
            continue
        cosine = min(1.0, max(-1.0, abs(dot(normalized[index - 1], normalized[index]))))
        angle = 2.0 * math.acos(cosine)
        velocities.append((times[index], angle / interval))
    accelerations: list[float] = []
    for (left_time, left), (right_time, right) in zip(velocities, velocities[1:]):
        interval = right_time - left_time
        if interval > 0:
            accelerations.append(abs(right - left) / interval)
    return statistics.median(accelerations) if accelerations else 0.0
