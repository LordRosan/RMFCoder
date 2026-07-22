from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

RUNS_DIR = Path('runs')


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def events_file(run_id: str) -> Path:
    return run_dir(run_id) / 'events.jsonl'


def new_run_id() -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"{ts}-{suffix}"


def ensure_run_dir(run_id: str) -> Path:
    path = run_dir(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
