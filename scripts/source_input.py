"""Input handling: YouTube URLs and local files -> a normalized `source` dict.

A source dict always has: kind, video_id, title, duration, local_path (once available),
url, creator, channel_url, rights. The video_id is the stable key for timestamp history:
  * YouTube: "yt-<11 char id>"  (same video via watch?v=, youtu.be, /shorts/, /live/ -> same id)
  * Local:   "local-<16 hex>"   (content fingerprint: size + head/tail sha256, so renames still match)
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts.common import (InputError, RightsError, SourceUnavailableError, UnsupportedFormatError,
                            log, require_binary, run)

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
RIGHTS_VALUES = {
    "own": "You created this video / own the channel.",
    "permission": "The rights holder gave you written permission to clip it.",
    "licensed": "You hold a license that covers editing and republishing.",
    "creative-commons": "The video is CC-BY (or similar) and you will follow its attribution terms.",
    "public-domain": "The work is in the public domain.",
    "user-responsible": "Not stated. The user is responsible for having the rights (default).",
}
DEFAULT_RIGHTS = "user-responsible"
_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
             "youtu.be", "www.youtube-nocookie.com", "youtube-nocookie.com"}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


# --------------------------------------------------------------------------- rights
def check_rights(rights: str | None) -> str:
    """No question is asked: without a value the user is responsible for having the rights, and the
    copyright risk notes in Publishing Notes stay on."""
    if not rights:
        return DEFAULT_RIGHTS
    rights = rights.strip().lower()
    if rights not in RIGHTS_VALUES:
        raise RightsError(f"Unknown rights value '{rights}'.",
                          f"Use one of: {', '.join(sorted(RIGHTS_VALUES))}.")
    return rights


# --------------------------------------------------------------------------- YouTube
def parse_youtube_id(url: str) -> str | None:
    """Return the 11-char video id, or None if `url` is not a YouTube video URL."""
    if not isinstance(url, str):
        return None
    candidate = url.strip()
    if not re.match(r"^https?://", candidate, re.I):
        if re.match(r"^(www\.|m\.)?(youtube\.com|youtu\.be)/", candidate, re.I):
            candidate = "https://" + candidate
        else:
            return None
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()
    if host not in _YT_HOSTS:
        return None
    vid = None
    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        vid = (parse_qs(parsed.query).get("v") or [None])[0]
    else:
        m = re.match(r"^/(shorts|live|embed|v)/([^/?#]+)", parsed.path)
        if m:
            vid = m.group(2)
    return vid if vid and _ID_RE.match(vid) else None


def is_youtube_url(value: str) -> bool:
    return parse_youtube_id(value) is not None


def canonical_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


_YTDLP_ERRORS = [
    (r"Private video", "The video is private."),
    (r"members-only|Join this channel", "The video is members-only."),
    (r"Sign in to confirm your age|age-restricted", "The video is age-restricted and needs a signed-in session."),
    (r"not available in your country|geo", "The video is not available in this region."),
    (r"Video unavailable|This video has been removed|does not exist", "The video is unavailable or was removed."),
    (r"live event will begin|Premieres in", "The video is an upcoming live stream/premiere."),
    (r"HTTP Error 429|Too Many Requests", "YouTube is rate-limiting requests from this network."),
    (r"Sign in to confirm you.re not a bot", "YouTube requires sign-in to confirm this is not a bot."),
]


def _classify_ytdlp_error(stderr: str) -> SourceUnavailableError:
    for pattern, msg in _YTDLP_ERRORS:
        if re.search(pattern, stderr, re.I):
            return SourceUnavailableError(msg, "Use a video you can access, or provide a local file you "
                                               "have rights to. This skill does not bypass access controls.")
    return SourceUnavailableError(f"Could not read the YouTube video: {stderr.strip()[-400:]}",
                                  "Check the URL and your network, update yt-dlp (pip install -U yt-dlp), "
                                  "or provide a local file.")


def youtube_metadata(url: str) -> dict:
    vid = parse_youtube_id(url)
    if not vid:
        raise InputError(f"'{url}' is not a valid YouTube video URL.",
                         "Use a link like https://www.youtube.com/watch?v=XXXXXXXXXXX or https://youtu.be/XXXXXXXXXXX")
    require_binary("yt-dlp")
    proc = run(["yt-dlp", "-J", "--no-playlist", "--skip-download", "--no-warnings",
                canonical_youtube_url(vid)], timeout=120, check=False)
    if proc.returncode != 0:
        raise _classify_ytdlp_error(proc.stderr.decode("utf-8", "replace"))
    info = json.loads(proc.stdout)
    if info.get("is_live"):
        raise SourceUnavailableError("The video is currently live.", "Wait until the stream VOD is available.")
    return {
        "kind": "youtube",
        "video_id": f"yt-{vid}",
        "youtube_id": vid,
        "url": canonical_youtube_url(vid),
        "title": info.get("title") or vid,
        "creator": info.get("channel") or info.get("uploader"),
        "channel_url": info.get("channel_url") or info.get("uploader_url"),
        "duration": float(info.get("duration") or 0),
        "upload_date": info.get("upload_date"),
        "width": info.get("width"),
        "height": info.get("height"),
        "fps": info.get("fps"),
        "tags": (info.get("tags") or [])[:30],
        "categories": info.get("categories") or [],
        "description_excerpt": (info.get("description") or "")[:600],
        "license": info.get("license"),
        "age_limit": info.get("age_limit") or 0,
        "has_chapters": bool(info.get("chapters")),
        "chapters": [{"start": c.get("start_time"), "end": c.get("end_time"), "title": c.get("title")}
                     for c in (info.get("chapters") or [])],
        # "Most replayed" graph (only on some videos): [{start, end, value 0..1}]
        "heatmap": [{"start": float(h.get("start_time") or 0), "end": float(h.get("end_time") or 0),
                     "value": float(h.get("value") or 0)} for h in (info.get("heatmap") or [])
                    if h.get("end_time") is not None],
        "subtitle_langs": sorted((info.get("subtitles") or {}).keys()),
        "auto_caption_langs": sorted((info.get("automatic_captions") or {}).keys()),
        "language": info.get("language"),
    }


def download_youtube(source: dict, dest_dir: Path, max_height: int = 2160) -> Path:
    """Download into the INTERNAL work dir (never into the output folder). Reuses a finished download."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for existing in dest_dir.glob("source.*"):
        if existing.suffix in SUPPORTED_EXTENSIONS and existing.stat().st_size > 0:
            log(f"Reusing downloaded source {existing.name}")
            return existing
    fmt = f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b"
    log(f"Downloading {source['url']} (<= {max_height}p) to the internal work folder ...")
    proc = run(["yt-dlp", "--no-playlist", "--no-warnings", "-f", fmt, "--merge-output-format", "mp4",
                "--continue", "-o", str(dest_dir / "source.%(ext)s"), source["url"]],
               timeout=None, check=False)
    if proc.returncode != 0:
        raise _classify_ytdlp_error(proc.stderr.decode("utf-8", "replace"))
    files = [p for p in dest_dir.glob("source.*") if p.suffix in SUPPORTED_EXTENSIONS]
    if not files:
        raise SourceUnavailableError("Download finished but no video file was produced.")
    return files[0]


# --------------------------------------------------------------------------- fast YouTube path
# Instead of downloading the whole (often multi-GB) video, the fast path fetches:
#   1. metadata + "most replayed" heatmap + chapters      (no download)
#   2. YouTube captions as the transcript                 (a few KB)
#   3. audio only, for loudness / pause analysis           (about 0.5 MB per minute)
#   4. only the chosen clip ranges, at full quality        (one short section per Short)
def _pick_sub_lang(langs: list[str], preferred: str | None, original: str | None) -> str | None:
    wanted = [x for x in (preferred, original) if x] + ["en", "en-US", "en-GB"]
    for w in wanted:
        for cand in (f"{w}-orig", w):
            if cand in langs:
                return cand
    for w in wanted:  # e.g. "en" matches "en-IN"
        for lang in langs:
            if lang.split("-")[0] == w.split("-")[0]:
                return lang
    origs = [x for x in langs if x.endswith("-orig")]
    return origs[0] if origs else None


def download_youtube_subtitles(source: dict, dest_dir: Path, language: str | None = None) -> Path | None:
    """Fetch the video's own captions (manual first, then auto-generated). Returns a .vtt path or None."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for existing in sorted(dest_dir.glob("subs.*.vtt")):
        if existing.stat().st_size > 0:
            return existing
    plans = [("--write-subs", source.get("subtitle_langs") or []),
             ("--write-auto-subs", source.get("auto_caption_langs") or [])]
    for flag, langs in plans:
        lang = _pick_sub_lang(langs, language, source.get("language"))
        if not lang:
            continue
        log(f"Fetching YouTube captions ({'auto-generated' if 'auto' in flag else 'uploaded'}, {lang}) ...")
        proc = run(["yt-dlp", "--no-playlist", "--no-warnings", "--skip-download", flag, "--sub-langs", lang,
                    "--sub-format", "vtt", "-o", str(dest_dir / "subs.%(ext)s"), source["url"]],
                   timeout=180, check=False)
        files = [p for p in dest_dir.glob("subs.*.vtt") if p.stat().st_size > 0]
        if proc.returncode == 0 and files:
            return files[0]
    return None


AUDIO_FORMAT = "wa[abr>=32]/ba[abr<=96]/wa/ba"


def youtube_stream_info(source: dict) -> dict:
    """Direct stream address for the audio track (no file is downloaded). Cached in the source dict; the
    address expires after a few hours, so it is looked up again when a stream fails."""
    if source.get("_stream") and not source.get("_stream_stale"):
        return source["_stream"]
    proc = run(["yt-dlp", "--no-playlist", "--no-warnings", "-j", "-f", AUDIO_FORMAT, source["url"]],
               timeout=180, check=False)
    if proc.returncode != 0:
        raise _classify_ytdlp_error(proc.stderr.decode("utf-8", "replace"))
    info = json.loads(proc.stdout.decode("utf-8", "replace"))
    if not info.get("url"):
        raise SourceUnavailableError("No direct audio stream was offered for this video.")
    source["_stream"] = {"url": info["url"], "headers": info.get("http_headers") or {}}
    source["_stream_stale"] = False
    return source["_stream"]


def stream_youtube_audio_section(source: dict, dest_dir: Path, start: float, end: float) -> Path:
    """Read only [start, end] of the audio straight from the stream into a small file, via FFmpeg HTTP range
    requests. No yt-dlp download step and no full-length file. The audio is decoded and written as 16 kHz mono
    FLAC, so the start is exact (a stream copy would start at the nearest keyframe) and the file is small."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = f"audio_{start:.0f}_{end:.0f}"
    for existing in dest_dir.glob(stem + ".*"):
        if not existing.name.endswith((".part", ".ytdl")) and existing.stat().st_size > 0:
            return existing
    st = youtube_stream_info(source)
    headers = "".join(f"{k}: {v}\r\n" for k, v in st["headers"].items())
    out = dest_dir / f"{stem}.flac"
    tmp = dest_dir / f"{stem}.part.flac"
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y"]
    if headers:
        cmd += ["-headers", headers]
    cmd += ["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", st["url"],
            "-vn", "-sn", "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "flac", "-f", "flac", str(tmp)]
    proc = run(cmd, timeout=None, check=False)
    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        source["_stream_stale"] = True  # the address may have expired: look it up again next time
        tmp.unlink(missing_ok=True)
        raise SourceUnavailableError("Streaming the audio section failed.",
                                     (proc.stderr or b"").decode("utf-8", "replace")[-300:])
    tmp.replace(out)
    return out


def download_youtube_audio_section(source: dict, dest_dir: Path, start: float, end: float) -> Path:
    """Low-bitrate audio for [start, end] only (about 0.4 MB per minute)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = f"audio_{start:.0f}_{end:.0f}"
    for existing in dest_dir.glob(stem + ".*"):
        if not existing.name.endswith((".part", ".ytdl")) and existing.stat().st_size > 0:
            return existing
    proc = run(["yt-dlp", "--no-playlist", "--no-warnings", "-f", "wa[abr>=32]/ba[abr<=96]/wa/ba",
                "--download-sections", f"*{start:.3f}-{end:.3f}",
                "-o", str(dest_dir / f"{stem}.%(ext)s"), source["url"]], timeout=None, check=False)
    if proc.returncode != 0:
        raise _classify_ytdlp_error(proc.stderr.decode("utf-8", "replace"))
    files = [p for p in dest_dir.glob(stem + ".*") if not p.name.endswith((".part", ".ytdl"))]
    if not files:
        raise SourceUnavailableError("Audio download finished but no file was produced.")
    return files[0]


def local_audio_section(path: str, dest_dir: Path, start: float, end: float) -> Path:
    """Audio for [start, end] of a local file only (16 kHz mono FLAC), so long files are handled in batches."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"audio_{start:.0f}_{end:.0f}.flac"
    if out.exists() and out.stat().st_size > 0:
        return out
    tmp = out.with_suffix(".part.flac")
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
         "-i", str(path), "-vn", "-sn", "-ac", "1", "-ar", "16000", "-c:a", "flac", str(tmp)], timeout=None)
    tmp.replace(out)
    return out


def local_section(path: str, dest_dir: Path, start: float, end: float) -> Path:
    """Copy [start, end] of a local file without re-encoding (may start at the keyframe before `start`)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(path).suffix.lower() if Path(path).suffix.lower() in (".mp4", ".mov", ".mkv", ".m4v") else ".mkv"
    out = dest_dir / f"section_{start:.0f}_{end:.0f}{ext}"
    if out.exists() and out.stat().st_size > 0:
        return out
    tmp = dest_dir / f"section_{start:.0f}_{end:.0f}.part{ext}"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{start:.3f}", "-i", str(path),
         "-t", f"{end - start:.3f}", "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
         "-avoid_negative_ts", "make_zero", str(tmp)], timeout=None)
    tmp.replace(out)
    return out


def section_range(start: float, end: float, duration: float, pad: float = 3.0) -> tuple[float, float]:
    return max(0.0, round(start - pad, 3)), min(duration or end + pad, round(end + pad, 3))


def download_youtube_section(source: dict, dest_dir: Path, start: float, end: float,
                             max_height: int = 2160, exact: bool = False) -> Path:
    """Download only [start, end] (seconds) at full quality. By default the streams are copied (no extra
    encode, so no quality loss); `exact` re-encodes at the cut points instead."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = f"section_{start:.3f}_{end:.3f}".replace(".", "-")
    for existing in dest_dir.glob(stem + ".*"):
        if existing.suffix in SUPPORTED_EXTENSIONS and existing.stat().st_size > 0:
            return existing
    fmt = f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b"
    log(f"Downloading only {start:.1f}s - {end:.1f}s (<= {max_height}p) ...")
    proc = run(["yt-dlp", "--no-playlist", "--no-warnings", "-f", fmt, "--merge-output-format", "mp4",
                "--download-sections", f"*{start:.3f}-{end:.3f}",
                *(["--force-keyframes-at-cuts"] if exact else []),
                "-o", str(dest_dir / f"{stem}.%(ext)s"), source["url"]], timeout=None, check=False)
    if proc.returncode != 0:
        raise _classify_ytdlp_error(proc.stderr.decode("utf-8", "replace"))
    files = [p for p in dest_dir.glob(stem + ".*") if p.suffix in SUPPORTED_EXTENSIONS]
    if not files:
        raise SourceUnavailableError("Section download finished but no video file was produced.")
    return files[0]


# --------------------------------------------------------------------------- local
def fingerprint(path: Path, chunk: int = 4 * 1024 * 1024) -> str:
    size = path.stat().st_size
    h = hashlib.sha256(str(size).encode())
    with open(path, "rb") as fh:
        h.update(fh.read(chunk))
        if size > chunk:
            fh.seek(max(0, size - chunk))
            h.update(fh.read(chunk))
    return h.hexdigest()[:16]


def local_source(path_str: str) -> dict:
    path = Path(path_str).expanduser()
    if not path.exists():
        raise InputError(f"File not found: {path}")
    if not path.is_file():
        raise InputError(f"{path} is not a file.")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFormatError(
            f"Unsupported file type '{path.suffix}'.",
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}. Convert with: ffmpeg -i in.ext -c copy out.mp4")
    from scripts.video_analyzer import probe  # local import avoids a cycle
    meta = probe(path)
    return {
        "kind": "local",
        "video_id": f"local-{fingerprint(path)}",
        "url": None,
        "title": path.stem.replace("_", " ").strip() or path.name,
        "creator": None,
        "channel_url": None,
        "duration": meta["duration"],
        "local_path": str(path.resolve()),
        "probe": meta,
    }


def resolve_source(value: str, rights: str | None, *, creator: str | None = None,
                   channel_url: str | None = None, source_url: str | None = None,
                   title: str | None = None) -> dict:
    """Validate input + rights and return a source dict (no download yet for YouTube)."""
    rights = check_rights(rights)
    if is_youtube_url(value):
        src = youtube_metadata(value)
    elif re.match(r"^https?://", value.strip(), re.I):
        raise InputError("Only YouTube video URLs or local files are supported.",
                         "Download the video yourself (if you have the rights) and pass the file path.")
    else:
        src = local_source(value)
    src["rights"] = rights
    if creator:
        src["creator"] = creator
    if channel_url:
        src["channel_url"] = channel_url
    if source_url:
        src["url"] = source_url
    if title:
        src["title"] = title
    if src["duration"] <= 0:
        raise SourceUnavailableError("Could not determine the video duration.")
    return src
