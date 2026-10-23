"""Desktop App Runner for SAHAM Analyzer.
Launches the in-process FastAPI analytical engine and opens the standalone desktop UI window.
"""
import sys
import os
import time
import threading
import subprocess
import webbrowser
import multiprocessing
from pathlib import Path

APP_URL = "http://127.0.0.1:8765"
HEALTH_URL = f"{APP_URL}/api/health"

# Log file in %TEMP%; rotate once it grows past ~2 MB so it never grows unbounded
log_path = Path(os.environ.get('TEMP', '.')) / "saham_app.log"
LOG_MAX_BYTES = 2 * 1024 * 1024
try:
    if log_path.is_file() and log_path.stat().st_size > LOG_MAX_BYTES:
        os.replace(log_path, log_path.with_name(log_path.name + ".1"))
except Exception:
    pass

# Safe stdout/stderr for windowed/consoleless app (prevents None.write error on Windows)
try:
    if sys.stdout is None:
        sys.stdout = open(log_path, 'a', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(log_path, 'a', encoding='utf-8')
except Exception:
    pass

# Multiprocessing freeze support for PyInstaller on Windows
multiprocessing.freeze_support()

def log(msg: str):
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%X')}] {msg}\n")
    except Exception:
        pass

log("Starting SAHAM App runner...")

BROWSER_CANDIDATES = [
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
]

uvicorn = None
app = None
server_instance = None

def import_engine() -> bool:
    """Import uvicorn + the engine. Importing engine.main starts the auto-scanner and Telegram
    threads, so this must only run after we know no other SAHAM instance is running."""
    global uvicorn, app
    try:
        import uvicorn as _uvicorn
        from engine.main import app as _app
        uvicorn, app = _uvicorn, _app
        log("FastAPI & uvicorn imported successfully.")
        return True
    except Exception:
        import traceback
        log(f"Import error: {traceback.format_exc()}")
        return False

def run_uvicorn():
    """Run uvicorn server in-process."""
    global server_instance
    try:
        log("Uvicorn starting on 127.0.0.1:8765...")
        config = uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning", access_log=False)
        server_instance = uvicorn.Server(config)
        server_instance.run()
        log("Uvicorn stopped cleanly.")
    except Exception as e:
        import traceback
        log(f"Server error: {traceback.format_exc()}")

def stop_uvicorn():
    global server_instance
    if server_instance is not None:
        server_instance.should_exit = True

def check_engine_ready(url: str = HEALTH_URL, retries: int = 35) -> bool:
    import urllib.request
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    log(f"Engine verified ready on attempt {i+1}.")
                    return True
        except Exception:
            time.sleep(0.2)
    return False

def engine_already_running(url: str = HEALTH_URL) -> bool:
    """Single probe: does another SAHAM instance already answer on port 8765?"""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False

def show_error_box(text: str):
    """Visible error for the windowed (console-less) build."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        MB_OK, MB_ICONERROR = 0x0, 0x10
        ctypes.windll.user32.MessageBoxW(None, text, "SAHAM", MB_OK | MB_ICONERROR)
    except Exception:
        pass

def find_app_browser():
    for p in BROWSER_CANDIDATES:
        if Path(p).is_file():
            return p
    return None

def get_browser_profile_dir() -> Path:
    p = Path(os.environ.get('LOCALAPPDATA', os.environ.get('TEMP', '.'))) / "SAHAM" / "browser_profile"
    p.mkdir(parents=True, exist_ok=True)
    return p

def app_window_cmd(browser_exe: str, app_url: str) -> list:
    return [
        browser_exe,
        f"--app={app_url}",
        f"--user-data-dir={get_browser_profile_dir()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        "--window-size=1440,900",
        "--window-position=50,50",
    ]

def open_existing_instance(app_url: str):
    """Another instance owns the engine: just open a window for it, don't wait for it."""
    browser_exe = find_app_browser()
    if browser_exe:
        try:
            subprocess.Popen(app_window_cmd(browser_exe, app_url))
            log(f"Opened app window for existing instance via {browser_exe}.")
            return
        except Exception as e:
            log(f"App window launch failed ({e}); falling back to default browser.")
    webbrowser.open(app_url)

def wait_for_window_close(proc=None):
    """Keep the engine alive while the desktop window lives (see engine/app_lifecycle.py).

    The Edge launcher process exiting is only a hint: Edge frequently hands the window to an
    existing browser process, and hidden windows have throttled timers. We stop only on a
    'bye' beacon, on browser-gone + long silence, or after a long silence safety net.
    """
    from engine import app_lifecycle
    started = time.time()
    proc_exited_at = None
    seen_bye = None
    log("Window lifecycle monitor active (heartbeat + bye beacon).")
    while True:
        time.sleep(2)
        now = time.time()
        if proc is not None and proc_exited_at is None and proc.poll() is not None:
            proc_exited_at = now
            log(f"Browser launcher process exited (code {proc.returncode}); waiting on UI heartbeat.")
        st = app_lifecycle.snapshot()
        if st["bye_at"] and st["bye_at"] != seen_bye:
            seen_bye = st["bye_at"]
            log("Window sent 'bye' (closing or reloading).")
        reason = app_lifecycle.exit_reason(now, started, st["last_seen"], st["bye_at"], proc_exited_at)
        if reason:
            log(f"Exiting: {reason}")
            break

def launch_desktop(app_url: str):
    browser_exe = find_app_browser()
    if browser_exe:
        log(f"Launching app mode: {browser_exe} with profile {get_browser_profile_dir()}")
        desktop_proc = subprocess.Popen(app_window_cmd(browser_exe, app_url))
        log(f"Browser PID={desktop_proc.pid} opened.")
        try:
            wait_for_window_close(desktop_proc)
        except KeyboardInterrupt:
            log("Interrupted by user.")
    else:
        log(f"Fallback to default browser for {app_url}")
        webbrowser.open(app_url)
        wait_for_window_close(None)

def main():
    log("Starting main()...")
    # 0. Single instance: if an engine already answers, just show its window and leave
    #    (before importing engine.main, which would start a second scanner + Telegram bot).
    if engine_already_running():
        log("Another SAHAM instance is already running; opening its window and exiting.")
        open_existing_instance(APP_URL)
        os._exit(0)

    if not import_engine():
        show_error_box(
            "SAHAM gagal dimuat.\n\n"
            f"Detail kesalahan ada di log:\n{log_path}\n(%TEMP%\\saham_app.log)"
        )
        os._exit(1)

    # 1. Start in-process Python backend thread
    server_thread = threading.Thread(target=run_uvicorn, daemon=True)
    server_thread.start()

    # 2. Wait for health check
    if not check_engine_ready():
        log("Engine failed to respond to health check.")
        show_error_box(
            "Mesin analisis SAHAM gagal dijalankan.\n\n"
            "Pastikan port 8765 tidak dipakai aplikasi lain, lalu coba lagi.\n"
            f"Detail kesalahan ada di log:\n{log_path}\n(%TEMP%\\saham_app.log)"
        )
        os._exit(1)

    log("Engine ready! Preparing browser window...")

    # 3. Launch Desktop Window
    try:
        launch_desktop(APP_URL)
    except KeyboardInterrupt:
        log("Interrupted by user.")
    except Exception:
        import traceback
        log(f"Desktop window error: {traceback.format_exc()}")
    finally:
        log("Stopping server...")
        stop_uvicorn()
        server_thread.join(timeout=3)
        log("SAHAM runner terminated.")
        # Hard exit: queued scan work and daemon threads (scanner, Telegram) must not keep a
        # hidden process alive after the window closes. SQLite WAL survives this safely.
        os._exit(0)

if __name__ == "__main__":
    main()
