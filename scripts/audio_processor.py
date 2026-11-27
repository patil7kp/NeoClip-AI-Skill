"""Audio finishing: fades, loudness normalization, optional LICENSED music bed with ducking.

Music rules (enforced in code, not just docs):
  * Only tracks listed in a local music_library.json with `verified: true` and an allowed
    license are ever used. Nothing is downloaded automatically; no "trending" audio.
  * Original dialogue and sound effects are never replaced; music only sits underneath,
    ducked under speech by a sidechain compressor.
  * If no suitable verified track exists, the original audio is kept unchanged.
  * Attribution text is returned so it can be added to the Short's description.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import InputError, read_json, state_dir

ALLOWED_LICENSES = {
    "youtube-audio-library": "YouTube Audio Library track (check the per-track attribution requirement)",
    "cc0": "Creative Commons Zero / public domain dedication",
    "cc-by": "Creative Commons Attribution (attribution required)",
    "commercial-license": "Purchased/subscribed license that covers YouTube use (keep the license file)",
    "original": "Music you composed or own outright",
}
REQUIRED_TRACK_FIELDS = {"path", "title", "license", "source"}


def library_path(cfg: dict) -> Path:
    return Path(cfg.get("music_library") or state_dir() / "music_library.json").expanduser()


def load_library(cfg: dict) -> tuple[list[dict], list[str]]:
    """Return (usable tracks, warnings). Unverified or incomplete entries are skipped with a reason."""
    path = library_path(cfg)
    data = read_json(path, None)
    if data is None:
        return [], []
    tracks = data.get("tracks", data if isinstance(data, list) else [])
    usable, warnings = [], []
    for t in tracks:
        name = t.get("title") or t.get("path")
        missing = REQUIRED_TRACK_FIELDS - t.keys()
        if missing:
            warnings.append(f"music '{name}': missing {sorted(missing)}; skipped")
            continue
        if t["license"] not in ALLOWED_LICENSES:
            warnings.append(f"music '{name}': license '{t['license']}' is not in the allowed list; skipped")
            continue
        if not t.get("verified"):
            warnings.append(f"music '{name}': licensing terms not marked verified; skipped (never assume)")
            continue
        if t.get("attribution_required") or t["license"] == "cc-by":
            if not t.get("attribution_text"):
                warnings.append(f"music '{name}': attribution required but attribution_text is empty; skipped")
                continue
        p = Path(t["path"]).expanduser()
        if not p.is_absolute():
            p = path.parent / p
        if not p.exists():
            warnings.append(f"music '{name}': file not found at {p}; skipped")
            continue
        usable.append({**t, "path": str(p)})
    return usable, warnings


def decide_music(template: dict, audio: dict | None, clip: dict, speech_coverage: float, cfg: dict,
                 policy_music_overlap: bool) -> dict:
    mcfg = template["music"]
    mode = clip.get("music", mcfg.get("mode", "off"))
    if mode == "off":
        return {"used": False, "reason": "music disabled for this template/clip; original audio kept"}
    if not (audio or {}).get("has_audio") and mode != "always":
        return {"used": False, "reason": "source has no audio track; music would need a deliberate choice"}
    if policy_music_overlap:
        return {"used": False, "reason": "clip already contains possible music; not layering more"}
    if mode == "auto" and speech_coverage > float(mcfg.get("max_speech_coverage", 0.35)):
        return {"used": False, "reason": "dialogue carries the clip; background music not needed"}
    tracks, warnings = load_library(cfg)
    mood = clip.get("mood") or mcfg.get("default_mood")
    pick = None
    if clip.get("music_track"):
        pick = next((t for t in tracks if t["title"] == clip["music_track"]), None)
        if not pick:
            return {"used": False, "warnings": warnings,
                    "reason": f"requested track '{clip['music_track']}' is not a verified library entry"}
    else:
        ranked = sorted(tracks, key=lambda t: 0 if mood and mood in (t.get("moods") or []) else 1)
        pick = ranked[0] if ranked else None
    if not pick:
        return {"used": False, "warnings": warnings,
                "reason": "no verified licensed track available; original audio kept"}
    return {"used": True, "track": pick, "volume_db": float(mcfg.get("volume_db", -20)),
            "duck": bool(mcfg.get("duck", True)), "warnings": warnings,
            "attribution": pick.get("attribution_text"),
            "reason": f"licensed bed '{pick['title']}' ({pick['license']}) under original audio"}


def audio_filter(in_label: str, out_label: str, duration: float, plan: dict, cfg: dict,
                 music: dict | None, music_input_index: int | None) -> str:
    fi, fo = plan["audio_fade_in"], plan["audio_fade_out"]
    chain = (f"{in_label}afade=t=in:d={fi:.3f},afade=t=out:st={max(0.0, duration - fo):.3f}:d={fo:.3f},"
             f"loudnorm=I={cfg['loudness_lufs']}:TP={cfg['true_peak_db']}:LRA=11,"
             f"aresample=48000,aformat=channel_layouts=stereo")
    if not music or not music.get("used") or music_input_index is None:
        return f"{chain}{out_label}"
    vol = music["volume_db"]
    m = (f"[{music_input_index}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,aresample=48000,"
         f"aformat=channel_layouts=stereo,volume={vol}dB,afade=t=in:d=0.6,"
         f"afade=t=out:st={max(0.0, duration - 1.0):.3f}:d=1.0[mus]")
    if music.get("duck", True):
        return (f"{chain}[speech];[speech]asplit=2[sp_a][sp_b];{m};"
                f"[mus][sp_a]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=450[ducked];"
                f"[sp_b][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89{out_label}")
    return f"{chain}[speech];{m};[speech][mus]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89{out_label}"


def example_library() -> str:
    return json.dumps({"tracks": [{
        "path": "tracks/upbeat_loop.mp3", "title": "Example Track", "artist": "Artist Name",
        "source": "YouTube Audio Library", "license": "youtube-audio-library",
        "license_url": "https://www.youtube.com/audiolibrary", "attribution_required": False,
        "attribution_text": "", "moods": ["upbeat", "funny"], "verified": False,
        "verified_note": "Set verified=true only after reading this track's license terms yourself."}]}, indent=2)


def validate_track_entry(t: dict) -> None:
    missing = REQUIRED_TRACK_FIELDS - t.keys()
    if missing:
        raise InputError(f"Track entry missing {sorted(missing)}")
