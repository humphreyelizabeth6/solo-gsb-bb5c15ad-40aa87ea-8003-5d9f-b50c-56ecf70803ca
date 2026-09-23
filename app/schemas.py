"""请求 / 响应 Pydantic 模型。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class BatchCreate(BaseModel):
    roll_code: str = Field(..., min_length=1, description="胶卷编号")
    range_start: int = Field(..., description="预期帧号起始（含）")
    range_end: int = Field(..., description="预期帧号结束（含）")
    frames: List[int] = Field(..., description="本批实际扫描到的帧号列表")
    batch_id: Optional[str] = Field(
        None, description="批次标识；留空则按请求内容自动生成（内容相同即为同一批）"
    )

    @field_validator("roll_code")
    @classmethod
    def _roll_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("roll_code 不能为空字符串")
        return v

    @field_validator("range_end")
    @classmethod
    def _range_order(cls, v: int, info) -> int:
        start = info.data.get("range_start")
        if start is not None and v < start:
            raise ValueError("range_end 不能小于 range_start")
        return v

    @field_validator("frames")
    @classmethod
    def _frames_positive(cls, v: List[int]) -> List[int]:
        bad = [f for f in v if f < 1]
        if bad:
            raise ValueError(f"扫描帧号必须为正整数，非法值：{bad}")
        return v


class BatchResult(BaseModel):
    status: str
    batch_id: str
    roll_code: str
    total_scanned_unique: int
    duplicate_frames: List[int]
    duplicate_count: int
    missing_ranges: List[str]
    out_of_range_frames: List[int]
    out_of_range_count: int
    expected_ranges: List[str]


class RollSummary(BaseModel):
    roll_code: str
    expected_ranges: List[str]
    scanned_frames: List[int]
    total_scanned_unique: int
    duplicate_frames: List[int]
    duplicate_count: int
    missing_ranges: List[str]
    out_of_range_frames: List[int]
    out_of_range_count: int
    batch_count: int


class BatchMeta(BaseModel):
    batch_id: str
    roll_code: str
    range_start: int
    range_end: int
    frame_count: int
    created_at: str


class BatchDetail(BatchMeta):
    frames: List[int]


class Health(BaseModel):
    status: str
    db_path: str
