import cv2
import numpy as np
import easyocr
import sqlite3
import os
import sys
import re
import time
import subprocess
from datetime import datetime
from collections import deque, defaultdict
from pathlib import Path
from ultralytics import YOLO
import tensorflow as tf

# =========================================================
# CONFIGURATION
# =========================================================
VIDEO_SOURCE = "Test_traffic_OCR.mp4"
MODEL_PATH = "zimbabwe_traffic_model.h5"

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

DB_PATH = PROJECT_ROOT / "database" / "itms_production.db"
EVIDENCE_DIR = PROJECT_ROOT / "dashboard" / "evidence"

DEBUG_ANPR = False
DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 720

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from api.sms_service import process_sms_for_violation
    SMS_AVAILABLE = True
except ImportError:
    process_sms_for_violation = None
    SMS_AVAILABLE = False

from api.runtime_config import get_runtime_config

DEFAULT_INTERSECTION_ID = 1
CNN_CLASSES = ["ambulance", "civilian_car", "fire_truck", "police_car"]
VALID_STATUSES = {"Pending", "Approved", "Rejected", "AutoApproved", "Paid"}
UNKNOWN_PLATE_SENTINEL = "UNKNOWN-UNREGISTERED"

# =========================================================
# DEMO / TRACKING SETTINGS
# =========================================================
TRIGGER_BAND_PX = 35
LINE_CROSS_MARGIN = 6

DETECT_EVERY_N_FRAMES = 2
OCR_NEAR_LINE_EVERY_N_FRAMES = 2
OCR_POST_CROSS_EVERY_N_FRAMES = 1
MAX_ACTIVE_OCR_TRACKS = 4

TRACK_MAX_AGE_FRAMES = 30
TRACK_MATCH_DISTANCE = 110
POST_CROSS_OCR_FRAMES = 130

GLOBAL_PLATE_DEDUP_SECONDS = 45.0
GLOBAL_BOX_DEDUP_SECONDS = 10.0
GLOBAL_CROSSING_BOX_DEDUP_SECONDS = 4.0

# =========================================================
# OCR / UK PLATE SETTINGS
# =========================================================
UK_PLATE_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{3}$")

MIN_PLATE_REGION_WIDTH = 70
MIN_PLATE_REGION_HEIGHT = 14
MIN_PLATE_SHARPNESS = 10.0

MIN_SINGLE_READ_CONF = 55.0
MIN_CHAR_TOTAL_WEIGHT = 145.0
MIN_FULL_PLATE_REPEAT = 2


# =========================================================
# PLATE HELPERS
# =========================================================
def normalize_plate(plate: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", plate.upper()) if plate else "UNKNOWN"


def is_exact_uk_plate(text: str) -> bool:
    if not text or text == "UNKNOWN":
        return False
    return UK_PLATE_RE.match(normalize_plate(text)) is not None


def normalize_uk_candidate(raw: str) -> str | None:
    cleaned = normalize_plate(raw)
    if not cleaned:
        return None

    candidates = []
    if len(cleaned) >= 7:
        for i in range(0, len(cleaned) - 6):
            candidates.append(cleaned[i:i + 7])
    else:
        return None

    digit_map = {
        "O": "0", "Q": "0", "D": "0",
        "I": "1", "L": "1", "T": "1",
        "Z": "2",
        "S": "5",
        "B": "8",
        "G": "6",
    }

    letter_map = {
        "0": "O",
        "1": "I",
        "2": "Z",
        "5": "S",
        "6": "G",
        "8": "B",
    }

    best = None
    best_score = -1e9

    for cand in candidates:
        if len(cand) != 7:
            continue

        chars = list(cand)
        score = 0.0
        valid = True

        # UK format: AA00AAA
        for pos in [0, 1, 4, 5, 6]:
            c = chars[pos]
            if c.isalpha():
                score += 2.0
            elif c in letter_map:
                chars[pos] = letter_map[c]
                score += 1.0
            else:
                valid = False
                break

        if not valid:
            continue

        for pos in [2, 3]:
            c = chars[pos]
            if c.isdigit():
                score += 2.0
            elif c in digit_map:
                chars[pos] = digit_map[c]
                score += 1.0
            else:
                valid = False
                break

        if not valid:
            continue

        fixed = "".join(chars)
        if not UK_PLATE_RE.match(fixed):
            continue

        if fixed == cand:
            score += 5.0

        if score > best_score:
            best_score = score
            best = fixed

    return best


# =========================================================
# CHARACTER-LEVEL UK VOTER
# =========================================================
class UKCharPlateVoter:
    def __init__(self):
        self.full_counts = defaultdict(int)
        self.full_weights = defaultdict(float)
        self.full_best_conf = defaultdict(float)
        self.char_weights = [defaultdict(float) for _ in range(7)]
        self.total_reads = 0

    def add(self, plate: str, conf: float, quality: float = 0.0):
        candidate = normalize_uk_candidate(plate)
        if candidate is None:
            return

        weight = max(float(conf), 1.0) + min(float(quality) / 8.0, 25.0)

        self.total_reads += 1
        self.full_counts[candidate] += 1
        self.full_weights[candidate] += weight
        self.full_best_conf[candidate] = max(self.full_best_conf[candidate], float(conf))

        for i, ch in enumerate(candidate):
            self.char_weights[i][ch] += weight

    def best_full(self):
        if not self.full_weights:
            return None, 0, 0.0, 0.0

        best_plate = None
        best_weight = -1.0
        best_count = 0
        best_conf = 0.0

        for plate, weight in self.full_weights.items():
            count = self.full_counts[plate]
            conf = self.full_best_conf[plate]

            if (
                weight > best_weight
                or (abs(weight - best_weight) < 1e-6 and count > best_count)
                or (abs(weight - best_weight) < 1e-6 and count == best_count and conf > best_conf)
            ):
                best_plate = plate
                best_weight = weight
                best_count = count
                best_conf = conf

        return best_plate, best_count, best_weight, best_conf

    def best_char_consensus(self):
        chars = []
        total_weight = 0.0
        min_position_weight = float("inf")

        for position_weights in self.char_weights:
            if not position_weights:
                return None, 0.0, 0.0

            ch, weight = max(position_weights.items(), key=lambda item: item[1])
            chars.append(ch)
            total_weight += weight
            min_position_weight = min(min_position_weight, weight)

        plate = "".join(chars)

        if not UK_PLATE_RE.match(plate):
            return None, total_weight, min_position_weight

        return plate, total_weight, min_position_weight

    def best(self):
        full_plate, full_count, full_weight, full_conf = self.best_full()
        char_plate, char_weight, min_pos_weight = self.best_char_consensus()

        if (
            full_plate is not None
            and full_count >= MIN_FULL_PLATE_REPEAT
            and full_weight >= MIN_CHAR_TOTAL_WEIGHT * 0.55
        ):
            return full_plate, "full_vote", full_count, full_weight, full_conf

        if char_plate is not None and char_weight >= MIN_CHAR_TOTAL_WEIGHT and min_pos_weight >= 12.0:
            return char_plate, "char_vote", full_count, char_weight, full_conf

        if full_plate is not None and full_conf >= MIN_SINGLE_READ_CONF:
            return full_plate, "best_single", full_count, full_weight, full_conf

        return None, "none", 0, 0.0, 0.0


# =========================================================
# DEDUP HELPERS
# =========================================================
def similar_box(box_a, box_b, dx_thresh=90, dy_thresh=90, dw_thresh=70, dh_thresh=70):
    x1, y1, x2, y2 = box_a
    a1, b1, a2, b2 = box_b

    cx1 = (x1 + x2) / 2.0
    cy1 = (y1 + y2) / 2.0
    w1 = x2 - x1
    h1 = y2 - y1

    cx2 = (a1 + a2) / 2.0
    cy2 = (b1 + b2) / 2.0
    w2 = a2 - a1
    h2 = b2 - b1

    return (
        abs(cx1 - cx2) < dx_thresh
        and abs(cy1 - cy2) < dy_thresh
        and abs(w1 - w2) < dw_thresh
        and abs(h1 - h2) < dh_thresh
    )


def is_duplicate_global_event(recent_events, plate, pred_class, bbox, now):
    recent_events[:] = [
        e for e in recent_events
        if now - e["time"] <= max(GLOBAL_PLATE_DEDUP_SECONDS, GLOBAL_BOX_DEDUP_SECONDS)
    ]

    for e in recent_events:
        if e["class"] != pred_class:
            continue

        if (
            plate != "UNKNOWN"
            and e["plate"] != "UNKNOWN"
            and plate == e["plate"]
            and now - e["time"] <= GLOBAL_PLATE_DEDUP_SECONDS
        ):
            return True

        if (
            plate == "UNKNOWN"
            and similar_box(bbox, e["bbox"])
            and now - e["time"] <= GLOBAL_BOX_DEDUP_SECONDS
        ):
            return True

    return False


def is_duplicate_crossing(recent_crossings, pred_class, bbox, now):
    recent_crossings[:] = [
        e for e in recent_crossings
        if now - e["time"] <= GLOBAL_CROSSING_BOX_DEDUP_SECONDS
    ]

    for e in recent_crossings:
        if e["class"] != pred_class:
            continue

        if similar_box(bbox, e["bbox"], dx_thresh=100, dy_thresh=100, dw_thresh=80, dh_thresh=80):
            return True

    return False


# =========================================================
# TRACKING
# =========================================================
class Track:
    def __init__(self, track_id: int, bbox, frame_img: np.ndarray):
        x1, y1, x2, y2 = bbox

        self.id = track_id
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

        self.cx = (x1 + x2) / 2.0
        self.cy = (y1 + y2) / 2.0
        self.w = x2 - x1
        self.h = y2 - y1

        self.missed = 0
        self.finalized = False

        self.crossed_line = False
        self.crossed_at_frame = None
        self.post_cross_frames_left = 0

        self.event_id = None
        self.event_created = False

        self.voter = UKCharPlateVoter()
        self.best_plate_seen = "UNKNOWN"
        self.best_plate_conf = 0.0

        self.pred_class = None
        self.class_conf = 0.0
        self.last_cls_update_frame = 0

        self.snapshot = frame_img[y1:y2, x1:x2].copy() if y2 > y1 and x2 > x1 else None

    def bbox(self):
        return int(self.x1), int(self.y1), int(self.x2), int(self.y2)

    def update(self, bbox, frame_img: np.ndarray):
        x1, y1, x2, y2 = bbox

        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

        self.cx = (x1 + x2) / 2.0
        self.cy = (y1 + y2) / 2.0
        self.w = x2 - x1
        self.h = y2 - y1
        self.missed = 0

        crop = frame_img[y1:y2, x1:x2]
        if crop.size > 0:
            self.snapshot = crop.copy()

    def center_distance(self, bbox) -> float:
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        return float(np.hypot(self.cx - cx, self.cy - cy))


class VehicleTracker:
    def __init__(self):
        self.tracks = {}
        self.next_id = 1

    def update(self, detections, frame_img: np.ndarray):
        assigned_tracks = set()

        for bbox in detections:
            best_track_id = None
            best_dist = 1e9

            for track_id, track in self.tracks.items():
                if track.finalized:
                    continue

                dist = track.center_distance(bbox)
                if dist < TRACK_MATCH_DISTANCE and dist < best_dist:
                    best_dist = dist
                    best_track_id = track_id

            if best_track_id is not None:
                self.tracks[best_track_id].update(bbox, frame_img)
                assigned_tracks.add(best_track_id)
            else:
                track = Track(self.next_id, bbox, frame_img)
                self.tracks[self.next_id] = track
                assigned_tracks.add(self.next_id)
                self.next_id += 1

        for track_id, track in list(self.tracks.items()):
            if track_id not in assigned_tracks:
                track.missed += 1

            if track.missed > TRACK_MAX_AGE_FRAMES:
                track.finalized = True

        return self.tracks


# =========================================================
# OCR / PLATE REGION
# =========================================================
def crop_quality_score(img: np.ndarray) -> float:
    if img is None or img.size == 0:
        return 0.0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
    h, w = gray.shape[:2]

    size_score = min(w / 120.0, 1.0) * 40.0 + min(h / 28.0, 1.0) * 20.0
    sharp_score = min(sharpness / 80.0, 1.0) * 40.0

    return size_score + sharp_score


def preprocess_plate(img: np.ndarray):
    h, w = img.shape[:2]

    if w < 280 and w > 0:
        scale = 280 / w
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    variants = []

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    sharp_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])

    v1 = clahe.apply(gray)
    v1 = cv2.filter2D(v1, -1, sharp_kernel)
    variants.append(cv2.cvtColor(v1, cv2.COLOR_GRAY2BGR))

    _, v2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(cv2.cvtColor(v2, cv2.COLOR_GRAY2BGR))

    v3 = cv2.bilateralFilter(gray, 7, 50, 50)
    v3 = cv2.filter2D(v3, -1, sharp_kernel)
    variants.append(cv2.cvtColor(v3, cv2.COLOR_GRAY2BGR))

    variants.append(img)
    return variants


def detect_plate_region(car_crop: np.ndarray):
    h_car, w_car = car_crop.shape[:2]

    if h_car == 0 or w_car == 0:
        return car_crop, "invalid"

    gray = cv2.cvtColor(car_crop, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    sx = cv2.Sobel(blur, cv2.CV_64F, 1, 0, ksize=3)
    sy = cv2.Sobel(blur, cv2.CV_64F, 0, 1, ksize=3)
    edges = cv2.convertScaleAbs(np.sqrt(sx**2 + sy**2))

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    _, thresh = cv2.threshold(closed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_crop = None
    best_score = -1.0

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)

        if h == 0:
            continue

        aspect = w / h
        area = w * h

        if not (
            2.0 <= aspect <= 7.8
            and 0.10 <= w / w_car <= 0.88
            and 0.03 <= h / h_car <= 0.32
            and y > h_car * 0.22
            and area > 80
        ):
            continue

        crop = car_crop[y:y + h, x:x + w]
        quality = crop_quality_score(crop)

        if quality > best_score:
            best_score = quality
            best_crop = crop

    if best_crop is not None and best_crop.size > 0:
        return best_crop, "contour"

    mid_lower = car_crop[
        int(h_car * 0.50):int(h_car * 0.84),
        int(w_car * 0.08):int(w_car * 0.92),
    ]

    if mid_lower.size > 0:
        return mid_lower, "mid_lower_band"

    bottom = car_crop[int(h_car * 0.58):, :]
    if bottom.size > 0:
        return bottom, "bottom_band"

    return car_crop, "full_crop"


def read_plate(reader: easyocr.Reader, car_crop: np.ndarray, debug_path: Path | None = None):
    plate_region, method = detect_plate_region(car_crop)

    if plate_region is None or plate_region.size == 0:
        return "UNKNOWN", 0.0, 0.0

    h, w = plate_region.shape[:2]
    sharpness = cv2.Laplacian(cv2.cvtColor(plate_region, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
    quality = crop_quality_score(plate_region)

    if w < MIN_PLATE_REGION_WIDTH or h < MIN_PLATE_REGION_HEIGHT or sharpness < MIN_PLATE_SHARPNESS:
        return "UNKNOWN", 0.0, quality

    variants = preprocess_plate(plate_region)

    if debug_path:
        debug_path.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        cv2.imwrite(str(debug_path / f"{stamp}_car.jpg"), car_crop)
        cv2.imwrite(str(debug_path / f"{stamp}_plate_{method}.jpg"), plate_region)

    best_text = "UNKNOWN"
    best_conf = 0.0
    best_score = -1e9

    for variant in variants:
        try:
            results = reader.readtext(
                variant,
                detail=1,
                paragraph=False,
                allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                width_ths=0.7,
                text_threshold=0.30,
                low_text=0.20,
            )
        except Exception:
            continue

        if not results:
            continue

        combined_text = "".join(r[1] for r in results)
        combined_conf = float(np.mean([r[2] for r in results])) * 100.0

        candidate = normalize_uk_candidate(combined_text)
        if candidate is None:
            continue

        score = combined_conf + min(quality / 4.0, 25.0)

        if score > best_score:
            best_score = score
            best_conf = combined_conf
            best_text = candidate

    return best_text, best_conf, quality


# =========================================================
# MODELS
# =========================================================
def load_models():
    print("Initialising ITMS Edge AI...")

    yolo_model = YOLO("yolov8n.pt")

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(MODEL_PATH)

    cnn_model = tf.keras.models.load_model(MODEL_PATH)

    try:
        reader = easyocr.Reader(["en"], gpu=True)
    except Exception:
        print("⚠️ EasyOCR GPU init failed. Falling back to CPU.")
        reader = easyocr.Reader(["en"], gpu=False)

    return yolo_model, cnn_model, reader


def classify_vehicle(cnn_model, car_crop):
    img_arr = tf.expand_dims(cv2.resize(car_crop, (150, 150)) / 255.0, 0)
    score = tf.nn.softmax(cnn_model.predict(img_arr, verbose=0)[0]).numpy()
    idx = int(np.argmax(score))
    return CNN_CLASSES[idx], float(100 * np.max(score))


# =========================================================
# FILE / VIDEO HELPERS
# =========================================================
def ensure_directories():
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    if DEBUG_ANPR:
        (EVIDENCE_DIR / "debug_plates").mkdir(parents=True, exist_ok=True)


def ffmpeg_available():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def save_video_clip(frames, output_path, fps):
    if not frames:
        return False

    h, w, _ = frames[0].shape

    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (w, h),
    )

    if not writer.isOpened():
        return False

    for f in frames:
        writer.write(f)

    writer.release()
    return output_path.exists() and output_path.stat().st_size > 0


def convert_to_browser_mp4(input_path, output_path):
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )

        return output_path.exists() and output_path.stat().st_size > 0
    except Exception:
        return False


# =========================================================
# FINAL PLATE DECISION
# =========================================================
def choose_final_plate(track: Track):
    plate, method, count, weight, peak_conf = track.voter.best()

    if plate is not None and is_exact_uk_plate(plate):
        return plate

    if is_exact_uk_plate(track.best_plate_seen) and track.best_plate_conf >= MIN_SINGLE_READ_CONF:
        return track.best_plate_seen

    return "UNKNOWN"


# =========================================================
# DATABASE LOGGING
# =========================================================
def log_violation(plate, v_class, conf, frame_img, video_filename):
    conn = None

    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        c = conn.cursor()

        runtime_config = get_runtime_config()
        jpeg_quality = runtime_config["jpeg_quality"]
        auto_flag_threshold = runtime_config["auto_flag_threshold"]
        review_threshold = runtime_config["review_threshold"]

        row = c.execute(
            "SELECT 1 FROM intersection WHERE intersection_id = ? LIMIT 1",
            (DEFAULT_INTERSECTION_ID,),
        ).fetchone()

        if row is None:
            print(f"❌ intersection_id={DEFAULT_INTERSECTION_ID} not found.")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        unique_id = int(time.time() * 1000)
        img_filename = f"violation_{unique_id}.jpg"

        cv2.imwrite(
            str(EVIDENCE_DIR / img_filename),
            frame_img,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
        )

        raw_plate = normalize_plate(plate)

        row = c.execute(
            "SELECT 1 FROM vehicle WHERE plate_number = ? LIMIT 1",
            (raw_plate,),
        ).fetchone()

        is_registered = row is not None

        if not is_registered:
            if raw_plate and raw_plate != "UNKNOWN":
                try:
                    c.execute(
                        "INSERT OR IGNORE INTO vehicle (plate_number, owner_id, is_exempt) VALUES (?, NULL, 0)",
                        (raw_plate,),
                    )
                    conn.commit()
                    safe_plate = raw_plate
                except Exception:
                    safe_plate = UNKNOWN_PLATE_SENTINEL
            else:
                c.execute(
                    "INSERT OR IGNORE INTO vehicle (plate_number, is_exempt) VALUES (?, 0)",
                    (UNKNOWN_PLATE_SENTINEL,),
                )
                conn.commit()
                safe_plate = UNKNOWN_PLATE_SENTINEL
        else:
            safe_plate = raw_plate

        note = (
            f"Detected Class: {v_class}; OCR Plate: {raw_plate}; "
            f"Registered: {is_registered}; "
            f"AutoFlagThreshold: {auto_flag_threshold}; "
            f"ReviewThreshold: {review_threshold}; "
            f"ImageQuality: {runtime_config['image_quality']}"
        )

        if raw_plate == "UNKNOWN":
            note += " [PLATE NOT LOCKED]"
        elif not is_registered:
            note += " [UNREGISTERED — pending manual review]"

        if v_class != "civilian_car":
            status, decision = "Rejected", "Auto"
        elif not is_registered:
            status, decision = "Pending", "Flagged"
        elif conf >= auto_flag_threshold:
            status, decision = "AutoApproved", "Auto"
        elif conf >= review_threshold:
            status, decision = "Pending", "Flagged"
        else:
            status, decision = "Rejected", "Auto"

        if status not in VALID_STATUSES:
            status = "Pending"

        c.execute(
            """
            INSERT INTO violation (
                plate_number, intersection_id, timestamp,
                image_path, video_path, confidence_score,
                decision_type, status, review_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                safe_plate,
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

        new_id = c.lastrowid
        conn.commit()

        print(
            f"💾 V-{new_id} | OCR: {raw_plate} → {safe_plate} | "
            f"Registered: {is_registered} | Status: {status}"
        )

        if SMS_AVAILABLE and is_registered and status in ("AutoApproved", "Pending"):
            try:
                result = process_sms_for_violation(conn, new_id)
                print(f"📱 SMS: {result.get('status')} → {result.get('recipientPhone')}")
            except Exception as sms_err:
                print(f"⚠️ SMS error: {sms_err}")

    except sqlite3.IntegrityError as e:
        print(f"❌ Integrity error: {e}")
    except Exception as e:
        print(f"❌ Database error: {e}")
    finally:
        if conn:
            conn.close()


def finalize_event(event, ffmpeg_ok, fps):
    raw_vid = EVIDENCE_DIR / f"violation_{event['id']}_raw.avi"
    final_vid = EVIDENCE_DIR / f"violation_{event['id']}.mp4"

    if save_video_clip(event["frames"], raw_vid, fps):
        vid_name = raw_vid.name

        if ffmpeg_ok and convert_to_browser_mp4(raw_vid, final_vid):
            vid_name = final_vid.name
            try:
                os.remove(raw_vid)
            except Exception:
                pass

        log_violation(
            event["plate"],
            event["class"],
            event["conf"],
            event["snapshot"],
            vid_name,
        )


# =========================================================
# MAIN
# =========================================================
def main():
    ensure_directories()

    ffmpeg_ok = ffmpeg_available()
    yolo_model, cnn_model, reader = load_models()
    cap = cv2.VideoCapture(VIDEO_SOURCE)

    if not cap.isOpened():
        print(f"❌ Could not open: {VIDEO_SOURCE}")
        return

    runtime_config = get_runtime_config()

    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    line_y = int(height * 0.7)

    pre_frames = int(max(1, runtime_config["clip_duration_seconds"] // 2) * fps)
    post_frames = int(max(1, runtime_config["clip_duration_seconds"] - runtime_config["clip_duration_seconds"] // 2) * fps)

    frame_index = 0
    frame_buffer = deque(maxlen=pre_frames)

    pending_events = []
    event_by_id = {}

    recent_events = []
    recent_crossings = []

    tracker = VehicleTracker()
    light_state = "RED"
    debug_dir = EVIDENCE_DIR / "debug_plates" if DEBUG_ANPR else None

    cached_detections = []
    tracks = {}

    print(f"📹 Video: {width}x{height} @ {fps:.1f}fps")

    cv2.namedWindow("ITMS Edge Node Feed", cv2.WINDOW_NORMAL)

    if DISPLAY_WIDTH and DISPLAY_HEIGHT:
        cv2.resizeWindow("ITMS Edge Node Feed", DISPLAY_WIDTH, DISPLAY_HEIGHT)

    print(
        f"\n{'=' * 72}\n"
        f"✅ Immediate Violation + UK Char Voting Mode | {VIDEO_SOURCE}\n"
        f"   G=GREEN | R=RED | Q=Quit\n"
        f"   Violation creation       : immediate on crossing\n"
        f"   Plate finalization       : UK char-level consensus\n"
        f"   Detection stride         : {DETECT_EVERY_N_FRAMES}\n"
        f"   Post-cross OCR frames    : {POST_CROSS_OCR_FRAMES}\n"
        f"   Max OCR tracks           : {MAX_ACTIVE_OCR_TRACKS}\n"
        f"{'=' * 72}\n"
    )

    while cap.isOpened():
        ret, frame = cap.read()

        if not ret:
            break

        frame_index += 1
        raw_frame = frame.copy()
        now = time.time()

        finished = [e for e in pending_events if e["remaining_frames"] <= 0]

        for event in finished:
            pending_events.remove(event)
            event_by_id.pop(event["id"], None)
            finalize_event(event, ffmpeg_ok, fps)

        for event in pending_events:
            event["frames"].append(raw_frame.copy())
            event["remaining_frames"] -= 1

        lc = (0, 0, 255) if light_state == "RED" else (0, 255, 0)

        cv2.line(frame, (0, line_y), (width, line_y), lc, 3)

        cv2.putText(
            frame,
            f"{light_state}: {'ACTIVE' if light_state == 'RED' else 'PAUSED'}",
            (10, line_y - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            lc,
            2,
        )

        detections = cached_detections

        if light_state == "RED" and frame_index % DETECT_EVERY_N_FRAMES == 0:
            detections = []

            results = yolo_model(frame, imgsz=640, verbose=False)

            for box in results[0].boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cls = int(box.cls[0])

                if cls in [2, 3, 5, 7]:
                    detections.append((x1, y1, x2, y2))

            cached_detections = detections

        tracks = tracker.update(detections, raw_frame)

        if light_state == "RED":
            for track in tracks.values():
                if track.finalized or track.snapshot is None:
                    continue

                x1, y1, x2, y2 = track.bbox()
                box_center_y = int(track.cy)
                crop = raw_frame[y1:y2, x1:x2]

                if crop.size > 0 and (track.pred_class is None or frame_index - track.last_cls_update_frame >= 8):
                    pred_class, class_conf = classify_vehicle(cnn_model, crop)
                    track.pred_class = pred_class
                    track.class_conf = class_conf
                    track.last_cls_update_frame = frame_index

                if not track.crossed_line and box_center_y >= (line_y - LINE_CROSS_MARGIN):
                    pred_class = track.pred_class if track.pred_class else "civilian_car"

                    if not is_duplicate_crossing(recent_crossings, pred_class, track.bbox(), now):
                        track.crossed_line = True
                        track.crossed_at_frame = frame_index
                        track.post_cross_frames_left = POST_CROSS_OCR_FRAMES

                        event_id = int(now * 1000) + track.id

                        event = {
                            "id": event_id,
                            "track_id": track.id,
                            "frames": list(frame_buffer) + [raw_frame.copy()],
                            "remaining_frames": post_frames,
                            "snapshot": track.snapshot.copy(),
                            "plate": "UNKNOWN",
                            "class": pred_class,
                            "conf": track.class_conf if track.class_conf else 97.0,
                            "created_time": now,
                        }

                        pending_events.append(event)
                        event_by_id[event_id] = event

                        track.event_id = event_id
                        track.event_created = True

                        recent_crossings.append(
                            {
                                "time": now,
                                "class": pred_class,
                                "bbox": track.bbox(),
                            }
                        )

                        print(f"🚨 Crossing detected -> Event created for Track {track.id}")
                    else:
                        track.crossed_line = True
                        track.crossed_at_frame = frame_index
                        track.post_cross_frames_left = POST_CROSS_OCR_FRAMES

            active_tracks = []

            for track in tracks.values():
                if track.finalized or track.snapshot is None:
                    continue

                box_center_y = int(track.cy)
                near_line = abs(box_center_y - line_y) <= TRIGGER_BAND_PX

                if track.crossed_line and track.post_cross_frames_left > 0:
                    active_tracks.append(track)
                elif near_line:
                    active_tracks.append(track)

            active_tracks.sort(
                key=lambda t: (
                    0 if t.crossed_line else 1,
                    abs(int(t.cy) - line_y),
                    t.missed,
                )
            )

            active_tracks = active_tracks[:MAX_ACTIVE_OCR_TRACKS]

            for track in active_tracks:
                x1, y1, x2, y2 = track.bbox()
                crop = raw_frame[y1:y2, x1:x2]

                if crop.size == 0:
                    continue

                ocr_stride = OCR_POST_CROSS_EVERY_N_FRAMES if track.crossed_line else OCR_NEAR_LINE_EVERY_N_FRAMES

                if frame_index % ocr_stride == 0:
                    plate_this_frame, plate_conf, plate_quality = read_plate(reader, crop, debug_dir)

                    track.voter.add(plate_this_frame, plate_conf, plate_quality)

                    if is_exact_uk_plate(plate_this_frame) and plate_conf > track.best_plate_conf:
                        track.best_plate_conf = plate_conf
                        track.best_plate_seen = normalize_plate(plate_this_frame)

                    if track.event_created and track.event_id in event_by_id:
                        event = event_by_id[track.event_id]
                        best_now = choose_final_plate(track)

                        event["plate"] = best_now
                        event["class"] = track.pred_class if track.pred_class else event["class"]
                        event["conf"] = track.class_conf if track.class_conf else event["conf"]

                        if track.snapshot is not None:
                            event["snapshot"] = track.snapshot.copy()

                    voted_plate, method, count, weight, peak_conf = track.voter.best()
                    best_candidate = voted_plate or track.best_plate_seen

                    print(
                        f"🔍 Track {track.id}: '{plate_this_frame}' "
                        f"(ocr={plate_conf:.1f}%, q={plate_quality:.1f}) | "
                        f"best: {best_candidate if best_candidate != 'UNKNOWN' else 'UNKNOWN'}"
                    )

                if track.crossed_line and track.post_cross_frames_left > 0:
                    track.post_cross_frames_left -= 1

                color = (0, 0, 255) if track.pred_class == "civilian_car" else (0, 255, 0)

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                voted_plate, method, count, weight, peak_conf = track.voter.best()
                best_candidate = voted_plate or track.best_plate_seen

                label_text = f"T{track.id}"

                if track.pred_class:
                    label_text += f" {track.pred_class} {track.class_conf:.0f}%"

                if best_candidate and best_candidate != "UNKNOWN":
                    label_text += f" | {best_candidate}"

                cv2.putText(
                    frame,
                    label_text,
                    (x1, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    color,
                    2,
                )

            for track in tracks.values():
                if not track.crossed_line or track.finalized:
                    continue

                if track.post_cross_frames_left <= 0:
                    if track.event_created and track.event_id in event_by_id:
                        event = event_by_id[track.event_id]

                        final_plate = choose_final_plate(track)
                        pred_class = track.pred_class if track.pred_class else event["class"]

                        if not is_duplicate_global_event(
                            recent_events,
                            final_plate,
                            pred_class,
                            track.bbox(),
                            now,
                        ):
                            event["plate"] = final_plate
                            event["class"] = pred_class
                            event["conf"] = track.class_conf if track.class_conf else event["conf"]

                            recent_events.append(
                                {
                                    "time": now,
                                    "plate": final_plate,
                                    "class": pred_class,
                                    "bbox": track.bbox(),
                                }
                            )

                        track.finalized = True

        frame_buffer.append(raw_frame.copy())

        cv2.imshow("ITMS Edge Node Feed", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break
        elif key == ord("g"):
            light_state = "GREEN"
        elif key == ord("r"):
            light_state = "RED"

    for track in tracks.values():
        if track.crossed_line and track.event_created and track.event_id in event_by_id:
            event = event_by_id[track.event_id]
            event["plate"] = choose_final_plate(track)
            event["class"] = track.pred_class if track.pred_class else event["class"]
            event["conf"] = track.class_conf if track.class_conf else event["conf"]

    for event in list(pending_events):
        pending_events.remove(event)
        event_by_id.pop(event["id"], None)
        finalize_event(event, ffmpeg_ok, fps)

    cap.release()
    cv2.destroyAllWindows()

    print("🛑 System stopped.")


if __name__ == "__main__":
    main()