"""Audio analysis: loudness timeline, silences, energy spikes (reactions), possible music.

Streams 16 kHz mono PCM from FFmpeg in chunks, so a 3-hour stream uses little memory.
Windows are 0.5 s. Output arrays are aligned to `times` (window start).

"possible_music" is a HEURISTIC (sustained tonal energy with low spectral flatness).
It is a prompt to check for third-party music, never proof either way.
CLI: python scripts/audio_analyzer.py <file>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import DependencyError, log, merge_intervals, require_binary

SR = 16000
WIN = 0.5


def _np():
    try:
        import numpy as np
    except ImportError as exc:
        raise DependencyError("numpy is not installed.", "pip install -r requirements.txt") from exc
    return np


def analyze_audio(path: Path | str, meta: dict, start: float = 0.0, end: float | None = None) -> dict:
    np = _np()
    end = meta["duration"] if end is None else min(end, meta["duration"])
    if not meta.get("has_audio"):
        return {"has_audio": False, "window": WIN, "times": [], "rms_db": [], "flatness": [],
                "energy_z": [], "silences": [[start, end]], "spikes": [], "possible_music": [],
                "noise_floor_db": None}
    require_binary("ffmpeg")
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path), "-t", f"{max(0.1, end - start):.3f}", "-vn", "-sn", "-ac", "1",
            "-ar", str(SR), "-f", "s16le", "-"]
    win = int(SR * WIN)
    times, rms_db, flat, zcr = [], [], [], []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    hann = np.hanning(win).astype(np.float32)
    i = 0
    try:
        while True:
            buf = proc.stdout.read(win * 2)
            if len(buf) < win:  # drop tiny tail
                break
            x = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
            if len(x) < win:
                x = np.pad(x, (0, win - len(x)))
            rms = float(np.sqrt(np.mean(x * x)) + 1e-9)
            spec = np.abs(np.fft.rfft(x * hann))[1:] + 1e-9
            flatness = float(np.exp(np.mean(np.log(spec))) / np.mean(spec))
            z = float(np.mean(np.abs(np.diff(np.signbit(x).astype(np.int8)))))
            times.append(round(start + i * WIN, 3))
            rms_db.append(round(20 * np.log10(rms), 2))
            flat.append(round(flatness, 4))
            zcr.append(round(z, 4))
            i += 1
    finally:
        proc.stdout.close()
        proc.stderr.read()
        proc.wait()
    if not times:
        return {"has_audio": False, "window": WIN, "times": [], "rms_db": [], "flatness": [],
                "energy_z": [], "silences": [[start, end]], "spikes": [], "possible_music": [],
                "noise_floor_db": None}

    db = np.maximum(np.array(rms_db), -90.0)  # digital silence would otherwise dominate the statistics
    noise_floor = float(np.percentile(db, 10))
    silence_thr = max(-60.0, min(-38.0, noise_floor + 8.0))  # constant game/music audio is not silence
    silences = _runs(times, db < silence_thr, min_len=0.5)

    # Energy relative to a rolling 60 s median: reactions stand out from the local baseline.
    k = max(3, int(60 / WIN)) | 1
    baseline = _rolling_median(db, k)
    active = db[db > silence_thr]
    if len(active) > 10:
        q75, q25 = np.percentile(active, [75, 25])
        spread = max(3.0, float(q75 - q25))
    else:
        spread = 6.0
    ez = (db - baseline) / spread
    spikes = []
    for j in range(1, len(ez) - 1):
        if ez[j] > 1.6 and ez[j] >= ez[j - 1] and ez[j] >= ez[j + 1] and db[j] > silence_thr + 6:
            spikes.append({"t": times[j], "z": round(float(ez[j]), 2), "db": round(float(db[j]), 1)})
    # Keep the strongest spike per 4 s.
    spikes.sort(key=lambda s: -s["z"])
    kept: list[dict] = []
    for s in spikes:
        if all(abs(s["t"] - o["t"]) >= 4 for o in kept):
            kept.append(s)
    kept.sort(key=lambda s: s["t"])

    music_mask = (np.array(flat) < 0.12) & (db > silence_thr + 10) & (np.array(zcr) < 0.12)
    possible_music = [r for r in _runs(times, music_mask, min_len=8.0, max_gap=1.5)]
    return {
        "has_audio": True,
        "window": WIN,
        "times": times,
        "rms_db": rms_db,
        "flatness": flat,
        "energy_z": [round(float(v), 3) for v in ez],
        "noise_floor_db": round(noise_floor, 2),
        "silence_threshold_db": round(silence_thr, 2),
        "silences": silences,
        "spikes": kept,
        "possible_music": possible_music,
    }


def _rolling_median(arr, k: int):
    np = _np()
    if len(arr) <= k:
        return np.full_like(arr, np.median(arr))
    pad = k // 2
    padded = np.pad(arr, (pad, pad), mode="edge")
    # Strided median on a subsample for speed, then interpolate.
    step = max(1, k // 8)
    idx = np.arange(0, len(arr), step)
    meds = np.array([np.median(padded[i:i + k]) for i in idx])
    return np.interp(np.arange(len(arr)), idx, meds)


def _runs(times: list[float], mask, min_len: float, max_gap: float = 0.0) -> list[list[float]]:
    runs = []
    cur = None
    for t, m in zip(times, mask):
        if m:
            if cur is None:
                cur = [t, t + WIN]
            else:
                cur[1] = t + WIN
        elif cur is not None:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    runs = merge_intervals(runs, gap=max_gap)
    return [[round(s, 2), round(e, 2)] for s, e in runs if e - s >= min_len]


def value_at(audio: dict, key: str, t: float, default: float = 0.0) -> float:
    times = audio.get("times") or []
    if not times:
        return default
    i = int((t - times[0]) / audio["window"])
    if 0 <= i < len(times):
        return audio[key][i]
    return default


def is_silent_between(audio: dict, a: float, b: float) -> bool:
    return any(s <= a and e >= b for s, e in audio.get("silences", []))


def main(argv: list[str] | None = None) -> int:
    from scripts.video_analyzer import probe
    path = (argv or sys.argv[1:])[0]
    meta = probe(path)
    log(f"Analysing audio of {path}")
    res = analyze_audio(path, meta)
    print(json.dumps({k: res[k] for k in ("has_audio", "noise_floor_db", "spikes", "possible_music")}
                     | {"silences": len(res["silences"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
