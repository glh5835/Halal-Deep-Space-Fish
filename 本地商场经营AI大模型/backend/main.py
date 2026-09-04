from fastapi import FastAPI, APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
import httpx
import pandas as pd
from datetime import date

from database import engine, get_db, Base
from models import SaleRecord
from schemas import SaleCreate, SaleOut, DailySummary
from crud import create_sale, get_daily_summary, get_category_summary, get_latest_dates, insert_sales_overwrite
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


@api.post("/upload")
async def upload_sales(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".csv")):
        raise HTTPException(400, "仅支持 xlsx/csv 文件")
    content = await file.read()
    # 阶段一：读取（编码回退 + 列名映射）
    try:
        df = read_table(content, filename)
    except Exception as e:
        raise HTTPException(400, f"文件解析失败：{e}")
    mapping = detect_mapping(df)
    missing = [col for col in COLUMN_ALIASES if col not in mapping]
    if missing:
        raise HTTPException(400, f"无法识别必需列：{', '.join(missing)}，请参考标准模板")
    df = apply_mapping(df, mapping)
    # 阶段二：校验（脏行不进数据库）；阶段三：覆盖式批量写入，一次提交
    valid, errors = parse_rows(df)
    covered_dates = sorted({s.date for s in valid})
    try:
        inserted = insert_sales_overwrite(db, valid, covered_dates)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"数据库写入失败：{e}")
    return {
        "total": len(df),
        "success": inserted,
        "failed": len(df) - len(valid),
        "batch_id": None,  # 批次表在后续版本引入后填真实值
        "mode": "overwrite",
        "covered_dates": [d.isoformat() for d in covered_dates],
        "errors": errors[:100],
    }

@api.get("/summary/{query_date}")
def daily_summary(query_date: date, db: Session = Depends(get_db)):
    summary = get_daily_summary(db, query_date)
    if not summary:
        raise HTTPException(404, "该日期无数据")
    return summary

@api.get("/advice/{query_date}")
def daily_advice(query_date: date, db: Session = Depends(get_db)):
    summary = get_daily_summary(db, query_date)
    if not summary:
        raise HTTPException(404, "无数据")
    cat_data = get_category_summary(db, query_date)
    # get_category_summary 返回 (品类, 销售额, 毛利) 三元组，必须按三个解包
    cat_str = "; ".join([f"{c}: 销售额{sales}, 毛利{profit}" for c, sales, profit in cat_data])
    try:
        suggestions, warning = generate_advice(summary, cat_str)
    except Exception as e:
        suggestions, warning = [], f"AI 服务暂时不可用：{e}"
    return {"date": query_date, "suggestions": suggestions, "warning": warning}

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
