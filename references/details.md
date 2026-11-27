# NeoClip-AI-Skill: more details

Moved here from the README to keep it short.

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

## More commands
```bash
python scripts/cli.py analyze "https://youtu.be/XXXXXXXXXXX" --rights own > candidates.json
python scripts/cli.py render --plan plan.json
python scripts/cli.py history show ~/Videos/stream.mp4
python scripts/cli.py templates list
python scripts/cli.py templates set gaming-reaction captions.uppercase=false
python scripts/cli.py templates reset gaming-reaction
```
