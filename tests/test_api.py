import uuid


def test_single_batch_missing_and_dedup(client):
    resp = client.post(
        "/api/batches",
        json={
            "roll_code": "R001",
            "range_start": 1,
            "range_end": 10,
            "frames": [1, 2, 2, 3, 5, 8, 9, 10],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "created"
    # 批内重复的 2 只计一次
    assert data["total_scanned_unique"] == 7
    assert data["duplicate_frames"] == []  # 仅一个批次，尚无跨批重复
    assert data["missing_ranges"] == ["4", "6-7"]
    assert data["out_of_range_frames"] == []


def test_cross_batch_merge_and_duplicates(client):
    client.post(
        "/api/batches",
        json={
            "roll_code": "R002",
            "range_start": 1,
            "range_end": 10,
            "frames": [1, 2, 3, 5],
            "batch_id": "b1",
        },
    )
    resp = client.post(
        "/api/batches",
        json={
            "roll_code": "R002",
            "range_start": 1,
            "range_end": 12,
            "frames": [3, 5, 7, 8, 12],
            "batch_id": "b2",
        },
    )
    data = resp.json()
    assert data["status"] == "created"
    # 跨批重复帧 3、5 只计一次并单独列出
    assert data["duplicate_frames"] == [3, 5]
    assert data["total_scanned_unique"] == 7
    assert data["missing_ranges"] == ["4", "6", "9-11"]


def test_reimport_same_batch_is_idempotent(client):
    payload = {
        "roll_code": "R003",
        "range_start": 1,
        "range_end": 5,
        "frames": [1, 1, 3],
        "batch_id": "dup-1",
    }
    first = client.post("/api/batches", json=payload).json()
    # 完全重复提交
    second = client.post("/api/batches", json=payload).json()
    # 帧序不同、批内重复写法不同，语义相同且未带 batch_id：自动指纹同样判重
    auto = client.post(
        "/api/batches",
        json={
            "roll_code": "R003",
            "range_start": 1,
            "range_end": 5,
            "frames": [3, 1],
        },
    ).json()

    for later in (second, auto):
        assert later["status"] == "duplicate"
        assert later["total_scanned_unique"] == first["total_scanned_unique"]
        assert later["duplicate_frames"] == first["duplicate_frames"]
        assert later["missing_ranges"] == first["missing_ranges"]

    roll = client.get("/api/rolls/R003").json()
    assert roll["total_scanned_unique"] == 2
    assert roll["batch_count"] == 1
    assert roll["missing_ranges"] == ["2", "4-5"]


def test_same_batch_id_conflicting_content_returns_409(client):
    client.post(
        "/api/batches",
        json={
            "roll_code": "R004",
            "range_start": 1,
            "range_end": 5,
            "frames": [1],
            "batch_id": "x",
        },
    )
    resp = client.post(
        "/api/batches",
        json={
            "roll_code": "R004",
            "range_start": 1,
            "range_end": 5,
            "frames": [2],
            "batch_id": "x",
        },
    )
    assert resp.status_code == 409
    # 冲突提交不改变已有结果
    roll = client.get("/api/rolls/R004").json()
    assert roll["scanned_frames"] == [1]


def test_out_of_range_frames_listed(client):
    resp = client.post(
        "/api/batches",
        json={
            "roll_code": "R005",
            "range_start": 100,
            "range_end": 102,
            "frames": [100, 101, 102, 1, 200],
        },
    )
    data = resp.json()
    assert data["out_of_range_frames"] == [1, 200]
    assert data["missing_ranges"] == []


def test_disjoint_expected_ranges(client):
    client.post(
        "/api/batches",
        json={"roll_code": "R006", "range_start": 1, "range_end": 4, "frames": [1, 4]},
    )
    client.post(
        "/api/batches",
        json={"roll_code": "R006", "range_start": 10, "range_end": 12, "frames": [11]},
    )
    roll = client.get("/api/rolls/R006").json()
    assert roll["expected_ranges"] == ["1-4", "10-12"]
    assert roll["missing_ranges"] == ["2-3", "10", "12"]


def test_rolls_list_and_404(client):
    assert client.get("/api/rolls").json() == []
    assert client.get("/api/rolls/nope").status_code == 404
    assert client.get("/api/batches/nope").status_code == 404

    client.post(
        "/api/batches",
        json={"roll_code": "R007", "range_start": 1, "range_end": 2, "frames": [1]},
    )
    codes = [r["roll_code"] for r in client.get("/api/rolls").json()]
    assert codes == ["R007"]
    metas = client.get("/api/rolls/R007/batches").json()
    assert len(metas) == 1 and metas[0]["frame_count"] == 1


def test_invalid_payload(client):
    # range_end < range_start
    resp = client.post(
        "/api/batches",
        json={"roll_code": "R008", "range_start": 9, "range_end": 3, "frames": []},
    )
    assert resp.status_code == 422
    # 帧号非正整数
    resp = client.post(
        "/api/batches",
        json={"roll_code": "R008", "range_start": 1, "range_end": 3, "frames": [0]},
    )
    assert resp.status_code == 422
