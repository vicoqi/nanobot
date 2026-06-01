Review recent conversation history and maintain the proactive delivery strategy in `skills/daily-channel-delivery/PLAN.md`.

Output one line only:
[PLAN] concise directive describing how the plan should change

Use [SKIP] only if the history provides no plausible proactive topic and the existing plan needs no adjustment.

Rules:
- The plan is a durable strategy document, not today's final message.
- Prefer strong signals: explicit requests, repeated follow-ups, corrected preferences, recurring utility-seeking topics.
- The candidate can be an informative update, a contextual check-in, or a grounded offer of help — not just a brief or digest.
- Avoid generic "how are you" pings; if suggesting a question, tie it to the user's recent context, projects, routines, or concerns.
- If signals are mixed or incomplete but still plausibly useful, emit a candidate [PLAN] directive anyway instead of staying silent.
- Low confidence is acceptable; use candidate backups and cautious tone rather than overcommitting.
- Keep the first candidate concrete enough that the executor could use it as a provisional fallback if `Active Delivery` is empty.
- Update the plan when the active topic, audience, tone, inputs, references, fetch approach, output contract, confidence, or suppress rules should change.
- Use `status: inactive` only when history indicates proactive delivery should pause, stop, or remain disabled.
- Do not output [FILE], [FILE-REMOVE], or [SKILL] lines.
