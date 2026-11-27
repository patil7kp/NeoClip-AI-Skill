# Main workflow (the 30 steps, and who does each one)

`A` = the agent (reasoning and talking to the user) · `E` = the engine (`scripts/cli.py`)

| # | Step | Who | How |
|---|---|---|---|
| 1 | Receive a YouTube URL or local video | A | ask for count/template if they're missing |
| 2 | Validate input and usage permissions | A+E | `inspect`; ask for the rights basis; `--rights` is required |
| 3 | Retrieve metadata | E | yt-dlp JSON / ffprobe |
| 4 | Analyse duration, frames, audio | E | `analyze` (cached) |
| 5 | Identify the source by a unique id | E | `yt-<id>` or `local-<content hash>` |
| 6 | Retrieve timestamp history | E | `history/<video_id>.json`; interrupted clips recovered |
| 7 | Find unused interesting portions | E | used footage is masked before peak search |
| 8 | Analyse and rank moments | E → A | candidates with reasons and excerpts; the agent reviews them (`clip-selection.md`) |
| 9 | Select the best 3 (default) | A | write `plan.json` |
| 10 | Apply the template | E | `templates/<id>.md` JSON block + user overrides |
| 11 | Trim | E | sentence-snapped; plan times honoured |
| 12 | Remove pauses | E | silent, word-free gaps only |
| 13 | Crop and resize intelligently | E | face, subject or gaming layouts |
| 14 | Gaming layouts | E | facecam + gameplay stack |
| 15 | Captions | E | Whisper words → ASS, synced through the timeline map |
| 16 | Animations and effects | E | restrained zooms, hook, fades |
| 17 | Audio and music | E | loudnorm; verified-only music |
| 18 | Copyright risk | E → A | `risk.items`; the agent explains them |
| 19 | Age and policy risk | E → A | lexicon flags with timestamps |
| 20 | Render | E | single pass, temp file |
| 21 | Quality checks | E | `quality_validator` |
| 22 | Correct and retry | E | full → no_zoom → safe |
| 23 | Title | A | in the plan (heuristic if `run`) |
| 24 | Description and credit | A+E | the agent's story + the engine's credit and links |
| 25 | Hashtags | A | 3 to 6, relevant |
| 26 | Date folder | E | `YouTube_Shorts/YYYY-MM-DD/` |
| 27 | Save the Shorts | E | `NN_slug.mp4`, never overwritten |
| 28 | Write or update `YOUTUBE_METADATA.md` | E | append or replace the block |
| 29 | Update history | E | `completed` only after validation and the move |
| 30 | Final summary | A | from the result JSON: files, timestamps, warnings, risks |

## Command sequence
```bash
python scripts/cli.py doctor
python scripts/cli.py inspect "<input>"
python scripts/cli.py analyze "<input>" --rights own --template gaming-reaction --count 3 > candidates.json
#   … agent writes plan.json …
python scripts/cli.py render --plan plan.json > result.json
```
Unattended: `python scripts/cli.py run "<input>" --rights own --count 3`.
More from the same video later: `python scripts/cli.py more "<input>" --rights own --count 2`.
After a crash: `python scripts/cli.py resume`.

## Status discipline
- Report a clip as done only if its `status` is `completed`.
- `partial` means some clips failed. List them with `error` and `hint`, and offer to retry (`resume`).
- Never tell the user a failed or skipped clip exists.
