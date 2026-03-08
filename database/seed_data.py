import sqlite3

DB_NAME = "itms_production.db"

def seed_data():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # 1. Add Intersection (Samora Machel)
    c.execute("INSERT OR IGNORE INTO intersection (name, location, region) VALUES (?, ?, ?)", 
              ("Samora Machel & Julius Nyerere", "-17.8292, 31.0522", "Harare CBD"))

    # 2. Add Users (Police Admin)
    c.execute("INSERT OR IGNORE INTO system_user (full_name, role, username, password_hash) VALUES (?, ?, ?, ?)",
              ("Officer T. Moyo", "Admin", "admin", "hashed_secret_password"))

    # 3. Add Drivers
    c.execute("INSERT OR IGNORE INTO driver (full_name, national_id, phone_number) VALUES (?, ?, ?)",
              ("John Doe", "63-123456-F-12", "+263771234567"))
    c.execute("INSERT OR IGNORE INTO driver (full_name, national_id, phone_number) VALUES (?, ?, ?)",
              ("Zimbabwe Republic Police", "GOVT-001", "999"))

    # Get Driver IDs
    c.execute("SELECT driver_id FROM driver WHERE full_name='John Doe'")
    civ_id = c.fetchone()[0]
    c.execute("SELECT driver_id FROM driver WHERE full_name='Zimbabwe Republic Police'")
    police_id = c.fetchone()[0]

    # 4. Add Vehicles
    # Civilian Car
    c.execute("INSERT OR IGNORE INTO vehicle (plate_number, model, color, owner_id, is_exempt) VALUES (?, ?, ?, ?, ?)",
              ("ABC-1234", "Honda Fit", "Silver", civ_id, 0))
    
    # Police Car (ZRP)
    c.execute("INSERT OR IGNORE INTO vehicle (plate_number, model, color, owner_id, is_exempt) VALUES (?, ?, ?, ?, ?)",
              ("ZRP-0001","Ford Ranger", "White", police_id, 1))

    conn.commit()
    conn.close()
    print("✅ Seed Data Inserted: 1 Intersection, 2 Users, 2 Vehicles.")

if __name__ == "__main__":
    seed_data()