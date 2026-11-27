# Template: Gaming Reaction

For gaming videos, livestreams and streamer reactions.

## What it does
- **Layout:** `gaming_stack` — facecam panel on top (36% of the height), gameplay below (64%).
  Gameplay always keeps the majority of the frame; the facecam is never enlarged over the action.
  If no stable facecam is detected the engine switches to full-height gameplay tracking and says so.
- **Gameplay framing:** follows on-screen action (motion centroid), centre-weighted and heavily
  smoothed so it never jitters; it avoids including the facecam overlay inside the gameplay panel.
- **Moments:** loud reactions (audio spikes), excitement/surprise cues ("let's go", "no way"),
  high motion and scene changes. The window starts ~7 s before the peak so the viewer sees the
  play *and* the reaction.
- **Zoom:** smooth punch-in on the gameplay panel at reaction peaks (max 3 per clip, 4 s apart).
- **Captions:** `bold_pop`, sitting on the seam between facecam and gameplay so they cover neither
  the face nor the centre of the action. Move them with `layout.cam_position` / caption overrides.
- **Pause removal:** light (only gaps > 1.2 s with no speech and no sound events).

## Agent guidance
- Pair the in-game event with the reaction: the clip must show what caused the reaction.
- Prefer clutch plays, fails, jump scares, unexpected bugs, and genuine laughter.
- Don't cut gameplay audio under the reaction: game sound effects are part of the moment.
- Title idea pattern: what happened + who (e.g. "Last-second clutch had him screaming"). No fake stakes.
- Use the game name as a hashtag when known.

## Customize
`python scripts/cli.py templates set gaming-reaction layout.cam_ratio=0.32 zoom.max_per_clip=2`

```json
{
  "id": "gaming-reaction",
  "name": "Gaming Reaction",
  "duration": {"min": 15, "target": 35, "max": 60},
  "selection": {
    "weights": {"audio_spike": 1.6, "audio_energy": 1.0, "motion": 0.9, "scene_change": 0.3, "speech": 0.3,
                "laughter": 1.2, "surprise": 1.4, "excitement": 1.5, "emotion": 0.4, "story": 0.1, "question": 0.1},
    "lead_in": 7.0, "smooth_radius": 2,
    "score_weights": {"mean": 1.0, "peak": 1.0, "hook": 0.7, "ending": 0.2, "speech": 0.1, "dead": 0.9}
  },
  "layout": {"mode": "gaming_stack", "cam_ratio": 0.36, "cam_position": "top", "gameplay_zoom": 1.0,
             "center_weight": 0.7, "smoothing": 0.15, "static_threshold": 0.12, "avoid_cam_in_gameplay": true},
  "zoom": {"enabled": true, "style": "punch", "strength": 0.12, "hold": 1.1, "max_per_clip": 3, "min_spacing": 4.0,
           "opening_zoom": 0.0, "jump_cut_style": "none", "max_zoom": 1.3},
  "captions": {"enabled": true, "preset": "bold_pop", "drop_fillers": true, "overrides": {}},
  "pause_removal": {"enabled": true, "min_pause": 1.2, "pad": 0.25, "max_removed_ratio": 0.15},
  "transitions": {"fade_in": 0.0, "fade_out": 0.15, "audio_fade_in": 0.04, "audio_fade_out": 0.25},
  "hook": {"enabled": true, "duration": 2.2},
  "music": {"mode": "off", "volume_db": -22, "duck": true, "default_mood": "energetic", "max_speech_coverage": 0.35},
  "sfx": {"enabled": true, "kinds": ["hit", "surprise", "laugh"], "max_per_clip": 2, "gain_db": -18, "min_spike_z": 3.0},
  "metadata": {"base_hashtags": ["#gaming", "#gameplay"], "credit": true, "creator_hashtag": true}
}
```
