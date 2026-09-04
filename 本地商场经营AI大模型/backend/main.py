import json
from datetime import date, datetime
from io import BytesIO

import httpx
import pandas as pd
from fastapi import FastAPI, APIRouter, UploadFile, File, Form, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.orm import Session

from database import engine, get_db, Base
from models import SaleRecord, ImportBatch
from schemas import SaleCreate
from crud import (
    create_sale, get_daily_summary, get_category_summary, get_latest_dates,
    get_trend, insert_sales_overwrite, insert_sales_append,
    data_fingerprint, get_advice_row, upsert_advice, clear_advice_cache,
)
from ai_service import generate_advice, OLLAMA_BASE_URL, OLLAMA_MODEL
from utils_file import read_table, detect_mapping, apply_mapping, COLUMN_ALIASES

app = FastAPI(title="商场AI经营分析系统")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 统一 API 前缀，与前端 axios baseURL '/api' 对应
api = APIRouter(prefix="/api")


def _to_float(value, label: str) -> float:
    if pd.isna(value):
        raise ValueError(f"{label}为空")
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        raise ValueError(f"{label}列无法转为数字：'{value}'")


def _to_int(value) -> int:
    if pd.isna(value):
        raise ValueError("数量为空")
    try:
        return int(float(value))
    except (TypeError, ValueError):
        raise ValueError(f"数量列无法转为整数：'{value}'")


def parse_rows(df):
    """阶段二：在 pandas 层逐行校验，脏行不进数据库。

    返回 (valid_rows, errors)；行号从 2 开始（表头算第 1 行）。
    """
    valid, errors = [], []
    for i, (_, row) in enumerate(df.iterrows()):
        row_no = i + 2
        try:
            if pd.isna(row["date"]):
                raise ValueError("日期为空")
            parsed_date = pd.to_datetime(row["date"], errors="coerce")
            if pd.isna(parsed_date):
                raise ValueError(f"日期无法解析：'{row['date']}'")
            name = row["product_name"]
            if pd.isna(name) or not str(name).strip():
                raise ValueError("商品名称为空")
            category = row["category"]
            if pd.isna(category) or not str(category).strip():
                raise ValueError("品类为空")
            valid.append(SaleCreate(
                date=parsed_date.date(),
                product_name=str(name).strip(),
                category=str(category).strip(),
                unit_price=_to_float(row["unit_price"], "售价"),
                cost_price=_to_float(row["cost_price"], "成本价"),
                quantity=_to_int(row["quantity"]),
            ))
        except ValueError as e:
            errors.append({"row": row_no, "reason": str(e)})
        except Exception as e:  # 未知异常同样拦在本阶段，不让脏行进数据库
            errors.append({"row": row_no, "reason": f"行解析失败：{e}"})
    return valid, errors


def _read_upload_df(file: UploadFile):
    """阶段一：读取上传文件（编码回退 + 列名校验）。返回 (df, filename)。"""
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".csv")):
        raise HTTPException(400, "仅支持 xlsx/csv 文件")
    content = file.file.read()
    try:
        df = read_table(content, filename)
    except Exception as e:
        raise HTTPException(400, f"文件解析失败：{e}")
    return df, filename


def _resolve_mapping(df, mapping_json: str | None) -> dict:
    """自动识别列映射；mapping_json 可按 {目标列: 源列名} 覆盖（源列必须真实存在）。"""
    mapping = dict(detect_mapping(df))
    if mapping_json:
        try:
            override = json.loads(mapping_json)
        except json.JSONDecodeError:
            raise HTTPException(400, "mapping 参数不是合法 JSON")
        if not isinstance(override, dict):
            raise HTTPException(400, "mapping 参数必须是 {目标列: 源列名} 形式的对象")
        for tgt, src in override.items():
            if tgt in COLUMN_ALIASES:
                if src not in df.columns:
                    raise HTTPException(400, f"映射的源列 '{src}' 不存在于文件中")
                mapping[tgt] = src
    missing = [col for col in COLUMN_ALIASES if col not in mapping]
    if missing:
        raise HTTPException(400, f"无法识别必需列：{', '.join(missing)}，请参考标准模板")
    return mapping


def _jsonable(v):
    """把 pandas/numpy 值转成 JSON 可序列化类型（sample_rows 用）。"""
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
        return None
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "item"):
        return v.item()
    return v


@api.post("/upload")
async def upload_sales(
    file: UploadFile = File(...),
    mode: str = Form("overwrite"),
    mapping: str = Form(""),
    db: Session = Depends(get_db),
):
    if mode not in ("overwrite", "append"):
        raise HTTPException(400, "mode 仅支持 overwrite/append")
    df, filename = _read_upload_df(file)
    mapping_dict = _resolve_mapping(df, mapping or None)
    df = apply_mapping(df, mapping_dict)
    # 阶段二：校验（脏行不进数据库）
    valid, errors = parse_rows(df)
    file_dates = sorted({s.date for s in valid})
    # 阶段三：批次记录与明细同一事务写入，拿到批次号后一次性 commit
    try:
        batch = ImportBatch(
            filename=filename, mode=mode, row_count=0,
            date_from=file_dates[0] if file_dates else None,
            date_to=file_dates[-1] if file_dates else None,
            imported_at=datetime.now(),
        )
        db.add(batch)
        db.flush()  # 取得 batch.id，明细行带上外键
        skipped = 0
        if mode == "overwrite":
            inserted = insert_sales_overwrite(db, valid, file_dates, batch_id=batch.id)
        else:
            inserted, skipped = insert_sales_append(db, valid, file_dates, batch_id=batch.id)
        batch.row_count = inserted
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"数据库写入失败：{e}")
    if mode == "overwrite":
        clear_advice_cache(db, file_dates)  # 数据变了，受影响日期的建议缓存直接失效
    return {
        "message": f"成功导入 {inserted} 条记录" + (f"，跳过重复 {skipped} 条" if skipped else ""),
        "total": len(df),
        "success": inserted,
        "skipped": skipped,
        "failed": len(df) - len(valid),
        "batch_id": batch.id,
        "mode": mode,
        "covered_dates": [d.isoformat() for d in file_dates],
        "errors": errors[:100],
    }


@api.post("/upload/preview")
async def upload_preview(file: UploadFile = File(...)):
    """只解析不入库：返回识别到的列映射、样例行和预计成功/失败行数。"""
    df, _ = _read_upload_df(file)
    detected = detect_mapping(df)
    missing = [col for col in COLUMN_ALIASES if col not in detected]
    sample_rows, estimated_valid = [], 0
    if not missing:
        sub = apply_mapping(df, detected)
        valid, _errors = parse_rows(sub)
        estimated_valid = len(valid)
        sample_rows = [{k: _jsonable(v) for k, v in row.items()}
                       for _, row in sub.head(5).iterrows()]
    return {
        "detected_mapping": {tgt: detected.get(tgt) for tgt in COLUMN_ALIASES},
        "missing_columns": missing,
        "columns": [str(c) for c in df.columns],
        "sample_rows": sample_rows,
        "estimated_total": len(df),
        "estimated_valid": estimated_valid,
    }


@api.get("/template")
def download_template():
    """标准导入模板：6 列英文表头 + 1 行示例数据。"""
    df = pd.DataFrame([{
        "date": "2026-09-01", "product_name": "示例商品A", "category": "示例品类",
        "unit_price": 10.5, "cost_price": 6.0, "quantity": 3,
    }])
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sales_template.xlsx"'},
    )


@api.get("/batches")
def list_batches(db: Session = Depends(get_db)):
    rows = db.query(ImportBatch).order_by(
        ImportBatch.imported_at.desc(), ImportBatch.id.desc()
    ).limit(20).all()
    return [{
        "id": b.id,
        "filename": b.filename,
        "mode": b.mode,
        "row_count": b.row_count,
        "date_from": b.date_from.isoformat() if b.date_from else None,
        "date_to": b.date_to.isoformat() if b.date_to else None,
        "imported_at": b.imported_at.isoformat(sep=" ", timespec="seconds") if b.imported_at else None,
    } for b in rows]


@api.delete("/batches/{batch_id}")
def delete_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(ImportBatch, batch_id)
    if not batch:
        raise HTTPException(404, "批次不存在")
    rows_query = db.query(SaleRecord).filter(SaleRecord.batch_id == batch_id)
    affected = [r[0] for r in rows_query.with_entities(SaleRecord.date).distinct()]
    deleted = rows_query.delete(synchronize_session=False)
    db.delete(batch)
    db.commit()
    clear_advice_cache(db, affected)
    return {"deleted_rows": deleted, "affected_dates": [d.isoformat() for d in affected]}


@api.get("/summary/{query_date}")
def daily_summary(query_date: date, db: Session = Depends(get_db)):
    summary = get_daily_summary(db, query_date)
    if not summary:
        raise HTTPException(404, "该日期无数据")
    return summary


@api.get("/categories/{query_date}")
def categories(query_date: date, db: Session = Depends(get_db)):
    rows = get_category_summary(db, query_date)
    if not rows:
        raise HTTPException(404, "该日期无数据")
    total = sum(r[1] or 0 for r in rows)
    return [{
        "category": c,
        "sales": round(s or 0, 2),
        "profit": round(p or 0, 2),
        "share": round((s or 0) / total * 100, 1) if total else 0,
    } for c, s, p in sorted(rows, key=lambda r: r[1] or 0, reverse=True)]


@api.get("/trend")
def trend(days: int = 30, db: Session = Depends(get_db)):
    return get_trend(db, max(1, min(days, 365)))


def _build_cat_str(db: Session, query_date: date) -> str:
    cat_data = get_category_summary(db, query_date)
    # get_category_summary 返回 (品类, 销售额, 毛利) 三元组
    return "; ".join([f"{c}: 销售额{sales}, 毛利{profit}" for c, sales, profit in cat_data])


def _generate_and_cache(db: Session, summary: dict, query_date: date):
    """调模型生成建议并按指纹写缓存。返回 (suggestions, warning)。"""
    try:
        suggestions, warning = generate_advice(summary, _build_cat_str(db, query_date))
    except Exception as e:
        suggestions, warning = [], f"AI 服务暂时不可用：{e}"
    if not warning and suggestions:
        fp = data_fingerprint(summary["total_sales"], summary["record_count"], query_date)
        upsert_advice(db, query_date, fp, suggestions, OLLAMA_MODEL)
    return suggestions, warning


def _advice_payload(query_date, suggestions, cached, model, generated_at, warning):
    return {
        "date": query_date,
        "suggestions": suggestions,
        "cached": cached,
        "model": model,
        "generated_at": generated_at.isoformat(sep=" ", timespec="seconds") if generated_at else None,
        "warning": warning,
    }


@api.get("/advice/{query_date}")
def daily_advice(query_date: date, db: Session = Depends(get_db)):
    summary = get_daily_summary(db, query_date)
    if not summary:
        raise HTTPException(404, "无数据")
    fp = data_fingerprint(summary["total_sales"], summary["record_count"], query_date)
    row = get_advice_row(db, query_date)
    if row and row.data_fingerprint == fp:  # 命中缓存：数据没变过，直接复用
        return _advice_payload(query_date, json.loads(row.suggestions or "[]"), True,
                               row.model, row.created_at, None)
    suggestions, warning = _generate_and_cache(db, summary, query_date)
    return _advice_payload(query_date, suggestions, False, OLLAMA_MODEL, datetime.now(), warning)


@api.post("/advice/{query_date}/regenerate")
def regenerate_advice(query_date: date, db: Session = Depends(get_db)):
    summary = get_daily_summary(db, query_date)
    if not summary:
        raise HTTPException(404, "无数据")
    suggestions, warning = _generate_and_cache(db, summary, query_date)
    return _advice_payload(query_date, suggestions, False, OLLAMA_MODEL, datetime.now(), warning)


@api.get("/dates")
def available_dates(db: Session = Depends(get_db)):
    return get_latest_dates(db)


@api.get("/health")
def health(db: Session = Depends(get_db)):
    ollama_error = None
    ollama_ok = False
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        ollama_ok = resp.status_code == 200
        if not ollama_ok:
            ollama_error = f"HTTP {resp.status_code}"
    except Exception as e:
        ollama_error = str(e)
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"ollama_ok": ollama_ok, "model": OLLAMA_MODEL, "db_ok": db_ok, "ollama_error": ollama_error}


app.include_router(api)

Base.metadata.create_all(bind=engine)

# SQLite 不支持 ALTER TABLE ADD COLUMN IF NOT EXISTS，先检查列是否存在再补
# （兼容批次 3 之前创建的旧库）
_inspector = sa_inspect(engine)
if "batch_id" not in [c["name"] for c in _inspector.get_columns("sales")]:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE sales ADD COLUMN batch_id INTEGER"))
        conn.execute(text("CREATE INDEX ix_sales_batch_id ON sales (batch_id)"))
