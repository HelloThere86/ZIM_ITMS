# api/traffic_results.py
"""
FastAPI router for /api/traffic-results.

Reads from a JSON results file produced by your comparison script.
The file path is configurable via the RESULTS_FILE env var or
defaults to results/comparison_results.json relative to this file.
"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ── Path to the JSON file your comparison script writes ───────────────────────
RESULTS_FILE = Path(
    os.environ.get("RESULTS_FILE", Path(__file__).parent.parent / "results" / "comparison_results.json")
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class ModelResult(BaseModel):
    avgWaitPerStep:  float
    avgQueuePerStep: float
    throughput:      float
    runs:            int = 5


class TrafficResults(BaseModel):
    models:          dict[str, ModelResult]
    trainingRewards: list[dict] = []
    notes:           str = ""


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/traffic-results", response_model=TrafficResults)
def get_traffic_results():
    if not RESULTS_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Results file not found at {RESULTS_FILE}. Run the comparison script first."
        )

    try:
        with open(RESULTS_FILE, "r") as f:
            raw = json.load(f)
        return TrafficResults(**raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse results: {e}")