# Workflow: video editing

The engine does this per clip. The agent's job is to pick the right template and settings.

1. **Edit plan** (`video_editor.plan_edit`): keep-intervals from pause removal → TimelineMap; zoom events from
   spikes and cue words; jump-cut points; hook.
2. **Layout** (`smart_cropper.plan_layout`): face_track, subject_track, gaming_stack or fit_blur, with keyframes in
   output time. Fallbacks are reported in clip `warnings`.
3. **Captions** (`caption_generator`): see `caption-generation.md`.
4. **Audio** (`audio_processor`): normalization and the music decision.
5. **Render and validate** (`video_renderer`, `quality_validator`).

## When to change settings
| Symptom | Setting |
|---|---|
| Too many or too strong zooms | `zoom.max_per_clip=1`, `zoom.strength=0.08`, or `zoom.enabled=false` |
| Pause removal feels choppy | `pause_removal.min_pause=1.2` or `enabled=false` |
| Facecam panel too big or small | `layout.cam_ratio=0.30` (range 0.20 to 0.45) |
| Gameplay crop misses the HUD | `layout.center_weight=0.9` (stay centred) or another moment |
| Speaker cut off in a wide two-person shot | `layout.mode=fit_blur` |
| Clips too short or long | `duration.min`, `duration.target`, `duration.max` (max ≤ 180) |
Apply with `templates set <id> key=value` (remembered) and re-render.
