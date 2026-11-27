# Template: Storytelling & Commentary

For storytelling, commentary and explanatory videos.

## What it does
- **Moments:** story markers ("so basically", "turns out", "here's why"), emotional statements and
  explanations; longer windows (30-90 s) with sentence-level snapping so each clip has a clear
  beginning, middle and end.
- **Layout:** `face_track` with static framing per shot.
- **Zoom:** subtle push-in and alternate-zoom jump cuts; emphasis zoom on key lines (max 2).
- **Captions:** `story` preset (word highlight, slightly calmer than bold_pop).
- **Pause removal:** moderate, never cutting explanations (max 20% removed).
- **Music:** `auto` — a verified licensed bed may be added under narration only if the clip has
  little dialogue and a verified track exists; otherwise original audio is kept.

## Agent guidance
- Verify from the excerpt that the clip starts where the idea starts and ends after the conclusion.
- If the explanation needs more than 90 s, prefer the most self-contained part or split into
  "Part 1/Part 2" only when each part stands on its own.

```json
{
  "id": "storytelling-commentary",
  "name": "Storytelling & Commentary",
  "duration": {"min": 30, "target": 55, "max": 90},
  "selection": {
    "weights": {"audio_spike": 0.4, "audio_energy": 0.6, "motion": 0.2, "scene_change": 0.2, "speech": 1.2,
                "laughter": 0.5, "surprise": 0.8, "excitement": 0.4, "emotion": 1.3, "story": 1.6, "question": 0.8},
    "lead_in": 12.0, "smooth_radius": 4,
    "score_weights": {"mean": 1.0, "peak": 0.5, "hook": 0.6, "ending": 0.7, "speech": 0.7, "dead": 0.8}
  },
  "layout": {"mode": "face_track", "base_zoom": 1.0, "headroom": 0.36, "smoothing": 0.2, "static_threshold": 0.08,
             "center_weight": 0.6},
  "zoom": {"enabled": true, "style": "subtle", "push_in": 0.04, "strength": 0.07, "hold": 1.5, "max_per_clip": 2,
           "min_spacing": 8.0, "opening_zoom": 0.0, "jump_cut_style": "zoom_alternate", "jump_cut_zoom": 0.05,
           "max_zoom": 1.2},
  "captions": {"enabled": true, "preset": "story", "drop_fillers": true, "overrides": {}},
  "pause_removal": {"enabled": true, "min_pause": 0.8, "pad": 0.2, "max_removed_ratio": 0.2},
  "transitions": {"fade_in": 0.0, "fade_out": 0.25, "audio_fade_in": 0.05, "audio_fade_out": 0.35},
  "hook": {"enabled": false, "duration": 2.5},
  "music": {"mode": "auto", "volume_db": -24, "duck": true, "default_mood": "cinematic", "max_speech_coverage": 0.35},
  "metadata": {"base_hashtags": ["#storytime"], "credit": true, "creator_hashtag": true}
}
```
