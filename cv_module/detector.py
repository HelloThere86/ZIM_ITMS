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
VIDEO_SOURCE = "test_traffic.mp4"
MODEL_PATH = "zimbabwe_traffic_model.h5"

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

DB_PATH = PROJECT_ROOT / "database" / "itms_production.db"
EVIDENCE_DIR = PROJECT_ROOT / "dashboard" / "evidence"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Optional import for SMS
try:
    from api.sms_service import process_sms_for_violation
except ImportError:
    process_sms_for_violation = None

from api.runtime_config import get_runtime_config

DEFAULT_INTERSECTION_ID = 1
TRIGGER_COOLDOWN_SECONDS = 2.5
CNN_CLASSES = ["ambulance", "civilian_car", "fire_truck", "police_car"]


# =========================================================
# HELPER FUNCTIONS
# =========================================================
def ensure_directories():
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

def ffmpeg_available():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

def save_video_clip(frames, output_path, fps):
    if not frames:
        return False
    height, width, _ = frames[0].shape
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (width, height)
    )
    if not writer.isOpened():
        return False
    for frame in frames:
        writer.write(frame)
    writer.release()
    return output_path.exists() and output_path.stat().st_size > 0

def convert_to_browser_mp4(input_path, output_path):
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(input_path), "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path),
        ], check=True, capture_output=True)
        return output_path.exists() and output_path.stat().st_size > 0
    except Exception:
        return False

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def vehicle_exists(conn, plate):
    c = conn.cursor()
    c.execute("SELECT 1 FROM vehicle WHERE plate_number = ? LIMIT 1", (plate,))
    return c.fetchone() is not None

def normalize_plate_text(plate):
    return plate.upper().strip().replace(" ", "") if plate else "UNKNOWN"

def log_violation(plate, v_class, conf, frame_img, video_filename):
    """Logs violation to SQLite using runtime config values."""
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()

        runtime_config = get_runtime_config()
        jpeg_quality = runtime_config["jpeg_quality"]
        auto_flag_threshold = runtime_config["auto_flag_threshold"]
        review_threshold = runtime_config["review_threshold"]

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        unique_id = int(time.time() * 1000)

        img_filename = f"violation_{unique_id}.jpg"
        img_path = EVIDENCE_DIR / img_filename

        cv2.imwrite(
            str(img_path),
            frame_img,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)]
        )

        raw_plate = normalize_plate_text(plate)
        safe_plate = raw_plate if (raw_plate != "UNKNOWN" and vehicle_exists(conn, raw_plate)) else None

        # Config-driven decision logic
        if v_class != "civilian_car":
            status = "Rejected"
            decision = "Auto"
        elif conf >= auto_flag_threshold:
            status = "AutoApproved"
            decision = "Auto"
        elif conf >= review_threshold:
            status = "Pending"
            decision = "Flagged"
        else:
            status = "Rejected"
            decision = "Auto"

        note = (
            f"Detected Class: {v_class}; OCR: {raw_plate}; "
            f"AutoFlagThreshold: {auto_flag_threshold}; "
            f"ReviewThreshold: {review_threshold}; "
            f"ImageQuality: {runtime_config['image_quality']}"
        )

        c.execute("""
            INSERT INTO violation (
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
        """, (
            safe_plate,
            DEFAULT_INTERSECTION_ID,
            timestamp,
            img_filename,
            video_filename,
            float(conf),
            decision,
            status,
            note
        ))

        new_violation_id = c.lastrowid
        conn.commit()
        print(
            f"💾 [DATABASE] Violation V-{new_violation_id} logged locally. "
            f"Status: {status} | "
            f"JPEG={jpeg_quality} | "
            f"AutoFlag={auto_flag_threshold} | "
            f"Review={review_threshold}"
        )

    except Exception as e:
        print(f"❌ Database Error: {e}")
    finally:
        if conn:
            conn.close()

def load_models():
    print("Initializing ITMS Edge AI...")
    yolo_model = YOLO("yolov8n.pt")
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(MODEL_PATH)
    cnn_model = tf.keras.models.load_model(MODEL_PATH)
    reader = easyocr.Reader(["en"], gpu=False)
    return yolo_model, cnn_model, reader

def classify_vehicle(cnn_model, car_crop):
    img_resized = cv2.resize(car_crop, (150, 150))
    img_array = tf.expand_dims(img_resized / 255.0, 0)
    preds = cnn_model.predict(img_array, verbose=0)
    score = tf.nn.softmax(preds[0]).numpy()
    pred_index = int(np.argmax(score))
    return CNN_CLASSES[pred_index], float(100 * np.max(score))


# =========================================================
# MAIN
# =========================================================
def main():
    ensure_directories()
    ffmpeg_ok = ffmpeg_available()
    yolo_model, cnn_model, reader = load_models()
    cap = cv2.VideoCapture(VIDEO_SOURCE)

    if not cap.isOpened():
        print(f"❌ ERROR: Could not open video: {VIDEO_SOURCE}")
        return

    runtime_config = get_runtime_config()

    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    line_y = int(height * 0.7)

    clip_duration_seconds = runtime_config["clip_duration_seconds"]
    pre_event_seconds = max(1, clip_duration_seconds // 2)
    post_event_seconds = max(1, clip_duration_seconds - pre_event_seconds)

    pre_event_frames = int(pre_event_seconds * fps)
    post_event_frames = int(post_event_seconds * fps)

    frame_buffer = deque(maxlen=pre_event_frames)
    pending_events = []
    recent_triggers = {}
    light_state = "RED"

    print(
        "\n" + "=" * 40 +
        f"\n✅ System Online. Processing Video...\n"
        f"   Press 'G' for GREEN | 'R' for RED | 'Q' to Quit\n"
        f"   Clip={runtime_config['clip_duration_label']} "
        f"| ImageQuality={runtime_config['image_quality']} "
        f"| AutoFlagThreshold={runtime_config['auto_flag_threshold']} "
        f"| ReviewThreshold={runtime_config['review_threshold']}\n" +
        "=" * 40 + "\n"
    )

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        raw_frame = frame.copy()
        now = time.time()

        # 1. Process Finished Video Captures
        finished_events = [e for e in pending_events if e.get("remaining_frames", 0) <= 0]
        for event in finished_events:
            pending_events.remove(event)
            raw_vid = EVIDENCE_DIR / f"violation_{event['id']}_raw.avi"
            final_vid = EVIDENCE_DIR / f"violation_{event['id']}.mp4"

            if save_video_clip(event["frames"], raw_vid, fps):
                vid_to_store = raw_vid.name
                if ffmpeg_ok and convert_to_browser_mp4(raw_vid, final_vid):
                    vid_to_store = final_vid.name
                    try:
                        os.remove(raw_vid)
                    except Exception:
                        pass

                log_violation(
                    event["plate"],
                    event["class"],
                    event["conf"],
                    event["snapshot"],
                    vid_to_store
                )

        for event in pending_events:
            event["frames"].append(raw_frame.copy())
            event["remaining_frames"] -= 1

        # 2. Draw UI
        line_color = (0, 0, 255) if light_state == "RED" else (0, 255, 0)
        line_text = f"{light_state} LIGHT: ENFORCEMENT {'ACTIVE' if light_state == 'RED' else 'PAUSED'}"
        cv2.line(frame, (0, line_y), (width, line_y), line_color, 3)
        cv2.putText(frame, line_text, (10, line_y - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, line_color, 2)

        # 3. Detect and Trigger
        if light_state == "RED":
            results = yolo_model(frame, verbose=False)
            for box in results[0].boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cls = int(box.cls[0])

                if cls in [2, 3, 5, 7] and (y2 > line_y and y2 < line_y + 15):
                    car_crop = raw_frame[y1:y2, x1:x2]
                    if car_crop.size == 0:
                        continue

                    pred_class, confidence = classify_vehicle(cnn_model, car_crop)

                    plate_text = "UNKNOWN"
                    try:
                        ocr_res = reader.readtext(car_crop, detail=0, paragraph=False)
                        if ocr_res:
                            plate_text = normalize_plate_text(ocr_res[0])
                    except Exception:
                        pass

                    trigger_key = f"{plate_text}_{pred_class}_{x1//80}"
                    if trigger_key in recent_triggers and (now - recent_triggers[trigger_key]) < TRIGGER_COOLDOWN_SECONDS:
                        continue
                    recent_triggers[trigger_key] = now

                    color = (0, 0, 255) if pred_class == "civilian_car" else (0, 255, 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                    cv2.putText(
                        frame,
                        f"{pred_class.upper()} {confidence:.0f}%",
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        color,
                        2
                    )

                    pending_events.append({
                        "id": int(now * 1000),
                        "frames": list(frame_buffer) + [raw_frame.copy()],
                        "remaining_frames": post_event_frames,
                        "snapshot": car_crop.copy(),
                        "plate": plate_text,
                        "class": pred_class,
                        "conf": confidence
                    })
                    print(f"🎥 Violation Triggered: {pred_class} ({confidence:.1f}%)")

        frame_buffer.append(raw_frame.copy())

        cv2.imshow("ITMS Edge Node Feed", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("g"):
            light_state = "GREEN"
        elif key == ord("r"):
            light_state = "RED"

    cap.release()
    cv2.destroyAllWindows()
    print("🛑 System stopped.")

if __name__ == "__main__":
    main()