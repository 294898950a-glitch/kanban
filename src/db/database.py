import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 确保在 WSL 中路径拼接无误
BASE_DIR = Path(__file__).parent.parent.parent
DB_DIR = BASE_DIR / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "matetial_monitor.db"


# 创建数据库引擎
# check_same_thread=False 允许在 FastAPI 等多线程环境中共用连接
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,  # 打印底层 SQL 语句供调试时可设为 True
    connect_args={"check_same_thread": False},
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 定义所有数据模型的基类
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
