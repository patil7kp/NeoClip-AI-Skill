# Cropping guidelines

The output is always 9:16. The default target is 2160×3840 (4K vertical). Nothing is ever blindly centre-cropped
when there is something better to follow.

| Mode | When | How |
|---|---|---|
| `face_track` | people on screen | follows the dominant face; sticks with the same person until a shot change; frames a **two-shot** when both faces fit in the crop; puts faces in the upper third (`headroom`); static per shot when the face moves less than 8% of the width, otherwise eased pans |
| `subject_track` | no faces, or gaming without a cam | follows the motion centroid, centre-weighted, heavily smoothed |
| `gaming_stack` | streams with a webcam | see `gaming-editing.md` |
| `fit_blur` | slides, screen recordings, wide shots that can't be cropped | full frame fitted to the width over a blurred, darkened fill (no black bars) |

## Rules
- The crop window is computed in source pixels and clamped to the frame, so there is never padding or black bars.
- Paths are simplified (Ramer–Douglas–Peucker) and compiled into one FFmpeg expression, so dynamic crops
  render in a single pass.
- Vertical sources are scaled to fill. Square sources are cropped to 9:16 around the subject.
- If faces are detected in less than 20% of a clip's samples, framing switches to action tracking and says so.
- After rendering, `quality_validator` runs `cropdetect` over the whole clip to catch letterboxing or empty bands.

## Resolution honesty
- `upscale_factor` = output height ÷ source crop height. A 1080p 16:9 source cropped to 9:16 gives 608×1080
  pixels of real detail, so a 2160×3840 output is about 3.6× **upscaled** (Lanczos).
- The result JSON gives a `resolution_note` for every clip, and the metadata adds a publishing note when
  footage is upscaled. **Never describe upscaled output as native 4K.** True native 4K vertical needs a
  vertical 4K source or an 8K landscape source.
- Use `--resolution 1080x1920` when the source is ≤ 1080p and speed matters. YouTube still streams it well.
