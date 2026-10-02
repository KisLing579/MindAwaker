"""
日志配置
统一的日志格式和级别管理
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(
    log_level: str = None,
    log_dir: str = "app/assets/logs",
    app_name: str = "mindawaker"
):
    """
    配置应用日志

    Args:
        log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR)，默认从环境变量读取
        log_dir: 日志文件目录
        app_name: 应用名称
    """
    # 从环境变量获取日志级别
    level = (log_level or os.getenv("LOG_LEVEL", "INFO")).upper()

    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 日志格式
    log_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 详细格式（包含文件名和行号）
    detailed_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level))

    # 清除已有处理器
    root_logger.handlers = []

    # 1. 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(log_format)
    root_logger.addHandler(console_handler)

    # 2. 文件处理器（按天轮转）
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path / f"{app_name}_{today}.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=30,  # 保留30天
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_format)
    root_logger.addHandler(file_handler)

    # 3. 错误日志单独文件
    error_handler = logging.handlers.RotatingFileHandler(
        filename=log_path / f"{app_name}_error_{today}.log",
        maxBytes=10*1024*1024,
        backupCount=30,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_format)
    root_logger.addHandler(error_handler)

    # 设置第三方库日志级别
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)

    # 记录启动信息
    logger = logging.getLogger(__name__)
    logger.info("="*50)
    logger.info("Mindawaker 日志系统启动")
    logger.info(f"日志级别: {level}")
    logger.info(f"日志目录: {log_path.absolute()}")
    logger.info("="*50)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    获取命名日志器

    Args:
        name: 模块名，通常传 __name__

    Returns:
        logging.Logger: 配置好的日志器
    """
    return logging.getLogger(name)
