import sqlite3
import os

DB_NAME = "itms_production.db"

def create_tables():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Enable Foreign Key support
    c.execute("PRAGMA foreign_keys = ON;")

    # 1. TABLE: Driver
    c.execute('''CREATE TABLE IF NOT EXISTS driver (
        driver_id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        national_id TEXT UNIQUE NOT NULL,
        phone_number TEXT
    )''')

    # 2. TABLE: System_User
    c.execute('''CREATE TABLE IF NOT EXISTS system_user (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        role TEXT CHECK(role IN ('Admin', 'Officer', 'Operator')),
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_active BOOLEAN DEFAULT 1
    )''')

    # 3. TABLE: Intersection
    c.execute('''CREATE TABLE IF NOT EXISTS intersection (
        intersection_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        location TEXT,
        region TEXT
    )''')

    # 4. TABLE: Vehicle (Linked to Driver)
    c.execute('''CREATE TABLE IF NOT EXISTS vehicle (
        plate_number TEXT PRIMARY KEY,
        model TEXT,
        color TEXT,
        owner_id INTEGER,
        is_exempt BOOLEAN DEFAULT 0,
        FOREIGN KEY (owner_id) REFERENCES driver(driver_id)
    )''')

    # 5. TABLE: Traffic_Stats (Linked to Intersection)
    c.execute('''CREATE TABLE IF NOT EXISTS traffic_stats (
        stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        intersection_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        avg_queue_length INTEGER,
        phase_duration INTEGER,
        FOREIGN KEY (intersection_id) REFERENCES intersection(intersection_id)
    )''')

    # 6. TABLE: Violation (The Core Table)
    c.execute('''CREATE TABLE IF NOT EXISTS violation (
        violation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_number TEXT,
        intersection_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        image_path TEXT,
        video_path TEXT,
        confidence_score REAL,
        decision_type TEXT CHECK(decision_type IN ('Auto', 'Flagged', 'LoggedOnly')),
        status TEXT CHECK(status IN ('Pending', 'Approved', 'Rejected', 'AutoApproved', 'Paid')),
        fine_amount REAL,
        reviewer_user_id INTEGER,
        reviewed_at DATETIME,
        review_note TEXT,
        FOREIGN KEY (plate_number) REFERENCES vehicle(plate_number),
        FOREIGN KEY (intersection_id) REFERENCES intersection(intersection_id),
        FOREIGN KEY (reviewer_user_id) REFERENCES system_user(user_id)
    )''')

    # 7. TABLE: System_Config
    c.execute('''CREATE TABLE IF NOT EXISTS system_config (
        config_key TEXT PRIMARY KEY,
        config_value TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_by INTEGER,
        FOREIGN KEY (updated_by) REFERENCES system_user(user_id)
    )''')

    # 8. TABLE: Audit_Log (Security Requirement)
    c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        user_id INTEGER,
        action_type TEXT,
        entity_type TEXT,
        entity_id TEXT,
        old_value JSON,
        new_value JSON,
        note TEXT,
        FOREIGN KEY (user_id) REFERENCES system_user(user_id)
    )''')

    conn.commit()
    conn.close()
    print(f"✅ Production Database '{DB_NAME}' created successfully with ERD structure.")

if __name__ == "__main__":
    create_tables()