from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text
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
    batch_id = Column(Integer, index=True)   # 所属导入批次，撤销批次时按此删除


class AiAdvice(Base):
    """AI 运营建议缓存：同一天数据（指纹一致）直接复用，避免重复推理。"""
    __tablename__ = "ai_advice"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True)   # 建议对应的数据日期
    data_fingerprint = Column(String(64))          # md5(总销售额|记录数|日期)，数据变化自动失效
    suggestions = Column(Text)                     # JSON 数组文本
    model = Column(String(64))                     # 生成时使用的模型
    created_at = Column(DateTime)


class ImportBatch(Base):
    """导入批次：支持查看最近导入与按批次撤销。"""
    __tablename__ = "import_batch"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255))
    mode = Column(String(16))                      # overwrite | append
    row_count = Column(Integer, default=0)
    date_from = Column(Date)
    date_to = Column(Date)
    imported_at = Column(DateTime)
