"""Ensure the two speech-recognition model assets exist on NAS startup."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path


SENSEVOICE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"
)
VAD_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "silero_vad.onnx"
)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != root and root not in target.parents:
            raise RuntimeError(f"Unsafe model archive member: {member.name}")
    archive.extractall(destination, filter="data")


def ensure_models() -> None:
    model_dir = Path(
        os.environ.get(
            "SENSEVOICE_MODEL_DIR",
            "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
        )
    )
    vad_path = Path(os.environ.get("SILERO_VAD_PATH", "models/silero_vad.onnx"))
    model_file = model_dir / "model.int8.onnx"
    token_file = model_dir / "tokens.txt"
    if model_file.is_file() and token_file.is_file() and vad_path.is_file():
        print("[Bootstrap] Speech models are ready.")
        return
    if env_bool("SKIP_MODEL_DOWNLOAD"):
        raise RuntimeError(
            "SKIP_MODEL_DOWNLOAD=true but one or more speech model files are missing"
        )

    model_dir.parent.mkdir(parents=True, exist_ok=True)
    vad_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="icourse-models-") as directory:
        archive_path = Path(directory) / "sensevoice.tar.bz2"
        print("[Bootstrap] Downloading SenseVoice model archive.")
        urllib.request.urlretrieve(SENSEVOICE_URL, archive_path)
        with tarfile.open(archive_path, "r:bz2") as archive:
            _safe_extract(archive, model_dir.parent)
        print("[Bootstrap] Downloading Silero VAD model.")
        temporary_vad = Path(directory) / "silero_vad.onnx"
        urllib.request.urlretrieve(VAD_URL, temporary_vad)
        shutil.copy2(temporary_vad, vad_path)


if __name__ == "__main__":
    ensure_models()
