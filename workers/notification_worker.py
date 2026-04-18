import sqlite3
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

DB_PATH = PROJECT_ROOT / "database" / "itms_production.db"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from api.sms_service import process_sms_for_violation

POLL_SECONDS = 5
BATCH_SIZE = 10


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def find_sms_candidates(conn):
    rows = conn.execute(
        """
        SELECT v.violation_id, v.status, v.plate_number
        FROM violation v
        WHERE v.status IN ('Approved', 'AutoApproved')
        AND NOT EXISTS (
            SELECT 1
            FROM notification_log n
            WHERE n.violation_id = v.violation_id
              AND n.channel = 'SMS'
        )
        ORDER BY v.violation_id ASC
        LIMIT ?
        """,
        (BATCH_SIZE,),
    ).fetchall()

    return rows


def main():
    print("📱 Starting notification worker...")

    while True:
        conn = get_db()

        try:
            rows = find_sms_candidates(conn)

            if not rows:
                conn.close()
                time.sleep(POLL_SECONDS)
                continue

            for row in rows:
                violation_id = row["violation_id"]

                try:
                    result = process_sms_for_violation(
                        conn=conn,
                        violation_id=violation_id,
                        user_id=None,
                        note="Async SMS worker after approval",
                    )

                    conn.commit()

                    print(
                        f"📱 SMS worker V-{violation_id}: "
                        f"{result.get('status')} -> {result.get('recipientPhone')}"
                    )

                except Exception as e:
                    conn.rollback()
                    print(f"❌ SMS worker failed on V-{violation_id}: {e}")

        finally:
            conn.close()

        time.sleep(1)


if __name__ == "__main__":
    main()