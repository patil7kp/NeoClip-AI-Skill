# Output guidelines

```
YouTube_Shorts/                 ← --output-root (default ./YouTube_Shorts)
└── 2026-11-27/                 ← processing date, YYYY-MM-DD (local time; --date to override)
    ├── 01_best_reaction.mp4
    ├── 02_funny_moment.mp4
    ├── 03_epic_gameplay.mp4
    └── YOUTUBE_METADATA.md     ← exactly one per date, covering every Short in the folder
```

## Rules the engine enforces
- **Only** `NN_descriptive_name.mp4` files and one `YOUTUBE_METADATA.md`. No `source/`, `logs/`, `config/`,
  `previews/`, `thumbnails/`, `reports/`, no per-Short Markdown, and no copies of the original video.
- Numbering continues across sessions on the same date. A second run that day creates `04_…`, `05_…` and
  appends to the same metadata file. Nothing is overwritten.
- Filenames come from the plan's `slug` (the agent's description of the content) or the detected moment type.
  Make slugs specific: `boss_fight_clutch`, not `clip`.
- Updates are block-level: an existing Short's entry is matched by filename and replaced in place, never duplicated.
- Internal state (history, caches, temporary renders, risk reports, job files) lives in
  `~/.neoclip-ai/`, never in the output.

## YOUTUBE_METADATA.md entry format
See `examples/example-metadata.md`. Each entry has: `## Short NN: Heading`, **Video File**, **Original Timestamp**,
`### YouTube Title`, `### YouTube Description` (paste-ready: story, credit lines, links, hashtags),
**Original Creator**, **Channel** (clickable), **Original Video** (clickable, with `&t=`), `### Hashtags`, and
`### Publishing Notes` (risk summary and upscaling notice, for the uploader; not for the description).
Credit lines appear only when the source is known and attribution is appropriate.

## Writing titles and descriptions (agent)
- **Title:** what happens + why it's interesting, ≤ 70 characters (YouTube allows 100), natural language, specific nouns
  (game, person, topic). No fake stakes, no "you won't believe", no ALL CAPS.
- **Description:** 2 to 4 sentences that tell the whole story of the Short: setup, what happens, the reaction or
  point. Add keywords naturally. The engine appends the credit, links and hashtags.
- **Hashtags:** 3 to 6, starting with `#shorts`, then topic, game or creator. They must be relevant to the clip.
