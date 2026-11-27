"""Shared helpers: errors, subprocess, paths, atomic JSON, locking, time and interval math.

Every other module imports from here so behaviour (error codes, file safety,
timestamp formatting) is identical across the engine.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1


# --------------------------------------------------------------------------- errors
class SkillError(Exception):
    """Base error. `code` is stable and machine readable; `hint` tells the user what to do."""

    code = "skill_error"

    def __init__(self, message: str, hint: str = "", code: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        if code:
            self.code = code

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, "hint": self.hint}


class InputError(SkillError):
    code = "invalid_input"


class UnsupportedFormatError(SkillError):
    code = "unsupported_format"


class SourceUnavailableError(SkillError):
    code = "source_unavailable"


class RightsError(SkillError):
    code = "rights_not_confirmed"


class DependencyError(SkillError):
    code = "missing_dependency"


class TranscriptionError(SkillError):
    code = "transcription_failed"


class AIProviderError(SkillError):
    code = "ai_provider_error"


class RenderError(SkillError):
    code = "render_failed"


class ValidationFailed(SkillError):
    code = "validation_failed"


class DiskSpaceError(SkillError):
    code = "insufficient_disk_space"


class HistoryError(SkillError):
    code = "history_error"


# --------------------------------------------------------------------------- logging
_QUIET = os.environ.get("YT_SHORTS_QUIET") == "1"


def log(msg: str) -> None:
    """Progress goes to stderr so stdout stays clean JSON for agents."""
    if not _QUIET:
        print(f"[shorts] {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- subprocess
def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        hints = {
            "ffmpeg": "Install FFmpeg (https://ffmpeg.org/download.html; macOS: brew install ffmpeg; "
            "Windows: winget install Gyan.FFmpeg; Debian/Ubuntu: apt install ffmpeg).",
            "ffprobe": "ffprobe ships with FFmpeg; install FFmpeg.",
            "yt-dlp": "Install yt-dlp: pip install -U yt-dlp",
        }
        raise DependencyError(f"'{name}' was not found on PATH.", hints.get(name, f"Install {name}."))
    return path


def run(cmd: Sequence[str], timeout: float | None = None, check: bool = True,
        capture: bool = True, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    """Run a command without a shell. Raises DependencyError if the binary is missing."""
    require_binary(cmd[0])
    try:
        proc = subprocess.run(list(cmd), capture_output=capture, timeout=timeout, input=input_bytes)
    except subprocess.TimeoutExpired as exc:
        raise SkillError(f"Command timed out after {timeout}s: {cmd[0]}", code="timeout") from exc
    if check and proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace")[-2000:]
        raise SkillError(f"{cmd[0]} failed (exit {proc.returncode}): {err.strip()}", code="command_failed")
    return proc


# --------------------------------------------------------------------------- paths
def state_dir() -> Path:
    """Internal state lives OUTSIDE the user's output folders.

    Override with YT_SHORTS_STATE_DIR. Default: ~/.neoclip-ai
    """
    base = os.environ.get("YT_SHORTS_STATE_DIR")
    p = Path(base).expanduser() if base else Path.home() / ".neoclip-ai"
    p.mkdir(parents=True, exist_ok=True)
    return p


def work_dir(video_id: str) -> Path:
    p = state_dir() / "work" / safe_id(video_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_id(video_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", video_id)[:120]


# --------------------------------------------------------------------------- JSON + locking
def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        # Never silently discard a corrupt history file: keep a copy and fail loudly.
        backup = path.with_suffix(path.suffix + f".corrupt-{int(time.time())}")
        shutil.copy2(path, backup)
        raise HistoryError(f"{path} is not valid JSON ({exc}). A copy was saved to {backup}.",
                           "Restore it from the .bak file next to it, or delete it to start fresh.") from exc


def atomic_write_json(path: Path, data: Any) -> None:
    """Write via temp file + fsync + rename, keeping the previous version as .bak."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        _default_mode(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        _default_mode(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _default_mode(path: str) -> None:
    """mkstemp creates 0600 files; give user-facing files normal permissions (respecting umask)."""
    try:
        mask = os.umask(0)
        os.umask(mask)
        os.chmod(path, 0o666 & ~mask)
    except OSError:
        pass


@contextlib.contextmanager
def file_lock(path: Path, timeout: float = 30.0) -> Iterator[None]:
    """Cross-platform advisory lock using an O_EXCL lock file (stale after 10 min)."""
    lock = path.with_suffix(path.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 600:
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.time() > deadline:
                raise HistoryError(f"Timed out waiting for lock {lock}.",
                                   "Another run may be active. If not, delete the .lock file.")
            time.sleep(0.1)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


# --------------------------------------------------------------------------- time
def fmt_ts(seconds: float, millis: bool = False) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if millis:
        return f"{h:02d}:{m:02d}:{s:06.3f}"
    return f"{h:02d}:{m:02d}:{int(s):02d}"


def parse_ts(value: str | float | int) -> float:
    """Accept 75, 75.5, '1:15', '00:01:15', '00:01:15.250'."""
    if isinstance(value, (int, float)):
        return float(value)
    value = value.strip()
    if re.fullmatch(r"\d+(\.\d+)?", value):
        return float(value)
    parts = value.split(":")
    if not 2 <= len(parts) <= 3 or not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        raise InputError(f"Cannot parse timestamp '{value}'.", "Use seconds or HH:MM:SS(.mmm).")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total


def today() -> str:
    return _dt.date.today().isoformat()


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- text
def slugify(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    text = text[:max_len].rstrip("_")
    return text or "short"


# --------------------------------------------------------------------------- intervals
Interval = tuple[float, float]


def merge_intervals(items: Iterable[Sequence[float]], gap: float = 0.0) -> list[list[float]]:
    out: list[list[float]] = []
    for s, e in sorted((float(a), float(b)) for a, b in items if b > a):
        if out and s <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def subtract_intervals(base: Sequence[float], remove: Iterable[Sequence[float]]) -> list[list[float]]:
    s0, e0 = base
    result = [[float(s0), float(e0)]]
    for rs, re_ in merge_intervals(remove):
        nxt = []
        for s, e in result:
            if re_ <= s or rs >= e:
                nxt.append([s, e])
                continue
            if rs > s:
                nxt.append([s, rs])
            if re_ < e:
                nxt.append([re_, e])
        result = nxt
    return [r for r in result if r[1] - r[0] > 1e-6]


def overlap(a: Sequence[float], b: Sequence[float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def total_overlap(a: Sequence[float], others: Iterable[Sequence[float]]) -> float:
    return sum(overlap(a, o) for o in merge_intervals(others))


# --------------------------------------------------------------------------- disk
def ensure_disk_space(path: Path, needed_bytes: int, what: str = "rendering") -> None:
    path = Path(path)
    probe = path if path.exists() else path.parent
    while not probe.exists():
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free < needed_bytes:
        raise DiskSpaceError(
            f"Not enough disk space for {what}: need ~{needed_bytes / 1e9:.1f} GB, "
            f"{free / 1e9:.1f} GB free at {probe}.",
            "Free up space, choose another --output-root / YT_SHORTS_STATE_DIR, or render at 1080x1920.")
