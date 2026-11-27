# Template: Minimal Professional

Clean, consistent Shorts for brands, education, interviews and corporate content. Default template.

## What it does
- **Layout:** `face_track` with static framing per shot (no visible camera moves).
- **Effects:** none — no zooms, no hook overlay, no animated captions.
- **Captions:** `minimal` (sentence-case, soft box, no highlighting), standardized position.
- **Pause removal:** conservative (gaps > 1.0 s only).
- **Audio:** loudness-normalized original audio (-14 LUFS, -1 dBTP); no music.

## Agent guidance
- Prioritise clarity: complete thoughts, clean starts and endings, no mid-sentence cuts.
- Titles should be descriptive and factual.

```json
{
  "id": "minimal-professional",
  "name": "Minimal Professional",
  "duration": {"min": 20, "target": 45, "max": 75},
  "selection": {
    "weights": {"audio_spike": 0.4, "audio_energy": 0.6, "motion": 0.2, "scene_change": 0.1, "speech": 1.2,
                "laughter": 0.4, "surprise": 0.6, "excitement": 0.4, "emotion": 0.9, "story": 1.1, "question": 0.8},
    "lead_in": 10.0, "smooth_radius": 3,
    "score_weights": {"mean": 1.0, "peak": 0.5, "hook": 0.5, "ending": 0.7, "speech": 0.7, "dead": 0.8}
  },
  "layout": {"mode": "face_track", "base_zoom": 1.0, "headroom": 0.36, "smoothing": 0.15, "static_threshold": 0.12,
             "center_weight": 0.7},
  "zoom": {"enabled": false, "style": "none", "strength": 0.0, "hold": 1.0, "max_per_clip": 0, "min_spacing": 10.0,
           "opening_zoom": 0.0, "jump_cut_style": "none", "max_zoom": 1.0},
  "captions": {"enabled": true, "preset": "minimal", "drop_fillers": true, "overrides": {}},
  "pause_removal": {"enabled": true, "min_pause": 1.0, "pad": 0.22, "max_removed_ratio": 0.15},
  "transitions": {"fade_in": 0.0, "fade_out": 0.2, "audio_fade_in": 0.05, "audio_fade_out": 0.3},
  "hook": {"enabled": false, "duration": 2.5},
  "music": {"mode": "off", "volume_db": -24, "duck": true, "default_mood": "calm", "max_speech_coverage": 0.35},
  "sfx": {"enabled": false, "kinds": [], "max_per_clip": 0, "gain_db": -20, "min_spike_z": 3.5},
  "metadata": {"base_hashtags": [], "credit": true, "creator_hashtag": false}
}
```
