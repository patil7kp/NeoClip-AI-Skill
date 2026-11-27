"""Edit planning: pause removal, emphasis zooms, jump-cut treatment, hook, fades.

Produces an EditPlan (pure data) that video_renderer turns into one FFmpeg filtergraph.
Effects are deliberately restrained: zooms only on real emphasis (reaction spikes or cue words),
spaced apart and capped per clip; templates can switch every effect off.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.clip_selector import cue_hits
from scripts.video_cutter import TimelineMap, clip_words, keep_intervals


def _ease(var: str, a: float, d: float) -> str:
    """Smoothstep from 0 at t=a to 1 at t=a+d."""
    r = f"clip(({var}-{a:.3f})/{max(d, 0.01):.3f},0,1)"
    return f"({r}*{r}*(3-2*{r}))"


def zoom_events(start: float, end: float, tmap: TimelineMap, audio: dict | None, transcript: dict | None,
                zcfg: dict) -> list[dict]:
    if not zcfg.get("enabled") or zcfg.get("style") == "none":
        return []
    cands = []
    for sp in (audio or {}).get("spikes", []):
        if start + 0.8 <= sp["t"] <= end - 1.2:
            cands.append((sp["z"], sp["t"], "reaction"))
    seg = {"segments": [s for s in (transcript or {}).get("segments", []) if s["end"] > start and s["start"] < end]}
    for h in cue_hits(seg):
        if h["category"] in ("surprise", "laughter", "excitement", "emotion") and start + 0.8 <= h["t"] <= end - 1.2:
            cands.append((1.8, h["t"], h["category"]))
    cands.sort(key=lambda c: -c[0])
    spacing = float(zcfg.get("min_spacing", 4.0))
    max_n = int(zcfg.get("max_per_clip", 3))
    chosen: list[dict] = []
    for z, t, why in cands:
        ot = tmap.to_output(t)
        if ot is None:
            continue
        if all(abs(ot - c["t"]) >= spacing for c in chosen):
            chosen.append({"t": round(max(0.0, ot - 0.12), 3), "reason": why, "strength": float(zcfg.get("strength", 0.12)),
                           "hold": float(zcfg.get("hold", 1.2))})
        if len(chosen) >= max_n:
            break
    return sorted(chosen, key=lambda c: c["t"])


def zoom_expression(events: list[dict], duration: float, zcfg: dict, fps: float,
                    cut_points: list[float]) -> str | None:
    var = f"(on/{fps:g})"
    terms = []
    style = zcfg.get("style", "punch")
    if zcfg.get("enabled") and style == "subtle":
        push = float(zcfg.get("push_in", 0.05))
        terms.append(f"{push:.3f}*{_ease(var, 0, max(1.0, duration))}")
    if zcfg.get("opening_zoom"):
        oz = float(zcfg["opening_zoom"])
        terms.append(f"{oz:.3f}*(1-{_ease(var, 0, 0.8)})")
    for ev in events:
        a, s, hold = ev["t"], ev["strength"], ev["hold"]
        ri, ro = 0.18, 0.45
        terms.append(f"{s:.3f}*{_ease(var, a, ri)}*(1-{_ease(var, a + ri + hold, ro)})")
    if zcfg.get("jump_cut_style") == "zoom_alternate" and cut_points:
        amt = float(zcfg.get("jump_cut_zoom", 0.06))
        # alternate framing on every jump cut so pause removal reads as an intentional cut
        for i, cp in enumerate(cut_points):
            sign = 1 if i % 2 == 0 else -1
            terms.append(f"{sign * amt:.3f}*gte({var},{cp:.3f})")
    if not terms:
        return None
    max_z = float(zcfg.get("max_zoom", 1.35))
    return f"clip(1+{'+'.join(terms)},1,{max_z:.3f})"


def plan_edit(clip: dict, template: dict, audio: dict | None, transcript: dict | None, fps: float) -> dict:
    start, end = float(clip["start"]), float(clip["end"])
    words = clip_words(transcript, start, end)
    keeps = keep_intervals(start, end, words, audio, template["pause_removal"])
    tmap = TimelineMap(keeps)
    zcfg = template["zoom"]
    events = zoom_events(start, end, tmap, audio, transcript, zcfg)
    cut_points = []
    acc = 0.0
    for s, e in keeps[:-1]:
        acc += e - s
        cut_points.append(round(acc, 3))
    zexpr = zoom_expression(events, tmap.duration, zcfg, fps, cut_points)
    tr = template["transitions"]
    hook_cfg = template["hook"]
    hook = None
    if hook_cfg.get("enabled") and clip.get("hook_text"):
        hook = {"text": clip["hook_text"], "duration": hook_cfg.get("duration", 2.5)}
    return {
        "source_start": start, "source_end": end, "keeps": keeps, "tmap": tmap,
        "output_duration": round(tmap.duration, 3), "removed_seconds": tmap.removed_seconds,
        "jump_cuts": cut_points, "zoom_events": events, "zoom_expr": zexpr,
        "fade_in": float(tr.get("fade_in", 0.0)), "fade_out": float(tr.get("fade_out", 0.0)),
        "audio_fade_in": float(tr.get("audio_fade_in", 0.05)), "audio_fade_out": float(tr.get("audio_fade_out", 0.25)),
        "hook": hook, "words": words,
    }


def describe_edit(plan: dict) -> dict:
    """JSON-safe summary for reports."""
    return {k: v for k, v in plan.items() if k not in ("tmap", "words", "zoom_expr")} | {
        "zoom": bool(plan["zoom_expr"]), "keep_segments": len(plan["keeps"])}
