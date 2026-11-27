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

from scripts.common import (DependencyError, InputError, SourceUnavailableError, UnsupportedFormatError, log,
                            require_binary, run)


# --------------------------------------------------------------------------- probe
def _fps(rate: str | None) -> float:
    if not rate or rate in ("0/0", "0"):
        return 0.0
    if "/" in rate:
        n, d = rate.split("/")
        return float(n) / float(d) if float(d) else 0.0
    return float(rate)


def probe(path: Path | str, require_video: bool = True) -> dict:
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
    if not video and require_video:
        raise UnsupportedFormatError(f"{path} has no video stream.")
    video = video or {}
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    rotation = 0
    for sd in video.get("side_data_list") or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    rotation = int((video.get("tags") or {}).get("rotate", rotation))
    if abs(rotation) % 180 == 90:
        width, height = height, width
    duration = float((data.get("format") or {}).get("duration") or video.get("duration")
                     or (audio or {}).get("duration") or 0)
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
    sum_acc = sq_acc = None  # per-pixel brightness statistics: how much each area changes over time
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
                g = gray.astype(np.float32) / 255.0
                sum_acc = g if sum_acc is None else sum_acc + g
                sq_acc = g * g if sq_acc is None else sq_acc + g * g
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
    change = None
    if sum_acc is not None:
        mean = sum_acc / max(1, n_face_samples)
        change = np.sqrt(np.maximum(0.0, sq_acc / max(1, n_face_samples) - mean * mean))
    facecam = detect_facecam(faces, n_face_samples, persistent_edges, aw, ah, change)
    if facecam is None or facecam.get("border_sides", 0) < 4:
        # The reaction may be any picture-in-picture video (not only a face): look for its outline.
        inset = detect_inset_video(persistent_edges, change, aw, ah,
                                   tuple(facecam["face_center"]) if facecam else None)
        if inset and (facecam is None or _contains(inset["rect"], facecam["face_center"])):
            r = inset["rect"]
            facecam = {"rect": [round(v, 4) for v in r],
                       "face_center": facecam["face_center"] if facecam else [round(r[0] + r[2] / 2, 4),
                                                                               round(r[1] + r[3] * 0.45, 4)],
                       "presence": facecam["presence"] if facecam else 1.0,
                       "confidence": round(min(1.0, inset["score"]), 3), "border_sides": 4,
                       "kind": "inset_video" if not facecam else "webcam"}
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


def empty_visual(sample_fps: float = 2.0) -> dict:
    """Placeholder when the whole video was not downloaded (fast YouTube mode)."""
    return {"sample_fps": sample_fps, "face_fps": 1.0, "analysis_size": [0, 0], "times": [], "motion": [],
            "motion_cx": [], "motion_cy": [], "brightness": [], "scene_cuts": [], "faces": [],
            "face_samples": 0, "facecam": None, "content_hint": "unknown", "face_backend": None,
            "partial": True}


def shift_visual(visual: dict, offset: float) -> dict:
    """Move a visual analysis of a downloaded section onto the source timeline."""
    out = dict(visual)
    out["times"] = [round(t + offset, 3) for t in visual["times"]]
    out["scene_cuts"] = [round(t + offset, 3) for t in visual["scene_cuts"]]
    out["faces"] = [{**f, "t": round(f["t"] + offset, 3)} for f in visual["faces"]]
    return out


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


def _refine_with_edges(rect: list[float], edges, aw: int, ah: int,
                       face: list[float] | None = None) -> tuple[list[float], int]:
    """Snap a rough cam box to its real border.

    An overlay's frame, or the boundary between the webcam picture and the game behind it, is a straight
    edge that stays in place in every sampled frame. Game HUD lines and colour bars are persistent too, but
    they keep going past the corners of the cam box, while the cam's own border stops there. Each side is
    searched in a wide band (never through the face) and scored as "strong along the box, weak beyond it".
    Returns (rect, number_of_sides_snapped)."""
    if edges is None:
        return rect, 0
    import numpy as np
    x, y, w, h = rect
    x0, x1 = int(x * aw), int((x + w) * aw)
    y0, y1 = int(y * ah), int((y + h) * ah)
    if face:
        fl, ft = int(face[0] * aw), int(face[1] * ah)
        fr, fb = int((face[0] + face[2]) * aw), int((face[1] + face[3]) * ah)
    else:
        fl, ft, fr, fb = (x0 + x1) // 2, (y0 + y1) // 2, (x0 + x1) // 2, (y0 + y1) // 2
    # thicken by one pixel so slightly wobbly lines still count
    e = np.maximum(edges, np.maximum(np.roll(edges, 1, 0), np.roll(edges, 1, 1)))
    thr = 0.25

    def side(axis: int, lo: int, hi: int, a0: int, a1: int, fallback: int) -> tuple[int, bool]:
        n = e.shape[1] if axis == 0 else e.shape[0]
        lo, hi = max(0, lo), min(n - 1, hi)
        a0, a1 = max(0, a0), min((e.shape[0] if axis == 0 else e.shape[1]), a1)
        if hi <= lo or a1 - a0 < 4:
            return fallback, False
        span = a1 - a0
        best, best_score = fallback, 0.0
        for c in range(lo, hi + 1):
            line = e[a0:a1, c] if axis == 0 else e[c, a0:a1]
            inside = float(line.mean())
            if inside < thr:
                continue
            ext = int(span * 0.25)
            before = e[max(0, a0 - ext):a0, c] if axis == 0 else e[c, max(0, a0 - ext):a0]
            after = e[a1:a1 + ext, c] if axis == 0 else e[c, a1:a1 + ext]
            beyond = [float(v.mean()) for v in (before, after) if v.size >= 3]
            outside = max(beyond) if beyond else 0.0
            score = inside - 0.9 * outside
            if score > best_score + 1e-6 or (abs(score - best_score) < 0.05 and abs(c - fallback) < abs(best - fallback)
                                              and score > 0.2):
                best, best_score = c, score
        return best, best_score > 0.2

    pad_x, pad_y = int((x1 - x0) * 0.6), int((y1 - y0) * 0.8)
    snapped = [False] * 4
    for _ in range(2):  # columns use the current rows and vice versa, so run twice
        nx0, s0 = side(0, x0 - pad_x, min(x0 + pad_x, fl - 2), y0, y1, x0)
        nx1, s1 = side(0, max(x1 - pad_x, fr + 2), x1 + pad_x, y0, y1, x1)
        ny0, s2 = side(1, y0 - pad_y, min(y0 + pad_y, ft - 2), nx0, nx1, y0)
        ny1, s3 = side(1, max(y1 - pad_y, fb + 2), y1 + pad_y, nx0, nx1, y1)
        if nx1 - nx0 < 0.5 * (x1 - x0) or ny1 - ny0 < 0.5 * (y1 - y0):
            return rect, 0
        x0, x1, y0, y1 = nx0, nx1, ny0, ny1
        snapped = [s0, s1, s2, s3]
    # a side that touches the frame edge needs no line
    x1 = aw if not snapped[1] and x1 > aw * 0.97 else x1
    y1 = ah if not snapped[3] and y1 > ah * 0.97 else y1
    x0 = 0 if not snapped[0] and x0 < aw * 0.03 else x0
    y0 = 0 if not snapped[2] and y0 < ah * 0.03 else y0
    return [x0 / aw, y0 / ah, (x1 - x0) / aw, (y1 - y0) / ah], sum(snapped)


def detect_facecam(faces: list[dict], n_samples: int, edges=None, aw: int = 960, ah: int = 540,
                   change=None) -> dict | None:
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
        fw_med = sorted(b[2] for b in c["items"])[len(c["items"]) // 2]
        # An overlay webcam stays in one place, but the streamer inside it moves (leaning in, reacting).
        # Allow movement of about half a face width (std); a person walking across the frame moves much more.
        # ...and a face that drifts out of the cluster (split into several clusters) is roaming, not a cam
        roaming = sum(1 for f in faces if f["t"] not in c["times"] and any(
            abs(bx[0] + bx[2] / 2 - c["cx"]) < 3 * fw_med and abs(bx[1] + bx[3] / 2 - c["cy"]) < 3 * fw_med
            and 0.6 * fw_med <= bx[2] <= 1.6 * fw_med for bx in f["boxes"]))
        settled = roaming / n_samples < 0.1
        if presence >= 0.25 and area < 0.05 and off_center and settled and spread < max(0.02, 0.6 * fw_med):
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
    face_box = [cxn - fw / 2, cyn - fh / 2, fw, fh]
    rect, snapped = _refine_with_edges([x, y, w, h], edges, aw, ah, face_box)
    rect = _extend_to_frame_edges(rect, change, aw, ah)
    if snapped < 4:
        rect = _with_margin(rect, 0.04)  # no full border found: keep a little extra so nothing is cut off
    return {"rect": [round(v, 4) for v in rect], "face_center": [round(cxn, 4), round(cyn, 4)],
            "presence": round(best["presence"], 3), "confidence": round(min(1.0, best["score"]), 3),
            "border_sides": snapped}


def _line_positions(profile, min_strength: float, gap: int = 3) -> list[int]:
    """Indexes where a 1-D profile has a local peak above min_strength (nearby peaks merged)."""
    idx = [i for i in range(len(profile)) if profile[i] >= min_strength
           and profile[i] >= profile[max(0, i - 1)] and profile[i] >= profile[min(len(profile) - 1, i + 1)]]
    out: list[int] = []
    for i in idx:
        if out and i - out[-1] <= gap:
            if profile[i] > profile[out[-1]]:
                out[-1] = i
        else:
            out.append(i)
    return out


def detect_inset_video(edges, change, aw: int, ah: int, face_center: tuple[float, float] | None = None) -> dict | None:
    """Find a picture-in-picture region (reaction video, webcam, another clip) without needing a face.

    Its outline is a set of straight edges that stay put in every sampled frame and stop at the corners,
    and the picture inside it keeps changing (it is video, not a static HUD panel). Sides may also be the
    frame edge (insets in a corner). Returns {"rect": [x, y, w, h] normalized, "score": ...} or None."""
    if edges is None or change is None:
        return None
    import numpy as np
    e = np.maximum(edges, np.maximum(np.roll(edges, 1, 0), np.roll(edges, 1, 1)))
    on = (e >= 0.35).astype(np.float32)
    cv = np.vstack([np.zeros((1, aw), np.float32), np.cumsum(on, axis=0)])   # vertical runs
    ch = np.hstack([np.zeros((ah, 1), np.float32), np.cumsum(on, axis=1)])   # horizontal runs

    def vsup(x, y0, y1):
        if x <= 1 or x >= aw - 2:
            return 1.0, True
        y0, y1 = max(0, y0), min(ah, y1)
        return (float(cv[y1, x] - cv[y0, x]) / max(1, y1 - y0)), False

    def hsup(y, x0, x1):
        if y <= 1 or y >= ah - 2:
            return 1.0, True
        x0, x1 = max(0, x0), min(aw, x1)
        return (float(ch[y, x1] - ch[y, x0]) / max(1, x1 - x0)), False

    # Long persistent straight runs ("segments"). Two segments meeting at a corner define a rectangle.
    def runs(arr, min_len, gap=3):
        out, start, last = [], None, None
        for i in np.flatnonzero(arr):
            if start is None:
                start = last = i
            elif i - last <= gap:
                last = i
            else:
                if last - start >= min_len:
                    out.append((int(start), int(last)))
                start = last = i
        if start is not None and last - start >= min_len:
            out.append((int(start), int(last)))
        return out
    vsegs = [(x, a0, a1) for x in range(aw) for a0, a1 in runs(on[:, x], int(ah * 0.1))]
    hsegs = [(y, a0, a1) for y in range(ah) for a0, a1 in runs(on[y, :], int(aw * 0.08))]

    def dedupe(segs):
        segs = sorted(segs, key=lambda t: -(t[2] - t[1]))
        kept = []
        for sg in segs:
            if not any(abs(sg[0] - k[0]) <= 2 and abs(sg[1] - k[1]) <= 6 and abs(sg[2] - k[2]) <= 6 for k in kept):
                kept.append(sg)
        return kept[:80]
    vsegs, hsegs = dedupe(vsegs), dedupe(hsegs)
    tol = 6
    cands = set()
    for vx, vy0, vy1 in vsegs:
        for hy, hx0, hx1 in hsegs:
            near_top, near_bot = abs(vy0 - hy) <= tol, abs(vy1 - hy) <= tol
            near_l, near_r = abs(vx - hx0) <= tol, abs(vx - hx1) <= tol
            if near_l and near_top:
                cands.add((vx, hy, hx1, vy1))
            if near_r and near_top:
                cands.add((hx0, hy, vx, vy1))
            if near_l and near_bot:
                cands.add((vx, vy0, hx1, hy))
            if near_r and near_bot:
                cands.add((hx0, vy0, vx, hy))
    # snap far ends that stop just short of the frame edge
    snapped = set()
    for x0, y0, x1, y1 in cands:
        x0 = 0 if x0 <= 4 else x0
        y0 = 0 if y0 <= 4 else y0
        x1 = aw - 1 if x1 >= aw - 5 else x1
        y1 = ah - 1 if y1 >= ah - 5 else y1
        snapped.add((x0, y0, x1, y1))
    game_change = float(np.median(change))
    best = None
    for x0, y0, x1, y1 in sorted(snapped):
        w, h = x1 - x0, y1 - y0
        if w < aw * 0.12 or w > aw * 0.7 or h < ah * 0.12 or h > ah * 0.75:
            continue
        area = (w * h) / (aw * ah)
        if area < 0.025 or area > 0.4:
            continue
        asp = (w * 16 / aw) / (h * 9 / ah)  # pixel aspect for a 16:9 frame
        if asp < 0.45 or asp > 3.0:
            continue
        sides = [vsup(x0, y0, y1), vsup(x1, y0, y1), hsup(y0, x0, x1), hsup(y1, x0, x1)]
        real = [v for v, frame in sides if not frame]
        if len(real) < 2:
            continue
        sv = sorted(v for v, _ in sides)
        weak_pen = 0.0
        if sv[0] < 0.6:
            # one faint side is allowed when the other three are clear (low-contrast edge)
            if sv[0] < 0.15 or sv[1] < 0.75:
                continue
            weak_pen = 0.6 - sv[0]
        # the outline must stop at the corners (a HUD line or colour bar keeps going)
        ext_v, ext_h = int(h * 0.3), int(w * 0.3)
        beyond = []
        for x, frame in ((x0, sides[0][1]), (x1, sides[1][1])):
            if not frame:
                beyond += [vsup(x, y0 - ext_v, y0 - 2)[0] if y0 > 4 else 0.0,
                           vsup(x, y1 + 2, y1 + ext_v)[0] if y1 < ah - 5 else 0.0]
        for y, frame in ((y0, sides[2][1]), (y1, sides[3][1])):
            if not frame:
                beyond += [hsup(y, x0 - ext_h, x0 - 2)[0] if x0 > 4 else 0.0,
                           hsup(y, x1 + 2, x1 + ext_h)[0] if x1 < aw - 5 else 0.0]
        leak = max(beyond) if beyond else 0.0
        inside = float(np.percentile(change[y0 + 2:y1 - 1, x0 + 2:x1 - 1], 90))
        if inside < 0.01:
            continue  # static panel, not video
        frame_sides = sum(1 for _, frame in sides if frame)
        score = (sum(real) / len(real) - 0.8 * leak
                 - 0.05 * frame_sides + 0.05 * min(area / 0.1, 1.0) - 0.5 * weak_pen)
        if face_center is not None:
            fx, fy = face_center[0] * aw, face_center[1] * ah
            if x0 < fx < x1 and y0 < fy < y1:
                score += 0.5
        if score > 0.5 and (best is None or score > best["score"]):
            best = {"rect": [x0 / aw, y0 / ah, w / aw, h / ah], "score": round(score, 3),
                    "inside_change": round(inside, 4), "game_change": round(game_change, 4)}
    return best


def apply_facecam_override(visual: dict, override, src_w: int, src_h: int) -> dict:
    """User override: "none" disables the stacked layout; [x, y, w, h] (pixels, or 0..1 fractions) sets the cam."""
    if override in (None, "", "auto"):
        return visual
    out = dict(visual)
    if isinstance(override, str) and override.lower() in ("none", "off", "no"):
        out["facecam"] = None
        return out
    vals = [float(v) for v in (override.split(",") if isinstance(override, str) else override)]
    if len(vals) != 4 or vals[2] <= 0 or vals[3] <= 0:
        raise InputError(f"Bad facecam value {override!r}.", "Use x,y,w,h in pixels of the source video "
                                                              "(e.g. 1400,40,480,270) or 'none'.")
    if max(vals) > 1.0:
        vals = [vals[0] / src_w, vals[1] / src_h, vals[2] / src_w, vals[3] / src_h]
    x, y, w, h = vals
    x, y = max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
    w, h = min(w, 1.0 - x), min(h, 1.0 - y)
    out["facecam"] = {"rect": [round(x, 4), round(y, 4), round(w, 4), round(h, 4)],
                      "face_center": [round(x + w / 2, 4), round(y + h * 0.42, 4)],
                      "presence": 1.0, "confidence": 1.0, "border_sides": 4, "manual": True}
    return out


def _extend_to_frame_edges(rect: list[float], change, aw: int, ah: int) -> list[float]:
    """Webcams usually sit in a corner. If the strip between a side of the box and the frame edge behaves
    like the webcam picture (how much it changes over time) rather than like the game, it is part of the
    cam: an internal line in the webcam image (a shelf, a door frame) was mistaken for the border."""
    if change is None:
        return rect
    import numpy as np
    x0, y0 = int(rect[0] * aw), int(rect[1] * ah)
    x1, y1 = int((rect[0] + rect[2]) * aw), int((rect[1] + rect[3]) * ah)
    bw, bh = x1 - x0, y1 - y0
    if bw < 8 or bh < 8:
        return rect
    cam = float(np.median(change[y0 + bh // 4:y1 - bh // 4, x0 + bw // 4:x1 - bw // 4]))
    mask = np.ones_like(change, dtype=bool)
    mask[max(0, y0 - 4):y1 + 4, max(0, x0 - 4):x1 + 4] = False
    game = float(np.median(change[mask])) if mask.any() else cam

    def belongs_to_cam(strip) -> bool:
        if strip.size < 16:
            return False
        v = float(np.median(strip))
        return abs(v - cam) < abs(v - game) * 0.7

    limit_x, limit_y = 0.6 * bw, 0.6 * bh
    if 0 < x0 <= limit_x and belongs_to_cam(change[y0:y1, :x0]):
        x0 = 0
    if 0 < aw - x1 <= limit_x and belongs_to_cam(change[y0:y1, x1:]):
        x1 = aw
    if 0 < y0 <= limit_y and belongs_to_cam(change[:y0, x0:x1]):
        y0 = 0
    if 0 < ah - y1 <= limit_y and belongs_to_cam(change[y1:, x0:x1]):
        y1 = ah
    return [x0 / aw, y0 / ah, (x1 - x0) / aw, (y1 - y0) / ah]


def _contains(rect: list[float], point) -> bool:
    return rect[0] <= point[0] <= rect[0] + rect[2] and rect[1] <= point[1] <= rect[1] + rect[3]


def _with_margin(rect: list[float], frac: float) -> list[float]:
    x, y, w, h = rect
    x0, y0 = max(0.0, x - w * frac), max(0.0, y - h * frac)
    x1, y1 = min(1.0, x + w * (1 + frac)), min(1.0, y + h * (1 + frac))
    return [x0, y0, x1 - x0, y1 - y0]


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
