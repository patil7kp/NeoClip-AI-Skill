"""Single-pass FFmpeg render: trim/pause-removal -> layout/crop -> zoom -> captions -> fades -> encode.

Renders to a temporary file in the internal work folder. The pipeline only moves it into the
date folder after quality validation passes, so a crash or failed render never leaves a
half-written Short in the output and never overwrites an existing file.

Fallback ladder (used on render error or failed validation):
  attempt 1  full template (zooms, dynamic crop, captions)
  attempt 2  no zoom effects
  attempt 3  no zoom, static centre-weighted framing, faster preset
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.audio_processor import audio_filter
from scripts.caption_generator import ass_filter
from scripts.common import RenderError, atomic_write_text, ensure_disk_space, log, run
from scripts.smart_cropper import layout_filter
from scripts.video_cutter import trim_filter

PROFILES = [
    {"name": "full", "zoom": True, "static_layout": False, "preset": None, "hw": True},
    {"name": "no_zoom", "zoom": False, "static_layout": False, "preset": None, "hw": True},
    {"name": "safe", "zoom": False, "static_layout": True, "preset": "medium", "hw": False},
]
_HW_CACHE: dict = {}


def hardware_encoder(cfg: dict) -> str | None:
    """h264_videotoolbox (Apple) or h264_nvenc (NVIDIA) if FFmpeg has it and it actually works here."""
    if str(cfg.get("hw_encoder", "auto")).lower() in ("off", "false", "none", "no"):
        return None
    if "enc" in _HW_CACHE:
        return _HW_CACHE["enc"]
    found = None
    try:
        listing = run(["ffmpeg", "-hide_banner", "-encoders"], timeout=30, check=False).stdout.decode("utf-8", "replace")
        for enc in ("h264_videotoolbox", "h264_nvenc"):
            if enc in listing:
                probe = run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=s=256x256:d=0.2",
                             "-c:v", enc, "-f", "null", "-"], timeout=30, check=False)
                if probe.returncode == 0:
                    found = enc
                    break
    except Exception:  # noqa: BLE001 - any probing problem means software encoding
        found = None
    _HW_CACHE["enc"] = found
    return found


def video_codec_args(codec: str, cfg: dict, preset: str, out_w: int, out_h: int) -> list[str]:
    if codec == "h264_videotoolbox":
        mbps = 45 if out_w * out_h >= 2160 * 3840 else 16
        return ["-c:v", codec, "-b:v", f"{mbps}M", "-maxrate", f"{int(mbps * 1.5)}M",
                "-bufsize", f"{mbps * 2}M", "-profile:v", "high", "-allow_sw", "1"]
    if codec == "h264_nvenc":
        return ["-c:v", codec, "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", str(int(cfg.get("crf", 17)) + 2),
                "-b:v", "0", "-profile:v", "high"]
    args = ["-c:v", codec, "-preset", preset, "-crf", str(cfg.get("crf", 17))]
    if codec == "libx264":
        args += ["-profile:v", "high"]
    elif codec == "libx265":
        args += ["-tag:v", "hvc1"]
    return args


def output_fps(src_fps: float, max_fps: float) -> float:
    fps = src_fps if src_fps and src_fps > 1 else 30.0
    if fps > max_fps + 0.5:
        fps = max_fps if max_fps in (24, 25, 30, 50, 60) else 30.0
    return round(fps, 3)


def estimate_bytes(duration: float, out_w: int, out_h: int) -> int:
    mbps = 45 if out_w * out_h >= 2160 * 3840 else 14
    return int(duration * mbps * 1e6 / 8 * 2.2) + 50_000_000


def _static(layout: dict) -> dict:
    """Freeze dynamic crop paths at their median position (fallback profile)."""
    import copy
    lay = copy.deepcopy(layout)

    def med(kf):
        vals = sorted(v for _, v in kf)
        return f"{vals[len(vals) // 2]:.1f}" if vals else "0"
    if lay.get("crop"):
        lay["crop"]["x_expr"] = med(lay["crop"]["x_keyframes"])
        lay["crop"]["y_expr"] = med(lay["crop"]["y_keyframes"])
    if lay.get("gameplay"):
        lay["gameplay"]["x_expr"] = med(lay["gameplay"]["x_keyframes"])
    return lay


def build_command(*, source_path: str, source_start: float = 0.0, meta: dict, edit: dict, layout: dict,
                  captions_path: str | None, out_path: Path, out_w: int, out_h: int, fps: float, cfg: dict,
                  music: dict | None, profile: dict, graph_path: Path, encoder: str | None = None,
                  sfx: list[dict] | None = None) -> list[str]:
    keeps = edit["keeps"]
    offset = max(0.0, keeps[0][0] - 1.0)
    span = keeps[-1][1] - offset + 0.5
    has_audio = bool(meta.get("has_audio"))
    trim, vlab, alab = trim_filter(keeps, offset, has_audio)
    lay = _static(layout) if profile["static_layout"] else layout
    zoom = edit["zoom_expr"] if profile["zoom"] else None
    parts = [trim, layout_filter(lay, vlab, "[vlay]", out_w, out_h, fps, zoom)]
    dur = edit["output_duration"]
    post = []
    if captions_path:
        post.append(ass_filter(Path(captions_path), cfg.get("fontsdir")))
    if edit["fade_in"] > 0:
        post.append(f"fade=t=in:st=0:d={edit['fade_in']:.3f}")
    if edit["fade_out"] > 0:
        post.append(f"fade=t=out:st={max(0.0, dur - edit['fade_out']):.3f}:d={edit['fade_out']:.3f}")
    post.append("format=yuv420p")
    parts.append(f"[vlay]{','.join(post)}[vout]")
    music_idx = None
    # source_start: the file is a downloaded section that begins at this source time (fast YouTube mode)
    cmd = ["ffmpeg", "-y", "-nostdin", "-v", "error", "-ss", f"{max(0.0, offset - source_start):.3f}",
           "-t", f"{span:.3f}",
           "-i", source_path]
    if has_audio and music and music.get("used"):
        cmd += ["-stream_loop", "-1", "-i", music["track"]["path"]]
        music_idx = 1
    # effects tied to a zoom are dropped when the fallback profile has no zooms
    fx = [e for e in (sfx or []) if profile["zoom"]] if has_audio else []
    fx_first = None
    if fx:
        fx_first = 1 + (1 if music_idx is not None else 0)
        for e in fx:
            cmd += ["-i", e["path"]]
    if has_audio:
        parts.append(audio_filter(alab, "[aout]", dur, edit, cfg, music, music_idx, fx, fx_first,
                                  float(cfg.get("_sfx_gain_db", -18.0))))
    atomic_write_text(graph_path, ";\n".join(parts))
    codec = encoder or cfg.get("video_codec", "libx264")
    preset = profile["preset"] or cfg.get("preset", "slow")
    cmd += ["-filter_complex_script", str(graph_path), "-map", "[vout]"]
    if has_audio:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", cfg.get("audio_bitrate", "320k"), "-ar", "48000"]
    cmd += video_codec_args(codec, cfg, preset, out_w, out_h)
    cmd += ["-pix_fmt", "yuv420p", "-r", f"{fps:g}", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-movflags", "+faststart", "-t", f"{dur:.3f}"]
    cmd += [str(out_path)]
    return cmd


def render(*, source_path: str, source_start: float = 0.0, meta: dict, edit: dict, layout: dict, captions_path: str | None,
           tmp_dir: Path, out_w: int, out_h: int, cfg: dict, music: dict | None, profile: dict,
           name: str, sfx: list[dict] | None = None) -> dict:
    fps = output_fps(meta.get("fps", 30), cfg.get("max_fps", 60))
    ensure_disk_space(tmp_dir, estimate_bytes(edit["output_duration"], out_w, out_h))
    out_path = tmp_dir / f"{name}.partial.mp4"
    out_path.unlink(missing_ok=True)
    graph = tmp_dir / f"{name}.filtergraph.txt"
    hw = hardware_encoder(cfg) if profile.get("hw", True) else None
    encoders = [hw, None] if hw else [None]  # a hardware encoder failure falls back to software at once
    err, cmd, t0 = "", [], time.time()
    for enc in encoders:
        cmd = build_command(source_path=source_path, source_start=source_start, meta=meta, edit=edit,
                            layout=layout, captions_path=captions_path, out_path=out_path, out_w=out_w,
                            out_h=out_h, fps=fps, cfg=cfg, music=music, profile=profile, graph_path=graph,
                            encoder=enc, sfx=sfx)
        log(f"Rendering {name} [{profile['name']}, {enc or cfg.get('video_codec', 'libx264')}] "
            f"{out_w}x{out_h}@{fps:g} ({edit['output_duration']:.1f}s) ...")
        t0 = time.time()
        proc = run(cmd, timeout=None, check=False)
        if proc.returncode == 0 and out_path.exists():
            break
        err = proc.stderr.decode("utf-8", "replace")[-1500:]
        out_path.unlink(missing_ok=True)
    else:
        raise RenderError(f"FFmpeg render failed ({profile['name']}): {err.strip()}",
                          "The pipeline retries with simpler settings automatically.")
    return {"path": str(out_path), "fps": fps, "seconds": round(time.time() - t0, 1), "profile": profile["name"],
            "command": cmd, "filtergraph": str(graph)}
