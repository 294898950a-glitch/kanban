import sqlite3
conn = sqlite3.connect('data/matetial_monitor.db')
c = conn.cursor()
c.execute('SELECT batch_id FROM kpi_history ORDER BY timestamp DESC LIMIT 1')
batch = c.fetchone()
print('最新batch:', batch)
if batch:
    c.execute('SELECT plan_issue_date FROM issue_audit_snapshots WHERE batch_id=? LIMIT 10', (batch[0],))
    rows = c.fetchall()
    print('plan_issue_date样本:', rows)
    c.execute('SELECT COUNT(*) FROM issue_audit_snapshots WHERE batch_id=? AND plan_issue_date != ""', (batch[0],))
    print('有日期的记录数:', c.fetchone())
conn.close()
