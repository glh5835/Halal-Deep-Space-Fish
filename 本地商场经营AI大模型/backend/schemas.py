from pydantic import BaseModel
from datetime import date

class SaleCreate(BaseModel):
    date: date
    product_name: str
    category: str
    unit_price: float
    cost_price: float
    quantity: int

class SaleOut(SaleCreate):
    id: int
    total_sales: float
    profit: float
    class Config:
        from_attributes = True

class DailySummary(BaseModel):
    date: date
    total_sales: float
    total_cost: float
    total_profit: float
    margin: float
    record_count: int