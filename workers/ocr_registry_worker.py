import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["FLAGS_allocator_strategy"] = "auto_growth"
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import time
import json
import cv2
import sqlite3
import re
from collections import defaultdict
from pathlib import Path

from paddleocr import PaddleOCR

# =========================================================
# CONFIG
# =========================================================
BASE_DIR     = Path(__file__).resolve().parent.parent
DB_PATH      = BASE_DIR / "database" / "itms_production.db"
EVIDENCE_DIR = BASE_DIR / "dashboard" / "evidence"
DEBUG_DIR    = EVIDENCE_DIR / "debug_plates"

POLL_INTERVAL      = 2
VIDEO_WAIT_RETRIES = 5
VIDEO_WAIT_SLEEP   = 3

MIN_CONFIDENCE   = 45
MIN_READS        = 2
MAX_OCR_ATTEMPTS = 6

# =========================================================
# BBOX CROP SETTINGS
# =========================================================
# BBOX_PAD_BOTTOM = 0: never extend below the vehicle bbox.
# Downward padding was reading the plate of the car ahead of a tailgater.
BBOX_PAD_TOP    = 10
BBOX_PAD_BOTTOM = 0
BBOX_PAD_X      = 30

# Keep only the lower half of the vehicle crop — roof/windscreen not useful.
PLATE_ZONE_RATIO    = 0.50
FALLBACK_CROP_RATIO = 0.65

# =========================================================
# TEMPLATE MATCHING TRACKER
# =========================================================
# Biased downward — vehicle moves toward camera (increasing y).
TMPL_SEARCH_UP    = 15
TMPL_SEARCH_DOWN  = 60
TMPL_SEARCH_X     = 30
TMPL_MIN_SCORE    = 0.40
TMPL_VEHICLE_FRAC = 0.45

# =========================================================
# TWO-PASS OCR
# =========================================================
# Pass 1 skips the first CLEAR_ZONE_FRAMES after the event.
# This gives the car ahead time to move clear of the violating vehicle's plate.
CLEAR_ZONE_FRAMES = 30

# =========================================================
# PLATE FORMAT REGEXES
# =========================================================
ZW_PLATE_RE = re.compile(r'^[A-Z]{2,3}\d{3,4}$')     # Zimbabwe: ABC1234
UK_PLATE_RE = re.compile(r'^[A-Z]{2}\d{2}[A-Z]{3}$') # UK:       AB11ABC


def is_valid_plate(plate: str) -> bool:
    if not plate:
        return False
    return bool(ZW_PLATE_RE.match(plate)) or bool(UK_PLATE_RE.match(plate))


# =========================================================
# INIT OCR — paddleocr==2.7.3 / paddlepaddle==2.6.2
# =========================================================
print("🔧 Initialising PaddleOCR 2.7.3 ...")
ocr = PaddleOCR(
    use_angle_cls=True,
    lang='en',
    use_gpu=False,
    show_log=False,
)
print("✅ PaddleOCR 2.7.3 ready.")


# =========================================================
# DIRECTORY SETUP
# =========================================================
def ensure_directories():
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# DB HELPERS
# =========================================================
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def load_review_data(note: str) -> dict:
    if not note:
        return {}
    marker = "ReviewData="
    idx = note.find(marker)
    if idx == -1:
        try:
            return json.loads(note)
        except Exception:
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
# PLATE CLEANING  —  format-aware with A/M/W substitution
# =========================================================
#
# LETTER_FIXES — digit-lookalike → correct letter (applied in letter segment):
#   0→O  1→I  5→S  8→B  6→G  2→Z  7→T
#
# DIGIT_FIXES — letter-lookalike → correct digit (applied in digit segment):
#   O→0  I→1  S→5  B→8  A→4  G→6  Z→2  D→0  Q→0  T→7  L→1  U→0
#
# A/M/W SUBSTITUTION — applied at UK letter positions only:
#   A, M and W are visually similar on intersection camera footage,
#   especially in the area-code positions (0,1).
#   Example: AM51VSU → MW51VSU
#     Position 0: OCR read A, correct char is M → A→M swap
#     Position 1: OCR read M, correct char is W → M→W swap
#   The function tries each member of {A, M, W} as a replacement at each
#   letter position individually until a valid UK plate is produced.

LETTER_FIXES: dict[str, str] = {
    '0': 'O', '1': 'I', '5': 'S', '8': 'B',
    '6': 'G', '2': 'Z', '7': 'T',
}

DIGIT_FIXES: dict[str, str] = {
    'O': '0', 'I': '1', 'S': '5', 'B': '8',
    'A': '4', 'G': '6', 'Z': '2', 'D': '0',
    'Q': '0', 'T': '7', 'L': '1', 'U': '0',
}

# Letter positions within a 7-char UK plate (LLDDLLL)
_UK_LETTER_POSITIONS = {0, 1, 4, 5, 6}

# Characters that are visually confused with each other at letter positions
_AMW_CANDIDATES = {'A', 'M', 'W', 'Z', 'E'}


def _coerce_uk_chars(chars: list) -> str:
    """Apply per-position confusion fixes to a 7-char list and validate."""
    result = []
    for i, ch in enumerate(chars):
        if i in _UK_LETTER_POSITIONS:
            result.append(LETTER_FIXES.get(ch, ch))
        else:
            result.append(DIGIT_FIXES.get(ch, ch))
    coerced = "".join(result)
    return coerced if UK_PLATE_RE.match(coerced) else ""


def apply_uk_coercion(text: str) -> str:
    if len(text) != 7:
        return ""

    chars = list(text)

    # Attempt 1: standard fixes
    result = _coerce_uk_chars(chars)
    if result:
        return result

    # Attempt 2: single A/M/W swap at each letter position
    for pos in sorted(_UK_LETTER_POSITIONS):
        if chars[pos] not in _AMW_CANDIDATES:
            continue
        for replacement in sorted(_AMW_CANDIDATES - {chars[pos]}):
            swapped = chars.copy()
            swapped[pos] = replacement
            result = _coerce_uk_chars(swapped)
            if result:
                return result

    # Attempt 3: two simultaneous A/M/W swaps (catches AM→MW etc.)
    letter_positions = sorted(_UK_LETTER_POSITIONS)
    for i, pos_a in enumerate(letter_positions):
        for pos_b in letter_positions[i + 1:]:
            if chars[pos_a] not in _AMW_CANDIDATES and \
               chars[pos_b] not in _AMW_CANDIDATES:
                continue
            replacements_a = (
                sorted(_AMW_CANDIDATES - {chars[pos_a]})
                if chars[pos_a] in _AMW_CANDIDATES else [chars[pos_a]]
            )
            replacements_b = (
                sorted(_AMW_CANDIDATES - {chars[pos_b]})
                if chars[pos_b] in _AMW_CANDIDATES else [chars[pos_b]]
            )
            for rep_a in replacements_a:
                for rep_b in replacements_b:
                    swapped = chars.copy()
                    swapped[pos_a] = rep_a
                    swapped[pos_b] = rep_b
                    result = _coerce_uk_chars(swapped)
                    if result:
                        return result

    return ""


def apply_zw_coercion(text: str) -> str:
    """
    Zimbabwe format: left-to-right letter segment then digit segment.
    Letters appearing after the digit run (suffix) get letter fixes.
    """
    in_digit_segment = False
    result = []
    for ch in text:
        if not in_digit_segment:
            if ch.isdigit():
                in_digit_segment = True
                result.append(DIGIT_FIXES.get(ch, ch))
            else:
                result.append(LETTER_FIXES.get(ch, ch))
        else:
            if ch.isalpha():
                result.append(LETTER_FIXES.get(ch, ch))
            else:
                result.append(DIGIT_FIXES.get(ch, ch))
    return "".join(result)


def clean_plate(text: str) -> str:
    """
    Normalise raw OCR text and apply format-aware confusion fixes.

    1. Strip non-alphanumeric, uppercase.
    2. If 7 chars → try UK coercion (standard fixes + A/M/W substitution).
    3. Otherwise → Zimbabwe left-to-right segment coercion.
    """
    if not text:
        return ""
    text = re.sub(r'[^A-Z0-9]', '', text.upper())
    if not text:
        return ""

    if len(text) == 7:
        uk = apply_uk_coercion(text)
        if uk:
            return uk

    return apply_zw_coercion(text)


# =========================================================
# IMAGE PREPROCESSING
# =========================================================
def preprocess_for_ocr(frame):
    if frame is None or frame.size == 0:
        return frame
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    lab_eq = cv2.merge([clahe.apply(l), a, b])
    return cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)


# =========================================================
# PADDLEOCR READ
# =========================================================
def paddle_read(image):
    try:
        processed = preprocess_for_ocr(image)
        result = ocr.ocr(processed, cls=True)
        if not result or result[0] is None:
            return None, 0.0

        best_text = None
        best_conf = 0.0
        for line in result[0]:
            if not line or len(line) < 2:
                continue
            text_info = line[1]
            if not text_info or len(text_info) < 2:
                continue
            text     = text_info[0]
            conf_pct = float(text_info[1]) * 100.0
            cleaned  = clean_plate(text)
            if len(cleaned) >= 6 and conf_pct > best_conf:
                best_text = cleaned
                best_conf = conf_pct

        return best_text, best_conf

    except Exception as e:
        print(f"   ⚠️  OCR frame error: {e}")
        return None, 0.0


# =========================================================
# DEBUG PLATE SAVER
# =========================================================
def save_debug_crop(violation_id: int, frame_idx: int,
                    crop, label: str, plate_read: str):
    try:
        if crop is None or crop.size == 0:
            return
        plate_safe = re.sub(r'[^A-Z0-9]', '_', (plate_read or 'NOREAD').upper())
        filename   = f"V{violation_id}_f{frame_idx:03d}_{label}_{plate_safe}.jpg"
        annotated  = crop.copy()
        cv2.putText(
            annotated, plate_read or "NO READ",
            (4, max(20, annotated.shape[0] - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2,
        )
        cv2.imwrite(str(DEBUG_DIR / filename), annotated)
    except Exception:
        pass


# =========================================================
# BBOX HELPERS
# =========================================================
def scale_bbox(bbox, src_dims, dst_shape):
    if bbox is None or src_dims is None:
        return bbox
    dh, dw = dst_shape[:2]
    sw, sh = src_dims
    if sw == dw and sh == dh:
        return bbox
    x1, y1, x2, y2 = bbox
    return (int(x1*dw/sw), int(y1*dh/sh), int(x2*dw/sw), int(y2*dh/sh))


def clamp_bbox(bbox, frame_shape):
    fh, fw = frame_shape[:2]
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, fw - 1))
    y1 = max(0, min(y1, fh - 1))
    x2 = max(x1 + 1, min(x2, fw))
    y2 = max(y1 + 1, min(y2, fh))
    return (x1, y1, x2, y2)


def crop_to_plate_zone(frame, bbox):
    """
    Crop to the lower PLATE_ZONE_RATIO of the vehicle bbox.
    BBOX_PAD_BOTTOM = 0 prevents reading the plate of the car ahead.
    """
    if frame is None or bbox is None:
        return None, "no_bbox"
    fh, fw = frame.shape[:2]
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
    except (TypeError, ValueError):
        return None, "bad_bbox"

    x1 = max(0, x1 - BBOX_PAD_X)
    y1 = max(0, y1 - BBOX_PAD_TOP)
    x2 = min(fw, x2 + BBOX_PAD_X)
    y2 = min(fh, y2 + BBOX_PAD_BOTTOM)  # 0 — stay within vehicle bbox

    if x2 <= x1 or y2 <= y1:
        return None, "empty_bbox"

    region_h  = y2 - y1
    plate_top = y1 + int(region_h * (1.0 - PLATE_ZONE_RATIO))
    crop      = frame[max(0, plate_top):y2, x1:x2]
    return (crop if crop.size > 0 else None), "bbox"


def crop_fallback(frame):
    if frame is None:
        return None
    h = frame.shape[0]
    region = frame[int(h * FALLBACK_CROP_RATIO):, :]
    return region if region.size > 0 else None


# =========================================================
# TEMPLATE MATCHING TRACKER
# =========================================================
def build_template(frame, bbox):
    """Extract the lower TMPL_VEHICLE_FRAC of the bbox as a tracking template."""
    if frame is None or bbox is None:
        return None
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1 = max(0, x1);  y1 = max(0, y1)
    x2 = min(frame.shape[1], x2);  y2 = min(frame.shape[0], y2)
    h        = y2 - y1
    tmpl_top = y1 + int(h * (1.0 - TMPL_VEHICLE_FRAC))
    tmpl     = frame[tmpl_top:y2, x1:x2]
    return tmpl if tmpl.size > 0 else None


def search_for_template(frame, template, current_bbox):
    """
    Search for template in a downward-biased region around current_bbox.
    Returns the updated bbox, or current_bbox if match is below threshold.
    """
    if frame is None or template is None or current_bbox is None:
        return current_bbox

    fh, fw = frame.shape[:2]
    th, tw = template.shape[:2]
    if tw <= 0 or th <= 0:
        return current_bbox

    x1, y1, x2, y2 = [int(v) for v in current_bbox]
    bw = x2 - x1
    bh = y2 - y1

    sx1 = max(0,  x1 - TMPL_SEARCH_X)
    sy1 = max(0,  y1 - TMPL_SEARCH_UP)
    sx2 = min(fw, x2 + TMPL_SEARCH_X)
    sy2 = min(fh, y2 + TMPL_SEARCH_DOWN)

    if sx2 - sx1 < tw or sy2 - sy1 < th:
        return current_bbox

    search_region = frame[sy1:sy2, sx1:sx2]
    if search_region.shape[0] < th or search_region.shape[1] < tw:
        return current_bbox

    try:
        result = cv2.matchTemplate(search_region, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
    except Exception:
        return current_bbox

    if max_val < TMPL_MIN_SCORE:
        return current_bbox

    match_x       = sx1 + max_loc[0]
    match_y       = sy1 + max_loc[1]
    tmpl_offset_y = int(bh * (1.0 - TMPL_VEHICLE_FRAC))

    new_x1 = max(0,  match_x)
    new_y1 = max(0,  match_y - tmpl_offset_y)
    new_x2 = min(fw, new_x1 + bw)
    new_y2 = min(fh, match_y + th)

    return (new_x1, new_y1, new_x2, new_y2)


def track_vehicle_template(frames, event_bbox, event_frame_idx, detect_dims=None):
    """
    Initialise template on event_frame_idx and track the vehicle forward.
    Pre-event frames get the static event bbox.
    Returns dict[frame_idx → (x1,y1,x2,y2)].
    """
    n = len(frames)
    if not frames or event_bbox is None:
        return {i: event_bbox for i in range(n)}

    event_frame_idx = max(0, min(event_frame_idx, n - 1))
    init_frame      = frames[event_frame_idx]

    bbox = scale_bbox(event_bbox, detect_dims, init_frame.shape) \
           if detect_dims else event_bbox
    bbox = clamp_bbox(bbox, init_frame.shape)

    bboxes   = {i: bbox for i in range(event_frame_idx + 1)}
    template = build_template(init_frame, bbox)

    if template is None:
        for i in range(event_frame_idx + 1, n):
            bboxes[i] = bbox
        return bboxes

    th, tw = template.shape[:2]
    print(
        f"   🔍 Template tracking | init={event_frame_idx} "
        f"tmpl={tw}x{th} bbox={bbox} frames={n}"
    )

    current_bbox = bbox
    for i in range(event_frame_idx + 1, n):
        frame = frames[i]
        if frame is None:
            bboxes[i] = current_bbox
            continue
        new_bbox = search_for_template(frame, template, current_bbox)
        if new_bbox != current_bbox:
            fresh = build_template(frame, new_bbox)
            if fresh is not None and fresh.size > 0:
                template = fresh
            current_bbox = new_bbox
        bboxes[i] = current_bbox

    print(f"   ✅ Tracking done | final_bbox={current_bbox}")
    return bboxes


# =========================================================
# VIDEO FRAME LOADER — ALL frames (tracker needs continuity)
# =========================================================
def wait_for_video(path: Path) -> bool:
    for attempt in range(VIDEO_WAIT_RETRIES):
        if path.exists() and path.stat().st_size > 0:
            return True
        print(f"   ⏳ Waiting for {path.name} ({attempt + 1}/{VIDEO_WAIT_RETRIES})...")
        time.sleep(VIDEO_WAIT_SLEEP)
    return False


def load_video_frames(video_path: str) -> list:
    frames = []
    if not video_path:
        return frames
    p = Path(video_path)
    if not wait_for_video(p):
        print(f"   ❌ Video never appeared: {p.name}")
        return frames
    cap   = cv2.VideoCapture(str(p))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total == 0:
        cap.release()
        return frames
    print(f"   📽️  Loading all {total} frames from {p.name}")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()
    return frames


# =========================================================
# MULTI-FRAME OCR — two-pass
# =========================================================
def ocr_frame_set(frames, per_frame_bboxes, violation_id, label_prefix):
    """Run OCR on a set of frames using per-frame tracked bboxes."""
    scores = defaultdict(float)
    counts = defaultdict(int)
    peak   = 0.0

    for frame_idx, frame in enumerate(frames):
        this_bbox = per_frame_bboxes.get(frame_idx)
        region, _ = crop_to_plate_zone(frame, this_bbox)

        if region is not None and region.size > 0:
            plate, conf = paddle_read(region)
            save_debug_crop(violation_id, frame_idx, region,
                            label_prefix, plate or "NOREAD")
            if plate:
                scores[plate] += conf / 100.0
                counts[plate] += 1
                peak = max(peak, conf)
        else:
            # Fallback to bottom strip of full frame when bbox crop is empty
            fb = crop_fallback(frame)
            if fb is not None:
                plate_fb, conf_fb = paddle_read(fb)
                save_debug_crop(violation_id, frame_idx, fb,
                                f"{label_prefix}_fb", plate_fb or "NOREAD")
                if plate_fb:
                    scores[plate_fb] += conf_fb / 100.0
                    counts[plate_fb] += 1
                    peak = max(peak, conf_fb)

    return scores, counts, peak


def aggregate_reads_tracked(frames, event_bbox=None, violation_id=None,
                             event_frame_idx=None, detect_dims=None):
    """
    Two-pass OCR with template tracking.

    Pass 1 — CLEAR ZONE:
      Frames from (event_frame_idx + CLEAR_ZONE_FRAMES) onward.
      The car ahead has cleared; the violating vehicle's plate is visible.

    Pass 2 — FULL CLIP:
      Fallback if pass 1 produces nothing (short clip, still blocked, etc.).
    """
    if not frames:
        return "UNKNOWN", 0.0, 0, "no_read"

    if event_frame_idx is None:
        event_frame_idx = max(0, len(frames) // 4)

    per_frame_bboxes = track_vehicle_template(
        frames, event_bbox, event_frame_idx, detect_dims=detect_dims,
    )

    n = len(frames)

    # Pass 1: clear zone
    clear_start  = min(event_frame_idx + CLEAR_ZONE_FRAMES, n)
    clear_frames = frames[clear_start:]

    if clear_frames:
        clear_bboxes = {
            i: per_frame_bboxes.get(clear_start + i, event_bbox)
            for i in range(len(clear_frames))
        }
        s1, c1, p1 = ocr_frame_set(clear_frames, clear_bboxes,
                                    violation_id, "clear")
        if s1:
            best = max(s1, key=s1.get)
            if c1[best] >= MIN_READS:
                print(
                    f"   ✅ Pass 1 (clear zone, frames {clear_start}-{n}) "
                    f"→ plate={best} reads={c1[best]} peak={p1:.1f}%"
                )
                return best, p1, c1[best], "clear_zone"

    # Pass 2: full clip fallback
    print("   🔄 Pass 1 empty — full clip scan")
    s2, c2, p2 = ocr_frame_set(frames, per_frame_bboxes, violation_id, "full")

    if s2:
        best = max(s2, key=s2.get)
        return best, p2, c2[best], "full_clip"

    return "UNKNOWN", 0.0, 0, "no_read"


# =========================================================
# REGISTRY MATCHING
# =========================================================
def get_all_plates(conn) -> list:
    rows = conn.execute("SELECT plate_number FROM vehicle").fetchall()
    return [r["plate_number"] for r in rows]


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        return levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, c1 in enumerate(a):
        curr = [i + 1]
        for j, c2 in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def find_similar(plate: str, registry: list) -> list:
    matches = []
    for r in registry:
        dist = levenshtein(plate, r)
        if dist <= 2:
            matches.append({
                "plate":    r,
                "distance": dist,
                "score":    max(0, 100 - dist * 20),
            })
    return sorted(matches, key=lambda x: -x["score"])[:3]


# =========================================================
# CORE VIOLATION PROCESSOR
# =========================================================
def process_violation(v: dict):
    conn = get_db()
    try:
        review_data     = load_review_data(v.get("review_note", ""))
        event_bbox      = review_data.get("eventBbox")
        event_frame_idx = review_data.get("eventFrameIdx")
        detect_dims_raw = review_data.get("detectDims")
        detect_dims     = tuple(detect_dims_raw) if detect_dims_raw else None

        # ---- Attempt counter ------------------------------------------------
        ocr_attempts = int(review_data.get("ocrAttempts", 0)) + 1
        review_data["ocrAttempts"] = ocr_attempts

        if ocr_attempts > MAX_OCR_ATTEMPTS:
            review_data.update({
                "ocrStatus":      "MaxAttemptsReached",
                "registryStatus": "ManualReview",
                "ocrReliable":    False,
                "registered":     False,
            })
            conn.execute(
                "UPDATE violation SET status='Rejected', review_note=? "
                "WHERE violation_id=?",
                (rebuild_review_note(review_data), v["violation_id"]),
            )
            conn.commit()
            print(f"   🛑 V-{v['violation_id']}: max attempts → Rejected")
            return
        # ---------------------------------------------------------------------

        vid_filename = v.get("video_path")
        video_path   = EVIDENCE_DIR / vid_filename if vid_filename else None
        frames       = load_video_frames(str(video_path)) if video_path else []

        if not frames:
            print(
                f"   ⚠️  V-{v['violation_id']}: no frames "
                f"(attempt {ocr_attempts}) — will retry."
            )
            conn.execute(
                "UPDATE violation SET review_note=? WHERE violation_id=?",
                (rebuild_review_note(review_data), v["violation_id"]),
            )
            conn.commit()
            return

        plate, peak_conf, reads, crop_mode = aggregate_reads_tracked(
            frames,
            event_bbox=event_bbox,
            violation_id=v["violation_id"],
            event_frame_idx=event_frame_idx,
            detect_dims=detect_dims,
        )

        print(
            f"   🔎 V-{v['violation_id']} attempt={ocr_attempts} "
            f"crop={crop_mode} raw_plate={plate} "
            f"peak={peak_conf:.1f}% reads={reads} "
            f"event_frame_idx={event_frame_idx} total_frames={len(frames)} "
            f"[debug → evidence/debug_plates/V{v['violation_id']}_*.jpg]"
        )

        # ---- Registry lookup — always recomputed, never inherited -----------
        registry    = get_all_plates(conn)
        registered  = False
        suggestions = []
        if plate and plate != "UNKNOWN":
            registered = plate in registry
            if not registered:
                suggestions = find_similar(plate, registry)
        # ---------------------------------------------------------------------

        # ---- Decision -------------------------------------------------------
        plate_valid = is_valid_plate(plate)

        if peak_conf < MIN_CONFIDENCE or reads < MIN_READS or not plate_valid:
            # OCR not reliable enough — retry next poll
            ocr_status      = "LowConfidence"
            registry_status = "LowConfidence"
            new_db_status   = "Pending"
            ocr_reliable    = False
            existing        = v.get("plate_number", "")
            plate_to_write  = (
                existing
                if existing and existing not in
                   ("UNKNOWN-UNREGISTERED", "UNKNOWN", "", None)
                else "UNKNOWN-UNREGISTERED"
            )
            display_plate = "UNKNOWN"

        elif registered:
            # Exact registry match — auto-approve
            ocr_status      = "Success"
            registry_status = "ExactMatch"
            new_db_status   = "AutoApproved"
            ocr_reliable    = True
            plate_to_write  = plate
            display_plate   = plate

        else:
            # Valid plate format, not in registry.
            # Retrying the same video produces the same plate — pointless.
            # Move to Approved so an officer reviews it. The dashboard will
            # show the OCR plate and the similar-plates suggestions so the
            # officer can correct it if it was misread.
            ocr_status      = "Success"
            registry_status = "NoExactMatch"
            new_db_status   = "Pending"
            ocr_reliable    = True
            plate_to_write  = plate
            display_plate   = plate
        # ---------------------------------------------------------------------

        review_data.update({
            "ocrPlate":                display_plate,
            "ocrPeakConfidence":       round(peak_conf, 2),
            "ocrReads":                reads,
            "ocrReliable":             ocr_reliable,
            "ocrStatus":               ocr_status,
            "ocrMethod":               "PaddleOCR_2.7.3",
            "ocrCropMode":             crop_mode,
            "ocrAttempts":             ocr_attempts,
            "registered":              registered,
            "registryStatus":          registry_status,
            "similarRegisteredPlates": suggestions,
        })

        conn.execute(
            """
            UPDATE violation
            SET plate_number = ?,
                status       = ?,
                review_note  = ?
            WHERE violation_id = ?
            """,
            (plate_to_write, new_db_status,
             rebuild_review_note(review_data), v["violation_id"]),
        )
        conn.commit()

        icon = "✅" if registered else ("⏳" if new_db_status == "Pending" else "🔍")
        print(
            f"   {icon} V-{v['violation_id']}: plate={plate_to_write} "
            f"peak={peak_conf:.1f}% reads={reads} valid={plate_valid} "
            f"registered={registered} "
            f"attempt={ocr_attempts}/{MAX_OCR_ATTEMPTS} → {new_db_status}"
        )

    except Exception as e:
        try:
            conn.execute(
                "UPDATE violation SET review_note=? WHERE violation_id=?",
                (rebuild_review_note(review_data), v["violation_id"]),
            )
            conn.commit()
        except Exception:
            pass
        print(f"   ❌ process_violation V-{v['violation_id']}: {e}")
    finally:
        conn.close()


# =========================================================
# WORKER LOOP
# =========================================================
def run_worker():
    ensure_directories()

    print(
        f"\n{'=' * 70}\n"
        f"🔁 PaddleOCR 2.7.3 worker started\n"
        f"   DB            : {DB_PATH}\n"
        f"   Evidence      : {EVIDENCE_DIR}\n"
        f"   Debug crops   : {DEBUG_DIR}\n"
        f"   Poll          : every {POLL_INTERVAL}s\n"
        f"   Min conf      : {MIN_CONFIDENCE}%  |  Min reads : {MIN_READS}\n"
        f"   Max attempts  : {MAX_OCR_ATTEMPTS} (then → Rejected)\n"
        f"   Plate formats : Zimbabwe (ABC1234) | UK (AB11ABC)\n"
        f"   Bbox pad      : top={BBOX_PAD_TOP}px bottom={BBOX_PAD_BOTTOM}px "
        f"sides={BBOX_PAD_X}px\n"
        f"   Clear zone    : first {CLEAR_ZONE_FRAMES} post-event frames skipped "
        f"(pass 1), then full clip (pass 2)\n"
        f"   A/M/W swap    : enabled at UK letter positions (0,1,4,5,6)\n"
        f"   NoExactMatch  : → Approved for officer review (stops infinite retry)\n"
        f"{'=' * 70}\n"
    )

    while True:
        try:
            conn = get_db()
            rows = conn.execute(
                """
                SELECT violation_id, video_path, review_note, plate_number
                FROM   violation
                WHERE  status     = 'Pending'
                AND    video_path IS NOT NULL
                AND    (plate_number IS NULL
                        OR plate_number IN ('UNKNOWN-UNREGISTERED', 'UNKNOWN'))
                ORDER  BY violation_id ASC
                """
            ).fetchall()
            conn.close()

            if rows:
                print(f"📋 {len(rows)} violation(s) queued for OCR.")
                for v in rows:
                    process_violation(dict(v))

        except Exception as e:
            print(f"❌ Worker loop error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_worker()