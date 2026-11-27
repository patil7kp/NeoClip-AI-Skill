# Video analysis

`scripts/video_analyzer.py`, `scripts/audio_analyzer.py` and `scripts/transcription.py` analyse the **whole**
video once and cache the results in `<state>/work/<video_id>/`. Later runs on the same video reuse the cache.

## Visual (FFmpeg decode → OpenCV), 2 samples/s by default
- **Motion energy and motion centroid:** where the action is. Drives gameplay framing and subject tracking.
- **Scene cuts:** histogram correlation plus motion. Crops stay static within a shot and re-target on cuts.
- **Brightness:** finds blank or black sections.
- **Faces:** 1 per second. Uses YuNet if the model is installed (`cli.py setup-models`), otherwise Haar cascades
  (OpenCV < 5). With no detector, framing follows motion and the run says so.
- **Facecam detection:** a small face that stays still, sits off-centre, and appears in at least 30% of samples
  is treated as a webcam overlay. Its box is snapped to persistent overlay borders.
- **content_hint:** `gaming`, `podcast`, `talking` or `general`. This is a suggestion for template choice.

## Audio (16 kHz mono, streamed, 0.5 s windows)
- **Loudness timeline (dB)** and **energy z-score** against a rolling 60 s median. This means "louder than the
  surrounding minute", which is how reactions show up in streams and podcasts.
- **Spikes:** sharp local peaks (shouts, laughs, impacts). Keeps the strongest one per 4 s.
- **Silences:** windows below an adaptive threshold (noise floor + 8 dB, capped at -38 dBFS). Constant game
  audio or music is not treated as silence.
- **possible_music:** sustained tonal audio (low spectral flatness). This is a *heuristic* that prompts a
  copyright check. It is not song identification.

## Speech
- faster-whisper (or openai-whisper) with word timestamps and VAD. No API key or paid service is needed.
- Videos longer than 45 minutes are transcribed only around the top audio/visual candidates (`transcribe_scope:
  auto`). Use `full` in `config.json` for complete transcripts.
- `--subtitles file.srt|vtt` uses existing captions instead (word timings are interpolated).
- If transcription is impossible, the run continues without captions or speech cues and reports a warning.

## Long videos
A 3-hour stream analyses in a few minutes on a laptop. Memory stays flat because frames and audio are
streamed. The first Whisper model download needs internet access.
