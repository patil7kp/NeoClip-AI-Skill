"""Speech-to-text with word timestamps (local Whisper; no paid API needed).

Backends, tried in order:
  1. faster-whisper   (recommended; CPU or CUDA)
  2. openai-whisper   (reference implementation)
  3. an existing subtitle file (.srt / .vtt) passed with --subtitles
If none is available, a TranscriptionError is raised and the pipeline continues without
captions/keyword cues, reporting a warning (it never pretends captions exist).

Transcript format:
  {"language": "en", "backend": "...", "model": "...",
   "segments": [{"start": s, "end": e, "text": "...", "words": [{"start","end","word","prob"}]}]}
Times are absolute seconds in the source video.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import TranscriptionError, log, parse_ts, run


def available_backend() -> str | None:
    try:
        import faster_whisper  # noqa: F401
        return "faster-whisper"
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return "openai-whisper"
    except ImportError:
        return None


def _extract_wav(src: Path, start: float, end: float, dest: Path) -> None:
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{start:.3f}", "-i", str(src),
         "-t", f"{end - start:.3f}", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
        timeout=600)


def _faster_whisper(path: Path, model: str, language: str | None, device: str, compute_type: str,
                    offset: float, beam_size: int = 5) -> tuple[list[dict], str]:
    from faster_whisper import WhisperModel
    if device == "auto":
        device = "cpu"
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                device = "cuda"
        except Exception:  # noqa: BLE001 - any CUDA probing failure -> CPU
            pass
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    m = _MODEL_CACHE.get((model, device, compute_type))
    if m is None:
        m = WhisperModel(model, device=device, compute_type=compute_type)
        _MODEL_CACHE[(model, device, compute_type)] = m
    segments, info = m.transcribe(str(path), language=language, word_timestamps=True, vad_filter=True,
                                  beam_size=beam_size, condition_on_previous_text=False)
    out = []
    for s in segments:
        words = [{"start": round(w.start + offset, 3), "end": round(w.end + offset, 3), "word": w.word.strip(),
                  "prob": round(float(w.probability), 3)} for w in (s.words or []) if w.word.strip()]
        out.append({"start": round(s.start + offset, 3), "end": round(s.end + offset, 3),
                    "text": s.text.strip(), "words": words})
    return out, info.language


def _openai_whisper(path: Path, model: str, language: str | None, offset: float) -> tuple[list[dict], str]:
    import whisper
    m = _MODEL_CACHE.get(("oa", model))
    if m is None:
        m = whisper.load_model(model)
        _MODEL_CACHE[("oa", model)] = m
    res = m.transcribe(str(path), language=language, word_timestamps=True, condition_on_previous_text=False)
    out = []
    for s in res.get("segments", []):
        words = [{"start": round(w["start"] + offset, 3), "end": round(w["end"] + offset, 3),
                  "word": w["word"].strip(), "prob": round(float(w.get("probability", 1.0)), 3)}
                 for w in s.get("words", []) if w["word"].strip()]
        out.append({"start": round(s["start"] + offset, 3), "end": round(s["end"] + offset, 3),
                    "text": s["text"].strip(), "words": words})
    return out, res.get("language", language or "unknown")


_MODEL_CACHE: dict = {}


def transcribe(path: Path | str, model: str = "small", language: str | None = None,
               ranges: list[list[float]] | None = None, device: str = "auto",
               compute_type: str = "auto", beam_size: int = 5) -> dict:
    """Transcribe the full file, or only `ranges` (absolute [start, end] seconds)."""
    path = Path(path)
    backend = available_backend()
    if backend is None:
        raise TranscriptionError("No speech-recognition backend is installed.",
                                 "pip install faster-whisper   (or pass --subtitles file.srt)")
    log(f"Transcribing with {backend} ({model}){' on ' + str(len(ranges)) + ' ranges' if ranges else ''} ...")
    segments: list[dict] = []
    lang = language or "unknown"
    try:
        if not ranges:
            if backend == "faster-whisper":
                segments, lang = _faster_whisper(path, model, language, device, compute_type, 0.0, beam_size)
            else:
                segments, lang = _openai_whisper(path, model, language, 0.0)
        else:
            with tempfile.TemporaryDirectory() as td:
                for i, (s, e) in enumerate(ranges):
                    wav = Path(td) / f"r{i}.wav"
                    _extract_wav(path, s, e, wav)
                    if backend == "faster-whisper":
                        segs, lang = _faster_whisper(wav, model, language, device, compute_type, s, beam_size)
                    else:
                        segs, lang = _openai_whisper(wav, model, language, s)
                    segments.extend(segs)
    except TranscriptionError:
        raise
    except Exception as exc:  # noqa: BLE001 - model download/decoding errors vary by backend
        raise TranscriptionError(f"Transcription failed: {exc}",
                                 "Check the model name/network for the first model download, try "
                                 "--whisper-model base, or pass --subtitles.") from exc
    segments.sort(key=lambda s: s["start"])
    return {"language": lang, "backend": backend, "model": model,
            "ranges": ranges or None, "segments": segments}


# --------------------------------------------------------------------------- subtitle files
_SRT_TIME = re.compile(r"(\d+:\d{2}:\d{2}[.,]\d{1,3})\s*-->\s*(\d+:\d{2}:\d{2}[.,]\d{1,3})")
_VTT_TIME = re.compile(r"((?:\d+:)?\d{2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d+:)?\d{2}:\d{2}[.,]\d{1,3})")


_INLINE_TS = re.compile(r"<(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{2}:\d{2}[.,]\d{3})>")


def parse_youtube_auto_vtt(text: str) -> list[dict] | None:
    """YouTube auto-captions carry per-word times (<00:00:01.230><c> word</c>) and repeat the previous
    line in every cue. Return de-duplicated segments with real word times, or None if not that format."""
    if not _INLINE_TS.search(text):
        return None
    segments = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        lines = [ln for ln in block.strip().split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            m = _VTT_TIME.search(ln)
            if not m:
                continue
            cs, ce = parse_ts(m.group(1).replace(",", ".")), parse_ts(m.group(2).replace(",", "."))
            for body in lines[i + 1:]:
                if not _INLINE_TS.search(body):
                    continue  # repeated line from the previous cue
                pieces = _INLINE_TS.split(body)
                words = []
                first = re.sub(r"<[^>]+>", "", pieces[0]).strip()
                for w in first.split():
                    words.append({"start": cs, "word": w})
                for k in range(1, len(pieces), 2):
                    t = parse_ts(pieces[k].replace(",", "."))
                    for w in re.sub(r"<[^>]+>", "", pieces[k + 1]).split():
                        words.append({"start": t, "word": w})
                for j, w in enumerate(words):
                    nxt = words[j + 1]["start"] if j + 1 < len(words) else ce
                    w["end"] = round(max(w["start"] + 0.05, min(nxt, w["start"] + 1.5)), 3)
                    w["start"] = round(w["start"], 3)
                    w["prob"] = 1.0
                if words:
                    segments.append({"start": words[0]["start"], "end": words[-1]["end"],
                                     "text": " ".join(w["word"] for w in words), "words": words})
            break
    return segments or None


def load_subtitles(path: Path | str) -> dict:
    """Parse .srt/.vtt into the transcript format. Word times are interpolated by character length,
    except YouTube auto-captions, which carry real per-word times."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    auto = parse_youtube_auto_vtt(text)
    if auto:
        return {"language": "unknown", "backend": "youtube-auto-captions", "model": None, "ranges": None,
                "segments": auto}
    segments = []
    blocks = re.split(r"\n\s*\n", text.replace("\r", ""))
    for block in blocks:
        lines = [ln for ln in block.strip().split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            m = _SRT_TIME.search(ln) or _VTT_TIME.search(ln)
            if m:
                s = parse_ts(m.group(1).replace(",", "."))
                e = parse_ts(m.group(2).replace(",", "."))
                body = " ".join(re.sub(r"<[^>]+>", "", x) for x in lines[i + 1:]).strip()
                if body and e > s and not (segments and segments[-1]["text"] == body
                                           and s - segments[-1]["end"] < 0.5):
                    segments.append({"start": s, "end": e, "text": body, "words": interpolate_words(body, s, e)})
                break
    if not segments:
        raise TranscriptionError(f"No cues found in subtitle file {path}.")
    return {"language": "unknown", "backend": "subtitle-file", "model": None, "ranges": None,
            "segments": segments}


def interpolate_words(text: str, start: float, end: float) -> list[dict]:
    tokens = text.split()
    if not tokens:
        return []
    total = sum(len(t) + 1 for t in tokens)
    t = start
    words = []
    for tok in tokens:
        d = (end - start) * (len(tok) + 1) / total
        words.append({"start": round(t, 3), "end": round(t + d, 3), "word": tok, "prob": 1.0})
        t += d
    return words


def all_words(transcript: dict | None, start: float = 0.0, end: float = float("inf")) -> list[dict]:
    if not transcript:
        return []
    return [w for s in transcript["segments"] for w in s.get("words", [])
            if w["end"] > start and w["start"] < end]


def text_in_range(transcript: dict | None, start: float, end: float) -> str:
    return " ".join(w["word"] for w in all_words(transcript, start, end)).strip()


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--model", default="small")
    ap.add_argument("--language")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    res = transcribe(args.file, args.model, args.language)
    out = json.dumps(res, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
