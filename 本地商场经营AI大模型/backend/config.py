"""集中配置：全部读环境变量，带合理默认值（不设任何环境变量也能直接跑）。"""
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mall_sales.db")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
# 逗号分隔的允许来源；生产走 Nginx 同源反代，默认只放行本地开发地址
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
