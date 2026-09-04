from sqlalchemy.orm import Session
from sqlalchemy import func
from models import SaleRecord
from datetime import date
from typing import List

def _to_record(sale_data) -> SaleRecord:
    total = round(sale_data.unit_price * sale_data.quantity, 2)
    profit = round((sale_data.unit_price - sale_data.cost_price) * sale_data.quantity, 2)
    return SaleRecord(
        **sale_data.model_dump(),
        total_sales=total,
        profit=profit
    )

def create_sale(db: Session, sale_data):
    db_sale = _to_record(sale_data)
    db.add(db_sale)
    db.commit()
    db.refresh(db_sale)
    return db_sale

def insert_sales_overwrite(db: Session, sales: list, covered_dates: list) -> int:
    """覆盖式批量写入：先删 covered_dates 的旧数据，再一次 commit。

    脏行应在调用前的校验阶段被拦下；这里抛出的只可能是数据库级异常，
    由调用方负责 rollback。
    """
    if covered_dates:
        db.query(SaleRecord).filter(SaleRecord.date.in_(covered_dates)) \
            .delete(synchronize_session=False)
    db.add_all(_to_record(s) for s in sales)
    db.commit()
    return len(sales)

def get_daily_summary(db: Session, query_date: date):
    row = db.query(
        func.sum(SaleRecord.total_sales),
        func.sum(SaleRecord.cost_price * SaleRecord.quantity),
        func.count(SaleRecord.id)
    ).filter(SaleRecord.date == query_date).first()
    if not row or row[0] is None:
        return None
    total_sales = round(row[0], 2)
    total_cost = round(row[1], 2) if row[1] else 0
    profit = round(total_sales - total_cost, 2)
    margin = round((profit / total_sales * 100), 2) if total_sales else 0
    return {
        "date": query_date,
        "total_sales": total_sales,
        "total_cost": total_cost,
        "total_profit": profit,
        "margin": margin,
        "record_count": row[2]
    }

def get_category_summary(db: Session, query_date: date):
    return db.query(
        SaleRecord.category,
        func.sum(SaleRecord.total_sales),
        func.sum(SaleRecord.profit)
    ).filter(SaleRecord.date == query_date).group_by(SaleRecord.category).all()

def get_latest_dates(db: Session, limit=30):
    dates = db.query(SaleRecord.date).distinct().order_by(SaleRecord.date.desc()).limit(limit).all()
    return [d[0] for d in dates]