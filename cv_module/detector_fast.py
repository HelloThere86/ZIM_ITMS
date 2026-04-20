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
MODEL_PATH   = "zimbabwe_traffic_model.h5"

BASE_DIR     = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

DB_PATH      = PROJECT_ROOT / "database" / "itms_production.db"
EVIDENCE_DIR = PROJECT_ROOT / "dashboard" / "evidence"

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from api.runtime_config import get_runtime_config

DEFAULT_INTERSECTION_ID = 1
CNN_CLASSES             = ["ambulance", "civilian_car", "fire_truck", "police_car"]
UNKNOWN_PLATE_SENTINEL  = "UNKNOWN-UNREGISTERED"

DISPLAY_WIDTH  = 1280
DISPLAY_HEIGHT = 720

# =========================================================
# BOT-SORT DETECTOR SETTINGS
# =========================================================
YOLO_IMGSZ           = 640
TRACK_EVERY_N_FRAMES = 1

LINE_CROSS_MARGIN = 4

MIN_TRACK_AGE_FOR_CROSSING   = 2
MIN_TRACK_AGE_FOR_LATE_CATCH = 3

POST_CAPTURE_FRAMES   = 150
MAX_BACKGROUND_SAVERS = 2
TRACK_FORGET_FRAMES   = 180

# =========================================================
# LATE-CATCH SETTINGS
# =========================================================
LATE_CATCH_FIRST_SEEN_ABOVE_BUFFER = 90
LATE_CATCH_FIRST_SEEN_BELOW_BUFFER = 120
LATE_CATCH_MAX_BELOW_LINE          = 240

# =========================================================
# DUPLICATE SAFETY NET
# =========================================================
GLOBAL_CROSSING_DEDUP_FRAMES = 200
RECENT_SIMILARITY_FRAMES     = 15

GHOST_TTL_FRAMES = 300
GHOST_IOU_THRESH = 0.30

# =========================================================
# LANE-SLOT COOLDOWN
# =========================================================
LANE_SLOTS           = 6
LANE_COOLDOWN_FRAMES = 60

# Minimum IoU between a new crossing bbox and the cooldown-triggering bbox
# to treat it as the same physical vehicle and suppress it.
#
# WHY: The old cooldown was purely time-based — any car in the same lane
# slot within 60 frames was blocked, including genuine separate vehicles.
# Now we only suppress if the bboxes overlap significantly (same physical
# car re-detected under a new track ID after brief occlusion).
# A different car coming from behind occupies a completely different screen
# region at that moment -> low IoU -> passes through correctly.
LANE_COOLDOWN_IOU_THRESH = 0.25


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
    idx    = note.find(marker)
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
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0, x2 - x1, y2 - y1


def box_iou(box_a, box_b) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1   = max(ax1, bx1);  iy1 = max(ay1, by1)
    ix2   = min(ax2, bx2);  iy2 = min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return inter / (area_a + area_b - inter)


def similar_box(box_a, box_b, iou_thresh: float = 0.35) -> bool:
    return box_iou(box_a, box_b) >= iou_thresh


def is_ghost_reentry(track_ghosts: dict, bbox) -> bool:
    return any(
        box_iou(bbox, g["bbox"]) >= GHOST_IOU_THRESH
        for g in track_ghosts.values()
    )


def is_duplicate_crossing(recent_crossings, track_id, bbox, frame_index):
    recent_crossings[:] = [
        e for e in recent_crossings
        if frame_index - e["frame_index"] <= GLOBAL_CROSSING_DEDUP_FRAMES
    ]
    cx, cy, w, h = box_features(bbox)

    for e in recent_crossings:
        frame_gap = frame_index - e["frame_index"]
        if frame_gap < 0:
            continue
        if e.get("track_id") == track_id:
            return True, "same_track_id"
        if frame_gap <= RECENT_SIMILARITY_FRAMES and similar_box(bbox, e["bbox"]):
            return True, "similar_box_iou"
        if (
            frame_gap <= RECENT_SIMILARITY_FRAMES
            and abs(cx - e["cx"]) < 40
            and abs(cy - e["cy"]) < 40
            and abs(w  - e["w"])  < 40
            and abs(h  - e["h"])  < 40
        ):
            return True, "same_region_like"

    return False, "none"


def check_lane_cooldown(lane_cooldown: dict, slot: int,
                        frame_index: int, bbox) -> tuple:
    """
    IoU-gated lane slot cooldown.

    Suppress only when BOTH conditions hold:
      1. Within LANE_COOLDOWN_FRAMES of the last crossing in this slot.
      2. New bbox overlaps the stored bbox by >= LANE_COOLDOWN_IOU_THRESH,
         confirming it is the same physical vehicle re-detected under a
         new track ID after a brief occlusion.

    A genuinely different vehicle entering the same lane from behind will
    be at a completely different screen position -> low IoU -> allowed.
    """
    last = lane_cooldown.get(slot)
    if last is None:
        return False, "none"

    if frame_index - last["frame"] >= LANE_COOLDOWN_FRAMES:
        return False, "none"   # window expired

    iou = box_iou(bbox, last["bbox"])
    if iou >= LANE_COOLDOWN_IOU_THRESH:
        return True, f"lane_cooldown(iou={iou:.2f})"

    # Different vehicle in the same lane slot — allow it through
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
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except FileNotFoundError:
        return False


def save_video_clip(frames, output_path, fps):
    if not frames:
        return False
    h, w, _ = frames[0].shape
    writer  = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h),
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
                "ffmpeg", "-y", "-i", str(input_path),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(output_path),
            ],
            check=True, capture_output=True,
        )
        return output_path.exists() and output_path.stat().st_size > 0
    except Exception:
        return False


# =========================================================
# MODEL HELPERS
# =========================================================
def classify_vehicle(cnn_model, car_crop):
    img_arr = tf.expand_dims(cv2.resize(car_crop, (150, 150)) / 255.0, 0)
    score   = tf.nn.softmax(cnn_model.predict(img_arr, verbose=0)[0]).numpy()
    idx     = int(np.argmax(score))
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
    v_class, conf, frame_img,
    event_bbox=None, track_id=None, trigger_reason=None,
    event_frame_idx=None, frame_width=None, frame_height=None,
):
    conn = None
    try:
        conn = get_db()
        c    = conn.cursor()

        runtime_config = get_runtime_config()
        jpeg_quality   = runtime_config["jpeg_quality"]

        row = c.execute(
            "SELECT 1 FROM intersection WHERE intersection_id = ? LIMIT 1",
            (DEFAULT_INTERSECTION_ID,),
        ).fetchone()
        if row is None:
            print(f"intersection_id={DEFAULT_INTERSECTION_ID} not found.")
            return None

        timestamp    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        unique_id    = int(time.time() * 1000)
        img_filename = f"violation_{unique_id}.jpg"

        cv2.imwrite(
            str(EVIDENCE_DIR / img_filename), frame_img,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
        )

        registry_lookup_mode = os.environ.get("REGISTRY_LOOKUP_MODE", "local").lower()

        review_data = {
            "detectedClass": v_class,
            "ocrPlate":      "UNKNOWN",
            "registered":    False,
            "registryStatus": (
                "OCRPending" if registry_lookup_mode != "offline" else "PendingSync"
            ),
            "registryLookupMode": registry_lookup_mode,
            "ocrStatus":    "Pending",
            "videoStatus":  "Pending",
            "ocrReliable":  False,
            "ocrMethod":    "async_pending",
            "ocrCount":     0,
            "ocrWeight":    0.0,
            "ocrPeakConfidence": 0.0,
            "similarRegisteredPlates": [],
            "eventBbox":     list(event_bbox) if event_bbox else None,
            "eventFrameIdx": int(event_frame_idx) if event_frame_idx is not None else None,
            "detectDims": (
                [int(frame_width), int(frame_height)]
                if frame_width and frame_height else None
            ),
            "tracker":       "BoT-SORT",
            "trackId":       int(track_id) if track_id is not None else None,
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
                UNKNOWN_PLATE_SENTINEL, DEFAULT_INTERSECTION_ID, timestamp,
                img_filename, None, float(conf),
                "Flagged", "Pending", note,
            ),
        )

        violation_id = c.lastrowid
        conn.commit()

        print(
            f"FAST V-{violation_id} inserted | "
            f"Track={track_id} | Class={v_class} ({conf:.1f}%) | "
            f"Trigger={trigger_reason} | "
            f"EventFrame={event_frame_idx} | "
            f"DetectDims={frame_width}x{frame_height}"
        )
        return violation_id

    except Exception as e:
        print(f"Immediate violation insert failed: {e}")
        return None
    finally:
        if conn:
            conn.close()


def update_violation_video_path(violation_id, video_filename):
    conn = None
    try:
        conn = get_db()
        c    = conn.cursor()

        row = c.execute(
            "SELECT review_note FROM violation WHERE violation_id = ?",
            (violation_id,),
        ).fetchone()
        if not row:
            print(f"Could not update video. V-{violation_id} not found.")
            return

        data = extract_review_data(row["review_note"] or "")
        if not data:
            data = {}

        data["videoStatus"] = "Ready" if video_filename else "Failed"
        c.execute(
            "UPDATE violation SET video_path=?, review_note=? WHERE violation_id=?",
            (video_filename, rebuild_review_note(data), violation_id),
        )
        conn.commit()
        print(f"V-{violation_id} video -> {video_filename or 'FAILED'}")

    except Exception as e:
        print(f"Video update failed for V-{violation_id}: {e}")
    finally:
        if conn:
            conn.close()


def finalize_event_async(event, ffmpeg_ok, fps):
    violation_id = event.get("violation_id")
    if not violation_id:
        return

    raw_vid   = EVIDENCE_DIR / f"violation_{event['id']}_raw.avi"
    final_vid = EVIDENCE_DIR / f"violation_{event['id']}.mp4"
    vid_name  = None

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
    cx, cy, w, h   = box_features(bbox)

    crop     = frame_img[y1:y2, x1:x2]
    snapshot = crop.copy() if crop.size > 0 else None

    if track_id not in track_states:
        track_states[track_id] = {
            "track_id":              track_id,
            "age":                   1,
            "first_seen_frame":      frame_index,
            "first_seen_y2":         y2,
            "first_seen_cy":         cy,
            "prev_cx":               None,
            "prev_cy":               None,
            "prev_y2":               None,
            "cx":                    cx,
            "cy":                    cy,
            "y2":                    y2,
            "bbox":                  bbox,
            "last_seen_frame":       frame_index,
            "crossed_line":          False,
            "event_created":         False,
            "pred_class":            None,
            "class_conf":            0.0,
            "last_cls_update_frame": 0,
            "snapshot":              snapshot,
            "best_snapshot":         snapshot,
            "best_snapshot_y2":      y2,
        }
        return track_states[track_id]

    state = track_states[track_id]
    state["prev_cx"] = state["cx"]
    state["prev_cy"] = state["cy"]
    state["prev_y2"] = state["y2"]
    state["cx"]      = cx
    state["cy"]      = cy
    state["y2"]      = y2
    state["bbox"]    = bbox
    state["age"]    += 1
    state["last_seen_frame"] = frame_index

    if snapshot is not None:
        state["snapshot"] = snapshot
        if y2 > state["best_snapshot_y2"]:
            state["best_snapshot"]    = snapshot
            state["best_snapshot_y2"] = y2

    return state


def prune_old_tracks(track_states: dict, track_ghosts: dict, frame_index: int):
    dead_ids = [
        tid for tid, st in track_states.items()
        if frame_index - st["last_seen_frame"] > TRACK_FORGET_FRAMES
    ]
    for tid in dead_ids:
        st = track_states[tid]
        if st["event_created"]:
            track_ghosts[tid] = {"bbox": st["bbox"], "died_frame": frame_index}
        del track_states[tid]

    for tid in [
        t for t, g in track_ghosts.items()
        if frame_index - g["died_frame"] > GHOST_TTL_FRAMES
    ]:
        del track_ghosts[tid]


# =========================================================
# MAIN LOOP
# =========================================================
def main():
    ensure_directories()

    ffmpeg_ok             = ffmpeg_available()
    yolo_model, cnn_model = load_models()
    cap                   = cv2.VideoCapture(VIDEO_SOURCE)

    if not cap.isOpened():
        print(f"Could not open: {VIDEO_SOURCE}")
        return

    runtime_config = get_runtime_config()

    fps    = cap.get(cv2.CAP_PROP_FPS) or 20.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    line_y = int(height * 0.7)

    safe_width = max(width, 1)
    pre_frames = int(max(1, runtime_config["clip_duration_seconds"] // 2) * fps)

    frame_index      = 0
    frame_buffer     = deque(maxlen=pre_frames)
    pending_events   = []
    recent_crossings = []
    track_states     = {}
    track_ghosts     = {}

    # lane_cooldown: slot -> {"frame": int, "bbox": tuple}
    # Stores both timestamp AND bbox of the last crossing per slot so
    # check_lane_cooldown can gate suppression on IoU overlap rather
    # than elapsed frames alone.
    lane_cooldown = {}

    light_state = "RED"
    executor    = ThreadPoolExecutor(max_workers=MAX_BACKGROUND_SAVERS)

    print(f"BoT-SORT detector: {width}x{height} @ {fps:.1f}fps | line_y={line_y}")

    cv2.namedWindow("ITMS BoT-SORT Edge Feed", cv2.WINDOW_NORMAL)
    if DISPLAY_WIDTH and DISPLAY_HEIGHT:
        cv2.resizeWindow("ITMS BoT-SORT Edge Feed", DISPLAY_WIDTH, DISPLAY_HEIGHT)

    print(
        f"\n{'=' * 96}\n"
        f"FAST ASYNC EDGE DETECTOR - BOT-SORT + LATE-CATCH | {VIDEO_SOURCE}\n"
        f"   G=GREEN | R=RED | Q=Quit\n"
        f"   Crossing detection   : bbox bottom (y2) crossing line_y={line_y}\n"
        f"   Tracker              : Ultralytics BoT-SORT\n"
        f"   DB insert            : immediate on crossing / late-catch\n"
        f"   Video save           : background thread\n"
        f"   OCR                  : workers/ocr_registry_worker.py\n"
        f"   YOLO imgsz           : {YOLO_IMGSZ}\n"
        f"   Post-capture frames  : {POST_CAPTURE_FRAMES}\n"
        f"   Dedup window         : {GLOBAL_CROSSING_DEDUP_FRAMES} frames\n"
        f"   Ghost TTL            : {GHOST_TTL_FRAMES} frames\n"
        f"   Lane cooldown        : {LANE_COOLDOWN_FRAMES}f + IoU>={LANE_COOLDOWN_IOU_THRESH} "
        f"(distinct bbox = different car = allowed)\n"
        f"   Stop line colour     : black (avoids confusion with red vehicle boxes)\n"
        f"   detectDims stored    : yes ({width}x{height})\n"
        f"{'=' * 96}\n"
    )

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_index += 1
            raw_frame    = frame.copy()

            if frame_index == 1:
                h_actual, w_actual = raw_frame.shape[:2]
                if w_actual > 0:
                    safe_width = w_actual

            # Finalise completed events
            finished = [e for e in pending_events if e["remaining_frames"] <= 0]
            for event in finished:
                pending_events.remove(event)
                executor.submit(finalize_event_async, event, ffmpeg_ok, fps)

            for event in pending_events:
                event["frames"].append(raw_frame.copy())
                event["remaining_frames"] -= 1

            # Stop line drawn in black to avoid being confused with the red
            # vehicle bounding boxes which could affect YOLO detection quality.
            lc = (0, 0, 0) if light_state == "RED" else (0, 255, 0)
            cv2.line(frame, (0, line_y), (width, line_y), lc, 3)
            cv2.putText(
                frame,
                f"{light_state}: {'ACTIVE' if light_state == 'RED' else 'PAUSED'}",
                (10, line_y - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, lc, 2,
            )

            if light_state == "RED" and frame_index % TRACK_EVERY_N_FRAMES == 0:
                try:
                    results = yolo_model.track(
                        frame,
                        imgsz=YOLO_IMGSZ,
                        persist=True,
                        tracker="botsort.yaml",
                        classes=[2, 3, 5, 7],
                        conf=0.14,
                        iou=0.50,
                        verbose=False,
                    )
                except Exception as e:
                    print(f"BoT-SORT failed on frame {frame_index}: {e}")
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
                            x1 = max(0, min(width  - 1, x1))
                            y1 = max(0, min(height - 1, y1))
                            x2 = max(0, min(width  - 1, x2))
                            y2 = max(0, min(height - 1, y2))

                            if x2 <= x1 or y2 <= y1:
                                continue

                            bbox  = (x1, y1, x2, y2)
                            state = get_or_create_track_state(
                                track_states, track_id, bbox, frame_index, raw_frame,
                            )

                            crop = raw_frame[y1:y2, x1:x2]

                            if crop.size > 0 and (
                                state["pred_class"] is None
                                or frame_index - state["last_cls_update_frame"] >= 12
                            ):
                                try:
                                    pred_class, class_conf = classify_vehicle(cnn_model, crop)
                                    if pred_class != "civilian_car" and class_conf < 85.0:
                                        pred_class = "civilian_car"
                                    state["pred_class"]            = pred_class
                                    state["class_conf"]            = class_conf
                                    state["last_cls_update_frame"] = frame_index
                                except Exception as cls_err:
                                    print(f"CNN failed Track {track_id}: {cls_err}")

                            crossed_from_above = (
                                state["prev_y2"] is not None
                                and state["age"] >= MIN_TRACK_AGE_FOR_CROSSING
                                and state["prev_y2"] < (line_y - LINE_CROSS_MARGIN)
                                and state["y2"]  >= (line_y - LINE_CROSS_MARGIN)
                            )

                            late_visible_below_line = (
                                not crossed_from_above
                                and not state["event_created"]
                                and state["age"] >= MIN_TRACK_AGE_FOR_LATE_CATCH
                                and state["first_seen_y2"] is not None
                                and (line_y - LATE_CATCH_FIRST_SEEN_ABOVE_BUFFER)
                                    <= state["first_seen_y2"]
                                    <= (line_y + LATE_CATCH_FIRST_SEEN_BELOW_BUFFER)
                                and state["y2"] >= line_y
                                and state["y2"] <= (line_y + LATE_CATCH_MAX_BELOW_LINE)
                                and state["prev_y2"] is not None
                                and abs(state["y2"] - state["first_seen_y2"]) > 8
                            )

                            trigger_reason = None
                            if crossed_from_above:
                                trigger_reason = "crossed_from_above"
                            elif late_visible_below_line:
                                trigger_reason = "late_visible_below_line"

                            if not state["event_created"] and trigger_reason is not None:
                                pred_class   = state["pred_class"] or "civilian_car"
                                bbox         = state["bbox"]
                                cx, cy, w, h = box_features(bbox)

                                duplicate, reason = is_duplicate_crossing(
                                    recent_crossings, track_id, bbox, frame_index,
                                )

                                if not duplicate and is_ghost_reentry(track_ghosts, bbox):
                                    duplicate, reason = True, "ghost_reentry"

                                if not duplicate:
                                    slot = int(cx / safe_width * LANE_SLOTS)
                                    slot = max(0, min(LANE_SLOTS - 1, slot))
                                    # IoU-gated cooldown: only suppress if the new
                                    # bbox overlaps the stored one significantly.
                                    # A different vehicle in the same lane but at a
                                    # different screen position will have low IoU
                                    # and will NOT be suppressed.
                                    duplicate, reason = check_lane_cooldown(
                                        lane_cooldown, slot, frame_index, bbox
                                    )

                                # ---- FIRE EVENT ----------------------------
                                if not duplicate:
                                    state["crossed_line"]  = True
                                    state["event_created"] = True

                                    snapshot = state.get("best_snapshot")
                                    if snapshot is None:
                                        snapshot = state.get("snapshot")
                                    if snapshot is None and crop.size > 0:
                                        snapshot = crop.copy()

                                    if snapshot is None:
                                        continue

                                    pre_buffer_len = len(frame_buffer)

                                    violation_id = insert_violation_immediately(
                                        v_class=pred_class,
                                        conf=state["class_conf"] if state["class_conf"] else 97.0,
                                        frame_img=snapshot,
                                        event_bbox=bbox,
                                        track_id=track_id,
                                        trigger_reason=trigger_reason,
                                        event_frame_idx=pre_buffer_len,
                                        frame_width=width,
                                        frame_height=height,
                                    )

                                    if violation_id:
                                        event_id = int(time.time() * 1000) + track_id

                                        event = {
                                            "id":               event_id,
                                            "violation_id":     violation_id,
                                            "track_id":         track_id,
                                            "frames":           list(frame_buffer) + [raw_frame.copy()],
                                            "remaining_frames": POST_CAPTURE_FRAMES,
                                            "created_frame":    frame_index,
                                            "bbox":             bbox,
                                            "event_frame_idx":  pre_buffer_len,
                                        }

                                        pending_events.append(event)

                                        recent_crossings.append({
                                            "frame_index": frame_index,
                                            "track_id":    track_id,
                                            "bbox":        bbox,
                                            "cx":          cx,
                                            "cy":          cy,
                                            "w":           w,
                                            "h":           h,
                                        })

                                        # Store frame index AND bbox per slot.
                                        # check_lane_cooldown needs the bbox to
                                        # compute IoU against future crossings.
                                        slot = int(cx / safe_width * LANE_SLOTS)
                                        slot = max(0, min(LANE_SLOTS - 1, slot))
                                        lane_cooldown[slot] = {
                                            "frame": frame_index,
                                            "bbox":  bbox,
                                        }

                                        print(
                                            f"V-{violation_id} | Track={track_id} "
                                            f"reason={trigger_reason} slot={slot} "
                                            f"y2={state['y2']} line_y={line_y} "
                                            f"event_frame_idx={pre_buffer_len}"
                                        )

                                else:
                                    state["crossed_line"]  = True
                                    state["event_created"] = True
                                    print(
                                        f"Suppressed Track={track_id} "
                                        f"reason={reason} y2={state['y2']}"
                                    )

                            # -----------------------------------------------
                            # DRAW BOUNDING BOX + LABEL
                            # -----------------------------------------------
                            if state["event_created"]:
                                color = (0, 0, 255)
                                if state["pred_class"] and state["pred_class"] != "civilian_car":
                                    color = (0, 255, 0)

                                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                                label = f"ID {track_id}"
                                if state["pred_class"]:
                                    label += f" {state['pred_class']} {state['class_conf']:.0f}%"
                                label += f" y2={y2}"

                                cv2.putText(
                                    frame, label,
                                    (x1, max(20, y1 - 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2,
                                )

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
        print("BoT-SORT detector stopped.")


if __name__ == "__main__":
    main()