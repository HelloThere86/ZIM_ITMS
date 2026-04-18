import cv2
import numpy as np
import sqlite3
import os
import sys
import re
import time
import json
import subprocess
from datetime import datetime
from collections import deque
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
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

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from api.runtime_config import get_runtime_config

DEFAULT_INTERSECTION_ID = 1
CNN_CLASSES = ["ambulance", "civilian_car", "fire_truck", "police_car"]
UNKNOWN_PLATE_SENTINEL = "UNKNOWN-UNREGISTERED"

DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 720

# =========================================================
# BOT-SORT DETECTOR SETTINGS
# =========================================================
YOLO_IMGSZ = 416
TRACK_EVERY_N_FRAMES = 1

LINE_CROSS_MARGIN = 6
MIN_TRACK_AGE_FOR_CROSSING = 2
MIN_TRACK_AGE_FOR_LATE_CATCH = 3

POST_CAPTURE_FRAMES = 90
MAX_BACKGROUND_SAVERS = 2
TRACK_FORGET_FRAMES = 180

# =========================================================
# LATE-CATCH SETTINGS
# =========================================================
# Used for cars whose plate becomes visible only after they cross the line.
# LATE_CATCH_FIRST_SEEN_BELOW_BUFFER tightened from 120 -> 30 to prevent
# below-line re-spawned re-IDs from firing a second event.
LATE_CATCH_FIRST_SEEN_ABOVE_BUFFER = 90
LATE_CATCH_FIRST_SEEN_BELOW_BUFFER = 30      # FIX: was 120
LATE_CATCH_MAX_BELOW_LINE = 240

# =========================================================
# DUPLICATE SAFETY NET
# =========================================================
# BoT-SORT handles most identity persistence via ReID appearance features.
# These are layered safety nets for the cases that slip through.

GLOBAL_CROSSING_DEDUP_FRAMES = 600   # FIX: was 70 (~3.5s) -> now ~7.5s at 20fps
RECENT_SIMILARITY_FRAMES = 60        # FIX: was 28

# Ghost registry: remember dead tracks that fired events so we can block
# re-IDed versions of the same vehicle from firing a second event.
GHOST_TTL_FRAMES = 300              # how long to keep a dead track's bbox
GHOST_IOU_THRESH = 0.30             # IoU overlap to consider a re-entry

# Lane-slot cooldown: blunt last-resort net.
# Divide the frame width into N horizontal slots. Once a slot fires, it
# cannot fire again for LANE_COOLDOWN_FRAMES frames.
LANE_SLOTS = 10
LANE_COOLDOWN_FRAMES = 120


# =========================================================
# BASIC HELPERS
# =========================================================
def normalize_plate(plate: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", plate.upper()) if plate else "UNKNOWN"


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
        f"VideoStatus: {data.get('videoStatus', 'Unknown')}; "
        f"OCRReliable: {data.get('ocrReliable', False)}; "
        f"OCRMethod: {data.get('ocrMethod', 'unknown')}; "
        f"OCRPeakConfidence: {data.get('ocrPeakConfidence', 0)}; "
        f"SimilarMatches: {json.dumps(data.get('similarRegisteredPlates', []))}; "
        f"ReviewData={json.dumps(data)}"
    )


# =========================================================
# DUPLICATE HELPERS
# =========================================================
def box_features(bbox):
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    w = x2 - x1
    h = y2 - y1
    return cx, cy, w, h


def box_iou(box_a, box_b) -> float:
    """
    Intersection-over-Union for two (x1, y1, x2, y2) boxes.
    Much more robust than absolute pixel delta comparisons because it is
    scale-invariant — a vehicle close to camera and one far away are treated
    consistently.
    """
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))

    return inter / (area_a + area_b - inter)


def similar_box(box_a, box_b, iou_thresh: float = 0.35) -> bool:
    """
    FIX: replaced absolute pixel delta checks with IoU.
    The old approach broke when vehicles were at different distances from
    the camera because the pixel sizes varied wildly.
    """
    return box_iou(box_a, box_b) >= iou_thresh


def is_ghost_reentry(track_ghosts: dict, bbox) -> bool:
    """
    Returns True if bbox overlaps significantly with a recently dead track
    that already fired a crossing event. This catches the most common cause
    of duplicates: BoT-SORT losing a track for a few frames and re-issuing a
    new ID for the same physical vehicle.
    """
    return any(
        box_iou(bbox, g["bbox"]) >= GHOST_IOU_THRESH
        for g in track_ghosts.values()
    )


def is_duplicate_crossing(recent_crossings, track_id, bbox, frame_index):
    """
    Layered duplicate suppression safety net.

    Layer 1: Same BoT-SORT track_id -> instant reject.
    Layer 2: IoU overlap within the short similarity window -> reject.
    Layer 3: Spatial centroid similarity within the short window -> reject.

    Ghost re-entry and lane cooldown are checked by the caller so they can
    be logged with distinct reasons.
    """
    recent_crossings[:] = [
        e for e in recent_crossings
        if frame_index - e["frame_index"] <= GLOBAL_CROSSING_DEDUP_FRAMES
    ]

    cx, cy, w, h = box_features(bbox)

    for e in recent_crossings:
        frame_gap = frame_index - e["frame_index"]

        if frame_gap < 0:
            continue

        # Layer 1 — identical tracker ID
        if e.get("track_id") == track_id:
            return True, "same_track_id"

        # Layer 2 — IoU overlap (replaces old pixel-delta similar_box)
        if frame_gap <= RECENT_SIMILARITY_FRAMES and similar_box(bbox, e["bbox"]):
            return True, "similar_box_iou"

        # Layer 3 — centroid + size similarity
        same_region_like = (
            frame_gap <= RECENT_SIMILARITY_FRAMES
            and abs(cx - e["cx"]) < 80
            and abs(cy - e["cy"]) < 110
            and abs(w - e["w"]) < 70
            and abs(h - e["h"]) < 80
        )

        if same_region_like:
            return True, "same_region_like"

    return False, "none"


# =========================================================
# FILE / VIDEO HELPERS
# =========================================================
def ensure_directories():
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


def ffmpeg_available():
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
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
# MODEL HELPERS
# =========================================================
def classify_vehicle(cnn_model, car_crop):
    img_arr = tf.expand_dims(cv2.resize(car_crop, (150, 150)) / 255.0, 0)
    score = tf.nn.softmax(cnn_model.predict(img_arr, verbose=0)[0]).numpy()
    idx = int(np.argmax(score))
    return CNN_CLASSES[idx], float(100 * np.max(score))


def load_models():
    print("Initialising BoT-SORT fast edge detector...")

    yolo_model = YOLO("yolov8n.pt")

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(MODEL_PATH)

    cnn_model = tf.keras.models.load_model(MODEL_PATH)

    return yolo_model, cnn_model


# =========================================================
# DATABASE INSERT / UPDATE
# =========================================================
def insert_violation_immediately(
    v_class, conf, frame_img, event_bbox=None, track_id=None, trigger_reason=None
):
    conn = None

    try:
        conn = get_db()
        c = conn.cursor()

        runtime_config = get_runtime_config()
        jpeg_quality = runtime_config["jpeg_quality"]

        row = c.execute(
            "SELECT 1 FROM intersection WHERE intersection_id = ? LIMIT 1",
            (DEFAULT_INTERSECTION_ID,),
        ).fetchone()

        if row is None:
            print(f"❌ intersection_id={DEFAULT_INTERSECTION_ID} not found.")
            return None

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        unique_id = int(time.time() * 1000)
        img_filename = f"violation_{unique_id}.jpg"

        cv2.imwrite(
            str(EVIDENCE_DIR / img_filename),
            frame_img,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
        )

        registry_lookup_mode = os.environ.get("REGISTRY_LOOKUP_MODE", "local").lower()

        review_data = {
            "detectedClass": v_class,
            "ocrPlate": "UNKNOWN",
            "registered": False,
            "registryStatus": (
                "OCRPending" if registry_lookup_mode != "offline" else "PendingSync"
            ),
            "registryLookupMode": registry_lookup_mode,
            "ocrStatus": "Pending",
            "videoStatus": "Pending",
            "ocrReliable": False,
            "ocrMethod": "async_pending",
            "ocrCount": 0,
            "ocrWeight": 0.0,
            "ocrPeakConfidence": 0.0,
            "similarRegisteredPlates": [],
            "eventBbox": list(event_bbox) if event_bbox else None,
            "tracker": "BoT-SORT",
            "trackId": int(track_id) if track_id is not None else None,
            "triggerReason": trigger_reason or "unknown",
        }

        note = rebuild_review_note(review_data)

        c.execute(
            "INSERT OR IGNORE INTO vehicle (plate_number, is_exempt) VALUES (?, 0)",
            (UNKNOWN_PLATE_SENTINEL,),
        )

        c.execute(
            """
            INSERT INTO violation (
                plate_number, intersection_id, timestamp,
                image_path, video_path, confidence_score,
                decision_type, status, review_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                UNKNOWN_PLATE_SENTINEL,
                DEFAULT_INTERSECTION_ID,
                timestamp,
                img_filename,
                None,
                float(conf),
                "Flagged",
                "Pending",
                note,
            ),
        )

        violation_id = c.lastrowid
        conn.commit()

        print(
            f"💾 FAST V-{violation_id} inserted immediately | "
            f"Track={track_id} | Class: {v_class} ({conf:.1f}%) | "
            f"OCRPending | VideoPending | Trigger={trigger_reason}"
        )

        return violation_id

    except Exception as e:
        print(f"❌ Immediate violation insert failed: {e}")
        return None
    finally:
        if conn:
            conn.close()


def update_violation_video_path(violation_id, video_filename):
    conn = None

    try:
        conn = get_db()
        c = conn.cursor()

        row = c.execute(
            "SELECT review_note FROM violation WHERE violation_id = ?",
            (violation_id,),
        ).fetchone()

        if not row:
            print(f"⚠️ Could not update video. V-{violation_id} not found.")
            return

        data = extract_review_data(row["review_note"] or "")
        if not data:
            data = {}

        data["videoStatus"] = "Ready" if video_filename else "Failed"

        updated_note = rebuild_review_note(data)

        c.execute(
            """
            UPDATE violation
            SET video_path = ?,
                review_note = ?
            WHERE violation_id = ?
            """,
            (video_filename, updated_note, violation_id),
        )

        conn.commit()

        print(f"🎞️ FAST V-{violation_id} video updated -> {video_filename or 'FAILED'}")

    except Exception as e:
        print(f"❌ Video update failed for V-{violation_id}: {e}")
    finally:
        if conn:
            conn.close()


def finalize_event_async(event, ffmpeg_ok, fps):
    violation_id = event.get("violation_id")
    if not violation_id:
        return

    raw_vid = EVIDENCE_DIR / f"violation_{event['id']}_raw.avi"
    final_vid = EVIDENCE_DIR / f"violation_{event['id']}.mp4"

    vid_name = None

    if save_video_clip(event["frames"], raw_vid, fps):
        vid_name = raw_vid.name

        if ffmpeg_ok and convert_to_browser_mp4(raw_vid, final_vid):
            vid_name = final_vid.name
            try:
                os.remove(raw_vid)
            except Exception:
                pass

    update_violation_video_path(violation_id, vid_name)


# =========================================================
# TRACK STATE HELPERS
# =========================================================
def get_or_create_track_state(track_states, track_id, bbox, frame_index, frame_img):
    x1, y1, x2, y2 = bbox
    cx, cy, w, h = box_features(bbox)

    crop = frame_img[y1:y2, x1:x2]
    snapshot = crop.copy() if crop.size > 0 else None

    if track_id not in track_states:
        track_states[track_id] = {
            "track_id": track_id,
            "age": 1,
            "first_seen_frame": frame_index,
            "first_seen_cy": cy,
            "prev_cx": None,
            "prev_cy": None,
            "cx": cx,
            "cy": cy,
            "bbox": bbox,
            "last_seen_frame": frame_index,
            "crossed_line": False,
            "event_created": False,
            "pred_class": None,
            "class_conf": 0.0,
            "last_cls_update_frame": 0,
            "snapshot": snapshot,
        }
        return track_states[track_id]

    state = track_states[track_id]

    state["prev_cx"] = state["cx"]
    state["prev_cy"] = state["cy"]
    state["cx"] = cx
    state["cy"] = cy
    state["bbox"] = bbox
    state["age"] += 1
    state["last_seen_frame"] = frame_index

    if snapshot is not None:
        state["snapshot"] = snapshot

    return state


def prune_old_tracks(track_states: dict, track_ghosts: dict, frame_index: int):
    """
    Remove tracks that haven't been seen for TRACK_FORGET_FRAMES.

    FIX: tracks that already fired a crossing event are moved to track_ghosts
    so we can detect re-IDed versions of the same vehicle reappearing.
    """
    dead_ids = [
        tid
        for tid, state in track_states.items()
        if frame_index - state["last_seen_frame"] > TRACK_FORGET_FRAMES
    ]

    for tid in dead_ids:
        state = track_states[tid]
        if state["event_created"]:
            # Remember this vehicle's last known bbox. Any new track that
            # overlaps this bbox within GHOST_TTL_FRAMES will be suppressed.
            track_ghosts[tid] = {
                "bbox": state["bbox"],
                "died_frame": frame_index,
            }
        del track_states[tid]

    # Expire stale ghosts
    expired_ghosts = [
        tid
        for tid, g in track_ghosts.items()
        if frame_index - g["died_frame"] > GHOST_TTL_FRAMES
    ]
    for tid in expired_ghosts:
        del track_ghosts[tid]


# =========================================================
# MAIN LOOP
# =========================================================
def main():
    ensure_directories()

    ffmpeg_ok = ffmpeg_available()
    yolo_model, cnn_model = load_models()
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

    frame_index = 0
    frame_buffer = deque(maxlen=pre_frames)

    pending_events = []
    recent_crossings = []

    track_states = {}
    track_ghosts = {}   # tid -> {bbox, died_frame} for dead-track re-ID detection
    lane_cooldown = {}  # lane_slot -> frame_index of last accepted crossing

    light_state = "RED"
    executor = ThreadPoolExecutor(max_workers=MAX_BACKGROUND_SAVERS)

    print(f"📹 BoT-SORT detector video: {width}x{height} @ {fps:.1f}fps")

    cv2.namedWindow("ITMS BoT-SORT Edge Feed", cv2.WINDOW_NORMAL)

    if DISPLAY_WIDTH and DISPLAY_HEIGHT:
        cv2.resizeWindow("ITMS BoT-SORT Edge Feed", DISPLAY_WIDTH, DISPLAY_HEIGHT)

    print(
        f"\n{'=' * 96}\n"
        f"✅ FAST ASYNC EDGE DETECTOR - BOT-SORT + LATE-CATCH MODE | {VIDEO_SOURCE}\n"
        f"   G=GREEN | R=RED | Q=Quit\n"
        f"   Tracker                  : Ultralytics BoT-SORT\n"
        f"   DB insert                : immediate on crossing / late-catch\n"
        f"   Video save               : background update\n"
        f"   OCR responsibility       : workers/ocr_registry_worker.py\n"
        f"   SMS responsibility       : workers/notification_worker.py\n"
        f"   YOLO imgsz               : {YOLO_IMGSZ}\n"
        f"   Tracking stride          : {TRACK_EVERY_N_FRAMES}\n"
        f"   Post-capture frames      : {POST_CAPTURE_FRAMES}\n"
        f"   Dedup window             : {GLOBAL_CROSSING_DEDUP_FRAMES} frames\n"
        f"   Ghost TTL                : {GHOST_TTL_FRAMES} frames\n"
        f"   Lane slots               : {LANE_SLOTS} | cooldown: {LANE_COOLDOWN_FRAMES} frames\n"
        f"{'=' * 96}\n"
    )

    try:
        while cap.isOpened():
            ret, frame = cap.read()

            if not ret:
                break

            frame_index += 1
            raw_frame = frame.copy()

            # Dispatch finished evidence clips to background thread
            finished = [e for e in pending_events if e["remaining_frames"] <= 0]

            for event in finished:
                pending_events.remove(event)
                executor.submit(finalize_event_async, event, ffmpeg_ok, fps)

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

            if light_state == "RED" and frame_index % TRACK_EVERY_N_FRAMES == 0:
                try:
                    results = yolo_model.track(
                        frame,
                        imgsz=YOLO_IMGSZ,
                        persist=True,
                        tracker="botsort.yaml",
                        classes=[2, 3, 5, 7],
                        conf=0.18,
                        iou=0.50,
                        verbose=False,
                    )
                except Exception as e:
                    print(f"⚠️ BoT-SORT failed on frame {frame_index}: {e}")
                    results = []

                if results:
                    boxes = results[0].boxes

                    if boxes is not None and boxes.id is not None:
                        for box in boxes:
                            track_id_tensor = box.id
                            if track_id_tensor is None:
                                continue

                            track_id = int(track_id_tensor.item())

                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            x1 = max(0, min(width - 1, x1))
                            y1 = max(0, min(height - 1, y1))
                            x2 = max(0, min(width - 1, x2))
                            y2 = max(0, min(height - 1, y2))

                            if x2 <= x1 or y2 <= y1:
                                continue

                            bbox = (x1, y1, x2, y2)

                            state = get_or_create_track_state(
                                track_states,
                                track_id,
                                bbox,
                                frame_index,
                                raw_frame,
                            )

                            crop = raw_frame[y1:y2, x1:x2]

                            if crop.size > 0 and (
                                state["pred_class"] is None
                                or frame_index - state["last_cls_update_frame"] >= 12
                            ):
                                try:
                                    pred_class, class_conf = classify_vehicle(
                                        cnn_model, crop
                                    )
                                    state["pred_class"] = pred_class
                                    state["class_conf"] = class_conf
                                    state["last_cls_update_frame"] = frame_index
                                except Exception as cls_err:
                                    print(
                                        f"⚠️ CNN classification failed for "
                                        f"Track {track_id}: {cls_err}"
                                    )

                            # -----------------------------------------------
                            # CROSSING DETECTION
                            # -----------------------------------------------
                            crossed_from_above = (
                                state["prev_cy"] is not None
                                and state["age"] >= MIN_TRACK_AGE_FOR_CROSSING
                                and state["prev_cy"] < (line_y - LINE_CROSS_MARGIN)
                                and state["cy"] >= (line_y - LINE_CROSS_MARGIN)
                            )

                            # FIX: added movement guard (prev_cy check + min
                            # displacement) to stop re-IDed stationary spawns
                            # below the line from triggering late-catch.
                            late_visible_below_line = (
                                not crossed_from_above
                                and not state["event_created"]
                                and state["age"] >= MIN_TRACK_AGE_FOR_LATE_CATCH
                                and state["first_seen_cy"] is not None
                                and (line_y - LATE_CATCH_FIRST_SEEN_ABOVE_BUFFER)
                                <= state["first_seen_cy"]
                                <= (line_y + LATE_CATCH_FIRST_SEEN_BELOW_BUFFER)
                                and state["cy"] >= (line_y - LINE_CROSS_MARGIN)
                                and state["cy"] <= (line_y + LATE_CATCH_MAX_BELOW_LINE)
                                and state["prev_cy"] is not None          # must have history
                                and abs(state["cy"] - state["first_seen_cy"]) > 8  # must have moved
                            )

                            trigger_reason = None
                            if crossed_from_above:
                                trigger_reason = "crossed_from_above"
                            elif late_visible_below_line:
                                trigger_reason = "late_visible_below_line"

                            if not state["event_created"] and trigger_reason is not None:
                                pred_class = state["pred_class"] or "civilian_car"
                                bbox = state["bbox"]
                                cx, cy, w, h = box_features(bbox)

                                # --- Layer 1-3: standard dedup ---
                                duplicate, reason = is_duplicate_crossing(
                                    recent_crossings,
                                    track_id,
                                    bbox,
                                    frame_index,
                                )

                                # --- Layer 4: ghost re-entry ---
                                # Catches re-IDed vehicles that BoT-SORT dropped
                                # briefly and reissued a new track ID for.
                                if not duplicate and is_ghost_reentry(track_ghosts, bbox):
                                    duplicate, reason = True, "ghost_reentry"

                                # --- Layer 5: lane-slot cooldown ---
                                # Blunt last-resort net. If the same horizontal
                                # lane fired very recently, suppress.
                                if not duplicate:
                                    slot = int(cx / width * LANE_SLOTS)
                                    last_lane_frame = lane_cooldown.get(slot, -9999)
                                    if frame_index - last_lane_frame < LANE_COOLDOWN_FRAMES:
                                        duplicate, reason = True, "lane_cooldown"

                                # ----------------------------------------
                                # FIRE EVENT
                                # ----------------------------------------
                                if not duplicate:
                                    state["crossed_line"] = True
                                    state["event_created"] = True

                                    snapshot = state["snapshot"]
                                    if snapshot is None and crop.size > 0:
                                        snapshot = crop.copy()

                                    if snapshot is None:
                                        continue

                                    violation_id = insert_violation_immediately(
                                        v_class=pred_class,
                                        conf=(
                                            state["class_conf"]
                                            if state["class_conf"]
                                            else 97.0
                                        ),
                                        frame_img=snapshot,
                                        event_bbox=bbox,
                                        track_id=track_id,
                                        trigger_reason=trigger_reason,
                                    )

                                    if violation_id:
                                        event_id = int(time.time() * 1000) + track_id

                                        event = {
                                            "id": event_id,
                                            "violation_id": violation_id,
                                            "track_id": track_id,
                                            "frames": list(frame_buffer)
                                            + [raw_frame.copy()],
                                            "remaining_frames": POST_CAPTURE_FRAMES,
                                            "created_frame": frame_index,
                                            "bbox": bbox,
                                        }

                                        pending_events.append(event)

                                        recent_crossings.append(
                                            {
                                                "frame_index": frame_index,
                                                "track_id": track_id,
                                                "bbox": bbox,
                                                "cx": cx,
                                                "cy": cy,
                                                "w": w,
                                                "h": h,
                                            }
                                        )

                                        # Record lane cooldown slot
                                        slot = int(cx / width * LANE_SLOTS)
                                        lane_cooldown[slot] = frame_index

                                        print(
                                            f"🚨 BoT-SORT event -> V-{violation_id} "
                                            f"Track={track_id} reason={trigger_reason} "
                                            f"lane_slot={slot} | video queued"
                                        )

                                else:
                                    # Mark as done so we never revisit this track
                                    state["crossed_line"] = True
                                    state["event_created"] = True
                                    print(
                                        f"↪️ Duplicate suppressed -> "
                                        f"Track={track_id} reason={reason}"
                                    )

                            # -----------------------------------------------
                            # DRAW BOUNDING BOX + LABEL
                            # -----------------------------------------------
                            color = (0, 0, 255)
                            if state["pred_class"] and state["pred_class"] != "civilian_car":
                                color = (0, 255, 0)

                            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                            label = f"ID {track_id}"
                            if state["pred_class"]:
                                label += (
                                    f" {state['pred_class']} "
                                    f"{state['class_conf']:.0f}%"
                                )

                            cv2.putText(
                                frame,
                                label,
                                (x1, max(20, y1 - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.52,
                                color,
                                2,
                            )

            # FIX: pass track_ghosts so dead tracks are remembered
            prune_old_tracks(track_states, track_ghosts, frame_index)

            frame_buffer.append(raw_frame.copy())

            cv2.imshow("ITMS BoT-SORT Edge Feed", frame)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            elif key == ord("g"):
                light_state = "GREEN"
            elif key == ord("r"):
                light_state = "RED"

    finally:
        for event in list(pending_events):
            executor.submit(finalize_event_async, event, ffmpeg_ok, fps)

        executor.shutdown(wait=True)

        cap.release()
        cv2.destroyAllWindows()

        print("🛑 BoT-SORT detector stopped.")


if __name__ == "__main__":
    main()