"""Prepare private runtime files; never overwrite an existing file."""
import argparse
import getpass
import os
import re
from pathlib import Path


def create_private(path: Path, content: str) -> bool:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    return True


def initialize(root: Path, semester: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", semester):
        raise ValueError("semester must contain only letters, digits, '_' or '-'")
    os.umask(0o077)
    for relative in ("secrets", ".runtime", ".runtime/models",
                     f".runtime/canvas/{semester}/.state", f".runtime/icourse/{semester}"):
        (root / relative).mkdir(parents=True, exist_ok=True, mode=0o700)
    example = (root / ".env.example").read_text(encoding="utf-8")
    create_private(root / ".env", example.replace("SEMESTER_KEY=2026-fall", f"SEMESTER_KEY={semester}"))
    # Only a non-secret placeholder; every Canvas run refreshes it using SSO.
    create_private(root / f".runtime/canvas/{semester}/canvas-downloader.toml",
                   'canvas_url = "https://elearning.fudan.edu.cn"\ncanvas_token = "bootstrap-refresh-required"\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semester", default="2026-fall")
    parser.add_argument("--credentials", action="store_true", help="Prompt locally for missing UIS secrets")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    initialize(root, args.semester)
    if args.credentials:
        for filename, label in (("fudan_username", "UIS account"), ("fudan_password", "UIS password")):
            path = root / "secrets" / filename
            if path.exists():
                print(f"Keeping existing {filename}.")
                continue
            value = getpass.getpass(f"{label} (hidden): ").strip()
            if not value:
                raise SystemExit("Empty credential rejected.")
            create_private(path, value + "\n")
    print("Prepared private runtime. Edit .env before starting; existing files were kept.")


if __name__ == "__main__":
    main()
