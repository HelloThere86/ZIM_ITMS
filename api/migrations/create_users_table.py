"""
Run once to add authentication users to the existing ITMS SQLite database.

Usage from project root:
  python -m api.migrations.create_users_table
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

DEFAULT_ADMIN_EMAIL = "admin@itms.zrp.gov.zw"
DEFAULT_ADMIN_PASSWORD = "Admin@ITMS2024"

LEGACY_ROLE_MAP = {
    "admin": "Admin",
    "supervisor": "Operator",
    "officer": "Officer",
}

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def sync_user_to_legacy(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    conn.execute(
        """
        INSERT INTO system_user (
            user_id,
            full_name,
            role,
            username,
            password_hash,
            is_active
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            full_name = excluded.full_name,
            role = excluded.role,
            username = excluded.username,
            password_hash = excluded.password_hash,
            is_active = excluded.is_active
        """,
        (
            row["user_id"],
            row["full_name"],
            LEGACY_ROLE_MAP[row["role"]],
            row["email"],
            row["password_hash"],
            int(row["is_active"]),
        ),
    )


def ensure_default_admin(conn: sqlite3.Connection) -> sqlite3.Row:
    existing = conn.execute(
        "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
        (DEFAULT_ADMIN_EMAIL,),
    ).fetchone()
    if existing:
        return existing

    legacy_admin = conn.execute(
        """
        SELECT user_id, full_name
        FROM system_user
        WHERE role = 'Admin'
        ORDER BY user_id ASC
        LIMIT 1
        """
    ).fetchone()

    desired_user_id = None
    full_name = "System Administrator"
    if legacy_admin:
        desired_user_id = legacy_admin["user_id"]
        full_name = legacy_admin["full_name"] or full_name

    password_hash = pwd_ctx.hash(DEFAULT_ADMIN_PASSWORD)

    if desired_user_id is not None:
        occupied = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (desired_user_id,),
        ).fetchone()
        if not occupied:
            conn.execute(
                """
                INSERT INTO users (
                    user_id,
                    full_name,
                    email,
                    password_hash,
                    role,
                    badge_number
                )
                VALUES (?, ?, ?, ?, 'admin', ?)
                """,
                (
                    desired_user_id,
                    full_name,
                    DEFAULT_ADMIN_EMAIL,
                    password_hash,
                    "ADMIN-001",
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO users (
                    full_name,
                    email,
                    password_hash,
                    role,
                    badge_number
                )
                VALUES (?, ?, ?, 'admin', ?)
                """,
                (
                    full_name,
                    DEFAULT_ADMIN_EMAIL,
                    password_hash,
                    "ADMIN-001",
                ),
            )
    else:
        conn.execute(
            """
            INSERT INTO users (
                full_name,
                email,
                password_hash,
                role,
                badge_number
            )
            VALUES (?, ?, ?, 'admin', ?)
            """,
            (
                full_name,
                DEFAULT_ADMIN_EMAIL,
                password_hash,
                "ADMIN-001",
            ),
        )

    return conn.execute(
        "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
        (DEFAULT_ADMIN_EMAIL,),
    ).fetchone()


def run() -> None:
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.execute(
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

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_email
        ON users(email)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_role
        ON users(role)
        """
    )

    admin_row = ensure_default_admin(conn)
    admin_user_id = admin_row["user_id"]

    for row in conn.execute("SELECT * FROM users ORDER BY user_id ASC").fetchall():
        sync_user_to_legacy(conn, row)

    conn.commit()
    conn.close()

    print("Users table ready.")
    print(f"Database          : {db_path}")
    print(f"Default admin     : {DEFAULT_ADMIN_EMAIL}")
    print(f"Default password  : {DEFAULT_ADMIN_PASSWORD}")
    print(f"Default admin id  : {admin_user_id}")
    print("Change this password after first login.")


if __name__ == "__main__":
    run()
