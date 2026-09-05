import os
import sys
import tempfile

# 必须在导入任何 backend 模块之前设置：测试用独立临时库，绝不写 backend/mall_sales.db
_TMP_DIR = tempfile.mkdtemp(prefix="mall_tests_")
os.environ["DATABASE_URL"] = "sqlite:///" + _TMP_DIR.replace("\\", "/") + "/test.db"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import pytest


@pytest.fixture()
def clean_db():
    """每个测试独享干净数据（三张表全清）。"""
    from database import Base, SessionLocal, engine
    from models import SaleRecord, AiAdvice, ImportBatch  # noqa: F401  确保表已注册

    Base.metadata.create_all(bind=engine)  # 纯单元测试路径不走 main，这里兜底建表
    db = SessionLocal()
    for model in (SaleRecord, AiAdvice, ImportBatch):
        db.query(model).delete(synchronize_session=False)
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    import main

    return TestClient(main.app)
