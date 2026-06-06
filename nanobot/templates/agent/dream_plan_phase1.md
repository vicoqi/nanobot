Review the available context and maintain the proactive delivery plan in `skills/daily-channel-delivery/PLAN.md`.

Output one line only:
[PLAN] concise directive describing how the plan should change

Use [SKIP] only if there is no plausible proactive topic and today's plan has already been reviewed.

Rules:
- The plan has two layers: a durable Strategy Layer and a Daily Intent Layer for today's proactive delivery.
- If the current plan is a legacy v1 shape with `# Dream Managed State`, recommend migrating it to the two-layer shape while preserving useful signals and candidates.
- The Daily Intent Layer should be refreshed once per local day, even when there is no new archived history.
- Do not draft the final user-facing message; write the intent, hook, reply question, fetch policy, and output contract.
- Today's intent must use the exact V2 keys: `date`, `status`, `delivery_type`, `topic`, `why_today`, `signal_source`, `audience`, `tone`, `message_goal`, `hook`, `reply_question`, `fetch_policy`, `output_contract`.
- Do not use aliases such as `type`, `intent`, `goal`, or legacy `Active Delivery` fields.
- Prefer strong signals: explicit requests, repeated follow-ups, corrected preferences, recurring utility-seeking topics.
- The candidate can be an informative update, a contextual check-in, or a grounded offer of help — not just a brief or digest.
- Avoid generic "how are you" pings; if suggesting a question, tie it to the user's recent context, projects, routines, or concerns.
- If signals are mixed or incomplete but still plausibly useful, emit a candidate [PLAN] directive anyway instead of staying silent.
- Low confidence is acceptable; use candidate backups and cautious tone rather than overcommitting.
- Rotate delivery types to avoid a mechanical daily report: contextual_followup, useful_brief, curiosity_hook, action_offer, gentle_checkin.
- Keep today's intent concrete enough that the executor can produce one concise message with a specific reply question.
- Keep the first candidate backup concrete enough that the executor could use it as a provisional fallback if today's intent is empty.
- Update the plan when today's topic, delivery type, hook, reply question, audience, tone, fetch approach, output contract, confidence, or suppress rules should change.
- Use `status: inactive` only when history indicates proactive delivery should pause, stop, or remain disabled.
- Do not output [FILE], [FILE-REMOVE], or [SKILL] lines.
