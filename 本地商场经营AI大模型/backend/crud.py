import hashlib
import json
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import SaleRecord, AiAdvice


def _to_record(sale_data, batch_id=None) -> SaleRecord:
    total = round(sale_data.unit_price * sale_data.quantity, 2)
    profit = round((sale_data.unit_price - sale_data.cost_price) * sale_data.quantity, 2)
    return SaleRecord(
        **sale_data.model_dump(),
        total_sales=total,
        profit=profit,
        batch_id=batch_id,
    )

def create_sale(db: Session, sale_data):
    db_sale = _to_record(sale_data)
    db.add(db_sale)
    db.commit()
    db.refresh(db_sale)
    return db_sale

def insert_sales_overwrite(db: Session, sales: list, covered_dates: list, batch_id=None) -> int:
    """覆盖式写入：先删 covered_dates 的旧数据，再批量插入。

    不提交，由调用方把批次记录和明细放在同一事务里统一 commit；
    脏行应在调用前的校验阶段被拦下，这里抛出的只可能是数据库级异常。
    """
    if covered_dates:
        db.query(SaleRecord).filter(SaleRecord.date.in_(covered_dates)) \
            .delete(synchronize_session=False)
    db.add_all(_to_record(s, batch_id) for s in sales)
    return len(sales)

def insert_sales_append(db: Session, sales: list, file_dates: list, batch_id=None):
    """追加去重：按（日期, 商品名, 单价）判重，库内已有或文件内重复的行跳过。

    返回 (插入数, 跳过数)；不提交，由调用方统一 commit。
    """
    existing = set(
        db.query(SaleRecord.date, SaleRecord.product_name, SaleRecord.unit_price)
        .filter(SaleRecord.date.in_(file_dates)).all()
    )
    to_insert, seen, skipped = [], set(), 0
    for s in sales:
        key = (s.date, s.product_name, s.unit_price)
        if key in existing or key in seen:
            skipped += 1
            continue
        seen.add(key)
        to_insert.append(s)
    db.add_all(_to_record(s, batch_id) for s in to_insert)
    return len(to_insert), skipped

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

def get_trend(db: Session, days: int):
    """近 N 天趋势：终点取库内最大日期，缺失日期补 0，按日期升序。"""
    end = db.query(func.max(SaleRecord.date)).scalar()
    if end is None:
        return []
    start = end - timedelta(days=days - 1)
    rows = db.query(
        SaleRecord.date,
        func.sum(SaleRecord.total_sales),
        func.sum(SaleRecord.cost_price * SaleRecord.quantity),
    ).filter(SaleRecord.date >= start, SaleRecord.date <= end) \
     .group_by(SaleRecord.date).all()
    by_date = {r[0]: (r[1] or 0.0, r[2] or 0.0) for r in rows}
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        sales, cost = by_date.get(d, (0.0, 0.0))
        sales = round(sales, 2)
        profit = round(sales - cost, 2)
        margin = round(profit / sales * 100, 2) if sales else 0
        out.append({"date": d.isoformat(), "total_sales": sales,
                    "total_profit": profit, "margin": margin})
    return out

def data_fingerprint(total_sales, record_count, query_date) -> str:
    return hashlib.md5(f"{total_sales}|{record_count}|{query_date}".encode()).hexdigest()

def get_advice_row(db: Session, query_date: date):
    return db.query(AiAdvice).filter(AiAdvice.date == query_date).first()

def upsert_advice(db: Session, query_date: date, fingerprint: str, suggestions: list, model: str):
    row = get_advice_row(db, query_date)
    payload = json.dumps(suggestions, ensure_ascii=False)
    if row is None:
        row = AiAdvice(date=query_date, data_fingerprint=fingerprint, suggestions=payload,
                       model=model, created_at=datetime.now())
        db.add(row)
    else:
        row.data_fingerprint = fingerprint
        row.suggestions = payload
        row.model = model
        row.created_at = datetime.now()
    db.commit()
    return row

def clear_advice_cache(db: Session, dates):
    """覆盖导入或撤销批次后，受影响日期的建议直接清掉，下次访问重新生成。"""
    if dates:
        db.query(AiAdvice).filter(AiAdvice.date.in_(dates)).delete(synchronize_session=False)
        db.commit()
