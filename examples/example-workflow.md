# Example session (agent-driven)

**User:** Make 3 Shorts from my stream https://www.youtube.com/watch?v=XXXXXXXXXXX. Gaming template.

**Agent** checks the setup and the input, then asks about rights:
```bash
python scripts/cli.py doctor
python scripts/cli.py inspect "https://www.youtube.com/watch?v=XXXXXXXXXXX"
```
> "This is 2h 41m, 'Ranked grind to Immortal' by YourChannel. Is this your own channel? I can only clip
> videos you own or have permission to use."

**User:** Yes, it's my channel.

```bash
python scripts/cli.py analyze "https://www.youtube.com/watch?v=XXXXXXXXXXX" --rights own \
  --template gaming-reaction --count 3 > /tmp/candidates.json
```
Excerpt of the result (illustrative):
```json
{
  "status": "analyzed", "video_id": "yt-XXXXXXXXXXX", "content_hint": "gaming", "facecam_detected": true,
  "previously_completed": [],
  "candidates": [
    {"rank": 1, "start": 4512.3, "end": 4549.8, "range": "01:15:12 - 01:15:49", "score": 1.92,
     "category": "excitement", "reasons": ["sharp loudness peak (reaction/shout/laugh)", "excitement cues (\"let's go\", \"insane\")"],
     "excerpt": "Okay one left, he's in site. I'm one HP. No way. NO WAY! Let's go! That's the clutch!"},
    {"rank": 2, "start": 2210.0, "end": 2241.6, "range": "00:36:50 - 00:37:21", "score": 1.71,
     "category": "laughter", "excerpt": "Did he just jump off the map? Haha I can't breathe ..."}
  ]
}
```

The agent reviews the excerpts. In rank 1 the setup ("one left, I'm one HP") is present and the payoff lands,
but the celebration continues after it, so the agent extends the end by 3 s. Then it writes the plan:

```json
{
  "input": "https://www.youtube.com/watch?v=XXXXXXXXXXX",
  "rights": "own",
  "template": "gaming-reaction",
  "clips": [
    {"start": "01:15:12.3", "end": "01:15:52.8", "slug": "one_hp_clutch",
     "title": "1 HP, last one alive... and he clutched it",
     "description": "Down to one HP with one enemy left on site, the round looks lost. A last-second peek wins it, and the reaction says the rest.",
     "hashtags": ["#shorts", "#valorant", "#clutch", "#gaming"], "hook_text": "1 HP. Last alive."},
    {"start": "00:36:50", "end": "00:37:21.6", "slug": "enemy_jumps_off_map",
     "title": "The enemy just... jumped off the map",
     "description": "Mid-fight, the opponent panics and walks straight off the edge. Nobody in the lobby can stop laughing.",
     "hashtags": ["#shorts", "#valorant", "#funny", "#gaming"], "hook_text": "Wait, where did he go?"},
    {"start": "02:03:05", "end": "02:03:41", "slug": "ace_to_immortal",
     "title": "The ace that finally hit Immortal",
     "description": "Match point for the rank-up. Five kills in one round, then the rank screen pops.",
     "hashtags": ["#shorts", "#valorant", "#ace", "#ranked"]}
  ]
}
```

```bash
python scripts/cli.py render --plan /tmp/plan.json > /tmp/result.json
```

**Agent's report (from result.json):**
> Done: 3 Shorts in `YouTube_Shorts/2026-11-27/`.
> 1. `01_one_hp_clutch.mp4` (01:15:12 to 01:15:52, 40.1 s). Risk: low.
> 2. `02_enemy_jumps_off_map.mp4` (00:36:50 to 00:37:21, 30.9 s). Risk: medium. Possible music was detected
>    for 12 s (the game soundtrack). Check it's fine for your channel, or I can trim that part.
> 3. `03_ace_to_immortal.mp4` (02:03:05 to 02:03:41, 35.6 s). Risk: low.
>
> All three use the gaming layout (facecam on top). They're 2160×3840 but upscaled from a 1080p source, so
> don't call them native 4K. Titles, descriptions and hashtags are in `YOUTUBE_METADATA.md`.
> 2h 39m of the stream is still unused. Ask for more any time.

**Next day. User:** Two more from that stream.
```bash
python scripts/cli.py more "https://www.youtube.com/watch?v=XXXXXXXXXXX" --rights own --count 2
```
The engine skips the three used ranges automatically, and the new files go to the new date folder.
