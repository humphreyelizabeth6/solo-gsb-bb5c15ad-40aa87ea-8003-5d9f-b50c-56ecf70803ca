"""核心业务逻辑：批次导入（幂等）与胶卷汇总。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .frames import Interval, format_interval, merge_intervals, missing_intervals


def canonical_hash(payload: Dict[str, Any]) -> str:
    """按规范化的请求内容计算 SHA-256。

    帧序列先去重再排序，因此帧号顺序不同、批内重复写法不同，
    只要语义相同就得到相同指纹，实现“重复导入相同批次不得改变结果”。
    """
    canonical = json.dumps(
        {
            "roll_code": payload["roll_code"],
            "range_start": payload["range_start"],
            "range_end": payload["range_end"],
            "frames": sorted(set(payload["frames"])),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_roll_state(conn: sqlite3.Connection, roll_code: str) -> Dict[str, Any]:
    batches = conn.execute(
        "SELECT batch_id, range_start, range_end, frames_json, created_at "
        "FROM batches WHERE roll_code = ? ORDER BY created_at, rowid",
        (roll_code,),
    ).fetchall()

    ranges: List[Interval] = [(b["range_start"], b["range_end"]) for b in batches]
    expected = merge_intervals(ranges)

    frame_rows = conn.execute(
        "SELECT frame_no, ref_count FROM roll_frames WHERE roll_code = ?",
        (roll_code,),
    ).fetchall()
    scanned = sorted(r["frame_no"] for r in frame_rows)
    ref_counts = {r["frame_no"]: r["ref_count"] for r in frame_rows}
    # 被两个及以上批次引用的帧 = 跨批重复帧
    duplicate = sorted(f for f, c in ref_counts.items() if c > 1)

    covered = set()
    for start, end in expected:
        covered.update(range(start, end + 1))
    out_of_range = sorted(f for f in scanned if f not in covered)

    missing = missing_intervals(expected, scanned)

    return {
        "expected": expected,
        "scanned": scanned,
        "duplicate": duplicate,
        "out_of_range": out_of_range,
        "missing": missing,
        "batch_count": len(batches),
    }


def build_roll_summary(conn: sqlite3.Connection, roll_code: str) -> Optional[Dict[str, Any]]:
    if conn.execute("SELECT 1 FROM rolls WHERE roll_code = ?", (roll_code,)).fetchone() is None:
        return None
    state = _load_roll_state(conn, roll_code)
    return {
        "roll_code": roll_code,
        "expected_ranges": [format_interval(r) for r in state["expected"]],
        "scanned_frames": state["scanned"],
        "total_scanned_unique": len(state["scanned"]),
        "duplicate_frames": state["duplicate"],
        "duplicate_count": len(state["duplicate"]),
        "missing_ranges": [format_interval(r) for r in state["missing"]],
        "out_of_range_frames": state["out_of_range"],
        "out_of_range_count": len(state["out_of_range"]),
        "batch_count": state["batch_count"],
    }


def build_batch_result(
    conn: sqlite3.Connection, *, batch_id: str, roll_code: str, status: str
) -> Dict[str, Any]:
    summary = build_roll_summary(conn, roll_code)
    assert summary is not None
    result = dict(summary)
    result.pop("scanned_frames", None)
    result.pop("batch_count", None)
    result["status"] = status
    result["batch_id"] = batch_id
    return result


def submit_batch(conn: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    """导入一个扫描批次。

    - batch_id 为空：使用内容指纹。内容相同的再次提交直接返回现状（幂等）。
    - batch_id 已存在且内容一致：幂等返回；内容不一致返回 409。
    - 并发下由 payload_hash 唯一约束兜底，捕获冲突后重新查询。
    """
    roll_code = payload["roll_code"]
    range_start = payload["range_start"]
    range_end = payload["range_end"]
    unique_frames = sorted(set(payload["frames"]))
    frames_json = json.dumps(unique_frames)
    digest = canonical_hash(payload)
    batch_id = (payload.get("batch_id") or f"auto-{digest[:16]}").strip()

    try:
        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute(
            "SELECT batch_id, payload_hash FROM batches WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()

        if existing is None:
            # 内容指纹已存在（同一内容、不同/自动 batch_id）→ 视为重复导入
            same = conn.execute(
                "SELECT batch_id FROM batches WHERE payload_hash = ?", (digest,)
            ).fetchone()
            if same is not None:
                conn.commit()
                return build_batch_result(
                    conn, batch_id=same["batch_id"], roll_code=roll_code,
                    status="duplicate",
                )

            conn.execute(
                "INSERT INTO rolls(roll_code) VALUES (?) ON CONFLICT DO NOTHING",
                (roll_code,),
            )
            conn.execute(
                "INSERT INTO batches"
                "(batch_id, roll_code, range_start, range_end, frames_json, payload_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (batch_id, roll_code, range_start, range_end, frames_json, digest),
            )
            for frame in unique_frames:
                conn.execute(
                    "INSERT INTO roll_frames(roll_code, frame_no, ref_count) "
                    "VALUES (?, ?, 1) "
                    "ON CONFLICT(roll_code, frame_no) "
                    "DO UPDATE SET ref_count = ref_count + 1",
                    (roll_code, frame),
                )
            conn.commit()
            return build_batch_result(
                conn, batch_id=batch_id, roll_code=roll_code, status="created"
            )

        # batch_id 已存在
        if existing["payload_hash"] != digest:
            conn.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    f"批次 {batch_id} 已存在但提交内容与首次不同；"
                    "相同 batch_id 的数据必须一致"
                ),
            )
        conn.commit()
        return build_batch_result(
            conn, batch_id=batch_id, roll_code=roll_code, status="duplicate"
        )

    except sqlite3.IntegrityError as exc:
        # 并发提交撞 payload_hash 唯一约束：对方已写入，按幂等读取
        conn.rollback()
        row = conn.execute(
            "SELECT batch_id FROM batches WHERE payload_hash = ?", (digest,)
        ).fetchone()
        if row is not None:
            return build_batch_result(
                conn, batch_id=row["batch_id"], roll_code=roll_code, status="duplicate"
            )
        raise HTTPException(status_code=409, detail=f"批次冲突：{exc}") from exc
