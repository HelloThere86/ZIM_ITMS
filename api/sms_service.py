# api/sms_service.py
import os
import json
import sqlite3
import uuid
from datetime import datetime
from dotenv import load_dotenv
from twilio.rest import Client

# Load environment variables from .env file
load_dotenv()

def write_audit_log(conn, user_id, action_type, entity_type, entity_id, old_value=None, new_value=None, note=None):
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO audit_log (
            user_id, action_type, entity_type, entity_id, old_value, new_value, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            action_type,
            entity_type,
            entity_id,
            json.dumps(old_value) if old_value is not None else None,
            json.dumps(new_value) if new_value is not None else None,
            note,
        ),
    )

def get_violation_sms_context(conn, violation_id: int):
    c = conn.cursor()
    # We fetch the default fine from fine_matrix if v.fine_amount is null
    c.execute(
        """
        SELECT
            v.violation_id,
            v.plate_number,
            v.timestamp,
            v.status AS violation_status,
            COALESCE(v.fine_amount, fm.fine_amount, 30.00) AS fine_amount,
            veh.is_exempt,
            d.full_name AS driver_name,
            d.phone_number
        FROM violation v
        LEFT JOIN vehicle veh ON v.plate_number = veh.plate_number
        LEFT JOIN driver d ON veh.owner_id = d.driver_id
        LEFT JOIN fine_matrix fm ON fm.violation_name = 'civilian_car'
        WHERE v.violation_id = ?
        """,
        (violation_id,),
    )
    return c.fetchone()

def latest_sms_already_sent(conn, violation_id: int) -> bool:
    c = conn.cursor()
    c.execute(
        """
        SELECT 1
        FROM notification_log
        WHERE violation_id = ? AND channel = 'SMS' AND status IN ('Sent', 'Delivered', 'Failed')
        ORDER BY sent_at DESC
        LIMIT 1
        """,
        (violation_id,),
    )
    return c.fetchone() is not None

def build_sms_message(row):
    # Extract the variables we need from the database row
    violation_code = f"V-{row['violation_id']}"
    plate_number = row["plate_number"] or "UNKNOWN"
    timestamp = row["timestamp"] or "unknown time"

    # Return the carrier-safe formatted string
    return (
        f"TICKET REF: {violation_code}\n"
        f"VEHICLE: {plate_number}\n"
        f"DATE: {timestamp}\n"
        f"STATUS: Pending Review.\n"
        f"Please visit the nearest ZRP office to clear this notice."
    )

def insert_notification_log(conn, violation_id, recipient_phone, message_text, status, provider="Twilio", provider_message_id=None, error_message=None):
    c = conn.cursor()
    sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute(
        """
        INSERT INTO notification_log
        (
            violation_id, channel, recipient_phone, message_text, 
            status, provider, provider_message_id, error_message, sent_at
        )
        VALUES (?, 'SMS', ?, ?, ?, ?, ?, ?, ?)
        """,
        (violation_id, recipient_phone, message_text, status, provider, provider_message_id, error_message, sent_at),
    )
    return c.lastrowid

def send_real_twilio_sms(phone_number: str, message_text: str):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not account_sid or not auth_token:
        raise ValueError("Twilio credentials not found.")

    client = Client(account_sid, auth_token)
    message = client.messages.create(
        body=message_text,
        from_=twilio_number,
        to=phone_number
    )
    return message.sid

def send_sms_for_violation(conn, violation_id: int):
    row = get_violation_sms_context(conn, violation_id)
    if not row:
        return {"ok": False, "status": "Failed", "message": "Violation not found."}

    # If we already tried and failed, succeeded, or skipped, don't retry.
    if latest_sms_already_sent(conn, violation_id):
        return {"ok": True, "status": "Skipped", "message": "Violation already processed."}

    if row["violation_status"] not in ["Approved", "AutoApproved"]:
        # Logic: Don't log a 'Failed' record here yet, as it might become Approved later
        return {"ok": True, "status": "Skipped", "message": "Status not eligible."}

    # --- LOG THE SKIP FOR EXEMPT VEHICLES ---
    if row["is_exempt"] == 1:
        insert_notification_log(
            conn=conn, violation_id=violation_id, recipient_phone=row["phone_number"],
            message_text=None, status="Skipped", error_message="Vehicle is exempt (Emergency/VIP)."
        )
        return {"ok": True, "status": "Skipped", "message": "Vehicle is exempt."}

    if not row["plate_number"] or row["plate_number"] == "UNKNOWN":
        insert_notification_log(
            conn=conn, violation_id=violation_id, recipient_phone=None,
            message_text=None, status="Failed", error_message="Plate unreadable."
        )
        return {"ok": False, "status": "Failed", "message": "Permanent Error: Plate UNKNOWN."}

    if not row["phone_number"]:
        insert_notification_log(
            conn=conn, violation_id=violation_id, recipient_phone=None,
            message_text=None, status="Failed", error_message="No registered phone number."
        )
        return {"ok": False, "status": "Failed", "message": "Permanent Error: No phone number."}

    message_text = build_sms_message(row)
    
    try:
        provider_message_id = send_real_twilio_sms(row["phone_number"], message_text)
        insert_notification_log(
            conn=conn, violation_id=violation_id, recipient_phone=row["phone_number"],
            message_text=message_text, status="Sent", provider="Twilio", provider_message_id=provider_message_id
        )
        return {"ok": True, "status": "Sent", "message": "SMS sent successfully."}
    except Exception as e:
        insert_notification_log(
            conn=conn, violation_id=violation_id, recipient_phone=row["phone_number"],
            message_text=message_text, status="Queued", provider="Twilio", error_message=str(e)
        )
        return {"ok": False, "status": "Queued", "message": "Network down. Queued."}
    
def process_sms_for_violation(conn, violation_id: int, user_id=None, note=None):
    """
    Central helper used by the Sync Worker:
    - sends / skips / fails SMS based on current violation state
    - writes matching audit log
    """
    result = send_sms_for_violation(conn, violation_id)

    action_type = (
        "SMS Notification Sent"
        if result["status"] == "Sent"
        else "SMS Notification Skipped"
        if result["status"] == "Skipped"
        else "SMS Notification Failed"
    )

    write_audit_log(
        conn=conn,
        user_id=user_id,
        action_type=action_type,
        entity_type="Violation",
        entity_id=f"V-{violation_id}",
        old_value=None,
        new_value={
            "status": result.get("status"),
            "recipientPhone": result.get("recipientPhone"),
        },
        note=note or result.get("message"),
    )

    return result