# api/plate_matcher.py
import re
from typing import List, Dict, Tuple

UK_PLATE_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{3}$")
ZW_CIVILIAN_RE = re.compile(r"^[A-Z]{3}\d{4}$")
ZW_POLICE_RE = re.compile(r"^ZRP\d{4}$")


def normalize_plate(plate: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (plate or "").upper())


def levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0

    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))

    for i, ca in enumerate(a, start=1):
        current = [i]

        for j, cb in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))

        previous = current

    return previous[-1]


def plate_format(plate: str) -> str:
    p = normalize_plate(plate)

    if UK_PLATE_RE.match(p):
        return "UK"
    if ZW_POLICE_RE.match(p):
        return "ZW_POLICE"
    if ZW_CIVILIAN_RE.match(p):
        return "ZW_CIVILIAN"

    return "UNKNOWN"


def position_weighted_score(ocr_plate: str, db_plate: str) -> float:
    ocr = normalize_plate(ocr_plate)
    db = normalize_plate(db_plate)

    if not ocr or not db:
        return -999.0

    score = 0.0
    max_len = max(len(ocr), len(db))

    for i in range(max_len):
        oc = ocr[i] if i < len(ocr) else ""
        dc = db[i] if i < len(db) else ""

        if oc == dc:
            score += 3.0
        elif oc and dc and oc.isalpha() == dc.isalpha():
            score += 0.5
        else:
            score -= 1.0

    distance = levenshtein_distance(ocr, db)
    score -= distance * 1.5

    if len(ocr) >= 2 and len(db) >= 2 and ocr[:2] == db[:2]:
        score += 2.0

    if len(ocr) >= 4 and len(db) >= 4 and ocr[-4:] == db[-4:]:
        score += 3.0

    if plate_format(ocr) != "UNKNOWN" and plate_format(ocr) == plate_format(db):
        score += 3.0

    return score


def find_similar_registered_plates(conn, ocr_plate: str, limit: int = 5) -> List[Dict]:
    ocr_plate = normalize_plate(ocr_plate)

    if not ocr_plate or ocr_plate == "UNKNOWN":
        return []

    rows = conn.execute(
        """
        SELECT plate_number
        FROM vehicle
        WHERE plate_number IS NOT NULL
        """
    ).fetchall()

    scored: List[Tuple[str, float, int, str]] = []

    for row in rows:
        db_plate = normalize_plate(row["plate_number"])

        if not db_plate or db_plate == "UNKNOWN" or db_plate == "UNKNOWNUNREGISTERED":
            continue

        score = position_weighted_score(ocr_plate, db_plate)
        distance = levenshtein_distance(ocr_plate, db_plate)
        fmt = plate_format(db_plate)

        if score >= 8.0 or distance <= 2:
            scored.append((db_plate, score, distance, fmt))

    scored.sort(key=lambda x: (x[1], -x[2]), reverse=True)

    return [
        {
            "plate": plate,
            "score": round(score, 2),
            "distance": distance,
            "format": fmt,
        }
        for plate, score, distance, fmt in scored[:limit]
    ]