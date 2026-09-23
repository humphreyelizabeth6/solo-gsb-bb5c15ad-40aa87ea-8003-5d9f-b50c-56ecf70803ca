"""运行期配置，全部可通过环境变量覆盖。"""
from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    def __init__(self) -> None:
        # SQLite 数据库文件路径；启动时若不存在会自动创建并初始化表结构。
        self.db_path: str = os.getenv("DB_PATH", "/data/film.db")
        # HTTP 服务监听参数（仅在直接 `python -m app.main` 启动时生效，
        # 通过 uvicorn / gunicorn 启动时由命令行参数控制）。
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.db_timeout: float = float(os.getenv("DB_TIMEOUT", "30"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
