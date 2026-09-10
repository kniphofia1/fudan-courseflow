"""Container-side Canvas lock and retry wrapper, shared by cron and manual runs."""
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path


def main():
    os.umask(0o077)
    lock = Path("/data/.canvas-sync.lock")
    with lock.open("a") as handle:
        os.chmod(lock, 0o600)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[Canvas] Another sync holds the lock; skipping.", flush=True)
            return 0
        command = [sys.executable, "/usr/local/bin/refresh_and_run.py",
                   "--binary", "/usr/local/bin/canvas-downloader",
                   "--force-refresh-token", "--token-expires-after-days", "1",
                   "--", "-n", "-d", "/downloads"]
        for attempt in range(1, 4):
            status = subprocess.run(command, check=False).returncode
            if status == 0:
                return 0
            if attempt < 3:
                print(f"[Canvas] Attempt {attempt}/3 failed; retry in 60s.", flush=True)
                time.sleep(60)
        return status


if __name__ == "__main__":
    raise SystemExit(main())
