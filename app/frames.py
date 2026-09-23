"""帧号区间的纯函数工具。"""
from __future__ import annotations

from typing import List, Tuple

# 连续区间，闭区间 [start, end]
Interval = Tuple[int, int]


def merge_intervals(intervals: List[Interval]) -> List[Interval]:
    """合并重叠/相邻的整数闭区间。输入无序也可。"""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged: List[Interval] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        # 相邻区间（差 1）之间不存在缺帧，一并合并
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def missing_intervals(expected: List[Interval], scanned) -> List[Interval]:
    """返回 ``scanned`` 帧号集合在合并后的预期范围内未覆盖的连续区间。"""
    scanned_set = set(scanned)
    result: List[Interval] = []
    for start, end in merge_intervals(expected):
        gap_start = None
        for frame in range(start, end + 1):
            if frame in scanned_set:
                if gap_start is not None:
                    result.append((gap_start, frame - 1))
                    gap_start = None
            elif gap_start is None:
                gap_start = frame
        if gap_start is not None:
            result.append((gap_start, end))
    return result


def format_interval(pair: Interval) -> str:
    start, end = pair
    return str(start) if start == end else f"{start}-{end}"
