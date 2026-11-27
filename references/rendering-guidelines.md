# Rendering guidelines

## One pass, high quality
Each Short renders in a single FFmpeg filtergraph: trim and pause removal (concat) → layout crop (dynamic
expressions) → Lanczos scale → optional zoompan → ASS captions → fades → yuv420p. Audio: trims with micro-fades
→ fades → loudnorm (-14 LUFS, -1 dBTP) → 48 kHz stereo (optional ducked music).

| Setting | Default | Notes |
|---|---|---|
| resolution | 2160×3840 | `--resolution 1080x1920` is about 4× faster |
| codec | libx264 High, CRF 17, preset slow | `video_codec: libx265` for smaller files (tagged hvc1) |
| fps | source fps, capped at 60 | 23.976/25/29.97/30/50/60 kept as-is |
| audio | AAC 320 kb/s 48 kHz | |
| colour | BT.709 tagged | |
| container | MP4 with `+faststart` | |

## Safe output handling
- Renders go to `<state>/work/<video>/jobs/<job>/<clip>.partial.mp4`. Only after **validation passes** is the file
  moved into the date folder, as a hidden `.part` file and then an atomic rename. A crash never leaves a broken
  or half-written Short in the output, and existing files are never overwritten.
- Disk space is checked before each render (about 45 Mb/s at 4K × duration × 2.2 headroom).

## Automated validation (`quality_validator.py`)
Required: file exists · full decode with no errors · duration within tolerance · 1 to 180 s · exact resolution ·
9:16 aspect · H.264/HEVC yuv420p · audio present when the source has audio · audio and video start and duration
aligned (≤ 50 ms / 150 ms) · no black segments ≥ 0.4 s (excluding fades) · no letterbox or empty bands
(cropdetect) · captions present when speech exists, inside the safe zone and within the duration.
Warning only: frozen video ≥ 4 s (static podcasts can trigger this legitimately).

## Retry ladder
1. `full`: the template as configured.
2. `no_zoom`: same, without zoom effects.
3. `safe`: no zoom, static framing, `medium` preset.
If all attempts fail, the clip is reported **failed** with the reasons. It is not saved and not marked as used.
Other clips continue.

## Performance tips
- A GPU isn't needed for rendering. Whisper benefits from CUDA (`whisper_device: cuda`).
- For long batches, use `--resolution 1080x1920` and `preset: medium` in `config.json`.
