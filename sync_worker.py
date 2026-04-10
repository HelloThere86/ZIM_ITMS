import sqlite3
import time
import os
import sys
from datetime import datetime

# --- SETUP ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
    
from api.sms_service import process_sms_for_violation

DB_PATH = "database/itms_production.db"
CHECK_INTERVAL_SECONDS = 30 # Check less often to reduce spam

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def process_sync_queue():
    """
    Finds 'AutoApproved' violations that have NOT been processed yet
    and tries to send an SMS for them.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Sync Worker: Checking for new 'AutoApproved' tasks...")
    
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        # --- THE SMART QUERY ---
        # Find violations that are AutoApproved AND have NO existing notification log entry.
        c.execute("""
            SELECT v.violation_id FROM violation v
            WHERE v.status = 'AutoApproved' AND NOT EXISTS (
                SELECT 1 FROM notification_log nl 
                WHERE nl.violation_id = v.violation_id
            )
        """)
        tasks_to_process = c.fetchall()
        
        if not tasks_to_process:
            conn.close()
            return

        print(f"⚠️ Found {len(tasks_to_process)} NEW tasks to process. Attempting SMS notifications...")
        
        for task in tasks_to_process:
            violation_id = task['violation_id']
            print(f"   -> Processing V-{violation_id}...")
            
            # This function will now try once. If it fails (e.g., no plate), it will
            # create a "Failed" log, and this query won't pick it up again.
            result = process_sms_for_violation(
                conn=conn, 
                violation_id=violation_id, 
                note="Processed by Sync Worker"
            )
            
            # Commit the new notification log entry (whether it's Sent, Failed, or Skipped)
            conn.commit()

            print(f"   -> Result for V-{violation_id}: {result.get('status')} - {result.get('message')}")
            
    except Exception as e:
        print(f"❌ Sync Worker Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("="*50)
    print("📡 ITMS OFFLINE SYNC DAEMON STARTED (Smart Queue Mode)")
    print("This worker will now process each violation only once.")
    print("="*50)
    
    while True:
        process_sync_queue()
        time.sleep(CHECK_INTERVAL_SECONDS)