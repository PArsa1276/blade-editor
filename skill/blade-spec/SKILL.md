---
name: blade-spec
description: Spec-driven workflow for Blade Editor video edits (adapted from spec-kit) - turn the request into a short edit spec, plan shots and tools, render once, verify against the spec, then converge. Use for any Blade Editor edit that has a reference, more than one source clip, or more than one requirement.
---

# Blade spec: brief -> spec -> plan -> build -> verify

Keep every artefact short. Write them in the chat only as compact lists; save nothing extra.

## 1. Spec (what "done" means) - before any render

- **Output:** length, aspect/size, platform, file size limit.
- **Must keep (locks):** song, title text, a shot, a colour, "no text", etc.
- **Style target:** from the reference breakdown: cuts/s, shot length, flashes/s, camera moves,
  grade - or a preset name.
- **Acceptance checks:** `quality_check` clean; style table within ~30% of the reference;
  every lock present.
- **Not possible / approximate:** from the decision gate in blade-edit. Tell the user now.

Ask a question only when a missing fact changes the result (for example the length). Otherwise
choose a sensible default and write it in the spec.

## 2. Plan (shot list)

One line per output shot: time range, source clip + in/out, tool(s) (`camera` keys/preset,
effects, ramp, overlay, Kinetograph, Flow), text, sfx. Map every reference shot you rebuild.

## 3. Build

One preview of the whole edit (`render_edl preview=true`), `view_frames` on it, fix, then the
final render. Follow blade-ponytail limits.

## 4. Verify (against the spec, not against taste)

Run the acceptance checks. For each failed check: fix once if a tool can fix it; otherwise list
it as a limit. Do not loop.

## 5. Deliver

Path of the final file, the spec checks with pass/fail, and the honest limits - in a few lines.
