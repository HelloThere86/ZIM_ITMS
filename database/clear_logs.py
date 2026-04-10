import sqlite3
DB_PATH = "itms_production.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("DELETE FROM notification_log")
conn.commit()
conn.close()
print("✅ Notification log has been cleared. Ready for fresh test.")