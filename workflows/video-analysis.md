# Workflow: video analysis

1. `inspect <input>`. Confirm it is valid. For YouTube, this reads metadata only (no download yet).
2. Confirm rights. Then run `analyze <input> --rights … --template … --count N`.
   - YouTube: downloads up to 2160p into `~/.neoclip-ai/work/yt-<id>/download/` (never the output folder).
     Downloads are reused on later runs. `clean <input>` deletes the cache but keeps the history.
   - Local: the file is read in place. Nothing is copied.
3. First analysis of a video: visual pass, then audio pass, then transcription. It's cached, so repeats are instant.
4. Read the result:
   - `content_hint` / `facecam_detected`: suggest switching templates if they don't match the user's choice
     (for example gaming content with a detected cam under the podcast template).
   - `has_transcript: false`: tell the user captions will be missing, and suggest `--subtitles` or installing faster-whisper.
   - `previously_completed`: what earlier sessions used.
   - `warnings`: relay them.
5. Errors: `source_unavailable` (private, removed, age-gated or region-blocked) means ask for a local file they have rights
   to. Don't try workarounds. `unsupported_format` means suggest remuxing with FFmpeg.
