import cv2
import easyocr
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from collections import defaultdict
import numpy as np
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

DB_PATH = PROJECT_ROOT / "database" / "itms_production.db"
EVIDENCE_DIR = PROJECT_ROOT / "dashboard" / "evidence"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from api.plate_matcher import find_similar_registered_plates

UNKNOWN_PLATE_SENTINEL = "UNKNOWN-UNREGISTERED"

POLL_SECONDS = 3
BATCH_SIZE = 5

YOLO_IMGSZ = 416
VIDEO_SAMPLE_FRAMES = 12
MAX_VEHICLE_CROPS_PER_FRAME = 3

MIN_PLATE_REGION_WIDTH = 60
MIN_PLATE_REGION_HEIGHT = 12
MIN_PLATE_SHARPNESS = 6.0

AUTO_APPROVE_OCR_CONF = 50.0

UK_PLATE_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{3}$")


def normalize_plate(plate: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", plate.upper()) if plate else "UNKNOWN"


def is_exact_uk_plate(text: str) -> bool:
    return bool(text and UK_PLATE_RE.match(normalize_plate(text)))


def normalize_uk_candidate(raw: str) -> str | None:
    cleaned = normalize_plate(raw)

    if not cleaned or len(cleaned) < 7:
        return None

    candidates = [cleaned[i:i + 7] for i in range(0, len(cleaned) - 6)]

    digit_map = {
        "O": "0", "Q": "0", "D": "0",
        "I": "1", "L": "1", "T": "1",
        "Z": "2", "S": "5", "B": "8", "G": "6",
    }

    letter_map = {
        "0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B",
    }

    best = None
    best_score = -1e9

    for cand in candidates:
        chars = list(cand)
        score = 0.0
        valid = True

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


class PlateVote:
    def __init__(self):
        self.full_counts = defaultdict(int)
        self.full_weights = defaultdict(float)
        self.full_best_conf = defaultdict(float)
        self.char_weights = [defaultdict(float) for _ in range(7)]
        self.reads = []

    def add(self, plate: str, conf: float, quality: float):
        candidate = normalize_uk_candidate(plate)
        if candidate is None:
            return

        weight = max(float(conf), 1.0) + min(float(quality) / 8.0, 25.0)

        self.full_counts[candidate] += 1
        self.full_weights[candidate] += weight
        self.full_best_conf[candidate] = max(self.full_best_conf[candidate], float(conf))
        self.reads.append((candidate, float(conf), float(quality), weight))

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

        if full_plate and full_count >= 2:
            return full_plate, "full_vote", full_count, full_weight, full_conf

        if char_plate and char_weight >= 90.0 and min_pos_weight >= 8.0:
            return char_plate, "char_vote", full_count, char_weight, full_conf

        if full_plate and full_conf >= AUTO_APPROVE_OCR_CONF:
            return full_plate, "best_single", full_count, full_weight, full_conf

        return None, "none", 0, 0.0, 0.0


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def extract_review_data(note: str) -> dict:
    if not note:
        return {}

    marker = "ReviewData="
    idx = note.find(marker)

    if idx == -1:
        return {}

    raw = note[idx + len(marker):].strip()

    # If later officer notes were appended, trim them off.
    officer_idx = raw.find(" [OFFICER_REVIEW=")
    if officer_idx != -1:
        raw = raw[:officer_idx].strip()

    try:
        return json.loads(raw)
    except Exception:
        return {}


def rebuild_review_note(data: dict) -> str:
    return (
        f"Detected Class: {data.get('detectedClass', 'unknown')}; "
        f"OCR Plate: {data.get('ocrPlate', 'UNKNOWN')}; "
        f"Registered: {data.get('registered', False)}; "
        f"RegistryStatus: {data.get('registryStatus', 'Unknown')}; "
        f"OCRStatus: {data.get('ocrStatus', 'Unknown')}; "
        f"OCRReliable: {data.get('ocrReliable', False)}; "
        f"OCRMethod: {data.get('ocrMethod', 'unknown')}; "
        f"OCRPeakConfidence: {data.get('ocrPeakConfidence', 0)}; "
        f"SimilarMatches: {json.dumps(data.get('similarRegisteredPlates', []))}; "
        f"ReviewData={json.dumps(data)}"
    )


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
        return car_crop

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
            2.0 <= aspect <= 8.5
            and 0.08 <= w / w_car <= 0.95
            and 0.02 <= h / h_car <= 0.35
            and y > h_car * 0.15
            and area > 50
        ):
            continue

        crop = car_crop[y:y + h, x:x + w]
        quality = crop_quality_score(crop)

        if quality > best_score:
            best_score = quality
            best_crop = crop

    if best_crop is not None and best_crop.size > 0:
        return best_crop

    mid_lower = car_crop[
        int(h_car * 0.45):int(h_car * 0.88),
        int(w_car * 0.05):int(w_car * 0.95),
    ]

    if mid_lower.size > 0:
        return mid_lower

    return car_crop


def read_plate(reader: easyocr.Reader, car_crop: np.ndarray):
    plate_region = detect_plate_region(car_crop)

    if plate_region is None or plate_region.size == 0:
        return "UNKNOWN", 0.0, 0.0

    h, w = plate_region.shape[:2]
    gray = cv2.cvtColor(plate_region, cv2.COLOR_BGR2GRAY)
    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
    quality = crop_quality_score(plate_region)

    if w < MIN_PLATE_REGION_WIDTH or h < MIN_PLATE_REGION_HEIGHT or sharpness < MIN_PLATE_SHARPNESS:
        return "UNKNOWN", 0.0, quality

    variants = preprocess_plate(plate_region)

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
                text_threshold=0.25,
                low_text=0.15,
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


def extract_vehicle_crops_from_frame(yolo_model, frame: np.ndarray):
    crops = []

    try:
        results = yolo_model(frame, imgsz=YOLO_IMGSZ, verbose=False)
    except Exception:
        return crops

    h_frame, w_frame = frame.shape[:2]

    boxes = []
    for box in results[0].boxes:
        cls = int(box.cls[0])
        if cls not in [2, 3, 5, 7]:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w_frame, x2)
        y2 = min(h_frame, y2)

        if x2 <= x1 or y2 <= y1:
            continue

        area = (x2 - x1) * (y2 - y1)
        cy = (y1 + y2) / 2

        # Prefer vehicles lower in frame and larger, because they are more likely to be the crossing vehicle.
        priority = area + cy * 500
        boxes.append((priority, x1, y1, x2, y2))

    boxes.sort(reverse=True)

    for _, x1, y1, x2, y2 in boxes[:MAX_VEHICLE_CROPS_PER_FRAME]:
        crop = frame[y1:y2, x1:x2]
        if crop.size > 0:
            crops.append(crop)

    return crops


def sample_video_frames(video_file: Path, max_frames: int = VIDEO_SAMPLE_FRAMES):
    frames = []

    cap = cv2.VideoCapture(str(video_file))
    if not cap.isOpened():
        return frames

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    if total <= 0:
        cap.release()
        return frames

    sample_indexes = np.linspace(0, max(0, total - 1), num=min(max_frames, total), dtype=int)

    for idx in sample_indexes:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)

    cap.release()
    return frames


def find_pending_ocr_cases(conn):
    rows = conn.execute(
        """
        SELECT violation_id, plate_number, image_path, video_path, confidence_score, status, review_note
        FROM violation
        WHERE image_path IS NOT NULL
        ORDER BY violation_id ASC
        LIMIT 100
        """
    ).fetchall()

    pending = []

    for row in rows:
        data = extract_review_data(row["review_note"] or "")

        if data.get("ocrStatus") != "Pending":
            continue

        video_status = data.get("videoStatus")

        # New async behaviour:
        # - Show record immediately in frontend.
        # - Wait for video to be Ready before OCR, so OCR gets multi-frame evidence.
        # - If video save failed, process snapshot as fallback.
        if video_status == "Pending":
            continue

        if video_status in ("Ready", "Failed", None):
            pending.append(row)

        if len(pending) >= BATCH_SIZE:
            break

    return pending


def process_case(reader, yolo_model, row):
    violation_id = row["violation_id"]

    data = extract_review_data(row["review_note"] or "")

    image_path = row["image_path"]
    video_path = row["video_path"]

    candidate_crops = []

    if image_path:
        image_file = EVIDENCE_DIR / image_path
        if image_file.exists():
            img = cv2.imread(str(image_file))
            if img is not None:
                candidate_crops.append(("snapshot", img))

    if video_path:
        video_file = EVIDENCE_DIR / video_path
        if video_file.exists():
            frames = sample_video_frames(video_file)

            for frame in frames:
                vehicle_crops = extract_vehicle_crops_from_frame(yolo_model, frame)

                for crop in vehicle_crops:
                    candidate_crops.append(("video_yolo_crop", crop))

    if not candidate_crops:
        data["ocrStatus"] = "EvidenceMissing"
        data["registryStatus"] = "EvidenceMissing"
        update_case(row, data, "UNKNOWN", "Pending", "Flagged")
        print(f"⚠️ OCR Worker V-{violation_id}: no evidence available")
        return

    voter = PlateVote()
    best_raw = ("UNKNOWN", 0.0, 0.0, "none")

    for source, crop in candidate_crops:
        plate, conf, quality = read_plate(reader, crop)
        voter.add(plate, conf, quality)

        if plate != "UNKNOWN" and conf > best_raw[1]:
            best_raw = (plate, conf, quality, source)

    final_plate, method, count, weight, peak_conf = voter.best()

    if final_plate is None:
        final_plate = "UNKNOWN"
        method = "none"
        count = 0
        weight = 0.0
        peak_conf = 0.0

    ocr_reliable = is_exact_uk_plate(final_plate) and peak_conf >= AUTO_APPROVE_OCR_CONF

    conn = get_db()

    try:
        is_registered = False
        similar_matches = []
        registry_status = "PlateNotLocked"

        final_plate_number = UNKNOWN_PLATE_SENTINEL
        status = "Pending"
        decision_type = "Flagged"

        if final_plate != "UNKNOWN":
            existing = conn.execute(
                "SELECT 1 FROM vehicle WHERE plate_number = ? LIMIT 1",
                (final_plate,),
            ).fetchone()

            is_registered = existing is not None

            if is_registered:
                registry_status = "ExactMatch"
                final_plate_number = final_plate

                if ocr_reliable and data.get("detectedClass") == "civilian_car":
                    status = "AutoApproved"
                    decision_type = "Auto"
                else:
                    status = "Pending"
                    decision_type = "Flagged"
            else:
                registry_status = "NoExactMatch"
                similar_matches = find_similar_registered_plates(conn, final_plate, limit=5)
                final_plate_number = UNKNOWN_PLATE_SENTINEL

        data.update(
            {
                "ocrPlate": final_plate,
                "registered": is_registered,
                "registryStatus": registry_status,
                "ocrStatus": "Complete",
                "ocrReliable": ocr_reliable,
                "ocrMethod": f"async_video_multi_frame_{method}",
                "ocrCount": count,
                "ocrWeight": round(float(weight), 2),
                "ocrPeakConfidence": round(float(peak_conf), 2),
                "ocrBestSource": best_raw[3],
                "similarRegisteredPlates": similar_matches,
            }
        )

        note = rebuild_review_note(data)

        conn.execute(
            """
            UPDATE violation
            SET plate_number = ?,
                status = ?,
                decision_type = ?,
                review_note = ?
            WHERE violation_id = ?
            """,
            (
                final_plate_number,
                status,
                decision_type,
                note,
                violation_id,
            ),
        )

        conn.commit()

        print(
            f"🔍 OCR Worker V-{violation_id}: {final_plate} "
            f"peak={peak_conf:.1f}% reads={count} "
            f"registered={is_registered} registry={registry_status} "
            f"status={status} source={best_raw[3]}"
        )

        if similar_matches:
            print(f"   suggestions={similar_matches}")

    finally:
        conn.close()


def update_case(row, data, plate, status, decision_type):
    conn = get_db()

    try:
        data.update(
            {
                "ocrPlate": plate,
                "ocrStatus": data.get("ocrStatus", "Complete"),
                "ocrReliable": False,
                "similarRegisteredPlates": [],
            }
        )

        conn.execute(
            """
            UPDATE violation
            SET status = ?,
                decision_type = ?,
                review_note = ?
            WHERE violation_id = ?
            """,
            (
                status,
                decision_type,
                rebuild_review_note(data),
                row["violation_id"],
            ),
        )

        conn.commit()
    finally:
        conn.close()


def main():
    print("🔁 Starting OCR + Registry worker...")
    print(f"   Exact registry auto-approval OCR threshold: {AUTO_APPROVE_OCR_CONF}%")
    print(f"   Video sample frames per case: {VIDEO_SAMPLE_FRAMES}")

    try:
        reader = easyocr.Reader(["en"], gpu=True)
    except Exception:
        print("⚠️ EasyOCR GPU init failed. Falling back to CPU.")
        reader = easyocr.Reader(["en"], gpu=False)

    yolo_model = YOLO("yolov8n.pt")

    while True:
        conn = get_db()

        try:
            cases = find_pending_ocr_cases(conn)
        finally:
            conn.close()

        if not cases:
            time.sleep(POLL_SECONDS)
            continue

        for row in cases:
            try:
                process_case(reader, yolo_model, row)
            except Exception as e:
                print(f"❌ OCR worker failed on V-{row['violation_id']}: {e}")

        time.sleep(0.5)


if __name__ == "__main__":
    main()