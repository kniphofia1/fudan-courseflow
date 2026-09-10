import os


def _read_secret(*env_names: str, file_env: str) -> str:
    """Read a Docker secret first, then fall back to legacy environment names."""

    secret_path = os.environ.get(file_env, "").strip()
    if secret_path:
        try:
            with open(secret_path, encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError as exc:
            raise RuntimeError(f"Unable to read {file_env}: {exc}") from exc
    for name in env_names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


STUDENT_ID = _read_secret("STUID", "StuId", file_env="STUID_FILE")
PASSWORD = _read_secret("UISPSW", "UISPsw", file_env="UISPSW_FILE")

WEBVPN_BASE = "https://webvpn.fudan.edu.cn"
IDP_BASE = "https://id.fudan.edu.cn"
ICOURSE_BASE = "https://icourse.fudan.edu.cn"

WEBVPN_AES_KEY = b"wrdvpnisthebest!"
WEBVPN_AES_IV = b"wrdvpnisthebest!"

TENANT_CODE = "222"
GROUP_CODE = "2095000001"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# LLM (ModelScope OpenAI-compatible API)
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
LLM_BASE_URL = "https://api-inference.modelscope.cn/v1/"
LLM_MODELS = [
    "ZhipuAI/GLM-5",
    "deepseek-ai/DeepSeek-V3.2",
    "MiniMax/MiniMax-M2.5",
    "Qwen/Qwen3.5-397B-A17B",
    "ZhipuAI/GLM-4.7"
]

# Gemini fallback (for content policy bypass)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-3-flash-preview"
]

# QQ SMTP
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "")
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465

# Database & Storage
DATA_DIR = os.environ.get("DATA_DIR", "data")
VIDEO_DIR = os.path.join(DATA_DIR, "videos")
DB_PATH = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "icourse.db"))

# Markdown export (used by the NAS deployment; harmless in GitHub Actions).
EXPORT_DIR = os.environ.get("EXPORT_DIR", "exports")
MARKDOWN_EXPORT_ENABLED = _env_bool("MARKDOWN_EXPORT_ENABLED", False)
EXPORT_TRANSCRIPT = _env_bool("EXPORT_TRANSCRIPT", True)
EXPORT_USE_EXISTING_COURSE_DIRS = _env_bool(
    "EXPORT_USE_EXISTING_COURSE_DIRS", False
)
EXPORT_COURSE_SUBDIR = os.environ.get("EXPORT_COURSE_SUBDIR", "")

# SenseVoice STT (sherpa-onnx)
SENSEVOICE_LANGUAGE = os.environ.get("SENSEVOICE_LANGUAGE", "auto").strip().lower()
if SENSEVOICE_LANGUAGE not in {"auto", "zh", "en", "yue", "ja", "ko"}:
    raise ValueError("SENSEVOICE_LANGUAGE must be auto, zh, en, yue, ja, or ko")
SENSEVOICE_MODEL_DIR = os.environ.get(
    "SENSEVOICE_MODEL_DIR",
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
)
SILERO_VAD_PATH = os.environ.get("SILERO_VAD_PATH", "silero_vad.onnx")

# 监控的课程 ID 列表
COURSE_IDS = [
    c.strip()
    for c in os.environ.get("COURSE_IDS", "").split(",")
    if c.strip()
]

# Optional automatic course discovery from the secret-free Canvas manifest.
COURSE_DISCOVERY_MODE = os.environ.get(
    "COURSE_DISCOVERY_MODE", "explicit"
).strip().lower()
ICOURSE_TERM_ID = os.environ.get("ICOURSE_TERM_ID", "")
COURSE_MANIFEST_PATH = os.environ.get(
    "COURSE_MANIFEST_PATH", "canvas-state/semester-courses.json"
)
COURSE_MAP_PATH = os.environ.get(
    "COURSE_MAP_PATH", os.path.join(DATA_DIR, "course-map.json")
)
CONFIRMED_COURSES_PATH = os.environ.get("CONFIRMED_COURSES_PATH", "")
