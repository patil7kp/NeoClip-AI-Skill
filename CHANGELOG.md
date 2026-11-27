# Changelog

NeoClip-AI-Skill, created by Kiran Patil. © 2026 Kiran Patil. All Rights Reserved.

## 2.0.0 (2026-11-27)
- **Fast YouTube mode (default):** no full-video download. Audio is fetched in 1-hour batches (parallel,
  bounded disk use, resumable per batch), analysed and transcribed with Whisper, then deleted. Only the chosen
  clips are downloaded at full quality, in parallel while earlier clips render, and deleted once saved.
- Whisper transcribes the real audio; YouTube captions are only used with `--youtube-captions`.
  Long videos (over 3 hours by default) transcribe the strongest moments; `--transcribe full` covers everything.
- YouTube "most replayed" graph used as an extra selection signal.
- New options: `--range`, `--transcribe`, `--full-download`, `--youtube-captions`, `--workers`;
  config `whisper_beam_size`, `hw_encoder`, `exact_section_cuts`, `audio_chunk_minutes`.
- Hardware encoding (VideoToolbox / NVENC) when available, with automatic fallback to x264.
- Fixed `templates set <id> captions.uppercase=false`.
- **Reaction cam detection rebuilt:** finds a moving streamer's webcam, bordered or borderless cams, and any
  picture-in-picture reaction overlay without a face. The whole cam is shown in the top panel, never cropped.
- **4K export by default** (2160×3840); `--1080p` for a faster 1080×1920 export.
- **Sound effects:** strict content matching (laugh, surprise, hit), only when the moment needs one. Built-in
  synthesised effects by default; your own generic, cleared files from `~/NeoClip-SFX/cleared/`. Copyrighted
  sources are blocked, nothing is downloaded automatically, and every sound used is listed in Publishing Notes.
- **Claude Code plugin:** install with `/plugin marketplace add patil7kp/NeoClip-AI-Skill` and
  `/plugin install neoclip-ai-skill@neoclip-ai`. Other agents install as before.
- **Simpler YOUTUBE_METADATA.md:** filename, Title, Description (plain text, keywords, creator credit,
  hashtags last) and Publishing Notes, ready to copy into YouTube.

## 1.0.0 (2026-11-27)
First release.
- Branded as **NeoClip-AI-Skill** by Kiran Patil. Added `AUTHOR.md`, an all-rights-reserved `LICENSE` and
  `THIRD_PARTY_NOTICES.md`.
- `SKILL.md` (Agent Skills format) with cross-agent entry points: `AGENTS.md`, `GEMINI.md`, a Cursor rule,
  and ChatGPT/Gemini planning-mode instructions.
- Python engine with a JSON CLI: `doctor`, `setup-models`, `templates`, `inspect`, `analyze`, `render`, `run`,
  `more`, `resume`, `history`, `clean`.
- Input: YouTube URLs (yt-dlp, rights-gated, access errors classified) and local MP4/MOV/MKV/WebM/M4V/AVI.
- Whole-video analysis: motion, scene cuts, faces, facecam detection, loudness spikes, silences,
  possible-music heuristic, Whisper word timestamps (long videos: candidate-range transcription).
- Clip selection with template weights, sentence-snapped windows, hook and ending scoring, and NMS.
- Persistent timestamp history with a reserved → completed/failed lifecycle, crash recovery, overlap tolerance and
  duplicate prevention across sessions.
- Five templates (gaming reaction, podcast, funny/viral, storytelling, minimal), remembered and customizable.
- Editing: pause removal with an exact timeline map, punch, subtle and opening zooms, alternating jump-cut zoom,
  hook text, fades.
- Smart 9:16 framing: face tracking with two-shots, action tracking, gaming facecam + gameplay stack, blurred fit.
- Standardized ASS captions (4 presets, word highlight, safe zone, face avoidance, per-project consistency).
- Policy and copyright risk screening with official sources, timestamps and remedies; licensed-only music
  with ducking.
- Single-pass FFmpeg render up to 2160×3840, automated validation, a three-step retry ladder, atomic output moves.
- Date-wise output with `NN_slug.mp4` and one `YOUTUBE_METADATA.md` per date.
- 66 pytest tests (unit + integration on synthetic media).
