# Changelog

NeoClip-AI-Skill, created by Kiran Patil. © 2026 Kiran Patil. All Rights Reserved.

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
