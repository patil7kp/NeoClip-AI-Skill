# Claude notes

- **Claude Code**: copy the folder to `~/.claude/skills/neoclip-ai/`. Claude loads `SKILL.md` when a
  request matches the description. Everything runs locally, including YouTube input, history and 4K renders.
- **Claude apps with Skills + code execution**: upload a zip of the folder. Code execution sandboxes may not have
  FFmpeg with libass or network access. Run `python scripts/cli.py doctor` first. If it isn't ready, use Claude
  Code or the planning flow in `chatgpt-instructions.md`.
- **Claude Agent SDK**: point the SDK's skills directory at this folder, or load `SKILL.md` as a system prompt and
  give the agent a Bash tool.
