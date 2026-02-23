from sqlalchemy import inspect
from src.db.database import engine, Base
import src.db.models  # 必须导入 models 否则 Base 原数据为空

def init_db():
    print("[DB] 检查数据库表结构...")
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    # 获取模型中定义的所有表名
    model_tables = [table.name for table in Base.metadata.sorted_tables]
    
    missing_tables = [t for t in model_tables if t not in existing_tables]
    
    if missing_tables:
        print(f"[DB] 发现缺失的表: {missing_tables}")
        print("[DB] 正在初始化数据库结构...")
        Base.metadata.create_all(bind=engine)
        print("[DB] 数据库表结构创建完成!")
    else:
        print("[DB] 所有表结构已存在，无需重建。")

if __name__ == "__main__":
    init_db()
