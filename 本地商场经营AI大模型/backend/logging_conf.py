"""基础日志：标准库实现，写入 backend/logs/ 按天轮转，保留 30 天。"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("mall")
    if logger.handlers:  # 防止重复初始化
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    fh = TimedRotatingFileHandler(
        os.path.join(log_dir, "app.log"), when="midnight", backupCount=30, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    logger.propagate = False
    return logger


logger = setup_logging()
