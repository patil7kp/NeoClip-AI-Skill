"""Clip selection: score the WHOLE video second by second, then build context-complete windows.

Signals (each robust-normalized across the video, then weighted per template):
  audio_energy  loudness above the local 60 s baseline (people getting louder)
  audio_spike   sharp loudness peaks (shouts, laughs, impacts)
  motion        visual motion energy (action, gestures)
  scene_change  cuts / big visual changes
  speech        words per second (conversation density)
  laughter / surprise / excitement / emotion / story / question   transcript cue phrases

Windows are snapped to sentence boundaries and pauses so every clip has a beginning and an
ending, never cut mid-word, and never sacrifice context just to be shorter. Segments already
used in completed Shorts are excluded (small tolerance), so repeat runs find NEW moments.

This module is deterministic and needs no AI provider. The calling agent is expected to review
the ranked candidates (with excerpts and reasons) and can override with its own plan.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import fmt_ts, merge_intervals, overlap, subtract_intervals
from scripts.timestamp_manager import overlap_conflict
from scripts.transcription import all_words

CUES: dict[str, list[str]] = {
    "laughter": [r"\bha(ha)+\b", r"\blol\b", r"\blmao\b", r"\[laugh(ter|s|ing)?\]", r"\bhilarious\b",
                 r"\bso funny\b", r"\bi'?m dying\b", r"\bthat'?s funny\b", r"\bjoke\b"],
    "surprise": [r"\bno way\b", r"\bwhat the\b", r"\boh my (god|gosh)\b", r"\bwait,? what\b", r"\bare you serious\b",
                 r"\bwhat\?!?", r"\bwow\b", r"\bunbelievable\b", r"\bi can'?t believe\b", r"\bholy\b",
                 r"\bdid (you|that) just\b", r"\bwhoa\b"],
    "excitement": [r"\blet'?s go+\b", r"\byes+!?\b", r"\bclutch\b", r"\binsane\b", r"\bcrazy\b", r"\bunreal\b",
                   r"\bwe did it\b", r"\bgg\b", r"\bace\b", r"\bheadshot\b", r"\bvictory\b", r"\bwin(ning)?\b",
                   r"\bepic\b", r"\bamazing\b"],
    "emotion": [r"\bi love\b", r"\bcried\b", r"\bcrying\b", r"\bhonestly\b", r"\bheartbroken\b", r"\bproud\b",
                r"\bscared\b", r"\bterrified\b", r"\bmeans a lot\b", r"\bnever forget\b", r"\bthank you\b"],
    "story": [r"\bso basically\b", r"\bthe thing is\b", r"\band then\b", r"\bone time\b", r"\bstory\b",
              r"\bwhat happened\b", r"\bturns out\b", r"\bthe secret\b", r"\bhere'?s (why|how|the)\b",
              r"\bthe reason\b", r"\bmost people\b", r"\bthe truth\b"],
    "question": [r"\?"],
}
_CUE_RE = {k: [re.compile(p, re.I) for p in v] for k, v in CUES.items()}

LABELS = {
    "laughter": "funny_moment", "surprise": "unexpected_reaction", "excitement": "epic_moment",
    "emotion": "emotional_moment", "story": "story_time", "question": "big_question",
    "audio_spike": "best_reaction", "motion": "intense_moment", "speech": "best_conversation",
    "audio_energy": "best_reaction", "scene_change": "highlight",
}
SENTENCE_END = re.compile(r"[.!?…]['\")\]]*$")


# --------------------------------------------------------------------------- features
def _robust(values: list[float]) -> list[float]:
    if not values:
        return values
    s = sorted(values)
    n = len(s)
    med = s[n // 2]
    iqr = (s[min(n - 1, int(n * 0.75))] - s[int(n * 0.25)]) or (max(s) - min(s)) or 1.0
    return [max(-2.0, min(4.0, (v - med) / iqr)) for v in values]


def _smooth(values: list[float], radius: int) -> list[float]:
    if radius <= 0 or not values:
        return values
    out, acc = [], 0.0
    pref = [0.0]
    for v in values:
        acc += v
        pref.append(acc)
    n = len(values)
    for i in range(n):
        a, b = max(0, i - radius), min(n, i + radius + 1)
        out.append((pref[b] - pref[a]) / (b - a))
    return out


def cue_hits(transcript: dict | None) -> list[dict]:
    hits = []
    for seg in (transcript or {}).get("segments", []):
        words = seg.get("words") or []
        for w in words:
            token = w["word"]
            for cat, pats in _CUE_RE.items():
                if cat == "question":
                    continue
                if any(p.search(token) for p in pats):
                    hits.append({"t": w["start"], "category": cat, "text": token})
        text = seg["text"]
        for cat, pats in _CUE_RE.items():
            for p in pats:
                for m in p.finditer(text):
                    if " " in m.group(0) or cat == "question":
                        # place multi-word cue at the proportional position inside the segment
                        frac = m.start() / max(1, len(text))
                        t = seg["start"] + frac * (seg["end"] - seg["start"])
                        hits.append({"t": round(t, 2), "category": cat, "text": m.group(0)})
    return hits


REPLAY_WEIGHT = 1.4  # YouTube "most replayed" graph: viewers rewatched this part


def build_timeline(duration: float, visual: dict | None, audio: dict | None,
                   transcript: dict | None, heatmap: list[dict] | None = None) -> dict:
    n = max(1, int(math.ceil(duration)))
    feat = {k: [0.0] * n for k in ("audio_energy", "audio_spike", "motion", "scene_change", "speech",
                                   "silent", "replay", *CUES.keys())}
    for h in heatmap or []:
        for i in range(int(h["start"]), min(n, int(math.ceil(h["end"])))):
            feat["replay"][i] = max(feat["replay"][i], float(h["value"]))
    if audio and audio.get("times"):
        for t, z in zip(audio["times"], audio["energy_z"]):
            i = int(t)
            if 0 <= i < n:
                feat["audio_energy"][i] = max(feat["audio_energy"][i], z)
        for sp in audio.get("spikes", []):
            for d in (-1, 0, 1):
                i = int(sp["t"]) + d
                if 0 <= i < n:
                    feat["audio_spike"][i] = max(feat["audio_spike"][i], sp["z"] * (1.0 if d == 0 else 0.5))
        for s, e in audio.get("silences", []):
            for i in range(int(s), min(n, int(math.ceil(e)))):
                if overlap((i, i + 1), (s, e)) >= 0.8:
                    feat["silent"][i] = 1.0
    if visual and visual.get("times"):
        for t, m in zip(visual["times"], visual["motion"]):
            i = int(t)
            if 0 <= i < n:
                feat["motion"][i] = max(feat["motion"][i], m)
        for t in visual.get("scene_cuts", []):
            i = int(t)
            if 0 <= i < n:
                feat["scene_change"][i] = 1.0
    for w in all_words(transcript):
        i = int(w["start"])
        if 0 <= i < n:
            feat["speech"][i] += 1.0
    for h in cue_hits(transcript):
        i = int(h["t"])
        if 0 <= i < n:
            feat[h["category"]][i] += 1.0
    norm = {}
    for k, v in feat.items():
        if k in ("silent", "scene_change", "replay") or k in CUES:
            norm[k] = [min(1.0, x) for x in v]
        elif k == "speech":
            norm[k] = [min(1.0, x / 3.0) for x in v]
        else:
            norm[k] = [(x + 2) / 6 for x in _robust(v)]  # map [-2,4] -> [0,1]
    return {"n": n, "features": norm, "has_replay": bool(heatmap)}


def interest_curve(timeline: dict, weights: dict[str, float], smooth_radius: int = 2) -> list[float]:
    f = timeline["features"]
    weights = dict(weights)
    if timeline.get("has_replay"):
        weights.setdefault("replay", REPLAY_WEIGHT)
    total_w = sum(abs(w) for w in weights.values()) or 1.0
    raw = []
    for i in range(timeline["n"]):
        s = sum(w * f[k][i] for k, w in weights.items() if k in f)
        s -= 0.35 * f["silent"][i] * (1 - f["audio_spike"][i])
        raw.append(s / total_w)
    return _smooth(raw, smooth_radius)


# --------------------------------------------------------------------------- boundaries
def _sentence_bounds(transcript: dict | None) -> tuple[list[float], list[float]]:
    starts, ends = [], []
    words = all_words(transcript)
    for i, w in enumerate(words):
        prev = words[i - 1] if i else None
        if prev is None or SENTENCE_END.search(prev["word"]) or w["start"] - prev["end"] > 0.6:
            starts.append(w["start"])
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or SENTENCE_END.search(w["word"]) or nxt["start"] - w["end"] > 0.6:
            ends.append(w["end"])
    return starts, ends


def _word_at(words: list[dict], t: float) -> dict | None:
    for w in words:
        if w["start"] < t < w["end"]:
            return w
    return None


def snap_window(start: float, end: float, peak: float, duration: float, dur_cfg: dict,
                transcript: dict | None, audio: dict | None, bounds=None) -> tuple[float, float]:
    starts, ends = bounds if bounds else _sentence_bounds(transcript)
    lo_s = max(0.0, start - 6.0)
    cand = [s for s in starts if lo_s <= s <= start + 2.0 and s < peak - 1.0]
    if cand:
        start = max(cand, key=lambda s: -abs(s - start))  # nearest sentence start
    elif audio:
        for s, e in audio.get("silences", []):
            if s <= start <= e and e < peak:
                start = e - 0.15
                break
    min_end = max(peak + 3.0, start + dur_cfg["min"])
    max_end = min(duration, start + dur_cfg["max"])
    cand = [e for e in ends if min_end <= e <= max_end]
    if cand:
        end = min(cand, key=lambda e: abs(e - max(end, min_end)))
    end = max(min(end, max_end), min(min_end, duration))
    words = all_words(transcript, start - 1, end + 1)
    w = _word_at(words, start)
    if w:
        start = w["start"]
    w = _word_at(words, end)
    if w and w["end"] - start <= dur_cfg["max"]:
        end = w["end"]
    start = max(0.0, start - 0.12)          # tiny breath before first word
    end = min(duration, end + 0.25)         # let the last word ring out
    return round(start, 3), round(end, 3)


# --------------------------------------------------------------------------- scoring
def score_window(curve: list[float], timeline: dict, start: float, end: float,
                 transcript: dict | None, sel_cfg: dict) -> dict:
    f = timeline["features"]
    a, b = int(start), max(int(start) + 1, int(math.ceil(end)))
    seg = curve[a:b] or [0.0]
    mean = sum(seg) / len(seg)
    peak = max(seg)
    hook = sum(curve[a:a + 3] or [0.0]) / max(1, len(curve[a:a + 3]))
    dead = sum(f["silent"][a:b]) / max(1, b - a)
    speech_cov = sum(1 for x in f["speech"][a:b] if x > 0) / max(1, b - a)
    words = all_words(transcript, start, end)
    ending = 1.0 if (not words or SENTENCE_END.search(words[-1]["word"]) or end - words[-1]["end"] > 0.3) else 0.4
    w = sel_cfg.get("score_weights", {})
    score = (w.get("mean", 1.0) * mean + w.get("peak", 0.8) * peak + w.get("hook", 0.6) * hook
             + w.get("ending", 0.2) * ending + w.get("speech", 0.2) * speech_cov
             - w.get("dead", 0.8) * dead)
    return {"score": round(score, 4), "mean": round(mean, 3), "peak": round(peak, 3),
            "hook": round(hook, 3), "ending": ending, "dead_fraction": round(dead, 3),
            "speech_coverage": round(speech_cov, 3)}


def _dominant_cue(timeline: dict, start: float, end: float, weights: dict) -> tuple[str, list[str]]:
    f = timeline["features"]
    a, b = int(start), int(math.ceil(end))
    totals = {}
    for k in list(CUES.keys()) + ["audio_spike", "motion", "speech", "audio_energy"]:
        vals = f[k][a:b]
        if not vals:
            continue
        base = sum(vals) if k in CUES else max(vals)
        totals[k] = base * (1 + weights.get(k, 0.0))
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    reasons = []
    for k, v in ranked[:3]:
        if v <= 0.0:
            continue
        reasons.append({
            "audio_spike": "sharp loudness peak (reaction/shout/laugh)",
            "audio_energy": "voices noticeably louder than the surrounding minute",
            "motion": "high on-screen action",
            "speech": "dense conversation",
            "laughter": "laughter cues in transcript",
            "surprise": "surprise cues (\"no way\", \"what\")",
            "excitement": "excitement cues (\"let's go\", \"insane\")",
            "emotion": "emotional statements",
            "story": "story/explanation markers",
            "question": "questions being asked",
        }.get(k, k))
    replay = f.get("replay", [])[a:b]
    if replay and max(replay) >= 0.6:
        reasons.insert(0, f"YouTube 'most replayed' peak ({max(replay):.0%} of the video's top replay level)")
    best = ranked[0][0] if ranked and ranked[0][1] > 0 else "audio_energy"
    cue_order = [k for k, v in ranked if k in CUES and k != "question" and v >= 1]
    category = cue_order[0] if cue_order else best
    return category, reasons


def select_clips(duration: float, visual: dict | None, audio: dict | None, transcript: dict | None,
                 template: dict, used_segments: list[list[float]] | None = None, count: int = 3,
                 candidate_pool: int = 12, heatmap: list[dict] | None = None) -> dict:
    """Return {"candidates": ranked list, "selected": top `count`} excluding used segments."""
    sel = template["selection"]
    dur_cfg = template["duration"]
    used = merge_intervals(used_segments or [])
    timeline = build_timeline(duration, visual, audio, transcript, heatmap)
    curve = interest_curve(timeline, sel["weights"], sel.get("smooth_radius", 2))
    bounds = _sentence_bounds(transcript)

    # mask used seconds so peaks are only searched in unused material
    masked = list(curve)
    for s, e in used:
        for i in range(int(s), min(len(masked), int(math.ceil(e)))):
            masked[i] = -1e9
    order = sorted(range(len(masked)), key=lambda i: -masked[i])
    spacing = max(4.0, dur_cfg["min"] / 2)
    peaks: list[int] = []
    for i in order:
        if masked[i] <= -1e8 or len(peaks) >= candidate_pool * 4:
            break
        if all(abs(i - p) >= spacing for p in peaks):
            peaks.append(i)

    lead = sel.get("lead_in", 6.0)
    cands: list[dict] = []
    for p in peaks:
        peak_t = p + 0.5
        start = max(0.0, peak_t - lead)
        end = min(duration, start + dur_cfg["target"])
        if end - start < dur_cfg["min"]:
            start = max(0.0, end - dur_cfg["target"])
        s, e = snap_window(start, end, peak_t, duration, dur_cfg, transcript, audio, bounds)
        if e - s < min(dur_cfg["min"], duration) - 0.01:
            continue
        if used and overlap_conflict(s, e, used):
            # try to slide the window out of the used region
            free = [seg for seg in subtract_intervals([0, duration], used) if seg[0] <= peak_t <= seg[1]]
            if not free:
                continue
            fs, fe = free[0]
            s, e = max(s, fs), min(e, fe)
            if e - s < dur_cfg["min"] or overlap_conflict(s, e, used):
                continue
        metrics = score_window(curve, timeline, s, e, transcript, sel)
        category, reasons = _dominant_cue(timeline, s, e, sel["weights"])
        cands.append({"start": s, "end": e, "duration": round(e - s, 2), "peak": round(peak_t, 2),
                      **metrics, "category": category, "label": LABELS.get(category, "best_moment"),
                      "reasons": reasons})

    # non-maximum suppression: no two candidates share > 10% of the shorter one
    cands.sort(key=lambda c: -c["score"])
    kept: list[dict] = []
    for c in cands:
        if all(overlap((c["start"], c["end"]), (k["start"], k["end"]))
               <= 0.10 * min(c["duration"], k["duration"]) for k in kept):
            kept.append(c)
        if len(kept) >= max(candidate_pool, count):
            break

    if len(kept) < count:  # short or flat video: fall back to evenly spread unused windows
        for seg in subtract_intervals([0, duration], used + [[k["start"], k["end"]] for k in kept]):
            t = seg[0]
            while seg[1] - t >= dur_cfg["min"] and len(kept) < count:
                e = min(seg[1], t + dur_cfg["target"])
                s2, e2 = snap_window(t, e, (t + e) / 2, duration, dur_cfg, transcript, audio, bounds)
                s2, e2 = max(s2, seg[0]), min(e2, seg[1])
                if e2 - s2 >= dur_cfg["min"] - 0.01:
                    m = score_window(curve, timeline, s2, e2, transcript, sel)
                    kept.append({"start": s2, "end": e2, "duration": round(e2 - s2, 2),
                                 "peak": round((s2 + e2) / 2, 2), **m, "category": "fallback",
                                 "label": "best_moment", "reasons": ["even coverage fallback (few strong signals)"]})
                t = e2 + 1.0

    for rank, c in enumerate(kept, 1):
        c["rank"] = rank
        c["range"] = f"{fmt_ts(c['start'])} - {fmt_ts(c['end'])}"
        words = all_words(transcript, c["start"], c["end"])
        c["excerpt"] = " ".join(w["word"] for w in words)[:600]
        c["hook_excerpt"] = " ".join(w["word"] for w in words if w["start"] < c["start"] + 4)[:160]
    return {"candidates": kept, "selected": kept[:count], "used_segments": used,
            "unused_seconds": round(sum(e - s for s, e in subtract_intervals([0, duration], used)), 1)}


def validate_plan_clips(clips: list[dict], duration: float, used: list[list[float]],
                        template: dict) -> tuple[list[dict], list[str]]:
    """Validate agent-provided clips. Returns (clean clips, warnings). Raises nothing; bad clips are dropped."""
    out, warnings = [], []
    d = template["duration"]
    taken: list[list[float]] = []
    for i, c in enumerate(clips, 1):
        s, e = float(c["start"]), float(c["end"])
        if not (0 <= s < e <= duration + 0.5):
            warnings.append(f"clip {i}: range {s}-{e} is outside the video (0-{duration:.1f}); dropped")
            continue
        e = min(e, duration)
        if e - s > 180:
            warnings.append(f"clip {i}: {e - s:.0f}s exceeds the 3-minute Shorts limit; dropped")
            continue
        if e - s < 5:
            warnings.append(f"clip {i}: shorter than 5 s; dropped")
            continue
        if not d["min"] <= e - s <= d["max"]:
            warnings.append(f"clip {i}: {e - s:.0f}s is outside the template range {d['min']}-{d['max']}s "
                            "(kept, because context beats length)")
        ov = overlap_conflict(s, e, used + taken)
        if ov and not c.get("overlap_reason"):
            warnings.append(f"clip {i}: overlaps already-used footage by {ov:.1f}s and no overlap_reason "
                            "was given; dropped to prevent a duplicate")
            continue
        taken.append([s, e])
        out.append({**c, "start": s, "end": e})
    return out, warnings
