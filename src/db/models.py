from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index
from datetime import datetime
from src.db.database import Base

class KPIHistory(Base):
    __tablename__ = "kpi_history"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(50), unique=True, index=True, nullable=False) # 存放执行批次ID，如：20260223_080000
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)      # 数据快照时间戳
    
    # 核心统计指标
    alert_group_count = Column(Integer, default=0)        # 退料预警组数
    high_risk_count = Column(Integer, default=0)          # 高风险组数(偏差>0)
    over_issue_lines = Column(Integer, default=0)         # 超发行数
    avg_aging_hours = Column(Float, default=0.0)          # 平均库龄(小时)

    # Phase 3 KPI 重构：三层分类计数
    confirmed_alert_count   = Column(Integer, default=0)  # 当期退料预警（完工+已匹配+仍有库存）
    unmatched_current_count = Column(Integer, default=0)  # 工单范围外库存（接收≥2026但工单未匹配）
    legacy_count            = Column(Integer, default=0)  # 历史遗留库存（接收<2026或为空）
    confirmed_alert_count_excl = Column(Integer, default=0)  # 剔除通用物料后的退料预警数
    avg_aging_hours_excl = Column(Float, default=0.0)     # 剔除通用物料后的平均库龄

class AlertReportSnapshot(Base):
    __tablename__ = "alert_report_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(50), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    shop_order = Column(String(50), index=True)           # 工单号
    material_code = Column(String(50), index=True)        # 物料编号
    material_desc = Column(Text)                          # 物料描述
    warehouse = Column(String(100), index=True)           # 线边仓
    unit = Column(String(20))                             # 单位
    actual_inventory = Column(Float, default=0.0)         # 实际库存(合计)
    barcode_count = Column(Integer, default=0)            # 条码数
    order_status = Column(String(50))                     # 工单状态
    planned_qty = Column(Float, default=0.0)              # 计划数量
    done_qty = Column(Float, default=0.0)                 # 完工数量
    bom_unit_qty = Column(Float, default=0.0)             # BOM单件用量
    bom_total_req = Column(Float, default=0.0)            # BOM总需求量
    theory_remain = Column(Float, default=0.0)            # 理论余料
    deviation = Column(Float, default=0.0)                # 偏差(实际-理论)
    receive_time = Column(String(50))                     # 接收时间(预留原始字符串)
    last_issue_time = Column(String(50))                  # 最新发料时间(预留原始字符串)
    is_legacy = Column(Integer, default=0)                # 是否为历史遗留数据 (0:否, 1:是)
    barcode_list = Column(Text, default="[]")             # JSON 字符串，存条码列表
    reuse_label = Column(String(20), default="")          # reuse_current / reuse_upcoming / ""

    # 复合索引，加速查询某批次下的特定工单/物料
    __table_args__ = (
        Index('idx_alert_batch_order_mat', 'batch_id', 'shop_order', 'material_code'),
    )

class InventoryStatusSnapshot(Base):
    __tablename__ = "inventory_status_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(50), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    shop_order      = Column(String(50), index=True)
    material_code   = Column(String(50), index=True)
    material_desc   = Column(Text)
    warehouse       = Column(String(100))
    unit            = Column(String(20))
    actual_inventory= Column(Float, default=0.0)
    barcode_count   = Column(Integer, default=0)
    order_status    = Column(String(50))          # 原始工单状态字段值
    wo_status_label = Column(String(20), default="")  # current/upcoming/completed/""
    receive_time    = Column(String(50))
    is_legacy       = Column(Integer, default=0)
    barcode_list    = Column(Text, default="[]")
    reuse_label     = Column(String(20), default="")  # reuse_current/reuse_upcoming/""
    theory_remain   = Column(Float, default=0.0)      # 仅completed行有意义
    deviation       = Column(Float, default=0.0)      # 仅completed行有意义

    __table_args__ = (
        Index('idx_invstatus_batch_order_mat', 'batch_id', 'shop_order', 'material_code'),
    )

class IssueAuditSnapshot(Base):
    __tablename__ = "issue_audit_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(50), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    instruction_doc_id = Column(String(50), index=True)   # 备料单ID
    demand_list_number = Column(String(100), index=True)  # 备料单号
    doc_status = Column(String(50))                       # 备料单状态
    related_wo = Column(String(255), index=True)          # 关联工单
    material_code = Column(String(50), index=True)        # 物料编号
    demand_qty = Column(Float, default=0.0)               # 计划发料量(demandQty)
    actual_qty = Column(Float, default=0.0)               # 实际发料量(actualQty)
    over_issue_qty = Column(Float, default=0.0)           # 超发量
    over_issue_rate = Column(Float, default=0.0)          # 超发率(%)
    is_over_issue = Column(String(50))                    # 是否超发 (超发/正常/少发)
    production_line = Column(String(100), index=True)     # 产线
    warehouse = Column(String(100))                       # 仓库
    bom_demand_qty = Column(Float, default=0.0)           # BOM 标准需求量(sumQty)
    over_vs_bom_qty = Column(Float, default=0.0)          # 超发量(vs BOM)
    over_vs_bom_rate = Column(Float, default=0.0)         # 超发率%(vs BOM)
    plan_issue_date  = Column(String(50), default="")        # 计划发料日期(ppStartTime)
    
    __table_args__ = (
        Index('idx_issue_batch_order_mat', 'batch_id', 'related_wo', 'material_code'),
    )

class DataQualitySnapshot(Base):
    __tablename__ = "data_quality_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(50), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # 线边仓分层
    inventory_total = Column(Integer, default=0)    # 总条目数
    inventory_legacy = Column(Integer, default=0)   # 历史遗留数（接收时间<2026或为空）
    inventory_current = Column(Integer, default=0)  # 当期数（接收时间>=2026）

    # IMES 工单关联率
    orders_total = Column(Integer, default=0)       # IMES 工单总数
    alert_matched = Column(Integer, default=0)      # 当期库存匹配到工单的组合数
    alert_unmatched = Column(Integer, default=0)    # 当期库存未匹配到工单的组合数
    alert_match_rate = Column(Float, default=0.0)   # 匹配率(%)

    # NWMS 关联率
    nwms_lines_total = Column(Integer, default=0)   # NWMS 发料行总数
    nwms_lines_matched = Column(Integer, default=0) # 关联工单在 IMES 中存在的行数
    nwms_match_rate = Column(Float, default=0.0)    # 匹配率(%)

