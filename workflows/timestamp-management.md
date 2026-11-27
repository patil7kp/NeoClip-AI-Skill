# Workflow: timestamp management and duplicate prevention

Storage: `~/.neoclip-ai/history/<video_id>.json` (schema `schemas/clip_history.schema.json`).

## Identity
- YouTube: `yt-<11-char id>`. Watch, youtu.be, shorts and live links all map to the same id.
- Local: `local-<16 hex>`, a hash of the size plus the first and last 4 MB. Renaming or moving the file keeps the
  same id. Re-encoding it creates a new id (it is a different file).

## Lifecycle
`reserved` → `rendering` → `completed` | `failed`. Stale `reserved`/`rendering` entries (from a crash) become
`interrupted` at the start of the next run. Only `completed` clips count as used. Writes are atomic with a
`.bak` copy and a lock file. A corrupt file is preserved (`.corrupt-<time>`) and reported, never silently reset.

## Using it
- Show what's been done: `history show "<url-or-file>"`. This gives completed ranges, files, dates and the used percentage.
- More Shorts: `more`, or analyze plus render. Unused footage is searched first and automatically.
- Overlap: up to min(2 s, 10% of the clip) is tolerated. Larger overlaps need `overlap_reason` in the plan.
- Every completed clip stores: URL, id, title, start and end, filename, output path, template, date, status,
  the title used, and the risk level.

## Never
- Never edit history files by hand to "free" footage unless the user asks. If they delete a Short and want
  that moment again, set `overlap_reason` instead, so the record stays truthful.
- Never mark something completed that wasn't rendered and validated. The engine refuses if the file is missing.
