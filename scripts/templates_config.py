"""Editing templates: one shared engine, five configurations.

Each templates/<id>.md holds human guidance for the agent plus ONE fenced ```json block
with the machine configuration. That block is the single source of truth; user
customizations are stored as overrides in preferences.json and deep-merged on load.
"""
from __future__ import annotations

import json
import re
from typing import Any

from scripts.common import SKILL_ROOT, InputError
from scripts.config import deep_merge, load_preferences, update_preferences

TEMPLATES_DIR = SKILL_ROOT / "templates"
DEFAULT_TEMPLATE = "minimal-professional"
_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.S)

REQUIRED_KEYS = {"id", "name", "duration", "selection", "layout", "zoom", "captions",
                 "pause_removal", "transitions", "hook", "music"}


def list_templates() -> list[str]:
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.md"))


def _load_base(template_id: str) -> dict:
    path = TEMPLATES_DIR / f"{template_id}.md"
    if not path.exists():
        raise InputError(f"Unknown template '{template_id}'.",
                         f"Choose one of: {', '.join(list_templates())}")
    m = _JSON_BLOCK.search(path.read_text(encoding="utf-8"))
    if not m:
        raise InputError(f"Template {path.name} has no ```json configuration block.")
    cfg = json.loads(m.group(1))
    missing = REQUIRED_KEYS - cfg.keys()
    if missing:
        raise InputError(f"Template {template_id} is missing keys: {sorted(missing)}")
    return cfg


def load_template(template_id: str | None = None, extra_overrides: dict | None = None) -> dict:
    prefs = load_preferences()
    template_id = template_id or prefs.get("template") or DEFAULT_TEMPLATE
    cfg = _load_base(template_id)
    cfg = deep_merge(cfg, (prefs.get("template_overrides") or {}).get(template_id, {}))
    if extra_overrides:
        cfg = deep_merge(cfg, extra_overrides)
    validate_template(cfg)
    return cfg


def validate_template(cfg: dict) -> None:
    d = cfg["duration"]
    if not (5 <= d["min"] <= d["target"] <= d["max"] <= 180):
        raise InputError(f"Template {cfg['id']}: duration must satisfy 5 <= min <= target <= max <= 180 "
                         "(YouTube Shorts are at most 3 minutes).")
    if cfg["layout"]["mode"] not in {"gaming_stack", "face_track", "subject_track", "fit_blur"}:
        raise InputError(f"Template {cfg['id']}: unknown layout mode {cfg['layout']['mode']}")


def remember_template(template_id: str) -> None:
    _load_base(template_id)  # validates it exists
    update_preferences(template=template_id)


def _coerce(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def customize_template(template_id: str, assignments: list[str]) -> dict:
    """assignments like ['captions.uppercase=false', 'duration.max=55']"""
    base = _load_base(template_id)
    prefs = load_preferences()
    all_over = prefs.get("template_overrides") or {}
    over = all_over.get(template_id, {})
    for item in assignments:
        if "=" not in item:
            raise InputError(f"Bad setting '{item}'.", "Use dotted.key=value, e.g. captions.uppercase=false")
        key, raw = item.split("=", 1)
        parts = key.strip().split(".")
        probe = base
        for p in parts[:-1]:
            if not isinstance(probe, dict) or p not in probe:
                raise InputError(f"Unknown setting '{key}' for template {template_id}.")
            probe = probe[p]
        if parts[-1] not in probe:
            raise InputError(f"Unknown setting '{key}' for template {template_id}.")
        node = over
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = _coerce(raw.strip())
    all_over[template_id] = over
    merged = deep_merge(base, over)
    validate_template(merged)
    update_preferences(template_overrides=all_over)
    return merged


def reset_template(template_id: str) -> None:
    prefs = load_preferences()
    all_over = prefs.get("template_overrides") or {}
    all_over.pop(template_id, None)
    update_preferences(template_overrides=all_over)
