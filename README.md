# NeoClip-AI-Skill

**Created by Kiran Patil - NeoClip-AI-Skill** · v1.0.0 · © 2026 Kiran Patil. All Rights Reserved.

A cross-agent AI skill that turns long videos (YouTube URLs or local files) into edited, captioned,
9:16 YouTube Shorts. It also writes publishing metadata and remembers which parts of each video it has
already used, so it never makes the same Short twice.

- **Works with** Claude (Code / Skills), OpenAI Codex CLI, Cursor, Gemini CLI, Copilot agent mode, and any
  agent that can read Markdown and run a command. ChatGPT and Gemini web apps can plan, and the engine runs
  locally. See [`references/agent-compatibility.md`](references/agent-compatibility.md).
- **No paid AI API needed.** Video work is done by FFmpeg, OpenCV and local Whisper. The agent supplies judgement.
- **Output stays simple:**
  ```
  YouTube_Shorts/2026-11-27/01_best_reaction.mp4
                           02_funny_moment.mp4
                           03_epic_gameplay.mp4
                           YOUTUBE_METADATA.md
  ```

## Features
| | |
|---|---|
| Inputs | YouTube URL (rights-gated, via yt-dlp) or local MP4 / MOV / MKV / WebM / M4V / AVI |
| Analysis | whole-video motion, scene cuts, faces, facecam detection, loudness spikes, silences, possible music, Whisper word timestamps |
| Selection | template-weighted interest curve, sentence-snapped windows, hook and ending scoring, unused footage first |
| Memory | persistent per-video timestamp history, crash-safe, duplicate prevention across sessions |
| Templates | Gaming Reaction · Podcast & Conversation · Funny & Viral · Storytelling & Commentary · Minimal Professional |
| Editing | pause removal (meaning-safe), restrained punch and push zooms, jump-cut treatment, hook text, fades |
| Framing | face tracking with two-shots, action tracking, facecam + gameplay stack, blurred fit, no blind centre crops |
| Captions | one standardized system, 4 presets, word highlight, safe zone, face and gameplay avoidance |
| Policy | copyright, Content ID, reused/inauthentic content, age and ad-suitability lexicon, metadata checks, with official sources |
| Music | licensed-only from your verified library, ducked under speech; otherwise the original audio is kept |
| Render | single-pass FFmpeg up to 2160×3840, honest upscaling notes, automated QA, retry ladder |
| Metadata | titles, full-story descriptions, creator credit with clickable links, hashtags, one Markdown file per date |

## Install
```bash
# 1. FFmpeg (with libass): macOS `brew install ffmpeg` · Windows `winget install Gyan.FFmpeg` · Ubuntu `sudo apt install ffmpeg`
# 2. Python 3.10+
python -m pip install -r requirements.txt
python scripts/cli.py doctor          # → "ready": true
python scripts/cli.py setup-models    # optional: YuNet face model (needed for face tracking on OpenCV 5)
```
Then install it for your agent ([details](references/agent-compatibility.md)):
- **Claude Code:** `cp -r neoclip-ai-skill ~/.claude/skills/`
- **Codex / Cursor / Copilot / others:** open the folder as the workspace (`AGENTS.md`, `.cursor/rules/`).
- **Gemini CLI:** run `gemini` inside the folder (`GEMINI.md`).

## Use it (through your agent)
> "Make 3 Shorts from https://youtu.be/XXXXXXXXXXX with the gaming template. It's my own stream."
>
> "Give me 2 more Shorts from that same video."
>
> "Switch to the podcast template and turn off uppercase captions."

## Use it (directly)
```bash
python scripts/cli.py run ~/Videos/stream.mp4 --rights own --template gaming-reaction --count 3
python scripts/cli.py more ~/Videos/stream.mp4 --rights own --count 2        # new moments only
python scripts/cli.py analyze "https://youtu.be/XXXXXXXXXXX" --rights own > candidates.json
python scripts/cli.py render --plan plan.json                                 # agent- or hand-written plan
python scripts/cli.py resume                                                  # finish an interrupted run
python scripts/cli.py history show ~/Videos/stream.mp4
python scripts/cli.py templates list | use <id> | set <id> key=value | reset <id>
```
Speed: `--resolution 1080x1920` renders about 4× faster than the 4K default.

## Configuration
Optional `~/.neoclip-ai-skill/config.json` (all keys: `scripts/config.py`):
```json
{"output_root": "~/Videos/YouTube_Shorts", "resolution": "2160x3840", "whisper_model": "small",
 "caption_corrections": {"valorent": "Valorant"}, "music_library": "~/Music/licensed/music_library.json",
 "ai": {"command": null}}
```
Environment: `YT_SHORTS_STATE_DIR`, `YT_SHORTS_OUTPUT_ROOT`, `YT_SHORTS_RESOLUTION`, `YT_SHORTS_WHISPER_MODEL`,
`YT_SHORTS_AI_COMMAND`, `YT_SHORTS_MUSIC_LIBRARY`.

## Project layout
```
SKILL.md                 agent instructions (Agent Skills format)
AGENTS.md / GEMINI.md / .cursor/rules/   entry points for other agents
AUTHOR.md, LICENSE, THIRD_PARTY_NOTICES.md   author, copyright, third-party licences
platforms/               ChatGPT, Gemini, Claude, Cursor specifics
references/              detailed guidance, loaded on demand
templates/               5 templates (guidance + JSON config block)
workflows/               step-by-step procedures
scripts/                 the engine (cli.py is the entry point)
schemas/                 JSON Schemas: history, source metadata, results, plan
tests/                   pytest suite (synthetic media, no network)
examples/                example session and metadata file
```
Architecture: `cli.py` → `pipeline.py` → {`source_input`, `video_analyzer`, `audio_analyzer`, `transcription`} →
`clip_selector` (+ `timestamp_manager`) → per clip {`video_editor` + `video_cutter`, `smart_cropper`,
`caption_generator`, `audio_processor`, `policy_checker`} → `video_renderer` → `quality_validator` →
`metadata_generator`. AI reasoning stays in the agent (or the optional `ai_bridge.py`).

## Tests
```bash
python -m pytest -q      # 66 tests, about 1 minute, needs FFmpeg
```

## Honest limitations
- **Moment detection** uses signals (loudness, motion, cue words, faces). It's good at finding energy and
  reactions, but it doesn't understand jokes or stories. That's why the agent reviews the excerpts.
- **Speaker detection** is approximate (dominant or persistent face plus two-shot). It doesn't use lip activity.
- **Face detection**: Haar (OpenCV 4) misses profiles and small faces. YuNet (`setup-models`) is better.
- **Music detection** is a heuristic for "possible music". It does not identify songs. Content ID is the real test.
- **Policy screening** can't see visual nudity or gore and can't judge fair use. It flags potential risks and
  is not legal advice.
- **4K**: most sources are upscaled when converted to 9:16 4K. Every result says so.
- **YouTube downloads** depend on yt-dlp and YouTube's current behaviour. Private, age-gated, members-only or
  region-blocked videos are not supported and are not bypassed.

## Responsible use
Process only videos you own or have permission to use. Credit doesn't replace permission. Follow YouTube's
Terms of Service and Community Guidelines. The skill offers no guarantees about claims, strikes,
monetization or reach. YouTube makes those decisions.

## Author & Copyright Information

**Project Name:** NeoClip-AI-Skill
**Created & Developed By:** Kiran Patil
**Role:** Software Engineer
**Project Type:** AI Agent Skill – YouTube Shorts Automation
**Version:** 1.0.0
**Copyright:** © 2026 Kiran Patil. All Rights Reserved.

### Contact Information

**Email:** [kiran.enquiry.ai@gmail.com](mailto:kiran.enquiry.ai@gmail.com)

### Ownership & Attribution

NeoClip-AI-Skill is an independently developed AI Agent Skill designed for intelligent video clipping, automated
YouTube Shorts creation, video editing, and publishing metadata generation.

The original architecture, workflows, documentation, and custom templates developed for NeoClip-AI-Skill are
attributed to Kiran Patil.

### Copyright Notice

Copyright © 2026 Kiran Patil. All Rights Reserved.

Unauthorized redistribution, republishing, or commercial redistribution of this original project and its
documentation without permission from the copyright owner is prohibited.

Third-party libraries, AI models, tools, and dependencies remain subject to their respective licences
(see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).

### Creator Attribution

When sharing, distributing, or referencing this skill, provide the following attribution:

**Created by Kiran Patil - NeoClip-AI-Skill**

### Important

- Preserve the original author attribution in the skill documentation.
- Do not remove or replace the original copyright notice when redistributing authorized copies.
- Clearly identify third-party components and their respective licences.
- Do not claim ownership of third-party AI models, libraries, or software.
- Any separate open-source licence must be followed according to its terms.

License: all rights reserved, see [`LICENSE`](LICENSE). Third-party components: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
