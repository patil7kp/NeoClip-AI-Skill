# Editing guidelines

All templates share one engine (`video_editor.py`, `video_cutter.py`, `smart_cropper.py`,
`caption_generator.py`, `audio_processor.py`, `video_renderer.py`). Templates only change settings.

## Principles
1. **Restraint.** An effect must earn its place. Zooms only fire on real emphasis (an audio spike or a
   cue word), at most `zoom.max_per_clip`, at least `zoom.min_spacing` seconds apart, and never above `zoom.max_zoom`.
2. **The first seconds matter most.** Selection rewards strong openings. Optional extras: a small opening
   zoom that eases out (`zoom.opening_zoom`) and a `hook_text` overlay for about 2 s. Both are off in Minimal.
3. **Pauses go, meaning stays.** Pause removal cuts only gaps that have no words *and* are actually
   silent. It keeps padding around speech, never removes a gap with a sound event (laugh, crash, sound
   effect), and never removes more than `max_removed_ratio` of the clip.
4. **Jump cuts look intentional.** With `jump_cut_style: zoom_alternate`, the framing alternates by about 5% at
   each removed pause, which is the standard way to hide a jump cut.
5. **Smooth starts and ends.** Short audio fades (40 to 300 ms) and an optional short video fade-out. There is no
   fade-in from black, because the first frame is the thumbnail moment.
6. **Sync is exact.** Every timestamp (captions, zooms, crop keyframes) is mapped through the same
   `TimelineMap` as the cuts, so sync holds after trimming.
7. **Audio.** Loudness is normalized to -14 LUFS integrated, -1 dBTP. Original dialogue and sound effects are
   always kept. Music is optional, verified-only, and ducked under speech.

## Effects reference
| Effect | Where | Setting |
|---|---|---|
| Punch-in zoom (ease in 0.18 s, hold, ease out 0.45 s) | reaction or cue moments | `zoom.style=punch`, `strength`, `hold` |
| Slow push-in | podcasts, story | `zoom.style=subtle`, `push_in` |
| Opening ease-out zoom | funny | `zoom.opening_zoom` |
| Alternating jump-cut zoom | podcast, story, funny | `zoom.jump_cut_style` |
| Hook text (first ~2 s) | gaming, funny | `hook.enabled` + clip `hook_text` |
| Fade-out | all | `transitions.fade_out` |

## Things the engine deliberately does not do
- It doesn't add stock sound effects, emojis or stickers. These are easy to overdo and add licensing questions.
- It doesn't speed up speech. Speed changes harm natural audio and lip sync.
- It doesn't use auto-generated voice-overs. If you want commentary for transformation, record your own.
