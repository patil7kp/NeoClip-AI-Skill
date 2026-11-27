# Music guidelines

## Default: keep the original audio
Most Shorts in these templates are dialogue- or reaction-driven, so music is **off** for every template
except `storytelling-commentary` (which uses `auto`). In `auto` mode, a bed is only considered when speech
covers less than 35% of the clip, the clip contains no possible music already, and a verified track exists.

## Your licensed music library
Create `~/.neoclip-ai-skill/music_library.json` (or set `music_library` in `config.json`):
```json
{"tracks": [{
  "path": "tracks/calm_piano.mp3",
  "title": "Calm Piano",
  "artist": "Artist Name",
  "source": "YouTube Audio Library",
  "license": "youtube-audio-library",
  "license_url": "https://www.youtube.com/audiolibrary",
  "attribution_required": false,
  "attribution_text": "",
  "moods": ["calm", "cinematic"],
  "verified": true,
  "verified_note": "Checked license in Audio Library on 2026-11-27"
}]}
```
Allowed `license` values: `youtube-audio-library`, `cc0`, `cc-by` (attribution text required),
`commercial-license`, `original`. The engine **skips** any entry that:
- is not `verified: true` (licensing terms must be checked by a human; never assume),
- has a license outside this list (for example `cc-by-nc` or unknown),
- requires attribution but has an empty `attribution_text`,
- points to a missing file.

## Mixing
- The music sits at `music.volume_db` (-20 to -24 dB) and is **ducked** under speech with a sidechain compressor.
- Original dialogue and sound effects are never removed or replaced.
- Attribution text, when present, is added to the Short's description and to `YOUTUBE_METADATA.md`.

## Agent rules
- Never download or suggest "trending" commercial songs for background use.
- Never label a track "copyright-free" or "no copyright" unless its license was verified. Say "licensed under X" instead.
- If no verified track fits, keep the original audio and say so (`music.reason` in the result).
- To use the official Shorts Audio Library songs (licensed only inside YouTube's editor), tell the user to add
  them in the YouTube app at upload time. They can't be baked in here.
