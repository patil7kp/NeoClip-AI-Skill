# Template: Podcast & Conversation

For podcasts, interviews and discussions.

## What it does
- **Layout:** `face_track` — follows the dominant face, switches subject only on shot changes,
  frames a two-shot when both speakers fit, and holds a static crop per shot when the person
  barely moves (no jitter). Faces sit in the upper third (headroom).
- **Moments:** dense conversation with strong statements, questions + answers, emotional or
  surprising lines, laughter. Windows snap to sentence boundaries; context beats brevity.
- **Pause removal:** removes silences > 0.7 s (keeps 0.18 s of air each side; never cuts inside
  words; never removes more than 25% of the clip). Jump cuts get an alternating subtle zoom so
  they read as intentional.
- **Zoom:** subtle slow push-in plus gentle emphasis on key lines.
- **Captions:** `clean_pro`, keywords highlighted, placed below faces in the safe zone.

## Agent guidance
- Read the excerpt: the clip must make sense without the full episode. Include the question if the
  answer is the payoff.
- Never splice sentences from different moments into a new meaning.
- Speaker detection is approximate (largest/most persistent face). If two people alternate quickly,
  consider `templates set podcast-conversation layout.mode=fit_blur` for a full-width framing.

```json
{
  "id": "podcast-conversation",
  "name": "Podcast & Conversation",
  "duration": {"min": 20, "target": 45, "max": 75},
  "selection": {
    "weights": {"audio_spike": 0.5, "audio_energy": 0.7, "motion": 0.2, "scene_change": 0.1, "speech": 1.2,
                "laughter": 1.0, "surprise": 1.0, "excitement": 0.5, "emotion": 1.2, "story": 1.0, "question": 0.9},
    "lead_in": 10.0, "smooth_radius": 3,
    "score_weights": {"mean": 1.0, "peak": 0.6, "hook": 0.6, "ending": 0.5, "speech": 0.6, "dead": 0.8}
  },
  "layout": {"mode": "face_track", "base_zoom": 1.0, "headroom": 0.36, "smoothing": 0.2, "static_threshold": 0.08,
             "center_weight": 0.6},
  "zoom": {"enabled": true, "style": "subtle", "push_in": 0.05, "strength": 0.06, "hold": 1.6, "max_per_clip": 2,
           "min_spacing": 6.0, "opening_zoom": 0.0, "jump_cut_style": "zoom_alternate", "jump_cut_zoom": 0.05,
           "max_zoom": 1.2},
  "captions": {"enabled": true, "preset": "clean_pro", "drop_fillers": true, "overrides": {}},
  "pause_removal": {"enabled": true, "min_pause": 0.7, "pad": 0.18, "max_removed_ratio": 0.25},
  "transitions": {"fade_in": 0.0, "fade_out": 0.2, "audio_fade_in": 0.05, "audio_fade_out": 0.3},
  "hook": {"enabled": false, "duration": 2.5},
  "music": {"mode": "off", "volume_db": -24, "duck": true, "default_mood": "calm", "max_speech_coverage": 0.35},
  "sfx": {"enabled": false, "kinds": [], "max_per_clip": 0, "gain_db": -20, "min_spike_z": 3.5},
  "metadata": {"base_hashtags": ["#podcast"], "credit": true, "creator_hashtag": true}
}
```
