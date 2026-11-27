# Copyright guidelines

## Rights gate (enforced by the engine)
Every run needs `--rights`:
| Value | Meaning | Residual risk |
|---|---|---|
| `own` | the user made the video or owns the channel | lowest, but third-party music or clips *inside* it can still be claimed |
| `permission` | written permission from the rights holder | Content ID may still claim unless the owner whitelists the channel; reused-content rules still apply for monetization |
| `licensed` | a license that covers editing and republishing | keep the license; scope matters |
| `creative-commons` | CC-BY or similar | follow the attribution terms exactly; NC/ND licenses may not allow this use |
| `public-domain` | no copyright | check that the specific copy is public domain (restorations can carry new rights) |

There is deliberately **no "fair use" option**. Fair use is a legal defence decided case by case, and the tool
can't make that call. If a user believes their use is fair use (for example commentary or criticism), explain
that this is their own legal judgement, point to https://support.google.com/youtube/answer/9783148, and don't
process the video on that basis alone.

## Myths to correct
- "I gave credit, so it's fine." Credit is not permission.
- "It's under 60 seconds / 10 seconds." No length makes a clip automatically legal.
- "It says no copyright intended." That disclaimer has no legal effect.
- "It's a reaction." Only *meaningful* commentary counts toward transformation, and it is judged case by case.
- "Everyone does it." Content ID and claims don't care.

## Content ID risk factors (flagged in reports)
- Music anywhere in the clip, including background music in a stream or a game soundtrack.
- TV, film or sports footage on screen (for example a streamer watching a video). These need human review, and
  the heuristic may not see them.
- Shorts longer than 60 s with any claim are blocked globally.

## Safer alternatives to recommend
- Use the user's own videos, or footage from creators who explicitly allow clipping. Some creators run clipping
  programs with stated terms, so read those terms.
- Mute or trim music sections. Use verified YouTube Audio Library tracks.
- Add original commentary (a voice-over) and analysis for real transformation. This also matters for the
  reused-content rules.
- Keep Shorts that contain third-party material under 60 s.

## Credit (still required when appropriate)
For non-owned sources, the metadata includes the original creator, a clickable channel link and the original
video link (with a timestamp). Credit comes *in addition to* rights, never *instead of* them.
