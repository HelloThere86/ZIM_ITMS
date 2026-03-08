import sqlite3
import os
from datetime import datetime

DB_NAME = "itms_data.db"

def init_db():
    """Initializes the database tables if they don't exist."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Table 1: Violations (From Computer Vision)
    c.execute('''CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    plate_number TEXT,
                    vehicle_class TEXT,
                    confidence REAL,
                    status TEXT DEFAULT 'PENDING', 
                    image_path TEXT
                )''')

    # Table 2: Traffic Stats (From DQN Simulation)
    c.execute('''CREATE TABLE IF NOT EXISTS traffic_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode INTEGER,
                    total_wait_time REAL,
                    timestamp TEXT
                )''')
    
    conn.commit()
    conn.close()
    print(f"✅ Database {DB_NAME} initialized successfully.")

def log_violation(plate, v_class, conf, img_path):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Auto-flag low confidence for Human Review
    status = "APPROVED" if conf >= 96.0 and v_class == 'civilian_car' else "REVIEW"
    
    c.execute("INSERT INTO violations (timestamp, plate_number, vehicle_class, confidence, status, image_path) VALUES (?, ?, ?, ?, ?, ?)",
              (timestamp, plate, v_class, conf, status, img_path))
    conn.commit()
    conn.close()

def log_training_step(episode, wait_time):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO traffic_stats (episode, total_wait_time, timestamp) VALUES (?, ?, ?)",
              (episode, wait_time, timestamp))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()