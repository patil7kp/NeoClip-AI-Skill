# YouTube policies: what the compliance module checks

**Last verified against official YouTube Help pages: 2026-11-27.** The engine sets `policy_review_due: true`
30 days after that date. When that happens, or when the user plans to monetize or asks a policy question,
open the official pages below and check for changes before giving advice. Prefer official YouTube
Help and policy pages over blogs. Policies change.

> Everything here is **risk screening**, not a ruling. Separate *potential risks* from *confirmed
> violations*. Never promise approval, monetization, freedom from claims or strikes, or reach.
> YouTube makes the final enforcement decisions.

## Official sources
| Topic | URL |
|---|---|
| Community Guidelines | https://www.youtube.com/howyoutubeworks/policies/community-guidelines/ |
| Age-restricted content | https://support.google.com/youtube/answer/2802167 |
| Copyright basics | https://support.google.com/youtube/answer/2797466 |
| How Content ID works | https://support.google.com/youtube/answer/2797370 |
| Fair use | https://support.google.com/youtube/answer/9783148 |
| Advertiser-friendly content guidelines | https://support.google.com/youtube/answer/6162278 |
| YouTube channel monetization policies (reused and inauthentic content) | https://support.google.com/youtube/answer/1311392 |
| Three-minute Shorts | https://support.google.com/youtube/answer/15424877 |
| Spam, deceptive practices and scams (metadata) | https://support.google.com/youtube/answer/2801973 |
| Hashtags | https://support.google.com/youtube/answer/6390658 |
| Audio Library | https://support.google.com/youtube/answer/3376882 |

## Key facts used by the checker (as verified on the date above)
- **Shorts format:** square or vertical videos up to **3 minutes** are Shorts (for uploads on or after
  15 Oct 2024). 16:9 stays long-form.
- **Content ID and long Shorts:** a Short **longer than 1 minute with an active Content ID claim is blocked
  globally** (it can't be viewed or monetized until the claim is resolved). The checker flags Shorts over
  60 s, with higher severity if third-party audio or footage may be present.
- **Shorts audio:** most Shorts Audio Library songs can be used for up to 90 s in a 3-minute Short (some
  tracks are limited to 60 or 30 s). Royalty-free tracks from the YouTube Audio Library don't receive Content
  ID claims. The skill only uses tracks the user has verified (see `music-guidelines.md`).
- **Reused content (YPP):** repurposing content that's already on YouTube or elsewhere without meaningful
  original commentary, education or narrative can make a channel ineligible for monetization. This applies
  *even with the owner's permission* and is separate from copyright. Reactions with real commentary, critical
  reviews and edited footage with an added storyline are examples of meaningful changes. Content that relies
  mostly on non-verbal reactions without added commentary is not.
- **Inauthentic content (formerly "repetitious content", renamed 15 Jul 2025):** mass-produced, templated or
  repetitive uploads with little variation can lose monetization. The checker warns at 10+ Shorts generated on
  one date. The agent should encourage variety and real commentary.
- **Hashtags:** a video with more than 60 hashtags has all of its hashtags ignored. Misleading or irrelevant
  hashtags can lead to removal. The engine caps at 6 and warns above 8. It reports an error above 15.
- **Metadata:** titles, thumbnails and descriptions that mislead viewers about the content break spam and
  deceptive practices policies. The checker flags ALL CAPS, excess punctuation and common clickbait phrases.
  Only the agent can judge whether a title matches the clip.

## What the checker does (`scripts/policy_checker.py`)
| Area | Method | Output |
|---|---|---|
| Possible music | audio heuristic overlapping the clip | `copyright_music` risk + timestamps |
| Third-party footage | rights basis given by the user | `copyright_third_party`, `reused_content` |
| >60 s Shorts | duration | `copyright_shorts_over_60s` |
| Age and ad suitability | transcript lexicon: strong language, violence, sexual, drugs, dangerous acts, self-harm, hate | `age_or_ads_*` with source and Short timestamps, masked terms |
| Age-restricted source | `age_limit` from YouTube metadata | `age_restricted_source` |
| Metadata | title, description and hashtag rules | `metadata` |
| Volume | Shorts per date | `inauthentic_content` |

**Not covered (needs human review):** visual nudity, gore or dangerous stunts, song identification, and fair-use
analysis. The report lists these every time under `needs_human_review`.

## How to communicate the risk
- Use words like "potential", "may", and "could be claimed".
- Give the timestamp and a concrete remedy (trim, mute, bleep, add commentary, keep it under 60 s, pick another moment).
- Mention that credit does not equal permission, and that short length does not equal fair use.
- For anything high-risk, suggest the user review the moment themselves or skip it.
