<p align="center"><img src="assets/banner-animated.webp" alt="NeoClip-AI-Skill banner" width="500"></p>

# NeoClip-AI-Skill

**Created by Kiran Patil - NeoClip-AI-Skill** · v2.0.0 · © 2026 Kiran Patil. All Rights Reserved.

A cross-agent AI skill that turns long videos (YouTube URLs or local files) into edited, captioned,
9:16 YouTube Shorts. It also writes publishing metadata and remembers which parts of each video it has
already used, so it never makes the same Short twice.

- **Works with** Claude (Code / Skills), OpenAI Codex CLI, Cursor, Gemini CLI, Copilot agent mode, and any
  agent that can read Markdown and run a command. ChatGPT and Gemini web apps can plan, and the engine runs
  locally. See [`references/agent-compatibility.md`](references/agent-compatibility.md).
- **No paid AI API needed.** Video work is done by FFmpeg, OpenCV and local Whisper. The agent supplies judgement.
- **Output stays simple:** each processing date gets its own folder containing only the finished Shorts (`.mp4`)
  and one `YOUTUBE_METADATA.md` with titles, descriptions and hashtags.

## Features

**Inputs**
- YouTube links (watch, youtu.be, Shorts, live) or local MP4, MOV, MKV, WebM, M4V and AVI files.
- Rights check first: you say why you may use the video (own, permission, licensed, Creative Commons, public domain).

**Long videos, fast (even 25-hour streams)**
- YouTube videos are never downloaded in full. Audio is fetched in 1-hour batches, in parallel, then deleted.
- Whisper transcribes the real audio. YouTube captions are not trusted by default.
- Resumes where it stopped: finished batches are kept, so an interrupted run doesn't start over.
- Only the chosen clips are downloaded at full quality, while earlier clips render.
- `--range` to analyse only part of a video, `--workers` to set parallel downloads.

**Finding the best moments**
- Uses loudness spikes, laughter and reactions, motion, scene cuts, faces, cue words and YouTube's "most replayed" graph.
- Clips start and end on full sentences, with a strong hook and a clean ending.
- Each template weights these signals differently. The agent reviews the transcript excerpts before rendering.

**Never the same Short twice**
- Remembers every timestamp it has used, per video, across sessions.
- `more` makes new Shorts only from footage not used yet. Crash-safe history.

**5 editing templates**
- Gaming Reaction, Podcast & Conversation, Funny & Viral, Storytelling & Commentary, Minimal Professional.
- Your choice and your tweaks are remembered (`templates use`, `templates set`, `templates reset`).

**Gaming reaction cam**
- Finds the reaction cam automatically: a webcam, a cam with or without a border, or any picture-in-picture
  overlay, even with no face in it.
- The whole cam is shown on top, never cut off. The gameplay fills the rest.

**Smart 9:16 framing**
- Follows the speaker's face, keeps two people in frame together, follows the action.
- Blurred-background fit when nothing can be cropped well. No blind centre crops.

**Editing**
- Removes dead pauses without changing what was said.
- Gentle punch-in and push zooms, jump-cut treatment, hook text at the start, fades.

**Captions**
- Word-by-word captions synced to the speech, with the current word highlighted.
- 4 styles: bold pop, clean pro, story, minimal. Kept in the safe zone, away from faces and the gameplay.
- Word fixes for names and games (for example "valorent" to "Valorant").

**Sound effects (only when needed)**
- A laugh, a surprise boom or a soft hit, only on a matching moment. Nothing otherwise.
- Built-in effects or your own cleared files. Never copyrighted sounds.

**Music**
- Only tracks from your own verified, licensed library, ducked under speech. Otherwise the original audio stays.

**4K export**
- 2160×3840 by default, `--1080p` for faster renders.
- Hardware encoding on Mac (VideoToolbox) and NVIDIA (NVENC), with automatic fallback.
- Says honestly when a video was upscaled.

**Quality checks**
- Every Short is checked after rendering (size, length, audio, black bars, frozen frames).
- A failed render is retried with a safer setting.

**Policy and copyright checks**
- Flags possible copyright, Content ID, music, reused-content, age and advertiser-friendly risks, with links
  to YouTube's rules. These are warnings, not guarantees.

**YouTube metadata, ready to paste**
- One `YOUTUBE_METADATA.md` per date. For each Short you get the filename, a Title, and a plain-text
  Description with the story, related keywords, creator credit with links and hashtags last.
- Publishing Notes for you: the original timestamp, the risk check and the sound effects used.

**Clean output**
- `YouTube_Shorts/YYYY-MM-DD/` holds only the `NN_name.mp4` Shorts and the metadata file.
- Numbering continues across runs on the same day. Internal files stay out of sight.

**Works with your AI agent**
- Claude (Code and Skills), Codex CLI, Cursor, Gemini CLI, Copilot agent mode and any agent that runs commands.
- ChatGPT and Gemini web apps can plan, and the engine runs on your computer.
- Free and local. No paid AI API needed.

**Handy commands**
- `doctor` (checks your setup), `run`, `more`, `analyze`, `render`, `resume`, `history`, `clean`, `templates`.

## Installation

### Claude Code plugin (easiest for Claude Code)

In Claude Code, run these two commands:

```text
/plugin marketplace add patil7kp/NeoClip-AI-Skill
/plugin install neoclip-ai-skill@neoclip-ai
```

On Claude Code 2.1.275 or later, this one line does both:

```text
/plugin install neoclip-ai-skill --marketplace patil7kp/NeoClip-AI-Skill
```

Then install the tools it uses once (FFmpeg and the Python requirements), as in [Manual install](#manual-install),
or just ask Claude: "Set up NeoClip-AI-Skill and run its doctor check." Update later with `/plugin update`.

### Quick install (any agent)

Open an AI agent that can use your terminal (Claude Code, Codex CLI, Gemini CLI, Cursor or GitHub Copilot)
and send it this prompt:

```text
Install the NeoClip-AI-Skill from https://github.com/patil7kp/NeoClip-AI-Skill. Clone it, install FFmpeg and the Python requirements, run "python scripts/cli.py doctor", and set it up as a skill for this agent by following the Installation section of its README.
```

**Using the Claude app or claude.ai?** Download the
[skill zip](https://github.com/patil7kp/NeoClip-AI-Skill/archive/refs/heads/main.zip), open
**Settings → Capabilities**, turn on code execution, and upload the zip under **Skills**.

### Manual install

**1. Install Python 3.10+ and FFmpeg**

macOS:
```bash
brew install python ffmpeg
```
Windows:
```powershell
winget install Python.Python.3.12 Gyan.FFmpeg
```
Ubuntu / Debian:
```bash
sudo apt install python3 python3-pip ffmpeg
```

**2. Download the skill and install its packages**
```bash
git clone https://github.com/patil7kp/NeoClip-AI-Skill.git
cd NeoClip-AI-Skill
python -m pip install -r requirements.txt
```

**3. Check it's ready** (should print `"ready": true`)
```bash
python scripts/cli.py doctor
```

**4. Optional: download the face-tracking model**
```bash
python scripts/cli.py setup-models
```

### Connect it to your agent

| Agent | How to connect | Mode |
|---|---|---|
| Claude Code | Copy the folder into your skills folder (command below), then run `claude` | Full |
| Claude app / claude.ai | Upload the zip in **Settings → Capabilities → Skills** | Planning or full |
| Codex CLI | Run `codex` inside the `NeoClip-AI-Skill` folder (reads `AGENTS.md`) | Full |
| Gemini CLI | Run `gemini` inside the `NeoClip-AI-Skill` folder (reads `GEMINI.md`) | Full |
| Cursor | **File → Open Folder** → `NeoClip-AI-Skill`, then use **Agent** | Full |
| GitHub Copilot (VS Code) | Open the folder, switch Copilot Chat to **Agent** mode | Full |
| ChatGPT / Gemini web | Paste [`platforms/chatgpt-instructions.md`](platforms/chatgpt-instructions.md) into a Project or Gem | Planning |
| Any other agent | Open the folder and say "Read SKILL.md and follow it" | Full |

**Full** means the agent runs everything for you. **Planning** means it picks the moments and writes the
titles in chat, and you run the `analyze` and `render` commands yourself.

Claude Code skills folder, macOS / Linux:
```bash
mkdir -p ~/.claude/skills && cp -r NeoClip-AI-Skill ~/.claude/skills/neoclip-ai-skill
```
Windows (PowerShell):
```powershell
Copy-Item -Recurse NeoClip-AI-Skill $HOME\.claude\skills\neoclip-ai-skill
```

Need to install the agent itself first?
```bash
npm install -g @openai/codex          # Codex CLI
npm install -g @google/gemini-cli     # Gemini CLI
```
For Claude Code, see the [official setup guide](https://docs.anthropic.com/en/docs/claude-code/setup).
More detail per agent: [`platforms/`](platforms/) and [`references/agent-compatibility.md`](references/agent-compatibility.md).

## Use it (through your agent)
Ask in plain words, for example:
```text
Make 3 Shorts from https://youtu.be/XXXXXXXXXXX with the gaming template. It's my own stream.
```
```text
Give me 2 more Shorts from that same video.
```
```text
Switch to the podcast template and turn off uppercase captions.
```

## Use it (directly)
```bash
python scripts/cli.py run ~/Videos/stream.mp4 --rights own --template gaming-reaction --count 3
python scripts/cli.py more ~/Videos/stream.mp4 --rights own --count 2        # new moments only
python scripts/cli.py analyze "https://youtu.be/XXXXXXXXXXX" --rights own > candidates.json
python scripts/cli.py render --plan plan.json                                 # agent- or hand-written plan
python scripts/cli.py resume                                                  # finish an interrupted run
python scripts/cli.py history show ~/Videos/stream.mp4
```
Templates:
```bash
python scripts/cli.py templates list
python scripts/cli.py templates use gaming-reaction
python scripts/cli.py templates set gaming-reaction captions.uppercase=false
python scripts/cli.py templates reset gaming-reaction
```
Quality: Shorts export in **4K (2160×3840)** by default. Add `--1080p` for a 1080×1920 export that renders about
4× faster. If the source is smaller than 4K, the result says it was upscaled.

## Gaming reaction videos
The `gaming-reaction` template finds the reaction cam on its own. It works with a normal webcam, a cam with a
border, a cam in a corner, and any picture-in-picture reaction overlay, even when no face is visible. The whole
cam is shown in the top panel (never cut off) and the gameplay fills the rest.

## Sound effects
Sound effects are added only when a moment really calls for one, and skipped otherwise:
- laughter → a laugh, a surprise or shock → a short boom, a big reaction spike → a soft hit.
- At most 1 or 2 per Short, quiet, under the original audio. Podcast and minimal templates use none.
- By default the engine uses its own built-in effects (made with FFmpeg, no copyright).
- To use your own sounds, put **generic, cleared** files in `~/NeoClip-SFX/cleared/` and name them by type
  (`laugh_1.mp3`, `boom.wav`, `hit_soft.mp3`). You can browse [Myinstants](https://www.myinstants.com/en/index/in/)
  yourself and save only generic, royalty-free effects there. The engine never downloads sounds by itself
  (the site's terms don't allow automated access).
- **No copyrighted sounds.** Files whose name points to a movie, TV show, song, game or brand are skipped.
  When in doubt, the engine uses a built-in effect or none. Every sound used is listed in the Short's
  Publishing Notes.

## YOUTUBE_METADATA.md
Made for copy and paste. Each Short has only its filename, a **Title** box, a **Description** box (plain text:
the full story, related keywords, creator credit with links, hashtags on the last line) and **Publishing Notes**
for you (timestamp, risk check, sound effects used). See [the example](examples/example-metadata.md).

## Long YouTube videos (fast mode)

YouTube videos are **never downloaded in full** by default. Instead the engine:

1. Reads the video's details and YouTube's "most replayed" graph (no download).
2. Fetches low-quality audio in **1-hour batches**, 3 at a time. Each batch gets a loudness pass and a
   **Whisper transcript of the real audio**, then its audio file is deleted. Results are saved per batch, so a
   stopped run continues from the last finished batch.
3. Picks the best moments from the transcript, the loudness and the replay graph.
4. Downloads **only the chosen clips** in full quality, in parallel, while earlier clips render. Each clip file
   is deleted once its Short is saved.

YouTube's own captions are not used unless you ask for them with `--youtube-captions`.

**Rough estimates for a 25-hour stream** (not measured on a real 25-hour video; depends on your connection
and computer):

| Step | Time | Disk space |
|---|---|---|
| Video details + replay graph | seconds | none |
| Audio, 25 batches | about 5–20 min to download, 1–3 min to analyse | under 100 MB at any moment |
| Whisper, default for videos over 3 hours: only the strongest moments | about 2–10 min | small |
| Whisper, `--transcribe full`: every hour | about 2.5–4 h on a modern CPU (small model), 1–2 h with `--whisper-model base`, 20–60 min on an NVIDIA GPU | small |
| Each chosen clip | under a minute to download | about 20–60 MB per clip at 4K, deleted afterwards |
| Rendering | about 1 min per Short with a hardware encoder, several minutes with x264 at 4K | the finished Shorts |

The old way downloaded the whole video first (often 10–50 GB for 25 hours at 4K) before anything else could start.

Useful options:
```bash
python scripts/cli.py run "https://youtu.be/XXXXXXXXXXX" --rights own --range 2:00:00-6:00:00   # only search part of it
python scripts/cli.py run "https://youtu.be/XXXXXXXXXXX" --rights own --transcribe full          # Whisper every hour
python scripts/cli.py run "https://youtu.be/XXXXXXXXXXX" --rights own --whisper-model base       # faster Whisper
python scripts/cli.py run "https://youtu.be/XXXXXXXXXXX" --rights own --workers 5                # more parallel downloads
python scripts/cli.py run "https://youtu.be/XXXXXXXXXXX" --rights own --full-download            # old behaviour
```

Rendering uses Apple VideoToolbox or NVIDIA NVENC automatically when FFmpeg has them, and falls back to x264 if
they fail. For the highest quality at the cost of speed, set `"hw_encoder": "off"` in the config.

## Configuration
Optional `~/.neoclip-ai-skill/config.json` (all keys: `scripts/config.py`):
```json
{"output_root": "~/Videos/YouTube_Shorts", "resolution": "2160x3840", "whisper_model": "small",
 "caption_corrections": {"valorent": "Valorant"}, "music_library": "~/Music/licensed/music_library.json",
 "ai": {"command": null}}
```
Environment: `YT_SHORTS_STATE_DIR`, `YT_SHORTS_OUTPUT_ROOT`, `YT_SHORTS_RESOLUTION`, `YT_SHORTS_WHISPER_MODEL`,
`YT_SHORTS_AI_COMMAND`, `YT_SHORTS_MUSIC_LIBRARY`.

## Tests
```bash
python -m pytest -q      # 80 tests, about 1 minute, needs FFmpeg
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
- **Fast mode framing** checks faces and the facecam inside each downloaded clip, not across the whole video.
  Use `--full-download` if a template needs whole-video visual analysis.
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
**Version:** 2.0.0
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
