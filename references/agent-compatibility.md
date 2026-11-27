# Agent compatibility

The skill has two parts:

1. **Instructions**: `SKILL.md` plus these Markdown files. Any agent that can read files can follow them.
2. **Engine**: `scripts/cli.py`, plain Python and FFmpeg that print JSON. Any agent that can run shell
   commands can drive it. No AI provider is needed for video processing.

So the same engine and the same results work everywhere. The only things that differ between agents are
how the instructions get loaded and whether a shell is available.

## Support matrix

| Agent | How it loads the skill | Runs the engine? | Notes |
|---|---|---|---|
| **Claude Code** (CLI, desktop, web) | Plugin (`/plugin install neoclip-ai-skill@neoclip-ai`) or native Agent Skills: copy the folder to `~/.claude/skills/neoclip-ai-skill/` (personal) or `.claude/skills/` (project) | Yes | Best supported. The skill triggers from its `description`. |
| **Claude.ai / Claude desktop (Skills)** | Upload the folder as a skill (zip) in Settings → Capabilities → Skills | Only where code execution is enabled **and** FFmpeg is available | The hosted sandbox may lack network access for YouTube, or FFmpeg/libass. Local files are best. |
| **OpenAI Codex CLI** | Reads `AGENTS.md`. Newer Codex versions also load `SKILL.md` skills from `~/.codex/skills/` | Yes | `AGENTS.md` points the agent at `SKILL.md`. |
| **ChatGPT (web/app)** | Paste `platforms/chatgpt-instructions.md` into a Project or Custom GPT and attach `SKILL.md` + references | **Usually no.** The ChatGPT sandbox has no internet and its FFmpeg build is not guaranteed | Use ChatGPT for planning (it writes `plan.json`) and run the engine locally, or use the Codex CLI. |
| **Gemini CLI** | Reads `GEMINI.md` (context file) in the project root | Yes | `GEMINI.md` imports `SKILL.md`. |
| **Gemini (web/app)** | Paste `platforms/gemini-instructions.md` into a Gem | No local shell | Planning only, like ChatGPT web. |
| **Cursor** | `.cursor/rules/neoclip-ai-skill.mdc` (agent-requested rule) and `AGENTS.md` | Yes (agent terminal) | Open the skill folder or add it to the workspace. |
| **GitHub Copilot agent mode, Windsurf, Cline, Roo, Aider, others** | `AGENTS.md` (widely supported) or reference `SKILL.md` manually | Yes, if the agent has a terminal | All you need is the ability to read Markdown and run a command. |

> The Agent Skills format (`SKILL.md` with YAML front matter) is an open standard that a growing number of
> tools load natively. Check your tool's documentation for its skills directory, because support changes quickly.

## Installation

```bash
git clone <your copy> neoclip-ai-skill    # or unzip the release
cd neoclip-ai-skill
python -m pip install -r requirements.txt
python scripts/cli.py doctor
```
FFmpeg must be installed separately. Use `brew install ffmpeg` (macOS), `winget install Gyan.FFmpeg` (Windows),
or `sudo apt install ffmpeg` (Debian/Ubuntu). The build must include libass. Standard builds do.

### Claude Code
As a plugin (recommended), in Terminal, one line at a time:
```bash
claude plugin marketplace add patil7kp/NeoClip-AI-Skill
claude plugin install neoclip-ai-skill@neoclip-ai
```
Inside a Claude Code chat, send the same as `/plugin ...` commands, one per message. The Claude desktop app's
`/plugin` takes no arguments, so use Terminal there.
Or as a plain skill folder:
```bash
mkdir -p ~/.claude/skills && cp -r neoclip-ai-skill ~/.claude/skills/
```
Ask: "Make 3 Shorts from ~/Videos/stream.mp4 with the gaming template, I own it."

### Codex CLI / Cursor / Copilot / others reading AGENTS.md
Open the skill folder as the workspace, or copy `AGENTS.md` into your project and fix the path inside it.
In Cursor, `.cursor/rules/neoclip-ai-skill.mdc` is picked up automatically when the folder is in the workspace.

### Gemini CLI
Run `gemini` from inside the skill folder. `GEMINI.md` is loaded automatically and imports `SKILL.md`.

### ChatGPT / Gemini web (planning-only mode)
1. Create a Project (ChatGPT) or Gem (Gemini). Paste the platform instructions file and attach `SKILL.md`,
   the `templates/` files and `references/clip-selection.md`.
2. Run `python scripts/cli.py analyze ... > candidates.json` locally and upload `candidates.json`.
3. The assistant returns `plan.json`. Then run `python scripts/cli.py render --plan plan.json` locally.

## Platform-specific limitations

- **No shell access** (ChatGPT/Gemini web): the agent cannot render or keep history. It can only plan.
  History lives on the machine that runs the engine.
- **Hosted sandboxes**: may block YouTube downloads (no network), lack GPUs (Whisper on CPU is slower,
  so use `--whisper-model base`), or limit file sizes and run time. Prefer local agents for long videos.
- **Context limits**: `analyze` returns excerpts, not the full transcript. Agents with small context
  windows should look at the top 6 to 10 candidates only.
- **Optional unattended AI**: for cron or batch use without an agent, set `ai.command` (for example
  `claude -p`, `gemini -p`, `ollama run llama3.1`). See `scripts/ai_bridge.py`. If it fails, the engine
  falls back to heuristics.

## Where state lives (same for every agent)

`~/.neoclip-ai-skill/` (override with `YT_SHORTS_STATE_DIR`):
`history/` (timestamp memory), `preferences.json` (remembered template), `config.json` (optional settings),
`work/` (downloads, analysis cache, temporary renders), `models/` (optional face model),
`music_library.json` (your verified tracks). Because this is plain files, memory survives new sessions and
switching agents.
