"""Engine configuration and user preferences (persisted outside output folders).

Resolution order (later wins): DEFAULTS -> <state_dir>/config.json -> environment -> CLI flags.
Preferences (remembered template, caption preset, overrides) live in <state_dir>/preferences.json.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from scripts.common import atomic_write_json, file_lock, read_json, state_dir

DEFAULTS: dict[str, Any] = {
    "output_root": "YouTube_Shorts",       # relative paths resolve against the current directory
    "resolution": "2160x3840",             # 4K vertical target; use 1080x1920 for speed
    "max_fps": 60,
    "video_codec": "libx264",              # libx264 (most compatible) or libx265
    "crf": 17,
    "preset": "slow",
    "audio_bitrate": "320k",
    "loudness_lufs": -14.0,
    "true_peak_db": -1.0,
    "analysis_fps": 2.0,
    "face_detect_fps": 1.0,
    "whisper_model": "small",
    "whisper_device": "auto",              # auto | cpu | cuda
    "whisper_compute_type": "auto",
    "language": None,                      # None = auto-detect
    "transcribe_scope": "auto",            # full | candidates | auto (candidates for > 45 min)
    "download_max_height": 2160,
    "default_count": 3,
    "max_render_attempts": 3,
    "fontsdir": None,                      # folder with caption fonts; None = system fonts
    "music_library": None,                 # path to music_library.json (licensed tracks only)
    "ai": {"command": None, "timeout": 180},  # optional provider-agnostic LLM command (stdin->stdout)
    "caption_corrections": {},             # {"wrong": "right"} applied to transcripts
    "policy_extra_terms": {},              # {"category": ["term", ...]}
}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def config_path() -> Path:
    return state_dir() / "config.json"


def load_config(cli_overrides: dict | None = None) -> dict:
    cfg = deep_merge(DEFAULTS, read_json(config_path(), {}) or {})
    env_map = {
        "YT_SHORTS_OUTPUT_ROOT": "output_root",
        "YT_SHORTS_RESOLUTION": "resolution",
        "YT_SHORTS_WHISPER_MODEL": "whisper_model",
        "YT_SHORTS_AI_COMMAND": ("ai", "command"),
        "YT_SHORTS_MUSIC_LIBRARY": "music_library",
    }
    for env, key in env_map.items():
        if os.environ.get(env):
            if isinstance(key, tuple):
                cfg[key[0]][key[1]] = os.environ[env]
            else:
                cfg[key] = os.environ[env]
    cfg = deep_merge(cfg, {k: v for k, v in (cli_overrides or {}).items() if v is not None})
    return cfg


def parse_resolution(value: str) -> tuple[int, int]:
    try:
        w, h = (int(x) for x in str(value).lower().split("x"))
    except ValueError as exc:
        from scripts.common import InputError
        raise InputError(f"Bad resolution '{value}'.", "Use WIDTHxHEIGHT, e.g. 2160x3840.") from exc
    if w % 2 or h % 2 or w <= 0 or h <= 0:
        from scripts.common import InputError
        raise InputError(f"Resolution {value} must be positive even numbers.")
    return w, h


# --------------------------------------------------------------------------- preferences
def preferences_path() -> Path:
    return state_dir() / "preferences.json"


def load_preferences() -> dict:
    return read_json(preferences_path(), {}) or {}


def update_preferences(**changes: Any) -> dict:
    path = preferences_path()
    with file_lock(path):
        prefs = read_json(path, {}) or {}
        for k, v in changes.items():
            if v is None:
                prefs.pop(k, None)
            else:
                prefs[k] = v
        atomic_write_json(path, prefs)
    return prefs
