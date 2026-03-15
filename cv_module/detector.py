import cv2
import numpy as np
import easyocr
import sqlite3
import os
import sys
import time
import subprocess
from datetime import datetime
from collections import deque
from pathlib import Path
from ultralytics import YOLO
import tensorflow as tf

# =========================================================
# CONFIGURATION
# =========================================================
VIDEO_SOURCE = "test_traffic.mp4"   # Change to 0 for webcam
MODEL_PATH = "zimbabwe_traffic_model.h5"

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

DB_PATH = PROJECT_ROOT / "database" / "itms_production.db"
EVIDENCE_DIR = PROJECT_ROOT / "dashboard" / "evidence"

# Make project root importable so detector can use api.sms_service
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from api.sms_service import process_sms_for_violation

CONFIDENCE_THRESHOLD = 96.0
DEFAULT_INTERSECTION_ID = 1

PRE_EVENT_SECONDS = 2
POST_EVENT_SECONDS = 3
TRIGGER_COOLDOWN_SECONDS = 2.5

CNN_CLASSES = ["ambulance", "civilian_car", "fire_truck", "police_car"]


# =========================================================
# FILESYSTEM / PROCESS HELPERS
# =========================================================
def ensure_directories():
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


def ffmpeg_available():
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def save_video_clip(frames, output_path, fps):
    """
    Save raw AVI clip using MJPG.
    This is more reliable than writing MP4 directly with OpenCV.
    """
    if not frames:
        print("❌ No frames available for video clip.")
        return False

    height, width = frames[0].shape[:2]

    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (width, height),
    )

    if not writer.isOpened():
        print(f"❌ Failed to open VideoWriter for: {output_path}")
        return False

    for frame in frames:
        writer.write(frame)

    writer.release()

    if not output_path.exists():
        print(f"❌ Raw clip file was not created: {output_path}")
        return False

    file_size = output_path.stat().st_size
    if file_size <= 0:
        print(f"❌ Raw clip file is empty: {output_path}")
        return False

    print(f"✅ Raw AVI clip saved: {output_path.name} ({file_size} bytes)")
    return True


def convert_to_browser_mp4(input_path, output_path):
    """
    Convert raw AVI to browser-friendly H.264 MP4.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(input_path),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(output_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print("❌ FFmpeg conversion failed.")
            print(result.stderr)
            return False

        if not output_path.exists():
            print(f"❌ FFmpeg output file not found: {output_path}")
            return False

        file_size = output_path.stat().st_size
        if file_size <= 0:
            print(f"❌ Converted MP4 is empty: {output_path}")
            return False

        print(f"✅ Browser MP4 created: {output_path.name} ({file_size} bytes)")
        return True

    except Exception as e:
        print(f"❌ FFmpeg conversion exception: {e}")
        return False


# =========================================================
# DATABASE HELPERS
# =========================================================
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def vehicle_exists(conn, plate_number):
    if not plate_number:
        return False

    c = conn.cursor()
    c.execute("SELECT 1 FROM vehicle WHERE plate_number = ? LIMIT 1", (plate_number,))
    return c.fetchone() is not None


def intersection_exists(conn, intersection_id):
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM intersection WHERE intersection_id = ? LIMIT 1",
        (intersection_id,),
    )
    return c.fetchone() is not None


def normalize_plate_text(plate_text):
    if not plate_text:
        return "UNKNOWN"

    cleaned = plate_text.upper().strip()
    cleaned = cleaned.replace(" ", "")
    return cleaned if cleaned else "UNKNOWN"


def log_violation(plate, v_class, conf, frame_img, video_filename):
    """
    Log violation to SQLite with image + video evidence.
    Also auto-process SMS when status becomes AutoApproved.
    """
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        unique_id = int(time.time() * 1000)

        # Save image snapshot
        img_filename = f"violation_{unique_id}.jpg"
        img_path = EVIDENCE_DIR / img_filename
        cv2.imwrite(str(img_path), frame_img)

        # Validate intersection
        if not intersection_exists(conn, DEFAULT_INTERSECTION_ID):
            print(
                f"❌ Database Error: intersection_id={DEFAULT_INTERSECTION_ID} "
                f"does not exist in intersection table"
            )
            return

        # Plate FK handling
        raw_plate = plate.strip().upper() if plate else "UNKNOWN"
        safe_plate_for_fk = None

        if raw_plate != "UNKNOWN" and vehicle_exists(conn, raw_plate):
            safe_plate_for_fk = raw_plate

        # Decision logic
        status = "Pending"
        decision = "LoggedOnly"

        if v_class == "civilian_car":
            status = "AutoApproved"
            decision = "Auto"
        elif conf < CONFIDENCE_THRESHOLD:
            status = "Pending"
            decision = "Flagged"
        else:
            # In current schema this represents exempt / no fine
            status = "Rejected"
            decision = "Auto"

        note = (
            f"Detected Class: {v_class}; OCR: {raw_plate}; "
            f"Stored Plate FK: {safe_plate_for_fk if safe_plate_for_fk else 'NULL'}"
        )

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
                safe_plate_for_fk,
                DEFAULT_INTERSECTION_ID,
                timestamp,
                img_filename,
                video_filename,
                float(conf),
                decision,
                status,
                note,
            ),
        )

        new_violation_id = c.lastrowid

        sms_result = None
        if status == "AutoApproved":
            sms_result = process_sms_for_violation(
                conn=conn,
                violation_id=new_violation_id,
                user_id=None,
                note="Automatic SMS after AutoApproved detector decision",
            )

        conn.commit()

        print(
            f"💾 [DATABASE] Logged: V-{new_violation_id} | OCR={raw_plate} | "
            f"stored_plate={safe_plate_for_fk} | class={v_class} | "
            f"conf={conf:.1f}% | status={status} | video={video_filename}"
        )

        if sms_result:
            print(
                f"📨 Auto SMS result for V-{new_violation_id}: "
                f"{sms_result['status']} | {sms_result['message']}"
            )

    except sqlite3.OperationalError as e:
        print(f"❌ Database Operational Error: {e}")

    except sqlite3.IntegrityError as e:
        print(f"❌ Database Integrity Error: {e}")

    except Exception as e:
        print(f"❌ Database Error: {e}")

    finally:
        if conn is not None:
            conn.close()


# =========================================================
# AI HELPERS
# =========================================================
def load_models():
    print("Initializing ITMS Edge AI...")

    print("... Loading YOLOv8 ...")
    yolo_model = YOLO("yolov8n.pt")

    print("... Loading Custom Exemption CNN ...")
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"{MODEL_PATH} not found")

    cnn_model = tf.keras.models.load_model(MODEL_PATH)

    print("... Loading OCR Engine ...")
    reader = easyocr.Reader(["en"], gpu=False)

    return yolo_model, cnn_model, reader


def extract_plate_text(reader, car_crop):
    plate_text = "UNKNOWN"
    try:
        ocr_res = reader.readtext(car_crop)
        if ocr_res:
            plate_text = normalize_plate_text(ocr_res[0][1])
    except Exception:
        pass
    return plate_text


def classify_vehicle(cnn_model, car_crop):
    img_resized = cv2.resize(car_crop, (150, 150))
    img_array = tf.expand_dims(img_resized / 255.0, 0)

    preds = cnn_model.predict(img_array, verbose=0)
    score = tf.nn.softmax(preds[0]).numpy()

    pred_index = int(np.argmax(score))
    pred_class = CNN_CLASSES[pred_index]
    confidence = float(100 * np.max(score))

    return pred_class, confidence


# =========================================================
# MAIN
# =========================================================
def main():
    ensure_directories()

    ffmpeg_ok = ffmpeg_available()
    if ffmpeg_ok:
        print("✅ FFmpeg detected. Browser-friendly MP4 conversion enabled.")
    else:
        print("⚠️ FFmpeg not found. Videos will still be saved, but browser playback may fail.")

    try:
        yolo_model, cnn_model, reader = load_models()
    except Exception as e:
        print(f"❌ Failed to load models: {e}")
        return

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        print(f"❌ ERROR: Could not open video source: {VIDEO_SOURCE}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 1:
        fps = 20.0

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    line_y = int(height * 0.7)
    pre_event_frames = int(PRE_EVENT_SECONDS * fps)
    post_event_frames = int(POST_EVENT_SECONDS * fps)

    frame_buffer = deque(maxlen=pre_event_frames)
    pending_events = []
    recent_trigger_times = {}

    print("✅ System Online. Processing Video...")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        raw_frame = frame.copy()
        now = time.time()

        # -------------------------------------------------
        # 1. Continue recording pending events
        # -------------------------------------------------
        finished_events = []

        for event in pending_events:
            event["frames"].append(raw_frame.copy())
            event["remaining_frames"] -= 1

            if event["remaining_frames"] <= 0:
                finished_events.append(event)

        for event in finished_events:
            pending_events.remove(event)

            raw_video_filename = f"violation_{event['event_id']}_raw.avi"
            raw_video_path = EVIDENCE_DIR / raw_video_filename

            final_video_filename = f"violation_{event['event_id']}.mp4"
            final_video_path = EVIDENCE_DIR / final_video_filename

            saved = save_video_clip(event["frames"], raw_video_path, fps)

            video_filename_to_store = None

            if not saved:
                print("❌ Could not save raw AVI video clip.")
            else:
                if ffmpeg_ok:
                    converted = convert_to_browser_mp4(raw_video_path, final_video_path)
                    if converted:
                        video_filename_to_store = final_video_filename

                        try:
                            os.remove(raw_video_path)
                            print(f"🧹 Removed raw file: {raw_video_filename}")
                        except Exception as e:
                            print(f"⚠️ Could not remove raw AVI: {e}")
                    else:
                        print("⚠️ Conversion failed. Raw AVI will be kept.")
                        video_filename_to_store = raw_video_filename
                else:
                    print("⚠️ FFmpeg unavailable. Storing raw AVI only.")
                    video_filename_to_store = raw_video_filename

            log_violation(
                plate=event["plate"],
                v_class=event["pred_class"],
                conf=event["confidence"],
                frame_img=event["snapshot"],
                video_filename=video_filename_to_store,
            )

        # -------------------------------------------------
        # 2. Cleanup expired cooldown keys
        # -------------------------------------------------
        expired_keys = [
            key for key, ts in recent_trigger_times.items()
            if now - ts > TRIGGER_COOLDOWN_SECONDS
        ]
        for key in expired_keys:
            del recent_trigger_times[key]

        # -------------------------------------------------
        # 3. Draw enforcement line
        # -------------------------------------------------
        cv2.line(frame, (0, line_y), (width, line_y), (0, 0, 255), 3)
        cv2.putText(
            frame,
            "ENFORCEMENT ZONE",
            (10, line_y - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
        )

        # -------------------------------------------------
        # 4. YOLO detection
        # -------------------------------------------------
        results = yolo_model(frame, verbose=False)

        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cls = int(box.cls[0])

            # YOLO classes of interest: car, motorcycle, bus, truck
            if cls not in [2, 3, 5, 7]:
                continue

            # Trigger when the bottom of the vehicle crosses the line
            if not (y2 > line_y and y2 < line_y + 10):
                continue

            car_crop = raw_frame[y1:y2, x1:x2]
            if car_crop.size == 0:
                continue

            pred_class, confidence = classify_vehicle(cnn_model, car_crop)
            plate_text = extract_plate_text(reader, car_crop)

            # Deduplicate repeated triggers nearby
            center_x_bucket = ((x1 + x2) // 2) // 80
            center_y_bucket = ((y1 + y2) // 2) // 80
            trigger_key = f"{plate_text}_{pred_class}_{center_x_bucket}_{center_y_bucket}"

            if trigger_key in recent_trigger_times:
                continue

            recent_trigger_times[trigger_key] = now

            # Visual feedback
            color = (0, 0, 255)
            if pred_class != "civilian_car":
                color = (0, 255, 0)

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            cv2.putText(
                frame,
                f"{pred_class.upper()} {confidence:.1f}%",
                (x1, max(20, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
            )

            event_id = int(time.time() * 1000)

            pending_events.append(
                {
                    "event_id": event_id,
                    "frames": list(frame_buffer) + [raw_frame.copy()],
                    "remaining_frames": post_event_frames,
                    "snapshot": car_crop.copy(),
                    "plate": plate_text,
                    "pred_class": pred_class,
                    "confidence": confidence,
                }
            )

            print(
                f"🎥 Triggered evidence capture: plate={plate_text} | "
                f"class={pred_class} | conf={confidence:.1f}%"
            )

        # -------------------------------------------------
        # 5. Add current frame to rolling pre-event buffer
        # -------------------------------------------------
        frame_buffer.append(raw_frame.copy())

        cv2.imshow("ITMS Camera Feed", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("🛑 System stopped.")


if __name__ == "__main__":
    main()