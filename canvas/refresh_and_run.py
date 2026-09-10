#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import (
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from nas.semester import (
    SemesterDiscoveryError,
    TargetSemesterPending,
    discover_target_semester,
    inject_term_id,
)


DEFAULT_CANVAS_URL = "https://elearning.fudan.edu.cn"
DEFAULT_PURPOSE = "nas-canvas-downloader"
DEFAULT_STORAGE_STATE = ".state/playwright-storage.json"
TOKEN_LINE_RE = re.compile(
    r'(?m)^(\s*canvas_token\s*=\s*)("([^"\\]|\\.)*"|\'[^\']*\'|[^\n#]*)(\s*(?:#.*)?)$'
)
TOKEN_LIKE_RE = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9._~/-]{24,}\b")

_SECRET_VALUES: list[str] = []


class TokenState(Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass
class AppConfig:
    canvas_url: str
    canvas_token: str


@dataclass
class RuntimeOptions:
    config: Path
    binary: Path
    log_file: Path
    update_log_dir: Path
    storage_state: Path
    token_purpose: str
    token_expires_at: str | None
    force_refresh_token: bool
    headless: bool
    login_timeout_ms: int
    auto_yes: bool
    target_term_name: str
    course_manifest: Path
    downloader_args: list[str]


@dataclass(frozen=True)
class FileSnapshotEntry:
    size: int
    mtime_ns: int


FileSnapshot = dict[str, FileSnapshotEntry]


def register_secret(value: str | None) -> None:
    if value and len(value) >= 4 and value not in _SECRET_VALUES:
        _SECRET_VALUES.append(value)


def redact(text: str) -> str:
    redacted = text
    for secret in sorted(_SECRET_VALUES, key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    redacted = re.sub(
        r'((?:canvas_)?token["\']?\s*[:=]\s*["\']?)[A-Za-z0-9._~/-]{16,}',
        r"\1[REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"(Authorization:\s*Bearer\s+)[A-Za-z0-9._~/-]{16,}",
        r"\1[REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = RedactingFormatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    os.chmod(log_file, 0o600)


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def token_expiry_after_days(days: int) -> str | None:
    if days <= 0:
        return None
    return (datetime.now().astimezone() + timedelta(days=days)).replace(
        microsecond=0
    ).isoformat()


def read_secret(name: str, default_file: Path | None = None) -> str:
    direct = os.getenv(name)
    if direct:
        register_secret(direct)
        return direct

    file_env = os.getenv(f"{name}_FILE")
    file_path = Path(file_env) if file_env else default_file
    if file_path and file_path.exists():
        value = file_path.read_text(encoding="utf-8").strip()
        register_secret(value)
        return value

    raise RuntimeError(
        f"Missing {name}. Set {name}, {name}_FILE, or provide {default_file}."
    )


def read_app_config(path: Path) -> AppConfig:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    canvas_url = str(data.get("canvas_url") or DEFAULT_CANVAS_URL).rstrip("/")
    canvas_token = str(data.get("canvas_token") or "")
    register_secret(canvas_token)
    if not canvas_token:
        raise RuntimeError(f"canvas_token is missing in {path}")
    return AppConfig(canvas_url=canvas_url, canvas_token=canvas_token)


def write_canvas_token(config_path: Path, new_token: str) -> None:
    content = config_path.read_text(encoding="utf-8")
    if TOKEN_LINE_RE.search(content):
        updated = TOKEN_LINE_RE.sub(
            lambda match: f"{match.group(1)}{json.dumps(new_token)}{match.group(4)}",
            content,
            count=1,
        )
    else:
        suffix = "" if content.endswith("\n") else "\n"
        updated = f"{content}{suffix}canvas_token = {json.dumps(new_token)}\n"

    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp_path.write_text(updated, encoding="utf-8")
    os.replace(tmp_path, config_path)
    os.chmod(config_path, 0o600)
    register_secret(new_token)


def check_canvas_token(canvas_url: str, token: str) -> TokenState:
    url = f"{canvas_url.rstrip('/')}/api/v1/users/self"
    try:
        response = requests.get(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        logging.error("Token check failed with network error: %s", exc)
        return TokenState.UNKNOWN

    try:
        payload: Any = response.json()
    except ValueError:
        payload = None

    if response.ok and isinstance(payload, dict) and payload.get("id"):
        logging.info("Canvas token is valid for user id %s.", payload["id"])
        return TokenState.VALID

    if response.status_code in {401, 403, 404}:
        logging.warning(
            "Canvas token is invalid or revoked. status=%s body=%s",
            response.status_code,
            redact(response.text[:300]),
        )
        return TokenState.INVALID

    if response.ok:
        logging.warning(
            "Canvas token check returned unexpected JSON. status=%s body=%s",
            response.status_code,
            redact(response.text[:300]),
        )
        return TokenState.INVALID

    logging.error(
        "Canvas token check returned an unexpected status. status=%s body=%s",
        response.status_code,
        redact(response.text[:300]),
    )
    return TokenState.UNKNOWN


def wait_for_optional_selector(page: Page, selector: str, timeout_ms: int) -> bool:
    try:
        page.wait_for_selector(selector, timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False


def web_session_user_id(page: Page, canvas_url: str) -> str | None:
    if not page.url.startswith(canvas_url):
        return None
    result = page.evaluate(
        """
        async ({ canvasUrl }) => {
          const api = canvasUrl.replace(/\\/$/, "");
          const resp = await fetch(`${api}/api/v1/users/self`, {
            credentials: "include",
            headers: { "Accept": "application/json" }
          });
          const text = await resp.text();
          let json = null;
          try { json = JSON.parse(text); } catch (_) {}
          return {
            ok: resp.ok && json && json.id,
            status: resp.status,
            id: json && json.id,
            text: text.slice(0, 300)
          };
        }
        """,
        {"canvasUrl": canvas_url},
    )
    if result.get("ok"):
        return str(result["id"])
    logging.warning(
        "Canvas web session check failed. status=%s body=%s",
        result.get("status"),
        redact(str(result.get("text", ""))),
    )
    return None


def login_to_fudan(page: Page, canvas_url: str, username: str, password: str, timeout_ms: int) -> None:
    logging.info("Opening Canvas settings page to establish a web session.")
    page.goto(f"{canvas_url}/profile/settings", wait_until="domcontentloaded", timeout=timeout_ms)

    if wait_for_optional_selector(page, "#login-username", 5000):
        logging.info("Fudan SSO login form detected; submitting username/password.")
        page.locator("#login-username").fill(username)
        page.locator("#login-password").fill(password)
        try:
            page.wait_for_function(
                """
                () => {
                  const buttons = Array.from(document.querySelectorAll("button"));
                  const button = buttons.find((item) => /登录|login/i.test(item.innerText || ""));
                  return button && !button.disabled && !button.classList.contains("is-disabled");
                }
                """,
                timeout=10000,
            )
        except PlaywrightTimeoutError:
            logging.warning("Login button did not visibly become enabled; trying submit anyway.")

        submit = page.locator("button", has_text=re.compile("login|登录", re.IGNORECASE))
        if submit.count() == 0:
            submit = page.locator(".submitBtnColor")
        submit.first.click()

    try:
        page.wait_for_url(re.compile(r"^https://elearning\.fudan\.edu\.cn/"), timeout=timeout_ms)
    except PlaywrightTimeoutError as exc:
        current_url = page.url
        raise RuntimeError(
            "Fudan SSO did not return to Canvas. "
            f"Current URL is {current_url}. Manual verification may be required."
        ) from exc

    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    user_id = web_session_user_id(page, canvas_url)
    if not user_id:
        raise RuntimeError("Canvas web session was not established after Fudan SSO.")
    logging.info("Canvas web session is established for user id %s.", user_id)


def create_token_via_canvas_api(
    page: Page,
    canvas_url: str,
    purpose: str,
    expires_at: str | None,
) -> str | None:
    logging.info("Trying Canvas Access Tokens API through the authenticated web session.")
    result = page.evaluate(
        """
        async ({ canvasUrl, purpose, expiresAt }) => {
          const api = canvasUrl.replace(/\\/$/, "");
          const cookie = document.cookie.split("; ").find((item) => item.startsWith("_csrf_token="));
          const csrf = cookie ? decodeURIComponent(cookie.split("=").slice(1).join("=")) : "";

          const userResp = await fetch(`${api}/api/v1/users/self`, {
            credentials: "include",
            headers: { "Accept": "application/json" }
          });
          const userText = await userResp.text();
          let user = null;
          try { user = JSON.parse(userText); } catch (_) {}
          if (!userResp.ok || !user || !user.id) {
            return { ok: false, stage: "get_user", status: userResp.status, text: userText.slice(0, 500) };
          }

          const body = new URLSearchParams();
          body.set("token[purpose]", purpose);
          if (expiresAt) body.set("token[expires_at]", expiresAt);

          const tokenResp = await fetch(`${api}/api/v1/users/${user.id}/tokens`, {
            method: "POST",
            credentials: "include",
            headers: {
              "Accept": "application/json",
              "Content-Type": "application/x-www-form-urlencoded",
              "X-CSRF-Token": csrf
            },
            body: body.toString()
          });
          const tokenText = await tokenResp.text();
          let tokenJson = null;
          try { tokenJson = JSON.parse(tokenText); } catch (_) {}
          return {
            ok: tokenResp.ok && tokenJson && (tokenJson.token || tokenJson.visible_token),
            stage: "create_token",
            status: tokenResp.status,
            text: tokenText.slice(0, 500),
            json: tokenJson
          };
        }
        """,
        {
            "canvasUrl": canvas_url,
            "purpose": purpose,
            "expiresAt": expires_at,
        },
    )

    if result.get("ok") and result.get("json"):
        token_json = result["json"]
        token_value = token_json.get("token") or token_json.get("visible_token")
        token = str(token_value or "")
        if not token:
            return None
        register_secret(token)
        logging.info("Canvas Access Tokens API created a new token.")
        return token

    logging.warning(
        "Canvas Access Tokens API failed at %s with status %s: %s",
        result.get("stage"),
        result.get("status"),
        redact(str(result.get("text", ""))),
    )
    return None


def first_visible_locator(page: Page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except PlaywrightError:
            continue
        for index in range(count):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=500):
                    return item
            except PlaywrightError:
                continue
    return None


def extract_token_from_page(page: Page) -> str | None:
    candidates: list[str] = []
    values = page.evaluate(
        """
        () => Array.from(document.querySelectorAll("input, textarea"))
          .map((el) => el.value || el.textContent || "")
          .filter(Boolean)
        """
    )
    candidates.extend(str(value) for value in values)
    candidates.append(page.locator("body").inner_text(timeout=5000))

    for candidate in candidates:
        for match in TOKEN_LIKE_RE.findall(candidate):
            if len(match) >= 32 and not match.startswith("http"):
                register_secret(match)
                return match
    return None


def create_token_via_ui(
    page: Page,
    canvas_url: str,
    purpose: str,
    expires_at: str | None,
    timeout_ms: int,
) -> str | None:
    logging.info("Falling back to Canvas profile settings UI token creation.")
    page.goto(f"{canvas_url}/profile/settings", wait_until="domcontentloaded", timeout=timeout_ms)

    add_button = first_visible_locator(
        page,
        [
            "button:has-text('New Access Token')",
            "a:has-text('New Access Token')",
            "button:has-text('新访问令牌')",
            "a:has-text('新访问令牌')",
            "button:has-text('新建访问令牌')",
            "a:has-text('新建访问令牌')",
            ".add_access_token_link",
            "#new_access_token",
        ],
    )
    if add_button is None:
        logging.error("Could not find the New Access Token control in Canvas settings.")
        return None
    add_button.click()

    purpose_input = first_visible_locator(
        page,
        [
            "input[name='token[purpose]']",
            "textarea[name='token[purpose]']",
            "input[aria-label*='Purpose']",
            "textarea[aria-label*='Purpose']",
            "input[placeholder*='Purpose']",
            "textarea[placeholder*='Purpose']",
            "input[aria-label*='用途']",
            "textarea[aria-label*='用途']",
        ],
    )
    if purpose_input is not None:
        purpose_input.fill(purpose)

    if expires_at:
        expires_input = first_visible_locator(
            page,
            [
                "input[name='token[expires_at]']",
                "input[aria-label*='Expires']",
                "input[placeholder*='Expires']",
                "input[aria-label*='过期']",
                "input[placeholder*='过期']",
            ],
        )
        if expires_input is not None:
            expires_input.fill(expires_at)

    generate_button = first_visible_locator(
        page,
        [
            "button:has-text('Generate Token')",
            "button:has-text('Generate')",
            "button:has-text('生成')",
            "button:has-text('创建')",
        ],
    )
    if generate_button is None:
        logging.error("Could not find the Generate Token button in Canvas settings.")
        return None
    generate_button.click()
    page.wait_for_timeout(1500)

    token = extract_token_from_page(page)
    if token:
        logging.info("Canvas settings UI produced a new token.")
        return token

    logging.error("Could not extract a token from the Canvas settings UI.")
    return None


def refresh_canvas_token(options: RuntimeOptions, app_config: AppConfig) -> str:
    username = read_secret("FUDAN_USERNAME", Path("/run/secrets/fudan_username"))
    password = read_secret("FUDAN_PASSWORD", Path("/run/secrets/fudan_password"))

    options.storage_state.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(options.storage_state.parent, 0o700)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=options.headless)
        context_kwargs: dict[str, Any] = {}
        if options.storage_state.exists():
            context_kwargs["storage_state"] = str(options.storage_state)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            login_to_fudan(
                page,
                app_config.canvas_url,
                username,
                password,
                options.login_timeout_ms,
            )
            context.storage_state(path=str(options.storage_state))
            os.chmod(options.storage_state, 0o600)

            new_token = create_token_via_canvas_api(
                page,
                app_config.canvas_url,
                options.token_purpose,
                options.token_expires_at,
            )
            if not new_token:
                new_token = create_token_via_ui(
                    page,
                    app_config.canvas_url,
                    options.token_purpose,
                    options.token_expires_at,
                    options.login_timeout_ms,
                )
            if not new_token:
                raise RuntimeError("Unable to create a new Canvas token.")
            return new_token
        finally:
            context.close()
            browser.close()


def refresh_and_store_canvas_token(
    options: RuntimeOptions, app_config: AppConfig
) -> AppConfig | None:
    new_token = refresh_canvas_token(options, app_config)
    validation = check_canvas_token(app_config.canvas_url, new_token)
    if validation is not TokenState.VALID:
        logging.error("New token did not pass validation; keeping existing config.")
        return None
    write_canvas_token(options.config, new_token)
    logging.info("canvas-downloader.toml was updated with the new token.")
    return AppConfig(canvas_url=app_config.canvas_url, canvas_token=new_token)


def downloader_download_dir(args: list[str]) -> Path | None:
    for index, arg in enumerate(args):
        if arg in {"-d", "--dir", "--directory", "--download-dir"}:
            if index + 1 < len(args):
                return Path(args[index + 1])
            return None
        for prefix in ("--dir=", "--directory=", "--download-dir="):
            if arg.startswith(prefix):
                return Path(arg.removeprefix(prefix))
    return None


def snapshot_files(root: Path) -> FileSnapshot:
    snapshot: FileSnapshot = {}
    if not root.exists():
        return snapshot

    for path in root.rglob("*"):
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError as exc:
            logging.warning("Skipping %s while building update snapshot: %s", path, exc)
            continue

        try:
            relative_path = path.relative_to(root).as_posix()
        except ValueError:
            relative_path = path.as_posix()
        snapshot[relative_path] = FileSnapshotEntry(
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )
    return snapshot


def changed_files(before: FileSnapshot, after: FileSnapshot) -> tuple[list[str], list[str], list[str]]:
    before_paths = set(before)
    after_paths = set(after)
    added = sorted(after_paths - before_paths)
    deleted = sorted(before_paths - after_paths)
    modified = sorted(
        path
        for path in before_paths & after_paths
        if before[path] != after[path]
    )
    return added, modified, deleted


def markdown_file_list(paths: list[str]) -> str:
    if not paths:
        return "- None\n"
    return "".join(f"- `{path}`\n" for path in paths)


def unique_log_path(log_dir: Path, started_at: datetime) -> Path:
    base_name = started_at.strftime("%Y-%m-%d_%H-%M-%S")
    path = log_dir / f"{base_name}.md"
    suffix = 1
    while path.exists():
        path = log_dir / f"{base_name}-{suffix}.md"
        suffix += 1
    return path


def write_update_log(
    options: RuntimeOptions,
    download_dir: Path,
    before: FileSnapshot,
    after: FileSnapshot,
    started_at: datetime,
    finished_at: datetime,
    exit_code: int,
) -> None:
    added, modified, deleted = changed_files(before, after)
    options.update_log_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(options.update_log_dir, 0o700)
    log_path = unique_log_path(options.update_log_dir, started_at)
    content = (
        f"# Canvas sync {started_at.strftime('%Y-%m-%d %H:%M:%S %z')}\n\n"
        f"- Started: {started_at.isoformat(timespec='seconds')}\n"
        f"- Finished: {finished_at.isoformat(timespec='seconds')}\n"
        f"- Exit code: {exit_code}\n"
        f"- Download directory: `{download_dir.as_posix()}`\n"
        f"- Added: {len(added)}\n"
        f"- Modified: {len(modified)}\n"
        f"- Deleted: {len(deleted)}\n\n"
        "## Added\n\n"
        f"{markdown_file_list(added)}\n"
        "## Modified\n\n"
        f"{markdown_file_list(modified)}\n"
        "## Deleted\n\n"
        f"{markdown_file_list(deleted)}"
    )
    log_path.write_text(content, encoding="utf-8")
    os.chmod(log_path, 0o600)
    logging.info("Wrote update log to %s.", log_path)


def run_downloader_command(command: list[str], options: RuntimeOptions) -> int:
    if options.auto_yes:
        completed = subprocess.run(
            command,
            input="y\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output = redact(completed.stdout or "")
        if output:
            with options.log_file.open("a", encoding="utf-8") as log:
                log.write(output)
            print(output, end="" if output.endswith("\n") else "\n")
        return completed.returncode

    return subprocess.run(command, check=False).returncode


def run_downloader(
    options: RuntimeOptions, downloader_args: list[str] | None = None
) -> int:
    args = options.downloader_args if downloader_args is None else downloader_args
    if not args:
        args = shlex.split(os.getenv("CANVAS_DOWNLOADER_ARGS", ""))
    # The checked-in Rust CLI requires -c with JSON credentials; the NAS SSO
    # wrapper stores its refreshed token in TOML. Keep the adapter ephemeral.
    if any(arg in ("-c", "--credential-file") or arg.startswith("--credential-file=")
           or (arg.startswith("-c") and not arg.startswith("--")) for arg in args):
        raise ValueError("Downloader credentials are managed by the refresh wrapper")
    app_config = read_app_config(options.config)
    with tempfile.TemporaryDirectory(prefix="canvas-credentials-") as directory:
        credentials = Path(directory) / "credentials.json"
        with credentials.open("x", encoding="utf-8") as handle:
            os.chmod(credentials, 0o600)
            json.dump({"canvasUrl": app_config.canvas_url,
                       "canvasToken": app_config.canvas_token}, handle)
        command = [str(options.binary), "-c", str(credentials), *args]
        return run_downloader_with_log(command, args, options)


def run_downloader_with_log(
    command: list[str], args: list[str], options: RuntimeOptions
) -> int:
    logging.info("Running canvas-downloader: %s", " ".join(shlex.quote(part) for part in command))

    download_dir = downloader_download_dir(args)
    if download_dir is None:
        logging.warning("Could not detect download directory; skipping per-run update log.")
        return run_downloader_command(command, options)

    started_at = datetime.now().astimezone()
    before = snapshot_files(download_dir)
    code = run_downloader_command(command, options)
    finished_at = datetime.now().astimezone()
    after = snapshot_files(download_dir)
    write_update_log(options, download_dir, before, after, started_at, finished_at, code)
    return code


def run_once(options: RuntimeOptions) -> int:
    app_config = read_app_config(options.config)

    if options.force_refresh_token:
        logging.info("Force refreshing Canvas token.")
        refreshed = refresh_and_store_canvas_token(options, app_config)
        if refreshed is None:
            return 21
        app_config = refreshed

    else:
        state = check_canvas_token(app_config.canvas_url, app_config.canvas_token)

        if state is TokenState.UNKNOWN:
            logging.error("Refusing to refresh token because token status is unknown.")
            return 20

        if state is TokenState.INVALID:
            logging.info("Refreshing Canvas token.")
            refreshed = refresh_and_store_canvas_token(options, app_config)
            if refreshed is None:
                return 21
            app_config = refreshed

    downloader_args = options.downloader_args
    if options.target_term_name:
        try:
            term_id, manifest = discover_target_semester(
                app_config.canvas_url,
                app_config.canvas_token,
                options.target_term_name,
                options.course_manifest,
            )
        except TargetSemesterPending as exc:
            logging.info("Target semester pending: %s", exc)
            return 0
        except SemesterDiscoveryError as exc:
            logging.error("Target semester discovery failed: %s", exc)
            return 22
        try:
            downloader_args = inject_term_id(downloader_args, term_id)
        except ValueError as exc:
            logging.error("Unsafe downloader arguments: %s", exc)
            return 22
        logging.info(
            "Selected Canvas term %s (%s) with %s course(s).",
            manifest["term"]["name"],
            term_id,
            len(manifest["courses"]),
        )

    return run_downloader(options, downloader_args)


def parse_args() -> tuple[RuntimeOptions, int]:
    parser = argparse.ArgumentParser(
        description="Refresh Fudan Canvas token when needed, then run canvas-downloader."
    )
    parser.add_argument("--config", type=Path, default=Path("canvas-downloader.toml"))
    parser.add_argument("--binary", type=Path, default=Path("./canvas-downloader"))
    parser.add_argument("--log-file", type=Path, default=Path("sync.log"))
    parser.add_argument(
        "--update-log-dir",
        type=Path,
        default=Path(os.getenv("CANVAS_UPDATE_LOG_DIR", "log")),
        help="Directory for per-run Markdown file update logs.",
    )
    parser.add_argument("--storage-state", type=Path, default=Path(DEFAULT_STORAGE_STATE))
    parser.add_argument(
        "--token-purpose",
        default=os.getenv("CANVAS_TOKEN_PURPOSE", DEFAULT_PURPOSE),
    )
    parser.add_argument("--token-expires-at", default=os.getenv("CANVAS_TOKEN_EXPIRES_AT"))
    parser.add_argument(
        "--token-expires-after-days",
        type=int,
        default=env_int("CANVAS_TOKEN_EXPIRES_AFTER_DAYS", 0),
        help="Set token expiration to this many days from the current local time.",
    )
    parser.add_argument(
        "--force-refresh-token",
        action="store_true",
        default=env_bool("CANVAS_FORCE_REFRESH_TOKEN", False),
        help="Create and store a new Canvas token before every downloader run.",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        default=env_bool("FUDAN_CANVAS_HEADFUL", False),
        help="Run Chromium with a visible browser window.",
    )
    parser.add_argument(
        "--login-timeout-ms",
        type=int,
        default=env_int("FUDAN_LOGIN_TIMEOUT_MS", 90000),
    )
    parser.add_argument(
        "--no-auto-yes",
        action="store_true",
        default=not env_bool("CANVAS_DOWNLOADER_AUTO_YES", True),
        help="Do not send 'y' to canvas-downloader automatically.",
    )
    parser.add_argument(
        "--target-term-name",
        default=os.getenv("CANVAS_TARGET_TERM_NAME", ""),
        help="Discover this Canvas term name and reject stale explicit term IDs.",
    )
    parser.add_argument(
        "--course-manifest",
        type=Path,
        default=Path(
            os.getenv(
                "CANVAS_COURSE_MANIFEST",
                ".state/semester-courses.json",
            )
        ),
        help="Credential-free course manifest written after term discovery.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=env_int("RUN_INTERVAL_SECONDS", 0),
        help="Run forever with this many seconds between sync attempts.",
    )
    parser.add_argument("downloader_args", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    downloader_args = args.downloader_args
    if downloader_args and downloader_args[0] == "--":
        downloader_args = downloader_args[1:]

    token_expires_at = args.token_expires_at or token_expiry_after_days(
        args.token_expires_after_days
    )

    options = RuntimeOptions(
        config=args.config,
        binary=args.binary,
        log_file=args.log_file,
        update_log_dir=args.update_log_dir,
        storage_state=args.storage_state,
        token_purpose=args.token_purpose,
        token_expires_at=token_expires_at,
        force_refresh_token=args.force_refresh_token,
        headless=not args.headful,
        login_timeout_ms=args.login_timeout_ms,
        auto_yes=not args.no_auto_yes,
        target_term_name=args.target_term_name.strip(),
        course_manifest=args.course_manifest,
        downloader_args=downloader_args,
    )
    return options, args.interval_seconds


def main() -> int:
    options, interval_seconds = parse_args()
    configure_logging(options.log_file)

    if interval_seconds <= 0:
        return run_once(options)

    logging.info("Starting scheduled mode with interval_seconds=%s.", interval_seconds)
    while True:
        code = run_once(options)
        if code != 0:
            logging.error("Sync attempt failed with exit code %s.", code)
        logging.info("Sleeping for %s seconds.", interval_seconds)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
