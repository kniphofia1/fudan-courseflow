"""Run iCourse once or at fixed local times inside the NAS container."""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

try:
    from bootstrap_models import ensure_models
except ModuleNotFoundError:  # imported as scripts.nas_scheduler in tests
    from scripts.bootstrap_models import ensure_models


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_run_times(raw: str) -> list[tuple[int, int]]:
    values: set[tuple[int, int]] = set()
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            hour_text, minute_text = item.split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
        except ValueError as exc:
            raise ValueError(f"Invalid RUN_TIMES entry: {item!r}") from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Invalid RUN_TIMES entry: {item!r}")
        values.add((hour, minute))
    if not values:
        raise ValueError("RUN_TIMES must contain at least one HH:MM value")
    return sorted(values)


def next_run(now: datetime, run_times: list[tuple[int, int]]) -> datetime:
    for hour, minute in run_times:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate
    hour, minute = run_times[0]
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)


@contextmanager
def exclusive_run_lock(path: str):
    """Yield whether this process acquired the non-blocking scheduler lock."""

    lock_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    os.chmod(lock_path, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(descriptor)


def run_command_with_retries(
    command: list[str], attempts: int, delay_seconds: float
) -> int:
    """Run a command with bounded retries, returning its final status."""

    attempts = max(1, attempts)
    last_status = 1
    for attempt in range(1, attempts + 1):
        result = subprocess.run(command, check=False)
        last_status = result.returncode
        if last_status == 0:
            return 0
        if attempt < attempts:
            print(
                f"[Scheduler] Attempt {attempt}/{attempts} exited {last_status}; "
                f"retrying in {delay_seconds:g}s",
                flush=True,
            )
            time.sleep(delay_seconds)
    return last_status


def run_once() -> int:
    command = [sys.executable, "-u", "main.py"]
    lock_path = os.environ.get("RUN_LOCK_PATH", "/app/data/.scheduler.lock")
    with exclusive_run_lock(lock_path) as acquired:
        if not acquired:
            print("[Scheduler] Another run holds the lock; skipping.", flush=True)
            return 0
        print(f"[Scheduler] Running: {' '.join(command)}", flush=True)
        status = run_command_with_retries(
            command,
            int(os.environ.get("RUN_RETRIES", "3")),
            float(os.environ.get("RETRY_DELAY_SECONDS", "60")),
        )
        print(f"[Scheduler] Run exited with code {status}", flush=True)
        return status


def main() -> int:
    ensure_models()
    mode = os.environ.get("RUN_MODE", "schedule").strip().lower()
    if mode == "once":
        return run_once()
    if mode != "schedule":
        raise ValueError(f"Unsupported RUN_MODE={mode!r}")

    run_times = parse_run_times(os.environ.get("RUN_TIMES", "13:00,22:00"))
    print(f"[Scheduler] Scheduled run times: {run_times}", flush=True)
    if env_bool("RUN_ON_STARTUP"):
        run_once()

    while True:
        now = datetime.now().astimezone()
        scheduled = next_run(now, run_times)
        seconds = max(1.0, (scheduled - now).total_seconds())
        print(f"[Scheduler] Next run at {scheduled.isoformat()} (sleep {seconds:.0f}s)", flush=True)
        time.sleep(seconds)
        run_once()


if __name__ == "__main__":
    raise SystemExit(main())
