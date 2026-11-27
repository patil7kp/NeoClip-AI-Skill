"""Trimming and pause removal with an exact source->output timeline map.

`keep_intervals` decides which parts of a clip survive pause removal:
  * only gaps with NO words and below the silence threshold are candidates
  * gaps shorter than `min_pause` are kept (natural rhythm)
  * `pad` seconds of air stay on each side of speech so cuts don't clip syllables
  * gaps containing a loud spike (laugh, impact, sound effect) are never removed
The TimelineMap converts any source timestamp into output time; captions, zooms and crop
keyframes all go through it, so sync survives trimming.
"""
from __future__ import annotations

import bisect
import sys
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import merge_intervals, overlap
from scripts.transcription import all_words


def keep_intervals(start: float, end: float, words: list[dict], audio: dict | None,
                   cfg: dict) -> list[list[float]]:
    if not cfg.get("enabled"):
        return [[start, end]]
    min_pause = float(cfg.get("min_pause", 0.8))
    pad = float(cfg.get("pad", 0.18))
    max_removed_ratio = float(cfg.get("max_removed_ratio", 0.25))
    words = sorted((w for w in words if w["end"] > start and w["start"] < end), key=lambda w: w["start"])
    if not words:
        return [[start, end]]
    silences = (audio or {}).get("silences", [])
    spikes = [s["t"] for s in (audio or {}).get("spikes", [])]
    gaps = []
    # gaps between consecutive words (and before first / after last)
    points = [(start, words[0]["start"])]
    points += [(words[i]["end"], words[i + 1]["start"]) for i in range(len(words) - 1)]
    points += [(words[-1]["end"], end)]
    for gs, ge in points:
        if ge - gs < min_pause:
            continue
        cut_s, cut_e = gs + pad, ge - pad
        if cut_e - cut_s < min_pause - 2 * pad or cut_e <= cut_s:
            continue
        if any(cut_s - 0.3 <= t <= cut_e + 0.3 for t in spikes):
            continue  # preserve reactions and sound effects
        silent = sum(overlap((cut_s, cut_e), s) for s in silences) if silences else (cut_e - cut_s)
        if silent < 0.8 * (cut_e - cut_s):
            continue  # there is sound in the gap (music, sfx, crowd) - keep it
        gaps.append([cut_s, cut_e])
    gaps = merge_intervals(gaps)
    removed = sum(e - s for s, e in gaps)
    if removed > max_removed_ratio * (end - start):
        gaps.sort(key=lambda g: -(g[1] - g[0]))
        keep_budget = max_removed_ratio * (end - start)
        chosen, acc = [], 0.0
        for g in gaps:
            if acc + (g[1] - g[0]) <= keep_budget:
                chosen.append(g)
                acc += g[1] - g[0]
        gaps = merge_intervals(chosen)
    keeps, cur = [], start
    for s, e in gaps:
        if s > cur:
            keeps.append([round(cur, 3), round(s, 3)])
        cur = e
    if end > cur:
        keeps.append([round(cur, 3), round(end, 3)])
    return [k for k in keeps if k[1] - k[0] >= 0.25] or [[start, end]]


@dataclass
class TimelineMap:
    keeps: list[list[float]]
    _out_starts: list[float] = field(default_factory=list, init=False)

    def __post_init__(self):
        acc = 0.0
        for s, e in self.keeps:
            self._out_starts.append(acc)
            acc += e - s
        self.duration = acc

    def to_output(self, t: float) -> float | None:
        """Map source time to output time; None if t falls inside removed material."""
        for (s, e), o in zip(self.keeps, self._out_starts):
            if s - 1e-6 <= t <= e + 1e-6:
                return round(o + (t - s), 4)
        return None

    def to_output_clamped(self, t: float) -> float:
        starts = [k[0] for k in self.keeps]
        i = bisect.bisect_right(starts, t) - 1
        if i < 0:
            return 0.0
        s, e = self.keeps[i]
        return round(self._out_starts[i] + min(max(t, s), e) - s, 4)

    def to_source(self, out_t: float) -> float:
        i = max(0, bisect.bisect_right(self._out_starts, out_t) - 1)
        s, e = self.keeps[i]
        return s + min(out_t - self._out_starts[i], e - s)

    def map_words(self, words: list[dict]) -> list[dict]:
        out = []
        for w in words:
            a, b = self.to_output(w["start"]), self.to_output(w["end"])
            if a is None and b is None:
                continue
            a = self.to_output_clamped(w["start"]) if a is None else a
            b = self.to_output_clamped(w["end"]) if b is None else b
            if b - a < 0.04:
                b = a + 0.04
            out.append({**w, "start": a, "end": min(b, self.duration)})
        return out

    @property
    def removed_seconds(self) -> float:
        return round((self.keeps[-1][1] - self.keeps[0][0]) - self.duration, 3)


def trim_filter(keeps: list[list[float]], offset: float, has_audio: bool, afade: float = 0.012) -> tuple[str, str, str]:
    """Return (filtergraph, video_label, audio_label). `offset` = input seek time (trim times are relative)."""
    parts = []
    n = len(keeps)
    vlabels, alabels = [], []
    for i, (s, e) in enumerate(keeps):
        rs, re_ = s - offset, e - offset
        parts.append(f"[0:v]trim=start={rs:.4f}:end={re_:.4f},setpts=PTS-STARTPTS[v{i}]")
        vlabels.append(f"[v{i}]")
        if has_audio:
            d = re_ - rs
            fade = min(afade, d / 4)
            parts.append(f"[0:a]atrim=start={rs:.4f}:end={re_:.4f},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:d={fade:.3f},afade=t=out:st={max(0, d - fade):.4f}:d={fade:.3f}[a{i}]")
            alabels.append(f"[a{i}]")
    if n == 1:
        parts.append(f"{vlabels[0]}null[vcat]")
        if has_audio:
            parts.append(f"{alabels[0]}anull[acat]")
    else:
        inter = "".join(v + (a if has_audio else "") for v, a in zip(vlabels, alabels or [""] * n))
        parts.append(f"{inter}concat=n={n}:v=1:a={1 if has_audio else 0}[vcat]" + ("[acat]" if has_audio else ""))
    return ";".join(parts), "[vcat]", "[acat]" if has_audio else ""


def clip_words(transcript: dict | None, start: float, end: float) -> list[dict]:
    return all_words(transcript, start, end)
