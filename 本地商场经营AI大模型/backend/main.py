from fastapi import FastAPI, APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import pandas as pd
from datetime import date
from io import BytesIO

from database import engine, get_db, Base
from models import SaleRecord
from schemas import SaleCreate, SaleOut, DailySummary
from crud import create_sale, get_daily_summary, get_category_summary, get_latest_dates
from ai_service import generate_advice

app = FastAPI(title="商场AI经营分析系统")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 统一 API 前缀，与前端 axios baseURL '/api' 对应
api = APIRouter(prefix="/api")

@api.post("/upload")
async def upload_sales(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(('.xlsx', '.csv')):
        raise HTTPException(400, "仅支持 xlsx/csv 文件")
    content = await file.read()
    if file.filename.endswith('.csv'):
        df = pd.read_csv(BytesIO(content))
    else:
        df = pd.read_excel(BytesIO(content))
    # 期望列：date, product_name, category, unit_price, cost_price, quantity
    count = 0
    for _, row in df.iterrows():
        try:
            sale = SaleCreate(
                date=pd.to_datetime(row['date']).date(),
                product_name=str(row['product_name']),
                category=str(row['category']),
                unit_price=float(row['unit_price']),
                cost_price=float(row['cost_price']),
                quantity=int(row['quantity'])
            )
            create_sale(db, sale)
            count += 1
        except Exception as e:
            continue
    return {"message": f"成功导入 {count} 条记录"}

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
    cat_str = "; ".join([f"{c}: 销售额{r[1]}, 毛利{r[2]}" for c, r in cat_data])
    advice = generate_advice(summary, cat_str)
    return {"date": query_date, "suggestions": advice}

@api.get("/dates")
def available_dates(db: Session = Depends(get_db)):
    return get_latest_dates(db)

app.include_router(api)

Base.metadata.create_all(bind=engine)