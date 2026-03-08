from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
from pydantic import BaseModel
from typing import List

app = FastAPI(title="ITMS Backend API")

# --- CORS SETUP ---
# This allows your React app (running on localhost:5173 or 3000) to talk to this Python server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to your React domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "../database/itms_production.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row # Returns rows as dictionaries instead of tuples
    return conn

# --- ENDPOINT 1: GET DASHBOARD STATS ---
@app.get("/api/stats")
def get_stats():
    conn = get_db()
    c = conn.cursor()
    
    # Count how many of each status exist
    c.execute("SELECT status, COUNT(*) as count FROM violation GROUP BY status")
    rows = c.fetchall()
    conn.close()
    
    stats = {"Flagged": 0, "Approved": 0, "Rejected": 0}
    for row in rows:
        status = row['status']
        count = row['count']
        if status == 'Pending':
            stats["Flagged"] += count
        elif status in ['Approved', 'AutoApproved']:
            stats["Approved"] += count
        elif status == 'Rejected':
            stats["Rejected"] += count
            
    return stats

# --- ENDPOINT 2: GET ALL VIOLATIONS ---
@app.get("/api/violations")
def get_violations():
    conn = get_db()
    c = conn.cursor()
    
    # We join the intersection table to get the real street name
    query = """
        SELECT v.violation_id, v.plate_number, i.name as intersection_name, 
               v.timestamp, v.confidence_score, v.status 
        FROM violation v
        LEFT JOIN intersection i ON v.intersection_id = i.intersection_id
        ORDER BY v.timestamp DESC
    """
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    
    violations =[]
    for row in rows:
        # Map DB status to UI status
        db_status = row['status']
        ui_status = "Flagged" if db_status == "Pending" else "Approved" if db_status in ["AutoApproved", "Approved"] else "Rejected"
        
        # Format the data to match your React Interface exactly!
        violations.append({
            "id": f"V-{row['violation_id']}",
            "plateNumber": row['plate_number'] or "UNKNOWN",
            "intersection": row['intersection_name'] or "Samora Machel",
            # Format DB datetime (YYYY-MM-DD HH:MM:SS) to React format (MM/DD/YYYY HH:MM)
            "time": row['timestamp'][5:7] + "/" + row['timestamp'][8:10] + "/" + row['timestamp'][0:4] + " " + row['timestamp'][11:16],
            "confidence": int(row['confidence_score']),
            "status": ui_status
        })
        
    return violations