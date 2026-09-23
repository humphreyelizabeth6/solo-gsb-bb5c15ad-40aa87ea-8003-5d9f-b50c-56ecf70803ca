"""SQLite 连接管理与启动初始化。

数据库在应用启动（lifespan）时自动创建表结构，无需手工执行迁移脚本。
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import get_settings

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS rolls (
    roll_code      TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS batches (
    batch_id        TEXT PRIMARY KEY,
    roll_code       TEXT NOT NULL REFERENCES rolls(roll_code),
    range_start     INTEGER NOT NULL,
    range_end       INTEGER NOT NULL,
    frames_json     TEXT NOT NULL,
    payload_hash    TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_batches_roll ON batches(roll_code);

-- 每胶卷每帧一行；ref_count 记录有多少个批次包含该帧（跨批重复依据）。
CREATE TABLE IF NOT EXISTS roll_frames (
    roll_code   TEXT NOT NULL REFERENCES rolls(roll_code),
    frame_no    INTEGER NOT NULL,
    ref_count   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (roll_code, frame_no)
);
"""


def _connect(db_path: str, timeout: float) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    # 写操作串行化，避免并发提交时 SQLITE_BUSY。
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """请求内使用的短连接；写入须显式 commit。"""
    settings = get_settings()
    conn = _connect(settings.db_path, settings.db_timeout)
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """创建数据目录（若需要）并初始化全部表结构。幂等，可重复执行。"""
    settings = get_settings()
    parent = os.path.dirname(os.path.abspath(settings.db_path))
    os.makedirs(parent, exist_ok=True)
    conn = _connect(settings.db_path, settings.db_timeout)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
