import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "itms_production.db"


def create_test_violation(
    plate_number: str,
    status: str = "AutoApproved",
    decision_type: str = "Auto",
    confidence_score: float = 99.0,
    review_note: str = "Manual SMS test record",
    intersection_id: int = 1,
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("PRAGMA foreign_keys = ON;")

    c.execute(
        """
        INSERT INTO violation
        (
            plate_number,
            intersection_id,
            timestamp,
            image_path,
            video_path,
            confidence_score,
            decision_type,
            status,
            review_note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plate_number,
            intersection_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            None,
            None,
            confidence_score,
            decision_type,
            status,
            review_note,
        ),
    )

    conn.commit()
    new_id = c.lastrowid
    conn.close()

    print(f"✅ New violation created: V-{new_id}")
    print(f"   plate_number = {plate_number}")
    print(f"   status       = {status}")
    print(f"   decision     = {decision_type}")


if __name__ == "__main__":
    print("Choose test case:")
    print("1. Civilian test (ABC-1234) -> should allow SMS")
    print("2. Exempt police test (ZRP-0001) -> should skip SMS")

    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        create_test_violation(
            plate_number="ABC-1234",
            status="AutoApproved",
            decision_type="Auto",
            confidence_score=99.0,
            review_note="Manual SMS success-path test record",
            intersection_id=1,
        )
    elif choice == "2":
        create_test_violation(
            plate_number="ZRP-0001",
            status="AutoApproved",
            decision_type="Auto",
            confidence_score=99.0,
            review_note="Manual SMS exempt-path test record",
            intersection_id=1,
        )
    else:
        print("❌ Invalid choice. Run again and choose 1 or 2.")