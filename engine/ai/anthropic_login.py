"""Sign in to Claude with an Anthropic Console account (no API key to copy).

Uses the official Anthropic CLI (`ant`): `ant auth login` opens the browser, the user signs
in, and the CLI stores an OAuth profile under %APPDATA%\\Anthropic. The `anthropic` SDK picks
that profile up automatically when a client is created without an API key.

The CLI binary is downloaded on request from the official GitHub release, pinned to one
version, and accepted only when its SHA-256 matches the digest recorded here.
Note: this is a Claude Console (API) account billed per use - not a claude.ai Pro/Max
subscription.
"""
import hashlib
import io
import os
import sys
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

ANT_VERSION = "1.44.0"
_RELEASE = f"https://github.com/anthropics/anthropic-cli/releases/download/v{ANT_VERSION}"
# SHA-256 of the official release archives (GitHub release asset digests, v1.44.0)
ANT_SHA256 = {
    "amd64": "abb6b322f889adfbfc1529288006fb0dc717c8a7ca206fa652c8d2969424dfca",
    "arm64": "8e6307a913b5db9bcbb847405f8de87be2a3113057986884cd017688084c673a",
    "386": "0adc1693f7e4c2ab2ff7cbc50c7569ca604aed8c611051959c950cc54264b931",
}
DOWNLOAD_TIMEOUT = 120
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_lock = threading.Lock()
_state: Dict[str, Any] = {"installing": False, "install_error": None, "login_started_at": None,
                          "login_url": None, "login_log": None}


def install_dir() -> Path:
    """Per-user, writable even when SAHAM itself lives in Program Files."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "SAHAM" / "bin"


def _arch() -> str:
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("x86", "i386", "i686"):
        return "386"
    return "amd64"


def find_ant() -> Optional[str]:
    local = install_dir() / "ant.exe"
    if local.is_file():
        return str(local)
    return shutil.which("ant")


def verify_sha256(data: bytes, expected: str) -> bool:
    return hashlib.sha256(data).hexdigest().lower() == expected.lower()


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SAHAM-Desktop"})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
        return resp.read()


def install_ant() -> Dict[str, Any]:
    """Download, verify and unpack ant.exe (blocking; call from a thread)."""
    arch = _arch()
    name = f"ant_{ANT_VERSION}_windows_{arch}.zip"
    data = _download(f"{_RELEASE}/{name}")
    if not verify_sha256(data, ANT_SHA256[arch]):
        raise RuntimeError("Checksum ant.exe tidak cocok — unduhan dibatalkan demi keamanan.")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        member = next((n for n in zf.namelist() if n.lower().endswith("ant.exe")), None)
        if not member:
            raise RuntimeError("Arsip resmi tidak berisi ant.exe.")
        target_dir = install_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp = target_dir / "ant.exe.part"
        tmp.write_bytes(zf.read(member))
        os.replace(tmp, target_dir / "ant.exe")
    return {"path": str(install_dir() / "ant.exe"), "version": ANT_VERSION}


# The pinned CLI build (and the browser sign-in) is the Windows one; on a Linux server use an API key
SUPPORTED = sys.platform == "win32"
UNSUPPORTED_MSG = "Login akun Anthropic hanya tersedia di aplikasi desktop Windows. Di server, pakai mode API key."


def start_install() -> Dict[str, Any]:
    if not SUPPORTED:
        return {"started": False, "message": UNSUPPORTED_MSG}
    with _lock:
        if _state["installing"]:
            return {"started": False, "message": "Sedang memasang Anthropic CLI..."}
        _state.update(installing=True, install_error=None)

    def job():
        try:
            install_ant()
        except Exception as e:  # noqa: BLE001 - reported to the UI
            with _lock:
                _state["install_error"] = str(e)
        finally:
            with _lock:
                _state["installing"] = False

    threading.Thread(target=job, daemon=True, name="ant-install").start()
    return {"started": True, "message": f"Mengunduh Anthropic CLI v{ANT_VERSION} resmi..."}


def start_login() -> Dict[str, Any]:
    """Launch `ant auth login`; it opens the browser and waits for the sign-in to finish."""
    if not SUPPORTED:
        return {"ok": False, "message": UNSUPPORTED_MSG}
    ant = find_ant()
    if not ant:
        return {"ok": False, "message": "Anthropic CLI belum terpasang."}
    log_path = Path(tempfile.gettempdir()) / "saham_ant_login.log"
    log = open(log_path, "w", encoding="utf-8", errors="replace")
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    subprocess.Popen([ant, "auth", "login"], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     env=env, creationflags=_NO_WINDOW, close_fds=True)
    with _lock:
        _state.update(login_started_at=time.time(), login_url=None, login_log=str(log_path))
    return {"ok": True, "message": "Browser dibuka untuk login. Selesaikan login di browser, lalu kembali ke SAHAM."}


def _login_url_from_log() -> Optional[str]:
    path = _state.get("login_log")
    if not path or not os.path.exists(path):
        return None
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"https://\S+", text)
    return m.group(0).rstrip(".,)") if m else None


def logout() -> Dict[str, Any]:
    ant = find_ant()
    if not ant:
        return {"ok": False, "message": "Anthropic CLI belum terpasang."}
    subprocess.run([ant, "auth", "logout"], capture_output=True, timeout=30, creationflags=_NO_WINDOW)
    return {"ok": True, "message": "Logout akun Anthropic berhasil."}


def login_status() -> Dict[str, Any]:
    """Logged in = an SDK client without an API key can list models."""
    from . import claude_provider
    with _lock:
        st = dict(_state)
    ant = find_ant()
    out: Dict[str, Any] = {
        "cli_installed": bool(ant), "cli_path": ant, "cli_version": ANT_VERSION,
        "installing": st["installing"], "install_error": st["install_error"],
        "login_in_progress": bool(st["login_started_at"] and time.time() - st["login_started_at"] < 600),
        "login_url": _login_url_from_log(),
        "api_key_env_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "supported": SUPPORTED,
    }
    if not SUPPORTED:
        out.update(logged_in=False, message=UNSUPPORTED_MSG)
        return out
    probe = claude_provider.probe_login()
    out.update(probe)
    if probe.get("logged_in"):
        with _lock:
            _state["login_started_at"] = None
        out["login_in_progress"] = False
    return out
