# api/sms_service.py
from datetime import datetime
import sqlite3
import uuid
import json


def write_audit_log(
    conn,
    user_id,
    action_type,
    entity_type,
    entity_id,
    old_value=None,
    new_value=None,
    note=None,
):
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
    c.execute(
        """
        SELECT
            v.violation_id,
            v.plate_number,
            v.timestamp,
            v.status AS violation_status,
            v.fine_amount,
            veh.is_exempt,
            d.full_name AS driver_name,
            d.phone_number
        FROM violation v
        LEFT JOIN vehicle veh ON v.plate_number = veh.plate_number
        LEFT JOIN driver d ON veh.owner_id = d.driver_id
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
        WHERE violation_id = ? AND channel = 'SMS' AND status = 'Sent'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (violation_id,),
    )
    return c.fetchone() is not None


def build_sms_message(row):
    violation_code = f"V-{row['violation_id']}"
    timestamp = row["timestamp"] or "unknown time"

    fine_text = ""
    if row["fine_amount"] is not None:
        fine_text = f" Fine amount: ${row['fine_amount']:.2f}."

    return (
        f"ITMS Notice: A traffic violation ({violation_code}) was recorded on {timestamp}."
        f"{fine_text} Please follow up with the traffic office if needed."
    )


def insert_notification_log(
    conn,
    violation_id: int,
    recipient_phone,
    message_text,
    status,
    provider="MockSMS",
    provider_message_id=None,
    error_message=None,
):
    c = conn.cursor()

    sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status == "Sent" else None

    c.execute(
        """
        INSERT INTO notification_log
        (
            violation_id,
            channel,
            recipient_phone,
            message_text,
            status,
            provider,
            provider_message_id,
            error_message,
            sent_at
        )
        VALUES (?, 'SMS', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            violation_id,
            recipient_phone,
            message_text,
            status,
            provider,
            provider_message_id,
            error_message,
            sent_at,
        ),
    )

    return c.lastrowid


def mock_send_sms(phone_number: str, message_text: str):
    provider_message_id = f"mock-{uuid.uuid4().hex[:12]}"
    print("\n" + "=" * 60)
    print("📱 MOCK SMS SENT")
    print(f"To: {phone_number}")
    print(f"Message: {message_text}")
    print(f"Provider Message ID: {provider_message_id}")
    print("=" * 60 + "\n")
    return provider_message_id


def send_sms_for_violation(conn, violation_id: int):
    row = get_violation_sms_context(conn, violation_id)
    if not row:
        return {
            "ok": False,
            "status": "Failed",
            "message": "Violation not found.",
            "recipientPhone": None,
            "notificationId": None,
        }

    if latest_sms_already_sent(conn, violation_id):
        notification_id = insert_notification_log(
            conn=conn,
            violation_id=violation_id,
            recipient_phone=row["phone_number"],
            message_text=None,
            status="Skipped",
            error_message="SMS already sent previously for this violation.",
        )
        return {
            "ok": True,
            "status": "Skipped",
            "message": "SMS already sent previously for this violation.",
            "recipientPhone": row["phone_number"],
            "notificationId": notification_id,
        }

    if row["violation_status"] not in ["Approved", "AutoApproved"]:
        notification_id = insert_notification_log(
            conn=conn,
            violation_id=violation_id,
            recipient_phone=row["phone_number"],
            message_text=None,
            status="Skipped",
            error_message=f"Violation status '{row['violation_status']}' is not eligible for SMS.",
        )
        return {
            "ok": True,
            "status": "Skipped",
            "message": f"Violation status '{row['violation_status']}' is not eligible for SMS.",
            "recipientPhone": row["phone_number"],
            "notificationId": notification_id,
        }

    if row["is_exempt"] == 1:
        notification_id = insert_notification_log(
            conn=conn,
            violation_id=violation_id,
            recipient_phone=row["phone_number"],
            message_text=None,
            status="Skipped",
            error_message="Vehicle is exempt; SMS not sent.",
        )
        return {
            "ok": True,
            "status": "Skipped",
            "message": "Vehicle is exempt; SMS not sent.",
            "recipientPhone": row["phone_number"],
            "notificationId": notification_id,
        }

    if not row["plate_number"]:
        notification_id = insert_notification_log(
            conn=conn,
            violation_id=violation_id,
            recipient_phone=None,
            message_text=None,
            status="Skipped",
            error_message="Violation has no linked registered plate.",
        )
        return {
            "ok": True,
            "status": "Skipped",
            "message": "Violation has no linked registered plate.",
            "recipientPhone": None,
            "notificationId": notification_id,
        }

    if not row["phone_number"]:
        notification_id = insert_notification_log(
            conn=conn,
            violation_id=violation_id,
            recipient_phone=None,
            message_text=None,
            status="Failed",
            error_message="No driver phone number available.",
        )
        return {
            "ok": False,
            "status": "Failed",
            "message": "No driver phone number available.",
            "recipientPhone": None,
            "notificationId": notification_id,
        }

    message_text = build_sms_message(row)
    provider_message_id = mock_send_sms(row["phone_number"], message_text)

    notification_id = insert_notification_log(
        conn=conn,
        violation_id=violation_id,
        recipient_phone=row["phone_number"],
        message_text=message_text,
        status="Sent",
        provider="MockSMS",
        provider_message_id=provider_message_id,
    )

    return {
        "ok": True,
        "status": "Sent",
        "message": "SMS sent successfully via mock provider.",
        "recipientPhone": row["phone_number"],
        "notificationId": notification_id,
    }


def process_sms_for_violation(conn, violation_id: int, user_id=None, note=None):
    """
    Central helper:
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
            "status": result["status"],
            "recipientPhone": result["recipientPhone"],
            "notificationId": result["notificationId"],
        },
        note=note or result["message"],
    )

    return result