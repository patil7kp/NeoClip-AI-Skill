<p align="center"><img src="assets/banner-animated.webp" alt="NeoClip-AI-Skill banner" width="100%"></p>

# NeoClip-AI-Skill

**Created by Kiran Patil - NeoClip-AI-Skill** · v1.0.0 · © 2026 Kiran Patil. All Rights Reserved.

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

## Installation

Use the quick install if you just want it working. The manual steps after it explain each agent in detail.

### Quick install (easiest)

**Option A: let your AI agent install it.** Open an agent that can use your terminal (Claude Code, Codex CLI,
Gemini CLI, Cursor or Copilot agent mode), copy this message, and send it:

> Install the NeoClip-AI-Skill from https://github.com/patil7kp/NeoClip-AI-Skill for me. Clone it, install
> FFmpeg and the Python requirements, run `python scripts/cli.py doctor`, and set it up as a skill for
> this agent by following the Installation section of its README.

The agent does the rest and asks before running each command.

**Option B: add it in your app's settings (Claude app and claude.ai).**
1. Download the skill: [NeoClip-AI-Skill.zip](https://github.com/patil7kp/NeoClip-AI-Skill/archive/refs/heads/main.zip)
   (or click **Code → Download ZIP** on this page).
2. In Claude, open **Settings → Capabilities**, make sure code execution is on, and upload the zip under
   **Skills**.
3. Start a new chat and ask for Shorts. Claude picks up the skill automatically.

Prefer to do it by hand, or using a different agent? Follow the two steps below.

### Step 1: Set up the engine (everyone does this once)

1. Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/).
2. Install **FFmpeg** (it must include libass, which the standard builds below do):
   - macOS: `brew install ffmpeg`
   - Windows: `winget install Gyan.FFmpeg`
   - Ubuntu / Debian: `sudo apt install ffmpeg`
3. Download the skill and install its Python packages:
   ```bash
   git clone https://github.com/patil7kp/NeoClip-AI-Skill.git
   cd NeoClip-AI-Skill
   python -m pip install -r requirements.txt
   ```
4. Check that everything is ready:
   ```bash
   python scripts/cli.py doctor          # should print "ready": true
   python scripts/cli.py setup-models    # optional: downloads the face-tracking model
   ```

### Step 2: Connect it to your AI agent

Pick the agent you use. Agents marked **full** run the engine for you. Agents marked **planning** choose the
moments and write the titles in chat, and you run two commands yourself.

#### Claude Code (full)
1. Install Claude Code: see the [official setup guide](https://docs.anthropic.com/en/docs/claude-code/setup).
2. Copy the skill into your skills folder:
   - macOS / Linux: `cp -r NeoClip-AI-Skill ~/.claude/skills/neoclip-ai-skill`
   - Windows (PowerShell): `Copy-Item -Recurse NeoClip-AI-Skill $HOME\.claude\skills\neoclip-ai-skill`
3. Start `claude` in any folder and ask: *"Make 3 Shorts from ~/Videos/stream.mp4. It's my own video."*
   Claude loads the skill automatically.

#### Claude desktop app and claude.ai (planning, sometimes full)
1. Zip the `NeoClip-AI-Skill` folder.
2. In Claude, open **Settings → Capabilities**, turn on code execution, then upload the zip under **Skills**.
3. Ask for Shorts as usual. Claude's online sandbox may not have FFmpeg or internet access, so if
   `doctor` is not ready there, Claude switches to planning mode: you run `analyze` and `render` on your
   computer and upload the JSON files it asks for.

#### Claude Agent SDK (full)
Point the SDK's skills directory at the `NeoClip-AI-Skill` folder, or load `SKILL.md` as the system prompt and
give the agent a Bash tool. See [`platforms/claude.md`](platforms/claude.md).

#### OpenAI Codex CLI (full)
1. Install Codex CLI: `npm install -g @openai/codex` (needs Node.js 18+), then sign in when it asks.
2. Open a terminal in the `NeoClip-AI-Skill` folder and run `codex`.
3. Codex reads `AGENTS.md` automatically. Ask for your Shorts and approve the commands when it asks.

#### ChatGPT (planning)
1. Create a **Project** (or a Custom GPT).
2. Paste the instructions from [`platforms/chatgpt-instructions.md`](platforms/chatgpt-instructions.md) into its
   instructions box.
3. Upload these files as project knowledge: `SKILL.md`, `templates/*.md`, `references/clip-selection.md`,
   `references/youtube-policies.md`, `references/output-guidelines.md`.
4. Chat with it. It tells you when to run `analyze` and `render` on your computer and what to upload.

#### Gemini CLI (full)
1. Install Gemini CLI: `npm install -g @google/gemini-cli` (needs Node.js 18+), then sign in with Google.
2. Open a terminal in the `NeoClip-AI-Skill` folder and run `gemini`.
3. Gemini reads `GEMINI.md`, which loads the skill. Approve the commands when it asks.

#### Gemini web app (planning)
1. Create a **Gem**.
2. Paste the same instructions used for ChatGPT ([`platforms/chatgpt-instructions.md`](platforms/chatgpt-instructions.md))
   and upload the same knowledge files.
3. Chat with it, and run `analyze` and `render` on your computer when it asks.

#### Cursor (full)
1. Open the `NeoClip-AI-Skill` folder in Cursor (**File → Open Folder**).
2. The rule in `.cursor/rules/neoclip-ai-skill.mdc` loads when you ask Cursor's **Agent** for Shorts.
3. Approve the terminal commands. Rendering can take a few minutes, so let long commands finish.

#### GitHub Copilot in VS Code (full)
1. Install the **GitHub Copilot** and **GitHub Copilot Chat** extensions and sign in.
2. Open the `NeoClip-AI-Skill` folder in VS Code.
3. Open Copilot Chat, switch the mode to **Agent**, and ask for your Shorts. Copilot reads `AGENTS.md`
   (if it doesn't, check that the *Use AGENTS.md file* setting is on, or attach `SKILL.md` to the chat).
4. Approve the terminal commands when it asks.

#### Any other agent (Windsurf, Cline, Aider and similar)
If the agent can read files and run terminal commands, open the `NeoClip-AI-Skill` folder and tell it:
*"Read SKILL.md and follow it."* If it can only chat, use the ChatGPT planning steps above.

More detail on what each agent can and can't do: [`references/agent-compatibility.md`](references/agent-compatibility.md).

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
