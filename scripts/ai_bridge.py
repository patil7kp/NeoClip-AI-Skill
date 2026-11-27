"""Optional, provider-agnostic AI refinement for fully unattended runs.

The skill normally needs NO AI API: the agent running the skill (Claude, ChatGPT, Gemini,
Cursor, ...) reads the candidates and writes the plan itself. For cron/batch use, set a
command that reads a prompt on stdin and prints text, e.g.
    "claude -p"            "gemini -p"            "ollama run llama3.1"
    "llm -m gpt-4o-mini"   "codex exec -"
via config.json {"ai": {"command": "..."}} or YT_SHORTS_AI_COMMAND. Any failure (missing
binary, timeout, bad JSON) raises AIProviderError and the pipeline falls back to heuristics.
"""
from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import AIProviderError

PROMPT = """You are editing YouTube Shorts from a longer video. Choose the {count} best clips from the
candidates below and write publishing metadata. Rules: keep each clip's start/end inside its candidate
range (you may tighten it for a cleaner opening/ending, never cut away needed context); titles must be
accurate to what happens (no misleading clickbait), <= 70 characters; descriptions explain the full story
of the clip in 2-4 sentences; 3-5 relevant hashtags; a short hook_text (<= 6 words) that is true to the clip;
a slug of 2-4 lowercase words describing the content (e.g. "boss_fight_reaction").
Return ONLY JSON: {{"clips": [{{"candidate_rank": n, "start": s, "end": e, "slug": "...", "title": "...",
"description": "...", "hashtags": ["#..."], "hook_text": "..."}}]}}

Source: {title} by {creator}
Template: {template}
Candidates:
{candidates}
"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise AIProviderError("AI provider returned no JSON.")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise AIProviderError(f"AI provider returned invalid JSON: {exc}") from exc


def refine(command: str, candidates: list[dict], source: dict, template: dict, count: int,
           timeout: float = 180) -> list[dict]:
    argv = shlex.split(command)
    if not argv or not shutil.which(argv[0]):
        raise AIProviderError(f"AI command '{command}' not found.", "Fix ai.command or unset it.")
    brief = [{k: c[k] for k in ("rank", "start", "end", "duration", "score", "category", "reasons", "excerpt")}
             for c in candidates[: max(count * 3, 6)]]
    prompt = PROMPT.format(count=count, title=source.get("title"), creator=source.get("creator") or "unknown",
                           template=template["name"], candidates=json.dumps(brief, indent=1, ensure_ascii=False))
    try:
        proc = subprocess.run(argv, input=prompt.encode(), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise AIProviderError(f"AI command timed out after {timeout}s.") from exc
    if proc.returncode != 0:
        raise AIProviderError(f"AI command failed: {proc.stderr.decode('utf-8', 'replace')[-300:]}")
    data = _extract_json(proc.stdout.decode("utf-8", "replace"))
    by_rank = {c["rank"]: c for c in candidates}
    out = []
    for item in data.get("clips", [])[:count]:
        base = by_rank.get(item.get("candidate_rank"))
        if not base:
            continue
        s = float(item.get("start", base["start"]))
        e = float(item.get("end", base["end"]))
        if not (base["start"] - 3 <= s < e <= base["end"] + 3):
            s, e = base["start"], base["end"]
        out.append({**base, "start": s, "end": e, "label": item.get("slug") or base["label"],
                    "title": item.get("title"), "description": item.get("description"),
                    "hashtags": item.get("hashtags"), "hook_text": item.get("hook_text"),
                    "metadata_source": "ai"})
    if not out:
        raise AIProviderError("AI provider selected no valid clips.")
    return out
