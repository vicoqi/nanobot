---
version: 1
last_reviewed_at: ""
status: inactive
active_delivery_id: ""
confidence: low
---

# Fixed Contract

- This file is consumed by `skills/daily-channel-delivery/SKILL.md`.
- Keep this structure stable.
- Do not store the final user-facing message here.
- Store durable strategy, not transient data.
- Active delivery may be an update, a contextual check-in, or an offer of help.

# Dream Managed State

## User Interest Model

### Strong Signals

- (none yet)

### Negative Signals

- (none yet)

## Active Delivery

- id:
- why_now:
- audience:
- language:
- tone:

### Inputs

- (none yet)

### Fetch Policy

1. Gather fresh information at send time.
2. Use referenced skills or tools only when the active delivery needs them.

### References

- (optional skill paths or data source notes)

### Output Contract

- Keep it concise and user-facing.

## Candidate Backups

- Candidate backups should be concrete enough to execute if needed.
- If `Active Delivery` is empty or incomplete, the executor may use the first concrete candidate backup for that run.
- (none yet)

## Suppress Rules

- If `status` is `inactive`, no delivery should be sent.
- If `confidence` is `low`, delivery may still be sent, but keep it cautious and high-signal.
