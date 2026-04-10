import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DB_PATH = PROJECT_ROOT / "database" / "itms_production.db"

DEFAULT_CONFIG = {
    "clip_duration": "15s",
    "image_quality": "High",
    "auto_flag_threshold": "85",
    "review_threshold": "75",
}

def _get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _read_config_map():
    conn = _get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT config_key, config_value FROM system_config")
        rows = c.fetchall()
        config_map = {row["config_key"]: row["config_value"] for row in rows}
        return {**DEFAULT_CONFIG, **config_map}
    finally:
        conn.close()

def parse_duration_seconds(value: str, fallback: int = 15) -> int:
    try:
        cleaned = value.strip().lower().replace(" ", "")
        if cleaned.endswith("s"):
            return int(cleaned[:-1])
        return int(cleaned)
    except Exception:
        return fallback

def get_runtime_config():
    config_map = _read_config_map()

    clip_duration_seconds = parse_duration_seconds(config_map["clip_duration"], 15)

    image_quality_map = {
        "Low": 60,
        "Medium": 75,
        "High": 90,
        "Ultra": 100,
    }
    image_quality_name = config_map["image_quality"]
    jpeg_quality = image_quality_map.get(image_quality_name, 90)

    try:
        auto_flag_threshold = float(config_map["auto_flag_threshold"])
    except Exception:
        auto_flag_threshold = 85.0

    try:
        review_threshold = float(config_map["review_threshold"])
    except Exception:
        review_threshold = 75.0

    return {
        "clip_duration_label": config_map["clip_duration"],
        "clip_duration_seconds": clip_duration_seconds,
        "image_quality": image_quality_name,
        "jpeg_quality": jpeg_quality,
        "auto_flag_threshold": auto_flag_threshold,
        "review_threshold": review_threshold,
    }