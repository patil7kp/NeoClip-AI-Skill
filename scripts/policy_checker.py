"""YouTube policy & compliance RISK screening (heuristic, never a verdict).

What it does
  * Copyright / Content ID: flags possible music, third-party footage (rights basis), the
    > 1 minute Content ID blocking rule for Shorts, and low transformation.
  * Age restriction / advertiser-friendliness: transcript lexicon scan with timestamps
    (strong language, violence, sexual content, drugs, dangerous acts, self-harm, hate).
  * Reused / inauthentic content: monetization-related reuse risk and template repetition.
  * Metadata: misleading/clickbait patterns, ALL CAPS, hashtag counts, length limits.
What it does NOT do
  * It cannot see visual nudity/gore, recognise songs, or decide fair use. Those need human
    review (and Content ID itself) and are listed as "needs_human_review".
  * It does not guarantee approval, monetization, reach, or freedom from claims/strikes.
Final enforcement decisions belong to YouTube. The calling agent must re-check the official
pages in references/youtube-policies.md when `policy_review_due` is true.
"""
from __future__ import annotations

import datetime as _dt
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import fmt_ts, overlap

POLICY_LAST_VERIFIED = "2026-11-27"
POLICY_REVIEW_DAYS = 30
OFFICIAL_SOURCES = {
    "community_guidelines": "https://www.youtube.com/howyoutubeworks/policies/community-guidelines/",
    "age_restriction": "https://support.google.com/youtube/answer/2802167",
    "copyright": "https://support.google.com/youtube/answer/2797466",
    "content_id": "https://support.google.com/youtube/answer/2797370",
    "fair_use": "https://support.google.com/youtube/answer/9783148",
    "advertiser_friendly": "https://support.google.com/youtube/answer/6162278",
    "ypp_monetization_policies": "https://support.google.com/youtube/answer/1311392",
    "three_minute_shorts": "https://support.google.com/youtube/answer/15424877",
    "metadata_spam": "https://support.google.com/youtube/answer/2801973",
    "hashtags": "https://support.google.com/youtube/answer/6390658",
    "audio_library": "https://support.google.com/youtube/answer/3376882",
}

LEXICON: dict[str, dict] = {
    "strong_language": {"severity": "medium", "terms": [
        r"\bf+u+c+k\w*", r"\bmotherf\w*", r"\bsh[i1]t\w*", r"\bbullsh\w*", r"\bc+u+n+t\w*", r"\bb[i1]tch\w*",
        r"\bdick(head)?s?\b", r"\bpussy\b", r"\basshole\w*", r"\bwh[o0]re\w*"]},
    "mild_language": {"severity": "low", "terms": [r"\bdamn\w*", r"\bhell\b", r"\bcrap\b", r"\bass\b",
                                                  r"\bpiss\w*", r"\bbastard\w*"]},
    "violence": {"severity": "medium", "terms": [
        r"\bkill(ed|ing|s)?\b", r"\bmurder\w*", r"\bstab\w*", r"\bshoot(ing)?\b", r"\bshot (him|her|them)\b",
        r"\bblood(y)?\b", r"\bgore\b", r"\bbehead\w*", r"\btorture\w*", r"\bbeat (him|her|them) up\b"]},
    "sexual": {"severity": "high", "terms": [r"\bsex(ual|y)?\b", r"\bporn\w*", r"\bnude(s)?\b", r"\bnaked\b",
                                             r"\bhorny\b", r"\borgasm\w*", r"\bonlyfans\b"]},
    "drugs": {"severity": "medium", "terms": [r"\bcocaine\b", r"\bheroin\b", r"\bmeth\b", r"\bweed\b",
                                              r"\bget(ting)? high\b", r"\bdrunk\b", r"\bovered?ose\w*", r"\bmdma\b",
                                              r"\bvape\b"]},
    "dangerous_acts": {"severity": "high", "terms": [r"\bdon'?t try this\b", r"\bchallenge\b", r"\bset (it|myself) on fire\b",
                                                     r"\bjump(ed)? off\b", r"\bprank\w*", r"\bexplosi\w*",
                                                     r"\bchok(e|ing) challenge\b"]},
    "self_harm": {"severity": "high", "terms": [r"\bsuicid\w*", r"\bkill myself\b", r"\bself[- ]harm\w*",
                                                r"\bcut(ting)? myself\b"]},
    "hate_or_harassment": {"severity": "high", "terms": [r"\bretard\w*", r"\bnazi\w*", r"\bterroris\w*"]},
}
GAMING_CONTEXT_NOTE = ("Violence words in gameplay commentary are common; YouTube evaluates context "
                       "(realistic vs. game violence). Review the flagged moments rather than assuming a problem.")
CLICKBAIT = [r"you won'?t believe", r"\bgone wrong\b", r"\b(gone )?sexual\b", r"\bnot clickbait\b", r"\b100% real\b",
             r"\bshocking\b", r"\bmust watch\b", r"\bdoctors hate\b", r"\bfree (v-?bucks|robux|money)\b"]


def _mask(word: str) -> str:
    w = re.sub(r"[^\w']", "", word)
    return w[0] + "*" * max(1, len(w) - 2) + (w[-1] if len(w) > 2 else "") if w else word


def _compile(extra: dict | None):
    lex = {k: {"severity": v["severity"], "terms": list(v["terms"])} for k, v in LEXICON.items()}
    for cat, terms in (extra or {}).items():
        lex.setdefault(cat, {"severity": "medium", "terms": []})["terms"] += [re.escape(t) for t in terms]
    return {k: (v["severity"], [re.compile(t, re.I) for t in v["terms"]]) for k, v in lex.items()}


def scan_transcript(words: list[dict], start: float, end: float, extra_terms: dict | None = None,
                    output_offset_map=None) -> list[dict]:
    lex = _compile(extra_terms)
    flags = []
    # scan both single tokens and a sliding 4-word window for phrases
    toks = [w for w in words if w["end"] > start and w["start"] < end]
    for i, w in enumerate(toks):
        window = " ".join(x["word"] for x in toks[i:i + 4])
        for cat, (sev, pats) in lex.items():
            for p in pats:
                if " " in p.pattern:
                    m = p.match(window)          # phrase anchored at this word -> reported once
                else:
                    m = p.search(w["word"])
                if m:
                    t_out = output_offset_map(w["start"]) if output_offset_map else None
                    flags.append({"category": cat, "severity": sev, "source_time": fmt_ts(w["start"]),
                                  "source_seconds": round(w["start"], 2),
                                  "short_time": round(t_out, 2) if t_out is not None else None,
                                  "term": _mask(m.group(0))})
                    break
    dedup, seen = [], set()
    for f in flags:
        key = (f["category"], round(f["source_seconds"]))
        if key not in seen:
            seen.add(key)
            dedup.append(f)
    return dedup


def check_metadata(title: str, description: str, hashtags: list[str]) -> list[dict]:
    issues = []
    if len(title) > 100:
        issues.append({"field": "title", "level": "error", "issue": f"title is {len(title)} chars (YouTube max 100)"})
    letters = [c for c in title if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7 and len(letters) > 8:
        issues.append({"field": "title", "level": "warning", "issue": "mostly ALL CAPS reads as spammy"})
    if re.search(r"[!?]{3,}", title):
        issues.append({"field": "title", "level": "warning", "issue": "excessive punctuation"})
    for p in CLICKBAIT:
        if re.search(p, title, re.I) or re.search(p, description, re.I):
            issues.append({"field": "title/description", "level": "warning",
                           "issue": f"pattern '{p.strip(chr(92) + 'b')}' can be misleading/clickbait; make sure it matches the clip"})
    if len(description) > 5000:
        issues.append({"field": "description", "level": "error", "issue": "description exceeds 5000 chars"})
    if len(hashtags) > 15:
        issues.append({"field": "hashtags", "level": "error",
                       "issue": "more than 15 hashtags: YouTube ignores all hashtags on such videos"})
    elif len(hashtags) > 8:
        issues.append({"field": "hashtags", "level": "warning", "issue": "keep hashtags to the few most relevant (3-6)"})
    lex = _compile(None)
    for cat in ("strong_language", "sexual"):
        for p in lex[cat][1]:
            if p.search(title):
                issues.append({"field": "title", "level": "warning",
                               "issue": f"{cat.replace('_', ' ')} in the title raises age-restriction/ad-suitability risk"})
                break
    return issues


def assess_clip(*, clip_range: tuple[float, float], output_duration: float, words: list[dict],
                audio: dict | None, source: dict, template_id: str, music: dict | None,
                title: str = "", description: str = "", hashtags: list[str] | None = None,
                extra_terms: dict | None = None, tmap=None, transformation: dict | None = None,
                same_day_count: int = 0) -> dict:
    s, e = clip_range
    content_flags = scan_transcript(words, s, e, extra_terms, tmap.to_output if tmap else None)
    risks = []

    def add(category, level, detail, recommendation, kind="potential_risk"):
        risks.append({"category": category, "level": level, "kind": kind, "detail": detail,
                      "recommendation": recommendation})

    # --- copyright / Content ID
    rights = source.get("rights")
    music_hits = [m for m in (audio or {}).get("possible_music", []) if overlap((s, e), m) > 2]
    if music_hits:
        secs = sum(overlap((s, e), m) for m in music_hits)
        add("copyright_music", "high" if rights not in ("own", "licensed") else "medium",
            f"~{secs:.0f}s of this clip looks like it may contain music (heuristic: sustained tonal audio).",
            "Confirm the music is yours or licensed. If not, cut those seconds, or mute and use a verified "
            "YouTube Audio Library track. Third-party music is the most common Content ID trigger.")
    if output_duration > 60:
        add("copyright_shorts_over_60s", "medium" if (music_hits or rights not in ("own",)) else "low",
            f"Short is {output_duration:.0f}s. Shorts longer than 1 minute with an active Content ID claim are "
            "blocked globally (per YouTube Help, 3-minute Shorts).",
            "Keep it under 60 s when any third-party audio/video is present.")
    if rights in ("permission", "licensed", "creative-commons"):
        add("copyright_third_party", "medium",
            f"Footage is used on the basis of '{rights}'. Keep written proof; the original owner's Content ID "
            "may still claim it unless they whitelist your channel.",
            "Ask the rights holder to whitelist your channel; keep the permission/license on file.")
    if rights == "public-domain":
        add("copyright_third_party", "low", "Public-domain source. Restorations/compilations can still carry new rights.",
            "Verify the specific copy you used is public domain.")
    # --- reuse / inauthentic (monetization)
    if rights != "own":
        tr = transformation or {}
        added = [k for k, v in tr.items() if v]
        add("reused_content", "medium",
            "Clipping someone else's video is 'reused content' for YouTube Partner Program purposes unless it "
            "adds meaningful original commentary or education. Captions/reframing alone may not be enough. "
            f"Edits applied here: {', '.join(added) or 'none'}.",
            "Add your own voice-over commentary, analysis or narrative if you plan to monetize.")
    if same_day_count >= 10:
        add("inauthentic_content", "medium",
            f"{same_day_count} Shorts generated today with similar templating.",
            "Vary formats and add distinct commentary; mass-produced, templated uploads risk the "
            "inauthentic-content policy.")
    # --- age restriction / ad suitability
    by_cat: dict[str, list[dict]] = {}
    for f in content_flags:
        by_cat.setdefault(f["category"], []).append(f)
    for cat, items in by_cat.items():
        sev = items[0]["severity"]
        early = [f for f in items if f["short_time"] is not None and f["short_time"] <= 7]
        level = "high" if sev == "high" or len(items) >= 4 else ("medium" if sev == "medium" else "low")
        detail = f"{len(items)} {cat.replace('_', ' ')} cue(s) at " + ", ".join(f["source_time"] for f in items[:8])
        if early and cat in ("strong_language",):
            detail += " (some in the first seconds, which advertiser-friendly guidelines weigh more heavily)"
        rec = {"strong_language": "Bleep/mute the words (or trim) if you want broad ad suitability.",
               "mild_language": "Usually fine; avoid it in the title and opening.",
               "violence": "Check visuals: realistic/graphic violence may be age-restricted. " + GAMING_CONTEXT_NOTE,
               "sexual": "Review carefully; sexual content is a primary age-restriction trigger.",
               "drugs": "Avoid glorifying drug use; educational context helps.",
               "dangerous_acts": "Dangerous challenges/pranks can be removed or age-restricted; add context or skip.",
               "self_harm": "Sensitive topic: avoid sensational framing; consider skipping this moment.",
               "hate_or_harassment": "Review context; hateful or harassing content can be removed."}.get(cat, "Review.")
        add(f"age_or_ads_{cat}", level, detail, rec)
    if (source.get("age_limit") or 0) >= 18:
        add("age_restricted_source", "high", "The original video is age-restricted on YouTube.",
            "Expect the Short to need age restriction too; pick a different moment or source.")
    # --- metadata
    meta_issues = check_metadata(title, description, hashtags or [])
    for mi in meta_issues:
        add("metadata", "medium" if mi["level"] == "error" else "low", f"{mi['field']}: {mi['issue']}",
            "Edit the metadata before publishing.")
    if music and music.get("used"):
        add("music_license", "low", f"Background track '{music['track']['title']}' ({music['track']['license']}).",
            "Keep the license; include attribution if required (already added to the description).")
    order = {"low": 0, "medium": 1, "high": 2}
    overall = max((order[r["level"]] for r in risks), default=0)
    review_due = (_dt.date.today() - _dt.date.fromisoformat(POLICY_LAST_VERIFIED)).days > POLICY_REVIEW_DAYS
    return {
        "overall_risk": ["low", "medium", "high"][overall],
        "risks": risks,
        "content_flags": content_flags,
        "needs_human_review": [
            "Visual content (nudity, gore, dangerous stunts) is not analysed by this heuristic.",
            "Song identification is not performed; only 'possible music' is detected.",
            "Fair use / transformation is a legal judgement this tool cannot make.",
        ],
        "disclaimer": "Potential risks only, not confirmed violations. YouTube makes all final decisions; "
                      "nothing here guarantees approval, monetization, reach, or freedom from claims or strikes.",
        "policy_last_verified": POLICY_LAST_VERIFIED,
        "policy_review_due": review_due,
        "sources": OFFICIAL_SOURCES,
    }
