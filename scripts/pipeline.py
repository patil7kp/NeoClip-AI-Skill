"""End-to-end orchestration (the 30-step workflow in workflows/main-workflow.md).

    prepare  -> validate input, identify video, load history, download to work dir
    analyze  -> probe, visual + audio analysis, transcription (cached per video)
    select   -> rank moments in UNUSED footage (or validate the agent's plan)
    produce  -> per clip: reserve in history, edit plan, layout, captions, policy, music,
                render (with fallbacks), validate, move into date folder, metadata, mark completed
Each clip is independent: one failure never blocks or corrupts the others, and failed clips are
never recorded as used. Job state is saved so an interrupted run can be resumed.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import (ai_bridge, audio_analyzer, caption_generator, clip_selector, metadata_generator,
                     policy_checker, quality_validator, smart_cropper, sound_effects, source_input, transcription,
                     video_analyzer, video_editor, video_renderer)
import datetime as _dt

from scripts.common import (AIProviderError, InputError, RenderError, SkillError, TranscriptionError,
                            ValidationFailed, atomic_write_json, fmt_ts, log, merge_intervals, now_iso,
                            parse_ts, read_json, state_dir, today, work_dir)
from scripts.config import load_config, parse_resolution, update_preferences
from scripts.templates_config import load_template
from scripts.timestamp_manager import HistoryStore

ANALYSIS_VERSION = 3


class Pipeline:
    def __init__(self, cfg: dict | None = None, store: HistoryStore | None = None):
        self.cfg = cfg or load_config()
        self.store = store or HistoryStore()
        self.out_w, self.out_h = parse_resolution(self.cfg["resolution"])

    # ------------------------------------------------------------------ prepare
    def prepare(self, value: str, rights: str | None, template_id: str | None = None, *,
                creator: str | None = None, channel_url: str | None = None, source_url: str | None = None,
                title: str | None = None, remember_template: bool = True) -> dict:
        source = source_input.resolve_source(value, rights, creator=creator, channel_url=channel_url,
                                             source_url=source_url, title=title)
        template = load_template(template_id)
        if remember_template and template_id:
            update_preferences(template=template["id"])
        wd = work_dir(source["video_id"])
        if source["kind"] == "youtube":
            fast = self.cfg.get("youtube_mode", "fast") != "full"
        else:
            fast = bool(self.cfg.get("batch_mode", True))
        if fast and source["kind"] != "youtube":
            # Local file: nothing to download. Audio is analysed in 1-hour batches and each chosen clip is
            # cut out on its own, exactly like a YouTube link, so long files never go through in one pass.
            meta = video_analyzer.probe(source["local_path"])
            source["duration"] = meta["duration"] or source["duration"]
        elif fast:
            # No full download: analysis uses captions, the replay heatmap and chunked audio; only the
            # chosen clip ranges are downloaded (at full quality) when they are rendered.
            meta = {"duration": source["duration"], "width": int(source.get("width") or 1920),
                    "height": int(source.get("height") or 1080), "fps": float(source.get("fps") or 30.0),
                    "has_audio": True, "partial": True}
        else:
            if source["kind"] == "youtube":
                path = source_input.download_youtube(source, wd / "download", int(self.cfg["download_max_height"]))
                source["local_path"] = str(path)
            meta = video_analyzer.probe(source["local_path"])
            source["duration"] = meta["duration"] or source["duration"]
        rec = self.store.ensure(source)
        recovered = self.store.recover_interrupted(source["video_id"])
        if recovered:
            log(f"Recovered {len(recovered)} interrupted clip(s) from an earlier run (not counted as used).")
        return {"source": source, "meta": meta, "template": template, "work": wd, "history": rec,
                "recovered": recovered, "fast": fast}

    def analysis_range(self, duration: float) -> tuple[float, float]:
        rng = self.cfg.get("analyze_range")
        if not rng:
            return 0.0, duration
        a, b = (parse_ts(x) if isinstance(x, str) else float(x) for x in rng)
        a, b = max(0.0, a), min(duration, b) if b > 0 else duration
        if b - a < 5:
            raise InputError(f"--range {rng} is too short or outside the video ({fmt_ts(duration)} long).")
        return a, b

    def excluded_by_range(self, duration: float) -> list[list[float]]:
        a, b = self.analysis_range(duration)
        return [x for x in ([0.0, a], [b, duration]) if x[1] - x[0] > 0]

    # ------------------------------------------------------------------ analyze
    def analyze(self, ctx: dict, *, subtitles: str | None = None, transcribe: bool = True,
                count: int = 3) -> dict:
        if ctx.get("fast"):
            return self._analyze_fast(ctx, subtitles=subtitles, transcribe=transcribe, count=count)
        src, meta, wd = ctx["source"], ctx["meta"], ctx["work"]
        warnings: list[str] = []
        visual = read_json(wd / "visual.json")
        if not visual or visual.get("_v") != ANALYSIS_VERSION:
            log(f"Analysing video frames ({fmt_ts(meta['duration'])}) ...")
            visual = video_analyzer.analyze_visual(src["local_path"], meta, self.cfg["analysis_fps"],
                                                   self.cfg["face_detect_fps"])
            visual["_v"] = ANALYSIS_VERSION
            atomic_write_json(wd / "visual.json", visual)
        audio = read_json(wd / "audio.json")
        if not audio or audio.get("_v") != ANALYSIS_VERSION:
            log("Analysing audio ...")
            audio = audio_analyzer.analyze_audio(src["local_path"], meta)
            audio["_v"] = ANALYSIS_VERSION
            atomic_write_json(wd / "audio.json", audio)
        if not meta["has_audio"]:
            warnings.append("Source has no audio: no captions, speech cues or reaction detection.")
        transcript = None
        if subtitles:
            transcript = transcription.load_subtitles(subtitles)
        elif transcribe and meta["has_audio"]:
            tpath = wd / f"transcript_{self.cfg['whisper_model']}.json"
            transcript = read_json(tpath)
            scope = self.cfg["transcribe_scope"]
            if scope == "auto":
                scope = "candidates" if meta["duration"] > 45 * 60 else "full"
            need_ranges = None
            if scope == "candidates":
                pre = clip_selector.select_clips(meta["duration"], visual, audio, None, ctx["template"],
                                                 self.store.used_segments(src["video_id"])
                                                 + self.excluded_by_range(meta["duration"]), count,
                                                 candidate_pool=max(12, count * 4))
                need_ranges = [[max(0.0, c["start"] - 20), min(meta["duration"], c["end"] + 20)]
                               for c in pre["candidates"]]
                need_ranges = merge_intervals(need_ranges)
                if transcript:
                    have = transcript.get("ranges") or [[0, meta["duration"]]]
                    need_ranges = [r for r in need_ranges
                                   if not any(h[0] <= r[0] and r[1] <= h[1] for h in have)]
            if transcript is None or (need_ranges is not None and need_ranges):
                try:
                    new = transcription.transcribe(src["local_path"], self.cfg["whisper_model"],
                                                   self.cfg["language"], ranges=need_ranges,
                                                   device=self.cfg["whisper_device"],
                                                   compute_type=self.cfg["whisper_compute_type"])
                    if transcript and need_ranges:
                        new["segments"] = sorted(transcript["segments"] + new["segments"], key=lambda s: s["start"])
                        new["ranges"] = (transcript.get("ranges") or []) + need_ranges
                    transcript = new
                    atomic_write_json(tpath, transcript)
                except TranscriptionError as exc:
                    warnings.append(f"Transcription unavailable ({exc.message}). Shorts will have no captions; "
                                    f"{exc.hint}")
                    transcript = None
        analysis = {"visual": visual, "audio": audio, "transcript": transcript, "warnings": warnings}
        return analysis

    # ------------------------------------------------------------------ analyze (fast YouTube mode)
    def _analyze_fast(self, ctx: dict, *, subtitles: str | None, transcribe: bool, count: int) -> dict:
        """Analyse a YouTube video without downloading the video itself.

        The audio is fetched in batches (`audio_chunk_minutes`, low bitrate), several downloads in parallel.
        Each batch gets a loudness/pause pass and, in full-transcript mode, a Whisper pass, then its
        audio is deleted. Results are saved per batch, so disk use stays at a few batches and an
        interrupted run continues from the last finished batch. YouTube's own captions are NOT used
        unless `youtube_captions` is turned on: the transcript comes from the real audio.
        """
        src, meta, wd = ctx["source"], ctx["meta"], ctx["work"]
        dur = meta["duration"]
        a, b = self.analysis_range(dur)
        warnings: list[str] = []
        heatmap = src.get("heatmap") or []
        transcript = transcription.load_subtitles(subtitles) if subtitles else None
        if transcript is None and self.cfg.get("youtube_captions") and src["kind"] == "youtube":
            subs = source_input.download_youtube_subtitles(src, wd / "subs", self.cfg.get("language"))
            if subs:
                try:
                    transcript = transcription.load_subtitles(subs)
                except TranscriptionError:
                    transcript = None
        scope = self.cfg["transcribe_scope"]
        if scope == "auto":
            scope = "full" if (b - a) <= float(self.cfg.get("full_transcribe_max_hours", 3)) * 3600 else "candidates"
        whisper_ok = transcribe and transcript is None and transcription.available_backend() is not None
        if transcribe and transcript is None and not whisper_ok:
            warnings.append("Whisper is not installed (pip install faster-whisper), so Shorts will have no captions.")
        audio, transcript_full = self._chunked_audio(src, wd, a, b, whisper=whisper_ok and scope == "full",
                                                     warnings=warnings)
        transcript = transcript or transcript_full
        visual = video_analyzer.empty_visual(self.cfg["analysis_fps"])
        if transcript is None and whisper_ok and scope == "candidates":
            warnings.append(f"Long video ({fmt_ts(b - a)}): Whisper transcribed the strongest moments found by "
                            "the loudness/replay pass, not every hour. Set transcribe_scope to 'full' to "
                            "transcribe everything (much slower).")
            transcript = self._transcribe_candidates(ctx, audio, visual, heatmap, count, warnings)
        if src["kind"] != "youtube":
            msg = "Batch mode: audio was analysed hour by hour; only the chosen clips are cut out and analysed."
        else:
            msg = "Fast mode: the full video was not downloaded; only the chosen clips are fetched in full quality."
        if not heatmap and src["kind"] == "youtube":
            msg += " YouTube has no 'most replayed' data for this video, so selection uses audio and speech."
        warnings.append(msg)
        return {"visual": visual, "audio": audio, "transcript": transcript, "warnings": warnings,
                "heatmap": heatmap}

    def _chunks(self, a: float, b: float) -> list[tuple[float, float]]:
        size = max(60.0, float(self.cfg.get("audio_chunk_minutes") or 60) * 60)
        out, t = [], a
        while t < b - 0.5:
            out.append((round(t, 3), round(min(b, t + size), 3)))
            t += size
        return out

    def _whisper(self, path, offset: float) -> dict:
        tr = transcription.transcribe(path, self.cfg["whisper_model"], self.cfg["language"],
                                      device=self.cfg["whisper_device"],
                                      compute_type=self.cfg["whisper_compute_type"],
                                      beam_size=int(self.cfg.get("whisper_beam_size", 5)))
        tr["segments"] = [{**seg, "start": round(seg["start"] + offset, 3), "end": round(seg["end"] + offset, 3),
                           "words": [{**w, "start": round(w["start"] + offset, 3), "end": round(w["end"] + offset, 3)}
                                     for w in seg.get("words", [])]} for seg in tr["segments"]]
        return tr

    def _chunked_audio(self, src: dict, wd: Path, a: float, b: float, *, whisper: bool,
                       warnings: list[str]) -> tuple[dict, dict | None]:
        """Batch pipeline: downloads run ahead in parallel (bounded window), loudness analysis runs in the
        download workers, Whisper runs one batch at a time (it already uses every CPU core / the GPU)."""
        from concurrent.futures import ThreadPoolExecutor
        cdir = wd / "audio_chunks"
        cdir.mkdir(parents=True, exist_ok=True)
        chunks = self._chunks(a, b)
        model = self.cfg["whisper_model"]

        def names(rng):
            s, e = rng
            return cdir / f"chunk_{s:.0f}_{e:.0f}.json", cdir / f"chunk_{s:.0f}_{e:.0f}.whisper_{model}.json"

        def fetch(rng):
            s, e = rng
            aj, tj = names(rng)
            part = read_json(aj)
            part = part if part and part.get("_v") == ANALYSIS_VERSION else None
            need_tr = whisper and not tj.exists()
            if part and not need_tr:
                return part, None
            path = self._audio_section(src, cdir, s, e)
            if part is None:
                m = video_analyzer.probe(path, require_video=False)
                part = audio_analyzer.shift_audio(audio_analyzer.analyze_audio(path, m), s)
                part["_v"] = ANALYSIS_VERSION
                atomic_write_json(aj, part)
            if not need_tr:
                Path(path).unlink(missing_ok=True)
                return part, None
            return part, path

        done = sum(1 for c in chunks if names(c)[0].exists() and (not whisper or names(c)[1].exists()))
        workers = max(1, int(self.cfg.get("download_workers") or 1))
        log(f"Audio: {len(chunks)} batch(es) of up to {self.cfg.get('audio_chunk_minutes', 60)} min, "
            f"{done} already done{', with Whisper' if whisper else ''} ...")
        parts, segments, lang = [], [], None
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = {}
            nxt = 0

            def top_up():
                nonlocal nxt
                while nxt < len(chunks) and len(pending) < workers:
                    pending[nxt] = pool.submit(fetch, chunks[nxt])
                    nxt += 1
            top_up()
            for i, rng in enumerate(chunks):
                part, path = pending.pop(i).result()
                top_up()  # keep downloads running while this batch is transcribed
                parts.append(part)
                log(f"Batch {i + 1}/{len(chunks)}: {fmt_ts(rng[0])}-{fmt_ts(rng[1])} audio analysed")
                tj = names(rng)[1]
                if whisper:
                    tr = read_json(tj)
                    if tr is None and path:
                        try:
                            log(f"Transcribing batch {i + 1}/{len(chunks)} ({fmt_ts(rng[0])} - {fmt_ts(rng[1])}) ...")
                            tr = self._whisper(path, rng[0])
                            atomic_write_json(tj, tr)
                        except TranscriptionError as exc:
                            warnings.append(f"Transcription stopped ({exc.message}). {exc.hint}")
                            whisper = False
                    if tr:
                        segments += tr["segments"]
                        lang = lang or tr.get("language")
                if path:
                    Path(path).unlink(missing_ok=True)
        transcript = None
        if segments:
            transcript = {"language": lang, "backend": "whisper", "model": model, "ranges": [[a, b]],
                          "segments": sorted(segments, key=lambda x: x["start"])}
        return audio_analyzer.merge_audio(parts), transcript

    @staticmethod
    def _audio_section(src: dict, dest: Path, s: float, e: float) -> Path:
        if src["kind"] == "youtube":
            return source_input.download_youtube_audio_section(src, dest, s, e)
        return source_input.local_audio_section(src["local_path"], dest, s, e)

    def _transcribe_candidates(self, ctx, audio, visual, heatmap, count, warnings) -> dict | None:
        """No captions: Whisper listens only to the most promising moments, fetched as small audio sections."""
        from concurrent.futures import ThreadPoolExecutor
        src, meta, wd = ctx["source"], ctx["meta"], ctx["work"]
        tpath = wd / f"transcript_fast_{self.cfg['whisper_model']}.json"
        cached = read_json(tpath)
        pre = clip_selector.select_clips(meta["duration"], visual, audio, None, ctx["template"],
                                         self.store.used_segments(src["video_id"])
                                         + self.excluded_by_range(meta["duration"]), count,
                                         candidate_pool=max(12, count * 4), heatmap=heatmap)
        ranges = merge_intervals([[max(0.0, c["start"] - 20), min(meta["duration"], c["end"] + 20)]
                                  for c in pre["candidates"]])
        have = (cached or {}).get("ranges") or []
        need = [r for r in ranges if not any(h[0] <= r[0] and r[1] <= h[1] for h in have)]
        if not need:
            return cached
        log(f"Transcribing {len(need)} candidate section(s) with Whisper ...")
        tdir = wd / "whisper"
        workers = max(1, int(self.cfg.get("download_workers") or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:  # downloads in parallel, Whisper one by one
            futures = [pool.submit(self._audio_section, src, tdir, s, e) for s, e in need]
            segments = list((cached or {}).get("segments") or [])
            lang = (cached or {}).get("language")
            try:
                for (s, e), fut in zip(need, futures):
                    path = fut.result()
                    try:
                        tr = self._whisper(path, s)
                    finally:
                        Path(path).unlink(missing_ok=True)
                    lang = tr.get("language") or lang
                    segments += tr["segments"]
                    have = have + [[s, e]]
                    atomic_write_json(tpath, {"language": lang, "backend": tr.get("backend"),
                                              "model": self.cfg["whisper_model"], "ranges": have,
                                              "segments": sorted(segments, key=lambda x: x["start"])})
            except TranscriptionError as exc:
                warnings.append(f"Transcription unavailable ({exc.message}). {exc.hint}")
        return read_json(tpath) or cached

    # ------------------------------------------------------------------ select
    def select(self, ctx: dict, analysis: dict, count: int, *, plan_clips: list[dict] | None = None,
               use_ai: bool = True) -> tuple[list[dict], dict, list[str]]:
        src, meta = ctx["source"], ctx["meta"]
        used = self.store.used_segments(src["video_id"], include_active=True)
        outside = self.excluded_by_range(meta["duration"])
        sel = clip_selector.select_clips(meta["duration"], analysis["visual"], analysis["audio"],
                                         analysis["transcript"], ctx["template"], used + outside, count,
                                         candidate_pool=max(12, count * 4), heatmap=analysis.get("heatmap"))
        warnings = []
        atomic_write_json(ctx["work"] / "candidates.json", sel)
        if plan_clips:
            clips, w = clip_selector.validate_plan_clips(plan_clips, meta["duration"], used, ctx["template"])
            warnings += w
            for c in clips:
                c.setdefault("metadata_source", "agent")
            return clips, sel, warnings
        clips = sel["selected"]
        if use_ai and self.cfg["ai"].get("command") and clips:
            try:
                clips = ai_bridge.refine(self.cfg["ai"]["command"], sel["candidates"], src, ctx["template"], count,
                                         float(self.cfg["ai"].get("timeout", 180)))
            except AIProviderError as exc:
                warnings.append(f"AI refinement skipped ({exc.message}); used heuristic selection and metadata.")
        if len(clips) < count:
            warnings.append(f"Only {len(clips)} distinct unused moment(s) found (asked for {count}); "
                            f"{sel['unused_seconds']:.0f}s of footage remains unused.")
        return clips, sel, warnings

    # ------------------------------------------------------------------ produce
    def produce(self, ctx: dict, analysis: dict, clips: list[dict], *, date: str | None = None,
                output_root: str | None = None, captions: bool = True, job_id: str | None = None,
                caption_preset: str | None = None) -> dict:
        src, template = ctx["source"], ctx["template"]
        date = date or today()
        out_root = Path(output_root or self.cfg["output_root"]).expanduser().resolve()
        folder = metadata_generator.date_folder(out_root, date)
        job_id = job_id or f"{date}-{uuid.uuid4().hex[:6]}"
        jdir = ctx["work"] / "jobs" / job_id
        jdir.mkdir(parents=True, exist_ok=True)
        rec = self.store.load(src["video_id"]) or {}
        preset = caption_preset or rec.get("caption_preset") or template["captions"]["preset"]
        if not rec.get("caption_preset"):
            self.store.set_caption_preset(src["video_id"], preset)
        job = read_json(jdir / "job.json") or {
            "job_id": job_id, "video_id": src["video_id"], "input": src.get("url") or src.get("local_path"),
            "rights": src.get("rights"), "template": template["id"], "date": date, "output_root": str(out_root),
            "created": now_iso(), "clips": [dict(c, status="pending") for c in clips],
            "creator": src.get("creator"), "channel_url": src.get("channel_url"), "title": src.get("title"),
        }
        atomic_write_json(jdir / "job.json", job)
        results = []
        same_day = len(list(folder.glob("*.mp4")))
        prefetch = self._prefetch_sections(ctx, [c for c in job["clips"] if c.get("status") != "completed"])
        for i, clip in enumerate(job["clips"]):
            if clip.get("status") == "completed" and clip.get("output_path") and Path(clip["output_path"]).exists():
                results.append({**clip, "skipped": "already completed"})
                continue
            res = self._produce_one(ctx, analysis, clip, folder, jdir, job_id, preset, captions, same_day,
                                    prefetch.get((clip["start"], clip["end"])))
            same_day += 1 if res["status"] == "completed" else 0
            job["clips"][i] = {**clip, **{k: res.get(k) for k in ("status", "filename", "output_path", "error",
                                                                   "clip_id")}}
            atomic_write_json(jdir / "job.json", job)
            results.append(res)
        if prefetch:
            prefetch_pool = prefetch.pop("_pool", None)
            if prefetch_pool:
                prefetch_pool.shutdown(wait=True)
        job["finished"] = now_iso()
        job["status"] = "completed" if all(r["status"] == "completed" or r.get("skipped") for r in results) else (
            "partial" if any(r["status"] == "completed" for r in results) else "failed")
        atomic_write_json(jdir / "job.json", job)
        result = self._summary(ctx, analysis, results, folder, job, preset)
        atomic_write_json(jdir / "result.json", result)
        return result

    def _prefetch_sections(self, ctx: dict, clips: list[dict]) -> dict:
        """Fast mode: start downloading every clip's section in parallel while earlier clips render."""
        if not ctx.get("fast") or not clips:
            return {}
        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(max_workers=max(1, int(self.cfg.get("download_workers") or 1)))
        out: dict = {"_pool": pool}
        for c in clips:
            out[(c["start"], c["end"])] = pool.submit(self._fetch_section, ctx, c["start"], c["end"])
        return out

    def _fetch_section(self, ctx: dict, start: float, end: float) -> tuple[Path, float]:
        src, meta = ctx["source"], ctx["meta"]
        s0, e0 = source_input.section_range(start, end, meta["duration"], float(self.cfg.get("section_padding", 3)))
        if src["kind"] == "youtube":
            path = source_input.download_youtube_section(src, ctx["work"] / "sections", s0, e0,
                                                         int(self.cfg["download_max_height"]),
                                                         exact=bool(self.cfg.get("exact_section_cuts")))
        else:
            path = source_input.local_section(src["local_path"], ctx["work"] / "sections", s0, e0)
        # A stream-copied section may begin at the keyframe before s0. If the file is longer than asked,
        # the extra is at the start, so its first frame is at e0 - duration on the source timeline.
        got = video_analyzer.probe(path)["duration"]
        if got > (e0 - s0) + 0.3:
            s0 = max(0.0, round(e0 - got, 3))
        return path, s0

    def _produce_one(self, ctx, analysis, clip, folder, jdir, job_id, preset, captions, same_day,
                     section_future=None) -> dict:
        src, meta, template = ctx["source"], ctx["meta"], ctx["template"]
        cfg = self.cfg
        label = clip.get("label") or "best_moment"
        clip_id = self.store.reserve(src["video_id"], clip["start"], clip["end"], template["id"], job_id=job_id,
                                     label=label, overlap_reason=clip.get("overlap_reason"))
        base = {"clip_id": clip_id, "label": label, "source_range": [clip["start"], clip["end"]],
                "source_timestamp": f"{fmt_ts(clip['start'])} - {fmt_ts(clip['end'])}", "warnings": []}
        section_path, source_path, source_start = None, src.get("local_path"), 0.0
        visual = analysis["visual"]
        try:
            if ctx.get("fast"):
                section_path, source_start = (section_future.result() if section_future
                                              else self._fetch_section(ctx, clip["start"], clip["end"]))
                source_path = str(section_path)
                meta = video_analyzer.probe(section_path)
                visual = video_analyzer.shift_visual(
                    video_analyzer.analyze_visual(section_path, meta, cfg["analysis_fps"], cfg["face_detect_fps"]),
                    source_start)
            fps = video_renderer.output_fps(meta["fps"], cfg["max_fps"])
            edit = video_editor.plan_edit(clip, template, analysis["audio"], analysis["transcript"], fps)
            layout = smart_cropper.plan_layout(meta["width"], meta["height"], self.out_w, self.out_h,
                                               template["layout"], visual, clip["start"], clip["end"],
                                               edit["tmap"])
            base["warnings"] += layout["notes"]
            words = caption_generator.clean_words(edit["words"], cfg.get("caption_corrections"),
                                                  template["captions"].get("drop_fillers", True))
            out_words = edit["tmap"].map_words(words)
            cap_info, cap_path = None, None
            if captions and template["captions"].get("enabled", True) and out_words:
                cap_path = jdir / f"{clip_id}.ass"
                cap_info = caption_generator.write_captions(cap_path, out_words, self.out_w, self.out_h,
                                                            edit["output_duration"], preset, layout,
                                                            template["captions"].get("overrides"), edit["hook"])
            elif captions and not out_words:
                base["warnings"].append("No transcribed speech in this clip, so it has no captions.")
                if edit["hook"]:
                    cap_path = jdir / f"{clip_id}.ass"
                    cap_info = caption_generator.write_captions(cap_path, [], self.out_w, self.out_h,
                                                                edit["output_duration"], preset, layout,
                                                                None, edit["hook"])
                    cap_info["expected"] = False
            speech_cov = (sum(w["end"] - w["start"] for w in out_words) / edit["output_duration"]
                          if edit["output_duration"] else 0)
            music_overlap = any(min(clip["end"], m[1]) - max(clip["start"], m[0]) > 2
                                for m in (analysis["audio"] or {}).get("possible_music", []))
            music = audio_processor_decide(template, analysis["audio"], clip, speech_cov, cfg, music_overlap)
            base["warnings"] += music.get("warnings", [])
            sfx = []
            if meta.get("has_audio") and cfg.get("sfx", True):
                try:
                    sfx = sound_effects.resolve(sound_effects.plan_sfx(template, edit, analysis["audio"], clip),
                                                cfg, clip_id)
                except SkillError as exc:
                    base["warnings"].append(f"Sound effects skipped ({exc.message}).")
            sfx_gain = sound_effects.settings(template)["gain_db"]
            # metadata (agent/AI-provided or heuristic)
            meta_src = clip.get("metadata_source") or ("agent" if clip.get("title") else "heuristic")
            title = (clip.get("title") or metadata_generator.heuristic_title(clip, src)).strip()
            story = (clip.get("description") or metadata_generator.heuristic_description(clip, src)).strip()
            tags = metadata_generator.normalize_hashtags(clip.get("hashtags") or
                                                         metadata_generator.build_hashtags({**clip, "title": title},
                                                                                           src, template))
            show_credit = bool(src.get("creator") or src.get("url")) and template.get("metadata", {}).get("credit", True)
            entry = {"label": label, "heading": clip.get("heading") or label.replace("_", " ").title(),
                     "start": clip["start"], "end": clip["end"], "title": title, "hashtags": tags,
                     "creator": src.get("creator"), "channel_url": src.get("channel_url"),
                     "video_url": metadata_generator.timestamp_link(src, clip["start"]) if src.get("url") else None,
                     "show_credit": show_credit,
                     "music_attribution": music.get("attribution") if music.get("used") else None}
            entry["excerpt"] = clip.get("excerpt")
            entry["description"] = metadata_generator.description_with_credit(story, entry, src)
            transformation = {"captions": bool(cap_info and cap_info["events"]), "vertical_reframe": True,
                              "pause_removal": edit["removed_seconds"] > 0.3,
                              "zoom_emphasis": bool(edit["zoom_events"]),
                              "voiceover_commentary": bool(clip.get("has_commentary"))}
            risk = policy_checker.assess_clip(
                clip_range=(clip["start"], clip["end"]), output_duration=edit["output_duration"], words=edit["words"],
                audio=analysis["audio"], source=src, template_id=template["id"], music=music, title=title,
                description=entry["description"], hashtags=tags, extra_terms=cfg.get("policy_extra_terms"),
                tmap=edit["tmap"], transformation=transformation, same_day_count=same_day)
            # render + validate with fallback ladder
            attempts, final, validation, rinfo = [], None, None, None
            max_attempts = min(int(cfg["max_render_attempts"]), len(video_renderer.PROFILES))
            for n, profile in enumerate(video_renderer.PROFILES[:max_attempts], 1):
                if profile["zoom"] and not edit["zoom_expr"] and n > 1:
                    continue
                self.store.mark_rendering(src["video_id"], clip_id, n)
                try:
                    rinfo = video_renderer.render(source_path=source_path, source_start=source_start, meta=meta, edit=edit, layout=layout,
                                                  captions_path=str(cap_path) if cap_path else None, tmp_dir=jdir,
                                                  out_w=self.out_w, out_h=self.out_h,
                                                  cfg={**cfg, "_sfx_gain_db": sfx_gain}, music=music,
                                                  profile=profile, name=clip_id, sfx=sfx)
                except RenderError as exc:
                    attempts.append({"profile": profile["name"], "error": exc.message[-400:]})
                    continue
                validation = quality_validator.validate(rinfo["path"], width=self.out_w, height=self.out_h,
                                                        expected_duration=edit["output_duration"],
                                                        expect_audio=meta["has_audio"], captions=cap_info)
                attempts.append({"profile": profile["name"], "passed": validation["passed"],
                                 "failed": validation["failed"]})
                if validation["passed"]:
                    final = rinfo
                    break
                Path(rinfo["path"]).unlink(missing_ok=True)
            if not final:
                raise ValidationFailed(f"Clip failed after {len(attempts)} attempt(s): {attempts}",
                                       "See the attempts list; the clip was not saved or marked as used.")
            # move into the date folder (never overwrite), then metadata, then history
            index = metadata_generator.next_index(folder)
            index, filename = metadata_generator.allocate_filename(folder, index, label)
            dest = folder / filename
            staging = folder / f".{filename}.part"
            shutil.move(final["path"], staging)
            os.replace(staging, dest)
            entry["filename"] = filename
            entry["notes"] = self._publishing_notes(risk, layout, edit)
            used_fx = [e for e in sfx if final["profile"] == "full"]
            if used_fx:
                entry["notes"].append("Sound effects: " + "; ".join(
                    f"{e['kind']} at {e['t']:.1f}s ({e['source']}: {e['name']})" for e in used_fx))
            metadata_generator.upsert_metadata(folder, index, entry)
            self.store.mark_completed(src["video_id"], clip_id, filename, str(dest), title=title,
                                      output_duration=edit["output_duration"], risk=risk["overall_risk"])
            upscaled = layout["upscale_factor"] > 1.05
            res = {**base, "status": "completed", "index": index, "filename": filename, "output_path": str(dest),
                   "output_duration": edit["output_duration"], "removed_pause_seconds": edit["removed_seconds"],
                   "title": title, "hashtags": tags, "metadata_source": meta_src, "layout": layout["mode"],
                   "zoom_events": len(edit["zoom_events"]) if final["profile"] == "full" else 0,
                   "captions": cap_info and {k: cap_info[k] for k in ("preset", "events", "position_y", "font")},
                   "resolution": f"{self.out_w}x{self.out_h}",
                   "resolution_note": (f"Upscaled ~{layout['upscale_factor']:.2f}x from the source crop; "
                                       f"{self.out_w}x{self.out_h} output but NOT native 4K detail."
                                       if upscaled else "Native resolution (no upscaling)."),
                   "music": {k: music[k] for k in ("used", "reason") if k in music},
                   "sound_effects": [{k: e[k] for k in ("kind", "t", "why", "name", "source", "license")}
                                     for e in sfx if final["profile"] == "full"],
                   "risk": {"overall": risk["overall_risk"],
                            "items": [f"[{r['level']}] {r['category']}: {r['detail']}" for r in risk["risks"]]},
                   "validation": {"passed": True, "warnings": validation["warnings"], "attempts": attempts},
                   "render_profile": final["profile"], "render_seconds": final["seconds"]}
            if final["profile"] != "full":
                res["warnings"].append(f"Rendered with fallback profile '{final['profile']}' after earlier attempts failed.")
            atomic_write_json(jdir / f"{clip_id}.risk.json", risk)
            if section_path:
                Path(section_path).unlink(missing_ok=True)  # the Short is saved; free the disk space
            return res
        except SkillError as exc:
            self.store.mark_failed(src["video_id"], clip_id, exc.message)
            log(f"Clip {label} failed: {exc.message[:300]}")
            return {**base, "status": "failed", "error": exc.message, "hint": exc.hint}
        except Exception as exc:  # noqa: BLE001 - one bad clip must not kill the batch or poison history
            import traceback
            (jdir / f"{clip_id}.error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            if os.environ.get("YT_SHORTS_DEBUG") == "1":
                raise
            self.store.mark_failed(src["video_id"], clip_id, f"{type(exc).__name__}: {exc}")
            log(f"Clip {label} failed unexpectedly: {exc}")
            return {**base, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _publishing_notes(risk: dict, layout: dict, edit: dict) -> list[str]:
        notes = [f"Risk check: {risk['overall_risk']} (potential risks, not confirmed violations; YouTube decides)."]
        for r in risk["risks"]:
            if r["level"] in ("medium", "high"):
                notes.append(f"{r['category'].replace('_', ' ')}: {r['recommendation']}")
        if layout["upscale_factor"] > 1.05:
            notes.append("Video is upscaled to the output resolution; do not describe it as native 4K.")
        return notes[:6]

    def _summary(self, ctx, analysis, results, folder, job, preset) -> dict:
        src = ctx["source"]
        done = [r for r in results if r["status"] == "completed" and not r.get("skipped")]
        failed = [r for r in results if r["status"] == "failed"]
        rec = self.store.load(src["video_id"]) or {}
        return {
            "status": job["status"], "job_id": job["job_id"], "video_id": src["video_id"],
            "source": {k: src.get(k) for k in ("kind", "title", "url", "creator", "channel_url", "duration", "rights")},
            "template": ctx["template"]["id"], "caption_preset": preset,
            "output_folder": str(folder),
            "metadata_file": str(folder / metadata_generator.METADATA_FILENAME) if done else None,
            "generated": len(done), "failed": len(failed),
            "clips": results,
            "warnings": analysis.get("warnings", []) + ([f"{len(ctx.get('recovered') or [])} interrupted clip(s) "
                                                         "from an earlier run were not counted as used."]
                                                        if ctx.get("recovered") else []),
            "history": {"used_segments": rec.get("used_segments"),
                        "unused_seconds": round(sum(e - s for s, e in rec.get("unused_segments") or []), 1)},
            "policy_review_due": (_dt.date.today() - _dt.date.fromisoformat(
                policy_checker.POLICY_LAST_VERIFIED)).days > policy_checker.POLICY_REVIEW_DAYS,
        }


def audio_processor_decide(template, audio, clip, speech_cov, cfg, music_overlap):
    from scripts.audio_processor import decide_music
    return decide_music(template, audio, clip, speech_cov, cfg, music_overlap)


# ---------------------------------------------------------------------- hour by hour
def _window_size(cfg: dict) -> float:
    return max(60.0, float(cfg.get("hours_per_run") or 1) * 3600)


def next_window(store: HistoryStore, video_id: str, duration: float, cfg: dict) -> list[float] | None:
    """The first block of the video (1 hour by default) that hasn't been processed yet."""
    size, done = _window_size(cfg), store.windows_done(video_id)
    t = 0.0
    while t < duration - 1:
        w = [round(t, 3), round(min(duration, t + size), 3)]
        if not any(d[0] <= w[0] + 1 and w[1] - 1 <= d[1] for d in done):
            return w
        t += size
    return None


def _hour_by_hour(cfg: dict) -> bool:
    return bool(cfg.get("hour_by_hour", True)) and not cfg.get("analyze_range")


# ---------------------------------------------------------------------- high level entry points
def run_auto(value: str, rights: str | None, *, template_id: str | None = None, count: int | None = None,
             cfg_overrides: dict | None = None, subtitles: str | None = None, date: str | None = None,
             captions: bool = True, use_ai: bool = True, plan_clips: list[dict] | None = None,
             creator: str | None = None, channel_url: str | None = None, source_url: str | None = None,
             title: str | None = None, caption_preset: str | None = None, dry_run: bool = False) -> dict:
    cfg = load_config(cfg_overrides)
    pipe = Pipeline(cfg)
    count = int(count or cfg["default_count"])
    if count < 1:
        raise InputError("--count must be at least 1.")
    ctx = pipe.prepare(value, rights, template_id, creator=creator, channel_url=channel_url,
                       source_url=source_url, title=title)
    vid, dur = ctx["source"]["video_id"], ctx["meta"]["duration"]
    window = None
    if _hour_by_hour(cfg) and dur > 0:
        if plan_clips:
            # agent plan: analyse just the block the clips came from
            size = _window_size(cfg)
            lo = min(c["start"] for c in plan_clips)
            hi = max(c["end"] for c in plan_clips)
            window = [round(lo // size * size, 3), round(min(dur, (hi // size + 1) * size), 3)]
        else:
            window = next_window(pipe.store, vid, dur, cfg)
            # every hour done: continue with whatever unused footage is left anywhere in the video
    while True:
        if window:
            pipe.cfg["analyze_range"] = window
            log(f"Working on {fmt_ts(window[0])}-{fmt_ts(window[1])} of {fmt_ts(dur)} "
                f"({count} Short(s) from this part)")
        analysis = pipe.analyze(ctx, subtitles=subtitles, count=count)
        clips, sel, warnings = pipe.select(ctx, analysis, count, plan_clips=plan_clips, use_ai=use_ai)
        analysis["warnings"] += warnings
        if clips or dry_run or not window or plan_clips:
            break
        # nothing usable in this hour: mark it and move on to the next one
        pipe.store.mark_window_done(vid, *window)
        window = next_window(pipe.store, vid, dur, cfg)
        if window is None:
            pipe.cfg["analyze_range"] = None
            analysis = pipe.analyze(ctx, subtitles=subtitles, count=count)
            clips, sel, warnings = pipe.select(ctx, analysis, count, plan_clips=plan_clips, use_ai=use_ai)
            analysis["warnings"] += warnings
            break
    if window:
        analysis["warnings"].append(f"Hour-by-hour: this run used {fmt_ts(window[0])}-{fmt_ts(window[1])}. "
                                    "Ask for more Shorts to continue with the next part.")
    if dry_run:
        return {"status": "dry_run", "video_id": ctx["source"]["video_id"], "template": ctx["template"]["id"],
                "selected": clips, "candidates": sel["candidates"], "warnings": analysis["warnings"]}
    if not clips:
        return {"status": "nothing_to_do", "video_id": ctx["source"]["video_id"],
                "warnings": analysis["warnings"] + ["No unused moments meet the template's minimum length."],
                "history": {"used_segments": pipe.store.used_segments(ctx["source"]["video_id"])}}
    result = pipe.produce(ctx, analysis, clips, date=date, output_root=cfg["output_root"], captions=captions,
                          caption_preset=caption_preset)
    if window and result.get("generated"):
        pipe.store.mark_window_done(vid, *window)
        nxt = next_window(pipe.store, vid, dur, cfg)
        result["window"] = {"processed": f"{fmt_ts(window[0])} - {fmt_ts(window[1])}",
                            "next": f"{fmt_ts(nxt[0])} - {fmt_ts(nxt[1])}" if nxt else None}
    return result


def analyze_only(value: str, rights: str | None, *, template_id: str | None = None, count: int | None = None,
                 cfg_overrides: dict | None = None, subtitles: str | None = None, **src_kw) -> dict:
    """For agent-driven runs: returns ranked candidates (unused footage only) with excerpts."""
    cfg = load_config(cfg_overrides)
    pipe = Pipeline(cfg)
    count = int(count or cfg["default_count"])
    ctx = pipe.prepare(value, rights, template_id, **src_kw)
    vid, dur = ctx["source"]["video_id"], ctx["meta"]["duration"]
    window = next_window(pipe.store, vid, dur, cfg) if _hour_by_hour(cfg) and dur > 0 else None
    while True:
        if window:
            pipe.cfg["analyze_range"] = window
            log(f"Working on {fmt_ts(window[0])}-{fmt_ts(window[1])} of {fmt_ts(dur)}")
        analysis = pipe.analyze(ctx, subtitles=subtitles, count=count)
        clips, sel, warnings = pipe.select(ctx, analysis, count, use_ai=False)
        if sel["candidates"] or not window:
            break
        pipe.store.mark_window_done(vid, *window)
        window = next_window(pipe.store, vid, dur, cfg)
        if window is None:
            pipe.cfg["analyze_range"] = None
            analysis = pipe.analyze(ctx, subtitles=subtitles, count=count)
            clips, sel, warnings = pipe.select(ctx, analysis, count, use_ai=False)
            break
    rec = pipe.store.load(ctx["source"]["video_id"]) or {}
    return {
        "status": "analyzed", "video_id": ctx["source"]["video_id"], "template": ctx["template"]["id"],
        "source": {k: ctx["source"].get(k) for k in ("kind", "title", "url", "creator", "channel_url", "duration")},
        "content_hint": analysis["visual"].get("content_hint"),
        "reaction_overlay_detected": (None if ctx.get("fast") else bool(analysis["visual"].get("reaction_overlay"))),
        "analysis_mode": "fast" if ctx.get("fast") else "full",
        "replay_heatmap": bool(analysis.get("heatmap")),
        "has_transcript": analysis["transcript"] is not None,
        "previously_completed": [{"range": f"{fmt_ts(c['start'])} - {fmt_ts(c['end'])}", "file": c["filename"],
                                  "date": c["processing_date"]} for c in rec.get("clips", [])
                                 if c["status"] == "completed"],
        "window": f"{fmt_ts(window[0])} - {fmt_ts(window[1])}" if window else None,
        "candidates": sel["candidates"], "suggested": [c["rank"] for c in sel["selected"]],
        "warnings": analysis["warnings"] + warnings,
        "next_step": "Write a plan JSON (see examples/example-workflow.md) and run: cli.py render --plan plan.json",
    }


def render_plan(plan_path: str, cfg_overrides: dict | None = None) -> dict:
    plan = read_json(Path(plan_path))
    if not plan or "input" not in plan or not plan.get("clips"):
        raise InputError(f"{plan_path} is not a valid plan.", "A plan needs 'input' and 'clips'.")
    for c in plan["clips"]:
        if "start" not in c or "end" not in c:
            raise InputError("Every plan clip needs start and end.")
        c["start"] = parse_ts(c["start"])
        c["end"] = parse_ts(c["end"])
        if c.get("slug") and not c.get("label"):
            c["label"] = c["slug"]
    overrides = dict(cfg_overrides or {})
    if plan.get("resolution"):
        overrides["resolution"] = plan["resolution"]
    if plan.get("output_root"):
        overrides["output_root"] = plan["output_root"]
    return run_auto(plan["input"], plan.get("rights"), template_id=plan.get("template"),
                    count=len(plan["clips"]), cfg_overrides=overrides, subtitles=plan.get("subtitles"),
                    date=plan.get("date"), captions=plan.get("captions", True), use_ai=False,
                    plan_clips=plan["clips"], creator=plan.get("creator"), channel_url=plan.get("channel_url"),
                    source_url=plan.get("source_url"), title=plan.get("title"),
                    caption_preset=plan.get("caption_preset"))


def resume(job_id: str | None = None, cfg_overrides: dict | None = None) -> dict:
    """Re-run unfinished clips of the most recent (or given) interrupted/partial job."""
    jobs = sorted((state_dir() / "work").glob("*/jobs/*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    target = None
    for j in jobs:
        data = read_json(j)
        if job_id and data.get("job_id") != job_id:
            continue
        if job_id or data.get("status") in (None, "partial", "failed"):
            target = (j, data)
            break
    if not target:
        return {"status": "nothing_to_resume", "message": "No interrupted or partial job found."}
    path, job = target
    pending = [c for c in job["clips"] if c.get("status") != "completed"]
    if not pending:
        return {"status": "nothing_to_resume", "job_id": job["job_id"], "message": "All clips already completed."}
    cfg = load_config({**(cfg_overrides or {}), "output_root": job.get("output_root")})
    pipe = Pipeline(cfg)
    ctx = pipe.prepare(job["input"], job["rights"], job["template"], creator=job.get("creator"),
                       channel_url=job.get("channel_url"), title=job.get("title"), remember_template=False)
    analysis = pipe.analyze(ctx, count=len(pending))
    # previously failed/interrupted entries are re-attempted; check they don't now collide with used footage
    used = pipe.store.used_segments(ctx["source"]["video_id"])
    clean, warnings = clip_selector.validate_plan_clips(pending, ctx["meta"]["duration"], used, ctx["template"])
    analysis["warnings"] += warnings
    for c in job["clips"]:
        if c.get("status") != "completed":
            c["status"] = "pending"
    atomic_write_json(path, job)
    return pipe.produce(ctx, analysis, clean, date=job["date"], output_root=job["output_root"],
                        job_id=job["job_id"])


def doctor() -> dict:
    import scripts as _pkg
    report = {"name": _pkg.__title__, "version": _pkg.__version__, "author": _pkg.__author__}
    for b in ("ffmpeg", "ffprobe", "yt-dlp"):
        report[b] = bool(shutil.which(b))
    for mod in ("cv2", "numpy", "faster_whisper", "whisper", "jsonschema"):
        try:
            __import__(mod)
            report[mod] = True
        except ImportError:
            report[mod] = False
    if report["ffmpeg"]:
        import subprocess
        filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        report["ffmpeg_libass"] = " ass " in filters
        report["ffmpeg_zoompan"] = " zoompan " in filters
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        report["libx264"] = "libx264" in enc
    report["state_dir"] = str(state_dir())
    report["ready"] = all(report.get(k) for k in ("ffmpeg", "ffprobe", "cv2", "numpy", "ffmpeg_libass", "libx264"))
    report["transcription"] = transcription.available_backend() or "none (captions disabled unless --subtitles)"
    report["youtube_input"] = "available" if report["yt-dlp"] else "unavailable (pip install yt-dlp)"
    return report


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
