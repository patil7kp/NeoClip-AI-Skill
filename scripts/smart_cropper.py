"""Smart 9:16 framing. Never blind centre-crops when there is something better to follow.

Layout modes
  face_track     follow the dominant face; two-shot when two faces fit; static per shot when the
                 subject barely moves (professional, no jitter), smooth eased pans when it does
  subject_track  follow on-screen action (motion centroid), centre-weighted, heavily smoothed
  gaming_stack   facecam panel + gameplay panel stacked; gameplay keeps the majority of the frame
  fit_blur       whole frame fitted to width over a blurred fill (for slides/screens that can't be cropped)
If a template asks for gaming_stack but no facecam was detected, it falls back to subject_track
(full-height gameplay) and says so in `notes`.

All crop paths are produced as keyframes in OUTPUT time (via TimelineMap) and compiled into an
FFmpeg piecewise-linear expression, so dynamic cropping happens in a single render pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.video_cutter import TimelineMap


def _even(v: float) -> int:
    return max(2, int(round(v / 2.0)) * 2)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# --------------------------------------------------------------------------- keyframe utilities
def simplify_keyframes(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker on (t, x) so the FFmpeg expression stays short."""
    if len(points) <= 2:
        return points

    def rdp(pts):
        (t0, x0), (t1, x1) = pts[0], pts[-1]
        best_i, best_d = 0, -1.0
        for i in range(1, len(pts) - 1):
            t, x = pts[i]
            interp = x0 + (x1 - x0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0)
            d = abs(x - interp)
            if d > best_d:
                best_i, best_d = i, d
        if best_d > tol:
            return rdp(pts[:best_i + 1])[:-1] + rdp(pts[best_i:])
        return [pts[0], pts[-1]]
    return rdp(points)


def piecewise_expr(points: list[tuple[float, float]], var: str = "t") -> str:
    """Compile keyframes to an FFmpeg expression: linear between keyframes, held at the ends."""
    pts = sorted(points)
    if not pts:
        return "0"
    if len(pts) == 1 or all(abs(p[1] - pts[0][1]) < 0.5 for p in pts):
        return f"{pts[0][1]:.1f}"
    expr = f"{pts[-1][1]:.1f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(pts[:-1], pts[1:]))):
        if t1 - t0 < 1e-3:
            seg = f"{x1:.1f}"
        else:
            seg = f"({x0:.1f}+({x1 - x0:.1f})*({var}-{t0:.3f})/{t1 - t0:.3f})"
        expr = f"if(lt({var},{t1:.3f}),{seg},{expr})"
    return f"if(lt({var},{pts[0][0]:.3f}),{pts[0][1]:.1f},{expr})"


def _ema(values: list[float], alpha: float) -> list[float]:
    out, cur = [], None
    for v in values:
        cur = v if cur is None else cur + alpha * (v - cur)
        out.append(cur)
    return out


def _shots(start: float, end: float, cuts: list[float]) -> list[tuple[float, float]]:
    edges = [start] + [c for c in cuts if start + 0.5 < c < end - 0.5] + [end]
    return list(zip(edges[:-1], edges[1:]))


# --------------------------------------------------------------------------- target paths
def face_targets(visual: dict, start: float, end: float, crop_w_norm: float) -> list[tuple[float, float, float]]:
    """(t, cx, cy) normalized targets; sticky to the current subject, two-shot when both fit."""
    out = []
    prev = None
    for f in visual.get("faces", []):
        if not start - 0.5 <= f["t"] <= end + 0.5:
            continue
        boxes = sorted(f["boxes"], key=lambda b: -(b[2] * b[3]))
        if not boxes:
            continue
        main = boxes[0]
        cand = [(b[0] + b[2] / 2, b[1] + b[3] / 2, b) for b in boxes if b[2] * b[3] >= 0.35 * main[2] * main[3]]
        if len(cand) >= 2:
            xs = sorted(cand, key=lambda c: c[0])
            a, b = xs[0], xs[-1]
            span = (b[0] + b[2][2] / 2) - (a[0] - a[2][2] / 2)
            if span < crop_w_norm * 0.9:
                tx = (a[0] + b[0]) / 2
                ty = (a[1] + b[1]) / 2
                out.append((f["t"], tx, ty))
                prev = (tx, ty)
                continue
        if prev is not None:
            cand.sort(key=lambda c: abs(c[0] - prev[0]))   # stay on the same person
            near = cand[0]
            if abs(near[0] - prev[0]) < 0.12:
                out.append((f["t"], near[0], near[1]))
                prev = (near[0], near[1])
                continue
        tx, ty = main[0] + main[2] / 2, main[1] + main[3] / 2
        out.append((f["t"], tx, ty))
        prev = (tx, ty)
    return out


def motion_targets(visual: dict, start: float, end: float, center_weight: float = 0.5) -> list[tuple[float, float, float]]:
    pts = []
    for t, cx, cy, m in zip(visual.get("times", []), visual.get("motion_cx", []),
                            visual.get("motion_cy", []), visual.get("motion", [])):
        if start - 0.5 <= t <= end + 0.5:
            w = 0.0 if m < 0.01 else 1.0
            pts.append((t, 0.5 + (cx - 0.5) * (1 - center_weight) * w, 0.5 + (cy - 0.5) * (1 - center_weight) * w))
    return pts


def build_path(targets: list[tuple[float, float, float]], start: float, end: float, cuts: list[float],
               smoothing: float, static_threshold: float, axis: int = 1) -> list[tuple[float, float]]:
    """Return [(source_t, normalized_center)] respecting shots: static per shot unless the subject moves."""
    if not targets:
        return [(start, 0.5), (end, 0.5)]
    path: list[tuple[float, float]] = []
    for s, e in _shots(start, end, cuts):
        pts = [(x[0], x[axis]) for x in targets if s - 0.5 <= x[0] <= e + 0.5]
        if not pts:
            last = path[-1][1] if path else targets[0][axis]
            path += [(s, last), (e, last)]
            continue
        vals = sorted(v for _, v in pts)
        med = vals[len(vals) // 2]
        if vals[-1] - vals[0] < static_threshold:
            path += [(s, med), (e - 0.001, med)]
        else:
            sm = _ema([v for _, v in pts], smoothing)
            path += [(s, sm[0])] + [(t, v) for (t, _), v in zip(pts, sm)] + [(e - 0.001, sm[-1])]
    return path


# --------------------------------------------------------------------------- layouts
def plan_layout(src_w: int, src_h: int, out_w: int, out_h: int, layout_cfg: dict, visual: dict | None,
                start: float, end: float, tmap: TimelineMap) -> dict:
    visual = visual or {"faces": [], "times": [], "scene_cuts": []}
    mode = layout_cfg["mode"]
    notes = []
    if mode == "gaming_stack" and not visual.get("facecam"):
        mode = "subject_track"
        notes.append("No stable facecam detected; used full-height gameplay tracking instead of a stacked layout.")
    cuts = visual.get("scene_cuts", [])
    out_aspect = out_w / out_h
    if mode == "gaming_stack":
        return _gaming_stack(src_w, src_h, out_w, out_h, layout_cfg, visual, start, end, tmap, cuts, notes)
    if mode == "fit_blur":
        scale = out_w / src_w
        return {"mode": mode, "notes": notes, "crop": None, "upscale_factor": round(scale, 3),
                "faces_out": [], "seam_y": None, "zoom_panel": "full", "zoom_center_y": 0.5}

    # single-panel crop (face_track / subject_track)
    zoom = float(layout_cfg.get("base_zoom", 1.0))
    if src_w / src_h > out_aspect:
        crop_h = _even(src_h / zoom)
        crop_w = _even(crop_h * out_aspect)
    else:
        crop_w = _even(src_w / zoom)
        crop_h = _even(crop_w / out_aspect)
    crop_w, crop_h = min(crop_w, src_w // 2 * 2), min(crop_h, src_h // 2 * 2)
    cwn = crop_w / src_w
    targets = face_targets(visual, start, end, cwn) if mode == "face_track" else []
    if mode == "face_track" and len(targets) < max(2, 0.2 * (end - start) * visual.get("face_fps", 1)):
        notes.append("Few faces detected in this clip; framing follows on-screen action instead.")
        targets = motion_targets(visual, start, end, layout_cfg.get("center_weight", 0.6))
    elif mode == "subject_track":
        targets = motion_targets(visual, start, end, layout_cfg.get("center_weight", 0.6))
    smoothing = float(layout_cfg.get("smoothing", 0.25))
    static_thr = float(layout_cfg.get("static_threshold", 0.08))
    xpath = build_path(targets, start, end, cuts, smoothing, static_thr, axis=1)
    ypath = build_path(targets, start, end, cuts, smoothing, static_thr, axis=2)
    # headroom: place faces in the upper third rather than dead centre vertically
    head = float(layout_cfg.get("headroom", 0.38)) if mode == "face_track" else 0.5
    xk = [(tmap.to_output_clamped(t), _clamp(cx * src_w - crop_w / 2, 0, src_w - crop_w)) for t, cx in xpath]
    yk = [(tmap.to_output_clamped(t), _clamp(cy * src_h - crop_h * head, 0, src_h - crop_h)) for t, cy in ypath]
    xk = simplify_keyframes(_dedupe(xk), tol=max(2.0, src_w * 0.004))
    yk = simplify_keyframes(_dedupe(yk), tol=max(2.0, src_h * 0.004))
    faces_out = _faces_in_output(visual, start, end, xpath, ypath, crop_w, crop_h, src_w, src_h, head)
    centre_y = sum(f[1] for f in faces_out) / len(faces_out) if faces_out else 0.45
    return {"mode": mode, "notes": notes,
            "crop": {"w": crop_w, "h": crop_h, "x_expr": piecewise_expr(xk), "y_expr": piecewise_expr(yk),
                     "x_keyframes": xk, "y_keyframes": yk},
            "upscale_factor": round(out_h / crop_h, 3), "faces_out": faces_out, "seam_y": None,
            "zoom_panel": "full", "zoom_center_y": round(_clamp(centre_y, 0.2, 0.8), 3)}


def _dedupe(points):
    out = []
    for t, x in sorted(points):
        if out and abs(t - out[-1][0]) < 1e-3:
            out[-1] = (t, x)
        else:
            out.append((t, x))
    return out


def _faces_in_output(visual, start, end, xpath, ypath, crop_w, crop_h, src_w, src_h, head):
    """Approximate face positions (normalized output y-range) for caption avoidance."""
    out = []
    for f in visual.get("faces", []):
        if not start <= f["t"] <= end:
            continue
        cx = _interp(xpath, f["t"]) * src_w - crop_w / 2
        cy = _interp(ypath, f["t"]) * src_h - crop_h * head
        cx = _clamp(cx, 0, src_w - crop_w)
        cy = _clamp(cy, 0, src_h - crop_h)
        for b in f["boxes"]:
            bx, by = b[0] * src_w - cx, b[1] * src_h - cy
            if 0 <= bx + b[2] * src_w / 2 <= crop_w:
                top, bot = by / crop_h, (by + b[3] * src_h) / crop_h
                out.append((round(top, 3), round((top + bot) / 2, 3), round(bot, 3)))
    return [(a, c, b) for a, c, b in [(o[0], o[1], o[2]) for o in out]]


def _interp(path, t):
    if not path:
        return 0.5
    if t <= path[0][0]:
        return path[0][1]
    for (t0, v0), (t1, v1) in zip(path[:-1], path[1:]):
        if t0 <= t <= t1:
            return v0 if t1 - t0 < 1e-6 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return path[-1][1]


def _fit_rect_to_aspect(rect: list[float], aspect: float, src_w: int, src_h: int,
                        focus: list[float] | None = None) -> tuple[int, int, int, int]:
    """Largest crop of pixel aspect `aspect` (w/h) INSIDE the normalized rect, centred on `focus`
    (the face) so the panel shows only the webcam, never the gameplay around it."""
    x, y, w, h = rect[0] * src_w, rect[1] * src_h, rect[2] * src_w, rect[3] * src_h
    inset = 0.03  # skip overlay borders/drop shadows around the webcam
    x, y, w, h = x + w * inset, y + h * inset, w * (1 - 2 * inset), h * (1 - 2 * inset)
    fx = focus[0] * src_w if focus else x + w / 2
    fy = focus[1] * src_h if focus else y + h / 2
    if w / h > aspect:
        nw, nh = h * aspect, h
    else:
        nw, nh = w, w / aspect
    nw, nh = _even(min(nw, w)), _even(min(nh, h))
    nx = _clamp(fx - nw / 2, x, x + w - nw)
    ny = _clamp(fy - nh * 0.45, y, y + h - nh)
    nx = _clamp(nx, 0, src_w - nw)
    ny = _clamp(ny, 0, src_h - nh)
    return int(nw), int(nh), int(nx), int(ny)


def _gaming_stack(src_w, src_h, out_w, out_h, cfg, visual, start, end, tmap, cuts, notes):
    cam = visual["facecam"]
    # The WHOLE webcam goes into its panel (never cropped into): the panel height follows the cam's own
    # shape, kept between 22% of the frame and the template's cam_ratio (at most 45%), so gameplay always
    # keeps the majority.
    r = list(cam["rect"])
    # trim a hair off sides that border the game (not the frame edge), so no sliver of gameplay shows
    tx, ty = r[2] * 0.012, r[3] * 0.012
    if r[0] > 0.002:
        r[0], r[2] = r[0] + tx, r[2] - tx
    if r[0] + r[2] < 0.998:
        r[2] -= tx
    if r[1] > 0.002:
        r[1], r[3] = r[1] + ty, r[3] - ty
    if r[1] + r[3] < 0.998:
        r[3] -= ty
    cx = _even(_clamp(r[0] * src_w, 0, src_w - 2))
    cy = _even(_clamp(r[1] * src_h, 0, src_h - 2))
    cw = _even(_clamp(r[2] * src_w, 2, src_w - cx))
    ch = _even(_clamp(r[3] * src_h, 2, src_h - cy))
    max_share = _clamp(float(cfg.get("cam_ratio", 0.36)), 0.22, 0.45)
    cam_h = _even(_clamp(out_w * ch / cw, out_h * 0.22, out_h * max_share))
    gp_h = out_h - cam_h
    fit = min(out_w / cw, cam_h / ch)
    shown_h = ch * fit
    if abs(shown_h - cam_h) > 4 or abs(cw * fit - out_w) > 4:
        notes.append("Webcam shown whole with a soft blurred fill around it (its shape differs from the panel).")
    gp_aspect = out_w / gp_h
    zoom = float(cfg.get("gameplay_zoom", 1.0))
    gh = _even(min(src_h, src_h / zoom))
    gw = _even(gh * gp_aspect)
    if gw > src_w:
        gw = src_w // 2 * 2
        gh = _even(gw / gp_aspect)
    targets = motion_targets(visual, start, end, cfg.get("center_weight", 0.7))
    # keep the cam overlay out of the gameplay panel when possible
    cam_l, cam_r = cam["rect"][0], cam["rect"][0] + cam["rect"][2]
    xpath = build_path(targets, start, end, cuts, float(cfg.get("smoothing", 0.15)),
                       float(cfg.get("static_threshold", 0.12)), axis=1)
    xk = []
    for t, c in xpath:
        x = _clamp(c * src_w - gw / 2, 0, src_w - gw)
        if cfg.get("avoid_cam_in_gameplay", True):
            l, r = x / src_w, (x + gw) / src_w
            if r > cam_l and l < cam_r:
                if cam_l > 0.5 and (cam_l * src_w - gw) >= 0:
                    x = min(x, cam_l * src_w - gw)
                elif cam_r < 0.5 and cam_r * src_w + gw <= src_w:
                    x = max(x, cam_r * src_w)
        xk.append((tmap.to_output_clamped(t), x))
    xk = simplify_keyframes(_dedupe(xk), tol=max(2.0, src_w * 0.004))
    gy = int((src_h - gh) / 2)
    cam_top = cfg.get("cam_position", "top") == "top"
    seam = cam_h / out_h if cam_top else gp_h / out_h
    face_in_panel = (cam_h - shown_h) / 2 + (cam["face_center"][1] * src_h - cy) * fit
    cam_face_out = face_in_panel / out_h if cam_top else (gp_h + face_in_panel) / out_h
    return {"mode": "gaming_stack", "notes": notes,
            "cam": {"w": cw, "h": ch, "x": cx, "y": cy, "panel_h": cam_h},
            "gameplay": {"w": gw, "h": gh, "x_expr": piecewise_expr(xk), "y": gy, "panel_h": gp_h,
                         "x_keyframes": xk},
            "cam_position": "top" if cam_top else "bottom",
            "upscale_factor": round(max(gp_h / gh, fit), 3),
            "faces_out": [(round(cam_face_out - 0.05, 3), round(cam_face_out, 3), round(cam_face_out + 0.05, 3))],
            "seam_y": round(seam, 4), "zoom_panel": "gameplay", "zoom_center_y": 0.5}


# --------------------------------------------------------------------------- filter graph
def zoompan_filter(z_expr: str, w: int, h: int, fps: float, center_y: float = 0.5) -> str:
    cy = f"ih*{center_y:.3f}-(ih/zoom*{center_y:.3f})"
    return (f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='{cy}':d=1:s={w}x{h}:fps={fps:g}")


def layout_filter(plan: dict, in_label: str, out_label: str, out_w: int, out_h: int, fps: float,
                  zoom_expr: str | None) -> str:
    """FFmpeg filter chain turning [in_label] into the framed [out_label] at out_w x out_h."""
    sc = "flags=lanczos"
    zp = (lambda w, h, cy: "," + zoompan_filter(zoom_expr, w, h, fps, cy)) if zoom_expr else (lambda w, h, cy: "")
    if plan["mode"] == "fit_blur":
        return (f"{in_label}split=2[fb_b][fb_f];"
                f"[fb_b]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h},"
                f"gblur=sigma=40,eq=brightness=-0.08[fb_bg];"
                f"[fb_f]scale={out_w}:-2:{sc}[fb_fg];"
                f"[fb_bg][fb_fg]overlay=(W-w)/2:(H-h)/2,fps={fps:g}{zp(out_w, out_h, 0.5)},setsar=1{out_label}")
    if plan["mode"] == "gaming_stack":
        c, g = plan["cam"], plan["gameplay"]
        ph = c["panel_h"]
        cam = (f"[gs_c]crop={c['w']}:{c['h']}:{c['x']}:{c['y']},split=2[gs_cb][gs_cf];"
               f"[gs_cb]scale={out_w}:{ph}:force_original_aspect_ratio=increase,crop={out_w}:{ph},"
               f"gblur=sigma=30,eq=brightness=-0.1[gs_cbg];"
               f"[gs_cf]scale={out_w}:{ph}:force_original_aspect_ratio=decrease:force_divisible_by=2:{sc}[gs_cfg];"
               f"[gs_cbg][gs_cfg]overlay=(W-w)/2:(H-h)/2,fps={fps:g},setsar=1[gs_cam]")
        gp = (f"[gs_g]crop={g['w']}:{g['h']}:x='{g['x_expr']}':y={g['y']},scale={out_w}:{g['panel_h']}:{sc},"
              f"fps={fps:g}{zp(out_w, g['panel_h'], 0.5)},setsar=1[gs_gp]")
        order = "[gs_cam][gs_gp]" if plan["cam_position"] == "top" else "[gs_gp][gs_cam]"
        return f"{in_label}split=2[gs_c][gs_g];{cam};{gp};{order}vstack=inputs=2{out_label}"
    cr = plan["crop"]
    return (f"{in_label}crop={cr['w']}:{cr['h']}:x='{cr['x_expr']}':y='{cr['y_expr']}',"
            f"scale={out_w}:{out_h}:{sc},fps={fps:g}{zp(out_w, out_h, plan.get('zoom_center_y', 0.5))},"
            f"setsar=1{out_label}")
