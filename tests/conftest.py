import os
import tempfile
import uuid

import pytest

# 必须在导入 app 之前指定独立的临时数据库
_tmp_dir = tempfile.mkdtemp(prefix="film-test-")
os.environ["DB_PATH"] = os.path.join(_tmp_dir, "test.db")

from app.config import get_settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    # 每个用例使用全新的数据库文件
    db_file = os.path.join(_tmp_dir, f"case-{uuid.uuid4().hex}.db")
    get_settings().db_path = db_file
    init_db()
    with TestClient(app) as c:
        yield c
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(db_file + suffix)
        except OSError:
            pass
