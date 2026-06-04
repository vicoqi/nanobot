---
version: 2
last_strategy_reviewed_at: ""
last_daily_reviewed_on: ""
status: inactive
confidence: low
---

# Fixed Contract

- This file is consumed by `skills/daily-channel-delivery/SKILL.md`.
- Keep this structure stable.
- Store durable strategy and today's delivery intent.
- Do not store the final drafted user-facing message here.

# Strategy Layer

## User Interest Model

### Strong Signals

- (none yet)

### Negative Signals

- (none yet)

## Delivery Principles

- Chinese by default; address the user according to `USER.md`.
- Keep proactive delivery short, specific, and easy to reply to.
- Prefer recent context over generic reminders.
- Avoid generic check-ins like "how are you" unless tied to concrete context.
- Low confidence is allowed, but use a cautious offer instead of overclaiming.

## Delivery Type Rotation

- contextual_followup: continue a recent topic with a useful next step.
- useful_brief: provide a compact data-driven update.
- curiosity_hook: surface a small observation worth discussing.
- action_offer: offer to do one concrete thing for the user.
- gentle_checkin: ask a context-aware question, not a generic greeting.

## Topic Rotation Rules

- Do not use the same topic two days in a row unless the user continued it.
- Do not duplicate a separate weather job unless weather is the clear user need.
- Workday mornings may prioritize market or project context; weekends may prioritize life, family, or local plans.
- Prefer topics with available skills or stable data sources.

# Daily Intent Layer

## Today Delivery Intent

Required exact keys. Do not use aliases such as `type`, `intent`, or `goal`.

- date:
- status: inactive
- delivery_type:
- topic:
- why_today:
- signal_source:
- audience:
- tone:
- message_goal:
- hook:
- reply_question:
- fetch_policy:
- output_contract: 1-3 concise user-facing sentences, ending with one concrete reply question.

## Candidate Backups

- Candidate backups should be concrete enough to execute if needed.
- If `Today Delivery Intent` is empty or incomplete, the executor may use the first concrete candidate backup for that run.
- (none yet)

## Recent Delivery State

| date | delivery_type | topic | note |
| --- | --- | --- | --- |
| (none yet) | | | |

## Suppress Rules

- If `status` is `inactive`, no delivery should be sent.
- If `confidence` is `low`, delivery may still be sent, but keep it cautious and high-signal.
