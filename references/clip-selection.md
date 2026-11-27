# Clip selection

## Signals (per second, robust-normalized across the video, weighted per template)
| Signal | Meaning |
|---|---|
| `audio_spike` | sharp loudness peak: reaction, laugh, scream, impact |
| `audio_energy` | sustained louder-than-usual stretch |
| `motion` | visual action |
| `scene_change` | cuts and big visual changes |
| `speech` | words per second (conversation density) |
| `laughter`, `surprise`, `excitement`, `emotion`, `story`, `question` | transcript cue phrases (`clip_selector.CUES`) |

Silent, low-action seconds are penalized. Each template's `selection.weights` sets what matters, so for
example gaming weights spikes and excitement, while storytelling weights story markers and speech.

## Building a candidate
1. Find peaks of the smoothed interest curve, **only in unused footage** (completed and in-progress clips
   are masked out).
2. Open the window `lead_in` seconds before the peak, so the viewer sees the cause and the reaction.
3. **Snap the start** to the nearest sentence start (or the end of a silence). **Snap the end** to a sentence
   end at least 3 s after the peak, within the template's min and max. Never cut mid-word. Keep a breath of
   air at both ends.
4. Score it: mean interest + peak + **hook** (the first 3 s) + clean ending + speech coverage − dead air.
5. Non-maximum suppression: two candidates may share at most 10% of the shorter one.
6. If strong peaks run out, fall back to evenly spread unused windows (labelled `fallback`).

## The agent's review (required for quality)
Signals find *energy*. They don't understand *story*. For each top candidate, read the `excerpt` and check:
- **Opening:** does the first sentence pull you in? If not, move the start to a stronger line, but don't drop
  the setup the payoff needs.
- **Center:** is there a clear event, statement, joke or play?
- **Payoff and ending:** does it end after the reaction or punchline lands, not mid-thought?
- **Context:** will a stranger understand it without the full video? If not, extend it. Context beats brevity.
- **Meaning:** does the trim keep what the speaker meant? Never splice separate moments into a new claim.
- **Duplicates:** compare against `previously_completed`. Similar topics are fine, but the same moment is not.

Ranking: put the most engaging, most self-contained clip first. The first 3 Shorts should be the strongest.

## Overlap rules
- The engine allows up to `min(2 s, 10% of the clip)` of overlap with used footage (a shared lead-in).
- Larger overlaps in a plan are dropped unless the clip has `"overlap_reason"` (for example "different angle on
  the same play, user asked"). Use this only for a strong editorial reason.
