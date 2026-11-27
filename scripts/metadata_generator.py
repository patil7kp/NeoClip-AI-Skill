"""Date-wise output folders and the single YOUTUBE_METADATA.md per date.

Output layout (nothing else is ever written there):
    <output_root>/YYYY-MM-DD/NN_descriptive_name.mp4
    <output_root>/YYYY-MM-DD/YOUTUBE_METADATA.md
Numbering continues across sessions on the same date (never overwrites). The metadata file is
updated in place: new Shorts are appended; re-running a Short replaces only its own block.

Titles/descriptions should normally be written by the agent (it has the transcript and context)
and passed in the plan. The heuristic fallbacks here keep fully-automatic runs usable and are
marked in the processing result as `metadata_source: "heuristic"`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import atomic_write_text, fmt_ts, slugify

METADATA_FILENAME = "YOUTUBE_METADATA.md"
HEADER = ("# YouTube Shorts Metadata\n\n"
          "Copy the Title and the Description of each Short straight into YouTube. "
          "Publishing Notes are for you, not for the description.\n")
STOPWORDS = set("""a an the and or but if then so to of in on at for with from by is are was were be been being it
its this that these those i you he she we they me him her us them my your our their what which who whom
whose when where why how all any both each few more most other some such no nor not only own same than too
very can will just don should now yeah like okay oh um uh gonna wanna got get know think right really one
there here about out up down off over again also back well even going come want say said thing things do did
does done have has had lets let watching watch today welcome everyone guys video thanks thank much whole im i'm it's that's you're we're they're dont can't cant didn't isn't wasn't""".split())


# --------------------------------------------------------------------------- folders + names
def date_folder(output_root: Path, date: str) -> Path:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError(f"date must be YYYY-MM-DD, got {date}")
    folder = Path(output_root).expanduser() / date
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def next_index(folder: Path) -> int:
    nums = [int(m.group(1)) for p in folder.glob("*.mp4") if (m := re.match(r"^(\d{2,3})_", p.name))]
    md = folder / METADATA_FILENAME
    if md.exists():
        nums += [int(n) for n in re.findall(r"^## (\d{2,3})_", md.read_text(encoding="utf-8"), re.M)]
    return max(nums, default=0) + 1


def allocate_filename(folder: Path, index: int, label: str) -> tuple[int, str]:
    slug = slugify(label, 40)
    while True:
        name = f"{index:02d}_{slug}.mp4"
        if not (folder / name).exists() and not any(folder.glob(f"{index:02d}_*.mp4")):
            return index, name
        index += 1


# --------------------------------------------------------------------------- heuristics
def keywords(text: str, n: int = 6) -> list[str]:
    counts: dict[str, int] = {}
    for w in re.findall(r"[A-Za-z][A-Za-z0-9']{3,}", text.lower()):
        if w not in STOPWORDS and "'" not in w:
            counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0])))[:n]]


def best_sentence(excerpt: str) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", excerpt) if len(s.strip()) > 8]
    if not sentences:
        return excerpt.strip()[:70]
    scored = sorted(sentences, key=lambda s: (-(("!" in s) + ("?" in s)), abs(len(s) - 50)))
    return scored[0]


def heuristic_title(clip: dict, source: dict) -> str:
    excerpt = clip.get("excerpt") or ""
    label = (clip.get("label") or "best moment").replace("_", " ")
    if excerpt:
        s = best_sentence(excerpt).strip(" .")
        s = s[:70].rsplit(" ", 1)[0] if len(s) > 70 else s
        title = f"“{s}”"
    else:
        title = label.title()
    who = source.get("creator")
    if who and len(title) + len(who) < 90:
        title += f" | {who}"
    return title[:100]


def heuristic_description(clip: dict, source: dict) -> str:
    excerpt = (clip.get("excerpt") or "").strip()
    what = (clip.get("label") or "moment").replace("_", " ")
    src_title = source.get("title") or "the full video"
    who = source.get("creator")
    article = "An" if what[:1].lower() in "aeiou" else "A"
    owner = f"{who}'s video " if who else ""
    lines = [f"{article} {what} from {owner}\u201c{src_title}\u201d."]
    if excerpt:
        quote = excerpt[:400].rsplit(" ", 1)[0] + ("\u2026" if len(excerpt) > 400 else "")
        lines.append(f"What happens: {quote}")
    return "\n\n".join(lines)


def topic_keywords(entry: dict, source: dict, limit: int = 10) -> list[str]:
    """Natural related keywords: creator, video topic, tags and words from the moment (no stuffing)."""
    out: list[str] = []
    for k in ([source.get("creator")] + list(source.get("tags") or [])[:6] + list(source.get("categories") or [])[:2]
              + keywords((entry.get("title") or "") + " " + (entry.get("excerpt") or ""), 5)):
        if k and str(k).lower() not in [o.lower() for o in out]:
            out.append(str(k))
    return out[:limit]


def build_hashtags(clip: dict, source: dict, template: dict, limit: int = 6) -> list[str]:
    tags = ["#shorts"]
    for t in template.get("metadata", {}).get("base_hashtags", []):
        tags.append(t if t.startswith("#") else f"#{t}")
    if source.get("creator") and template.get("metadata", {}).get("creator_hashtag", True):
        tags.append("#" + re.sub(r"[^A-Za-z0-9]", "", source["creator"]).lower())
    for t in (source.get("tags") or [])[:5]:
        tags.append("#" + re.sub(r"[^A-Za-z0-9]", "", t).lower())
    for k in keywords((clip.get("title") or "") + " " + (clip.get("excerpt") or ""), 4):
        tags.append("#" + re.sub(r"[^a-z0-9]", "", k))
    out = []
    for t in tags:
        if len(t) > 2 and t.lower() not in [o.lower() for o in out]:
            out.append(t.lower() if t != "#shorts" else t)
    return out[:limit]


def normalize_hashtags(tags: list[str]) -> list[str]:
    out = []
    for t in tags:
        t = "#" + re.sub(r"[^\w]", "", t.lstrip("#"))
        if len(t) > 1 and t.lower() not in [o.lower() for o in out]:
            out.append(t)
    if "#shorts" not in [o.lower() for o in out]:
        out.insert(0, "#shorts")
    return out


# --------------------------------------------------------------------------- markdown
def _link(url: str | None) -> str | None:
    return f"[{url}]({url})" if url else None


def timestamp_link(source: dict, start: float) -> str | None:
    from scripts.source_input import canonical_youtube_url, parse_youtube_id
    url = source.get("url")
    yid = parse_youtube_id(url) if url else None
    if yid:
        return f"{canonical_youtube_url(yid)}&t={int(start)}s"
    return url


def _plain(text: str) -> str:
    """Title/description must paste cleanly into YouTube: no code-fence backticks inside."""
    return text.replace("`", "'").strip()


def render_entry(index: int, entry: dict) -> str:
    """One Short: filename heading, Title (copy block), Description (copy block), Publishing Notes."""
    notes = [f"Original timestamp: {fmt_ts(entry['start'])} - {fmt_ts(entry['end'])}"] + list(entry.get("notes") or [])
    out = [f"## {entry['filename']}", "",
           "**Title**", "```text", _plain(entry["title"]), "```", "",
           "**Description**", "```text", _plain(entry["description"]), "```", "",
           "**Publishing Notes**"] + [f"- {n}" for n in notes] + ["", "---", ""]
    return "\n".join(out)


def description_with_credit(desc: str, entry: dict, source: dict | None = None) -> str:
    """Viewer-facing description, plain text: the story, related keywords, creator credit with plain
    links, and the hashtags as the last line. Ready to paste into YouTube."""
    parts = [desc.strip()]
    kws = topic_keywords(entry, source or {}) if source is not None else []
    if kws:
        parts.append("Related: " + ", ".join(kws))
    if entry.get("show_credit"):
        credit = []
        if entry.get("creator"):
            credit.append(f"Original creator: {entry['creator']}")
        if entry.get("channel_url"):
            credit.append(f"Channel: {entry['channel_url']}")
        if entry.get("video_url"):
            credit.append(f"Full video: {entry['video_url']}")
        if credit:
            parts.append("\n".join(credit))
    if entry.get("music_attribution"):
        parts.append(f"Music: {entry['music_attribution']}")
    parts.append(" ".join(entry["hashtags"]))
    return "\n\n".join(parts)


def upsert_metadata(folder: Path, index: int, entry: dict) -> Path:
    md = folder / METADATA_FILENAME
    text = md.read_text(encoding="utf-8") if md.exists() else HEADER + "\n"
    if not text.startswith(HEADER):
        text = HEADER + "\n" + text
    block = render_entry(index, entry)
    pattern = re.compile(rf"^## {re.escape(entry['filename'])}\n.*?^---\n\n?", re.M | re.S)
    if pattern.search(text):
        text = pattern.sub(lambda _: block, text, count=1)
    else:
        if not text.endswith("\n\n"):
            text = text.rstrip("\n") + "\n\n"
        text += block
    atomic_write_text(md, text)
    return md


def parse_metadata(md: Path) -> list[dict]:
    """Read back entries (used by tests and by `history` reconciliation)."""
    if not md.exists():
        return []
    entries = []
    for m in re.finditer(r"^## ((\d+)_[^\n]+\.mp4)\n.*?^- Original timestamp: ([\d:]+) - ([\d:]+)",
                         md.read_text(encoding="utf-8"), re.M | re.S):
        entries.append({"index": int(m.group(2)), "filename": m.group(1), "start": m.group(3), "end": m.group(4)})
    return entries
