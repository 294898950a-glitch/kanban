import os
import sys

# 把当前所处路径直接加入环境变量从而可以正确导入 src 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.db.database import engine, Base
from src.db import models

try:
    Base.metadata.create_all(bind=engine)
    print("OK")
except Exception as e:
    print(f"Error: {e}")
