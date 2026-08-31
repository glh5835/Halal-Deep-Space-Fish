# init_db.py
from backend.database import engine, Base
from backend.models import SaleRecord  # 导入模型，确保表被注册

def init():
    print("正在创建数据库表...")
    Base.metadata.create_all(bind=engine)
    print("数据库表创建成功！")

if __name__ == "__main__":
    init()