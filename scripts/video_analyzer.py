"""Video probing and visual analysis (FFmpeg decode + OpenCV).

Produces, for the whole video, a sampled timeline of:
  * motion energy and motion centroid (where the action is)
  * scene cuts
  * brightness (black/blank sections)
  * face boxes (Haar cascade; optional YuNet model if present)
and derives a facecam rectangle for gaming/stream layouts.

All coordinates are normalized to 0..1 of the (display-rotated) frame.
CLI:  python scripts/video_analyzer.py probe <file>
      python scripts/video_analyzer.py analyze <file> [--fps 2]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import (DependencyError, SourceUnavailableError, UnsupportedFormatError, log,
                            require_binary, run)


# --------------------------------------------------------------------------- probe
def _fps(rate: str | None) -> float:
    if not rate or rate in ("0/0", "0"):
        return 0.0
    if "/" in rate:
        n, d = rate.split("/")
        return float(n) / float(d) if float(d) else 0.0
    return float(rate)


def probe(path: Path | str) -> dict:
    """Return duration, display width/height, fps, codecs and audio info. Raises on undecodable input."""
    require_binary("ffprobe")
    proc = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                str(path)], timeout=120, check=False)
    if proc.returncode != 0:
        raise UnsupportedFormatError(f"FFmpeg cannot read {path}: "
                                     f"{proc.stderr.decode('utf-8', 'replace').strip()[-300:]}",
                                     "The file may be corrupt or use an unsupported codec.")
    data = json.loads(proc.stdout or b"{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video:
        raise UnsupportedFormatError(f"{path} has no video stream.")
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    rotation = 0
    for sd in video.get("side_data_list") or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    rotation = int((video.get("tags") or {}).get("rotate", rotation))
    if abs(rotation) % 180 == 90:
        width, height = height, width
    duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0)
    fps = _fps(video.get("avg_frame_rate")) or _fps(video.get("r_frame_rate"))
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": round(fps, 3) if fps else 30.0,
        "video_codec": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt"),
        "rotation": rotation,
        "bit_rate": int((data.get("format") or {}).get("bit_rate") or 0),
        "has_audio": audio is not None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "sample_rate": int(audio.get("sample_rate") or 0) if audio else 0,
        "channels": int(audio.get("channels") or 0) if audio else 0,
        "format_name": (data.get("format") or {}).get("format_name"),
    }


# --------------------------------------------------------------------------- visual analysis
def _import_cv():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise DependencyError("OpenCV/numpy are not installed.",
                              "pip install -r requirements.txt  (opencv-python-headless, numpy)") from exc
    return cv2, np


YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")


def model_dirs() -> list[Path]:
    from scripts.common import state_dir
    return [Path(__file__).resolve().parent.parent / "models", state_dir() / "models"]


class FaceDetector:
    """YuNet (OpenCV DNN) if face_detection_yunet*.onnx is in models/ or <state_dir>/models/
    (run `cli.py setup-models`), else Haar cascades (bundled with opencv-python < 5).
    If neither is available, `available` is False and framing falls back to motion tracking."""

    def __init__(self, frame_w: int, frame_h: int):
        cv2, _ = _import_cv()
        self.cv2 = cv2
        self.yunet = None
        self.frontal = self.profile = None
        for d in model_dirs():
            onnx = sorted(d.glob("face_detection_yunet*.onnx")) if d.exists() else []
            if onnx and hasattr(cv2, "FaceDetectorYN"):
                try:
                    self.yunet = cv2.FaceDetectorYN.create(str(onnx[-1]), "", (frame_w, frame_h), 0.75)
                    break
                except cv2.error:
                    self.yunet = None
        if self.yunet is None and hasattr(cv2, "CascadeClassifier"):
            base = Path(getattr(getattr(cv2, "data", None), "haarcascades", "") or "")
            frontal = base / "haarcascade_frontalface_default.xml"
            if frontal.exists():
                self.frontal = cv2.CascadeClassifier(str(frontal))
                self.profile = cv2.CascadeClassifier(str(base / "haarcascade_profileface.xml"))
        self.backend = "yunet" if self.yunet is not None else ("haar" if self.frontal is not None else "none")
        self.available = self.backend != "none"
        self.min_size = max(16, int(min(frame_w, frame_h) * 0.03))

    def _clahe(self):
        if not hasattr(self, "_cl"):
            self._cl = self.cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return self._cl

    def detect(self, gray, bgr=None) -> list[list[float]]:
        if not self.available:
            return []
        h, w = gray.shape[:2]
        boxes: list[list[float]] = []
        if self.yunet is not None:
            img = bgr if bgr is not None else self.cv2.cvtColor(gray, self.cv2.COLOR_GRAY2BGR)
            _, faces = self.yunet.detect(img)
            for f in faces if faces is not None else []:
                if f[2] >= self.min_size * 0.8:
                    boxes.append([float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])])
        else:
            ms = (self.min_size, self.min_size)
            for img in (gray, self._clahe().apply(gray)):
                for (x, y, fw, fh) in self.frontal.detectMultiScale(img, 1.1, 5, minSize=ms):
                    boxes.append([float(x), float(y), float(fw), float(fh), 1.0])
                if boxes:
                    break
            if not boxes and self.profile is not None and not self.profile.empty():
                for (x, y, fw, fh) in self.profile.detectMultiScale(gray, 1.1, 5, minSize=ms):
                    boxes.append([float(x), float(y), float(fw), float(fh), 0.8])
        return [[max(0.0, b[0] / w), max(0.0, b[1] / h), b[2] / w, b[3] / h, round(b[4], 3)] for b in boxes]


def download_face_model() -> Path:
    """Fetch the YuNet face model (MIT licensed, from the official opencv_zoo) into <state_dir>/models."""
    import urllib.request
    cv2, _ = _import_cv()
    dest_dir = model_dirs()[1]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "face_detection_yunet_2023mar.onnx"
    tmp = dest.with_suffix(".part")
    urllib.request.urlretrieve(YUNET_URL, tmp)
    try:
        cv2.FaceDetectorYN.create(str(tmp), "", (320, 240), 0.7)
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        raise DependencyError(f"Downloaded face model is not loadable: {exc}",
                              f"Download it manually from {YUNET_URL} into {dest_dir}") from exc
    tmp.replace(dest)
    return dest


def analyze_visual(path: Path | str, meta: dict, sample_fps: float = 2.0, face_fps: float = 1.0,
                   start: float = 0.0, end: float | None = None, analysis_width: int = 960) -> dict:
    """Stream frames from FFmpeg (fast, low memory) and compute per-sample visual features."""
    cv2, np = _import_cv()
    require_binary("ffmpeg")
    src_w, src_h = meta["width"], meta["height"]
    aw = min(analysis_width, src_w) // 2 * 2
    ah = max(2, int(round(src_h * aw / src_w / 2)) * 2)
    end = meta["duration"] if end is None else min(end, meta["duration"])
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path), "-t", f"{max(0.1, end - start):.3f}", "-an", "-sn",
            "-vf", f"fps={sample_fps},scale={aw}:{ah}:flags=area,format=gray", "-f", "rawvideo", "-"]
    frame_bytes = aw * ah
    detector = FaceDetector(aw, ah)
    if not detector.available:
        log("No face detector available (OpenCV 5 without a YuNet model): framing will follow motion. "
            "Run `cli.py setup-models` or install opencv-python-headless<5.")
    face_every = max(1, int(round(sample_fps / max(face_fps, 0.01))))
    small_w = 160
    small_h = max(2, int(round(ah * small_w / aw)))

    times, motion, cx, cy, brightness, cuts = [], [], [], [], [], []
    faces: list[dict] = []
    edge_acc = None
    prev_small = prev_hist = None
    idx = 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            gray = np.frombuffer(buf, dtype=np.uint8).reshape(ah, aw)
            t = start + idx / sample_fps
            small = cv2.resize(gray, (small_w, small_h), interpolation=cv2.INTER_AREA)
            hist = cv2.calcHist([small], [0], None, [32], [0, 256])
            cv2.normalize(hist, hist)
            if prev_small is None:
                m, mx, my, cut = 0.0, 0.5, 0.5, False
            else:
                diff = cv2.absdiff(small, prev_small).astype(np.float32)
                m = float(diff.mean() / 255.0)
                mass = diff.sum()
                if mass > 1e-3:
                    ys, xs = np.indices(diff.shape)
                    mx = float((diff * xs).sum() / mass / small_w)
                    my = float((diff * ys).sum() / mass / small_h)
                else:
                    mx, my = 0.5, 0.5
                corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
                cut = corr < 0.55 and m > 0.08
            times.append(round(t, 3))
            motion.append(round(m, 5))
            cx.append(round(mx, 4))
            cy.append(round(my, 4))
            brightness.append(round(float(small.mean() / 255.0), 4))
            cuts.append(bool(cut))
            if idx % face_every == 0:
                boxes = detector.detect(gray)
                if boxes:
                    faces.append({"t": round(t, 3), "boxes": boxes})
                edges = cv2.Canny(gray, 60, 160).astype(np.float32) / 255.0
                edge_acc = edges if edge_acc is None else edge_acc + edges
            prev_small, prev_hist = small, hist
            idx += 1
    finally:
        proc.stdout.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        proc.wait()
    if idx == 0:
        raise SourceUnavailableError(f"No frames could be decoded from {path}: {err.strip()[-300:]}")

    n_face_samples = (idx + face_every - 1) // face_every
    persistent_edges = None
    if edge_acc is not None:
        persistent_edges = edge_acc / max(1, n_face_samples)
    facecam = detect_facecam(faces, n_face_samples, persistent_edges, aw, ah)
    content_hint = guess_content_type(faces, n_face_samples, facecam, motion)
    return {
        "sample_fps": sample_fps,
        "face_fps": sample_fps / face_every,
        "analysis_size": [aw, ah],
        "times": times,
        "motion": motion,
        "motion_cx": cx,
        "motion_cy": cy,
        "brightness": brightness,
        "scene_cuts": [times[i] for i, c in enumerate(cuts) if c],
        "faces": faces,
        "face_samples": n_face_samples,
        "facecam": facecam,
        "content_hint": content_hint,
        "face_backend": detector.backend,
    }


# --------------------------------------------------------------------------- facecam
def _cluster_faces(faces: list[dict], tol: float = 0.06) -> list[dict]:
    clusters: list[dict] = []
    for f in faces:
        for b in f["boxes"]:
            cxn, cyn = b[0] + b[2] / 2, b[1] + b[3] / 2
            for c in clusters:
                if abs(c["cx"] - cxn) < tol and abs(c["cy"] - cyn) < tol:
                    c["items"].append(b)
                    c["times"].add(f["t"])
                    n = len(c["items"])
                    c["cx"] += (cxn - c["cx"]) / n
                    c["cy"] += (cyn - c["cy"]) / n
                    break
            else:
                clusters.append({"cx": cxn, "cy": cyn, "items": [b], "times": {f["t"]}})
    return clusters


def _refine_with_edges(rect: list[float], edges, aw: int, ah: int) -> list[float]:
    """Snap a rough cam box to persistent straight edges (overlay borders) if they exist."""
    if edges is None:
        return rect
    import numpy as np
    x, y, w, h = rect
    x0, x1 = int(x * aw), int((x + w) * aw)
    y0, y1 = int(y * ah), int((y + h) * ah)
    pad_x, pad_y = int(w * aw * 0.6), int(h * ah * 1.0)

    def best_line(profile, lo, hi, around):
        lo, hi = max(0, lo), min(len(profile) - 1, hi)
        if hi <= lo:
            return around, 0.0
        seg = profile[lo:hi + 1]
        i = int(np.argmax(seg))
        return lo + i, float(seg[i])

    rows = edges[max(0, y0):min(ah, y1), :]
    cols = edges[:, max(0, x0):min(aw, x1)]
    if rows.size == 0 or cols.size == 0:
        return rect
    vprof = rows.mean(axis=0)   # vertical lines -> columns
    hprof = cols.mean(axis=1)   # horizontal lines -> rows
    thr = 0.45                  # line present in >=45% of sampled frames along its length
    lx, ls = best_line(vprof, x0 - pad_x, x0 + pad_x // 3, x0)
    rx, rs = best_line(vprof, x1 - pad_x // 3, x1 + pad_x, x1)
    ty, ts = best_line(hprof, y0 - pad_y, y0 + pad_y // 3, y0)
    by, bs = best_line(hprof, y1 - pad_y // 3, y1 + pad_y, y1)
    nx0 = lx if ls > thr else x0
    nx1 = rx if rs > thr else x1
    ny0 = ty if ts > thr else y0
    ny1 = by if bs > thr else y1
    if nx1 - nx0 < 0.5 * (x1 - x0) or ny1 - ny0 < 0.5 * (y1 - y0):
        return rect
    return [nx0 / aw, ny0 / ah, (nx1 - nx0) / aw, (ny1 - ny0) / ah]


def detect_facecam(faces: list[dict], n_samples: int, edges=None, aw: int = 960, ah: int = 540) -> dict | None:
    """A facecam is a small, stable face that appears in a large share of samples, away from centre."""
    if n_samples == 0 or not faces:
        return None
    best = None
    for c in _cluster_faces(faces):
        presence = len(c["times"]) / n_samples
        sizes = sorted(b[2] * b[3] for b in c["items"])
        area = sizes[len(sizes) // 2]
        off_center = abs(c["cx"] - 0.5) > 0.18 or abs(c["cy"] - 0.5) > 0.22
        xs = [b[0] + b[2] / 2 for b in c["items"]]
        ys = [b[1] + b[3] / 2 for b in c["items"]]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        spread = max((sum((x - mx) ** 2 for x in xs) / len(xs)) ** 0.5, (sum((y - my) ** 2 for y in ys) / len(ys)) ** 0.5)
        # an overlay webcam sits still; a person walking across the frame is not a facecam
        if presence >= 0.3 and area < 0.05 and off_center and spread < 0.015:
            score = presence * (1.0 - area * 5)
            if not best or score > best["score"]:
                best = {"score": score, "cluster": c, "presence": presence, "area": area}
    if not best:
        return None
    items = best["cluster"]["items"]
    fw = sorted(b[2] for b in items)[len(items) // 2]
    fh = sorted(b[3] for b in items)[len(items) // 2]
    cxn, cyn = best["cluster"]["cx"], best["cluster"]["cy"]
    # Typical webcam overlay: face is ~1/3 of the box width; box is roughly 4:3 to 16:9.
    w = min(0.5, fw * 3.2)
    h = min(0.55, max(fh * 2.6, w * (9 / 16) * (aw / ah)))
    x = min(max(0.0, cxn - w / 2), 1.0 - w)
    y = min(max(0.0, cyn - h * 0.45), 1.0 - h)
    rect = _refine_with_edges([x, y, w, h], edges, aw, ah)
    return {"rect": [round(v, 4) for v in rect], "face_center": [round(cxn, 4), round(cyn, 4)],
            "presence": round(best["presence"], 3), "confidence": round(min(1.0, best["score"]), 3)}


def guess_content_type(faces: list[dict], n_samples: int, facecam: dict | None, motion: list[float]) -> str:
    if facecam:
        return "gaming"
    if n_samples == 0:
        return "general"
    with_face = len({f["t"] for f in faces}) / n_samples
    big = [b for f in faces for b in f["boxes"] if b[2] * b[3] > 0.02]
    avg_motion = sum(motion) / max(1, len(motion))
    if with_face > 0.5 and big and avg_motion < 0.04:
        return "podcast"
    if with_face > 0.4:
        return "talking"
    return "general"


# --------------------------------------------------------------------------- helpers for other modules
def faces_in_range(visual: dict, start: float, end: float) -> list[dict]:
    return [f for f in visual.get("faces", []) if start <= f["t"] <= end]


def sample_index(visual: dict, t: float) -> int:
    times = visual["times"]
    if not times:
        return 0
    i = int(round((t - times[0]) * visual["sample_fps"]))
    return max(0, min(len(times) - 1, i))


def series_in_range(visual: dict, key: str, start: float, end: float) -> list[tuple[float, Any]]:
    i0, i1 = sample_index(visual, start), sample_index(visual, end)
    return [(visual["times"][i], visual[key][i]) for i in range(i0, i1 + 1)]


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("file")
    a = sub.add_parser("analyze")
    a.add_argument("file")
    a.add_argument("--fps", type=float, default=2.0)
    args = ap.parse_args(argv)
    meta = probe(args.file)
    if args.cmd == "probe":
        print(json.dumps(meta, indent=2))
    else:
        log(f"Analysing {args.file} ({meta['duration']:.0f}s)")
        res = analyze_visual(args.file, meta, sample_fps=args.fps)
        summary = {k: res[k] for k in ("facecam", "content_hint", "face_samples")}
        summary["scene_cuts"] = len(res["scene_cuts"])
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
