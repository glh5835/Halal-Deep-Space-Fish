import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 容器内由环境变量指向挂载目录；本地裸跑默认 backend/ 下的 mall_sales.db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mall_sales.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()