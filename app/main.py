"""FastAPI 入口：路由与启动初始化。"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from . import services
from .config import get_settings
from .database import get_conn, init_db
from .schemas import BatchCreate, BatchDetail, BatchMeta, BatchResult, Health, RollSummary

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 容器启动即完成依赖数据落库：建目录 + 建表
    init_db()
    yield


app = FastAPI(
    title="胶片档案扫描整理 API",
    description="按胶卷合并跨批次扫描帧号，去重并输出缺帧区间。",
    version="1.0.0",
    lifespan=lifespan,
)


def conn_dep():
    with get_conn() as conn:
        yield conn


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=Health, tags=["系统"])
def health() -> Health:
    return Health(status="ok", db_path=settings.db_path)


@app.post("/api/batches", response_model=BatchResult, tags=["批次"], status_code=200)
def submit_batch_api(
    body: BatchCreate, conn=Depends(conn_dep)
) -> Dict[str, Any]:
    """提交一个扫描批次。重复提交（相同 batch_id 或相同内容）幂等，不改变结果。"""
    return services.submit_batch(conn, body.model_dump())


@app.get("/api/batches/{batch_id}", response_model=BatchDetail, tags=["批次"])
def get_batch_api(batch_id: str, conn=Depends(conn_dep)) -> BatchDetail:
    row = conn.execute(
        "SELECT batch_id, roll_code, range_start, range_end, frames_json, created_at "
        "FROM batches WHERE batch_id = ?",
        (batch_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"批次不存在：{batch_id}")
    return BatchDetail(
        batch_id=row["batch_id"],
        roll_code=row["roll_code"],
        range_start=row["range_start"],
        range_end=row["range_end"],
        frame_count=len(json.loads(row["frames_json"])),
        created_at=row["created_at"],
        frames=json.loads(row["frames_json"]),
    )


@app.get("/api/rolls", response_model=List[RollSummary], tags=["胶卷"])
def list_rolls_api(conn=Depends(conn_dep)) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT roll_code FROM rolls ORDER BY roll_code").fetchall()
    summaries = []
    for row in rows:
        summaries.append(services.build_roll_summary(conn, row["roll_code"]))
    return summaries


@app.get("/api/rolls/{roll_code}", response_model=RollSummary, tags=["胶卷"])
def get_roll_api(roll_code: str, conn=Depends(conn_dep)) -> Dict[str, Any]:
    summary = services.build_roll_summary(conn, roll_code)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"胶卷不存在：{roll_code}")
    return summary


@app.get("/api/rolls/{roll_code}/batches", response_model=List[BatchMeta], tags=["胶卷"])
def list_roll_batches_api(roll_code: str, conn=Depends(conn_dep)) -> List[BatchMeta]:
    if conn.execute("SELECT 1 FROM rolls WHERE roll_code = ?", (roll_code,)).fetchone() is None:
        raise HTTPException(status_code=404, detail=f"胶卷不存在：{roll_code}")
    rows = conn.execute(
        "SELECT batch_id, roll_code, range_start, range_end, frames_json, created_at "
        "FROM batches WHERE roll_code = ? ORDER BY created_at, rowid",
        (roll_code,),
    ).fetchall()
    return [
        BatchMeta(
            batch_id=r["batch_id"],
            roll_code=r["roll_code"],
            range_start=r["range_start"],
            range_end=r["range_end"],
            frame_count=len(json.loads(r["frames_json"])),
            created_at=r["created_at"],
        )
        for r in rows
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port)
