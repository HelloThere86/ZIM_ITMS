import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

workers = [
    BASE_DIR / "ocr_registry_worker.py",
    BASE_DIR / "notification_worker.py",
]

processes = []

try:
    for worker in workers:
        print(f"Starting {worker.name}...")
        p = subprocess.Popen([sys.executable, str(worker)])
        processes.append(p)

    print("✅ Edge workers running. Press CTRL+C to stop.")

    for p in processes:
        p.wait()

except KeyboardInterrupt:
    print("\nStopping workers...")

    for p in processes:
        p.terminate()

    for p in processes:
        p.wait()

    print("Workers stopped.")