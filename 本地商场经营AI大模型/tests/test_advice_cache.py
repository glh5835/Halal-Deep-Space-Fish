"""AI 建议缓存测试：指纹稳定性/敏感性、upsert、清除。"""
import json
from datetime import date

from crud import data_fingerprint, upsert_advice, get_advice_row, clear_advice_cache

D = date(2026, 9, 1)


def test_fingerprint_stable_and_sensitive():
    f1 = data_fingerprint(100.0, 5, D)
    assert f1 == data_fingerprint(100.0, 5, D)      # 同数据同指纹
    assert f1 != data_fingerprint(101.0, 5, D)      # 销售额变 → 失效
    assert f1 != data_fingerprint(100.0, 6, D)      # 记录数变 → 失效
    assert f1 != data_fingerprint(100.0, 5, date(2026, 9, 2))  # 日期变 → 失效


def test_upsert_updates_not_duplicates(clean_db):
    upsert_advice(clean_db, D, "fp1", [{"title": "a"}], "m")
    upsert_advice(clean_db, D, "fp2", [{"title": "b"}], "m")
    rows = get_advice_row(clean_db, D)
    assert rows.data_fingerprint == "fp2"
    assert json.loads(rows.suggestions)[0]["title"] == "b"
    from models import AiAdvice
    assert clean_db.query(AiAdvice).count() == 1  # 同日只有一条


def test_clear_cache(clean_db):
    upsert_advice(clean_db, D, "fp1", [{"title": "a"}], "m")
    clear_advice_cache(clean_db, [D])
    assert get_advice_row(clean_db, D) is None
