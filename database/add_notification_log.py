from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).resolve().parent / "itms_production.db"

def add_notification_log_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("PRAGMA foreign_keys = ON;")

    c.execute("""
        CREATE TABLE IF NOT EXISTS notification_log (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            violation_id INTEGER NOT NULL,
            channel TEXT NOT NULL CHECK(channel IN ('SMS')),
            recipient_phone TEXT,
            message_text TEXT,
            status TEXT NOT NULL CHECK(status IN ('Queued', 'Sent', 'Failed', 'Skipped')),
            provider TEXT,
            provider_message_id TEXT,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            sent_at DATETIME,
            FOREIGN KEY (violation_id) REFERENCES violation(violation_id)
        )
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_notification_log_violation_id
        ON notification_log(violation_id)
    """)

    conn.commit()
    conn.close()
    print("✅ notification_log table created successfully.")

if __name__ == "__main__":
    add_notification_log_table()