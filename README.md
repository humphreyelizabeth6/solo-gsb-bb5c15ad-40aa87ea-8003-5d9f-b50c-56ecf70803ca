# 胶片档案扫描整理 API

面向胶片档案扫描整理的本地 API 服务。每批提交 **胶卷编号、预期帧号起止范围、实际扫描帧号列表**；
同一胶卷跨批次自动合并帧号，重复帧只计一次并单独列出，并按预期范围返回连续缺帧区间。

- 技术栈：Python 3.12 · FastAPI · SQLite（标准库，零外部数据库依赖）
- 数据库在容器/服务启动时**自动建库建表**，无需手工初始化
- 重复导入相同批次**幂等**：不产生重复帧、不改变任何统计结果

## 一条命令启动

需要 Docker（含 Compose 插件）：

```bash
docker compose up -d --build
```

启动后：

| 用途 | 地址 |
| --- | --- |
| 交互式接口文档（Swagger UI） | http://localhost:8000/docs |
| OpenAPI 描述 | http://localhost:8000/openapi.json |
| 健康检查 | http://localhost:8000/health |

服务监听 **8000 端口**；根路径 `/` 会跳转到 `/docs`。

停止与清理：

```bash
docker compose down          # 停止（数据保留在卷 film-data 中）
docker compose down -v       # 停止并删除数据库卷
```

## API 一览

### 提交扫描批次

```
POST /api/batches
```

请求体：

```json
{
  "roll_code": "R-2026-001",
  "range_start": 1,
  "range_end": 12,
  "frames": [1, 2, 2, 3, 5, 8, 9, 10, 11, 12],
  "batch_id": "optional-批次标识"
}
```

- `batch_id` 可省略：省略时按请求内容生成指纹，**内容相同的再次提交自动判重**。
- 同一 `batch_id` 以不同内容重复提交返回 `409`，且不会改动已有数据。
- 响应 `status`：`created`（首次入库）或 `duplicate`（重复导入，结果不变）。

响应示例（合并了该胶卷全部批次后的汇总）：

```json
{
  "status": "created",
  "batch_id": "optional-批次标识",
  "roll_code": "R-2026-001",
  "total_scanned_unique": 9,
  "duplicate_frames": [],
  "duplicate_count": 0,
  "missing_ranges": ["4", "6-7"],
  "out_of_range_frames": [],
  "out_of_range_count": 0,
  "expected_ranges": ["1-12"]
}
```

字段说明：

- `total_scanned_unique`：该胶卷跨批次合并、去重后的实际扫描帧总数。
- `duplicate_frames`：重复帧（批内重复或被多个批次包含），**只计一次并在此单独列出帧号**。
- `missing_ranges`：按预期范围计算的连续缺帧区间，单帧为 `"4"`，多帧为 `"6-7"`。
- `out_of_range_frames`：扫描到但不在任何批次预期范围内的帧。
- `expected_ranges`：该胶卷全部批次预期范围取并集后的区间。

### 查询

| 方法与路径 | 说明 |
| --- | --- |
| `GET /api/rolls` | 全部胶卷及其汇总 |
| `GET /api/rolls/{roll_code}` | 单个胶卷的合并汇总（不存在返回 404） |
| `GET /api/rolls/{roll_code}/batches` | 某胶卷的批次清单 |
| `GET /api/batches/{batch_id}` | 单个批次的原始提交内容 |
| `GET /health` | 健康检查与数据库路径 |

curl 示例：

```bash
curl -X POST http://localhost:8000/api/batches \
  -H 'Content-Type: application/json' \
  -d '{"roll_code":"R01","range_start":1,"range_end":10,"frames":[1,2,4,5,10]}'

curl http://localhost:8000/api/rolls/R01
# => missing_ranges 为 ["3","6-9"]
```

## 配置（环境变量）

均为可选项，在 `docker-compose.yml` 的 `environment` 中修改：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DB_PATH` | `/data/film.db` | SQLite 数据库文件路径，位于挂载卷内持久化 |
| `HOST` | `0.0.0.0` | 直接运行 `python -m app.main` 时的监听地址 |
| `PORT` | `8000` | 直接运行 `python -m app.main` 时的监听端口 |
| `DB_TIMEOUT` | `30` | SQLite 写锁等待秒数（并发提交时生效） |

修改宿主机映射端口（例如改用 18000）：编辑 `docker-compose.yml` 的
`ports: ["18000:8000"]`，容器内端口仍为 8000。

## 本地开发（不使用 Docker）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 可用 DB_PATH 指定本地数据库文件路径（不传则使用代码默认值 /data/film.db）
DB_PATH=./data/film.db uvicorn app.main:app --reload --port 8000

# 运行测试
DB_PATH=/tmp/film-test/film.db pytest -q
```

## 幂等与合并规则

1. 批次内容指纹对 `{胶卷编号, 预期起止, 去重排序后的帧号}` 取 SHA-256；
   帧号书写顺序、批内重复不影响指纹。
2. 相同 `batch_id` 或相同内容指纹的提交一律视为重复，直接返回当前汇总，不写数据。
3. 同一胶卷的预期范围取所有批次范围的并集（自动合并重叠/相邻区间）。
4. 缺帧区间仅在合并后的预期范围内计算；超出范围的扫描帧列入 `out_of_range_frames`。
5. 所有写操作在 `BEGIN IMMEDIATE` 事务内完成，并以唯一约束兜底，并发提交也不会重复计数。
