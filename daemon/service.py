"""Daemon service management: start/stop/status via PID file.

Cross-platform: uses subprocess.Popen + PID file.
- Windows: taskkill /PID
- Unix: os.kill(SIGTERM)
"""

import logging
import os
import subprocess
import sys
import time

logger = logging.getLogger(__name__)

AGENT_DIR = os.path.join(os.path.dirname(__file__), "..")
PID_FILE = os.path.join(AGENT_DIR, "data", "daemon.pid")


def _read_pid() -> int | None:
    """Read PID from file, return None if missing or stale."""
    if not os.path.isfile(PID_FILE):
        return None
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        return None

    # Check if process is alive
    if _is_pid_alive(pid):
        return pid

    # Stale PID file
    _remove_pid()
    return None


def _write_pid(pid: int):
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(pid))


def _remove_pid():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
                encoding="utf-8", errors="ignore",
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)  # Signal 0 = check existence
            return True
        except OSError:
            return False


def start(config_path: str = "config/default.yaml", poll_interval: float = 5,
          verbose: bool = False) -> dict:
    """Start the daemon as a background subprocess.

    Returns {"ok": True, "pid": int} or {"ok": False, "error": str}.
    """
    existing = _read_pid()
    if existing:
        return {"ok": False, "error": f"Daemon already running (PID {existing})"}

    python = sys.executable
    daemon_script = os.path.join(os.path.dirname(__file__), "daemon.py")

    cmd = [python, daemon_script, "--config", config_path,
           "--poll-interval", str(poll_interval)]
    if verbose:
        cmd.append("--verbose")

    # Ensure log dir exists
    os.makedirs(os.path.join(AGENT_DIR, "logs"), exist_ok=True)

    # Launch detached
    kwargs = {
        "stdout": open(os.path.join(AGENT_DIR, "logs", "daemon_stdout.log"), "a"),
        "stderr": open(os.path.join(AGENT_DIR, "logs", "daemon_stderr.log"), "a"),
        "cwd": AGENT_DIR,
    }

    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        )
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)
    _write_pid(proc.pid)

    # Brief wait to check it didn't crash immediately
    time.sleep(0.5)
    if proc.poll() is not None:
        _remove_pid()
        return {"ok": False, "error": f"Daemon exited immediately (code {proc.returncode})"}

    logger.info("Daemon started (PID %d)", proc.pid)
    return {"ok": True, "pid": proc.pid}


def stop() -> dict:
    """Stop the running daemon.

    Returns {"ok": True} or {"ok": False, "error": str}.
    """
    pid = _read_pid()
    if not pid:
        return {"ok": False, "error": "Daemon is not running"}

    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=10,
            )
        else:
            os.kill(pid, signal_module.SIGTERM)
            # Wait up to 5s for graceful shutdown
            for _ in range(50):
                if not _is_pid_alive(pid):
                    break
                time.sleep(0.1)
            else:
                os.kill(pid, signal_module.SIGKILL)
    except Exception as e:
        _remove_pid()
        return {"ok": False, "error": str(e)}

    _remove_pid()
    logger.info("Daemon stopped (PID %d)", pid)
    return {"ok": True}


def status() -> dict:
    """Get daemon status.

    Returns {"running": bool, "pid": int|None}.
    """
    pid = _read_pid()
    return {"running": pid is not None, "pid": pid}


# Lazy import for signal on Unix (avoid import error on Windows for SIGKILL)
if sys.platform != "win32":
    import signal as signal_module
