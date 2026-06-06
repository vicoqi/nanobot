Update `{{ plan_path }}` based on the analysis below.

## Allowed file path (relative to workspace root)
- `{{ plan_path }}`

Do NOT edit any other file.

## Editing rules
- Edit directly — the current plan contents are provided below, no read_file needed
- Keep `# Fixed Contract` intact
- Edit only frontmatter, `# Strategy Layer`, and `# Daily Intent Layer`
- Prefer one batched `edit_file` call; use `write_file` only if the plan is truly missing
- Use exact text as old_text, include surrounding blank lines for unique match
- Surgical edits only — never rewrite the entire file unless it is missing
- If the current plan is a legacy v1 shape with `# Dream Managed State`, migrate it to the two-layer v2 shape while preserving useful signals and candidates.
- Remove legacy daily-intent fields such as `type`, `intent`, `goal`, `language`, `Inputs`, `Fetch Policy`, and `Output Contract` from `Today Delivery Intent`.
- If today's plan has not been reviewed yet, update `last_daily_reviewed_on` and `Today Delivery Intent` instead of stopping.
- If new history changes long-term interests or preferences, update `last_strategy_reviewed_at` and the Strategy Layer too.
- If today's plan has already been reviewed and analysis says [SKIP], stop without calling tools.

## Plan rules
- Maintain durable proactive-delivery strategy plus today's delivery intent, not today's final user-facing message
- Today's intent may describe an informative update, a contextual check-in, a curiosity hook, or a grounded offer of help
- `Today Delivery Intent` must contain exactly these V2 keys, in this order:
  - `date`
  - `status`
  - `delivery_type`
  - `topic`
  - `why_today`
  - `signal_source`
  - `audience`
  - `tone`
  - `message_goal`
  - `hook`
  - `reply_question`
  - `fetch_policy`
  - `output_contract`
- Do not use aliases such as `type`, `intent`, `goal`, or legacy `Active Delivery` fields.
- Prefer strong signals from the conversation history, but low-confidence candidates are acceptable
- Rotate delivery types to avoid repetitive daily reports
- Keep `Today Delivery Intent` concrete enough for the executor to output one concise message ending with a specific reply question
- Keep the first candidate backup concrete enough that the executor could use it when today's intent is empty
- Use `status: inactive` only when the evidence says proactive delivery should pause, stop, or remain disabled
- When evidence is partial, prefer a cautious candidate backup over leaving the plan empty
- Preserve stable structure and concise bullets
