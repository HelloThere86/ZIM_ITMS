import sqlite3

DB_PATH = "itms_production.db"

def setup_fines():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Create Fines Table
    c.execute('''CREATE TABLE IF NOT EXISTS fine_matrix (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    violation_name TEXT UNIQUE,
                    fine_amount REAL,
                    currency TEXT DEFAULT 'USD'
                )''')
    
    # Insert Standard Zimbabwean Fines
    fines =[
        ("Red Light Violation", 30.00),
        ("Speeding", 20.00),
        ("Unregistered Vehicle", 50.00)
    ]
    
    c.executemany("INSERT OR IGNORE INTO fine_matrix (violation_name, fine_amount) VALUES (?, ?)", fines)
    conn.commit()
    conn.close()
    print("✅ Fine Matrix Table created and populated!")

if __name__ == "__main__":
    setup_fines()