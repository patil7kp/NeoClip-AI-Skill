# Workflow: video analysis

1. `inspect <input>`. Confirm it is valid. For YouTube, this reads metadata only (no download yet).
2. Confirm rights. Then run `analyze <input> --rights … --template … --count N`.
   - YouTube (fast mode, default): nothing is downloaded in full. Audio is fetched in 1-hour batches (parallel,
     resumable), analysed and transcribed with Whisper, then deleted. Only the chosen clips are downloaded at
     up to 2160p when they are rendered. Batch results live in `~/.neoclip-ai-skill/work/yt-<id>/audio_chunks/`
     and are reused on later runs. `--range START-END` limits the search, `--transcribe full|candidates`
     controls Whisper (auto: everything up to 3 hours, strongest moments beyond), `--full-download` restores the
     old whole-video download. `clean <input>` deletes the cache but keeps the history.
   - Local: the file is read in place. Nothing is copied.
3. First analysis of a video: visual pass (local files and `--full-download`; in fast mode faces and facecam are
   checked inside each clip), then audio pass, then transcription. It's cached, so repeats are instant.
4. Read the result:
   - `analysis_mode: fast`: `facecam_detected` is `null` because it is checked per clip. `replay_heatmap` says
     whether YouTube's "most replayed" graph was used.
   - `content_hint` / `facecam_detected`: suggest switching templates if they don't match the user's choice
     (for example gaming content with a detected cam under the podcast template).
   - `has_transcript: false`: tell the user captions will be missing, and suggest `--subtitles` or installing faster-whisper.
   - `previously_completed`: what earlier sessions used.
   - `warnings`: relay them.
5. Errors: `source_unavailable` (private, removed, age-gated or region-blocked) means ask for a local file they have rights
   to. Don't try workarounds. `unsupported_format` means suggest remuxing with FFmpeg.
