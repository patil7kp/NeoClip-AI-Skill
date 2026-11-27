# Caption guidelines

One caption system for every category (`scripts/caption_generator.py`, burned in with libass).

## Consistency
- A source video's Shorts all use the **same preset**. The first preset used is stored in that video's history
  and reused unless `--caption-preset` changes it explicitly.
- Every preset uses the same safe-zone logic and sizes relative to the output height, so captions look the same
  at 1080p and 4K.

## Presets
| Preset | Look | Default for |
|---|---|---|
| `bold_pop` | heavy font, UPPERCASE, 3 words max, active word highlighted yellow, quick pop-in | gaming, funny |
| `clean_pro` | semibold, sentence case, up to 5 words, key words highlighted | podcast |
| `story` | bold, sentence case, 4 words max, active word highlighted orange | storytelling |
| `minimal` | medium weight, soft dark box, up to 6 words, no highlights | minimal professional |

Override individual style fields in a template: `templates set <id> captions.overrides='{"highlight":"00E5FF"}'`.
Fonts: the first installed font from the preset list is used (Montserrat, Inter, Arial, DejaVu). Put
custom fonts in a folder and set `fontsdir` in `config.json`.

## Placement (normalized height)
- Safe zone: 10% to 78% vertically, 6% to 86% horizontally. This keeps clear of the Shorts title, channel name
  and right-side buttons.
- Default centre is at 70%. If detected faces overlap that band, the engine tries 64%, 74%, 58% and then 28%.
- Gaming: on the seam between the facecam and the gameplay.
- Hook text: near the top (about 14%), only for the first ~2 s.

## Text quality
- Word-level timing from Whisper, re-mapped after pause removal.
- Clean-up: leading lowercase is capitalized, `i` becomes `I`, stray punctuation tokens are merged, stuttered
  repeats ("the the") are collapsed, and fillers (um, uh) are dropped from **captions only**.
- `caption_corrections` in `config.json` fixes recurring mistakes, for example game or creator names:
  `{"valorent": "Valorant"}`.
- Chunks break at punctuation, pauses over 0.6 s, the word or character limit, or 2.6 s on screen. Long chunks
  wrap to two lines.
- Languages: any language Whisper supports (`--language` to force one). The fonts must contain the glyphs, so
  install Noto fonts for non-Latin scripts.

## The agent's job
Read the generated caption text for proper nouns. If the transcript is consistently wrong about a name, add a
`caption_corrections` entry and re-render that clip.
