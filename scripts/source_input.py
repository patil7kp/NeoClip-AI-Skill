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
}
_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
             "youtu.be", "www.youtube-nocookie.com", "youtube-nocookie.com"}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


# --------------------------------------------------------------------------- rights
def check_rights(rights: str | None) -> str:
    if not rights:
        raise RightsError(
            "Usage rights were not confirmed.",
            "Ask the user whether they own the video or have permission, then pass "
            f"--rights one of: {', '.join(sorted(RIGHTS_VALUES))}. Credit alone is not permission.")
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
