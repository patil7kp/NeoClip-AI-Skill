"""NeoClip-AI-Skill command-line entry point (Created by Kiran Patil - NeoClip-AI-Skill; © 2026 Kiran Patil. All Rights Reserved).

Command-line entry point: the one interface every AI agent (or a human) drives.

All commands print a single JSON document on stdout; progress goes to stderr.
Exit codes: 0 ok, 1 error, 3 partial success (some clips failed).

  python scripts/cli.py doctor
  python scripts/cli.py setup-models                     (optional YuNet face model)
  python scripts/cli.py templates list | show <id> | use <id> | set <id> key=value ... | reset <id>
  python scripts/cli.py inspect <url-or-file>
  python scripts/cli.py analyze <url-or-file> --rights own [--template gaming-reaction] [--count 3]
  python scripts/cli.py render --plan plan.json
  python scripts/cli.py run <url-or-file> --rights own [--template ...] [--count 3]
  python scripts/cli.py more <url-or-file> --rights own --count 2        (new moments only)
  python scripts/cli.py resume [--job JOB_ID]
  python scripts/cli.py history list | show <url-or-file-or-id>
  python scripts/cli.py clean <url-or-file-or-id>          (delete cached download/analysis)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import pipeline  # noqa: E402
from scripts.common import SkillError, safe_id, state_dir  # noqa: E402
from scripts.source_input import RIGHTS_VALUES  # noqa: E402


def _common(p: argparse.ArgumentParser, needs_rights: bool = True) -> None:
    p.add_argument("input", help="YouTube URL or local video file")
    if needs_rights:
        p.add_argument("--rights", choices=sorted(RIGHTS_VALUES),
                       help="Your basis for using this video (required). Credit alone is not permission.")
    p.add_argument("--template", help="gaming-reaction | podcast-conversation | funny-viral-moments | "
                                      "storytelling-commentary | minimal-professional (remembered)")
    p.add_argument("--count", type=int, help="number of Shorts (default 3)")
    p.add_argument("--resolution", help="output WxH, default 2160x3840 (4K vertical); 1080x1920 is faster")
    p.add_argument("--output-root", help="folder that holds the date folders (default ./YouTube_Shorts)")
    p.add_argument("--date", help="processing date folder YYYY-MM-DD (default today)")
    p.add_argument("--subtitles", help="use an existing .srt/.vtt instead of Whisper")
    p.add_argument("--whisper-model", help="tiny | base | small | medium | large-v3 (default small)")
    p.add_argument("--language", help="force transcription language, e.g. en, es, hi")
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--no-ai", action="store_true", help="ignore a configured ai.command")
    p.add_argument("--caption-preset", help="bold_pop | clean_pro | story | minimal (kept per project)")
    p.add_argument("--creator", help="original creator name (local files)")
    p.add_argument("--channel-url", help="original channel URL (local files)")
    p.add_argument("--source-url", help="original video URL (local files)")
    p.add_argument("--title", help="override source title")
    p.add_argument("--dry-run", action="store_true", help="select clips but do not render")
    p.add_argument("--range", dest="analyze_range", metavar="START-END",
                   help="only look for moments in this part, e.g. 2:00:00-5:30:00")
    p.add_argument("--transcribe", choices=["auto", "full", "candidates"],
                   help="Whisper the whole video (full) or only the strongest moments (candidates); "
                        "auto = full up to 3 hours")
    p.add_argument("--full-download", action="store_true",
                   help="YouTube: download the whole video first (slow; default fetches audio batches + clips)")
    p.add_argument("--youtube-captions", action="store_true",
                   help="YouTube: use the video's own captions instead of Whisper")
    p.add_argument("--workers", type=int, help="parallel downloads (default 3)")


def _parse_range(value: str | None) -> list[str] | None:
    if not value:
        return None
    if value.count("-") != 1:
        raise SystemExit("--range must look like START-END, e.g. 1:00:00-3:30:00")
    return [x.strip() for x in value.split("-")]


def _overrides(a) -> dict:
    return {"resolution": getattr(a, "resolution", None), "output_root": getattr(a, "output_root", None),
            "whisper_model": getattr(a, "whisper_model", None), "language": getattr(a, "language", None),
            "analyze_range": _parse_range(getattr(a, "analyze_range", None)),
            "transcribe_scope": getattr(a, "transcribe", None),
            "youtube_mode": "full" if getattr(a, "full_download", False) else None,
            "youtube_captions": True if getattr(a, "youtube_captions", False) else None,
            "download_workers": getattr(a, "workers", None)}


def _src_kw(a) -> dict:
    return {"creator": a.creator, "channel_url": a.channel_url, "source_url": a.source_url, "title": a.title}


def main(argv: list[str] | None = None) -> int:
    import scripts as _pkg
    ap = argparse.ArgumentParser(prog="neoclip", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=f"{_pkg.__title__} {_pkg.__version__}. Created by {_pkg.__author__}. {_pkg.__copyright__}")
    ap.add_argument("--version", action="version", version=f"{_pkg.__title__} {_pkg.__version__} by {_pkg.__author__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="check dependencies")
    sub.add_parser("setup-models", help="download the optional YuNet face model (better face tracking)")
    t = sub.add_parser("templates", help="list/show/use/customize templates")
    t.add_argument("action", choices=["list", "show", "use", "set", "reset"])
    t.add_argument("template_id", nargs="?")
    t.add_argument("settings", nargs="*")
    i = sub.add_parser("inspect", help="validate input and show metadata + history (no download)")
    i.add_argument("input")
    for name in ("analyze", "run", "more"):
        _common(sub.add_parser(name))
    r = sub.add_parser("render", help="render an agent-written plan.json")
    r.add_argument("--plan", required=True)
    r.add_argument("--resolution")
    r.add_argument("--output-root")
    rs = sub.add_parser("resume", help="finish an interrupted/partial job")
    rs.add_argument("--job")
    h = sub.add_parser("history")
    h.add_argument("action", choices=["list", "show"])
    h.add_argument("query", nargs="?")
    c = sub.add_parser("clean", help="delete cached download/analysis for a video (keeps history)")
    c.add_argument("query")
    a = ap.parse_args(argv)

    try:
        if a.cmd == "doctor":
            res = pipeline.doctor()
            print(pipeline.dumps(res))
            return 0 if res["ready"] else 1
        if a.cmd == "setup-models":
            from scripts.video_analyzer import download_face_model
            print(pipeline.dumps({"status": "ok", "face_model": str(download_face_model())}))
            return 0
        if a.cmd == "templates":
            return _templates(a)
        if a.cmd == "inspect":
            print(pipeline.dumps(_inspect(a.input)))
            return 0
        if a.cmd == "history":
            from scripts.timestamp_manager import main as hist_main
            return hist_main([a.action] + ([a.query] if a.query else []))
        if a.cmd == "clean":
            return _clean(a.query)
        if a.cmd == "analyze":
            res = pipeline.analyze_only(a.input, a.rights, template_id=a.template, count=a.count,
                                        cfg_overrides=_overrides(a), subtitles=a.subtitles, **_src_kw(a))
        elif a.cmd in ("run", "more"):
            res = pipeline.run_auto(a.input, a.rights, template_id=a.template, count=a.count or (2 if a.cmd == "more" else None),
                                    cfg_overrides=_overrides(a), subtitles=a.subtitles, date=a.date,
                                    captions=not a.no_captions, use_ai=not a.no_ai, caption_preset=a.caption_preset,
                                    dry_run=a.dry_run, **_src_kw(a))
        elif a.cmd == "render":
            res = pipeline.render_plan(a.plan, {"resolution": a.resolution, "output_root": a.output_root})
        elif a.cmd == "resume":
            res = pipeline.resume(a.job)
        else:  # pragma: no cover
            ap.error("unknown command")
            return 1
        print(pipeline.dumps(res))
        status = res.get("status")
        return 3 if status == "partial" else (1 if status == "failed" else 0)
    except SkillError as exc:
        print(pipeline.dumps({"status": "error", **exc.to_dict()}))
        return 1


def _templates(a) -> int:
    from scripts import templates_config as tc
    from scripts.config import load_preferences
    if a.action == "list":
        cur = load_preferences().get("template") or tc.DEFAULT_TEMPLATE
        print(pipeline.dumps({"templates": [{"id": t, "name": tc.load_template(t)["name"], "current": t == cur}
                                            for t in tc.list_templates()]}))
    elif a.action == "show":
        print(pipeline.dumps(tc.load_template(a.template_id)))
    elif a.action == "use":
        tc.remember_template(a.template_id)
        print(pipeline.dumps({"status": "ok", "template": a.template_id}))
    elif a.action == "set":
        print(pipeline.dumps(tc.customize_template(a.template_id, a.settings)))
    elif a.action == "reset":
        tc.reset_template(a.template_id)
        print(pipeline.dumps({"status": "ok", "reset": a.template_id}))
    return 0


def _inspect(value: str) -> dict:
    from scripts import source_input
    from scripts.timestamp_manager import HistoryStore, summarize
    if source_input.is_youtube_url(value):
        src = source_input.youtube_metadata(value)
    else:
        src = source_input.local_source(value)
    rec = HistoryStore().load(src["video_id"])
    return {"source": src, "history": summarize(rec) if rec else None,
            "rights_required": "Pass --rights (" + ", ".join(sorted(RIGHTS_VALUES)) + ") to process."}


def _clean(query: str) -> int:
    from scripts.timestamp_manager import HistoryStore
    from scripts.source_input import fingerprint, parse_youtube_id
    vid = None
    if parse_youtube_id(query):
        vid = f"yt-{parse_youtube_id(query)}"
    elif Path(query).expanduser().exists():
        vid = f"local-{fingerprint(Path(query).expanduser())}"
    else:
        rec = HistoryStore().find(query)
        vid = rec["video_id"] if rec else query
    wd = state_dir() / "work" / safe_id(vid)
    if wd.exists():
        shutil.rmtree(wd)
    print(pipeline.dumps({"status": "ok", "removed": str(wd), "history_kept": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
