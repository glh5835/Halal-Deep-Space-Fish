"""汇总计算核心逻辑测试：正常值、除零边界、单条记录、空日期。"""
from datetime import date

from crud import create_sale, get_daily_summary
from schemas import SaleCreate

D = date(2026, 9, 1)


def _mk(unit, cost, qty):
    return SaleCreate(date=D, product_name="商品", category="品类",
                      unit_price=unit, cost_price=cost, quantity=qty)


def test_normal_summary(clean_db):
    create_sale(clean_db, _mk(5.5, 3.0, 10))
    create_sale(clean_db, _mk(29.9, 18.0, 3))
    s = get_daily_summary(clean_db, D)
    assert s["total_sales"] == 144.7
    assert s["total_cost"] == 84.0
    assert s["total_profit"] == 60.7
    assert s["margin"] == 41.95
    assert s["record_count"] == 2


def test_zero_sales_margin(clean_db):
    """除零保护：售价为 0 时毛利率应为 0 而不是抛异常。"""
    create_sale(clean_db, _mk(0, 0, 5))
    s = get_daily_summary(clean_db, D)
    assert s["total_sales"] == 0
    assert s["margin"] == 0


def test_single_record(clean_db):
    create_sale(clean_db, _mk(10, 6, 1))
    s = get_daily_summary(clean_db, D)
    assert s["date"] == D
    assert s["total_sales"] == 10.0
    assert s["total_profit"] == 4.0
    assert s["margin"] == 40.0
    assert s["record_count"] == 1


def test_empty_date_returns_none(clean_db):
    assert get_daily_summary(clean_db, date(2001, 1, 1)) is None
