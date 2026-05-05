# api/migrations/create_users_table.py
"""
Run once to add authentication users to the existing ITMS SQLite database.

Usage from project root:
  python -m api.migrations.create_users_table

Optional:
  set DB_PATH=database/itms_production.db
"""

import os
import sqlite3
from pathlib import Path

from passlib.context import CryptContext

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DB_PATH = os.environ.get(
    "DB_PATH",
    str(PROJECT_ROOT / "database" / "itms_production.db"),
)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def run() -> None:
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("PRAGMA foreign_keys = ON;")

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name     TEXT    NOT NULL,
            badge_number  TEXT    UNIQUE,
            email         TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            role          TEXT    NOT NULL CHECK(role IN ('admin','supervisor','officer')),
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            last_login    TEXT
        )
        """
    )

    c.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_email
        ON users(email)
        """
    )

    c.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_role
        ON users(role)
        """
    )

    default_email = "admin@itms.zrp.gov.zw"
    default_password = "Admin@ITMS2024"
    default_hash = pwd_ctx.hash(default_password)

    c.execute(
        """
        INSERT OR IGNORE INTO users (
            full_name,
            email,
            password_hash,
            role,
            badge_number
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "System Administrator",
            default_email,
            default_hash,
            "admin",
            "ADMIN-001",
        ),
    )

    conn.commit()
    conn.close()

    print("Users table ready.")
    print(f"Database          : {db_path}")
    print(f"Default admin     : {default_email}")
    print(f"Default password  : {default_password}")
    print("Change this password after first login.")


if __name__ == "__main__":
    run()
