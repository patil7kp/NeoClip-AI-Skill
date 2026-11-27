<p align="center"><img src="assets/banner-animated.webp" alt="NeoClip-AI-Skill banner" width="500"></p>

# NeoClip-AI-Skill

**Created by Kiran Patil - NeoClip-AI-Skill** · v2.1.0 · © 2026 Kiran Patil. All Rights Reserved.

Turn long videos into ready-to-post YouTube Shorts with your AI agent. Free, local, no paid API.

## Features

- 🎬 **Any video:** YouTube links or local MP4, MOV, MKV, WebM files.
- ⚡ **Fast on long videos:** handles even 25-hour streams without downloading the whole video.
- 🎙️ **Real transcripts:** Whisper listens to the actual audio, no trust in YouTube captions.
- 🔥 **Finds the best moments:** reactions, laughs, loud spikes and YouTube's "most replayed" parts.
- 🔁 **Never repeats:** remembers used timestamps, so every new Short is fresh.
- 🎨 **5 templates:** Gaming, Podcast, Funny, Storytelling, Minimal.
- 🎮 **Reaction videos:** finds the reaction overlay in gameplay automatically and shows it whole above the game.
- 📱 **Smart 9:16 crop:** follows faces and action, no blind centre crops.
- 💬 **Captions:** word-by-word, synced, 4 styles, never covering faces.
- 🔊 **Sound effects:** only when the moment needs one, never copyrighted.
- 📺 **4K export:** 2160×3840 by default, `--1080p` for speed.
- 🛡️ **Copyright check:** flags possible Content ID and policy risks before you upload.
- 📝 **Ready-to-paste metadata:** title, description and hashtags for every Short.
- 🤖 **Works with your AI:** Claude (plugin), Codex, Gemini, Cursor, Copilot. Free and local.

## Install

**Claude Code (plugin):** run these two lines in Terminal, one at a time:
```bash
claude plugin marketplace add patil7kp/NeoClip-AI-Skill
```
```bash
claude plugin install neoclip-ai-skill@neoclip-ai
```
Inside a Claude Code chat you can send `/plugin marketplace add patil7kp/NeoClip-AI-Skill`, then `/plugin install neoclip-ai-skill@neoclip-ai`, as two separate messages. In the Claude desktop app, `/plugin` takes no text after it, so use the Terminal lines above.

**Any other agent** (Codex, Gemini CLI, Cursor, Copilot): send it this prompt.
```text
Install the NeoClip-AI-Skill from https://github.com/patil7kp/NeoClip-AI-Skill. Clone it, install FFmpeg and the Python requirements, run "python scripts/cli.py doctor", and set it up as a skill for this agent by following the Install section of its README.
```

**Claude app / claude.ai:** download the [zip](https://github.com/patil7kp/NeoClip-AI-Skill/archive/refs/heads/main.zip) and upload it in **Settings → Capabilities → Skills**.

### Manual install
```bash
brew install python ffmpeg            # Windows: winget install Python.Python.3.12 Gyan.FFmpeg
git clone https://github.com/patil7kp/NeoClip-AI-Skill.git
cd NeoClip-AI-Skill
python -m pip install -r requirements.txt
python scripts/cli.py doctor          # should say "ready": true
```

| Agent | How to connect |
|---|---|
| Claude Code | Plugin (above), or copy the folder to `~/.claude/skills/neoclip-ai-skill` |
| Codex CLI / Gemini CLI | Run `codex` or `gemini` inside the folder |
| Cursor / Copilot | Open the folder, use **Agent** mode |
| ChatGPT / Gemini web | Paste [`platforms/chatgpt-instructions.md`](platforms/chatgpt-instructions.md) (planning only) |
| Any other agent | "Read SKILL.md and follow it" |

## Use it

Just ask your agent:
```text
Make Shorts from https://youtu.be/XXXXXXXXXXX
```
```text
Give me 2 more Shorts from that same video.
```

Or run it yourself:
```bash
python scripts/cli.py run ~/Videos/stream.mp4 --template gaming-reaction --count 3
python scripts/cli.py more ~/Videos/stream.mp4 --count 2
python scripts/cli.py resume
```
Add `--1080p` for faster renders, or `--range 2:00:00-6:00:00` to search only part of a long video.

## Good to know

- **Hour by hour:** each run does the next hour of the video (3 Shorts), then the next run does the following hour. `--hours 3` does 3 hours at once. YouTube videos are never downloaded in full.
- **Sound effects:** added only when a moment needs one. To use your own, put generic, copyright-free files in `~/NeoClip-SFX/cleared/`.
- **Output:** `YouTube_Shorts/YYYY-MM-DD/` with the Shorts and one `YOUTUBE_METADATA.md` ([example](examples/example-metadata.md)).
- **No questions:** send a link and it starts. You are responsible for having the rights to the video; copyright checks are warnings, not guarantees.

More: [details, options and limitations](references/details.md) · [agent setup](references/agent-compatibility.md) · [changelog](CHANGELOG.md)

## Author & Copyright Information

**Project Name:** NeoClip-AI-Skill
**Created & Developed By:** Kiran Patil
**Role:** Software Engineer
**Project Type:** AI Agent Skill – YouTube Shorts Automation
**Version:** 2.1.0
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
