# Workflow: metadata generation

The engine writes `YOUTUBE_METADATA.md` from the plan. The agent writes the words.

For each clip in the plan:
- `slug`: 2 to 4 lowercase words naming the content (`clutch_1v3_ending`, `why_sleep_matters`).
- `title`: ≤ 70 characters, accurate, specific, engaging. Good: "He clutched a 1v3 with 2 HP left". Bad: "INSANE!!! (you won't believe)".
- `description`: 3 to 5 plain-text sentences that explain the whole Short (setup, what happens, the reaction or
  takeaway), naming the creator, game or topic, with natural keywords. No Markdown. Don't put credit, related
  keywords or hashtags here: the engine appends a `Related:` line, the creator credit and the hashtags (last line).
- `hashtags`: 3 to 6 relevant tags, including `#shorts`.
- `hook_text` (gaming and funny templates): ≤ 6 words, true to the clip.

Credit: pass `creator`, `channel_url` and `source_url` in the plan for local files of someone else's content.
YouTube sources fill these in automatically. When the user owns the content, credit lines are still added if
the channel is known (harmless, and good for discovery). Set `metadata.credit=false` in the template to turn
them off.

`run` without a plan writes heuristic titles (a quoted line from the clip) and marks `metadata_source: heuristic`.
Offer to rewrite them, then edit those blocks in `YOUTUBE_METADATA.md` directly. Re-rendering the same
range would be blocked as a duplicate.
