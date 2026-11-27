"""Sound effects: STRICT rules.

1. An effect is added only when it matches what happens at that moment of the Short. If nothing clearly
   matches, the Short gets no effect. When unsure, none.
     laughter in the transcript               -> "laugh"
     surprise ("no way", "what?!")            -> "surprise"  (a deep boom)
     a real reaction spike / excitement       -> "hit"       (an impact)
   These are the moments the editor already punches in on, so the effect lands with the zoom.
   Templates decide (`sfx` block); Minimal and Podcast have effects off.
2. No copyrighted sounds. By default every effect is synthesised with FFmpeg on your computer, so it has
   no rights holder. ("laugh" has no built-in version, so laughter gets no effect unless you add one.)
3. Your own sounds (optional): sounds you found yourself, e.g. on Myinstants
   (https://www.myinstants.com/en/index/in/), are used ONLY if you put them in the `cleared/` sub-folder
   of `sfx_library` (default ~/NeoClip-SFX/cleared/), which means you checked they are generic and free to
   use. Files whose names point to a movie, show, song, game, brand or meme source are skipped anyway.
   Myinstants sounds are user uploads with unknown rights and its terms do not allow automated searching
   or downloading, so the skill never fetches from the site. Every effect used is listed with its source
   in the summary and in YOUTUBE_METADATA.md.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import log, run, state_dir

KINDS = ("laugh", "surprise", "hit")
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"}
DEFAULTS = {"enabled": False, "kinds": ["hit"], "max_per_clip": 1, "gain_db": -18.0, "min_spike_z": 3.0}
MYINSTANTS_URL = "https://www.myinstants.com/en/index/in/"
KEYWORDS = {
    "laugh": ("laugh", "haha", "lol", "giggle"),
    "surprise": ("surprise", "bruh", "boom", "what", "huh", "wow", "gasp", "oh-no", "ohno"),
    "hit": ("hit", "impact", "punch", "bass", "slam", "thud"),
}
# names that point to copyrighted sources (films, TV, music, games, brands, memes of those): never used
BLOCKLIST = ("movie", "film", "tv", "series", "episode", "show", "song", "music", "remix", "lyrics", "ost",
             "soundtrack", "theme", "trailer", "official", "anime", "cartoon", "netflix", "disney", "marvel",
             "dc", "pixar", "nintendo", "mario", "pokemon", "zelda", "minecraft", "fortnite", "roblox", "gta",
             "valorant", "spongebob", "simpsons", "family guy", "star wars", "harry potter", "tiktok", "brand",
             "commercial", "ad ", "jingle", "singer", "rapper", "feat", "ft.", "dialogue", "quote", "voice line")
REASON_TO_KIND = {"laughter": "laugh", "surprise": "surprise", "excitement": "hit", "reaction": "hit"}

# FFmpeg lavfi recipes for the built-in effects (generated locally, so they carry no third-party licence)
_SYNTH = {
    "surprise": ("sine=f=70:d=0.7:r=48000,vibrato=f=6:d=0.2,volume=1.8,afade=t=in:d=0.01,"
                 "afade=t=out:st=0.05:d=0.65:curve=exp", 0.7),
    "hit": ("sine=f=55:d=0.35:r=48000,volume=1.6,afade=t=out:d=0.35:curve=exp,"
            "aformat=channel_layouts=mono", 0.35),
}


def settings(template: dict) -> dict:
    return {**DEFAULTS, **(template.get("sfx") or {})}


def plan_sfx(template: dict, edit: dict, audio: dict | None, clip: dict) -> list[dict]:
    """Effects that match a moment in this Short. Returns [{"kind", "t", "why"}] (output seconds), often []."""
    s = settings(template)
    if not s["enabled"] or int(s["max_per_clip"]) <= 0:
        return []
    allowed = set(s.get("kinds") or [])
    spikes = [sp for sp in (audio or {}).get("spikes", []) if clip["start"] <= sp["t"] <= clip["end"]]
    events: list[dict] = []
    for z in edit.get("zoom_events") or []:
        kind = REASON_TO_KIND.get(z["reason"])
        if kind not in allowed:
            continue
        if kind == "hit":
            # an impact only on a genuinely big reaction (a loud spike right at this moment)
            t_src = None
            for sp in spikes:
                ot = edit["tmap"].to_output_clamped(sp["t"])
                if abs(ot - (z["t"] + 0.12)) <= 0.6 and sp["z"] >= float(s["min_spike_z"]):
                    t_src = sp
                    break
            if t_src is None:
                continue
            strength = t_src["z"]
        else:
            strength = 2.0
        events.append({"kind": kind, "t": round(z["t"], 3), "why": f"{z['reason']} at this moment",
                       "strength": strength})
    events.sort(key=lambda e: -e["strength"])
    kept: list[dict] = []
    for e in events:
        if len(kept) >= int(s["max_per_clip"]):
            break
        if all(abs(e["t"] - k["t"]) >= 3.0 for k in kept):
            kept.append(e)
    dur = edit.get("output_duration") or 0
    return sorted([e for e in kept if e["t"] < max(0.0, dur - 0.5)], key=lambda e: e["t"])


def _duration(path: Path) -> float:
    try:
        out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                  timeout=30, check=False).stdout.decode().strip()
        return float(out or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def blocked(name: str) -> bool:
    n = " " + name.lower().replace("_", " ").replace("-", " ") + " "
    return any(f" {w.strip()} " in n or (len(w.strip()) > 4 and w.strip() in n) for w in BLOCKLIST)


def library_files(library: str | None, kind: str) -> list[Path]:
    """Only sounds the user cleared (in <library>/cleared/), matching the kind, and not from a blocked source."""
    if not library:
        return []
    root = Path(library).expanduser() / "cleared"
    if not root.is_dir():
        return []
    words = KEYWORDS.get(kind, (kind,))
    return sorted(p for p in root.rglob("*") if p.suffix.lower() in AUDIO_EXT
                  and any(w in p.parent.name.lower() or w in p.stem.lower() for w in words)
                  and not blocked(p.stem) and not blocked(p.parent.name))


def synth_file(kind: str) -> Path:
    cache = state_dir() / "sfx"
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"builtin_{kind}.wav"
    if not out.exists() or out.stat().st_size == 0:
        recipe, d = _SYNTH[kind]
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", recipe, "-t", f"{d}",
             "-ac", "2", "-ar", "48000", str(out)], timeout=60)
    return out


def resolve(events: list[dict], cfg: dict, seed: str) -> list[dict]:
    """Attach a file + source record to each planned effect. Effects with no suitable file are dropped."""
    out = []
    for i, e in enumerate(events):
        lib = [p for p in library_files(cfg.get("sfx_library"), e["kind"]) if 0 < _duration(p) <= 2.5]
        if lib:
            pick = lib[int(hashlib.sha1(f"{seed}:{i}".encode()).hexdigest(), 16) % len(lib)]
            out.append({**e, "path": str(pick), "name": pick.stem, "source": "your cleared sound folder",
                        "license": "cleared by you (the skill cannot verify sound rights)",
                        "copyright_risk": False})
        elif e["kind"] in _SYNTH:
            out.append({**e, "path": str(synth_file(e["kind"])), "name": f"built-in {e['kind']}",
                        "source": "built-in (synthesised with FFmpeg)", "license": "none needed",
                        "copyright_risk": False})
        # else: no matching sound available -> no effect (strict rule)
    if out:
        log("Sound effects: " + ", ".join(f"{e['kind']} @ {e['t']:.1f}s ({e['source']})" for e in out))
    return out
