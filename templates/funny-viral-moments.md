# Template: Funny & Viral Moments

For comedy, entertainment and unexpected moments.

## What it does
- **Layout:** `face_track` (falls back to action tracking when no faces).
- **Moments:** laughter, surprise and sharp reaction peaks are weighted highest; the window starts
  only ~5 s before the peak so the clip opens fast, but sentence snapping keeps the setup that the
  joke needs.
- **Opening:** starts slightly zoomed (8%) and eases out in 0.8 s, plus an optional hook line for
  the first 2 s — a strong first frame without fake text.
- **Zoom:** punch-ins on laughs/reactions (max 3).
- **Pause removal:** tighter (gaps > 0.6 s) to keep pacing; spikes (laughs, crashes) are preserved.
- **Captions:** `bold_pop` word-by-word highlight.

## Agent guidance
- Keep the setup. A punchline without its setup is not funny and can misrepresent people.
- Avoid clips whose humour depends on mocking a private individual.
- hook_text must describe the real moment ("He did NOT expect that"), not invent one.

```json
{
  "id": "funny-viral-moments",
  "name": "Funny & Viral Moments",
  "duration": {"min": 12, "target": 30, "max": 55},
  "selection": {
    "weights": {"audio_spike": 1.4, "audio_energy": 0.9, "motion": 0.6, "scene_change": 0.3, "speech": 0.5,
                "laughter": 1.8, "surprise": 1.5, "excitement": 0.8, "emotion": 0.4, "story": 0.3, "question": 0.2},
    "lead_in": 5.0, "smooth_radius": 2,
    "score_weights": {"mean": 1.0, "peak": 1.0, "hook": 0.9, "ending": 0.3, "speech": 0.2, "dead": 1.0}
  },
  "layout": {"mode": "face_track", "base_zoom": 1.0, "headroom": 0.38, "smoothing": 0.25, "static_threshold": 0.08,
             "center_weight": 0.6},
  "zoom": {"enabled": true, "style": "punch", "strength": 0.14, "hold": 1.0, "max_per_clip": 3, "min_spacing": 3.5,
           "opening_zoom": 0.08, "jump_cut_style": "zoom_alternate", "jump_cut_zoom": 0.06, "max_zoom": 1.35},
  "captions": {"enabled": true, "preset": "bold_pop", "drop_fillers": true, "overrides": {}},
  "pause_removal": {"enabled": true, "min_pause": 0.6, "pad": 0.15, "max_removed_ratio": 0.3},
  "transitions": {"fade_in": 0.0, "fade_out": 0.12, "audio_fade_in": 0.03, "audio_fade_out": 0.2},
  "hook": {"enabled": true, "duration": 2.0},
  "music": {"mode": "off", "volume_db": -22, "duck": true, "default_mood": "funny", "max_speech_coverage": 0.35},
  "metadata": {"base_hashtags": ["#funny", "#comedy"], "credit": true, "creator_hashtag": true}
}
```
