# tools/

本目录存放项目级运维与验证工具脚本，非业务核心代码。

## 使用前提

```bash
cd /home/chenweijie/projects/matetial_monitor
source venv/bin/activate
# 或
export PYTHONPATH=/home/chenweijie/projects/matetial_monitor
```

---

## migrate_db.py — 数据库模型迁移工具

**用途**：向已存在的 SQLite 数据库加入新字段/新表，不删除任何历史数据。

**何时使用**：修改了 `src/db/models.py`（新增字段或新增表）后，对已有的 `data/matetial_monitor.db` 执行增量迁移。

```bash
python3 tools/migrate_db.py
```

> **注意**：脚本已内置幂等性保护（"column already exists" 时跳过，不报错）。  
> 目前包含的迁移项：
> - `alert_report_snapshots.is_legacy` Integer 默认 0
> - 新建 `data_quality_snapshots` 表

---

## test_consistency.py — 端对端数据一致性验证

**用途**：同时查询后端 API 与 SQLite 直查结果，逐项对比是否一致。

**何时使用**：
- 部署新版本后的冒烟测试
- 怀疑 API 返回值与数据库不符时

**运行（需后端已启动在 8000 端口）**：
```bash
python3 tools/test_consistency.py
```

**离线模式**：若后端未启动，API 相关项自动跳过（⚠️ SKIP），仅验证数据库内容合理性。

**检验项目**：
| 编号 | 检验内容 |
|------|---------|
| 1 | KPI 汇总（alert_group_count / high_risk_count / over_issue_lines / avg_aging_hours）|
| 2 | 退料预警 Top10 条目数、Top1 工单号、Top1 偏差值 |
| 3 | 超发预警 Top5 条目数、Top1 物料编号 |
| 4 | 批次列表条数与最新批次 ID |
| 5 | 数据质量快照合理性（历史遗留比例 < 30%）|
