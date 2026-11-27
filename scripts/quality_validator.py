"""Automated quality validation for a rendered Short.

Checks (each reported pass/fail with detail):
  exists, decodable (full decode, no errors), duration, resolution, 9:16 aspect, codec/pix_fmt,
  audio present when expected, A/V stream alignment, black frames, letterbox/empty bars,
  frozen video (warning), captions present/inside safe zone/inside duration.
`passed` is False if any *required* check fails. Warnings never fail a clip.
CLI: python scripts/quality_validator.py <file.mp4> [--width 2160 --height 3840 --duration 42.5]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import run


def _probe_streams(path: Path) -> dict:
    proc = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
               timeout=60, check=False)
    if proc.returncode != 0:
        return {}
    return json.loads(proc.stdout or b"{}")


def _filter_scan(path: Path, vf: str, timeout: float = 900) -> str:
    proc = run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "info", "-i", str(path), "-vf", vf, "-an",
                "-f", "null", "-"], timeout=timeout, check=False)
    return proc.stderr.decode("utf-8", "replace")


def validate(path: Path | str, *, width: int, height: int, expected_duration: float | None,
             expect_audio: bool, captions: dict | None = None, duration_tolerance: float = 0.35) -> dict:
    path = Path(path)
    checks: list[dict] = []

    def check(name, ok, detail="", required=True):
        checks.append({"name": name, "passed": bool(ok), "required": required, "detail": detail})
        return ok

    if not check("file_exists", path.exists() and path.stat().st_size > 1024,
                 f"{path.stat().st_size if path.exists() else 0} bytes"):
        return _result(checks)
    info = _probe_streams(path)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not check("probe_ok", v is not None, "ffprobe found a video stream" if v else "no video stream"):
        return _result(checks)

    dec = run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-f", "null", "-"], timeout=900, check=False)
    errs = [ln for ln in dec.stderr.decode("utf-8", "replace").splitlines() if ln.strip()]
    check("decodes_cleanly", dec.returncode == 0 and not errs, "; ".join(errs[:3]) or "full decode OK")

    dur = float((info.get("format") or {}).get("duration") or v.get("duration") or 0)
    if expected_duration:
        check("duration", abs(dur - expected_duration) <= max(duration_tolerance, expected_duration * 0.02),
              f"{dur:.2f}s (expected {expected_duration:.2f}s)")
    check("shorts_length", 1.0 <= dur <= 180.0, f"{dur:.1f}s (Shorts: up to 3 minutes)")
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    check("resolution", (w, h) == (width, height), f"{w}x{h} (expected {width}x{height})")
    check("aspect_9_16", h > 0 and abs(w / h - 9 / 16) < 0.01, f"{w}:{h}")
    check("codec", v.get("codec_name") in ("h264", "hevc") and v.get("pix_fmt") == "yuv420p",
          f"{v.get('codec_name')} {v.get('pix_fmt')}")
    if expect_audio:
        check("audio_present", a is not None, a.get("codec_name") if a else "missing audio stream")
        if a is not None:
            vd = float(v.get("duration") or dur)
            ad = float(a.get("duration") or dur)
            vs = float(v.get("start_time") or 0)
            as_ = float(a.get("start_time") or 0)
            check("av_sync", abs(vd - ad) <= 0.15 and abs(vs - as_) <= 0.05,
                  f"video {vs:.3f}+{vd:.3f}s, audio {as_:.3f}+{ad:.3f}s")
    # black frames (ignore intentional fades at the very start/end)
    # one pass for black frames, frozen video and letterboxing
    log = _filter_scan(path, "blackdetect=d=0.4:pix_th=0.10,freezedetect=n=0.002:d=4,"
                             "cropdetect=limit=24:round=2:reset=1")
    blacks = [(float(s), float(e)) for s, e in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)]
    bad = [(s, e) for s, e in blacks if not (e <= 0.5 or s >= dur - 0.6)]
    check("no_black_frames", not bad, ", ".join(f"{s:.1f}-{e:.1f}s" for s, e in bad) or "none")
    # letterbox / empty bars: cropdetect should find (almost) the full frame
    crops = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", log)
    if crops:
        cw = sorted(int(c[0]) for c in crops)[len(crops) // 2]
        ch = sorted(int(c[1]) for c in crops)[len(crops) // 2]
        check("no_empty_bars", cw >= 0.96 * w and ch >= 0.96 * h, f"median active area {cw}x{ch} of {w}x{h}")
    freezes = re.findall(r"freeze_start: ([\d.]+)", log)
    check("no_frozen_video", not freezes, f"frozen from {', '.join(freezes)}s" if freezes else "none", required=False)
    if captions is not None:
        n = captions.get("events", 0)
        if captions.get("expected", True):
            check("captions_present", n > 0, f"{n} caption events")
        if n:
            l, t, r, b = captions["safe_zone"]
            y = captions["position_y"]
            check("captions_in_safe_zone", t <= y <= b and l <= captions["position_x"] <= r, f"centre y={y:.2f}")
            last = captions.get("last") or 0
            check("captions_within_duration", last <= dur + 0.05, f"last caption ends {last:.2f}s")
    return _result(checks, {"duration": dur, "width": w, "height": h, "has_audio": a is not None,
                            "size_bytes": path.stat().st_size,
                            "bit_rate": int((info.get("format") or {}).get("bit_rate") or 0)})


def _result(checks: list[dict], stats: dict | None = None) -> dict:
    failed = [c for c in checks if c["required"] and not c["passed"]]
    warnings = [c for c in checks if not c["required"] and not c["passed"]]
    return {"passed": not failed, "failed": [c["name"] for c in failed],
            "warnings": [f"{c['name']}: {c['detail']}" for c in warnings], "checks": checks, "stats": stats or {}}


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--width", type=int, default=2160)
    ap.add_argument("--height", type=int, default=3840)
    ap.add_argument("--duration", type=float)
    ap.add_argument("--no-audio", action="store_true")
    a = ap.parse_args(argv)
    res = validate(a.file, width=a.width, height=a.height, expected_duration=a.duration, expect_audio=not a.no_audio)
    print(json.dumps(res, indent=2))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
