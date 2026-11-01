---
name: blade-ponytail
description: Lean mode for Blade Editor video work - reach the requested edit with the fewest tool calls, renders and tokens, with hard limits that stop analysis and revision loops. Use together with blade-edit on every Blade Editor job, and whenever the user mentions tokens, speed, "simple", or a job starts to repeat itself.
---

# Blade ponytail: the lazy senior editor

The best edit is the one made once. Get the whole result with the least work.

## Budget for one edit (hard limits)

| Step | Limit |
|---|---|
| `analyze_video` / `reference_breakdown` per file | 1 (a 2nd only after `verify_cuts` shows a real error) |
| `verify_cuts` per file | 1 |
| `view_frames` per file | 2 (12-16 frames; `every=0.1` only on a short part) |
| previews | 2 |
| final renders | 1, plus at most 2 revision rounds the user asks for |
| `compare_videos` | 1 per final |

When a limit is reached: stop, deliver the best result, and say in one line what is still
different. Never start a third pass on the same doubt.

## Lazy order (take the first that works)

1. `auto_edit` already gives the edit? Use it.
2. `auto_edit` + small EDL changes (camera keys from `reference_breakdown`, text, ramps)?
3. A hand-written EDL with presets (`camera_preset`, grades, effects).
4. Kinetograph only for what the EDL cannot draw (3D, designed graphics).
5. Google Flow only for shots the user does not have.

## Save tokens

- Read the saved JSON path instead of asking for an analysis again.
- Keep EDLs small: reuse effect lists, do not repeat unchanged clips in your messages.
- Show the user results, not tool logs. Short progress lines.
- Do not print long keyframe lists back to the user.

## Never cut

The user's explicit requests, the quality check, honest limits, credit-spending confirmation
for Google Flow.
