"""文件解析与导入流程测试：编码回退、表头映射、脏数据行号与原因、覆盖/追加语义。"""
import pandas as pd
import pytest

from utils_file import decode_csv, detect_mapping, normalize_header


def _csv(rows, enc="utf-8"):
    return ("\n".join(rows)).encode(enc)


def test_decode_utf8_bom():
    assert decode_csv("date,qty".encode("utf-8-sig")) == "date,qty"


def test_decode_gbk():
    assert decode_csv("商品,数量".encode("gbk")) == "商品,数量"


def test_decode_latin1_fallback():
    # 0xFF 在 utf-8/gb18030/gbk/big5 中都不是合法字节，应兜底落到 latin1
    assert decode_csv(b"\xff\xff\xff") == "ÿÿÿ"


def test_normalize_header():
    assert normalize_header("  售价(元) ") == "售价"
    assert normalize_header("商品名称（全称）") == "商品名称"
    assert normalize_header("DATE") == "date"


def test_detect_mapping_chinese_and_normalized():
    df = pd.DataFrame(columns=["  日期 ", "商品名称（全称）", "售价(元)", "cost_price", "数量"])
    m = detect_mapping(df)
    assert m["date"] == "  日期 "
    assert m["product_name"] == "商品名称（全称）"
    assert m["unit_price"] == "售价(元)"
    assert m["cost_price"] == "cost_price"
    assert "category" not in m  # 缺失列不出现


def test_upload_gbk_chinese_header_dirty_rows(client, clean_db):
    rows = [
        "日期,商品名称,品类,售价,成本价,数量",
        "2026-09-01,苹果,生鲜,5.5,3,10",
        "2026-09-01,坏数量,生鲜,5,3,3件",
        "2026-09-01,坏价格,生鲜,abc,3,1",
    ]
    r = client.post("/api/upload",
                    files={"file": ("t.csv", _csv(rows, "gbk"), "text/csv")},
                    data={"mode": "overwrite"})
    d = r.json()
    assert d["total"] == 3 and d["success"] == 1 and d["failed"] == 2
    # 行号从 2 开始（表头算第 1 行），原因可读
    assert d["errors"][0]["row"] == 3 and "数量" in d["errors"][0]["reason"]
    assert d["errors"][1]["row"] == 4 and "售价" in d["errors"][1]["reason"]


def test_upload_overwrite_twice_not_doubled(client, clean_db):
    from database import SessionLocal
    from models import SaleRecord

    rows = [
        "date,product_name,category,unit_price,cost_price,quantity",
        "2026-09-01,apple,fruit,5.5,3,10",
    ]
    files = {"file": ("t.csv", _csv(rows), "text/csv")}
    client.post("/api/upload", files=files, data={"mode": "overwrite"})
    r = client.post("/api/upload", files=files, data={"mode": "overwrite"})
    assert r.json()["success"] == 1
    db = SessionLocal()
    try:
        assert db.query(SaleRecord).count() == 1
    finally:
        db.close()


def test_upload_append_dedup(client, clean_db):
    rows = [
        "date,product_name,category,unit_price,cost_price,quantity",
        "2026-09-01,apple,fruit,5.5,3,10",
        "2026-09-01,apple,fruit,5.5,3,10",  # 文件内重复
    ]
    files = {"file": ("t.csv", _csv(rows), "text/csv")}
    d = client.post("/api/upload", files=files, data={"mode": "append"}).json()
    assert d["success"] == 1 and d["skipped"] == 1
    d2 = client.post("/api/upload", files=files, data={"mode": "append"}).json()
    assert d2["success"] == 0 and d2["skipped"] == 2  # 与库内/文件内重复均计入 skipped


def test_upload_missing_columns_400(client, clean_db):
    rows = ["date,product_name", "2026-09-01,apple"]
    r = client.post("/api/upload", files={"file": ("t.csv", _csv(rows), "text/csv")})
    assert r.status_code == 400
    assert "必需列" in r.json()["detail"]


def test_upload_oversize_400(client, clean_db):
    r = client.post("/api/upload",
                    files={"file": ("big.csv", b"date\n" + b"x" * (51 * 1024 * 1024), "text/csv")})
    assert r.status_code == 400
    assert "上限" in r.json()["detail"]


def test_parse_rows_valid_error_split():
    """三阶段导入的阶段二：有效行与错误行划分正确，脏行不进数据库。"""
    from main import parse_rows

    df = pd.DataFrame({
        "date": ["2026-09-01", "昨天", "2026-09-01"],
        "product_name": ["A", "B", ""],
        "category": ["C", "D", "E"],
        "unit_price": [1.0, 2.0, 3.0],
        "cost_price": [0.5, 1.0, 1.5],
        "quantity": [3, 2, 1],
    })
    valid, errors = parse_rows(df)
    assert len(valid) == 1 and len(errors) == 2
    assert errors[0]["row"] == 3 and "日期" in errors[0]["reason"]  # 昨天解析失败
    assert errors[1]["row"] == 4 and "商品名称" in errors[1]["reason"]  # 名称为空
