# AGENTS.md: NeoClip AI

This repository is an AI-agent skill. Codex, Cursor, Copilot, Windsurf, Cline, Aider and other agents that
read `AGENTS.md`: **read `SKILL.md` in this folder and follow it exactly.** It contains the workflow,
the rules (rights first, honest reporting, no policy guarantees) and the commands.

- Engine: `python scripts/cli.py <command>`. It prints JSON on stdout and progress on stderr.
- Check setup: `python scripts/cli.py doctor`
- Typical flow: `inspect` → `analyze` → write `plan.json` → `render --plan plan.json` → report.
- Tests: `python -m pytest -q` (needs FFmpeg).
- Don't write anything except the engine's outputs into the `YouTube_Shorts/` output folders.
- State and history: `~/.neoclip-ai/` (override with `YT_SHORTS_STATE_DIR`).

If this file was copied into another project, replace `scripts/cli.py` and `SKILL.md` with absolute paths to
the skill folder.

NeoClip AI, created by Kiran Patil. © 2026 Kiran Patil. All Rights Reserved. See `AUTHOR.md` and `LICENSE`.
