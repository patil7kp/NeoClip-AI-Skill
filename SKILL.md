---
name: neoclip-ai-skill
description: NeoClip-AI-Skill turns long videos (YouTube URL or local MP4/MOV/MKV/WebM) into edited 9:16 YouTube Shorts with smart cropping, gaming facecam layouts, synced captions, policy/copyright risk checks and a YOUTUBE_METADATA.md per date. Remembers used timestamps across sessions so repeat runs never duplicate clips. Use when the user wants Shorts/clips/highlights cut from a video, more Shorts from a video processed before, or to pick/customize a Shorts editing template.
license: Proprietary. © 2026 Kiran Patil. All Rights Reserved. See LICENSE.
compatibility: Needs Python 3.10+, FFmpeg (with libass) on PATH, and `pip install -r requirements.txt`. Shell access required. YouTube input also needs yt-dlp and network access.
metadata:
  version: "2.0.0"
  author: "Kiran Patil"
  display-name: "NeoClip-AI-Skill"
  copyright: "© 2026 Kiran Patil. All Rights Reserved."
---

# NeoClip-AI-Skill

*Created by Kiran Patil - NeoClip-AI-Skill · v2.0.0 · © 2026 Kiran Patil. All Rights Reserved. Author, contact and
usage terms: `AUTHOR.md`, `LICENSE`. Third-party components keep their own licences: `THIRD_PARTY_NOTICES.md`.*

You (the agent) do the judgement: rights, picking moments, writing titles and descriptions, and
explaining risks. A local Python engine does all video work (FFmpeg + OpenCV + Whisper), so the
same results come out whichever AI agent drives it. Every command prints one JSON document.

```
ENGINE = python <skill_dir>/scripts/cli.py
```

## Non-negotiable rules

1. **Rights first.** Never process a video until the user has told you their basis for using it:
   `own`, `permission`, `licensed`, `creative-commons` or `public-domain`. Giving credit is NOT
   permission, and short clips are NOT automatically allowed. If the user has no rights, stop and
   explain why. Never help bypass private, members-only, age-gated or DRM-protected content.
2. **Be honest about results.** Report only what the JSON says. A clip with `"status": "failed"` is
   failed. If the output is upscaled, it is not native 4K, so say that plainly.
3. **No guarantees.** Policy output lists *potential risks*, not verdicts. Never promise copyright safety,
   no age restriction, monetization, avoiding strikes, or reach. YouTube makes the final decisions.
4. **Keep the meaning.** Don't choose or trim clips in a way that changes what someone said or meant.
   Titles must describe what actually happens in the clip.
5. **Keep the output folder clean.** The engine writes only `NN_name.mp4` files and one `YOUTUBE_METADATA.md`
   to `YouTube_Shorts/YYYY-MM-DD/`. Don't add other files there.
6. **Sound effects only when they fit, never copyrighted.** The engine adds a laugh, surprise or hit only on a
   matching moment, from built-in effects or `~/NeoClip-SFX/cleared/`. Don't fetch sounds from websites, and
   don't add effects the clip doesn't need.

## First run on a machine

```bash
python <skill_dir>/scripts/cli.py doctor          # must report "ready": true
pip install -r <skill_dir>/requirements.txt       # if anything is missing
python <skill_dir>/scripts/cli.py setup-models    # optional: better face tracking (YuNet)
```
If `doctor` shows that something is missing, tell the user exactly what to install (see `README.md`).

## Workflow (follow in order)

**1. Understand the request.** Get the URL or file path, how many Shorts (default **3**), and the template.
If the user doesn't name a template, run `templates list`. The remembered one is marked `current`. Otherwise
suggest one from the content (see the table below) and confirm.

**2. Inspect + rights.** `ENGINE inspect <input>` validates the input. It also shows the title, duration, and
`history` (for a video processed before: what was already used). Ask about rights if you don't know them yet.

**3. Analyze.**
```bash
ENGINE analyze "<input>" --rights <basis> --template <id> --count 3 [--creator "Name" --channel-url URL --source-url URL]
```
This returns ranked `candidates` taken from **unused** footage only. Each has `start`/`end`, `score`, `reasons`,
`category` and a transcript `excerpt`. It also returns `previously_completed`, `content_hint` and `facecam_detected`.

**4. Choose and write the plan.** Read the excerpts. Pick the best N moments. Each one needs a strong
opening, a clear central event, a payoff and an ending, and it must make sense without the full video.
You may tighten or extend `start`/`end` to land on full sentences. Context beats brevity. For each clip, write:
`slug` (2 to 4 descriptive words, which becomes the filename), `title` (accurate, natural, 70 characters or
fewer, no misleading clickbait), `description` (2 to 4 sentences telling the whole story of the clip),
`hashtags` (3 to 6, including #shorts), and optionally `hook_text` (6 words or fewer, true to the clip).
Save the plan as JSON (schema: `schemas/plan.schema.json`, example: `examples/example-workflow.md`).
Write the plan file in a temporary/work location, **not** in the output folder.

**5. Render.** `ENGINE render --plan plan.json`. Per clip, the engine edits, crops, captions, checks policy,
renders, validates, retries simpler settings if needed, moves the file into the date folder, updates
`YOUTUBE_METADATA.md`, and records the timestamps in persistent history. A clip only counts as used after
it passes validation.

**6. Report.** Summarize from the result JSON: the output folder, then each file with its source timestamp,
its title, and its risk level with the key items. Include any `warnings`, the `resolution_note`, failed
clips with their `error`/`hint`, and what remains unused. If `policy_review_due` is true, or the user
plans to monetize, check the official pages listed in `references/youtube-policies.md` before you give
publishing advice.

**Fast path (no review):** `ENGINE run "<input>" --rights <basis> --template <id> --count 3` selects,
renders and writes heuristic metadata in one go. Prefer the analyze → plan → render path when you can,
because your titles and descriptions will be much better.

**More Shorts from the same video:** `ENGINE more "<input>" --rights <basis> --count 2` (or analyze plus
render again). History makes the engine skip used footage automatically. Never pass an already-used
range unless the user wants it. In that case, add `"overlap_reason"` to that clip.

**Interrupted run:** `ENGINE resume`. Completed clips are kept and the rest are retried.

## Choosing a template

| Content | Template id | Layout |
|---|---|---|
| Gameplay or streams with a facecam | `gaming-reaction` | facecam on top, gameplay ≥ 55% below, captions on the seam |
| Podcasts, interviews, panels | `podcast-conversation` | face tracking, two-shot when it fits, pause removal |
| Comedy, pranks, reactions, viral moments | `funny-viral-moments` | fast opening, punch-in zooms, word-pop captions |
| Storytime, commentary, explainers | `storytelling-commentary` | longer windows, beginning, middle and end |
| Brand, education, corporate | `minimal-professional` (default) | no effects, clean captions |

Use a template: `ENGINE templates use <id>` (remembered across sessions; `--template` on a run also
remembers it). Customize a template: `ENGINE templates set <id> key=value ...`, for example
`captions.uppercase=false`, `duration.max=55`, `layout.cam_ratio=0.32`, `zoom.enabled=false`.
Details: `templates/<id>.md`.

## Options you may need

`--resolution 1080x1920` renders much faster (the default target is 2160x3840).
`--output-root DIR` sets where the date folders go (default `./YouTube_Shorts`).
`--subtitles file.srt` skips Whisper.
YouTube input never downloads the whole video: audio comes in 1-hour batches and only the chosen clips are
downloaded. For very long videos suggest `--range START-END`; `--transcribe full` makes Whisper cover every
hour (slow on CPU), and `--full-download` restores the old behaviour.
`--whisper-model base|small|medium|large-v3` and `--language xx` control transcription.
`--caption-preset bold_pop|clean_pro|story|minimal` sets the caption style; it stays fixed per source
video, so all its Shorts match.
`--no-captions` turns captions off.
`--dry-run` selects without rendering.

## Music

The engine never adds music on its own initiative, and never "trending" or unverified audio. A
background bed is only possible from the user's own `music_library.json` entries marked
`verified: true` with an allowed license (see `references/music-guidelines.md`). With no such track, the
original audio is kept. Never call a track copyright-free unless the user has verified its license.

## Errors

Errors come back as `{"status":"error","error":code,"message":...,"hint":...}`. Relay the hint.
Common codes: `rights_not_confirmed`, `invalid_input`, `unsupported_format`, `source_unavailable`
(private, removed, age-gated or region-blocked, so ask for a local file the user has rights to),
`missing_dependency`, `transcription_failed` (the run continues without captions and warns),
`insufficient_disk_space`, `render_failed`/`validation_failed` (per clip; other clips continue).

## Reference map (load only what you need)

- Platforms and installation: `references/agent-compatibility.md`
- How moments are found and ranked: `references/video-analysis.md`, `references/clip-selection.md`
- Editing, gaming layouts, cropping: `references/editing-guidelines.md`, `references/gaming-editing.md`, `references/cropping-guidelines.md`
- Captions: `references/caption-guidelines.md`
- Policy, copyright, music: `references/youtube-policies.md`, `references/copyright-guidelines.md`, `references/music-guidelines.md`
- Rendering, QA, output rules: `references/rendering-guidelines.md`, `references/output-guidelines.md`
- Step-by-step procedures: `workflows/*.md` (start with `workflows/main-workflow.md`)
- Examples: `examples/example-workflow.md`, `examples/example-metadata.md`

## Attribution
Keep the author attribution and copyright notice intact. When you mention or share this skill, credit it as
**Created by Kiran Patil - NeoClip-AI-Skill**. Don't add NeoClip-AI-Skill credit lines to the user's YouTube metadata
unless they ask.
