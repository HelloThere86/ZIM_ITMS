from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from api.auth import UserOut, require_permission, router as auth_router
from api.sms_service import process_sms_for_violation
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import sqlite3
import json
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DB_PATH = PROJECT_ROOT / "database" / "itms_production.db"
EVIDENCE_DIR = PROJECT_ROOT / "dashboard" / "evidence"
TRAFFIC_RESULTS_PATH = PROJECT_ROOT / "results" / "comparison_results.json"

app = FastAPI(title="ITMS Backend API")
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/evidence", StaticFiles(directory=str(EVIDENCE_DIR)), name="evidence")


class ReviewDecisionRequest(BaseModel):
    decision: str  # Approved | Rejected
    reviewerUserId: Optional[int] = None
    note: Optional[str] = None
    correctedPlateNumber: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    configValue: str
    updatedBy: Optional[int] = None
    note: Optional[str] = None


class EvidenceAccessRequest(BaseModel):
    action: str  # Viewed | Exported
    userId: Optional[int] = None
    note: Optional[str] = None


class SendSmsRequest(BaseModel):
    userId: Optional[int] = None
    note: Optional[str] = None


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def normalize_plate(plate: Optional[str]) -> Optional[str]:
    if not plate:
        return None
    cleaned = "".join(ch for ch in plate.upper() if ch.isalnum())
    return cleaned or None


def parse_violation_id(violation_code: str) -> int:
    value = violation_code.strip()
    if value.upper().startswith("V-"):
        value = value[2:]
    try:
        return int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid violation ID format")


def format_timestamp(ts: Optional[str]) -> str:
    if not ts:
        return ""
    return f"{ts[5:7]}/{ts[8:10]}/{ts[0:4]} {ts[11:16]}"


def format_date(ts: Optional[str]) -> str:
    if not ts:
        return ""
    return f"{ts[5:7]}/{ts[8:10]}/{ts[0:4]}"


def get_confidence_label(confidence: float) -> str:
    if confidence >= 90:
        return "High"
    if confidence >= 75:
        return "Medium"
    return "Low"


def map_violation_status(db_status: str) -> str:
    if db_status == "Pending":
        return "Flagged"
    if db_status in ["Approved", "AutoApproved", "Paid"]:
        return "Approved"
    return "Rejected"


def map_review_status(db_status: str) -> str:
    if db_status == "Pending":
        return "Pending"
    if db_status == "Rejected":
        return "Rejected"
    return "Approved"


def build_case_reference(violation_id: int, timestamp: Optional[str]) -> str:
    year = timestamp[:4] if timestamp else "0000"
    return f"CASE-{year}-{violation_id:04d}"


def load_traffic_results():
    if not TRAFFIC_RESULTS_PATH.exists():
        fallback_models = {
            "fixed_timer": {
                "avgWaitPerStep": 159.10,
                "avgQueuePerStep": 17.12,
                "throughput": 4225,
                "runs": 5,
            },
            "individual_dqn": {
                "avgWaitPerStep": 53.43,
                "avgQueuePerStep": 10.39,
                "throughput": 4222,
                "runs": 5,
            },
            "coop_dqn": {
                "avgWaitPerStep": 52.58,
                "avgQueuePerStep": 10.49,
                "throughput": 4232,
                "runs": 5,
            },
            "qmix": {
                "avgWaitPerStep": 109.63,
                "avgQueuePerStep": 21.21,
                "throughput": 4035,
                "runs": 5,
            },
        }

        baseline_wait = fallback_models["fixed_timer"]["avgWaitPerStep"]
        best_wait = fallback_models["coop_dqn"]["avgWaitPerStep"]
        improvement = ((baseline_wait - best_wait) / baseline_wait) * 100

        return {
            "models": fallback_models,
            "baselineWaitingTime": baseline_wait,
            "dqnWaitingTime": best_wait,
            "improvementPercent": round(improvement, 2),
            "bestModelKey": "coop_dqn",
            "trainingEpisodes": 500,
            "trainingRewards": [],
            "notes": "Fallback demo values. Replace with exported comparison_results.json.",
        }

    with open(TRAFFIC_RESULTS_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    models = raw.get("models", {})

    fixed = models.get("fixed_timer", {})
    best = models.get("coop_dqn", {})

    baseline_wait = fixed.get("avgWaitPerStep")
    best_wait = best.get("avgWaitPerStep")

    if baseline_wait is None or best_wait is None:
        raise HTTPException(
            status_code=500,
            detail="comparison_results.json is missing avgWaitPerStep values for fixed_timer or coop_dqn",
        )

    improvement = ((baseline_wait - best_wait) / baseline_wait) * 100 if baseline_wait > 0 else 0.0

    return {
        "models": models,
        "baselineWaitingTime": round(float(baseline_wait), 2),
        "dqnWaitingTime": round(float(best_wait), 2),
        "improvementPercent": round(float(improvement), 2),
        "bestModelKey": "coop_dqn",
        "trainingEpisodes": raw.get("trainingEpisodes", 500),
        "trainingRewards": raw.get("trainingRewards", []),
        "notes": raw.get("notes", ""),
    }


def write_audit_log(
    conn,
    user_id: Optional[int],
    action_type: str,
    entity_type: str,
    entity_id: str,
    old_value=None,
    new_value=None,
    note: Optional[str] = None,
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


@app.get("/api/stats")
def get_stats(_: UserOut = Depends(require_permission("violations:read"))):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT status, COUNT(*) as count FROM violation GROUP BY status")
    rows = c.fetchall()
    conn.close()

    stats = {"Flagged": 0, "Approved": 0, "Rejected": 0}
    for row in rows:
        status = row["status"]
        count = row["count"]

        if status == "Pending":
            stats["Flagged"] += count
        elif status in ["Approved", "AutoApproved", "Paid"]:
            stats["Approved"] += count
        elif status == "Rejected":
            stats["Rejected"] += count

    return stats


@app.get("/api/violations")
def get_violations(_: UserOut = Depends(require_permission("violations:read"))):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            v.violation_id,
            v.plate_number,
            i.name as intersection_name,
            v.timestamp,
            v.confidence_score,
            v.status,
            v.image_path,
            v.video_path,
            v.review_note
        FROM violation v
        LEFT JOIN intersection i ON v.intersection_id = i.intersection_id
        ORDER BY v.timestamp DESC
    """
    c.execute(query)
    rows = c.fetchall()
    conn.close()

    violations = []
    for row in rows:
        ui_status = map_violation_status(row["status"])
        violations.append({
            "id": f"V-{row['violation_id']}",
            "plateNumber": row["plate_number"] or "UNKNOWN",
            "intersection": row["intersection_name"] or "Unknown Intersection",
            "time": format_timestamp(row["timestamp"]),
            "confidence": int(row["confidence_score"] or 0),
            "status": ui_status,
            "imagePath": row["image_path"],
            "videoPath": row["video_path"],
            "imageUrl": f"/evidence/{row['image_path']}" if row["image_path"] else None,
            "videoUrl": f"/evidence/{row['video_path']}" if row["video_path"] else None,
            "reviewNote": row["review_note"] or "",
        })

    return violations


@app.get("/api/traffic-results")
def get_traffic_results(_: UserOut = Depends(require_permission("results:read"))):
    try:
        return load_traffic_results()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load traffic results: {str(e)}")


@app.get("/api/review-queue")
def get_review_queue(_: UserOut = Depends(require_permission("violations:approve"))):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            v.violation_id,
            v.plate_number,
            i.name as intersection_name,
            v.timestamp,
            v.confidence_score,
            v.status,
            v.image_path,
            v.video_path,
            v.review_note
        FROM violation v
        LEFT JOIN intersection i ON v.intersection_id = i.intersection_id
        ORDER BY v.timestamp DESC
    """
    c.execute(query)
    rows = c.fetchall()
    conn.close()

    cases = []
    for row in rows:
        confidence = int(row["confidence_score"] or 0)
        cases.append({
            "id": f"V-{row['violation_id']}",
            "plateNumber": row["plate_number"] or "UNKNOWN",
            "intersection": row["intersection_name"] or "Unknown Intersection",
            "time": format_timestamp(row["timestamp"]),
            "confidence": confidence,
            "confidenceLevel": get_confidence_label(confidence),
            "reviewStatus": map_review_status(row["status"]),
            "evidenceType": "Video" if row["video_path"] else "Image",
            "notes": row["review_note"] or "No reviewer note available.",
            "imagePath": row["image_path"],
            "videoPath": row["video_path"],
            "imageUrl": f"/evidence/{row['image_path']}" if row["image_path"] else None,
            "videoUrl": f"/evidence/{row['video_path']}" if row["video_path"] else None,
        })

    return cases

@app.post("/api/review-queue/{violation_code}/decision")
def decide_review_case(
    violation_code: str,
    payload: ReviewDecisionRequest,
    user: UserOut = Depends(require_permission("violations:approve")),
):
    if payload.decision not in ["Approved", "Rejected"]:
        raise HTTPException(status_code=400, detail="Decision must be 'Approved' or 'Rejected'")

    violation_id = parse_violation_id(violation_code)
    corrected_plate = normalize_plate(payload.correctedPlateNumber)

    conn = get_db()
    c = conn.cursor()

    # Wrap everything in a try block to ensure the database NEVER gets locked
    try:
        c.execute(
            """
            SELECT violation_id, plate_number, status, reviewer_user_id, reviewed_at, review_note
            FROM violation
            WHERE violation_id = ?
            """,
            (violation_id,),
        )
        existing = c.fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Violation not found")

        final_plate = existing["plate_number"]

        # Guard clause for UNKNOWN plates
        if (not final_plate or final_plate == "UNKNOWN") and not corrected_plate:
            print(f"DEBUG: Rejecting case V-{violation_id} automatically - Plate is UNKNOWN.")
            c.execute(
                "UPDATE violation SET status = 'Rejected', review_note = 'Case automatically rejected: Unreadable license plate.' WHERE violation_id = ?",
                (violation_id,)
            )
            conn.commit()
            return {
                "message": "Case automatically rejected due to unreadable (UNKNOWN) license plate.",
                "status": "Rejected",
                "plateNumber": "UNKNOWN",
                "smsResult": None
            }

        # If approving with a correction, verify the corrected plate exists
        if payload.decision == "Approved" and corrected_plate:
            plate_exists = c.execute(
                "SELECT 1 FROM vehicle WHERE plate_number = ? LIMIT 1",
                (corrected_plate,),
            ).fetchone()

            if not plate_exists:
                raise HTTPException(
                    status_code=400,
                    detail=f"Corrected plate {corrected_plate} is not in the vehicle registry",
                )
            final_plate = corrected_plate

        old_state = {
            "plate_number": existing["plate_number"],
            "status": existing["status"],
            "reviewer_user_id": existing["reviewer_user_id"],
            "reviewed_at": existing["reviewed_at"],
            "review_note": existing["review_note"],
        }

        reviewed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing_note = existing["review_note"] or ""
        officer_note = payload.note or ""

        if corrected_plate and payload.decision == "Approved":
            officer_note = (
                f"{officer_note} | Officer confirmed plate: {corrected_plate}"
                if officer_note
                else f"Officer confirmed plate: {corrected_plate}"
            )

        updated_note = existing_note
        if officer_note:
            updated_note = f"{existing_note} [OFFICER_REVIEW={officer_note}]" if existing_note else officer_note

        # THE FIX: Only update the plate_number in the DB if you actually corrected it.
        # Otherwise, just update the status to Rejected.
        if corrected_plate:
            c.execute(
                """
                UPDATE violation
                SET status = ?,
                    decision_type = 'Flagged',
                    plate_number = ?,
                    reviewer_user_id = ?,
                    reviewed_at = ?,
                    review_note = ?
                WHERE violation_id = ?
                """,
                (payload.decision, final_plate, user.user_id, reviewed_at, updated_note, violation_id),
            )
        else:
            c.execute(
                """
                UPDATE violation
                SET status = ?,
                    decision_type = 'Flagged',
                    reviewer_user_id = ?,
                    reviewed_at = ?,
                    review_note = ?
                WHERE violation_id = ?
                """,
                (payload.decision, user.user_id, reviewed_at, updated_note, violation_id),
            )

        sms_result = None
        if payload.decision == "Approved":
            try:
                sms_result = process_sms_for_violation(
                    conn=conn,
                    violation_id=violation_id,
                    user_id=user.user_id,
                    note="Automatic SMS after human approval",
                )
            except Exception as sms_err:
                sms_result = {
                    "status": "Failed",
                    "error": str(sms_err),
                }

        new_state = {
            "plate_number": final_plate,
            "status": payload.decision,
            "reviewer_user_id": user.user_id,
            "reviewed_at": reviewed_at,
            "review_note": updated_note,
        }

        write_audit_log(
            conn=conn,
            user_id=user.user_id,
            action_type=f"Review {payload.decision}",
            entity_type="Violation",
            entity_id=f"V-{violation_id}",
            old_value=old_state,
            new_value=new_state,
            note=officer_note or f"Violation marked as {payload.decision}",
        )

        conn.commit()
        return {
            "message": f"Violation V-{violation_id} updated successfully",
            "status": payload.decision,
            "plateNumber": final_plate,
            "smsResult": sms_result,
        }

    except sqlite3.IntegrityError as e:
        # If any foreign key issues still happen, we rollback so the DB doesn't lock!
        conn.rollback()
        print(f"DEBUG: IntegrityError caught: {e}")
        raise HTTPException(status_code=400, detail="Database integrity error while saving the review decision.")
    
    finally:
        # This will ALWAYS execute, meaning your database will never lock up during the demo
        conn.close()

@app.get("/api/evidence-search")
def get_evidence_search(
    plateNumber: Optional[str] = Query(default=None),
    intersection: Optional[str] = Query(default=None),
    dateFrom: Optional[str] = Query(default=None),
    dateTo: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _: UserOut = Depends(require_permission("evidence:read")),
):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            v.violation_id,
            v.plate_number,
            i.name as intersection_name,
            v.timestamp,
            v.status,
            v.image_path,
            v.video_path,
            v.review_note
        FROM violation v
        LEFT JOIN intersection i ON v.intersection_id = i.intersection_id
        WHERE 1=1
    """
    params = []

    if plateNumber:
        query += " AND UPPER(COALESCE(v.plate_number, '')) LIKE ?"
        params.append(f"%{plateNumber.upper()}%")

    if intersection:
        query += " AND LOWER(COALESCE(i.name, '')) LIKE ?"
        params.append(f"%{intersection.lower()}%")

    if dateFrom:
        query += " AND DATE(v.timestamp) >= DATE(?)"
        params.append(dateFrom)

    if dateTo:
        query += " AND DATE(v.timestamp) <= DATE(?)"
        params.append(dateTo)

    if status and status != "All":
        if status == "Approved":
            query += " AND v.status IN ('Approved', 'AutoApproved', 'Paid')"
        elif status == "Flagged":
            query += " AND v.status = 'Pending'"
        elif status == "Rejected":
            query += " AND v.status = 'Rejected'"

    query += " ORDER BY v.timestamp DESC"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    records = []
    for row in rows:
        records.append({
            "id": f"V-{row['violation_id']}",
            "plateNumber": row["plate_number"] or "UNKNOWN",
            "intersection": row["intersection_name"] or "Unknown Intersection",
            "date": format_date(row["timestamp"]),
            "status": map_violation_status(row["status"]),
            "evidenceType": "Video" if row["video_path"] else "Image",
            "caseReference": build_case_reference(row["violation_id"], row["timestamp"]),
            "notes": row["review_note"] or "Evidence record available.",
            "imagePath": row["image_path"],
            "videoPath": row["video_path"],
            "imageUrl": f"/evidence/{row['image_path']}" if row["image_path"] else None,
            "videoUrl": f"/evidence/{row['video_path']}" if row["video_path"] else None,
        })

    return records


@app.post("/api/evidence-search/{violation_code}/access")
def log_evidence_access(
    violation_code: str,
    payload: EvidenceAccessRequest,
    user: UserOut = Depends(require_permission("evidence:read")),
):
    if payload.action not in ["Viewed", "Exported"]:
        raise HTTPException(status_code=400, detail="Action must be 'Viewed' or 'Exported'")
    if payload.action == "Exported" and "evidence:export" not in user.permissions:
        raise HTTPException(status_code=403, detail="You do not have permission to export evidence.")

    violation_id = parse_violation_id(violation_code)
    conn = get_db()
    c = conn.cursor()

    c.execute(
        """
        SELECT violation_id, plate_number, image_path, video_path, timestamp
        FROM violation
        WHERE violation_id = ?
        """,
        (violation_id,),
    )
    row = c.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Violation not found")

    evidence_type = "Video" if row["video_path"] else "Image" if row["image_path"] else "None"

    write_audit_log(
        conn=conn,
        user_id=user.user_id,
        action_type="Evidence Accessed",
        entity_type="Violation",
        entity_id=f"V-{violation_id}",
        old_value=None,
        new_value={
            "action": payload.action,
            "evidence_type": evidence_type,
            "plate_number": row["plate_number"],
            "timestamp": row["timestamp"],
        },
        note=payload.note or f"Evidence {payload.action.lower()} for V-{violation_id}",
    )

    conn.commit()
    conn.close()

    return {
        "message": f"Evidence access logged for V-{violation_id}",
        "action": payload.action,
    }


@app.get("/api/violations/{violation_id}/sms")
def get_sms_log(violation_id: int, _: UserOut = Depends(require_permission("sms:send"))):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT status, message_text, recipient_phone, sent_at, error_message
        FROM notification_log
        WHERE violation_id = ?
        ORDER BY notification_id DESC LIMIT 1
        """,
        (violation_id,),
    )
    row = c.fetchone()
    conn.close()

    if row:
        return dict(row)
    return {"status": "None", "message_text": "No SMS generated yet."}


@app.post("/api/violations/{violation_code}/send-sms")
def send_violation_sms(
    violation_code: str,
    payload: SendSmsRequest,
    user: UserOut = Depends(require_permission("sms:send")),
):
    violation_id = parse_violation_id(violation_code)
    conn = get_db()

    try:
        result = process_sms_for_violation(
            conn=conn,
            violation_id=violation_id,
            user_id=user.user_id,
            note=payload.note or "Manual SMS trigger from API/UI",
        )
        conn.commit()
        return result

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send SMS: {str(e)}")
    finally:
        conn.close()


@app.get("/api/notifications/sms")
def get_sms_notifications(_: UserOut = Depends(require_permission("sms:send"))):
    conn = get_db()
    c = conn.cursor()

    c.execute(
        """
        SELECT
            n.notification_id,
            n.violation_id,
            n.recipient_phone,
            n.message_text,
            n.status,
            n.provider,
            n.provider_message_id,
            n.error_message,
            n.created_at,
            n.sent_at
        FROM notification_log n
        WHERE n.channel = 'SMS'
        ORDER BY n.created_at DESC
        """
    )

    rows = c.fetchall()
    conn.close()

    return [
        {
            "id": row["notification_id"],
            "violationId": f"V-{row['violation_id']}",
            "recipientPhone": row["recipient_phone"],
            "messageText": row["message_text"],
            "status": row["status"],
            "provider": row["provider"],
            "providerMessageId": row["provider_message_id"],
            "errorMessage": row["error_message"],
            "createdAt": row["created_at"],
            "sentAt": row["sent_at"],
        }
        for row in rows
    ]


@app.get("/api/audit-log")
def get_audit_log(_: UserOut = Depends(require_permission("audit:read"))):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            a.audit_id,
            a.timestamp,
            a.action_type,
            a.entity_type,
            a.entity_id,
            a.old_value,
            a.new_value,
            a.note,
            COALESCE(au.full_name, su.full_name) as actor_name
        FROM audit_log a
        LEFT JOIN users au ON a.user_id = au.user_id
        LEFT JOIN system_user su ON a.user_id = su.user_id
        ORDER BY a.timestamp DESC
    """
    c.execute(query)
    rows = c.fetchall()
    conn.close()

    events = []
    for row in rows:
        action_type = row["action_type"] or "Unknown Action"

        if action_type == "Configuration Updated":
            severity = "Critical"
        elif action_type in [
            "Review Approved",
            "Review Rejected",
            "Evidence Accessed",
            "SMS Notification Sent",
            "SMS Notification Failed",
            "SMS Notification Skipped",
        ]:
            severity = "Sensitive"
        else:
            severity = "Normal"

        events.append({
            "id": f"AUD-{row['audit_id']}",
            "timestamp": row["timestamp"] or "",
            "actor": row["actor_name"] or "System",
            "actionType": action_type,
            "target": f"{row['entity_type']} {row['entity_id']}" if row["entity_type"] else row["entity_id"],
            "summary": row["note"] or "No summary available.",
            "severity": severity,
            "oldValue": row["old_value"],
            "newValue": row["new_value"],
        })

    return events


@app.get("/api/config")
def get_config(_: UserOut = Depends(require_permission("settings:read"))):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            sc.config_key,
            sc.config_value,
            sc.updated_at,
            sc.updated_by,
            COALESCE(au.full_name, su.full_name) as updated_by_name
        FROM system_config sc
        LEFT JOIN users au ON sc.updated_by = au.user_id
        LEFT JOIN system_user su ON sc.updated_by = su.user_id
        ORDER BY sc.config_key ASC
    """
    c.execute(query)
    rows = c.fetchall()
    conn.close()

    config_items = []
    for row in rows:
        config_items.append({
            "key": row["config_key"],
            "value": row["config_value"],
            "updatedAt": row["updated_at"],
            "updatedBy": row["updated_by"],
            "updatedByName": row["updated_by_name"] or "System",
        })

    return config_items


@app.put("/api/config/{config_key}")
def update_config(
    config_key: str,
    payload: ConfigUpdateRequest,
    user: UserOut = Depends(require_permission("settings:write")),
):
    conn = get_db()
    c = conn.cursor()

    c.execute(
        """
        SELECT config_key, config_value, updated_at, updated_by
        FROM system_config
        WHERE config_key = ?
        """,
        (config_key,),
    )
    existing = c.fetchone()

    old_state = None
    if existing:
        old_state = {
            "config_key": existing["config_key"],
            "config_value": existing["config_value"],
            "updated_at": existing["updated_at"],
            "updated_by": existing["updated_by"],
        }

    c.execute(
        """
        INSERT INTO system_config (config_key, config_value, updated_at, updated_by)
        VALUES (?, ?, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(config_key) DO UPDATE SET
            config_value = excluded.config_value,
            updated_at = CURRENT_TIMESTAMP,
            updated_by = excluded.updated_by
        """,
        (config_key, payload.configValue, user.user_id),
    )

    new_state = {
        "config_key": config_key,
        "config_value": payload.configValue,
        "updated_by": user.user_id,
    }

    write_audit_log(
        conn=conn,
        user_id=user.user_id,
        action_type="Configuration Updated",
        entity_type="System_Config",
        entity_id=config_key,
        old_value=old_state,
        new_value=new_state,
        note=payload.note or f"Configuration '{config_key}' updated",
    )

    conn.commit()
    conn.close()

    return {"message": f"Configuration '{config_key}' updated successfully"}


@app.get("/api/fines")
def get_fines(_: UserOut = Depends(require_permission("fines:read"))):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT violation_name, fine_amount, currency FROM fine_matrix")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]
