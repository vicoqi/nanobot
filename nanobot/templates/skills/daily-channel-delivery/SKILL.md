---
name: daily-channel-delivery
description: Execute a Dream-maintained proactive delivery plan and output one final user-facing message.
---

# Daily Channel Delivery

Use this skill when a scheduled job asks you to produce one proactive delivery for the user.

## Files

- Execution plan: `skills/daily-channel-delivery/PLAN.md`
- Optional supporting skills: read any skill files referenced by the plan

## Steps

1. Read `skills/daily-channel-delivery/PLAN.md`.
2. If the plan is missing or inactive, return exactly `All clear.` and stop.
3. Prefer the `Active Delivery` section when it contains a concrete delivery.
4. If `Active Delivery` is empty, incomplete, or has no usable `id`, scan `Candidate Backups`. If the first concrete candidate backup is executable, treat it as a provisional delivery for this run instead of returning `All clear.`.
5. Follow the selected delivery's topic, fetch policy, and output contract.
6. If the selected delivery references another skill or data source, read it before acting.
7. Gather fresh information at run time. Do not rely on stale values stored in the plan.
8. If the plan's confidence is low, keep the message especially cautious, concise, and utility-focused rather than suppressing delivery.
9. Output only the final user-facing message for delivery.

## Rules

- Do not quote the plan or expose raw commands unless the plan explicitly requires it.
- Do not emit internal reasoning, progress, or file names.
- Do not rewrite the plan while executing it.
- If `Active Delivery` is unusable but a concrete candidate backup exists, prefer the first concrete candidate backup over returning `All clear.`.
- If neither `Active Delivery` nor any candidate backup is concrete enough to execute, return exactly `All clear.`.
- If the plan says no delivery is needed today, return exactly `All clear.`.
- Keep the final message concise and useful.

## Example

If the plan says to send a Shanghai weather brief:

1. Read the plan.
2. Run the fetch command or referenced weather workflow.
3. Summarize the fresh result in the requested tone and length.
4. Return only the final weather message.
