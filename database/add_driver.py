import sqlite3
from pathlib import Path

# Update these before running
FULL_NAME = "Ethan Murire"
NATIONAL_ID = "123456789qwertt"
PHONE_NUMBER = "263784283886"

# This script is inside: D:\ZIM_ITMS\database\
DB_PATH = Path(__file__).resolve().parent / "itms_production.db"


def validate_inputs(full_name: str, national_id: str, phone_number: str) -> None:
    if not full_name.strip():
        raise ValueError("FULL_NAME cannot be empty.")
    if not national_id.strip():
        raise ValueError("NATIONAL_ID cannot be empty.")
    if not phone_number.strip():
        raise ValueError("PHONE_NUMBER cannot be empty.")


def add_driver(full_name: str, national_id: str, phone_number: str) -> None:
    validate_inputs(full_name, national_id, phone_number)

    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys = ON;")

        c.execute(
            """
            SELECT driver_id, full_name, national_id, phone_number
            FROM driver
            WHERE national_id = ?
            """,
            (national_id,),
        )
        existing = c.fetchone()

        if existing:
            print("A driver with that national ID already exists:")
            print(dict(existing))
            return

        c.execute(
            """
            INSERT INTO driver (full_name, national_id, phone_number)
            VALUES (?, ?, ?)
            """,
            (full_name.strip(), national_id.strip(), phone_number.strip()),
        )
        conn.commit()

        new_driver_id = c.lastrowid
        print("Driver added successfully.")
        print(f"driver_id: {new_driver_id}")
        print(f"full_name: {full_name}")
        print(f"national_id: {national_id}")
        print(f"phone_number: {phone_number}")

    except sqlite3.IntegrityError as e:
        conn.rollback()
        print(f"Database integrity error: {e}")
    except Exception as e:
        conn.rollback()
        print(f"Failed to add driver: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    add_driver(
        full_name=FULL_NAME,
        national_id=NATIONAL_ID,
        phone_number=PHONE_NUMBER,
    )