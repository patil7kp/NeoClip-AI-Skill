# Workflow: clip selection

1. Take the top `count × 2` candidates from `analyze`.
2. For each one, read the `excerpt` and `reasons`, then apply the checklist in `references/clip-selection.md`
   (opening, center, payoff, ending, context, meaning, no duplicates).
3. Adjust the boundaries when needed. Use whole sentences. Timestamps can be seconds or `HH:MM:SS(.mmm)`.
   - Extend backward if the setup is missing. Extend forward if the reaction or punchline is cut off.
   - Keep clips ≤ 60 s when third-party audio or footage may be present (Content ID rule for longer Shorts).
4. Order the plan by quality. The first Short is the best one.
5. Write the slug, title, description, hashtags and optional hook_text (see `metadata-generation.md`).
6. If fewer good moments exist than requested, say so. Don't pad the plan with weak clips. Offer to pick
   from lower-ranked candidates if the user still wants them.
