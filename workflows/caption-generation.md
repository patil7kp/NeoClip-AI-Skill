# Workflow: caption generation

1. Transcription happens during `analyze` (cached). For non-English content, pass `--language xx` for better accuracy.
2. Per clip: words are cleaned, remapped through the TimelineMap, chunked, and placed in the safe zone away from faces.
3. Preset choice: the template default, or `--caption-preset`. After the first Short of a source video, the preset
   is locked for that video's later Shorts, which keeps a series consistent.
4. Review: skim `captions.events` in the result (0 means no speech was found). If names are wrong, add
   `caption_corrections` to `~/.neoclip-ai/config.json` and re-render the plan.
5. No transcript (no backend, or no audio): the Shorts render without captions and the result warns. Tell the
   user. Options: `pip install faster-whisper`, or `--subtitles` with an existing .srt/.vtt.
