from sqlalchemy import Column, Integer, String, Float, Date
from database import Base

class SaleRecord(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)          # 销售日期
    product_name = Column(String)            # 商品名称
    category = Column(String)                # 品类
    unit_price = Column(Float)               # 售价
    cost_price = Column(Float)               # 成本
    quantity = Column(Integer)               # 数量
    total_sales = Column(Float)              # 销售额(自动计算)
    profit = Column(Float)                   # 毛利(自动计算)